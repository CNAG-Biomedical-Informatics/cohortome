from __future__ import annotations

import re
from pathlib import Path

from fastapi import Request

from app.auth import auth_enabled, session_user
from app.config import DEFAULT_LOCAL_USER_ID, STATE_ROOT_DIR


_SAFE_USER_ID_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def normalize_user_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_LOCAL_USER_ID
    normalized = _SAFE_USER_ID_RE.sub("_", raw).strip("._-")
    return normalized or DEFAULT_LOCAL_USER_ID


def request_user_id(request: Request | None) -> str:
    if request is None:
        return DEFAULT_LOCAL_USER_ID
    if auth_enabled():
        user = session_user(request)
        if user:
            return normalize_user_id(str(user.get("username") or DEFAULT_LOCAL_USER_ID))
    return normalize_user_id(
        request.headers.get("X-User-Id")
        or request.cookies.get("pn_user_id")
        or DEFAULT_LOCAL_USER_ID
    )


def user_state_dir(user_id: str | None = None) -> Path:
    normalized = normalize_user_id(user_id)
    return STATE_ROOT_DIR / "users" / normalized


def user_state_file(filename: str, user_id: str | None = None) -> Path:
    return user_state_dir(user_id) / filename
