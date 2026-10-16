"""User-owned Query conversations, stored independently of executable analyses."""
from datetime import datetime, timezone
import json

from app.config import STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import normalize_user_id

USER_STATE_ROOT = STATE_ROOT_DIR / "users"


def _path(user_id):
    path = USER_STATE_ROOT / normalize_user_id(user_id) / "query-sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def list_sessions(user_id):
    path = _path(user_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def get_session(user_id, session_id):
    return next((item for item in list_sessions(user_id) if item["id"] == session_id), None)


def save_session(user_id, payload):
    path = _path(user_id)
    with advisory_file_lock(path.with_suffix(".lock")):
        items = list_sessions(user_id)
        existing = next((item for item in items if item["id"] == payload["id"]), None)
        if payload.get("revision", 0) != (existing or {}).get("revision", 0):
            raise ValueError("This chat was changed in another window. Reopen it before saving again.")
        now = datetime.now(timezone.utc).isoformat()
        saved = {**payload, "revision": payload.get("revision", 0) + 1,
                 "created_at": (existing or {}).get("created_at", now), "updated_at": now}
        items = [item for item in items if item["id"] != saved["id"]]
        atomic_write_json(path, [saved, *items])
    return saved


def delete_session(user_id, session_id):
    path = _path(user_id)
    with advisory_file_lock(path.with_suffix(".lock")):
        items = list_sessions(user_id)
        filtered = [item for item in items if item["id"] != session_id]
        if len(items) == len(filtered):
            return False
        atomic_write_json(path, filtered)
    return True
