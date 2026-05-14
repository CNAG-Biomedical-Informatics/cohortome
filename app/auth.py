from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from app.config import STATE_ROOT_DIR


AUTH_USERS_PATH = STATE_ROOT_DIR / "auth" / "users.json"
PASSWORD_RESET_TOKENS_PATH = STATE_ROOT_DIR / "auth" / "password-reset-tokens.json"
PASSWORD_HASH_ITERATIONS = 390_000
PASSWORD_RESET_TOKEN_BYTES = 32


def auth_mode() -> str:
    return (os.getenv("PN_AUTH_MODE", "none").strip().lower() or "none")


def auth_enabled() -> bool:
    return auth_mode() == "local"


def auth_provider_mode() -> str:
    return "local" if auth_enabled() else "none"


def password_reset_ttl_minutes() -> int:
    raw = os.getenv("PN_PASSWORD_RESET_TTL_MINUTES", "").strip()
    if not raw:
        return 60
    try:
        return max(5, min(int(raw), 24 * 60))
    except ValueError:
        return 60


def _smtp_host() -> str:
    return os.getenv("PN_SMTP_HOST", "").strip()


def _smtp_from() -> str:
    return os.getenv("PN_SMTP_FROM", "").strip()


def password_reset_enabled() -> bool:
    return auth_enabled() and bool(_smtp_host() and _smtp_from())


def _normalize_email(value: Any) -> str:
    email = str(value or "").strip()
    if not email:
        return ""
    if "@" not in email or any(char.isspace() for char in email):
        return ""
    return email


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_admin_user(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    if str(user.get("role") or "").strip().lower() == "admin":
        return True
    groups = [str(item or "").strip().lower() for item in (user.get("groups") or [])]
    return "admin" in groups


def _default_users() -> List[Dict[str, Any]]:
    return [
        {
            "username": "admin",
            "password": "admin",
            "role": "admin",
            "display_name": "Administrator",
            "groups": ["admin"],
            "enabled": True,
            "auth_source": "local",
        },
        {
            "username": "mrueda",
            "password": "mrueda",
            "role": "user",
            "display_name": "mrueda",
            "groups": ["cnag"],
            "enabled": True,
            "auth_source": "local",
        }
    ]


def _hash_password(password: str, salt: bytes | None = None) -> Dict[str, str]:
    salt_bytes = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt_bytes, PASSWORD_HASH_ITERATIONS)
    return {
        "password_algorithm": "pbkdf2_sha256",
        "password_salt": base64.b64encode(salt_bytes).decode("ascii"),
        "password_hash": base64.b64encode(derived).decode("ascii"),
    }


def _verify_password(password: str, user: Dict[str, Any]) -> bool:
    algorithm = str(user.get("password_algorithm") or "").strip().lower()
    if algorithm == "pbkdf2_sha256":
        salt_text = str(user.get("password_salt") or "").strip()
        expected_text = str(user.get("password_hash") or "").strip()
        if not salt_text or not expected_text:
            return False
        try:
            salt = base64.b64decode(salt_text.encode("ascii"))
            expected = base64.b64decode(expected_text.encode("ascii"))
        except Exception:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
        return secrets.compare_digest(actual, expected)
    legacy = str(user.get("password") or "")
    return bool(legacy) and secrets.compare_digest(legacy, str(password or ""))


def _state_users_path() -> Path:
    return AUTH_USERS_PATH


def _normalize_role(value: Any) -> str:
    return "admin" if str(value or "").strip().lower() == "admin" else "user"


def _normalize_auth_source(value: Any) -> str:
    return "google" if str(value or "").strip().lower() == "google" else "local"


def _normalize_groups(value: Any) -> List[str]:
    return sorted(
        {
            str(group).strip()
            for group in (value or [])
            if str(group).strip()
        }
    )


