from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    auth_enabled,
    authenticate_local_user,
    auth_provider_mode,
    create_local_user,
    confirm_password_reset,
    delete_local_user,
    local_auth_diagnostics,
    local_users,
    password_reset_enabled,
    request_password_reset,
    require_admin,
    require_authenticated,
    reset_local_user_password,
    session_user,
    update_local_user,
)
from app.analysis import analysis_llm_reply
from app.analysis_catalog import analysis_catalog_payload
from app.analysis_sessions import (
    delete_analysis_session,
    get_analysis_session,
    list_analysis_sessions,
    list_sessions_referencing_saved_cohort,
    rename_analysis_session,
    save_analysis_session,
)
from app.bff import (
    build_patient_navigator,
    dashboard_summary,
    get_patient_context,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
)
from app.config import DEFAULT_DATA_DIR, branding_logo_path, branding_settings
from app.cohorts import delete_saved_cohort, list_saved_cohorts, save_cohort
from app.datasets import (
    authorized_datasets_for_user,
    current_dataset_id,
    current_dataset_ids,
    dataset_content_metadata,
    dataset_scope_id,
    effective_ai_provider_access,
    effective_query_granularity_ceiling,
    register_dataset,
    resolve_dataset,
    resolve_dataset_dir,
    resolve_dataset_ids,
    set_current_dataset,
    set_current_datasets,
    update_dataset,
    workspace_fingerprint_for_data_dir,
)
from app.lm import lm_studio_health
from app.jobs import (
    active_feature_job,
    delete_job,
    list_job_records,
    list_jobs_for_analysis_session,
    load_job_record,
    public_job_payload,
    resolve_job_artifact_path,
    submit_pheno_job,
)
from app.pheno import (
    pheno_ranker_alignment_details,
    pheno_ranker_explain,
    pheno_ranker_explain_llm,
    pheno_ranker_patient_ids_payload,
    pheno_ranker_result_file_path,
    pheno_run_requires_background_job,
    plan_pheno_ranker,
    run_pheno_ranker,
)
from app.query_store import molecular_dataset_inventory, molecular_expression_summary, molecular_gene_annotations, molecular_gene_inventory
from app.query_store import QueryStoreNotReadyError, dataset_query_store_status, ensure_query_store, prepare_dataset_query_store
from app.user_settings import load_user_settings, update_user_settings as patch_user_settings
from app.schemas import (
    AnalysisRequest,
    AnalysisSessionRenameRequest,
    AnalysisSessionRequest,
    AuthDiagnosticsResponse,
    AuthPasswordResetConfirmRequest,
    AuthPasswordResetRequest,
    AuthPasswordResetResponse,
    AuthPasswordResetStartRequest,
    AuthStatusResponse,
    AuthUserCreateRequest,
    AuthUserResponse,
    AuthUserUpdateRequest,
    AuthUsersResponse,
    DatasetRecordResponse,
    DatasetRegistrationRequest,
    DatasetsResponse,
    DatasetSelectionResponse,
    DatasetSelectionRequest,
    DatasetUpdateRequest,
    DeleteResponse,
    MolecularExpressionRequest,
    MolecularDatasetsResponse,
    LmStatusResponse,
    PatientSummaryResponse,
    PhenoRankerPlanRequest,
    PhenoRankerRequest,
    QueryRequest,
    SavedCohortRequest,
    SavedCohortResponse,
    SavedCohortsResponse,
    LoginRequest,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.query import answer_query


def _workspace_changed_detail(status: Dict[str, Any]) -> str:
    removed = list(status.get("removed_files") or [])
    added = list(status.get("added_files") or [])
    if removed and not added:
        removed_label = removed[0] if len(removed) == 1 else f"{len(removed)} clinical files"
        return f"This analysis session was created against an older workspace version. Missing from the current workspace: {removed_label}."
    if added and not removed:
        added_label = added[0] if len(added) == 1 else f"{len(added)} clinical files"
        return f"This analysis session was created against an older workspace version. The current workspace now includes additional clinical files such as {added_label}."
    if removed or added:
        return "This analysis session was created against an older workspace version. The active clinical file set has changed."
    return "This analysis session was created against an older workspace version."


def _analysis_session_workspace_status(session: Dict[str, Any], request: Request) -> Dict[str, Any]:
    dataset_key = str(session.get("dataset_id") or "").strip() or str(session.get("data_dir") or "").strip()
    stored = session.get("workspace_fingerprint") if isinstance(session.get("workspace_fingerprint"), dict) else {}
    if not dataset_key:
        return {
            "state": "unknown",
            "message": "No stored workspace fingerprint is available for this analysis session.",
            "stored_fingerprint": stored,
            "current_fingerprint": {},
            "removed_files": [],
            "added_files": [],
        }
    try:
        selected_ids = resolve_dataset_ids(request, dataset_key)
        resolved_scope_id = dataset_scope_id(selected_ids)
        resolved_dir = resolve_dataset_dir(request, dataset_key)
        current = workspace_fingerprint_for_data_dir(resolved_dir, dataset_id=resolved_scope_id, dataset_ids=selected_ids)
    except HTTPException as exc:
        detail = str(exc.detail or "").strip() or "The original dataset is no longer available."
        return {
            "state": "unavailable",
            "message": detail,
            "stored_fingerprint": stored,
            "current_fingerprint": {},
            "removed_files": [],
            "added_files": [],
        }
    stored_names = [str(item.get("name") or "").strip() for item in (stored.get("clinical_files") or []) if str(item.get("name") or "").strip()]
    current_names = [str(item.get("name") or "").strip() for item in (current.get("clinical_files") or []) if str(item.get("name") or "").strip()]
    removed = sorted(set(stored_names) - set(current_names))
    added = sorted(set(current_names) - set(stored_names))
    if not stored:
        return {
            "state": "unknown",
            "message": "No stored workspace fingerprint is available for this analysis session.",
            "stored_fingerprint": stored,
            "current_fingerprint": current,
            "removed_files": removed,
            "added_files": added,
        }
    if str(stored.get("token") or "").strip() != str(current.get("token") or "").strip():
        status = {
            "state": "stale",
            "message": "",
            "stored_fingerprint": stored,
            "current_fingerprint": current,
            "removed_files": removed,
            "added_files": added,
        }
        status["message"] = _workspace_changed_detail(status)
        return status
    return {
        "state": "current",
        "message": "",
        "stored_fingerprint": stored,
        "current_fingerprint": current,
        "removed_files": removed,
        "added_files": added,
    }
from app.query import disease_counts as query_disease_counts
from app.user_state import request_user_id


templates: Jinja2Templates | None = None


def init_routes_templates(value: Jinja2Templates) -> None:
    global templates
    templates = value


def index(request: Request) -> HTMLResponse:
    if templates is None:
        raise RuntimeError("Templates have not been initialized.")
    if auth_enabled():
        user = session_user(request)
        datasets = authorized_datasets_for_user(user) if user else []
        selected = resolve_dataset(request) if user else {}
    else:
        user = {"username": "local", "role": "admin", "display_name": "Local user"}
        datasets = authorized_datasets_for_user(user)
        selected = resolve_dataset(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_data_dir": DEFAULT_DATA_DIR,
            "datasets": datasets,
            "current_dataset_id": str(selected.get("dataset_id") or ""),
            "branding": branding_settings(),
            "auth_enabled": auth_enabled(),
        },
    )


