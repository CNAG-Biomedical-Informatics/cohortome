from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR
from app.env import app_env
from app.deployment_branding import router as deployment_branding_router
from app.export_settings import router as export_settings_router
from app.resource_install import router as resource_install_router
from app.resource_storage import router as resource_storage_router
from app.projects import router as projects_router
from app.patient_overview import router as patient_overview_router
from app.local_viewer import router as local_viewer_router
from app.pheno_sessions import router as pheno_sessions_router
from app.routes import (
    get_medication_counts,
    get_patient,
    get_patient_workspace,
    get_patients,
    register_routes,
    search_medication_cohort,
)


OPENAPI_TAGS = [
    {
        "name": "ui",
        "description": "HTML entrypoints and static branding assets used by the web application shell.",
    },
    {
        "name": "auth",
        "description": "Authentication state, local login, and user visibility endpoints.",
    },
    {
        "name": "datasets",
        "description": "Dataset registry, workspace selection, and dataset access policy management.",
    },
    {
        "name": "patients",
        "description": "Patient lists, patient timelines, dashboard summaries, and cohort count helpers.",
    },
    {
        "name": "query",
        "description": "Deterministic and LLM-assisted natural-language workspace queries.",
    },
    {
        "name": "analysis",
        "description": "Clinical, assay, imaging, and multimodal workspace analysis plus saved analysis sessions.",
    },
    {
        "name": "cohorts",
        "description": "Saved cohort persistence and cohort-scoped handoff utilities.",
    },
    {
        "name": "assays",
        "description": "Multimodal assay inventory, feature matrices, DICOM metadata, and expression summaries.",
    },
    {
        "name": "dicom",
        "description": "DICOM study discovery and OHIF launch integration.",
    },
    {
        "name": "pheno-ranker",
        "description": "Pheno-Ranker planning, execution, result download, and explanation endpoints.",
    },
]


def _session_secret() -> str:
    configured = app_env("COHORTOME_SESSION_SECRET", "").strip()
    if configured:
        return configured
    if app_env("COHORTOME_AUTH_MODE", "none").strip().lower() == "local":
        raise RuntimeError("COHORTOME_SESSION_SECRET must be set when COHORTOME_AUTH_MODE=local.")
    return "cohortome-dev-session"


app = FastAPI(
    title="COHORTome API",
    summary="Clinical and multimodal cohort exploration and analysis API.",
    description=(
        "COHORTome exposes a browser-facing API for governed multi-dataset workspaces, "
        "longitudinal clinical and assay exploration, cohort discovery, and traceable analysis."
    ),
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
)
app.add_middleware(SessionMiddleware, secret_key=_session_secret())
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

register_routes(app, templates)
app.include_router(deployment_branding_router)
app.include_router(export_settings_router)
app.include_router(resource_install_router)
app.include_router(resource_storage_router)
app.include_router(projects_router)
app.include_router(patient_overview_router)
app.include_router(local_viewer_router)
app.include_router(pheno_sessions_router)
