from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict
from urllib import error, request
from uuid import uuid4

from app.config import BASE_DIR

LM_DEBUG_DIR = BASE_DIR / "runs" / "lm-debug"


def lm_studio_enabled() -> bool:
    value = os.getenv("LM_STUDIO_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def lm_studio_base_url() -> str:
    return os.getenv("LM_STUDIO_BASE_URL", "http://192.168.1.42:1234/v1").rstrip("/")


def lm_studio_timeout() -> float:
    raw = os.getenv("LM_STUDIO_TIMEOUT", "30").strip()
    try:
        return float(raw)
    except ValueError:
        return 30.0


def lm_studio_api_key() -> str:
    return os.getenv("LM_STUDIO_API_KEY", "lm-studio")


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
    configured = os.getenv("LM_STUDIO_MODEL", "").strip()
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
