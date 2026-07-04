from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR
from app.env import app_env
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
        "description": "Clinical and transcriptomics assay workspace analysis plus saved analysis sessions.",
    },
    {
        "name": "cohorts",
        "description": "Saved cohort persistence and cohort-scoped handoff utilities.",
    },
    {
        "name": "assays",
        "description": "Assay inventory and per-gene expression summaries.",
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
    configured = app_env("BRN_SESSION_SECRET", "").strip()
    if configured:
        return configured
    if app_env("BRN_AUTH_MODE", "none").strip().lower() == "local":
        raise RuntimeError("BRN_SESSION_SECRET must be set when BRN_AUTH_MODE=local.")
    return "biomedical-research-navigator-dev-session"


app = FastAPI(
    title="Biomedical Research Navigator API",
    summary="Workspace-oriented clinical and assay exploration API.",
    description=(
        "Biomedical Research Navigator exposes a browser-facing API for multi-dataset workspace selection, "
        "clinical query and analysis, saved cohorts, and Pheno-Ranker execution over sample-level data."
    ),
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
)
app.add_middleware(SessionMiddleware, secret_key=_session_secret())
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

register_routes(app, templates)
