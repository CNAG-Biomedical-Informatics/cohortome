from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib import error, request
from uuid import uuid4
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.bff import (
    build_patient_navigator,
    dashboard_summary,
    ensure_data_dir,
    get_patient_context,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
    read_bff_records,
)
from app.query import answer_query


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = str((BASE_DIR / "data").resolve())
PHENO_RANKER_DIR = Path("/media/mrueda/2TBS/CNAG/Project_PhenoRanker/pheno-ranker")
PHENO_RANKER_BIN = PHENO_RANKER_DIR / "bin" / "pheno-ranker"
PHENO_RANKER_R_DIR = PHENO_RANKER_DIR / "share" / "r"
PHENO_RANKER_RUNS_DIR = BASE_DIR / "runs" / "pheno-ranker"

app = FastAPI(title="Patient Navigator BFF MVP")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class QueryTurn(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    q: str
    data_dir: str = DEFAULT_DATA_DIR
    history: List[QueryTurn] = Field(default_factory=list)


class PhenoRankerRequest(BaseModel):
    action: str = "compare"
    mode: str = "cohort"
    data_dir: str = DEFAULT_DATA_DIR
    patient_id: str = ""
    selected_patient_ids: str = ""
    disease_filter: str = ""
    include_terms: List[str] = Field(default_factory=list)
    exclude_terms: List[str] = Field(default_factory=list)
    similarity_metric_cohort: str = ""
    sort_by: str = ""
    max_out: int = 10
    render_heatmap: bool = True
    render_mds: bool = True

    @field_validator("include_terms", "exclude_terms", mode="before")
    @classmethod
    def _coerce_term_lists(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return _normalize_pheno_terms(value)
        return list(value)


class PhenoRankerPlanRequest(BaseModel):
    text: str
    data_dir: str = DEFAULT_DATA_DIR


def _lm_studio_enabled() -> bool:
    value = os.getenv("LM_STUDIO_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _lm_studio_base_url() -> str:
    return os.getenv("LM_STUDIO_BASE_URL", "http://192.168.1.42:1234/v1").rstrip("/")


def _lm_studio_timeout() -> float:
    raw = os.getenv("LM_STUDIO_TIMEOUT", "30").strip()
    try:
        return float(raw)
    except ValueError:
        return 30.0


def _lm_studio_api_key() -> str:
    return os.getenv("LM_STUDIO_API_KEY", "lm-studio")


def _http_json(url: str, payload: Dict | None = None) -> Dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {_lm_studio_api_key()}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with request.urlopen(req, timeout=_lm_studio_timeout()) as response:
        return json.loads(response.read().decode("utf-8"))


def _resolve_lm_studio_model() -> str | None:
    configured = os.getenv("LM_STUDIO_MODEL", "").strip()
    if configured:
        return configured
    try:
        payload = _http_json(f"{_lm_studio_base_url()}/models")
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    model_id = first.get("id")
    return model_id if isinstance(model_id, str) and model_id.strip() else None


def _extract_record_patient_id(record: Dict) -> str | None:
    patient_id = record.get("patient_id")
    if isinstance(patient_id, str) and patient_id.strip():
        return patient_id.strip()
    record_id = record.get("id")
    if isinstance(record_id, str) and record_id.strip():
        if ":" in record_id:
            return record_id.split(":", 1)[0].strip()
        return record_id.strip()
    return None


def _extract_record_disease_labels(record: Dict) -> List[str]:
    diseases = record.get("diseases")
    if not isinstance(diseases, list):
        return []
    labels: List[str] = []
    for item in diseases:
        if not isinstance(item, dict):
            continue
        code = item.get("diseaseCode")
        if not isinstance(code, dict):
            continue
        label = code.get("label") or code.get("id")
        if isinstance(label, str) and label.strip() and label not in labels:
            labels.append(label.strip())
    return labels


def _load_pheno_ranker_records(data_dir: str) -> List[Dict]:
    records: List[Dict] = []
    for _, _, record in read_bff_records(ensure_data_dir(data_dir)):
        records.append(record)
    return records


def _resolve_pheno_ranker_reference_path(data_dir: str) -> Path:
    resolved_dir = ensure_data_dir(data_dir)
    for candidate_name in ("bff.json", "individuals.json"):
        candidate = resolved_dir / candidate_name
        if candidate.exists() and candidate.is_file():
            return candidate
    matches = sorted(resolved_dir.glob("*.json"))
    if matches:
        return matches[0]
    raise HTTPException(status_code=404, detail=f"No JSON reference file found for Pheno-Ranker in: {resolved_dir}")


def _filter_records_by_disease(records: List[Dict], disease_filter: str) -> List[Dict]:
    query = disease_filter.strip().lower()
    if not query:
        return records
    filtered: List[Dict] = []
    for record in records:
        labels = _extract_record_disease_labels(record)
        if any(query in label.lower() for label in labels):
            filtered.append(record)
    return filtered


def _find_target_record(records: List[Dict], patient_id: str) -> Dict | None:
    query = patient_id.strip()
    if not query:
        return None
    for record in records:
        record_patient_id = _extract_record_patient_id(record)
        if record_patient_id == query:
            return record
    for record in records:
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id.strip() == query:
            return record
    return None


def _split_terms(raw_terms: str) -> List[str]:
    return [item.strip() for item in raw_terms.split(",") if item.strip()]


def _normalize_pheno_term(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    lowered = normalized.lower().replace("-", "").replace("_", "")
    aliases = {
        "diseases": "diseases",
        "disease": "diseases",
        "phenotype": "phenotypicFeatures",
        "phenotypes": "phenotypicFeatures",
        "phenotypicfeature": "phenotypicFeatures",
        "phenotypicfeatures": "phenotypicFeatures",
        "feature": "phenotypicFeatures",
        "features": "phenotypicFeatures",
        "measures": "measures",
        "measure": "measures",
        "treatments": "treatments",
        "treatment": "treatments",
        "procedures": "procedures",
        "procedure": "procedures",
        "exposures": "exposures",
        "exposure": "exposures",
        "sex": "sex",
        "ethnicity": "ethnicity",
    }
    return aliases.get(lowered, "")


def _normalize_pheno_terms(raw_terms: str) -> List[str]:
    normalized_terms: List[str] = []
    seen = set()
    expanded_terms = re.split(r"[,/]|(?:\band\b)|(?:\bonly\b)", raw_terms, flags=re.IGNORECASE)
    for term in expanded_terms:
        term = term.strip()
        if not term:
            continue
        normalized = _normalize_pheno_term(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_terms.append(normalized)
    return normalized_terms


def _normalize_pheno_metric(value: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in {"hamming", "jaccard"} else ""


def _filter_records_by_patient_ids(records: List[Dict], patient_ids: List[str]) -> List[Dict]:
    if not patient_ids:
        return records
    wanted = set(patient_ids)
    filtered: List[Dict] = []
    for record in records:
        record_patient_id = _extract_record_patient_id(record)
        record_id = record.get("id")
        if record_patient_id in wanted or (isinstance(record_id, str) and record_id in wanted):
            filtered.append(record)
    return filtered


def _available_patient_ids(data_dir: str, limit: int = 200) -> List[str]:
    ids: List[str] = []
    for record in _load_pheno_ranker_records(data_dir):
        patient_id = _extract_record_patient_id(record)
        if patient_id and patient_id not in ids:
            ids.append(patient_id)
        if len(ids) >= limit:
            break
    return ids


def _available_disease_labels(data_dir: str, limit: int = 50) -> List[str]:
    labels: List[str] = []
    for record in _load_pheno_ranker_records(data_dir):
        for label in _extract_record_disease_labels(record):
            if label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                return labels
    return labels


def _extract_patient_ids_from_text(text: str, known_ids: List[str]) -> List[str]:
    found: List[str] = []
    lowered = text.lower()
    for patient_id in known_ids:
        token = patient_id.lower()
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
        if re.search(pattern, lowered):
            found.append(patient_id)
    return found


def _extract_disease_filter_from_text(text: str, known_labels: List[str]) -> str:
    lowered = text.lower()
    for label in sorted(known_labels, key=len, reverse=True):
        if label.lower() in lowered:
            return label
    match = re.search(r"(?:with disease|by disease|disease)\s+([a-z0-9 :_-]+)", lowered)
    if match:
        return match.group(1).strip(" .?")
    return ""


def _plan_pheno_ranker_deterministic(plan_request: PhenoRankerPlanRequest) -> Dict:
    text = plan_request.text.strip()
    lowered = text.lower()
    known_ids = _available_patient_ids(plan_request.data_dir)
    known_diseases = _available_disease_labels(plan_request.data_dir)
    patient_ids = _extract_patient_ids_from_text(text, known_ids)
    disease_filter = _extract_disease_filter_from_text(text, known_diseases)

    action = "extract" if any(keyword in lowered for keyword in ("extract", "export")) else "compare"
    patient_mode_phrases = (
        "patient mode",
        "to all",
        "to all others",
        "against all",
        "against all others",
        "vs all",
        "vs all others",
        "versus all",
        "versus all others",
        "best matches to",
        "closest matches to",
        "similar patients to",
        "matches to",
    )
    mode = "patient" if any(phrase in lowered for phrase in patient_mode_phrases) and patient_ids else "cohort"
    patient_id = patient_ids[0] if mode == "patient" and patient_ids else ""
    selected_patient_ids = patient_ids if mode != "patient" else []

    include_terms = []
    exclude_terms = []
    include_match = re.search(r"include(?: terms)?\s+([a-z0-9_, -]+)", lowered)
    if include_match:
        include_terms = _normalize_pheno_terms(include_match.group(1))
    if not include_terms:
        inferred_include_terms: List[str] = []
        for pattern in (
            r"based on\s+([a-z0-9_, /\-]+)",
            r"using\s+([a-z0-9_, /\-]+)",
            r"with\s+([a-z0-9_, /\-]+)",
            r"by\s+([a-z0-9_, /\-]+)",
        ):
            match = re.search(pattern, lowered)
            if not match:
                continue
            for normalized in _normalize_pheno_terms(match.group(1)):
                if normalized not in inferred_include_terms:
                    inferred_include_terms.append(normalized)
        include_terms = inferred_include_terms
    exclude_match = re.search(r"exclude(?: terms)?\s+([a-z0-9_, -]+)", lowered)
    if exclude_match:
        exclude_terms = _normalize_pheno_terms(exclude_match.group(1))

    render_heatmap = "mds only" not in lowered and ("heatmap" in lowered or "both" in lowered or "plot" in lowered or action == "compare")
    render_mds = "heatmap only" not in lowered and ("mds" in lowered or "both" in lowered or "plot" in lowered or action == "compare")
    if action == "extract":
        render_heatmap = False
        render_mds = False

    similarity_metric = _normalize_pheno_metric("jaccard" if "jaccard" in lowered else ("hamming" if "hamming" in lowered else ""))
    sort_by = _normalize_pheno_metric("jaccard" if "sort by jaccard" in lowered else ("hamming" if "sort by hamming" in lowered else ""))

    reasoning = []
    reasoning.append(f"Detected action: {action}.")
    reasoning.append(f"Detected mode: {mode}.")
    if patient_id:
        reasoning.append(f"Detected target patient: {patient_id}.")
    if selected_patient_ids:
        reasoning.append(f"Detected selected patient IDs: {', '.join(selected_patient_ids)}.")
    if disease_filter:
        reasoning.append(f"Detected disease filter: {disease_filter}.")

    return {
        "source": "deterministic",
        "plan": {
            "action": action,
            "mode": mode,
            "data_dir": plan_request.data_dir,
            "patient_id": patient_id,
            "selected_patient_ids": ",".join(selected_patient_ids),
            "disease_filter": disease_filter,
            "include_terms": include_terms,
            "exclude_terms": exclude_terms,
            "similarity_metric_cohort": similarity_metric,
            "sort_by": sort_by,
            "max_out": 10,
            "render_heatmap": render_heatmap,
            "render_mds": render_mds,
        },
        "reasoning": reasoning,
        "follow_up_suggestions": [
            "Compare all patients",
            "Compare patient 107 to all",
            "Extract patients with Crohn Disease",
        ],
    }


def _plan_pheno_ranker_llm(plan_request: PhenoRankerPlanRequest) -> Dict | None:
    if not _lm_studio_enabled():
        return None
    model = _resolve_lm_studio_model()
    if not model:
        return None
    context = {
        "request": plan_request.text,
        "available_patient_ids": _available_patient_ids(plan_request.data_dir, limit=100),
        "available_disease_labels": _available_disease_labels(plan_request.data_dir, limit=40),
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Convert the user request into a JSON Pheno-Ranker plan. "
                    "Return JSON only with keys: action, mode, patient_id, selected_patient_ids, disease_filter, "
                    "include_terms, exclude_terms, similarity_metric_cohort, sort_by, max_out, render_heatmap, render_mds, reasoning. "
                    "Use arrays for include_terms and exclude_terms. "
                    "Use action compare or extract. Use mode cohort or patient."
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=True, separators=(",", ":"))},
        ],
    }
    try:
        response = _http_json(f"{_lm_studio_base_url()}/chat/completions", payload)
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    reasoning = parsed.get("reasoning")
    if isinstance(reasoning, str):
        reasoning = [reasoning]
    if not isinstance(reasoning, list):
        reasoning = ["Planned by LM Studio."]
    plan = {
        "action": parsed.get("action") or "compare",
        "mode": parsed.get("mode") or "cohort",
        "data_dir": plan_request.data_dir,
        "patient_id": parsed.get("patient_id") or "",
        "selected_patient_ids": ",".join(parsed.get("selected_patient_ids") or []) if isinstance(parsed.get("selected_patient_ids"), list) else str(parsed.get("selected_patient_ids") or ""),
        "disease_filter": parsed.get("disease_filter") or "",
        "include_terms": _normalize_pheno_terms(",".join(parsed.get("include_terms") or [])) if isinstance(parsed.get("include_terms"), list) else _normalize_pheno_terms(str(parsed.get("include_terms") or "")),
        "exclude_terms": _normalize_pheno_terms(",".join(parsed.get("exclude_terms") or [])) if isinstance(parsed.get("exclude_terms"), list) else _normalize_pheno_terms(str(parsed.get("exclude_terms") or "")),
        "similarity_metric_cohort": _normalize_pheno_metric(str(parsed.get("similarity_metric_cohort") or "")),
        "sort_by": _normalize_pheno_metric(str(parsed.get("sort_by") or "")),
        "max_out": int(parsed.get("max_out") or 10),
        "render_heatmap": bool(parsed.get("render_heatmap", True)),
        "render_mds": bool(parsed.get("render_mds", True)),
    }
    return {"source": "lm_studio", "plan": plan, "reasoning": reasoning, "follow_up_suggestions": []}


def _plan_pheno_ranker(plan_request: PhenoRankerPlanRequest) -> Dict:
    deterministic = _plan_pheno_ranker_deterministic(plan_request)
    text = plan_request.text.strip().lower()
    if deterministic["plan"]["patient_id"] or deterministic["plan"]["selected_patient_ids"] or deterministic["plan"]["disease_filter"] or "compare all" in text or "extract" in text:
        return deterministic
    llm_plan = _plan_pheno_ranker_llm(plan_request)
    if llm_plan is not None:
        return llm_plan
    return deterministic


def _pheno_ranker_job_dir() -> Path:
    job_dir = PHENO_RANKER_RUNS_DIR / uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _run_plot_script(job_dir: Path, script_name: str) -> Dict[str, str]:
    script_path = PHENO_RANKER_R_DIR / script_name
    proc = subprocess.run(
        ["Rscript", str(script_path)],
        cwd=job_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "script": script_name,
        "returncode": str(proc.returncode),
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _serialize_pheno_result(job_dir: Path, command: List[str], proc: subprocess.CompletedProcess[str], mode: str, plot_runs: List[Dict[str, str]]) -> Dict:
    files = []
    for path in sorted(job_dir.iterdir()):
        if not path.is_file():
            continue
        files.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "url": f"/pheno-ranker/results/{job_dir.name}/{path.name}",
            }
        )
    return {
        "job_id": job_dir.name,
        "mode": mode,
        "command": " ".join(command),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "plots": plot_runs,
        "files": files,
    }


def _run_pheno_ranker(request: PhenoRankerRequest) -> Dict:
    if not PHENO_RANKER_BIN.exists():
        raise HTTPException(status_code=500, detail=f"Pheno-Ranker binary not found: {PHENO_RANKER_BIN}")

    job_dir = _pheno_ranker_job_dir()
    action = request.action.strip().lower() or "compare"
    mode = request.mode.strip().lower() or "cohort"
    records: List[Dict] = []
    selected_ids = _split_terms(request.selected_patient_ids)
    if action == "compare" and mode == "patient":
        selected_ids = []
    if request.disease_filter.strip() or mode == "patient" or selected_ids:
        records = _load_pheno_ranker_records(request.data_dir)

    if request.disease_filter.strip():
        records = _filter_records_by_disease(records, request.disease_filter)
        if not records:
            raise HTTPException(status_code=404, detail="No records matched the selected disease filter for Pheno-Ranker.")
    if selected_ids:
        base_records = records if records else _load_pheno_ranker_records(request.data_dir)
        records = _filter_records_by_patient_ids(base_records, selected_ids)
        if not records:
            raise HTTPException(status_code=404, detail="No records matched the selected patient IDs for Pheno-Ranker.")

    use_temp_reference = bool(request.disease_filter.strip() or selected_ids)
    if use_temp_reference:
        reference_path = job_dir / "reference.json"
        reference_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        reference_path = _resolve_pheno_ranker_reference_path(request.data_dir)

    command = [str(PHENO_RANKER_BIN), "-r", str(reference_path)]
    output_path = job_dir / ("matrix.txt" if mode == "cohort" else "rank.txt")

    if action == "extract":
        if not selected_ids:
            raise HTTPException(status_code=400, detail="Extraction mode requires one or more selected patient IDs.")
        poi_dir = job_dir / "patients_of_interest"
        poi_dir.mkdir(parents=True, exist_ok=True)
        command.extend(["-poi", ",".join(selected_ids), "-poi-out-dir", str(poi_dir)])
        proc = subprocess.run(command, cwd=job_dir, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Pheno-Ranker extraction failed.",
                    "command": " ".join(command),
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
            )
        return _serialize_pheno_result(job_dir, command, proc, "extract", [])

    if mode == "patient":
        target_records = records if records else _load_pheno_ranker_records(request.data_dir)
        target_record = _find_target_record(target_records, request.patient_id) or _find_target_record(_load_pheno_ranker_records(request.data_dir), request.patient_id)
        if target_record is None:
            raise HTTPException(status_code=404, detail=f"Patient not found for Pheno-Ranker target mode: {request.patient_id}")
        poi_dir = job_dir / "patient_target"
        poi_dir.mkdir(parents=True, exist_ok=True)
        extract_command = [
            str(PHENO_RANKER_BIN),
            "-r",
            str(reference_path),
            "-poi",
            str(request.patient_id),
            "-poi-out-dir",
            str(poi_dir),
        ]
        extract_proc = subprocess.run(extract_command, cwd=job_dir, capture_output=True, text=True, check=False)
        if extract_proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Pheno-Ranker patient extraction failed.",
                    "command": " ".join(extract_command),
                    "stdout": extract_proc.stdout,
                    "stderr": extract_proc.stderr,
                },
            )
        target_path = poi_dir / f"{request.patient_id}.json"
        if not target_path.exists():
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Pheno-Ranker patient extraction did not produce the expected target file.",
                    "command": " ".join(extract_command),
                    "stdout": extract_proc.stdout,
                    "stderr": extract_proc.stderr,
                },
            )
        command.extend(["-t", str(target_path)])

    command.extend(["-o", str(output_path)])

    include_terms = []
    for term in request.include_terms:
        normalized = _normalize_pheno_term(term)
        if normalized and normalized not in include_terms:
            include_terms.append(normalized)
    if include_terms:
        command.extend(["-include-terms", *include_terms])
    exclude_terms = []
    for term in request.exclude_terms:
        normalized = _normalize_pheno_term(term)
        if normalized and normalized not in exclude_terms:
            exclude_terms.append(normalized)
    if exclude_terms:
        command.extend(["-exclude-terms", *exclude_terms])
    sort_by = _normalize_pheno_metric(request.sort_by)
    if sort_by:
        command.extend(["-sort-by", sort_by])
    similarity_metric = _normalize_pheno_metric(request.similarity_metric_cohort)
    if mode == "cohort" and similarity_metric:
        command.extend(["-similarity-metric-cohort", similarity_metric])
    if action == "compare" and mode == "patient" and request.max_out > 0:
        command.extend(["-max-out", str(request.max_out)])

    proc = subprocess.run(command, cwd=job_dir, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Pheno-Ranker command failed.",
                "command": " ".join(command),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            },
        )

    plot_runs: List[Dict[str, str]] = []
    if mode == "cohort" and output_path.exists():
        if request.render_heatmap:
            plot_runs.append(_run_plot_script(job_dir, "heatmap.R"))
        if request.render_mds:
            plot_runs.append(_run_plot_script(job_dir, "mds.R"))

    return _serialize_pheno_result(job_dir, command, proc, mode, plot_runs)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_data_dir": DEFAULT_DATA_DIR,
        },
    )