def _normalize_stored_user(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    username = str(item.get("username") or "").strip()
    if not username:
        return None
    normalized = {
        "username": username,
        "role": _normalize_role(item.get("role")),
        "display_name": str(item.get("display_name") or username).strip() or username,
        "groups": _normalize_groups(item.get("groups") or []),
        "enabled": bool(item.get("enabled", True)),
        "auth_source": _normalize_auth_source(item.get("auth_source")),
        "email": _normalize_email(item.get("email")),
    }
    if normalized["auth_source"] == "local":
        if str(item.get("password_hash") or "").strip() and str(item.get("password_salt") or "").strip():
            normalized.update(
                {
                    "password_algorithm": "pbkdf2_sha256",
                    "password_salt": str(item.get("password_salt") or "").strip(),
                    "password_hash": str(item.get("password_hash") or "").strip(),
                }
            )
        else:
            password = str(item.get("password") or "").strip()
            if not password:
                return None
            normalized.update(_hash_password(password))
    else:
        normalized["external_subject"] = str(item.get("external_subject") or "").strip()
    return normalized


def _normalize_seed_users(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        user = _normalize_stored_user(item)
        if user is None:
            continue
        normalized.append(user)
    return normalized


def _seed_users_from_env_or_default() -> List[Dict[str, Any]]:
    raw = os.getenv("PN_LOCAL_USERS_JSON", "").strip()
    if not raw:
        return _normalize_seed_users(_default_users())
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _normalize_seed_users(_default_users())
    if not isinstance(parsed, list):
        return _normalize_seed_users(_default_users())
    normalized = _normalize_seed_users(parsed)
    return normalized or _normalize_seed_users(_default_users())


def _write_local_users(users: List[Dict[str, Any]]) -> None:
    path = _state_users_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "provider": "local", "users": users}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def local_users(include_secrets: bool = False) -> List[Dict[str, Any]]:
    path = _state_users_path()
    source = "state"
    users: List[Dict[str, Any]]
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        items = parsed.get("users") if isinstance(parsed, dict) else None
        users = _normalize_seed_users(items if isinstance(items, list) else [])
        if not users:
            users = _seed_users_from_env_or_default()
            _write_local_users(users)
            source = "repaired"
    else:
        users = _seed_users_from_env_or_default()
        _write_local_users(users)
        source = "env" if os.getenv("PN_LOCAL_USERS_JSON", "").strip() else "default"
    if include_secrets:
        return users
    public_users: List[Dict[str, Any]] = []
    for item in users:
        public_users.append(
            {
                "username": item["username"],
                "role": item["role"],
                "display_name": item["display_name"],
                "groups": list(item.get("groups") or []),
                "enabled": bool(item.get("enabled", True)),
                "auth_source": item.get("auth_source") or "local",
                "email": str(item.get("email") or ""),
            }
        )
    setattr(local_users, "_last_source", source)
    return public_users


def local_auth_diagnostics() -> Dict[str, Any]:
    users = local_users()
    return {
        "enabled": auth_enabled(),
        "mode": auth_mode(),
        "provider": auth_provider_mode(),
        "user_count": len(users),
        "usernames": [str(item.get("username") or "") for item in users],
        "roles": {str(item.get("username") or ""): str(item.get("role") or "user") for item in users},
        "groups": {str(item.get("username") or ""): list(item.get("groups") or []) for item in users},
        "source": str(getattr(local_users, "_last_source", "state") or "state"),
    }


def find_local_user(username: str) -> Optional[Dict[str, Any]]:
    needle = str(username or "").strip()
    if not needle:
        return None
    for item in local_users(include_secrets=True):
        if str(item.get("username") or "") == needle:
            return item
    return None


def find_local_user_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    needle = str(identifier or "").strip()
    if not needle:
        return None
    needle_lower = needle.lower()
    for item in local_users(include_secrets=True):
        if str(item.get("username") or "") == needle:
            return item
        email = str(item.get("email") or "").strip().lower()
        if email and email == needle_lower:
            return item
    return None


def authenticate_local_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = find_local_user(username)
    if not user:
        return None
    if not bool(user.get("enabled", True)):
        return None
    if not _verify_password(password, user):
        return None
    return user


def _count_enabled_admins() -> int:
    return sum(
        1
        for item in local_users(include_secrets=True)
        if str(item.get("role") or "") == "admin" and bool(item.get("enabled", True))
    )


def _ensure_not_last_admin(target_username: str, next_role: str, next_enabled: bool) -> None:
    current = find_local_user(target_username)
    if not current:
        return
    if str(current.get("role") or "") != "admin" or not bool(current.get("enabled", True)):
        return
    if next_role == "admin" and next_enabled:
        return
    if _count_enabled_admins() <= 1:
        raise ValueError("Cannot remove, disable, or demote the last enabled admin user.")


def create_local_user(
    *,
    username: str,
    password: str,
    display_name: str = "",
    email: str = "",
    role: str = "user",
    groups: List[str] | None = None,
    enabled: bool = True,
    auth_source: str = "local",
) -> Dict[str, Any]:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("Username is required.")
    if find_local_user(normalized_username):
        raise ValueError("User already exists.")
    normalized_source = _normalize_auth_source(auth_source)
    if normalized_source == "local" and not str(password or "").strip():
        raise ValueError("Password is required for local users.")
    users = local_users(include_secrets=True)
    record = {
        "username": normalized_username,
        "display_name": str(display_name or normalized_username).strip() or normalized_username,
        "email": _normalize_email(email),
        "role": _normalize_role(role),
        "groups": _normalize_groups(groups or []),
        "enabled": bool(enabled),
        "auth_source": normalized_source,
    }
    if normalized_source == "local":
        record.update(_hash_password(password))
    users.append(record)
    users.sort(key=lambda item: str(item.get("username") or ""))
    _write_local_users(users)
    return find_local_user(normalized_username) or record


def update_local_user(
    username: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    role: str | None = None,
    groups: List[str] | None = None,
    enabled: bool | None = None,
) -> Dict[str, Any]:
    normalized_username = str(username or "").strip()
    users = local_users(include_secrets=True)
    updated: Dict[str, Any] | None = None
    for item in users:
        if str(item.get("username") or "") != normalized_username:
            continue
        next_role = _normalize_role(role if role is not None else item.get("role"))
        next_enabled = bool(item.get("enabled", True) if enabled is None else enabled)
        _ensure_not_last_admin(normalized_username, next_role, next_enabled)
        if display_name is not None:
            item["display_name"] = str(display_name or normalized_username).strip() or normalized_username
        if email is not None:
            item["email"] = _normalize_email(email)
        item["role"] = next_role
        if groups is not None:
            item["groups"] = _normalize_groups(groups)
        item["enabled"] = next_enabled
        updated = item
        break
    if updated is None:
        raise ValueError("User not found.")
    _write_local_users(users)
    return find_local_user(normalized_username) or updated


def reset_local_user_password(username: str, password: str) -> Dict[str, Any]:
    normalized_username = str(username or "").strip()
    if not str(password or "").strip():
        raise ValueError("Password is required.")
    users = local_users(include_secrets=True)
    updated: Dict[str, Any] | None = None
    for item in users:
        if str(item.get("username") or "") != normalized_username:
            continue
        if _normalize_auth_source(item.get("auth_source")) != "local":
            raise ValueError("Password reset is only supported for local users.")
        item.update(_hash_password(password))
        item.pop("password", None)
        updated = item
        break
    if updated is None:
        raise ValueError("User not found.")
    _write_local_users(users)
    return find_local_user(normalized_username) or updated


def _state_password_reset_tokens_path() -> Path:
    return PASSWORD_RESET_TOKENS_PATH


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _read_password_reset_tokens() -> List[Dict[str, Any]]:
    path = _state_password_reset_tokens_path()
    if not path.exists():
        return []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = parsed.get("tokens") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    now = _now_utc()
    active: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        expires_at = _parse_iso_datetime(item.get("expires_at"))
        token_hash = str(item.get("token_hash") or "").strip()
        username = str(item.get("username") or "").strip()
        if not username or not token_hash or expires_at is None or expires_at <= now:
            continue
        active.append(
            {
                "username": username,
                "token_hash": token_hash,
                "created_at": str(item.get("created_at") or ""),
                "expires_at": expires_at.isoformat(),
            }
        )
    if len(active) != len(items):
        _write_password_reset_tokens(active)
    return active


def _write_password_reset_tokens(tokens: List[Dict[str, Any]]) -> None:
    path = _state_password_reset_tokens_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "tokens": tokens}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _password_reset_base_url(request: Request) -> str:
    configured = os.getenv("PN_PUBLIC_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def _password_reset_url(request: Request, token: str) -> str:
    return f"{_password_reset_base_url(request)}/?password_reset_token={token}"


def create_password_reset_token(username: str) -> str:
    user = find_local_user(username)
    if not user:
        raise ValueError("User not found.")
    if _normalize_auth_source(user.get("auth_source")) != "local":
        raise ValueError("Password reset is only supported for local users.")
    if not bool(user.get("enabled", True)):
        raise ValueError("Password reset is only supported for enabled users.")
    token = secrets.token_urlsafe(PASSWORD_RESET_TOKEN_BYTES)
    now = _now_utc()
    expires_at = now + timedelta(minutes=password_reset_ttl_minutes())
    tokens = [
        item
        for item in _read_password_reset_tokens()
        if str(item.get("username") or "") != str(user.get("username") or "")
    ]
    tokens.append(
        {
            "username": str(user.get("username") or ""),
            "token_hash": _hash_reset_token(token),
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    )
    _write_password_reset_tokens(tokens)
    return token


def send_password_reset_email(user: Dict[str, Any], reset_url: str) -> None:
    recipient = _normalize_email(user.get("email"))
    if not recipient:
        raise ValueError("User does not have an email address.")
    host = _smtp_host()
    sender = _smtp_from()
    if not host or not sender:
        raise ValueError("SMTP password reset is not configured.")
    port = int(os.getenv("PN_SMTP_PORT", "587") or "587")
    username = os.getenv("PN_SMTP_USERNAME", "").strip()
    password = os.getenv("PN_SMTP_PASSWORD", "")
    use_tls = os.getenv("PN_SMTP_TLS", "true").strip().lower() not in {"0", "false", "no", "off"}
    message = EmailMessage()
    message["Subject"] = "Patient Navigator password reset"
    message["From"] = sender
    message["To"] = recipient
    display_name = str(user.get("display_name") or user.get("username") or "user")
    ttl = password_reset_ttl_minutes()
    message.set_content(
        "\n".join(
            [
                f"Hello {display_name},",
                "",
                "A password reset was requested for your Patient Navigator account.",
                f"Use this link within {ttl} minutes:",
                "",
                reset_url,
                "",
                "If you did not request this reset, ignore this message.",
            ]
        )
    )
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def request_password_reset(identifier: str, request: Request) -> bool:
    if not password_reset_enabled():
        return False
    user = find_local_user_by_identifier(identifier)
    if not user:
        return False
    if _normalize_auth_source(user.get("auth_source")) != "local":
        return False
    if not bool(user.get("enabled", True)):
        return False
    if not _normalize_email(user.get("email")):
        return False
    token = create_password_reset_token(str(user.get("username") or ""))
    try:
        send_password_reset_email(user, _password_reset_url(request, token))
    except Exception:
        _write_password_reset_tokens(
            [
                item
                for item in _read_password_reset_tokens()
                if str(item.get("username") or "") != str(user.get("username") or "")
            ]
        )
        raise
    return True


def confirm_password_reset(token: str, password: str) -> Dict[str, Any]:
    token_hash = _hash_reset_token(token)
    tokens = _read_password_reset_tokens()
    matched: Dict[str, Any] | None = None
    for item in tokens:
        if hmac.compare_digest(str(item.get("token_hash") or ""), token_hash):
            matched = item
            break
    if matched is None:
        raise ValueError("Password reset link is invalid or expired.")
    expires_at = _parse_iso_datetime(matched.get("expires_at"))
    if expires_at is None or expires_at <= _now_utc():
        _write_password_reset_tokens([item for item in tokens if item is not matched])
        raise ValueError("Password reset link is invalid or expired.")
    user = reset_local_user_password(str(matched.get("username") or ""), password)
    _write_password_reset_tokens(
        [
            item
            for item in tokens
            if str(item.get("username") or "") != str(matched.get("username") or "")
        ]
    )
    return user


def delete_local_user(username: str) -> None:
    normalized_username = str(username or "").strip()
    current = find_local_user(normalized_username)
    if current is None:
        raise ValueError("User not found.")
    _ensure_not_last_admin(normalized_username, "user", False)
    users = [item for item in local_users(include_secrets=True) if str(item.get("username") or "") != normalized_username]
    _write_local_users(users)


def session_user(request: Request) -> Optional[Dict[str, Any]]:
    session = getattr(request, "session", None) or {}
    username = str(session.get("username") or "").strip()
    if not username:
        return None
    user = find_local_user(username)
    if not user:
        return None
    if not bool(user.get("enabled", True)):
        return None
    return {
        "username": user["username"],
        "role": str(session.get("role") or user.get("role") or "user"),
        "display_name": str(session.get("display_name") or user.get("display_name") or user["username"]),
        "groups": list(session.get("groups") or user.get("groups") or []),
        "enabled": bool(user.get("enabled", True)),
        "auth_source": str(user.get("auth_source") or "local"),
        "email": str(user.get("email") or ""),
    }


def require_admin(request: Request) -> Dict[str, Any]:
    user = session_user(request)
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def require_authenticated(request: Request) -> Dict[str, Any]:
    if not auth_enabled():
        return {
            "username": "local",
            "role": "admin",
            "display_name": "Local user",
            "groups": [],
        }
    user = session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user
