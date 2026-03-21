from __future__ import annotations

from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.analysis import analysis_llm_reply
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
from app.schemas import AnalysisRequest, PhenoRankerPlanRequest, PhenoRankerRequest, QueryRequest, SavedCohortRequest
from app.query import answer_query


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
        },
    )


def get_patients(data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    try:
        patients = list_patient_summaries(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [patient.model_dump() for patient in patients]


def get_patient(patient_id: str, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    try:
        patient = get_patient_context(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return patient.model_dump()


def get_patient_navigator(patient_id: str, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    try:
        navigator = build_patient_navigator(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if navigator is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return navigator.model_dump()


def get_medication_counts(data_dir: str = DEFAULT_DATA_DIR) -> List[Dict]:
    try:
        return medication_counts(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def search_medication_cohort(medication: str, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    try:
        return medication_cohort(data_dir, medication)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def query_app(q: str, data_dir: str = DEFAULT_DATA_DIR) -> Dict:
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


def get_saved_cohorts(data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    return {"cohorts": list_saved_cohorts(data_dir)}


def create_saved_cohort(request: SavedCohortRequest) -> Dict:
    try:
        item = save_cohort(
            name=request.name,
            data_dir=request.data_dir,
            ids=request.patient_ids,
            id_type=request.id_type,
            source_kind=request.source_kind,
            source_prompt=request.source_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


def remove_saved_cohort(cohort_id: str) -> Dict:
    deleted = delete_saved_cohort(cohort_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved cohort not found.")
    return {"deleted": True, "id": cohort_id}


def query_app_post(request: QueryRequest) -> Dict:
    try:
        return answer_query(
            request.data_dir,
            request.q,
            history=[turn.model_dump() for turn in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def analysis_app(request: AnalysisRequest) -> Dict:
    try:
        return analysis_llm_reply(
            request.prompt,
            request.data_dir,
            selected_patient_ids=request.selected_patient_ids,
            compare_mode=request.compare_mode,
            compare_selected_patient_ids=request.compare_selected_patient_ids,
            history=[turn.model_dump() for turn in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def run_pheno_ranker_route(request: PhenoRankerRequest) -> Dict:
    return run_pheno_ranker(request)


def plan_pheno_ranker_route(request: PhenoRankerPlanRequest) -> Dict:
    return plan_pheno_ranker(request.text, request.data_dir, selected_patient_ids=request.selected_patient_ids)


def get_pheno_ranker_patient_ids(data_dir: str = DEFAULT_DATA_DIR) -> Dict:
    return pheno_ranker_patient_ids_payload(data_dir)


def get_pheno_ranker_result(job_id: str, filename: str) -> FileResponse:
    file_path = pheno_ranker_result_file_path(job_id, filename)
    return FileResponse(file_path)


def get_pheno_ranker_alignment(job_id: str, reference_id: str, target_id: str = "") -> Dict:
    return pheno_ranker_alignment_details(job_id, reference_id, target_id=target_id)


def explain_pheno_ranker_results(job_id: str, top_n: int = 3) -> Dict:
    return pheno_ranker_explain(job_id, top_n=top_n)


def explain_pheno_ranker_results_llm(job_id: str, top_n: int = 3) -> Dict:
    return pheno_ranker_explain_llm(job_id, top_n=top_n)


def get_dashboard(data_dir: str = DEFAULT_DATA_DIR) -> Dict:
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
    app.add_api_route("/branding/logo", get_branding_logo, methods=["GET"])
    app.add_api_route("/saved-cohorts", get_saved_cohorts, methods=["GET"])
    app.add_api_route("/saved-cohorts", create_saved_cohort, methods=["POST"])
    app.add_api_route("/saved-cohorts/{cohort_id}", remove_saved_cohort, methods=["DELETE"])
    app.add_api_route("/query", query_app_post, methods=["POST"])
    app.add_api_route("/analysis", analysis_app, methods=["POST"])
    app.add_api_route("/pheno-ranker/run", run_pheno_ranker_route, methods=["POST"])
    app.add_api_route("/pheno-ranker/plan", plan_pheno_ranker_route, methods=["POST"])
    app.add_api_route("/pheno-ranker/patient-ids", get_pheno_ranker_patient_ids, methods=["GET"])
    app.add_api_route("/pheno-ranker/results/{job_id}/{filename}", get_pheno_ranker_result, methods=["GET"])
    app.add_api_route("/pheno-ranker/alignment/{job_id}", get_pheno_ranker_alignment, methods=["GET"])
    app.add_api_route("/pheno-ranker/explain/{job_id}", explain_pheno_ranker_results, methods=["GET"])
    app.add_api_route("/pheno-ranker/explain-llm/{job_id}", explain_pheno_ranker_results_llm, methods=["GET"])
    app.add_api_route("/dashboard", get_dashboard, methods=["GET"])