@app.get("/patients")
def get_patients(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> List[Dict]:
    try:
        patients = list_patient_summaries(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [patient.model_dump() for patient in patients]


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        patient = get_patient_context(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return patient.model_dump()


@app.get("/patients/{patient_id}/navigator")
def get_patient_navigator(patient_id: str, data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        navigator = build_patient_navigator(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if navigator is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return navigator.model_dump()


@app.get("/cohorts/medications")
def get_medication_counts(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> List[Dict]:
    try:
        return medication_counts(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/cohorts/medications/search")
def search_medication_cohort(
    medication: str = Query(..., min_length=1),
    data_dir: str = Query(default=DEFAULT_DATA_DIR),
) -> Dict:
    try:
        return medication_cohort(data_dir, medication)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/query")
def query_app(
    q: str = Query(..., min_length=1),
    data_dir: str = Query(default=DEFAULT_DATA_DIR),
) -> Dict:
    try:
        return answer_query(data_dir, q)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/query")
def query_app_post(request: QueryRequest) -> Dict:
    try:
        return answer_query(
            request.data_dir,
            request.q,
            history=[turn.model_dump() for turn in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/pheno-ranker/run")
def run_pheno_ranker(request: PhenoRankerRequest) -> Dict:
    return _run_pheno_ranker(request)


@app.post("/pheno-ranker/plan")
def plan_pheno_ranker(request: PhenoRankerPlanRequest) -> Dict:
    return _plan_pheno_ranker(request)


@app.get("/pheno-ranker/results/{job_id}/{filename}")
def get_pheno_ranker_result(job_id: str, filename: str) -> FileResponse:
    safe_job_id = Path(job_id).name
    safe_filename = Path(filename).name
    file_path = (PHENO_RANKER_RUNS_DIR / safe_job_id / safe_filename).resolve()
    runs_root = PHENO_RANKER_RUNS_DIR.resolve()
    if runs_root not in file_path.parents:
        raise HTTPException(status_code=404, detail="Result file not found.")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Result file not found.")
    return FileResponse(file_path)


@app.get("/dashboard")
def get_dashboard(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        return dashboard_summary(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
