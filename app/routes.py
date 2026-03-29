from __future__ import annotations

from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import auth_enabled, authenticate_local_user, local_auth_diagnostics, local_users, require_admin, require_authenticated, session_user
from app.analysis import analysis_llm_reply
from app.analysis_sessions import (
    delete_analysis_session,
    list_analysis_sessions,
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
from app.lm import lm_studio_base_url, lm_studio_enabled, resolve_lm_studio_model
from app.pheno import (
    pheno_ranker_alignment_details,
    pheno_ranker_explain,
    pheno_ranker_explain_llm,
    pheno_ranker_patient_ids_payload,
    pheno_ranker_result_file_path,
    plan_pheno_ranker,
    run_pheno_ranker,
)
from app.query_store import molecular_dataset_inventory, molecular_expression_summary, molecular_gene_inventory
from app.schemas import (
    AnalysisRequest,
    AnalysisSessionRenameRequest,
    AnalysisSessionRequest,
    MolecularExpressionRequest,
    PhenoRankerPlanRequest,
    PhenoRankerRequest,
    QueryRequest,
    SavedCohortRequest,
    LoginRequest,
)
from app.query import answer_query
from app.user_state import request_user_id


templates: Jinja2Templates | None = None


def init_routes_templates(value: Jinja2Templates) -> None:
    global templates
    templates = value


def index(request: Request) -> HTMLResponse:
    if templates is None:
        raise RuntimeError("Templates have not been initialized.")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_data_dir": DEFAULT_DATA_DIR,
            "branding": branding_settings(),
            "auth_enabled": auth_enabled(),
        },
    )


