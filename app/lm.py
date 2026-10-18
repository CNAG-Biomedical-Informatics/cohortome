from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request
from urllib.parse import urlparse
from uuid import uuid4

from app.config import BASE_DIR, RUNS_ROOT_DIR, STATE_ROOT_DIR
from app.env import app_env
from app.state_io import advisory_file_lock, atomic_write_json

LM_DEBUG_DIR = RUNS_ROOT_DIR / "lm-debug"
DEFAULT_LLM_PROVIDER_ID = "system-default"
LLM_PROVIDER_DATA_BOUNDARIES = {"local", "external"}
DEFAULT_LLM_PROVIDER_DATA_BOUNDARY = "external"
LLM_PROVIDER_REGISTRY_PATH = STATE_ROOT_DIR / "llm" / "providers.json"
_SAFE_LLM_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_CURRENT_PROVIDER_ID: ContextVar[str] = ContextVar("patient_workspace_lm_provider_id", default=DEFAULT_LLM_PROVIDER_ID)


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_lm_provider_data_boundary(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in LLM_PROVIDER_DATA_BOUNDARIES:
        return normalized
    return DEFAULT_LLM_PROVIDER_DATA_BOUNDARY


def _system_default_provider() -> Dict[str, Any]:
    return {
        "id": DEFAULT_LLM_PROVIDER_ID,
        "label": "System default (LM Studio)",
        "base_url": os.getenv("LM_STUDIO_BASE_URL", "http://192.168.1.42:1234/v1").rstrip("/"),
        "model": os.getenv("LM_STUDIO_MODEL", "").strip(),
        "api_key": os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
        "api_key_env": "LM_STUDIO_API_KEY",
        "timeout": lm_studio_timeout(),
        "enabled": _truthy(os.getenv("LM_STUDIO_ENABLED", "")),
        "data_boundary": normalize_lm_provider_data_boundary(os.getenv("LM_STUDIO_DATA_BOUNDARY", "")),
        "source": "environment",
    }


def _normalize_provider(raw: Dict[str, Any], *, source: str | None = None) -> Dict[str, Any] | None:
    provider_id = str(raw.get("id") or "").strip()
    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    if not provider_id or not base_url:
        return None
    api_key_env = str(raw.get("api_key_env") or "").strip()
    api_key = str(raw.get("api_key") or "").strip()
    if api_key_env:
        api_key = os.getenv(api_key_env, api_key or "lm-studio")
    timeout = raw.get("timeout", raw.get("timeout_seconds", lm_studio_timeout()))
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        timeout_value = lm_studio_timeout()
    return {
        "id": provider_id,
        "label": str(raw.get("label") or provider_id).strip() or provider_id,
        "base_url": base_url,
        "model": str(raw.get("model") or "").strip(),
        "api_key": api_key or "lm-studio",
        "api_key_env": api_key_env,
        "timeout": timeout_value,
        "enabled": bool(raw.get("enabled", True)),
        "data_boundary": normalize_lm_provider_data_boundary(raw.get("data_boundary")),
        "source": str(source or raw.get("source") or "configuration"),
        "api_key_configured": bool(api_key_env or str(raw.get("api_key") or "").strip()),
    }


def _configured_registry_providers() -> list[Dict[str, Any]]:
    raw = app_env("COHORTOME_LLM_PROVIDERS_JSON", "").strip()
    if not raw:
        registry_path = app_env("COHORTOME_LLM_PROVIDERS_FILE", "").strip()
        if registry_path:
            try:
                path = BASE_DIR.joinpath(registry_path) if not os.path.isabs(registry_path) else Path(registry_path)
                raw = path.read_text(encoding="utf-8")
            except OSError:
                raw = ""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        items = parsed.get("llm_providers", parsed.get("providers"))
    else:
        items = parsed
    if not isinstance(items, list):
        return []
    providers: list[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            provider = _normalize_provider(item, source="configuration")
            if provider:
                providers.append(provider)
    return providers


def _managed_registry_lock_path():
    return LLM_PROVIDER_REGISTRY_PATH.with_name(f".{LLM_PROVIDER_REGISTRY_PATH.name}.lock")


def _desktop_default_editable() -> bool:
    return _truthy(app_env("COHORTOME_DESKTOP_MODE"))


def initialize_desktop_default_provider() -> None:
    """Seed once in the isolated desktop runtime, never overwrite user settings."""
    if not _desktop_default_editable():
        raise RuntimeError("Desktop provider initialization requires desktop mode.")
    with advisory_file_lock(_managed_registry_lock_path()):
        providers = _read_managed_registry_unlocked()
        if any(item["id"] == DEFAULT_LLM_PROVIDER_ID for item in providers):
            return
        providers.append(_canonical_managed_provider({
            "id": DEFAULT_LLM_PROVIDER_ID,
            "label": "System default (LM Studio)",
            "base_url": "http://127.0.0.1:1234/v1",
            "enabled": False,
            "data_boundary": "external",
        }))
        _write_managed_registry_unlocked(providers)


def _canonical_managed_provider(raw: Dict[str, Any]) -> Dict[str, Any]:
    provider_id = str(raw.get("id") or "").strip().lower()
    if not _SAFE_LLM_PROVIDER_ID_RE.fullmatch(provider_id):
        raise ValueError("Provider ID must start with a lowercase letter or number and contain only lowercase letters, numbers, dots, underscores, or hyphens (maximum 64 characters).")
    if provider_id == DEFAULT_LLM_PROVIDER_ID and not _desktop_default_editable():
        raise ValueError("The system-default provider is managed by environment configuration.")

    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Base URL must be a complete http:// or https:// URL.")
    if parsed_url.username or parsed_url.password:
        raise ValueError("Base URL must not contain credentials; use the API key field instead.")

    try:
        timeout = float(raw.get("timeout_seconds", raw.get("timeout", 30)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Timeout must be a number between 1 and 300 seconds.") from exc
    if timeout < 1 or timeout > 300:
        raise ValueError("Timeout must be between 1 and 300 seconds.")

    boundary = str(raw.get("data_boundary") or DEFAULT_LLM_PROVIDER_DATA_BOUNDARY).strip().lower()
    if boundary not in LLM_PROVIDER_DATA_BOUNDARIES:
        raise ValueError("Data boundary must be local or external.")

    return {
        "id": provider_id,
        "label": str(raw.get("label") or provider_id).strip() or provider_id,
        "base_url": base_url,
        "model": str(raw.get("model") or "").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
        "timeout_seconds": timeout,
        "enabled": bool(raw.get("enabled", True)),
        "data_boundary": boundary,
    }


def _read_managed_registry_unlocked() -> list[Dict[str, Any]]:
    if not LLM_PROVIDER_REGISTRY_PATH.exists():
        return []
    try:
        payload = json.loads(LLM_PROVIDER_REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Managed LLM provider registry is invalid; refusing to replace it.") from exc
    except OSError as exc:
        raise RuntimeError("Managed LLM provider registry could not be read.") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Managed LLM provider registry must contain a JSON array; refusing to replace it.")
    providers: list[Dict[str, Any]] = []
    seen: set[str] = set()
    try:
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Provider records must be JSON objects.")
            provider = _canonical_managed_provider(item)
            if provider["id"] in seen:
                raise ValueError(f"Duplicate managed provider ID: {provider['id']}.")
            seen.add(provider["id"])
            providers.append(provider)
    except ValueError as exc:
        raise RuntimeError(f"Managed LLM provider registry is invalid: {exc}") from exc
    return providers


def _read_managed_registry() -> list[Dict[str, Any]]:
    with advisory_file_lock(_managed_registry_lock_path()):
        return _read_managed_registry_unlocked()


def _write_managed_registry_unlocked(providers: list[Dict[str, Any]]) -> None:
    atomic_write_json(LLM_PROVIDER_REGISTRY_PATH, providers, file_mode=0o600)


def _managed_registry_providers() -> tuple[list[Dict[str, Any]], str]:
    try:
        records = _read_managed_registry()
    except RuntimeError as exc:
        return [], str(exc)
    providers = [
        provider
        for record in records
        if (provider := _normalize_provider(record, source="runtime")) is not None
    ]
    return providers, ""


def _readonly_provider_ids() -> set[str]:
    provider_ids = set() if _desktop_default_editable() else {DEFAULT_LLM_PROVIDER_ID}
    provider_ids.update(str(item.get("id") or "").strip().lower() for item in _configured_registry_providers())
    return provider_ids


def create_managed_lm_provider(raw: Dict[str, Any]) -> Dict[str, Any]:
    provider = _canonical_managed_provider(raw)
    if provider["id"] in _readonly_provider_ids():
        raise ValueError("That provider ID is already managed by environment configuration.")
    with advisory_file_lock(_managed_registry_lock_path()):
        providers = _read_managed_registry_unlocked()
        if any(item["id"] == provider["id"] for item in providers):
            raise ValueError("A managed provider with that ID already exists.")
        providers.append(provider)
        _write_managed_registry_unlocked(providers)
    normalized = _normalize_provider(provider, source="runtime")
    return public_llm_provider(normalized or provider)


def update_managed_lm_provider(provider_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    normalized_id = str(provider_id or "").strip().lower()
    if normalized_id in _readonly_provider_ids():
        raise ValueError("This provider is managed by environment configuration and is read-only in the app.")
    with advisory_file_lock(_managed_registry_lock_path()):
        providers = _read_managed_registry_unlocked()
        index = next((index for index, item in enumerate(providers) if item["id"] == normalized_id), None)
        if index is None:
            raise ValueError("Managed provider not found.")
        merged = dict(providers[index])
        for field in ("label", "base_url", "model", "timeout_seconds", "enabled", "data_boundary"):
            if field in updates and updates[field] is not None:
                merged[field] = updates[field]
        if str(updates.get("api_key") or "").strip():
            merged["api_key"] = str(updates["api_key"]).strip()
        merged["id"] = normalized_id
        providers[index] = _canonical_managed_provider(merged)
        _write_managed_registry_unlocked(providers)
    normalized = _normalize_provider(providers[index], source="runtime")
    return public_llm_provider(normalized or providers[index])


def delete_managed_lm_provider(provider_id: str) -> None:
    normalized_id = str(provider_id or "").strip().lower()
    if normalized_id == DEFAULT_LLM_PROVIDER_ID and _desktop_default_editable():
        raise ValueError("The default provider cannot be deleted. Disable it instead.")
    if normalized_id in _readonly_provider_ids():
        raise ValueError("This provider is managed by environment configuration and cannot be deleted in the app.")
    with advisory_file_lock(_managed_registry_lock_path()):
        providers = _read_managed_registry_unlocked()
        remaining = [item for item in providers if item["id"] != normalized_id]
        if len(remaining) == len(providers):
            raise ValueError("Managed provider not found.")
        _write_managed_registry_unlocked(remaining)


def llm_providers(include_disabled: bool = True) -> list[Dict[str, Any]]:
    providers = [_system_default_provider()]
    seen = {DEFAULT_LLM_PROVIDER_ID}
    for item in _configured_registry_providers():
        if item["id"] in seen:
            providers = [item if provider["id"] == item["id"] else provider for provider in providers]
        else:
            providers.append(item)
            seen.add(item["id"])
    managed, _registry_error = _managed_registry_providers()
    for item in managed:
        if item["id"] == DEFAULT_LLM_PROVIDER_ID and _desktop_default_editable() and item["id"] not in _readonly_provider_ids():
            providers = [item if provider["id"] == item["id"] else provider for provider in providers]
        elif item["id"] not in seen:
            providers.append(item)
            seen.add(item["id"])
    if not include_disabled:
        providers = [item for item in providers if item.get("enabled")]
    return providers


def public_llm_provider(provider: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(provider.get("id") or ""),
        "label": str(provider.get("label") or provider.get("id") or ""),
        "base_url": str(provider.get("base_url") or ""),
        "model": str(provider.get("model") or "") or None,
        "enabled": bool(provider.get("enabled", True)),
        "data_boundary": normalize_lm_provider_data_boundary(provider.get("data_boundary")),
        "source": str(provider.get("source") or "configuration"),
        "managed": str(provider.get("source") or "") == "runtime",
        "timeout_seconds": float(provider.get("timeout", lm_studio_timeout())),
        "api_key_configured": bool(provider.get("api_key_configured", provider.get("api_key") or provider.get("api_key_env"))),
    }


def resolve_lm_provider(provider_id: str | None = None) -> Dict[str, Any]:
    selected = str(provider_id or _CURRENT_PROVIDER_ID.get() or DEFAULT_LLM_PROVIDER_ID).strip() or DEFAULT_LLM_PROVIDER_ID
    providers = llm_providers(include_disabled=True)
    for provider in providers:
        if provider["id"] == selected:
            return provider
    return providers[0]


def lm_provider_data_boundary(provider_id: str | None = None) -> str:
    return normalize_lm_provider_data_boundary(resolve_lm_provider(provider_id).get("data_boundary"))


@contextmanager
def lm_provider_context(provider_id: str | None):
    token = _CURRENT_PROVIDER_ID.set(str(provider_id or DEFAULT_LLM_PROVIDER_ID).strip() or DEFAULT_LLM_PROVIDER_ID)
    try:
        yield
    finally:
        _CURRENT_PROVIDER_ID.reset(token)


def lm_studio_enabled() -> bool:
    return bool(resolve_lm_provider().get("enabled", False))


def lm_studio_base_url() -> str:
    return str(resolve_lm_provider().get("base_url") or "").rstrip("/")


def lm_studio_timeout() -> float:
    raw = os.getenv("LM_STUDIO_TIMEOUT", "30").strip()
    try:
        return float(raw)
    except ValueError:
        return 30.0


def lm_studio_api_key() -> str:
    return str(resolve_lm_provider().get("api_key") or "lm-studio")


def lm_studio_debug_log_enabled() -> bool:
    value = os.getenv("LM_STUDIO_DEBUG_LOG", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def write_lm_studio_debug_log(
    *,
    kind: str,
    url: str,
    payload: Dict[str, Any] | None,
    response_body: Dict[str, Any] | None,
    elapsed_ms: float,
    error_text: str | None = None,
) -> None:
    if not lm_studio_debug_log_enabled():
        return
    try:
        LM_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LM_DEBUG_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid4().hex[:8]}.json"
        content = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kind": kind,
            "url": url,
            "elapsed_ms": round(elapsed_ms, 2),
            "request_chars": len(json.dumps(payload, ensure_ascii=True, separators=(",", ":"))) if payload is not None else 0,
            "response_chars": len(json.dumps(response_body, ensure_ascii=True, separators=(",", ":"))) if response_body is not None else 0,
            "request": payload,
            "response": response_body,
            "error": error_text,
        }
        log_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def http_json(url: str, payload: Dict[str, Any] | None = None, *, log_kind: str = "generic") -> Dict[str, Any]:
    started = time.time()
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {lm_studio_api_key()}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with request.urlopen(req, timeout=lm_studio_timeout()) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        write_lm_studio_debug_log(
            kind=log_kind,
            url=url,
            payload=payload,
            response_body=parsed,
            elapsed_ms=(time.time() - started) * 1000,
        )
        return parsed
    except Exception as exc:
        write_lm_studio_debug_log(
            kind=log_kind,
            url=url,
            payload=payload,
            response_body=None,
            elapsed_ms=(time.time() - started) * 1000,
            error_text=str(exc),
        )
        raise


def sanitize_lm_text(content: str) -> str:
    original = content.strip()
    split_markers = re.findall(r"<unused\d+>", original, flags=re.IGNORECASE)
    if split_markers:
        parts = re.split(r"<unused\d+>", original, flags=re.IGNORECASE)
        tail = parts[-1].strip()
        if tail:
            return tail

    text = re.sub(r"^\s*<unused\d+>thought\s*", "", original, flags=re.IGNORECASE)
    text = re.sub(r"^\s*thought\s*", "", text, flags=re.IGNORECASE)
    lines = text.splitlines()
    if not lines:
        return text.strip()

    reasoning_markers = (
        "the user wants to",
        "identify the core question",
        "analyze the request",
        "scan the context",
        "formulate the answer",
        "synthesize the findings",
        "evaluate if",
        "examine the",
        "look for data points",
        "read through the json",
        "provided json context",
    )

    def _is_reasoning_line(line: str) -> bool:
        lowered = line.strip().lower()
        if not lowered:
            return False
        # Lists and bold Markdown are valid answers, not evidence of reasoning.
        return any(marker in lowered for marker in reasoning_markers)

    first_non_empty = next((line for line in lines if line.strip()), "")
    if not _is_reasoning_line(first_non_empty):
        return text.strip()

    kept = []
    started_answer = False
    for line in lines:
        stripped = line.strip()
        if not started_answer:
            if not stripped:
                continue
            if _is_reasoning_line(stripped):
                continue
            started_answer = True
        if started_answer:
            kept.append(line)

    cleaned = "\n".join(kept).strip()
    return cleaned or text.strip()


def resolve_lm_studio_model(*, log_kind: str = "generic_models") -> str | None:
    configured = str(resolve_lm_provider().get("model") or "").strip()
    if configured:
        return configured
    try:
        payload = http_json(f"{lm_studio_base_url()}/models", log_kind=log_kind)
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    model_id = first.get("id")
    return model_id if isinstance(model_id, str) and model_id.strip() else None


def general_llm_reply(prompt: str, history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
    question = str(prompt or "").strip()
    if not question:
        raise ValueError("A question is required.")
    if not lm_studio_enabled():
        raise RuntimeError("The selected model provider is disabled.")

    model = resolve_lm_studio_model(log_kind="general_question_models")
    if not model:
        raise RuntimeError("No model is available from the selected provider.")

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are the general knowledge assistant inside COHORTome. "
                "Answer using general knowledge only. You have not been given access to the active "
                "workspace, datasets, patients, assays, analysis results, or application state. "
                "Do not imply that you inspected them. If a question requires the current workspace, "
                "explain that General question mode has no workspace context. Be concise and factual. "
                "For medical questions, provide general educational information rather than personalized medical advice."
            ),
        }
    ]
    for turn in (history or [])[-6:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content[:4000]})
    messages.append({"role": "user", "content": question})

    try:
        response = http_json(
            f"{lm_studio_base_url()}/chat/completions",
            {
                "model": model,
                "messages": messages,
                "temperature": 0.2,
            },
            log_kind="general_question",
        )
    except Exception as exc:
        raise RuntimeError("The selected model provider could not answer this question.") from exc

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("The selected model provider returned an unexpected response.")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text") or "").strip()
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and str(item.get("text") or "").strip()
        )
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The selected model provider returned an empty response.")

    provider = resolve_lm_provider()
    return {
        "intent": "general_llm",
        "reply": sanitize_lm_text(content),
        "data": {
            "source": "general_llm",
            "execution": "llm",
            "context_mode": "none",
            "workspace_context_used": False,
            "model": model,
            "provider_id": str(provider.get("id") or DEFAULT_LLM_PROVIDER_ID),
            "provider_label": str(provider.get("label") or provider.get("id") or "Model provider"),
            "history_turns_used": max(0, len(messages) - 2),
        },
    }


def lm_studio_health(*, timeout: float = 2.0, provider_id: str | None = None) -> Dict[str, Any]:
    provider = resolve_lm_provider(provider_id)
    enabled = bool(provider.get("enabled", False))
    configured_model = str(provider.get("model") or "").strip()
    base_url = str(provider.get("base_url") or "").rstrip("/")
    public_provider = public_llm_provider(provider)
    if not enabled:
        return {
            "enabled": False,
            "available": False,
            "status": "disabled",
            "base_url": base_url,
            "model": configured_model or None,
            "detail": "Provider is disabled.",
            "provider": public_provider,
            "selected_provider_id": str(provider.get("id") or DEFAULT_LLM_PROVIDER_ID),
            "providers": [public_llm_provider(item) for item in llm_providers(include_disabled=True)],
        }
    req = request.Request(
        f"{base_url}/models",
        headers={"Accept": "application/json", "Authorization": f"Bearer {str(provider.get('api_key') or 'lm-studio')}"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "enabled": True,
            "available": False,
            "status": "unreachable",
            "base_url": base_url,
            "model": configured_model or None,
            "detail": f"Provider is enabled but unavailable: {exc}",
            "provider": public_provider,
            "selected_provider_id": str(provider.get("id") or DEFAULT_LLM_PROVIDER_ID),
            "providers": [public_llm_provider(item) for item in llm_providers(include_disabled=True)],
        }
    data = payload.get("data")
    loaded_models = [
        str(item.get("id") or "").strip()
        for item in (data if isinstance(data, list) else [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    model = configured_model or (loaded_models[0] if loaded_models else None)
    if not model:
        return {
            "enabled": True,
            "available": False,
            "status": "no_model",
            "base_url": base_url,
            "model": None,
            "detail": "Provider is reachable, but no model is loaded.",
            "provider": public_provider,
            "selected_provider_id": str(provider.get("id") or DEFAULT_LLM_PROVIDER_ID),
            "providers": [public_llm_provider(item) for item in llm_providers(include_disabled=True)],
        }
    return {
        "enabled": True,
        "available": True,
        "status": "ready",
        "base_url": base_url,
        "model": model,
        "detail": "Provider is reachable.",
        "provider": {**public_provider, "model": model},
        "selected_provider_id": str(provider.get("id") or DEFAULT_LLM_PROVIDER_ID),
        "providers": [public_llm_provider(item) for item in llm_providers(include_disabled=True)],
    }


def llm_provider_registry_status(*, timeout: float = 1.0) -> Dict[str, Any]:
    items = []
    for provider in llm_providers(include_disabled=True):
        provider_id = str(provider.get("id") or DEFAULT_LLM_PROVIDER_ID)
        health = lm_studio_health(timeout=timeout, provider_id=provider_id)
        public = public_llm_provider(provider)
        public.update(
            {
                "available": bool(health.get("available")),
                "status": str(health.get("status") or "disabled"),
                "detail": str(health.get("detail") or ""),
                "resolved_model": health.get("model"),
            }
        )
        items.append(public)
    _managed, registry_error = _managed_registry_providers()
    return {"providers": items, "registry_error": registry_error}


def test_lm_provider(provider_id: str, *, timeout: float = 3.0) -> Dict[str, Any]:
    normalized_id = str(provider_id or "").strip()
    provider = next((item for item in llm_providers(include_disabled=True) if item["id"] == normalized_id), None)
    if provider is None:
        raise ValueError("Provider not found.")
    health = lm_studio_health(timeout=timeout, provider_id=normalized_id)
    public = public_llm_provider(provider)
    public.update(
        {
            "available": bool(health.get("available")),
            "status": str(health.get("status") or "disabled"),
            "detail": str(health.get("detail") or ""),
            "resolved_model": health.get("model"),
        }
    )
    return public