def _dataset_provenance_from_sources(request: Request | None, source_files: List[str]) -> Dict[str, Any]:
    user = session_user(request) if request is not None and auth_enabled() else None
    if user:
        datasets = authorized_datasets_for_user(user)
    elif auth_enabled():
        datasets = []
    else:
        datasets = authorized_datasets_for_user({"username": "local", "role": "admin", "display_name": "Local user"})
    matched_ids: List[str] = []
    matched_names: List[str] = []
    normalized_sources = [str(item).strip() for item in source_files if str(item).strip()]
    for dataset in datasets:
        dataset_id = str(dataset.get("dataset_id") or "").strip()
        dataset_name = str(dataset.get("name") or dataset_id or "Dataset").strip() or "Dataset"
        root_path = str(dataset.get("root_path") or "").strip()
        if not dataset_id or not root_path:
            continue
        try:
            root = Path(root_path).resolve()
        except OSError:
            continue
        for source in normalized_sources:
            try:
                source_path = Path(source).resolve()
            except OSError:
                continue
            try:
                source_path.relative_to(root)
            except ValueError:
                continue
            if dataset_id not in matched_ids:
                matched_ids.append(dataset_id)
                matched_names.append(dataset_name)
            break
    return {
        "dataset_ids": matched_ids,
        "dataset_names": matched_names,
        "dataset_name": matched_names[0] if len(matched_names) == 1 else "",
    }


def _resolve_route_dataset_dir(
    request: Request | None,
    dataset_id: str = "",
    data_dir: str = DEFAULT_DATA_DIR,
) -> str:
    if request is None:
        if dataset_id:
            return resolve_dataset_dir(request, dataset_id)
        return data_dir
    resolved_key = dataset_id or data_dir
    if resolved_key:
        return resolve_dataset_dir(request, resolved_key)
    return resolve_dataset_dir(request, current_dataset_id(request_user_id(request)) or "")


def get_datasets(request: Request) -> Dict:
    user = require_authenticated(request)
    datasets = []
    for item in authorized_datasets_for_user(user):
        payload = dict(item)
        payload["query_store_status"] = dataset_query_store_status(str(item.get("dataset_id") or ""))
        try:
            payload.update(dataset_content_metadata(str(item.get("root_path") or "")))
        except FileNotFoundError:
            payload.update({"content_tags": [], "content_summary": "Dataset files are not available."})
        datasets.append(payload)
    selected_ids = resolve_dataset_ids(request)
    return {
        "datasets": datasets,
        "current_dataset_id": selected_ids[0] if len(selected_ids) == 1 else "",
        "current_dataset_ids": selected_ids,
        "current_dataset_scope_id": dataset_scope_id(selected_ids),
        "current_dataset": next((item for item in datasets if str(item.get("dataset_id") or "") == selected_ids[0]), None) if len(selected_ids) == 1 else None,
    }


def select_dataset(payload: DatasetSelectionRequest, request: Request) -> Dict:
    user = require_authenticated(request)
    requested_ids = payload.dataset_ids or ([payload.dataset_id] if payload.dataset_id else [])
    resolved_ids = resolve_dataset_ids(request, dataset_scope_id(requested_ids))
    set_current_datasets(str(user.get("username") or "local"), resolved_ids)
    return {
        "selected": True,
        "current_dataset_id": resolved_ids[0] if len(resolved_ids) == 1 else "",
        "current_dataset_ids": resolved_ids,
        "current_dataset_scope_id": dataset_scope_id(resolved_ids),
    }


