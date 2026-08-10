from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict
from urllib import error, request
from uuid import uuid4

from app.config import RUNS_ROOT_DIR
from app.env import app_env

LM_DEBUG_DIR = RUNS_ROOT_DIR / "lm-debug"
DEFAULT_LLM_PROVIDER_ID = "system-default"
_CURRENT_PROVIDER_ID: ContextVar[str] = ContextVar("patient_workspace_lm_provider_id", default=DEFAULT_LLM_PROVIDER_ID)


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
        "source": "env",
    }


def _normalize_provider(raw: Dict[str, Any]) -> Dict[str, Any] | None:
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
        "source": str(raw.get("source") or "registry"),
    }


def _configured_registry_providers() -> list[Dict[str, Any]]:
    raw = app_env("COHORTOME_LLM_PROVIDERS_JSON", "").strip()
    if not raw:
        registry_path = app_env("COHORTOME_LLM_PROVIDERS_FILE", "").strip()
        if registry_path:
            try:
                raw = BASE_DIR.joinpath(registry_path).read_text(encoding="utf-8") if not os.path.isabs(registry_path) else open(registry_path, encoding="utf-8").read()
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
            provider = _normalize_provider(item)
            if provider:
                providers.append(provider)
    return providers


def llm_providers(include_disabled: bool = True) -> list[Dict[str, Any]]:
    providers = [_system_default_provider()]
    seen = {DEFAULT_LLM_PROVIDER_ID}
    for item in _configured_registry_providers():
        if item["id"] in seen:
            providers = [item if provider["id"] == item["id"] else provider for provider in providers]
        else:
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
        "source": str(provider.get("source") or "registry"),
    }


def resolve_lm_provider(provider_id: str | None = None) -> Dict[str, Any]:
    selected = str(provider_id or _CURRENT_PROVIDER_ID.get() or DEFAULT_LLM_PROVIDER_ID).strip() or DEFAULT_LLM_PROVIDER_ID
    providers = llm_providers(include_disabled=True)
    for provider in providers:
        if provider["id"] == selected:
            return provider
    return providers[0]


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
        if re.match(r"^\d+\.\s", lowered):
            return True
        if lowered.startswith(("*", "-", "•")):
            return True
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
            "detail": "LM Studio is disabled.",
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
            "detail": f"LM Studio is enabled but unavailable: {exc}",
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
            "detail": "LM Studio is reachable, but no model is loaded.",
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
        "detail": "LM Studio is reachable.",
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
    return {"providers": items}
