"""Personal chat organization; no workspace or conversation content is modified."""
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal

from app.auth import require_authenticated
from app.config import STATE_ROOT_DIR
from app.user_state import normalize_user_id, request_user_id
from app.state_io import advisory_file_lock, atomic_write_json
from app.analysis_sessions import get_analysis_session
from app.query_sessions import get_session

USER_STATE_ROOT = STATE_ROOT_DIR / "users"
router = APIRouter(prefix="/chat-folders", tags=["chats"])


class FolderName(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ChatMove(BaseModel):
    kind: Literal["query", "analysis", "pheno"]
    chat_id: str = Field(min_length=1, max_length=200)
    folder_id: str = Field(default="", max_length=100)


class ChatPin(BaseModel):
    kind: Literal["query", "analysis", "pheno", "folder"]
    chat_id: str = Field(min_length=1, max_length=200)
    pinned: bool


def _path(user_id):
    path = USER_STATE_ROOT / normalize_user_id(user_id) / "chat-folders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_folders(user_id):
    path = _path(user_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"folders": [], "assignments": {}}


def change_folders(user_id, operation, *, folder_id="", name="", kind="", chat_id="", pinned=False):
    path = _path(user_id)
    with advisory_file_lock(path.with_suffix(".lock")):
        data = read_folders(user_id)
        folder = next((item for item in data["folders"] if item["id"] == folder_id), None)
        if operation in {"rename", "delete"} or (operation == "move" and folder_id):
            if folder is None:
                raise HTTPException(status_code=404, detail="Folder not found.")
        if operation in {"create", "rename"}:
            name = name.strip()
            if not name or name.casefold() == "unfiled":
                raise HTTPException(status_code=400, detail="Choose a folder name other than Unfiled.")
            if any(item["id"] != folder_id and item["name"].casefold() == name.casefold() for item in data["folders"]):
                raise HTTPException(status_code=409, detail="A folder with this name already exists.")
            if operation == "create":
                data["folders"].append({"id": str(uuid4()), "name": name})
            else:
                folder["name"] = name
        elif operation == "delete":
            data["folders"] = [item for item in data["folders"] if item["id"] != folder_id]
            data["assignments"] = {key: value for key, value in data["assignments"].items() if value != folder_id}
            data["pinned"] = [key for key in data.get("pinned", []) if key != f"folder:{folder_id}"]
        elif operation in {"move", "pin"}:
            chat = (next((item for item in data["folders"] if item["id"] == chat_id), None) if kind == "folder"
                    else get_session(user_id, chat_id, kind) if kind in {"query", "pheno"} else get_analysis_session(chat_id, user_id=user_id))
            if chat is None:
                raise HTTPException(status_code=404, detail="Chat not found. Save it before moving it.")
            key = f"{kind}:{chat_id}"
            if operation == "pin":
                data["pinned"] = [item for item in data.get("pinned", []) if item != key]
                if pinned:
                    data["pinned"].append(key)
            elif folder_id:
                data["assignments"][key] = folder_id
            else:
                data["assignments"].pop(key, None)
        atomic_write_json(path, data)
    return data


@router.get("")
def list_folders(request: Request):
    require_authenticated(request)
    return read_folders(request_user_id(request))


@router.post("")
def create_folder(payload: FolderName, request: Request):
    require_authenticated(request)
    return change_folders(request_user_id(request), "create", name=payload.name)


@router.post("/move")
def move_chat(payload: ChatMove, request: Request):
    require_authenticated(request)
    return change_folders(request_user_id(request), "move", **payload.model_dump())


@router.post("/pin")
def pin_chat(payload: ChatPin, request: Request):
    require_authenticated(request)
    return change_folders(request_user_id(request), "pin", **payload.model_dump())


@router.patch("/{folder_id}")
def rename_folder(folder_id: str, payload: FolderName, request: Request):
    require_authenticated(request)
    return change_folders(request_user_id(request), "rename", folder_id=folder_id, name=payload.name)


@router.delete("/{folder_id}")
def delete_folder(folder_id: str, request: Request):
    require_authenticated(request)
    return change_folders(request_user_id(request), "delete", folder_id=folder_id)
