from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request


def auth_mode() -> str:
    return (os.getenv("PN_AUTH_MODE", "none").strip().lower() or "none")


def auth_enabled() -> bool:
    return auth_mode() == "local"


def _default_users() -> List[Dict[str, Any]]:
    return [
        {
            "username": "admin",
            "password": "admin",
            "role": "admin",
            "display_name": "Administrator",
        }
    ]


def local_users() -> List[Dict[str, Any]]:
    raw = os.getenv("PN_LOCAL_USERS_JSON", "").strip()
    if not raw:
        return _default_users()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _default_users()
    if not isinstance(parsed, list):
        return _default_users()
    normalized: List[Dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username") or "").strip()
        password = str(item.get("password") or "").strip()
        if not username or not password:
            continue
        normalized.append(
            {
                "username": username,
                "password": password,
                "role": str(item.get("role") or "user").strip() or "user",
                "display_name": str(item.get("display_name") or username).strip() or username,
            }
        )
    return normalized or _default_users()


def local_auth_diagnostics() -> Dict[str, Any]:
    users = local_users()
    return {
        "enabled": auth_enabled(),
        "mode": auth_mode(),
        "user_count": len(users),
        "usernames": [str(item.get("username") or "") for item in users],
        "roles": {str(item.get("username") or ""): str(item.get("role") or "user") for item in users},
        "source": "env" if os.getenv("PN_LOCAL_USERS_JSON", "").strip() else "default",
    }


def find_local_user(username: str) -> Optional[Dict[str, Any]]:
    needle = str(username or "").strip()
    if not needle:
        return None
    for item in local_users():
        if str(item.get("username") or "") == needle:
            return item
    return None


def authenticate_local_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = find_local_user(username)
    if not user:
        return None
    if str(user.get("password") or "") != str(password or ""):
        return None
    return user


def session_user(request: Request) -> Optional[Dict[str, Any]]:
    session = getattr(request, "session", None) or {}
    username = str(session.get("username") or "").strip()
    if not username:
        return None
    user = find_local_user(username)
    if not user:
        return None
    return {
        "username": user["username"],
        "role": str(session.get("role") or user.get("role") or "user"),
        "display_name": str(session.get("display_name") or user.get("display_name") or user["username"]),
    }


def require_admin(request: Request) -> Dict[str, Any]:
    user = session_user(request)
    if not user or str(user.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user