def create_dataset_route(payload: DatasetRegistrationRequest, request: Request) -> Dict:
    user = require_admin(request)
    try:
        dataset = register_dataset(
            name=payload.name,
            root_path=payload.root_path,
            description=payload.description,
            visibility=payload.visibility,
            allowed_users=payload.allowed_users,
            allowed_groups=payload.allowed_groups,
            query_granularity_ceiling=payload.query_granularity_ceiling,
            ai_provider_access=payload.ai_provider_access,
            enabled=payload.enabled,
            created_by=str(user.get("username") or "admin"),
        )
        dataset["query_store_status"] = dataset_query_store_status(str(dataset.get("dataset_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dataset


def update_dataset_route(dataset_id: str, payload: DatasetUpdateRequest, request: Request) -> Dict:
    require_admin(request)
    try:
        updated = update_dataset(
            dataset_id,
            name=payload.name,
            root_path=payload.root_path,
            description=payload.description,
            visibility=payload.visibility,
            allowed_users=payload.allowed_users,
            allowed_groups=payload.allowed_groups,
            query_granularity_ceiling=payload.query_granularity_ceiling,
            ai_provider_access=payload.ai_provider_access,
            enabled=payload.enabled,
        )
        updated["query_store_status"] = dataset_query_store_status(str(updated.get("dataset_id") or ""))
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def prepare_dataset_route(dataset_id: str, request: Request) -> Dict:
    require_admin(request)
    try:
        status = prepare_dataset_query_store(dataset_id)
        dataset = resolve_dataset(request, dataset_id)
        payload = dict(dataset)
        payload["query_store_status"] = status
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_patients(request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    if request is not None:
        require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        patients = list_patient_summaries(resolved_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload: List[Dict[str, Any]] = []
    for patient in patients:
        item = patient.model_dump()
        item.update(_dataset_provenance_from_sources(request, item.get("source_files") or []))
        payload.append(item)
    return payload


def get_patient(patient_id: str, request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        patient = get_patient_context(resolved_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    payload = patient.model_dump()
    payload.update(_dataset_provenance_from_sources(request, payload.get("source_files") or []))
    return payload


def get_patient_navigator(patient_id: str, request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        navigator = build_patient_navigator(resolved_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if navigator is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    payload = navigator.model_dump()
    provenance = _dataset_provenance_from_sources(request, payload.get("summary", {}).get("source_files") or payload.get("patient_context", {}).get("source_files") or [])
    payload["summary"] = {**payload.get("summary", {}), **provenance}
    payload["patient_context"] = {**payload.get("patient_context", {}), **provenance}
    return payload


def get_medication_counts(request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    if request is not None:
        require_authenticated(request)
    try:
        return medication_counts(_resolve_route_dataset_dir(request, dataset_id, data_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_disease_counts(request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    if request is not None:
        require_authenticated(request)
    try:
        return query_disease_counts(_resolve_route_dataset_dir(request, dataset_id, data_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def search_medication_cohort(medication: str, request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        return medication_cohort(_resolve_route_dataset_dir(request, dataset_id, data_dir), medication)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def query_app(q: str, request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        return answer_query(_resolve_route_dataset_dir(request, dataset_id, data_dir), q)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_lm_status() -> Dict:
    return lm_studio_health()


def get_branding_logo() -> FileResponse:
    logo_path = branding_logo_path()
    if logo_path is None:
        raise HTTPException(status_code=404, detail="Branding logo not configured.")
    return FileResponse(logo_path)


def get_auth_status(request: Request) -> Dict:
    user = session_user(request)
    return {
        "enabled": auth_enabled(),
        "authenticated": bool(user) if auth_enabled() else True,
        "password_reset_enabled": password_reset_enabled(),
        "user": user if auth_enabled() else {
            "username": "local",
            "role": "admin",
            "display_name": "Local user",
            "email": "",
        },
    }


def login_local(request: Request, payload: LoginRequest) -> Dict:
    if not auth_enabled():
        return {"enabled": False, "authenticated": True, "password_reset_enabled": False}
    user = authenticate_local_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]
    request.session["display_name"] = user["display_name"]
    request.session["groups"] = list(user.get("groups") or [])
    return {
        "enabled": True,
        "authenticated": True,
        "password_reset_enabled": password_reset_enabled(),
        "user": {
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
            "email": str(user.get("email") or ""),
            "groups": list(user.get("groups") or []),
        },
    }


def logout_local(request: Request) -> Dict:
    session = getattr(request, "session", None)
    if session is not None:
        session.clear()
    return {"enabled": auth_enabled(), "authenticated": False, "password_reset_enabled": password_reset_enabled()}


def request_auth_password_reset(payload: AuthPasswordResetStartRequest, request: Request) -> Dict:
    message = "If an account exists, reset instructions were sent."
    if not auth_enabled():
        return {"ok": True, "message": message}
    if not password_reset_enabled():
        return {"ok": False, "message": "Password reset is not configured. Contact your administrator."}
    try:
        request_password_reset(payload.identifier, request)
    except Exception:
        # Keep the public response non-enumerating. Operational SMTP failures
        # should be handled through deployment logs and admin configuration.
        pass
    return {"ok": True, "message": message}


def confirm_auth_password_reset(payload: AuthPasswordResetConfirmRequest) -> Dict:
    if not auth_enabled() or not password_reset_enabled():
        raise HTTPException(status_code=400, detail="Password reset is not configured. Contact your administrator.")
    try:
        confirm_password_reset(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": "Password reset. You can sign in with the new password."}


def get_auth_diagnostics(request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    elif os.getenv("PN_AUTH_DEBUG_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=404, detail="Auth diagnostics are disabled.")
    return local_auth_diagnostics()


def get_auth_users(request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    return {
        "mode": auth_provider_mode(),
        "users": local_users(),
    }


def create_auth_user(request: AuthUserCreateRequest, raw_request: Request) -> Dict:
    if auth_enabled():
        require_admin(raw_request)
    try:
        user = create_local_user(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
            email=request.email,
            role=request.role,
            groups=request.groups,
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "username": str(user.get("username") or ""),
        "role": str(user.get("role") or "user"),
        "display_name": str(user.get("display_name") or user.get("username") or ""),
        "email": str(user.get("email") or ""),
        "groups": list(user.get("groups") or []),
        "enabled": bool(user.get("enabled", True)),
        "auth_source": str(user.get("auth_source") or "local"),
    }


def update_auth_user(username: str, request: AuthUserUpdateRequest, raw_request: Request) -> Dict:
    actor = None
    if auth_enabled():
        actor = require_admin(raw_request)
    actor_username = str((actor or {}).get("username") or "").strip()
    target_username = str(username or "").strip()
    if actor_username and actor_username == target_username:
        if request.enabled is False:
            raise HTTPException(status_code=400, detail="You cannot disable the user currently signed into this session.")
        if request.role is not None and str(request.role or "").strip().lower() != "admin":
            raise HTTPException(status_code=400, detail="You cannot remove your own admin access while signed into this session.")
    try:
        user = update_local_user(
            username,
            display_name=request.display_name,
            email=request.email,
            role=request.role,
            groups=request.groups,
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "username": str(user.get("username") or ""),
        "role": str(user.get("role") or "user"),
        "display_name": str(user.get("display_name") or user.get("username") or ""),
        "email": str(user.get("email") or ""),
        "groups": list(user.get("groups") or []),
        "enabled": bool(user.get("enabled", True)),
        "auth_source": str(user.get("auth_source") or "local"),
    }


def reset_auth_user_password(username: str, request: AuthPasswordResetRequest, raw_request: Request) -> Dict:
    if auth_enabled():
        require_admin(raw_request)
    try:
        user = reset_local_user_password(username, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "username": str(user.get("username") or ""),
        "role": str(user.get("role") or "user"),
        "display_name": str(user.get("display_name") or user.get("username") or ""),
        "email": str(user.get("email") or ""),
        "groups": list(user.get("groups") or []),
        "enabled": bool(user.get("enabled", True)),
        "auth_source": str(user.get("auth_source") or "local"),
    }


def delete_auth_user(username: str, request: Request) -> Dict:
    actor = None
    if auth_enabled():
        actor = require_admin(request)
    actor_username = str((actor or {}).get("username") or "").strip()
    target_username = str(username or "").strip()
    if actor_username and actor_username == target_username:
        raise HTTPException(status_code=400, detail="You cannot delete the user currently signed into this session.")
    try:
        delete_local_user(username)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if message == "User not found." else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"deleted": True, "id": username}


def get_user_settings(request: Request) -> Dict:
    require_authenticated(request)
    return load_user_settings(request_user_id(request))


def update_user_settings(request: UserSettingsUpdateRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    return patch_user_settings(request.model_dump(exclude_unset=True, exclude_none=True), request_user_id(raw_request))


def get_saved_cohorts(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, dataset_id or data_dir)
    return {"cohorts": list_saved_cohorts(dataset_scope_id(selected_ids), user_id=request_user_id(request))}


def create_saved_cohort(request: SavedCohortRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or request.data_dir)
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    try:
        item = save_cohort(
            name=request.name,
            dataset_id=dataset_scope_id(selected_ids),
            dataset_ids=selected_ids,
            data_dir=resolved_dir,
            sample_ids=request.sample_ids,
            patient_ids=request.patient_ids,
            id_type=request.id_type,
            source_kind=request.source_kind,
            source_prompt=request.source_prompt,
            user_id=request_user_id(raw_request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


def remove_saved_cohort(cohort_id: str, request: Request) -> Dict:
    require_authenticated(request)
    referenced_by = list_sessions_referencing_saved_cohort(cohort_id, user_id=request_user_id(request))
    if referenced_by:
        preview_titles = [str(item.get("title") or "").strip() or "Untitled analysis" for item in referenced_by[:3]]
        suffix = f" and {len(referenced_by) - 3} more" if len(referenced_by) > 3 else ""
        detail = (
            "Saved cohort is still referenced by analysis session"
            f"{'' if len(referenced_by) == 1 else 's'}: {', '.join(preview_titles)}{suffix}. "
            "Delete or update those analysis sessions first."
        )
        raise HTTPException(status_code=409, detail=detail)
    deleted = delete_saved_cohort(cohort_id, user_id=request_user_id(request))
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved cohort not found.")
    return {"deleted": True, "id": cohort_id}


def delete_user_analysis_sessions(request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    sessions = list_analysis_sessions(user_id=user_id)
    deleted_count = 0
    for item in sessions:
        session_id = str(item.get("id") or "").strip()
        if session_id and delete_analysis_session(session_id, user_id=user_id):
            deleted_count += 1
    return {"deleted": True, "deleted_count": deleted_count}


def delete_user_completed_jobs(request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    deleted_count = 0
    skipped_active_count = 0
    for item in list_job_records(user_id):
        job_id = str(item.get("job_id") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        if status in {"queued", "running"}:
            skipped_active_count += 1
            continue
        if job_id and delete_job(job_id, user_id):
            deleted_count += 1
    return {"deleted": True, "deleted_count": deleted_count, "skipped_active_count": skipped_active_count}


def delete_user_saved_cohorts(request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    cohorts = list_saved_cohorts(user_id=user_id)
    referenced = [
        item
        for item in cohorts
        if list_sessions_referencing_saved_cohort(str(item.get("id") or "").strip(), user_id=user_id)
    ]
    if referenced:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(referenced)} saved cohort"
                f"{'' if len(referenced) == 1 else 's'} still referenced by analysis chats. "
                "Delete analysis chats first or remove those cohort references."
            ),
        )
    deleted_count = 0
    for item in cohorts:
        cohort_id = str(item.get("id") or "").strip()
        if cohort_id and delete_saved_cohort(cohort_id, user_id=user_id):
            deleted_count += 1
    return {"deleted": True, "deleted_count": deleted_count}


def query_app_post(request: QueryRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or "")
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    try:
        return answer_query(
            resolved_dir,
            request.q,
            query_mode=request.query_mode,
            history=[turn.model_dump() for turn in request.history],
            scoped_patient_ids=request.scoped_patient_ids,
            granularity_mode=request.granularity_mode,
            granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
            ai_provider_access=effective_ai_provider_access(selected_ids),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def analysis_app(request: AnalysisRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or "")
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    if str(request.analysis_session_id or "").strip():
        session = get_analysis_session(request.analysis_session_id, user_id=request_user_id(raw_request))
        if session:
            workspace_status = _analysis_session_workspace_status(session, raw_request)
            if workspace_status["state"] in {"stale", "unavailable"}:
                raise HTTPException(status_code=409, detail=workspace_status["message"] or "This analysis session is no longer aligned with the current workspace.")
    try:
        return analysis_llm_reply(
            request.prompt,
            resolved_dir,
            catalog_item_id=request.catalog_item_id,
            dataset_id=request.dataset_id or "",
            molecular_dataset_name=request.molecular_dataset_name,
            analysis_session_id=request.analysis_session_id,
            user_id=request_user_id(raw_request),
            selected_patient_ids=request.selected_patient_ids,
            compare_mode=request.compare_mode,
            compare_selected_patient_ids=request.compare_selected_patient_ids,
            llm_only=request.llm_only,
            deterministic_only=request.deterministic_only,
            history=[turn.model_dump() for turn in request.history],
            granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
            ai_provider_access=effective_ai_provider_access(selected_ids),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def get_jobs(request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    items = [public_job_payload(item, user_id=user_id) for item in list_job_records(user_id)]
    return {"jobs": items}


def get_job(job_id: str, request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    return public_job_payload(record, include_result=True, user_id=user_id)


def get_job_artifact(job_id: str, filename: str, request: Request) -> FileResponse:
    require_authenticated(request)
    file_path = resolve_job_artifact_path(job_id, request_user_id(request), filename)
    return FileResponse(file_path)


def get_analysis_catalog(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, dataset_id or "")
    resolved_dir = resolve_dataset_dir(request, dataset_id or data_dir)
    try:
        return analysis_catalog_payload(
            resolved_dir,
            granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
            ai_provider_access=effective_ai_provider_access(selected_ids),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_molecular_datasets(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        return {"datasets": molecular_dataset_inventory(_resolve_route_dataset_dir(request, dataset_id, data_dir))}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_molecular_genes(dataset_name: str, request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR, q: str = "", limit: int = 50) -> Dict:
    require_authenticated(request)
    try:
        genes = molecular_gene_inventory(_resolve_route_dataset_dir(request, dataset_id, data_dir), dataset_name, search=q, limit=limit)
        return {
            "dataset_name": dataset_name,
            "genes": genes,
            "annotations": molecular_gene_annotations(genes),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_molecular_expression(request: MolecularExpressionRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    try:
        return molecular_expression_summary(
            resolved_dir,
            request.dataset_name,
            request.gene_id,
            selected_patient_ids=request.selected_patient_ids,
            compare_selected_patient_ids=request.compare_selected_patient_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_analysis_sessions(request: Request) -> Dict:
    require_authenticated(request)
    sessions = []
    for item in list_analysis_sessions(user_id=request_user_id(request)):
        session = dict(item)
        session["workspace_status"] = _analysis_session_workspace_status(session, request)
        sessions.append(session)
    return {"sessions": sessions}


def create_or_update_analysis_session(request: AnalysisSessionRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        payload = request.model_dump()
        user_id = request_user_id(raw_request)
        existing = get_analysis_session(request.id, user_id=user_id)
        selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or request.data_dir)
        resolved_scope_id = dataset_scope_id(selected_ids)
        resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
        payload["dataset_id"] = resolved_scope_id
        payload["data_dir"] = resolved_dir
        if existing and isinstance(existing.get("workspace_fingerprint"), dict) and existing.get("workspace_fingerprint"):
            payload["workspace_fingerprint"] = existing.get("workspace_fingerprint")
        else:
            payload["workspace_fingerprint"] = workspace_fingerprint_for_data_dir(
                resolved_dir,
                dataset_id=resolved_scope_id,
                dataset_ids=selected_ids,
            )
        saved = save_analysis_session(payload, user_id=user_id)
        saved["workspace_status"] = _analysis_session_workspace_status(saved, raw_request)
        return saved
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def update_analysis_session_title(session_id: str, request: AnalysisSessionRenameRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    item = rename_analysis_session(session_id, request.title, user_id=request_user_id(raw_request))
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return item


def remove_analysis_session(
    session_id: str,
    request: Request,
    delete_generated_data: bool = Query(default=False),
) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    session_exists = any(
        str(item.get("id") or "").strip() == session_id
        for item in list_analysis_sessions(user_id=user_id)
    )
    if not session_exists:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    deleted_job_count = 0
    if delete_generated_data:
        related_jobs = list_jobs_for_analysis_session(session_id, user_id)
        active = [
            item
            for item in related_jobs
            if str(item.get("status") or "").strip().lower() in {"queued", "running"}
        ]
        if active:
            raise HTTPException(
                status_code=409,
                detail="This analysis session has active background jobs. Wait for them to finish before deleting generated data.",
            )
        for item in related_jobs:
            if delete_job(str(item.get("job_id") or "").strip(), user_id):
                deleted_job_count += 1
    deleted = delete_analysis_session(session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return {
        "deleted": True,
        "id": session_id,
        "deleted_generated_data": bool(delete_generated_data),
        "deleted_job_count": deleted_job_count,
    }


def run_pheno_ranker_route(request: PhenoRankerRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    user_id = request_user_id(raw_request)
    resolved_dataset_id = request.dataset_id or request.data_dir
    selected_ids = resolve_dataset_ids(raw_request, resolved_dataset_id)
    resolved_scope_id = dataset_scope_id(selected_ids)
    resolved_dir = resolve_dataset_dir(raw_request, resolved_dataset_id)
    granularity_ceiling = effective_query_granularity_ceiling(selected_ids)
    if granularity_ceiling != "detailed":
        raise HTTPException(status_code=403, detail="Pheno-Ranker requires Detailed in-app access for the current dataset or workspace.")
    try:
        ensure_query_store(resolved_dir)
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = request.model_copy(
        update={
            "data_dir": resolved_dir,
            "dataset_id": resolved_scope_id,
            "granularity_ceiling": granularity_ceiling,
            "ai_provider_access": effective_ai_provider_access(selected_ids),
        }
    )
    active_pheno_job = active_feature_job(user_id, "pheno")
    if active_pheno_job:
        label = str(active_pheno_job.get("job_code") or active_pheno_job.get("job_id") or "").strip()
        detail = "A Pheno-Ranker background run is already in progress."
        if label:
            detail = f"{detail} {label}."
        raise HTTPException(status_code=409, detail=detail)

    pheno_background = pheno_run_requires_background_job(payload, user_id=user_id)
    if pheno_background.get("exceeds_hard_cap"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Pheno-Ranker cohort runs are currently capped at "
                f"{int(pheno_background.get('hard_cap') or 0)} resolved samples. "
                f"This request resolved to {int(pheno_background.get('resolved_sample_count') or 0)} samples."
            ),
        )
    if pheno_background["requires_background_job"]:
        try:
            job = submit_pheno_job(
                user_id=user_id,
                payload={
                    "name": "Pheno-Ranker cohort run",
                    "prompt": request.prompt,
                    "dataset_id": resolved_scope_id,
                    "data_dir": payload.data_dir,
                    "action": payload.action,
                    "mode": payload.mode,
                    "patient_id": payload.patient_id,
                    "selected_patient_ids": payload.selected_patient_ids,
                    "selected_saved_cohort_ids": payload.selected_saved_cohort_ids,
                    "disease_filter": payload.disease_filter,
                    "include_terms": payload.include_terms,
                    "exclude_terms": payload.exclude_terms,
                    "similarity_metric_cohort": payload.similarity_metric_cohort,
                    "sort_by": payload.sort_by,
                    "max_out": payload.max_out,
                    "align": payload.align,
                    "render_heatmap": payload.render_heatmap,
                    "render_mds": payload.render_mds,
                    "render_graph": payload.render_graph,
                    "graph_min_weight": payload.graph_min_weight,
                    "graph_max_weight": payload.graph_max_weight,
                    "granularity_ceiling": payload.granularity_ceiling,
                    "ai_provider_access": payload.ai_provider_access,
                    "resolved_sample_count": pheno_background["resolved_sample_count"],
                },
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "intent": "pheno_run",
            "job_id": str(job.get("job_id") or ""),
            "job_code": str(job.get("job_code") or ""),
            "status": str(job.get("status") or "queued"),
            "feature": "pheno",
            "mode": str(payload.mode or "cohort"),
            "dataset_id": resolved_scope_id,
            "resolved_sample_count": int(pheno_background["resolved_sample_count"]),
            "background_threshold": int(pheno_background["threshold"]),
            "reply": (
                f"Background Pheno-Ranker run {str(job.get('job_code') or job.get('job_id') or '').strip()} "
                f"submitted for {int(pheno_background['resolved_sample_count'])} samples."
            ),
            "data": {
                "source": "deterministic",
                "execution": "queued",
                "job_id": str(job.get("job_id") or ""),
                "job_status": str(job.get("status") or "queued"),
                "job_code": str(job.get("job_code") or ""),
                "feature": "pheno",
            },
        }
    return run_pheno_ranker(payload)


def plan_pheno_ranker_route(request: PhenoRankerPlanRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or "")
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    try:
        ensure_query_store(resolved_dir)
        return plan_pheno_ranker(
            request.text,
            resolved_dir,
            selected_patient_ids=request.selected_patient_ids,
            ai_provider_access=effective_ai_provider_access(selected_ids),
        )
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_pheno_ranker_patient_ids(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, dataset_id or data_dir)
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(status_code=403, detail="Pheno-Ranker requires Detailed in-app access for the current dataset or workspace.")
    resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
    try:
        ensure_query_store(resolved_dir)
        return pheno_ranker_patient_ids_payload(resolved_dir)
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_pheno_ranker_result(job_id: str, filename: str, request: Request) -> FileResponse:
    require_authenticated(request)
    file_path = pheno_ranker_result_file_path(job_id, filename, user_id=request_user_id(request))
    return FileResponse(file_path)


def get_pheno_ranker_alignment(job_id: str, reference_id: str, request: Request, target_id: str = "") -> Dict:
    require_authenticated(request)
    return pheno_ranker_alignment_details(job_id, reference_id, target_id=target_id, user_id=request_user_id(request))


def explain_pheno_ranker_results(job_id: str, request: Request, top_n: int = 3) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, "")
    return pheno_ranker_explain(job_id, top_n=top_n, ai_provider_access=effective_ai_provider_access(selected_ids), user_id=request_user_id(request))


def explain_pheno_ranker_results_llm(job_id: str, request: Request, top_n: int = 3) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, "")
    return pheno_ranker_explain_llm(job_id, top_n=top_n, ai_provider_access=effective_ai_provider_access(selected_ids), user_id=request_user_id(request))


def get_dashboard(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        return dashboard_summary(resolved_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def register_routes(app: FastAPI, template_engine: Jinja2Templates) -> None:
    init_routes_templates(template_engine)

    app.add_api_route("/", index, methods=["GET"], response_class=HTMLResponse, tags=["ui"], summary="Render the main application shell", description="Serves the Patient Navigator HTML shell with the current branding and authenticated user context.")
    app.add_api_route("/patients", get_patients, methods=["GET"], tags=["patients"], summary="List patient summaries", description="Returns patient-level summaries for the active dataset or workspace scope.", response_model=List[PatientSummaryResponse])
    app.add_api_route("/patients/{patient_id}", get_patient, methods=["GET"], tags=["patients"], summary="Get a patient context", description="Returns the normalized clinical context for a single patient identifier.")
    app.add_api_route("/patients/{patient_id}/navigator", get_patient_navigator, methods=["GET"], tags=["patients"], summary="Get a patient navigator view", description="Returns the timeline-oriented patient navigator payload used by the patient detail view.")
    app.add_api_route("/cohorts/medications", get_medication_counts, methods=["GET"], tags=["patients"], summary="Count medications in the workspace", description="Returns medication counts derived from the active workspace.")
    app.add_api_route("/cohorts/diseases", get_disease_counts, methods=["GET"], tags=["patients"], summary="Count diseases in the workspace", description="Returns disease counts derived from the active workspace.")
    app.add_api_route("/cohorts/medications/search", search_medication_cohort, methods=["GET"], tags=["patients"], summary="Build a medication workspace", description="Returns the deterministic medication-matched workspace subset for a single medication label.")
    app.add_api_route("/query", query_app, methods=["GET"], tags=["query"], summary="Run a simple GET workspace query", description="Executes a lightweight workspace query using query-string parameters. Prefer POST /query for full prompt history and planner mode control.")
    app.add_api_route("/lm-status", get_lm_status, methods=["GET"], tags=["auth"], summary="Inspect configured LM status", description="Returns whether LM Studio is enabled plus the current model and base URL.", response_model=LmStatusResponse)
    app.add_api_route("/auth/me", get_auth_status, methods=["GET"], tags=["auth"], summary="Get current authentication state", description="Returns the current local-auth session state and visible user identity.", response_model=AuthStatusResponse)
    app.add_api_route("/auth/login", login_local, methods=["POST"], tags=["auth"], summary="Log in with local credentials", description="Authenticates a local user and creates a session-backed login.", response_model=AuthStatusResponse)
    app.add_api_route("/auth/logout", logout_local, methods=["POST"], tags=["auth"], summary="Log out the current user", description="Clears the local session for the current user.", response_model=AuthStatusResponse)
    app.add_api_route("/auth/password-reset/request", request_auth_password_reset, methods=["POST"], tags=["auth"], summary="Request a local password reset", description="Sends a password reset email when SMTP-backed local reset is configured. The response does not reveal whether the account exists.", response_model=AuthPasswordResetResponse)
    app.add_api_route("/auth/password-reset/confirm", confirm_auth_password_reset, methods=["POST"], tags=["auth"], summary="Confirm a local password reset", description="Consumes a password reset token and replaces the local password.", response_model=AuthPasswordResetResponse)
    app.add_api_route("/auth/debug", get_auth_diagnostics, methods=["GET"], tags=["auth"], summary="Inspect auth diagnostics", description="Returns local-auth diagnostics useful during development and deployment troubleshooting.", response_model=AuthDiagnosticsResponse)
    app.add_api_route("/auth/users", get_auth_users, methods=["GET"], tags=["auth"], summary="List visible local users", description="Returns local users and groups. When auth is enabled, this endpoint is admin-only.", response_model=AuthUsersResponse)
    app.add_api_route("/auth/users", create_auth_user, methods=["POST"], tags=["auth"], summary="Create a local user", description="Creates a persisted local user with application role and groups. Admin-only when auth is enabled.", response_model=AuthUserResponse)
    app.add_api_route("/auth/users/{username}", update_auth_user, methods=["PATCH"], tags=["auth"], summary="Update a local user", description="Updates display name, role, groups, or enabled state for a local user. Admin-only when auth is enabled.", response_model=AuthUserResponse)
    app.add_api_route("/auth/users/{username}/password", reset_auth_user_password, methods=["POST"], tags=["auth"], summary="Reset a local user password", description="Replaces the password for a local user. Admin-only when auth is enabled.", response_model=AuthUserResponse)
    app.add_api_route("/auth/users/{username}", delete_auth_user, methods=["DELETE"], tags=["auth"], summary="Delete a local user", description="Deletes a persisted local user. Admin-only when auth is enabled.", response_model=DeleteResponse)
    app.add_api_route("/user-settings", get_user_settings, methods=["GET"], tags=["auth"], summary="Get user UI settings", description="Returns persisted UI preferences for the current user.", response_model=UserSettingsResponse)
    app.add_api_route("/user-settings", update_user_settings, methods=["PATCH"], tags=["auth"], summary="Update user UI settings", description="Persists UI preferences for the current user.", response_model=UserSettingsResponse)
    app.add_api_route("/datasets", get_datasets, methods=["GET"], tags=["datasets"], summary="List authorized datasets", description="Returns datasets visible to the current user plus the currently active workspace selection.", response_model=DatasetsResponse)
    app.add_api_route("/datasets/select", select_dataset, methods=["POST"], tags=["datasets"], summary="Select the active dataset workspace", description="Applies one or more authorized dataset IDs as the current workspace for the authenticated user.", response_model=DatasetSelectionResponse)
    app.add_api_route("/datasets", create_dataset_route, methods=["POST"], tags=["datasets"], summary="Register a dataset", description="Creates a new dataset registry entry. Admin-only.", response_model=DatasetRecordResponse)
    app.add_api_route("/datasets/{dataset_id}", update_dataset_route, methods=["PATCH"], tags=["datasets"], summary="Update dataset metadata and access", description="Updates dataset metadata, visibility, or access policy. Admin-only.", response_model=DatasetRecordResponse)
    app.add_api_route("/datasets/{dataset_id}/prepare-store", prepare_dataset_route, methods=["POST"], tags=["datasets"], summary="Prepare dataset DuckDB store", description="Builds or rebuilds the admin-managed DuckDB store for one dataset. Admin-only.", response_model=DatasetRecordResponse)
    app.add_api_route("/branding/logo", get_branding_logo, methods=["GET"], tags=["ui"], summary="Serve the configured branding logo", description="Returns the current instance branding logo file if one is configured.")
    app.add_api_route("/saved-cohorts", get_saved_cohorts, methods=["GET"], tags=["cohorts"], summary="List saved cohorts", description="Returns saved cohorts for the current user within the active dataset workspace.", response_model=SavedCohortsResponse)
    app.add_api_route("/saved-cohorts", create_saved_cohort, methods=["POST"], tags=["cohorts"], summary="Create a saved cohort", description="Persists a saved cohort containing canonical sample IDs and derived patient IDs.", response_model=SavedCohortResponse)
    app.add_api_route("/saved-cohorts/{cohort_id}", remove_saved_cohort, methods=["DELETE"], tags=["cohorts"], summary="Delete a saved cohort", description="Deletes a saved cohort owned by the current user.", response_model=DeleteResponse)
    app.add_api_route("/user-data/analysis-sessions", delete_user_analysis_sessions, methods=["DELETE"], tags=["auth"], summary="Delete current user's analysis chats", description="Deletes all saved analysis chats owned by the current user.")
    app.add_api_route("/user-data/jobs", delete_user_completed_jobs, methods=["DELETE"], tags=["auth"], summary="Delete current user's completed jobs", description="Deletes terminal background jobs and generated artifacts owned by the current user. Active jobs are skipped.")
    app.add_api_route("/user-data/saved-cohorts", delete_user_saved_cohorts, methods=["DELETE"], tags=["auth"], summary="Delete current user's saved cohorts", description="Deletes saved cohorts owned by the current user when they are not referenced by saved analysis chats.")
    app.add_api_route("/query", query_app_post, methods=["POST"], tags=["query"], summary="Run a workspace query", description="Executes a deterministic and/or LLM-assisted natural-language query against the active workspace.")
    app.add_api_route("/analysis/catalog", get_analysis_catalog, methods=["GET"], tags=["analysis"], summary="List curated analysis catalog entries", description="Returns curated analysis definitions plus computed availability for the current workspace.")
    app.add_api_route("/analysis", analysis_app, methods=["POST"], tags=["analysis"], summary="Run a workspace analysis", description="Executes clinical or molecular analysis over the active workspace or selected saved cohorts.")
    app.add_api_route("/jobs", get_jobs, methods=["GET"], tags=["jobs"], summary="List recent background jobs", description="Returns recent background jobs visible to the current user across supported product surfaces.")
    app.add_api_route("/jobs/{job_id}", get_job, methods=["GET"], tags=["jobs"], summary="Get one background job", description="Returns detailed status plus the completed payload for one background job visible to the current user.")
    app.add_api_route("/jobs/{job_id}/artifacts/{filename:path}", get_job_artifact, methods=["GET"], tags=["jobs"], summary="Download one background job artifact", description="Returns one persisted artifact for a background job visible to the current user.")
    app.add_api_route("/molecular/datasets", get_molecular_datasets, methods=["GET"], tags=["molecular"], summary="List molecular datasets in scope", description="Returns transcriptomic datasets visible in the current workspace.", response_model=MolecularDatasetsResponse)
    app.add_api_route("/molecular/genes", get_molecular_genes, methods=["GET"], tags=["molecular"], summary="Search genes in a molecular dataset", description="Returns gene identifiers for a selected molecular dataset with optional search and limit filtering.")
    app.add_api_route("/molecular/expression", get_molecular_expression, methods=["POST"], tags=["molecular"], summary="Summarize gene expression", description="Returns scoped gene expression summaries for one molecular dataset, optionally comparing cohort A and cohort B.")
    app.add_api_route("/analysis-sessions", get_analysis_sessions, methods=["GET"], tags=["analysis"], summary="List saved analysis sessions", description="Returns persisted analysis sessions for the current user.")
    app.add_api_route("/analysis-sessions", create_or_update_analysis_session, methods=["POST"], tags=["analysis"], summary="Create or update an analysis session", description="Persists analysis session state, including prompt draft, scopes, and prior turns.")
    app.add_api_route("/analysis-sessions/{session_id}", update_analysis_session_title, methods=["PATCH"], tags=["analysis"], summary="Rename an analysis session", description="Updates the title of a saved analysis session.")
    app.add_api_route("/analysis-sessions/{session_id}", remove_analysis_session, methods=["DELETE"], tags=["analysis"], summary="Delete an analysis session", description="Deletes a saved analysis session for the current user.", response_model=DeleteResponse)
    app.add_api_route("/pheno-ranker/run", run_pheno_ranker_route, methods=["POST"], tags=["pheno-ranker"], summary="Run Pheno-Ranker", description="Runs Pheno-Ranker for the active workspace using either patient mode or cohort mode.")
    app.add_api_route("/pheno-ranker/plan", plan_pheno_ranker_route, methods=["POST"], tags=["pheno-ranker"], summary="Plan a Pheno-Ranker run", description="Converts a natural-language request into a normalized Pheno-Ranker execution plan.")
    app.add_api_route("/pheno-ranker/patient-ids", get_pheno_ranker_patient_ids, methods=["GET"], tags=["pheno-ranker"], summary="List Pheno-Ranker scope IDs", description="Returns the sample-level identifiers currently available to Pheno-Ranker in the active workspace.")
    app.add_api_route("/pheno-ranker/results/{job_id}/{filename}", get_pheno_ranker_result, methods=["GET"], tags=["pheno-ranker"], summary="Download a Pheno-Ranker result file", description="Returns a generated Pheno-Ranker result artifact for a specific job.")
    app.add_api_route("/pheno-ranker/alignment/{job_id}", get_pheno_ranker_alignment, methods=["GET"], tags=["pheno-ranker"], summary="Get alignment details for one match", description="Returns the term-level alignment details between a target and a selected Pheno-Ranker match.")
    app.add_api_route("/pheno-ranker/explain/{job_id}", explain_pheno_ranker_results, methods=["GET"], tags=["pheno-ranker"], summary="Explain Pheno-Ranker results deterministically", description="Builds a deterministic summary from the top ranked Pheno-Ranker matches.")
    app.add_api_route("/pheno-ranker/explain-llm/{job_id}", explain_pheno_ranker_results_llm, methods=["GET"], tags=["pheno-ranker"], summary="Explain Pheno-Ranker results with the LLM", description="Builds an LLM-assisted explanation from the top ranked Pheno-Ranker matches.")
    app.add_api_route("/dashboard", get_dashboard, methods=["GET"], tags=["patients"], summary="Get the dashboard summary", description="Returns the dashboard summary payload used by the clinical and molecular overview panels.")