def get_patients(request: Request = None, data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    if request is not None:
        require_authenticated(request)
    try:
        patients = list_patient_summaries(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [patient.model_dump() for patient in patients]


def get_patient(patient_id: str, request: Request = None, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        patient = get_patient_context(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return patient.model_dump()


def get_patient_navigator(patient_id: str, request: Request = None, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        navigator = build_patient_navigator(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if navigator is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return navigator.model_dump()


def get_medication_counts(request: Request = None, data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    if request is not None:
        require_authenticated(request)
    try:
        return medication_counts(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def search_medication_cohort(medication: str, request: Request = None, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    if request is not None:
        require_authenticated(request)
    try:
        return medication_cohort(data_dir, medication)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def query_app(q: str, request: Request, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        return answer_query(data_dir, q)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_lm_status() -> Dict:
    enabled = lm_studio_enabled()
    model = resolve_lm_studio_model() if enabled else None
    base_url = lm_studio_base_url()
    return {
        "enabled": enabled,
        "base_url": base_url,
        "model": model,
    }


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
        "user": user if auth_enabled() else {
            "username": "local",
            "role": "admin",
            "display_name": "Local user",
        },
    }


def login_local(request: Request, payload: LoginRequest) -> Dict:
    if not auth_enabled():
        return {"enabled": False, "authenticated": True}
    user = authenticate_local_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]
    request.session["display_name"] = user["display_name"]
    return {
        "enabled": True,
        "authenticated": True,
        "user": {
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
        },
    }


def logout_local(request: Request) -> Dict:
    session = getattr(request, "session", None)
    if session is not None:
        session.clear()
    return {"enabled": auth_enabled(), "authenticated": False}


def get_auth_diagnostics() -> Dict:
    return local_auth_diagnostics()


def get_auth_users(request: Request) -> Dict:
    require_admin(request)
    return {
        "mode": "local" if auth_enabled() else "none",
        "users": [
            {
                "username": str(item.get("username") or ""),
                "role": str(item.get("role") or "user"),
                "display_name": str(item.get("display_name") or item.get("username") or ""),
            }
            for item in local_users()
        ],
    }


def get_saved_cohorts(request: Request, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    return {"cohorts": list_saved_cohorts(data_dir, user_id=request_user_id(request))}


def create_saved_cohort(request: SavedCohortRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        item = save_cohort(
            name=request.name,
            data_dir=request.data_dir,
            ids=request.patient_ids,
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
    deleted = delete_saved_cohort(cohort_id, user_id=request_user_id(request))
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved cohort not found.")
    return {"deleted": True, "id": cohort_id}


def query_app_post(request: QueryRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        return answer_query(
            request.data_dir,
            request.q,
            query_mode=request.query_mode,
            history=[turn.model_dump() for turn in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def analysis_app(request: AnalysisRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        return analysis_llm_reply(
            request.prompt,
            request.data_dir,
            selected_patient_ids=request.selected_patient_ids,
            compare_mode=request.compare_mode,
            compare_selected_patient_ids=request.compare_selected_patient_ids,
            llm_only=request.llm_only,
            history=[turn.model_dump() for turn in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_molecular_datasets(request: Request, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        return {"datasets": molecular_dataset_inventory(data_dir)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_molecular_genes(dataset_name: str, request: Request, data_dir: str = DEFAULT_DATA_DIR, q: str = "", limit: int = 50) -> Dict:
    require_authenticated(request)
    try:
        return {
            "dataset_name": dataset_name,
            "genes": molecular_gene_inventory(data_dir, dataset_name, search=q, limit=limit),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_molecular_expression(request: MolecularExpressionRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        return molecular_expression_summary(
            request.data_dir,
            request.dataset_name,
            request.gene_id,
            selected_patient_ids=request.selected_patient_ids,
            compare_selected_patient_ids=request.compare_selected_patient_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def get_analysis_sessions(request: Request) -> Dict:
    require_authenticated(request)
    return {"sessions": list_analysis_sessions(user_id=request_user_id(request))}


def create_or_update_analysis_session(request: AnalysisSessionRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    try:
        return save_analysis_session(request.model_dump(), user_id=request_user_id(raw_request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def update_analysis_session_title(session_id: str, request: AnalysisSessionRenameRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    item = rename_analysis_session(session_id, request.title, user_id=request_user_id(raw_request))
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return item


def remove_analysis_session(session_id: str, request: Request) -> Dict:
    require_authenticated(request)
    deleted = delete_analysis_session(session_id, user_id=request_user_id(request))
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return {"deleted": True, "id": session_id}


def run_pheno_ranker_route(request: PhenoRankerRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    return run_pheno_ranker(request)


def plan_pheno_ranker_route(request: PhenoRankerPlanRequest, raw_request: Request) -> Dict:
    require_authenticated(raw_request)
    return plan_pheno_ranker(request.text, request.data_dir, selected_patient_ids=request.selected_patient_ids)


def get_pheno_ranker_patient_ids(request: Request, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    return pheno_ranker_patient_ids_payload(data_dir)


def get_pheno_ranker_result(job_id: str, filename: str, request: Request) -> FileResponse:
    require_authenticated(request)
    file_path = pheno_ranker_result_file_path(job_id, filename)
    return FileResponse(file_path)


def get_pheno_ranker_alignment(job_id: str, reference_id: str, request: Request, target_id: str = "") -> Dict:
    require_authenticated(request)
    return pheno_ranker_alignment_details(job_id, reference_id, target_id=target_id)


def explain_pheno_ranker_results(job_id: str, request: Request, top_n: int = 3) -> Dict:
    require_authenticated(request)
    return pheno_ranker_explain(job_id, top_n=top_n)


def explain_pheno_ranker_results_llm(job_id: str, request: Request, top_n: int = 3) -> Dict:
    require_authenticated(request)
    return pheno_ranker_explain_llm(job_id, top_n=top_n)


def get_dashboard(request: Request, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    require_authenticated(request)
    try:
        return dashboard_summary(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def register_routes(app: FastAPI, template_engine: Jinja2Templates) -> None:
    init_routes_templates(template_engine)

    app.add_api_route("/", index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/patients", get_patients, methods=["GET"])
    app.add_api_route("/patients/{patient_id}", get_patient, methods=["GET"])
    app.add_api_route("/patients/{patient_id}/navigator", get_patient_navigator, methods=["GET"])
    app.add_api_route("/cohorts/medications", get_medication_counts, methods=["GET"])
    app.add_api_route("/cohorts/medications/search", search_medication_cohort, methods=["GET"])
    app.add_api_route("/query", query_app, methods=["GET"])
    app.add_api_route("/lm-status", get_lm_status, methods=["GET"])
    app.add_api_route("/auth/me", get_auth_status, methods=["GET"])
    app.add_api_route("/auth/login", login_local, methods=["POST"])
    app.add_api_route("/auth/logout", logout_local, methods=["POST"])
    app.add_api_route("/auth/debug", get_auth_diagnostics, methods=["GET"])
    app.add_api_route("/auth/users", get_auth_users, methods=["GET"])
    app.add_api_route("/branding/logo", get_branding_logo, methods=["GET"])
    app.add_api_route("/saved-cohorts", get_saved_cohorts, methods=["GET"])
    app.add_api_route("/saved-cohorts", create_saved_cohort, methods=["POST"])
    app.add_api_route("/saved-cohorts/{cohort_id}", remove_saved_cohort, methods=["DELETE"])
    app.add_api_route("/query", query_app_post, methods=["POST"])
    app.add_api_route("/analysis", analysis_app, methods=["POST"])
    app.add_api_route("/molecular/datasets", get_molecular_datasets, methods=["GET"])
    app.add_api_route("/molecular/genes", get_molecular_genes, methods=["GET"])
    app.add_api_route("/molecular/expression", get_molecular_expression, methods=["POST"])
    app.add_api_route("/analysis-sessions", get_analysis_sessions, methods=["GET"])
    app.add_api_route("/analysis-sessions", create_or_update_analysis_session, methods=["POST"])
    app.add_api_route("/analysis-sessions/{session_id}", update_analysis_session_title, methods=["PATCH"])
    app.add_api_route("/analysis-sessions/{session_id}", remove_analysis_session, methods=["DELETE"])
    app.add_api_route("/pheno-ranker/run", run_pheno_ranker_route, methods=["POST"])
    app.add_api_route("/pheno-ranker/plan", plan_pheno_ranker_route, methods=["POST"])
    app.add_api_route("/pheno-ranker/patient-ids", get_pheno_ranker_patient_ids, methods=["GET"])
    app.add_api_route("/pheno-ranker/results/{job_id}/{filename}", get_pheno_ranker_result, methods=["GET"])
    app.add_api_route("/pheno-ranker/alignment/{job_id}", get_pheno_ranker_alignment, methods=["GET"])
    app.add_api_route("/pheno-ranker/explain/{job_id}", explain_pheno_ranker_results, methods=["GET"])
    app.add_api_route("/pheno-ranker/explain-llm/{job_id}", explain_pheno_ranker_results_llm, methods=["GET"])
    app.add_api_route("/dashboard", get_dashboard, methods=["GET"])
