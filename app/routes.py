from __future__ import annotations

import json
from app import query_sessions
from app.schemas import QuerySessionRequest
from app.chat_folders import router as chat_folders_router

import os
import re
import secrets
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    auth_enabled,
    auth_mode,
    authenticate_local_user,
    auth_provider_mode,
    create_local_user,
    confirm_password_reset,
    delete_local_user,
    find_oidc_user,
    local_fallback_enabled,
    local_auth_diagnostics,
    local_users,
    oidc_authorization_url,
    oidc_configured,
    oidc_provider_name,
    oidc_userinfo_from_code,
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
    build_patient_workspace,
    dashboard_summary,
    get_patient_context,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
)
from app.config import DEFAULT_DATA_DIR, branding_logo_path, branding_settings, private_artifact_runtime_is_safe
from app.cohorts import delete_saved_cohort, list_saved_cohorts, save_cohort
from app.datasets import (
    authorized_datasets_for_user,
    constrain_ai_provider_access,
    current_dataset_id,
    current_dataset_ids,
    clinical_representation,
    dataset_content_metadata,
    dataset_scope_id,
    effective_ai_provider_access,
    effective_data_classification,
    effective_query_granularity_ceiling,
    normalize_dataset_id,
    normalize_query_granularity_ceiling,
    parse_scope_dataset_ids,
    register_dataset,
    resolve_dataset,
    resolve_dataset_dir,
    resolve_dataset_ids,
    set_current_dataset,
    set_current_datasets,
    update_dataset,
    workspace_fingerprint_for_data_dir,
)
from app.dicom import dicom_status, dicom_studies
from app.lm import (
    DEFAULT_LLM_PROVIDER_ID,
    create_managed_lm_provider,
    delete_managed_lm_provider,
    general_llm_reply,
    llm_provider_registry_status,
    lm_provider_context,
    lm_provider_data_boundary,
    lm_studio_health,
    test_lm_provider,
    update_managed_lm_provider,
)
from app.multimodal import multimodal_feature_matrix, multimodal_readiness
from app.jobs import (
    _authorize_analysis_scope,
    active_feature_job,
    active_job_status,
    analysis_worker_status,
    create_job_record,
    delete_expired_terminal_jobs,
    delete_job,
    job_dir,
    list_job_records,
    list_jobs_for_analysis_session,
    load_job_record,
    public_job_payload,
    resolve_job_artifact_path,
    save_job_result,
    submit_pheno_job,
    terminal_job_status,
    update_job_record,
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
from app.env import app_env
from app.query_store import assay_dataset_inventory, assay_expression_summary, assay_feature_annotations, assay_feature_inventory
from app.query_store import (
    QueryStoreNotReadyError,
    dataset_query_store_status,
    ensure_dataset_query_stores_ready,
    ensure_query_store,
    patient_clarid,
    patient_clarid_inventory,
    prepare_dataset_query_store,
    resolve_patient_identifier,
)
from app.user_settings import load_user_settings, update_user_settings as patch_user_settings
from app.query_results import (
    QUERY_RESULT_DEFAULT_PAGE_SIZE,
    QueryResultExpiredError,
    QueryResultNotFoundError,
    QueryResultStaleError,
    create_query_result,
    delete_query_results,
    load_query_result,
    query_result_membership,
    query_result_page,
    require_query_result_binding,
)
from app.query_policy import query_is_count_only, response_patient_ids, response_record_ids
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
    GeneralLlmRequest,
    AssayExpressionRequest,
    AssayDatasetsResponse,
    AssayFeatureMatrixResponse,
    AssayReadinessResponse,
    DicomStatusResponse,
    DicomStudiesResponse,
    LmStatusResponse,
    PatientSummaryResponse,
    PhenoRankerPlanRequest,
    PhenoRankerRequest,
    QueryRequest,
    QueryTurn,
    SavedCohortRequest,
    SavedCohortResponse,
    SavedCohortsResponse,
    LoginRequest,
    LmProviderCreateRequest,
    LmProviderResponse,
    LmProvidersResponse,
    LmProviderUpdateRequest,
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
from app.user_state import request_user_id, request_user_identity


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
    visible_datasets = [_dataset_record_for_user(item, user) for item in datasets]
    selected_name = str(selected.get("name") or selected.get("dataset_id") or "Not configured")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_data_dir": selected_name,
            "datasets": visible_datasets,
            "current_dataset_id": str(selected.get("dataset_id") or ""),
            "branding": branding_settings(),
            "appearance": load_user_settings(request_user_id(request)).get("appearance", "light") if user else "light",
            "auth_enabled": auth_enabled(),
            "desktop_mode": app_env("COHORTOME_DESKTOP_MODE").strip().lower() in {"1", "true", "yes", "on"},
        },
    )


