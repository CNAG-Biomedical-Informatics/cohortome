from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR
from app.routes import (
    get_medication_counts,
    get_patient,
    get_patient_navigator,
    get_patients,
    register_routes,
    search_medication_cohort,
)


app = FastAPI(title="Patient Navigator BFF MVP")
app.add_middleware(SessionMiddleware, secret_key="patient-navigator-local-session")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

register_routes(app, templates)