def _dataset_record_for_user(item: Dict[str, Any], user: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(item)
    store_status = payload.get("query_store_status")
    if isinstance(store_status, dict):
        payload["query_store_status"] = _public_dataset_store_status(store_status)
    if str((user or {}).get("role") or "user") != "admin":
        payload["root_path"] = ""
    return payload


def _public_dataset_store_status(status: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(status)
    if str(payload.get("last_error") or "").strip():
        payload["last_error"] = "Store preparation failed. Review server logs for technical details."
    return payload


def _authorized_datasets_for_request(request: Request | None) -> List[Dict[str, Any]]:
    user = session_user(request) if request is not None and auth_enabled() else None
    if user:
        return authorized_datasets_for_user(user)
    if auth_enabled():
        return []
    return authorized_datasets_for_user({"username": "local", "role": "admin", "display_name": "Local user"})


def _safe_source_path(request: Request | None, value: str) -> str:
    source = str(value or "").strip()
    if not source:
        return source
    try:
        path = Path(source).expanduser()
    except (OSError, RuntimeError, ValueError):
        return source
    is_absolute = path.is_absolute() or PureWindowsPath(source).is_absolute()
    if not is_absolute:
        return source
    if path.is_absolute():
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        for dataset in _authorized_datasets_for_request(request):
            dataset_id = str(dataset.get("dataset_id") or "dataset").strip() or "dataset"
            root_path = str(dataset.get("root_path") or "").strip()
            if not root_path:
                continue
            try:
                relative = resolved.relative_to(Path(root_path).expanduser().resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            return f"{dataset_id}:{relative.as_posix()}"
    return "[filesystem path redacted]"


def _sanitize_response_paths(value: Any, request: Request | None) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_response_paths(item, request) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_response_paths(item, request) for item in value]
    if isinstance(value, str):
        return _safe_source_path(request, value)
    return value


def _dataset_provenance_from_sources(request: Request | None, source_files: List[str]) -> Dict[str, Any]:
    datasets = _authorized_datasets_for_request(request)
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


def _route_dataset_ids(
    request: Request,
    dataset_id: str = "",
    data_dir: str = DEFAULT_DATA_DIR,
) -> List[str]:
    selected_ids = resolve_dataset_ids(request, dataset_id or data_dir)
    if not selected_ids:
        raise HTTPException(status_code=409, detail="No active workspace. Select and apply a dataset first.")
    return selected_ids


def _route_allows_detailed_identifiers(
    request: Request | None,
    dataset_id: str = "",
    data_dir: str = DEFAULT_DATA_DIR,
) -> bool:
    if request is None:
        return True
    return effective_query_granularity_ceiling(
        _route_dataset_ids(request, dataset_id, data_dir)
    ) == "detailed"


def _require_detailed_assay_access(
    request: Request,
    dataset_id: str = "",
    data_dir: str = DEFAULT_DATA_DIR,
) -> List[str]:
    selected_ids = _route_dataset_ids(request, dataset_id, data_dir)
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(
            status_code=403,
            detail="Sample-level assay and imaging data require Detailed in-app access for the current dataset or workspace.",
        )
    return selected_ids


def _summary_safe_assay_inventory(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary_items: List[Dict[str, Any]] = []
    for raw_item in items:
        item = dict(raw_item or {})
        item.pop("sample_ids", None)
        item.pop("patient_ids", None)
        summary_items.append(item)
    return summary_items


def _query_result_policy_binding(dataset_ids: List[str], request: Request | None = None) -> Dict[str, Any]:
    registry_records = {
        str(item.get("dataset_id") or ""): item
        for item in _authorized_datasets_for_request(request)
    }
    registry_binding = []
    for dataset_id in sorted(set(dataset_ids)):
        item = registry_records.get(dataset_id) or {}
        registry_binding.append(
            {
                "dataset_id": dataset_id,
                "root_path": str(item.get("root_path") or ""),
                "updated_at": str(item.get("updated_at") or ""),
                "data_classification": str(item.get("data_classification") or "private"),
            }
        )
    return {
        "granularity_ceiling": effective_query_granularity_ceiling(dataset_ids),
        "data_classification": effective_data_classification(dataset_ids),
        "registry": registry_binding,
    }


def _query_result_workspace(
    request: Request,
    dataset_id: str = "",
) -> tuple[List[str], str, str, Dict[str, Any], Dict[str, Any]]:
    selected_ids = resolve_dataset_ids(request, dataset_id)
    if not selected_ids:
        raise HTTPException(status_code=409, detail="No active workspace. Select and apply a dataset first.")
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(status_code=403, detail="Query results require Detailed in-app access for the current workspace.")
    scope_id = dataset_scope_id(selected_ids)
    resolved_dir = resolve_dataset_dir(request, scope_id)
    fingerprint = workspace_fingerprint_for_data_dir(
        resolved_dir,
        dataset_id=scope_id,
        dataset_ids=selected_ids,
    )
    return selected_ids, scope_id, resolved_dir, fingerprint, _query_result_policy_binding(selected_ids, request)


def _load_authorized_query_result(
    request: Request,
    handle: str,
    *,
    dataset_id: str = "",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    user_id = request_user_identity(request)
    try:
        record = load_query_result(user_id, handle)
    except QueryResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryResultExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    stored_scope_id = str(record.get("dataset_id") or "").strip()
    requested_scope_id = str(dataset_id or "").strip()
    if requested_scope_id and requested_scope_id != stored_scope_id:
        raise HTTPException(status_code=410, detail="Query result belongs to a different workspace.")
    selected_ids, scope_id, _, fingerprint, policy_binding = _query_result_workspace(request, stored_scope_id)
    if policy_binding.get("data_classification") == "private" and not private_artifact_runtime_is_safe():
        raise HTTPException(
            status_code=503,
            detail="Private query-result state requires protected runtime storage.",
        )
    try:
        require_query_result_binding(
            record,
            dataset_id=scope_id,
            dataset_ids=selected_ids,
            workspace_fingerprint=fingerprint,
            policy_binding=policy_binding,
        )
    except QueryResultStaleError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return record, query_result_membership(record)


def _query_result_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    patients = data.get("patients")
    if isinstance(patients, list):
        return [dict(item) for item in patients if isinstance(item, dict)]
    return []


def _bounded_query_data(
    data: Dict[str, Any],
    page: Dict[str, Any],
    membership_ids: List[str],
) -> Dict[str, Any]:
    membership_keys = {
        "patient_id",
        "patient_ids",
        "sample_id",
        "sample_ids",
        "original_id",
        "original_record_ids",
        "invalid_patient_ids",
        "record_ids",
        "scope_ids",
        "patients",
        "visits",
        "timeline",
        "patient_context",
        "conversation_history",
        "follow_up_suggestions",
        "follow_up_suggestion_metadata",
    }

    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key not in membership_keys}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    shaped = strip(data)
    shaped["result_handle"] = page["result_handle"]
    shaped["result_page"] = page
    shaped["patient_ids"] = page["patient_ids"]
    shaped["sample_ids"] = page["sample_ids"]
    shaped["patients"] = page["rows"] if page["id_type"] == "patient" else []
    suggestions = data.get("follow_up_suggestions")
    safe_suggestions = []
    if isinstance(suggestions, list):
        for item in suggestions:
            text = str(item or "").strip()
            if text and not any(identifier and identifier in text for identifier in membership_ids):
                safe_suggestions.append(text)
    if safe_suggestions:
        shaped["follow_up_suggestions"] = safe_suggestions
        safe_prompts = set(safe_suggestions)
        metadata = data.get("follow_up_suggestion_metadata")
        if isinstance(metadata, list):
            shaped["follow_up_suggestion_metadata"] = [
                dict(item)
                for item in metadata
                if isinstance(item, dict) and str(item.get("prompt") or "").strip() in safe_prompts
            ]
    return shaped


def _safe_query_history(turns: List[QueryTurn]) -> List[Dict[str, str]]:
    safe: List[Dict[str, str]] = []
    for turn in turns:
        role = str(turn.role or "user")
        content = str(turn.content or "")
        content = re.sub(r"\bqr_[A-Za-z0-9_-]{8,96}\b", "[query result]", content)
        if role == "assistant":
            content = "Previous workspace answer omitted; use the server-side Query result scope."
        safe.append({"role": role, "content": content})
    return safe


def _materialize_query_response(
    payload: Dict[str, Any],
    request: Request,
    *,
    selected_ids: List[str],
    scope_id: str,
    resolved_dir: str,
) -> Dict[str, Any]:
    if query_is_count_only(payload):
        return payload
    intent = str(payload.get("intent") or "").strip()
    if intent in {"patient_summary", "patient_timeline", "patient_visits", "patient_lookup"}:
        return payload
    data = payload.get("data")
    if not isinstance(data, dict) or str(data.get("granularity_applied") or "") != "detailed":
        return payload
    patient_ids = response_patient_ids(payload)
    sample_ids = response_record_ids(payload)
    if intent == "sample_inventory" and not patient_ids:
        patient_ids = [
            str(item).split(":", 1)[0].strip()
            for item in sample_ids
            if str(item).split(":", 1)[0].strip()
        ]
    if not patient_ids and not sample_ids:
        return payload
    fingerprint = workspace_fingerprint_for_data_dir(
        resolved_dir,
        dataset_id=scope_id,
        dataset_ids=selected_ids,
    )
    private_scope = any(
        str(item.get("data_classification") or "private").strip().lower() == "private"
        for item in _authorized_datasets_for_request(request)
        if str(item.get("dataset_id") or "") in set(selected_ids)
    )
    record = create_query_result(
        user_id=request_user_identity(request),
        dataset_id=scope_id,
        dataset_ids=selected_ids,
        workspace_fingerprint=fingerprint,
        policy_binding=_query_result_policy_binding(selected_ids, request),
        patient_ids=patient_ids,
        sample_ids=sample_ids,
        rows=_query_result_rows(payload),
        query_text=str(payload.get("query") or ""),
        id_type="sample" if intent == "sample_inventory" and sample_ids else "patient",
        private_scope=private_scope,
    )
    page = query_result_page(record, limit=QUERY_RESULT_DEFAULT_PAGE_SIZE)
    shaped = dict(payload)
    shaped_data = _bounded_query_data(data, page, patient_ids + sample_ids)
    shaped["data"] = shaped_data
    shaped["reply"] = (
        f"Found {page['total_count']} {'patient' if page['total_count'] == 1 else 'patients'}. "
        f"Showing {page['returned_count']} now; use Load more to continue."
        if page["id_type"] == "patient"
        else f"Found {page['total_count']} {'sample' if page['total_count'] == 1 else 'samples'}. Showing {page['returned_count']} now."
    )
    shaped["action_context"] = {
        "result_handle": page["result_handle"],
        "patient_ids": [],
        "record_ids": [],
        "id_type": page["id_type"],
        "analysis_prompt": "Interpret this selected workspace subset and summarize the main clinical and treatment patterns.",
    }
    shaped_data["available_actions"] = {
        "open_in_analysis": True,
        "save_cohort": bool(patient_ids),
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }
    return shaped


def get_query_result_page(
    handle: str,
    request: Request,
    cursor: str = Query(default="", max_length=256),
    limit: int = Query(default=QUERY_RESULT_DEFAULT_PAGE_SIZE, ge=1, le=100),
    sort_by: str = "",
    sort_direction: str = "asc",
) -> JSONResponse:
    require_authenticated(request)
    record, _ = _load_authorized_query_result(request, handle)
    record = _ordered_query_result(record, request, sort_by, sort_direction)
    try:
        page = query_result_page(record, cursor=cursor, limit=limit)
        return JSONResponse(page, headers={"Cache-Control": "no-store"})
    except QueryResultStaleError as exc:
        if "cursor" in str(exc).lower():
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=410, detail=str(exc)) from exc


def _ordered_query_result(record, request, sort_by, sort_direction, patients=None):
    from app import exports
    from app.query_results import sort_query_result
    if not sort_by:
        if sort_direction != "asc":
            raise HTTPException(400, "Choose a sort column before a direction.")
        return record
    exports.check_size(len(record.get("items") or []))
    if patients is None:
        patients = get_patients(request, dataset_id=record["dataset_id"])
    rows, _ = exports.query_rows(record, patients)
    try:
        return sort_query_result(record, rows, sort_by, sort_direction)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def export_query_result(handle: str, request: Request, format: str = "tsv", sort_by: str = "", sort_direction: str = "asc"):
    from app import exports
    require_authenticated(request)
    if format not in {"tsv", "csv", "json"}:
        raise HTTPException(400, "Choose TSV, CSV or JSON metadata.")
    record, _ = _load_authorized_query_result(request, handle)
    exports.check_size(len(record.get("items") or []))
    patients = get_patients(request, dataset_id=record["dataset_id"]) if format != "json" or sort_by else None
    record = _ordered_query_result(record, request, sort_by, sort_direction, patients)
    if format == "json":
        meta = exports.metadata("query_result", record.get("dataset_ids") or [],
                                len(record.get("items") or []), id_type=record.get("id_type"),
                                query_created_at=record.get("created_at"),
                                query_text=record.get("query_text", ""),
                                sort_by=sort_by or "original_result_order", sort_direction=sort_direction,
                                workspace_fingerprint=(record.get("workspace_fingerprint") or {}).get("token", ""),
                                scope="All rows in the stored query result; no query is rerun.")
        return exports.attachment(exports.json_bytes(meta), "query-result-metadata.json", "application/json")
    rows, columns = exports.query_rows(record, patients)
    content = exports.table_bytes(rows, columns, "," if format == "csv" else "\t")
    return exports.attachment(content, f"query-result.{format}",
                              "text/csv" if format == "csv" else "text/tab-separated-values")


def export_saved_cohort(cohort_id: str, request: Request):
    from app import exports
    require_authenticated(request)
    cohort = next((item for item in list_saved_cohorts(user_id=request_user_id(request))
                   if item.get("id") == cohort_id), None)
    if cohort is None:
        raise HTTPException(404, "Saved cohort not found.")
    scope_id = str(cohort.get("dataset_id") or "")
    if not parse_scope_dataset_ids(scope_id):
        raise HTTPException(409, "This cohort has no registered dataset scope.")
    selected_ids = resolve_dataset_ids(request, scope_id)
    if not selected_ids or effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(403, "Cohort export requires Detailed access to every source dataset.")
    if set(cohort.get("dataset_ids") or []) != set(selected_ids):
        raise HTTPException(409, "Saved cohort dataset scope is inconsistent.")
    exports.check_size(len(cohort.get("patient_ids") or []) + len(cohort.get("sample_ids") or []))
    patients = [] if cohort.get('members') is not None else get_patients(request, dataset_id=scope_id)
    return exports.attachment(exports.cohort_bundle(cohort, patients), "saved-cohort.zip", "application/zip")


def get_datasets(request: Request) -> Dict:
    user = require_authenticated(request)
    datasets = []
    authorized = authorized_datasets_for_user(user)
    for item in authorized:
        payload = dict(item)
        payload["query_store_status"] = dataset_query_store_status(str(item.get("dataset_id") or ""))
        try:
            payload.update(dataset_content_metadata(str(item.get("root_path") or "")))
        except FileNotFoundError:
            payload.update({"content_tags": [], "content_summary": "Dataset files are not available."})
        datasets.append(_dataset_record_for_user(payload, user))
    user_id = str(user.get("username") or "local")
    stored_ids = current_dataset_ids(user_id)
    authorized_ids = {str(item.get("dataset_id") or "") for item in authorized}
    selected_ids = stored_ids if stored_ids and all(item in authorized_ids for item in stored_ids) else []
    if selected_ids:
        try:
            ensure_dataset_query_stores_ready(selected_ids)
        except QueryStoreNotReadyError:
            selected_ids = []
    if stored_ids and not selected_ids:
        set_current_datasets(user_id, [])
    return {
        "datasets": datasets,
        "current_dataset_id": selected_ids[0] if len(selected_ids) == 1 else "",
        "current_dataset_ids": selected_ids,
        "current_dataset_scope_id": dataset_scope_id(selected_ids),
        "current_dataset": next((item for item in datasets if str(item.get("dataset_id") or "") == selected_ids[0]), None) if len(selected_ids) == 1 else None,
    }


def select_dataset(payload: DatasetSelectionRequest, request: Request) -> Dict:
    user = require_authenticated(request)
    user_id = str(user.get("username") or "local")
    requested_ids = payload.dataset_ids or ([payload.dataset_id] if payload.dataset_id else [])
    if not requested_ids:
        delete_query_results(user_id)
        set_current_datasets(user_id, [])
        return {
            "selected": False,
            "current_dataset_id": "",
            "current_dataset_ids": [],
            "current_dataset_scope_id": "",
        }
    resolved_ids = []
    for requested_id in requested_ids:
        normalized = normalize_dataset_id(requested_id)
        if not normalized:
            raise HTTPException(status_code=400, detail="Dataset selection contains an invalid id.")
        if normalized not in resolved_ids:
            resolved_ids.append(normalized)
    candidate_map = {
        str(item.get("dataset_id") or ""): item
        for item in authorized_datasets_for_user(user)
    }
    if any(dataset_id not in candidate_map for dataset_id in resolved_ids):
        raise HTTPException(status_code=403, detail="Dataset access denied.")
    try:
        ensure_dataset_query_stores_ready(resolved_ids)
    except QueryStoreNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail="One or more selected dataset stores are not ready. Prepare or rebuild them in Admin > Data.",
        ) from exc
    if resolved_ids != current_dataset_ids(user_id):
        delete_query_results(user_id)
    set_current_datasets(user_id, resolved_ids)
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
            data_classification=payload.data_classification,
            allowed_users=payload.allowed_users,
            allowed_groups=payload.allowed_groups,
            query_granularity_ceiling=payload.query_granularity_ceiling,
            ai_provider_access=payload.ai_provider_access,
            enabled=payload.enabled,
            created_by=str(user.get("username") or "admin"),
        )
        dataset["query_store_status"] = _public_dataset_store_status(
            dataset_query_store_status(str(dataset.get("dataset_id") or ""))
        )
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
            data_classification=payload.data_classification,
            allowed_users=payload.allowed_users,
            allowed_groups=payload.allowed_groups,
            query_granularity_ceiling=payload.query_granularity_ceiling,
            ai_provider_access=payload.ai_provider_access,
            enabled=payload.enabled,
        )
        updated["query_store_status"] = _public_dataset_store_status(
            dataset_query_store_status(str(updated.get("dataset_id") or ""))
        )
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def prepare_dataset_route(dataset_id: str, request: Request) -> Dict:
    require_admin(request)
    try:
        status = prepare_dataset_query_store(dataset_id)
        dataset = resolve_dataset(request, dataset_id)
        payload = dict(dataset)
        payload["query_store_status"] = _public_dataset_store_status(status)
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
        representation = clinical_representation(resolved_dir)
        clarids = (
            patient_clarid_inventory(resolved_dir)
            if _route_allows_detailed_identifiers(request, dataset_id, data_dir)
            else {}
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload: List[Dict[str, Any]] = []
    for patient in patients:
        item = patient.model_dump()
        item.update(_dataset_provenance_from_sources(request, item.get("source_files") or []))
        item["clinical_record_count"] = int(item.get("visit_count") or 0)
        item["clinical_representation"] = representation
        if item.get("patient_id") in clarids:
            item["clarid"] = clarids[item["patient_id"]]
        payload.append(_sanitize_response_paths(item, request))
    return payload


def get_patient(patient_id: str, request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        detailed_identifiers = _route_allows_detailed_identifiers(request, dataset_id, data_dir)
        resolved_identifier = resolve_patient_identifier(resolved_dir, patient_id) if detailed_identifiers else None
        canonical_patient_id = str((resolved_identifier or {}).get("patient_id") or patient_id)
        patient = get_patient_context(resolved_dir, canonical_patient_id)
        representation = clinical_representation(resolved_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    payload = patient.model_dump()
    payload.update(_dataset_provenance_from_sources(request, payload.get("source_files") or []))
    payload["clinical_record_count"] = len(payload.get("visits") or [])
    payload["clinical_representation"] = representation
    if detailed_identifiers:
        clarid = (resolved_identifier or {}).get("clarid") or patient_clarid(resolved_dir, canonical_patient_id)
        if clarid:
            payload["clarid"] = clarid
    return _sanitize_response_paths(payload, request)


def get_patient_workspace(patient_id: str, request: Request = None, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        detailed_identifiers = _route_allows_detailed_identifiers(request, dataset_id, data_dir)
        resolved_identifier = resolve_patient_identifier(resolved_dir, patient_id) if detailed_identifiers else None
        canonical_patient_id = str((resolved_identifier or {}).get("patient_id") or patient_id)
        patient_workspace = build_patient_workspace(resolved_dir, canonical_patient_id)
        representation = clinical_representation(resolved_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if patient_workspace is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    payload = patient_workspace.model_dump()
    provenance = _dataset_provenance_from_sources(request, payload.get("summary", {}).get("source_files") or payload.get("patient_context", {}).get("source_files") or [])
    payload["summary"] = {**payload.get("summary", {}), **provenance}
    payload["patient_context"] = {**payload.get("patient_context", {}), **provenance}
    payload["summary"]["clinical_record_count"] = int(payload["summary"].get("visit_count") or 0)
    payload["patient_context"]["clinical_representation"] = representation
    payload["clinical_representation"] = representation
    if detailed_identifiers:
        clarid = (resolved_identifier or {}).get("clarid") or patient_clarid(resolved_dir, canonical_patient_id)
        if clarid:
            payload["clarid"] = clarid
    return _sanitize_response_paths(payload, request)


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
        payload = medication_cohort(_resolve_route_dataset_dir(request, dataset_id, data_dir), medication)
        return _sanitize_response_paths(payload, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def query_app(q: str, request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    if not str(q or "").strip() or len(str(q)) > 12000:
        raise HTTPException(status_code=422, detail="Query must contain between 1 and 12000 characters.")
    try:
        selected_ids = resolve_dataset_ids(request, dataset_id or "")
        if not selected_ids:
            raise HTTPException(status_code=409, detail="No active workspace. Select and apply a dataset first.")
        scope_id = dataset_scope_id(selected_ids)
        resolved_dir = resolve_dataset_dir(request, scope_id)
        with lm_provider_context(selected_lm_provider_id(request)):
            payload = answer_query(
                resolved_dir,
                q,
                granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
                ai_provider_access=selected_ai_provider_access(request, selected_ids),
            )
            payload = _materialize_query_response(
                payload,
                request,
                selected_ids=selected_ids,
                scope_id=scope_id,
                resolved_dir=resolved_dir,
            )
            return _sanitize_response_paths(payload, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        if "Private query-result state requires" in str(exc):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise


def selected_lm_provider_id(request: Request | None) -> str:
    if request is None:
        return DEFAULT_LLM_PROVIDER_ID
    try:
        user_id = request_user_id(request)
    except Exception:
        return DEFAULT_LLM_PROVIDER_ID
    return str(load_user_settings(user_id).get("llm_provider_id") or DEFAULT_LLM_PROVIDER_ID)


def selected_ai_provider_access(request: Request | None, dataset_ids: List[str]) -> str:
    provider_id = selected_lm_provider_id(request)
    return constrain_ai_provider_access(
        dataset_ids,
        effective_ai_provider_access(dataset_ids),
        lm_provider_data_boundary(provider_id),
    )


def get_lm_status(request: Request) -> Dict:
    if auth_enabled():
        require_authenticated(request)
    return lm_studio_health(provider_id=selected_lm_provider_id(request))


def get_lm_providers(request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    return llm_provider_registry_status()


def create_lm_provider(payload: LmProviderCreateRequest, request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    try:
        return create_managed_lm_provider(payload.model_dump())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def update_lm_provider(provider_id: str, payload: LmProviderUpdateRequest, request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    try:
        return update_managed_lm_provider(provider_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        status_code = 404 if str(exc) == "Managed provider not found." else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def delete_lm_provider(provider_id: str, request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    try:
        delete_managed_lm_provider(provider_id)
    except ValueError as exc:
        status_code = 404 if str(exc) == "Managed provider not found." else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True, "id": provider_id}


def test_lm_provider_route(provider_id: str, request: Request) -> Dict:
    if auth_enabled():
        require_admin(request)
    try:
        return test_lm_provider(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_branding_logo() -> FileResponse:
    logo_path = branding_logo_path()
    if logo_path is None:
        raise HTTPException(status_code=404, detail="Branding logo not configured.")
    return FileResponse(logo_path)


def get_auth_status(request: Request) -> Dict:
    user = session_user(request)
    return {
        "enabled": auth_enabled(),
        "mode": auth_provider_mode(),
        "provider": oidc_provider_name() if auth_provider_mode() == "oidc" else auth_provider_mode(),
        "authenticated": bool(user) if auth_enabled() else True,
        "local_login_enabled": local_fallback_enabled(),
        "password_reset_enabled": password_reset_enabled(),
        "user": user if auth_enabled() else {
            "username": "local",
            "role": "admin",
            "display_name": "Local user",
            "email": "",
        },
    }


def login_local(request: Request, payload: LoginRequest) -> Dict:
    mode = auth_mode()
    if mode == "none":
        return {
            "enabled": False,
            "mode": "none",
            "provider": "none",
            "authenticated": True,
            "local_login_enabled": False,
            "password_reset_enabled": False,
        }
    if mode != "local" and not local_fallback_enabled():
        raise HTTPException(status_code=400, detail="Local password login is not enabled.")
    user = authenticate_local_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]
    request.session["display_name"] = user["display_name"]
    request.session["groups"] = list(user.get("groups") or [])
    request.session["login_method"] = "local"
    return {
        "enabled": True,
        "mode": "local",
        "provider": "local",
        "authenticated": True,
        "local_login_enabled": local_fallback_enabled(),
        "password_reset_enabled": password_reset_enabled(),
        "user": {
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
            "email": str(user.get("email") or ""),
            "login_method": "local",
            "groups": list(user.get("groups") or []),
        },
    }


def logout_local(request: Request) -> Dict:
    if not auth_enabled():
        return get_auth_status(request)
    session = getattr(request, "session", None)
    if session is not None:
        session.clear()
    return {
        "enabled": auth_enabled(),
        "mode": auth_provider_mode(),
        "provider": oidc_provider_name() if auth_provider_mode() == "oidc" else auth_provider_mode(),
        "authenticated": False,
        "local_login_enabled": local_fallback_enabled(),
        "password_reset_enabled": password_reset_enabled(),
    }


def login_oidc(request: Request) -> RedirectResponse:
    if auth_mode() != "oidc":
        return RedirectResponse(url="/", status_code=303)
    if not oidc_configured():
        raise HTTPException(status_code=500, detail="OIDC is not fully configured.")
    state = os.urandom(24).hex()
    nonce = os.urandom(24).hex()
    request.session["oidc_state"] = state
    request.session["oidc_nonce"] = nonce
    try:
        url = oidc_authorization_url(state, nonce)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(url=url, status_code=303)


def oidc_callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if auth_mode() != "oidc":
        raise HTTPException(status_code=404, detail="OIDC authentication is not enabled.")
    if error:
        raise HTTPException(status_code=400, detail=f"OIDC provider returned an error: {error}")
    expected_state = str(request.session.get("oidc_state") or "")
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Invalid OIDC login state.")
    if not code:
        raise HTTPException(status_code=400, detail="Missing OIDC authorization code.")
    try:
        claims = oidc_userinfo_from_code(code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = find_oidc_user(claims)
    if not user or not bool(user.get("enabled", True)):
        raise HTTPException(status_code=403, detail="OIDC user is not authorized for this COHORTome deployment.")
    request.session.pop("oidc_state", None)
    request.session.pop("oidc_nonce", None)
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]
    request.session["display_name"] = user["display_name"]
    request.session["groups"] = list(user.get("groups") or [])
    request.session["login_method"] = "oidc"
    return RedirectResponse(url="/", status_code=303)


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
    elif app_env("COHORTOME_AUTH_DEBUG_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
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


def get_about(request: Request) -> Dict:
    require_authenticated(request)
    from app.about import version_report
    return version_report()


def update_user_settings(request: UserSettingsUpdateRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    return patch_user_settings(request.model_dump(exclude_unset=True, exclude_none=True), request_user_id(raw_request))


def get_saved_cohorts(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, dataset_id or data_dir)
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(status_code=403, detail="Saved cohorts require Detailed in-app access for the current workspace.")
    return {"cohorts": list_saved_cohorts(dataset_scope_id(selected_ids), user_id=request_user_id(request))}


def create_saved_cohort(request: SavedCohortRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or request.data_dir)
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(status_code=403, detail="Saving a cohort requires Detailed in-app access for the current workspace.")
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    sample_ids = list(request.sample_ids)
    patient_ids = list(request.patient_ids)
    id_type = request.id_type
    if str(request.result_handle or "").strip():
        _, membership = _load_authorized_query_result(
            raw_request,
            request.result_handle,
            dataset_id=dataset_scope_id(selected_ids),
        )
        sample_ids = list(membership["sample_ids"])
        patient_ids = list(membership["patient_ids"])
        id_type = str(membership["id_type"] or id_type)
    try:
        from app.cohort_members import resolve_members
        roots = {identifier: resolve_dataset_dir(raw_request, identifier) for identifier in selected_ids}
        members = resolve_members(
            roots, members=[m.model_dump() for m in request.members] if request.members is not None and not request.result_handle else None,
            patient_ids=patient_ids, sample_ids=sample_ids, id_type=id_type,
        )
        item = save_cohort(
            name=request.name,
            dataset_id=dataset_scope_id(selected_ids),
            dataset_ids=selected_ids,
            data_dir=resolved_dir,
            sample_ids=sample_ids,
            patient_ids=patient_ids,
            id_type=id_type,
            source_kind=request.source_kind,
            source_prompt=request.source_prompt,
            user_id=request_user_id(raw_request),
            members=members,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail='Cohort source data are unavailable. Restore the original workspace before saving.') from None
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
    linked_job_session_ids = {
        str(item.get("analysis_session_id") or "").strip()
        for item in list_job_records(user_id)
        if str(item.get("analysis_session_id") or "").strip()
    }
    blocked_sessions = [
        item
        for item in sessions
        if str(item.get("id") or "").strip() in linked_job_session_ids
    ]
    if blocked_sessions:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(blocked_sessions)} analysis chat"
                f"{'' if len(blocked_sessions) == 1 else 's'} have linked generated runs. "
                "Delete those chats from Analysis and choose whether to keep or delete generated data."
            ),
        )
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
        if active_job_status(item.get("status")):
            skipped_active_count += 1
            continue
        if not terminal_job_status(item.get("status")):
            continue
        if job_id and delete_job(job_id, user_id):
            deleted_count += 1
    return {"deleted": True, "deleted_count": deleted_count, "skipped_active_count": skipped_active_count}


def remove_job(job_id: str, request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    if delete_job(job_id, user_id):
        return {"deleted": True, "id": Path(job_id).name}
    raise HTTPException(status_code=404, detail="Job not found.")


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
    requested_dataset_id = str(request.dataset_id or "").strip()
    if requested_dataset_id:
        selected_ids = resolve_dataset_ids(raw_request, requested_dataset_id)
    else:
        active_ids = current_dataset_ids(request_user_id(raw_request))
        if not active_ids:
            raise HTTPException(status_code=409, detail="No active workspace. Select and apply a dataset before running Query.")
        selected_ids = resolve_dataset_ids(raw_request, dataset_scope_id(active_ids))
    resolved_scope_id = dataset_scope_id(selected_ids)
    resolved_dir = resolve_dataset_dir(raw_request, resolved_scope_id)
    scoped_patient_ids = list(request.scoped_patient_ids)
    if str(request.scoped_result_handle or "").strip():
        _, membership = _load_authorized_query_result(
            raw_request,
            request.scoped_result_handle,
            dataset_id=resolved_scope_id,
        )
        scoped_patient_ids = list(membership["patient_ids"])
    try:
        with lm_provider_context(selected_lm_provider_id(raw_request)):
            payload = answer_query(
                resolved_dir,
                request.q,
                query_mode=request.query_mode,
                history=_safe_query_history(request.history),
                scoped_patient_ids=scoped_patient_ids,
                granularity_mode=request.granularity_mode,
                granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
                ai_provider_access=selected_ai_provider_access(raw_request, selected_ids),
            )
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            dataset_names_by_id = {
                str(item.get("dataset_id") or "").strip(): str(item.get("name") or item.get("dataset_id") or "Dataset").strip()
                for item in _authorized_datasets_for_request(raw_request)
            }
            dataset_names = [dataset_names_by_id.get(item, item) for item in selected_ids]
            data.update(
                {
                    "dataset_id": resolved_scope_id,
                    "dataset_ids": selected_ids,
                    "dataset_name": dataset_names[0] if len(dataset_names) == 1 else "",
                    "dataset_names": dataset_names,
                }
            )
            payload["data"] = data
            payload = _materialize_query_response(
                payload,
                raw_request,
                selected_ids=selected_ids,
                scope_id=resolved_scope_id,
                resolved_dir=resolved_dir,
            )
            return _sanitize_response_paths(payload, raw_request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        if "Private query-result state requires" in str(exc):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise


def general_llm_app(request: GeneralLlmRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        with lm_provider_context(selected_lm_provider_id(raw_request)):
            return general_llm_reply(
                request.prompt,
                history=[turn.model_dump() for turn in request.history],
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _resolve_saved_analysis_members(request, raw_request, selected_ids):
    """Reauthorize membership and bind it to the execution workspace identity."""
    from app.cohort_members import resolve_members
    roots = {identifier: resolve_dataset_dir(raw_request, identifier) for identifier in selected_ids}
    for metadata_field, ids_field in [('scope_metadata', 'selected_patient_ids'),
                                       ('compare_scope_metadata', 'compare_selected_patient_ids')]:
        if metadata_field == 'compare_scope_metadata' and not request.compare_mode:
            continue
        metadata = getattr(request, metadata_field)
        cohort_id = str(metadata.get('id') or '')
        if not cohort_id:
            continue
        if effective_query_granularity_ceiling(selected_ids) != 'detailed':
            raise HTTPException(403, 'Saved cohorts require Detailed access to every source dataset.')
        cohort = next((c for c in list_saved_cohorts(user_id=request_user_id(raw_request)) if c['id'] == cohort_id), None)
        if not cohort or not cohort.get('dataset_ids') or not set(cohort['dataset_ids']).issubset(selected_ids):
            raise HTTPException(409, 'Saved cohort is missing or belongs to a different workspace.')
        try:
            if cohort.get('members') is not None:
                members = resolve_members(roots, members=cohort['members'], id_type=cohort['id_type'])
                field = ('patient_key' if cohort['id_type'] == 'patient' else 'sample_key') if len(selected_ids) > 1 else ('patient_id' if cohort['id_type'] == 'patient' else 'sample_id')
                ids = [m[field] for m in members]
            else:
                ids = cohort['patient_ids'] if cohort['id_type'] == 'patient' else cohort['sample_ids']
        except FileNotFoundError:
            raise HTTPException(409, 'Cohort source data are unavailable.') from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        setattr(request, ids_field, ','.join(dict.fromkeys(ids)))
        setattr(request, metadata_field, cohort)


def analysis_app(request: AnalysisRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    requested_dataset_id = str(request.dataset_id or "").strip()
    if requested_dataset_id:
        if not parse_scope_dataset_ids(requested_dataset_id):
            raise HTTPException(status_code=403, detail="Dataset access denied.")
        selected_ids = resolve_dataset_ids(raw_request, requested_dataset_id)
    else:
        active_ids = current_dataset_ids(request_user_id(raw_request))
        if not active_ids:
            raise HTTPException(status_code=409, detail="No active workspace. Select and apply a dataset before running Analysis.")
        selected_ids = resolve_dataset_ids(raw_request, dataset_scope_id(active_ids))
    resolved_scope_id = dataset_scope_id(selected_ids)
    _resolve_saved_analysis_members(request, raw_request, selected_ids)
    resolved_dir = resolve_dataset_dir(raw_request, resolved_scope_id)
    selected_patient_ids = str(request.selected_patient_ids or "")
    scope_metadata_handle = (
        str(request.scope_metadata.get("query_result_handle") or "").strip()
        if isinstance(request.scope_metadata, dict)
        else ""
    )
    query_result_handle = str(request.query_result_handle or scope_metadata_handle).strip()
    if query_result_handle:
        _, membership = _load_authorized_query_result(
            raw_request,
            query_result_handle,
            dataset_id=resolved_scope_id,
        )
        scope_ids = membership["sample_ids"] if membership["id_type"] == "sample" else membership["patient_ids"]
        selected_patient_ids = ",".join(scope_ids)
    if str(request.analysis_session_id or "").strip():
        session = get_analysis_session(request.analysis_session_id, user_id=request_user_id(raw_request))
        if session:
            if session.get('dataset_id') != resolved_scope_id:
                raise HTTPException(409, "Apply this chat's original workspace or start a new Analysis chat.")
            workspace_status = _analysis_session_workspace_status(session, raw_request)
            if workspace_status["state"] in {"stale", "unavailable"}:
                raise HTTPException(status_code=409, detail=workspace_status["message"] or "This analysis session is no longer aligned with the current workspace.")
    try:
        with lm_provider_context(selected_lm_provider_id(raw_request)):
            if request.catalog_item_id == "synthetic-custom-script":
                from app.script_inputs import prepare_inputs
                from app.script_sandbox import sandbox_image
                if effective_query_granularity_ceiling(selected_ids) != "detailed":
                    raise RuntimeError("Custom scripts require Detailed workspace access.")
                prepared = prepare_inputs(resolved_dir, selected_patient_ids, request.compare_selected_patient_ids,
                                          request.compare_mode, request.custom_assay_ids, request.script_language)
                if prepared["contract_id"] != request.input_contract_id:
                    raise RuntimeError("Inputs changed or have not been prepared. Prepare the script template again.")
                if not request.custom_script.strip() or len(request.custom_script.encode()) > 131072:
                    raise RuntimeError("Provide a script of at most 128 KiB.")
                if sandbox_image() != request.sandbox_image_id:
                    raise RuntimeError("The sandbox environment changed. Prepare the template again.")
                packed = json.dumps({"script": request.custom_script, "contract_id": request.input_contract_id,
                                     "image_id": request.sandbox_image_id, "assay_ids": request.custom_assay_ids,
                                     "compare_mode": request.compare_mode, "language": request.script_language})
                import fcntl
                from app.jobs import user_jobs_root
                user_id = request_user_id(raw_request)
                with (user_jobs_root(user_id) / ".script-submit.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    if any(job.get("runner_type") == "container" and job.get("status") in {"queued", "running"}
                           for job in list_job_records(user_id)):
                        raise RuntimeError("You already have a custom script queued or running. Wait for it to finish before submitting another.")
                    return analysis_llm_reply(packed, resolved_dir, catalog_item_id=request.catalog_item_id,
                                              dataset_id=resolved_scope_id, analysis_session_id=request.analysis_session_id,
                                              user_id=user_id, selected_patient_ids=selected_patient_ids,
                                              compare_selected_patient_ids=request.compare_selected_patient_ids,
                                              compare_mode=request.compare_mode, deterministic_only=True)
            return analysis_llm_reply(
                request.prompt,
                resolved_dir,
                catalog_item_id=request.catalog_item_id,
                measurement=request.measurement,
                dataset_id=resolved_scope_id,
                assay_id=request.assay_id,
                analysis_session_id=request.analysis_session_id,
                user_id=request_user_id(raw_request),
                selected_patient_ids=selected_patient_ids,
                compare_mode=request.compare_mode,
                compare_selected_patient_ids=request.compare_selected_patient_ids,
                llm_only=request.llm_only,
                deterministic_only=request.deterministic_only,
                history=[turn.model_dump() for turn in request.history],
                granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
                ai_provider_access=selected_ai_provider_access(raw_request, selected_ids),
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
    items = []
    for item in list_job_records(user_id):
        if not (
            str(item.get("execution_backend") or "").strip().lower() == "job"
            or str(item.get("rq_job_id") or "").strip()
            or active_job_status(item.get("status"))
        ):
            continue
        try:
            _require_job_dataset_access(item, user_id)
        except HTTPException:
            continue
        items.append(public_job_payload(item, user_id=user_id))
    return {"jobs": items}


def get_jobs_status(request: Request) -> Dict:
    require_authenticated(request)
    return analysis_worker_status()


def get_run_history(request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    settings = load_user_settings(user_id)
    retention_days = int(settings.get("run_history_retention_days") or 0)
    expired_deleted_count = delete_expired_terminal_jobs(user_id, retention_days)
    items = []
    for item in list_job_records(user_id):
        try:
            _require_job_dataset_access(item, user_id)
        except HTTPException:
            continue
        items.append(public_job_payload(item, user_id=user_id))
    return {
        "runs": items,
        "expired_deleted_count": expired_deleted_count,
        "retention_days": retention_days,
    }


def _require_job_dataset_access(record: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    stored_dataset_id = str(record.get("dataset_id") or "").strip()
    if not stored_dataset_id:
        raise HTTPException(status_code=403, detail="Job dataset scope is unavailable.")
    try:
        scope = _authorize_analysis_scope(user_id, stored_dataset_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=403, detail="Job dataset access denied.") from exc
    if any(
        normalize_query_granularity_ceiling(dataset.get("query_granularity_ceiling")) != "detailed"
        for dataset in (scope.get("datasets") or [])
    ):
        raise HTTPException(
            status_code=403,
            detail="Job results require Detailed in-app access for the stored dataset scope.",
        )
    return scope


def remove_run_history_item(job_id: str, request: Request) -> Dict:
    return remove_job(job_id, request)


def delete_run_history(request: Request) -> Dict:
    return delete_user_completed_jobs(request)


def get_job(job_id: str, request: Request) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    _require_job_dataset_access(record, user_id)
    return public_job_payload(record, include_result=True, user_id=user_id)


def get_job_artifact(job_id: str, filename: str, request: Request) -> FileResponse:
    require_authenticated(request)
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    _require_job_dataset_access(record, user_id)
    file_path = resolve_job_artifact_path(job_id, user_id, filename)
    if record.get("runner_type") == "container":
        return FileResponse(file_path, media_type="image/png" if file_path.suffix == ".png" else "text/plain",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "sandbox; default-src 'none'"})
    return FileResponse(file_path)


def get_analysis_code(digest: str, request: Request) -> FileResponse:
    require_authenticated(request)
    from app.analysis_code import code_path
    return FileResponse(code_path(digest), media_type="text/plain", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


def prepare_analysis_script(request: AnalysisRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id)
    _resolve_saved_analysis_members(request, raw_request, selected_ids)
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(status_code=403, detail="Script preparation requires Detailed workspace access.")
    resolved_dir = resolve_dataset_dir(raw_request, dataset_scope_id(selected_ids))
    scope = request.selected_patient_ids
    if request.query_result_handle:
        _, membership = _load_authorized_query_result(raw_request, request.query_result_handle,
                                                     dataset_id=dataset_scope_id(selected_ids))
        scope = ",".join(membership["sample_ids"] if membership["id_type"] == "sample" else membership["patient_ids"])
    from app.script_inputs import prepare_inputs
    from app.script_sandbox import sandbox_status
    try:
        prepared = prepare_inputs(resolved_dir, scope, request.compare_selected_patient_ids,
                                  request.compare_mode, request.custom_assay_ids, request.script_language)
        prepared.pop("files")  # The AI template contains a schema, never data rows.
        prepared["sandbox"] = sandbox_status()
        return prepared
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def get_analysis_measurements(request: AnalysisRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id)
    _resolve_saved_analysis_members(request, raw_request, selected_ids)
    if effective_query_granularity_ceiling(selected_ids) != "detailed":
        raise HTTPException(status_code=403, detail="Measurement setup requires Detailed in-app access.")
    resolved_dir = resolve_dataset_dir(raw_request, dataset_scope_id(selected_ids))
    scope = request.selected_patient_ids
    if request.query_result_handle:
        _, membership = _load_authorized_query_result(raw_request, request.query_result_handle,
                                                     dataset_id=dataset_scope_id(selected_ids))
        scope = ",".join(membership["sample_ids"] if membership["id_type"] == "sample" else membership["patient_ids"])
    from app.analysis_measurements import measurement_options
    try:
        return {"measurements": measurement_options(resolved_dir, scope, request.compare_selected_patient_ids, request.compare_mode)}
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_analysis_catalog(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    selected_ids = resolve_dataset_ids(request, dataset_id or "")
    resolved_dir = resolve_dataset_dir(request, dataset_id or data_dir)
    try:
        return analysis_catalog_payload(
            resolved_dir,
            granularity_ceiling=effective_query_granularity_ceiling(selected_ids),
            ai_provider_access=selected_ai_provider_access(request, selected_ids),
            workspace_dataset_count=len(selected_ids),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_assay_datasets(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        selected_ids = _route_dataset_ids(request, dataset_id, data_dir)
        items = assay_dataset_inventory(_resolve_route_dataset_dir(request, dataset_id, data_dir))
        if effective_query_granularity_ceiling(selected_ids) != "detailed":
            items = _summary_safe_assay_inventory(items)
        return {"datasets": items}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_assay_readiness(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    _require_detailed_assay_access(request, dataset_id, data_dir)
    try:
        return multimodal_readiness(_resolve_route_dataset_dir(request, dataset_id, data_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_assay_feature_matrix(
    request: Request,
    dataset_id: str = "",
    data_dir: str = DEFAULT_DATA_DIR,
    max_features_per_dataset: int = 3,
    max_rows: int = 25,
) -> Dict:
    require_authenticated(request)
    _require_detailed_assay_access(request, dataset_id, data_dir)
    try:
        return multimodal_feature_matrix(
            _resolve_route_dataset_dir(request, dataset_id, data_dir),
            max_features_per_dataset=max_features_per_dataset,
            max_rows=max_rows,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_assay_features(assay_id: str, request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR, q: str = "", limit: int = 50) -> Dict:
    require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        genes = assay_feature_inventory(resolved_dir, assay_id, search=q, limit=limit)
        return {
            "assay_id": assay_id,
            "genes": genes,
            "annotations": assay_feature_annotations(genes, resolved_dir, assay_id),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unable to browse features. Check the assay declaration and use a prepared store or a matrix panel of at most 64 MiB.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_assay_expression(request: AssayExpressionRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    _require_detailed_assay_access(raw_request, request.dataset_id, request.data_dir)
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    try:
        return assay_expression_summary(
            resolved_dir,
            request.assay_id,
            request.gene_id,
            selected_patient_ids=request.selected_patient_ids,
            compare_selected_patient_ids=request.compare_selected_patient_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_dicom_studies(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    _require_detailed_assay_access(request, dataset_id, data_dir)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        status = dicom_status(resolved_dir)
        studies = dicom_studies(resolved_dir)
        from app.local_viewer import ASSETS, SYNTHETIC_ROOT
        from urllib.parse import quote
        if (ASSETS / 'index.html').is_file():
            ids = _route_dataset_ids(request, dataset_id, data_dir)
            for study in studies:
                source_id = study.get('source_dataset_id') or (ids[0] if len(ids) == 1 else '')
                if source_id and source_id in ids:
                    root = Path(_resolve_route_dataset_dir(request, source_id, '')).resolve()
                    if root == SYNTHETIC_ROOT.resolve():
                        study['local_viewer_url'] = '/local-viewer/open/' + quote(source_id, safe='') + '/' + quote(study['study_instance_uid'], safe='')
        return {
            "enabled": bool(status.get("enabled")),
            "ohif_public_url": str(status.get("ohif_public_url") or ""),
            "dicomweb_public_url": str(status.get("dicomweb_public_url") or ""),
            "studies": studies,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_dicom_status(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        return dicom_status(_resolve_route_dataset_dir(request, dataset_id, data_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _query_session_access(item: Dict, request: Request) -> None:
    if item.get("dataset_id"):
        selected = resolve_dataset_ids(request, item["dataset_id"])
        if effective_query_granularity_ceiling(selected) != item.get("granularity_ceiling"):
            raise HTTPException(status_code=403, detail="Response-detail policy changed. Start a new Query chat.")


def get_query_sessions(request: Request) -> Dict:
    require_authenticated(request)
    sessions = []
    for item in query_sessions.list_sessions(request_user_id(request)):
        try:
            _query_session_access(item, request)
        except HTTPException:
            # Do not disclose even titles after access to a source is revoked.
            continue
        sessions.append({key: item.get(key) for key in ("id", "title", "updated_at", "dataset_id")})
    return {"sessions": sessions}


def get_query_session(session_id: str, request: Request) -> Dict:
    require_authenticated(request)
    item = query_sessions.get_session(request_user_id(request), session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Query chat not found.")
    _query_session_access(item, request)
    status = _analysis_session_workspace_status(item, request) if item.get("dataset_id") else {"state": "current"}
    return {**item, "workspace_status": status}


def save_query_session(payload: QuerySessionRequest, request: Request) -> Dict:
    require_authenticated(request)
    item = payload.model_dump()
    if len(json.dumps(item).encode("utf-8")) > 2_000_000:
        raise HTTPException(status_code=413, detail="Chat is too large to save. Start a new chat.")
    user_id = request_user_id(request)
    existing = query_sessions.get_session(user_id, payload.id)
    if existing:
        _query_session_access(existing, request)
        if payload.dataset_id != existing.get("dataset_id"):
            raise HTTPException(status_code=409, detail="A chat cannot change its original workspace. Start a new chat.")
        item["workspace_fingerprint"] = existing.get("workspace_fingerprint", {})
        item["granularity_ceiling"] = existing.get("granularity_ceiling", "")
    elif payload.dataset_id:
        selected = resolve_dataset_ids(request, payload.dataset_id)
        directory = resolve_dataset_dir(request, payload.dataset_id)
        item["dataset_id"] = dataset_scope_id(selected)
        item["workspace_fingerprint"] = workspace_fingerprint_for_data_dir(directory, dataset_id=item["dataset_id"], dataset_ids=selected)
        item["granularity_ceiling"] = effective_query_granularity_ceiling(selected)
    if not payload.dataset_id and (any(turn.get("contextMode") != "general" for turn in payload.turns) or any(turn.get("context_mode") != "general" for turn in payload.history)):
        raise HTTPException(status_code=400, detail="Workspace messages require a dataset.")
    try:
        return query_sessions.save_session(user_id, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def remove_query_session(session_id: str, request: Request) -> Dict:
    require_authenticated(request)
    if not query_sessions.delete_session(request_user_id(request), session_id):
        raise HTTPException(status_code=404, detail="Query chat not found.")
    return {"deleted": True, "id": session_id}


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
        if existing and existing.get('dataset_id') != resolved_scope_id:
            raise HTTPException(409, "An Analysis chat keeps its original workspace. Start a new chat for a different workspace.")
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
    keep_generated_jobs: bool = Query(default=False),
) -> Dict:
    require_authenticated(request)
    delete_generated_data = delete_generated_data is True
    keep_generated_jobs = keep_generated_jobs is True
    if delete_generated_data and keep_generated_jobs:
        raise HTTPException(status_code=400, detail="Choose either delete_generated_data or keep_generated_jobs, not both.")
    user_id = request_user_id(request)
    session_exists = any(
        str(item.get("id") or "").strip() == session_id
        for item in list_analysis_sessions(user_id=user_id)
    )
    if not session_exists:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    related_jobs = list_jobs_for_analysis_session(session_id, user_id)
    related_job_count = len(related_jobs)
    if related_job_count and not delete_generated_data and not keep_generated_jobs:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This analysis chat has {related_job_count} linked generated run"
                f"{'' if related_job_count == 1 else 's'}. "
                "Choose whether to keep generated runs or delete generated data."
            ),
        )
    deleted_job_count = 0
    skipped_active_count = 0
    if delete_generated_data:
        active = [
            item
            for item in related_jobs
            if active_job_status(item.get("status"))
        ]
        if active:
            raise HTTPException(
                status_code=409,
                detail="This analysis session has active background jobs. Wait for them to finish before deleting generated data.",
            )
        for item in related_jobs:
            if delete_job(str(item.get("job_id") or "").strip(), user_id):
                deleted_job_count += 1
    else:
        skipped_active_count = sum(1 for item in related_jobs if active_job_status(item.get("status")))
    deleted = delete_analysis_session(session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return {
        "deleted": True,
        "id": session_id,
        "deleted_generated_data": bool(delete_generated_data),
        "related_job_count": related_job_count,
        "deleted_job_count": deleted_job_count,
        "kept_job_count": related_job_count - deleted_job_count,
        "skipped_active_count": skipped_active_count,
    }


def run_inline_pheno_ranker_job(payload: PhenoRankerRequest, user_id: str) -> Dict:
    record = create_job_record(
        job_type="pheno",
        user_id=user_id,
        data={
            "feature": "pheno",
            "name": "Pheno-Ranker run",
            "prompt": str(payload.prompt or "").strip(),
            "dataset_id": str(payload.dataset_id or "").strip(),
            "data_dir": str(payload.data_dir or "").strip(),
            "action": str(payload.action or "").strip(),
            "mode": str(payload.mode or "").strip(),
            "patient_id": str(payload.patient_id or "").strip(),
            "selected_patient_ids": str(payload.selected_patient_ids or "").strip(),
            "selected_saved_cohort_ids": list(payload.selected_saved_cohort_ids or []),
            "disease_filter": str(payload.disease_filter or "").strip(),
            "include_terms": list(payload.include_terms or []),
            "exclude_terms": list(payload.exclude_terms or []),
            "similarity_metric_cohort": str(payload.similarity_metric_cohort or "").strip(),
            "sort_by": str(payload.sort_by or "").strip(),
            "max_out": int(payload.max_out or 0),
            "align": bool(payload.align),
            "render_heatmap": bool(payload.render_heatmap),
            "render_mds": bool(payload.render_mds),
            "render_umap": bool(payload.render_umap),
            "render_graph": bool(payload.render_graph),
            "graph_min_weight": payload.graph_min_weight,
            "graph_max_weight": payload.graph_max_weight,
            "granularity_ceiling": str(payload.granularity_ceiling or "").strip(),
            "ai_provider_access": str(payload.ai_provider_access or "").strip(),
            "execution_backend": "inline",
        },
    )
    job_id = str(record.get("job_id") or "").strip()
    update_job_record(job_id, user_id, status="running", error="")
    try:
        request_payload = SimpleNamespace(**payload.model_dump(), job_dir_override=str(job_dir(job_id, user_id, create=True)))
        result = run_pheno_ranker(request_payload)
        result.setdefault("data", {})
        result["data"]["job_id"] = job_id
        result["data"]["job_status"] = "completed"
        result["data"]["execution_backend"] = "inline"
        result["job_id"] = job_id
        save_job_result(job_id, user_id, result)
        update_job_record(
            job_id,
            user_id,
            status="completed",
            result_available=True,
            reply_preview=str(result.get("reply") or f"Completed {str(payload.mode or 'pheno')} Pheno-Ranker run.")[:280],
            error="",
        )
        return result
    except HTTPException as exc:
        update_job_record(job_id, user_id, status="failed", error=str(exc.detail))
        raise
    except Exception as exc:
        update_job_record(job_id, user_id, status="failed", error=str(exc))
        raise


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
    payload = request.model_copy(
        update={
            "data_dir": resolved_dir,
            "dataset_id": resolved_scope_id,
            "granularity_ceiling": granularity_ceiling,
            "ai_provider_access": selected_ai_provider_access(raw_request, selected_ids),
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
    try:
        ensure_query_store(resolved_dir)
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
                    "render_umap": payload.render_umap,
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
    return run_inline_pheno_ranker_job(payload, user_id)


def plan_pheno_ranker_route(request: PhenoRankerPlanRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    selected_ids = resolve_dataset_ids(raw_request, request.dataset_id or "")
    resolved_dir = resolve_dataset_dir(raw_request, request.dataset_id or request.data_dir)
    try:
        ensure_query_store(resolved_dir)
        with lm_provider_context(selected_lm_provider_id(raw_request)):
            return plan_pheno_ranker(
                request.text,
                resolved_dir,
                selected_patient_ids=request.selected_patient_ids,
                ai_provider_access=selected_ai_provider_access(raw_request, selected_ids),
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
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    _require_job_dataset_access(record, user_id)
    file_path = pheno_ranker_result_file_path(job_id, filename, user_id=user_id)
    return FileResponse(file_path)


def get_pheno_ranker_alignment(job_id: str, reference_id: str, request: Request, target_id: str = "") -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    _require_job_dataset_access(record, user_id)
    return pheno_ranker_alignment_details(job_id, reference_id, target_id=target_id, user_id=user_id)


def explain_pheno_ranker_results(job_id: str, request: Request, top_n: int = 3) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    scope = _require_job_dataset_access(record, user_id)
    selected_ids = list(scope.get("dataset_ids") or [])
    return pheno_ranker_explain(
        job_id,
        top_n=top_n,
        ai_provider_access=selected_ai_provider_access(request, selected_ids),
        user_id=user_id,
    )


def explain_pheno_ranker_results_llm(job_id: str, request: Request, top_n: int = 3) -> Dict:
    require_authenticated(request)
    user_id = request_user_id(request)
    record = load_job_record(job_id, user_id)
    scope = _require_job_dataset_access(record, user_id)
    selected_ids = list(scope.get("dataset_ids") or [])
    with lm_provider_context(selected_lm_provider_id(request)):
        return pheno_ranker_explain_llm(
            job_id,
            top_n=top_n,
            ai_provider_access=selected_ai_provider_access(request, selected_ids),
            user_id=user_id,
        )


def get_dashboard(request: Request, dataset_id: str = "", data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        resolved_dir = _resolve_route_dataset_dir(request, dataset_id, data_dir)
        ensure_query_store(resolved_dir)
        payload = dashboard_summary(resolved_dir)
        representation = clinical_representation(resolved_dir)
        payload["clinical_representation"] = representation
        payload.setdefault("totals", {})["clinical_records"] = int(payload.get("totals", {}).get("visits") or 0)
        return _sanitize_response_paths(payload, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryStoreNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def register_routes(app: FastAPI, template_engine: Jinja2Templates) -> None:
    init_routes_templates(template_engine)

    app.add_api_route("/", index, methods=["GET"], response_class=HTMLResponse, tags=["ui"], summary="Render the main application shell", description="Serves the COHORTome HTML shell with the current branding and authenticated user context.")
    app.add_api_route("/patients", get_patients, methods=["GET"], tags=["patients"], summary="List patient summaries", description="Returns patient-level summaries for the active dataset or workspace scope.", response_model=List[PatientSummaryResponse])
    app.add_api_route("/patients/{patient_id}", get_patient, methods=["GET"], tags=["patients"], summary="Get a patient context", description="Returns the normalized clinical context for a single patient identifier.")
    app.add_api_route("/patients/{patient_id}/workspace", get_patient_workspace, methods=["GET"], tags=["patients"], summary="Get a patient workspace view", description="Returns the timeline-oriented patient workspace payload used by the patient detail view.")
    app.add_api_route("/cohorts/medications", get_medication_counts, methods=["GET"], tags=["patients"], summary="Count medications in the workspace", description="Returns medication counts derived from the active workspace.")
    app.add_api_route("/cohorts/diseases", get_disease_counts, methods=["GET"], tags=["patients"], summary="Count diseases in the workspace", description="Returns disease counts derived from the active workspace.")
    app.add_api_route("/cohorts/medications/search", search_medication_cohort, methods=["GET"], tags=["patients"], summary="Build a medication workspace", description="Returns the deterministic medication-matched workspace subset for a single medication label.")
    app.add_api_route("/query", query_app, methods=["GET"], tags=["query"], summary="Run a simple GET workspace query", description="Executes a lightweight workspace query using query-string parameters. Prefer POST /query for full prompt history and planner mode control.")
    app.add_api_route("/query-results/{handle}", get_query_result_page, methods=["GET"], tags=["query"], summary="Page through a Query result", description="Returns one bounded page from a short-lived, user-scoped Query result after rechecking workspace authorization and Detailed access.")
    app.add_api_route("/query-results/{handle}/export", export_query_result, methods=["GET"], tags=["query"], summary="Export all rows of an authorized Query result")
    app.add_api_route("/saved-cohorts/{cohort_id}/export", export_saved_cohort, methods=["GET"], tags=["cohorts"], summary="Export saved cohort membership and metadata")
    app.add_api_route("/lm-status", get_lm_status, methods=["GET"], tags=["auth"], summary="Inspect configured LM status", description="Returns whether LM Studio is enabled plus the current model and base URL.", response_model=LmStatusResponse)
    app.add_api_route("/lm-providers", get_lm_providers, methods=["GET"], tags=["auth"], summary="Inspect approved LLM providers", description="Admin-only registry and health view for approved OpenAI-compatible LLM endpoints.", response_model=LmProvidersResponse)
    app.add_api_route("/lm-providers", create_lm_provider, methods=["POST"], tags=["auth"], summary="Create a managed LLM provider", description="Persists an OpenAI-compatible provider in protected runtime state. The API key is write-only.", response_model=LmProviderResponse)
    app.add_api_route("/lm-providers/{provider_id}", update_lm_provider, methods=["PATCH"], tags=["auth"], summary="Update a managed LLM provider", description="Updates a runtime-managed provider. Environment-defined providers are read-only.", response_model=LmProviderResponse)
    app.add_api_route("/lm-providers/{provider_id}", delete_lm_provider, methods=["DELETE"], tags=["auth"], summary="Delete a managed LLM provider", description="Deletes a runtime-managed provider. Environment-defined providers cannot be deleted.", response_model=DeleteResponse)
    app.add_api_route("/lm-providers/{provider_id}/test", test_lm_provider_route, methods=["POST"], tags=["auth"], summary="Test an LLM provider", description="Runs an admin-only models-endpoint health check without exposing the configured API key.", response_model=LmProviderResponse)
    app.add_api_route("/auth/me", get_auth_status, methods=["GET"], tags=["auth"], summary="Get current authentication state", description="Returns the current local-auth session state and visible user identity.", response_model=AuthStatusResponse)
    app.add_api_route("/auth/login", login_oidc, methods=["GET"], tags=["auth"], summary="Start external OIDC login", description="Redirects to the configured OIDC provider when COHORTOME_AUTH_MODE=oidc.")
    app.add_api_route("/auth/login", login_local, methods=["POST"], tags=["auth"], summary="Log in with local credentials", description="Authenticates a local user and creates a session-backed login.", response_model=AuthStatusResponse)
    app.add_api_route("/auth/oidc/callback", oidc_callback, methods=["GET"], tags=["auth"], summary="Complete external OIDC login", description="Handles the OIDC authorization-code callback and maps the external identity to a local COHORTome user.")
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
    app.add_api_route("/about", get_about, methods=["GET"], tags=["auth"], summary="Detected software versions")
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
    app.add_api_route("/llm/general", general_llm_app, methods=["POST"], tags=["llm"], summary="Ask a general-knowledge question", description="Sends the prompt and recent General-question turns to the selected model provider without workspace or dataset context.")
    app.add_api_route("/analysis/catalog", get_analysis_catalog, methods=["GET"], tags=["analysis"], summary="List curated analysis catalog entries", description="Returns curated analysis definitions plus computed availability for the current workspace.")
    app.add_api_route("/analysis", analysis_app, methods=["POST"], tags=["analysis"], summary="Run a workspace analysis", description="Executes clinical or assay analysis over the active workspace or selected saved cohorts.")
    app.add_api_route("/analysis/measurements", get_analysis_measurements, methods=["POST"], tags=["analysis"])
    app.add_api_route("/analysis/script-template", prepare_analysis_script, methods=["POST"], tags=["analysis"])
    app.add_api_route("/analysis/code/{digest}", get_analysis_code, methods=["GET"], tags=["analysis"])
    app.add_api_route("/jobs", get_jobs, methods=["GET"], tags=["jobs"], summary="List recent background jobs", description="Returns recent background jobs visible to the current user across supported product surfaces.")
    app.add_api_route("/jobs/status", get_jobs_status, methods=["GET"], tags=["jobs"], summary="Inspect background-worker availability", description="Reports whether Redis and workers for the analysis queue are online, idle, or working without exposing worker host details.")
    app.add_api_route("/jobs/{job_id}", get_job, methods=["GET"], tags=["jobs"], summary="Get one background job", description="Returns detailed status plus the completed payload for one background job visible to the current user.")
    app.add_api_route("/jobs/{job_id}", remove_job, methods=["DELETE"], tags=["jobs"], summary="Delete one terminal job", description="Deletes one completed, failed, or cancelled job and its generated artifacts for the current user.", response_model=DeleteResponse)
    app.add_api_route("/jobs/{job_id}/artifacts/{filename:path}", get_job_artifact, methods=["GET"], tags=["jobs"], summary="Download one background job artifact", description="Returns one persisted artifact for a background job visible to the current user.")
    app.add_api_route("/run-history", get_run_history, methods=["GET"], tags=["jobs"], summary="List generated run history", description="Returns all generated analysis and Pheno-Ranker runs visible to the current user.")
    app.add_api_route("/run-history", delete_run_history, methods=["DELETE"], tags=["jobs"], summary="Delete terminal generated runs", description="Deletes completed, failed, or cancelled generated runs and artifacts owned by the current user. Active runs are skipped.", response_model=DeleteResponse)
    app.add_api_route("/run-history/{job_id}", remove_run_history_item, methods=["DELETE"], tags=["jobs"], summary="Delete one generated run", description="Deletes one completed, failed, or cancelled generated run and its artifacts for the current user.", response_model=DeleteResponse)
    app.add_api_route("/assays", get_assay_datasets, methods=["GET"], tags=["assays"], summary="List assays in scope", description="Returns assay datasets visible in the current workspace.", response_model=AssayDatasetsResponse)
    app.add_api_route("/assays/readiness", get_assay_readiness, methods=["GET"], tags=["assays"], summary="Get multimodal analysis readiness", description="Returns workspace-level multimodal coverage, overlap, linkage issues, and deterministic next-step suggestions.", response_model=AssayReadinessResponse)
    app.add_api_route("/assays/matrix", get_assay_feature_matrix, methods=["GET"], tags=["assays"], summary="Build multimodal feature matrix preview", description="Returns a bounded sample-level multimodal matrix preview with clinical covariates, selected assay features, DICOM viewer metadata, missingness, and provenance.", response_model=AssayFeatureMatrixResponse)
    app.add_api_route("/assays/features", get_assay_features, methods=["GET"], tags=["assays"], summary="Search features in an assay", description="Returns gene identifiers for a selected assay with optional search and limit filtering.")
    app.add_api_route("/assays/expression", get_assay_expression, methods=["POST"], tags=["assays"], summary="Summarize assay expression", description="Returns scoped gene expression summaries for one assay, optionally comparing cohort A and cohort B.")
    app.add_api_route("/dicom/studies", get_dicom_studies, methods=["GET"], tags=["dicom"], summary="List DICOM studies in scope", description="Returns DICOM studies configured for the current workspace with OHIF launch URLs.", response_model=DicomStudiesResponse)
    app.add_api_route("/dicom/status", get_dicom_status, methods=["GET"], tags=["dicom"], summary="Get DICOM integration status", description="Returns DICOM/OHIF/Orthanc configuration status for the current workspace.", response_model=DicomStatusResponse)
    app.include_router(chat_folders_router)
    app.add_api_route("/query-sessions", get_query_sessions, methods=["GET"], tags=["query"])
    app.add_api_route("/query-sessions", save_query_session, methods=["POST"], tags=["query"])
    app.add_api_route("/query-sessions/{session_id}", get_query_session, methods=["GET"], tags=["query"])
    app.add_api_route("/query-sessions/{session_id}", remove_query_session, methods=["DELETE"], tags=["query"])
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
    app.add_api_route("/dashboard", get_dashboard, methods=["GET"], tags=["patients"], summary="Get the dashboard summary", description="Returns the dashboard summary payload used by the clinical and assay overview panels.")
