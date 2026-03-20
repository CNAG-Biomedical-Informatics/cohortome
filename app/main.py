from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import csv
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
JQ_BIN = shutil.which("jq") or "jq"

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
    align: bool = True
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
    selected_patient_ids: str = ""


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


def _resolve_pheno_ranker_reference_paths(data_dir: str) -> List[Path]:
    resolved_dir = ensure_data_dir(data_dir)
    matches = sorted(path for path in resolved_dir.glob("*.json") if path.is_file())
    if matches:
        return matches
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


def _is_non_actionable_pheno_request(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True
    normalized = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in {
        "hi",
        "hello",
        "hey",
        "hola",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
        "ok",
        "okay",
    }:
        return True
    action_tokens = (
        "compare",
        "extract",
        "export",
        "match",
        "matches",
        "rank",
        "align",
        "heatmap",
        "mds",
        "phenotype",
        "phenotypes",
        "disease",
        "diseases",
        "treatment",
        "treatments",
        "exposure",
        "exposures",
        "procedure",
        "procedures",
        "measure",
        "measures",
        "patient",
        "patients",
        "cohort",
        "scope",
    )
    return not any(token in normalized for token in action_tokens)


def _plan_pheno_ranker_deterministic(plan_request: PhenoRankerPlanRequest) -> Dict:
    text = plan_request.text.strip()
    lowered = text.lower()
    if _is_non_actionable_pheno_request(text):
        return {
            "source": "deterministic",
            "plan": None,
            "reasoning": [
                "The prompt is not an actionable Pheno-Ranker request yet.",
                "Describe a comparison or extraction request, for example: compare the selected patients by disease.",
            ],
            "follow_up_suggestions": [
                "Compare all patients by diseases",
                "Find closest matches to Beacon_5 by phenotype",
                "Extract the selected patients",
            ],
        }
    known_ids = _available_patient_ids(plan_request.data_dir)
    known_diseases = _available_disease_labels(plan_request.data_dir)
    patient_ids = _extract_patient_ids_from_text(text, known_ids)
    scope_patient_ids = _split_terms(plan_request.selected_patient_ids)
    disease_filter = _extract_disease_filter_from_text(text, known_diseases)

    action = "extract" if any(keyword in lowered for keyword in ("extract", "export")) else "compare"
    explicit_cohort_phrases = (
        "all to all",
        "compare all",
        "compare everyone",
        "compare the cohort",
        "cohort mode",
        "all patients",
        "all individuals",
    )
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
        "match patient",
        "for patient",
        "for beacon_",
        "rank patient",
        "rank beacon_",
    )
    implicit_single_patient_phrases = (
        "i have a patient",
        "this patient",
        "that patient",
        "my patient",
        "one patient",
        "a patient",
        "the patient",
        "which patients are closer",
        "which patients are closest",
        "patients are closer",
        "patients are closest",
        "closer patients",
        "closest patients",
    )
    explicit_cohort = any(phrase in lowered for phrase in explicit_cohort_phrases)
    has_patient_mode_phrase = any(phrase in lowered for phrase in patient_mode_phrases)
    has_implicit_single_patient_phrase = any(phrase in lowered for phrase in implicit_single_patient_phrases)
    single_patient_compare = action == "compare" and len(patient_ids) == 1 and not explicit_cohort
    patient_mode_without_id = action == "compare" and not patient_ids and has_implicit_single_patient_phrase and not explicit_cohort
    mode = "patient" if (patient_ids and (has_patient_mode_phrase or single_patient_compare)) or patient_mode_without_id else "cohort"
    patient_id = patient_ids[0] if mode == "patient" and patient_ids else ""
    selected_patient_ids = patient_ids if mode != "patient" else []
    if not selected_patient_ids and mode == "cohort" and scope_patient_ids:
        selected_patient_ids = scope_patient_ids
    if mode == "patient" and not patient_id and len(scope_patient_ids) == 1:
        patient_id = scope_patient_ids[0]

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
    align_requested = any(
        phrase in lowered
        for phrase in (
            "align",
            "alignment",
            "which variables match",
            "what variables match",
            "shared variables",
            "matching variables",
            "why do they match",
            "why they match",
        )
    )
    align = mode == "patient" or align_requested
    if action == "extract":
        render_heatmap = False
        render_mds = False
        align = False

    similarity_metric = _normalize_pheno_metric("jaccard" if "jaccard" in lowered else ("hamming" if "hamming" in lowered else ""))
    sort_by = _normalize_pheno_metric("jaccard" if "sort by jaccard" in lowered else ("hamming" if "sort by hamming" in lowered else ""))

    reasoning = []
    reasoning.append(f"Detected action: {action}.")
    reasoning.append(f"Detected mode: {mode}.")
    if single_patient_compare and not has_patient_mode_phrase:
        reasoning.append("Defaulted to patient mode because the request targets one patient and did not explicitly ask for cohort/all-to-all mode.")
    if patient_mode_without_id:
        reasoning.append("Detected patient-mode intent, but no patient ID was provided. Select or provide one patient ID before running.")
    if patient_id:
        reasoning.append(f"Detected target patient: {patient_id}.")
    if selected_patient_ids:
        reasoning.append(f"Detected scope from selected patient IDs: {', '.join(selected_patient_ids)}.")
    elif scope_patient_ids:
        reasoning.append(f"Using existing scope from UI: {', '.join(scope_patient_ids)}.")
    if disease_filter:
        reasoning.append(f"Detected disease filter: {disease_filter}.")
    if include_terms:
        reasoning.append(f"Detected include terms: {', '.join(include_terms)}.")

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
            "align": align,
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


def _pheno_execution_steps(plan: Dict) -> List[str]:
    action = str(plan.get("action") or "compare")
    mode = str(plan.get("mode") or "cohort")
    selected_scope = str(plan.get("selected_patient_ids") or "").strip()
    patient_id = str(plan.get("patient_id") or "").strip()
    steps: List[str] = []

    if action == "extract":
        if selected_scope:
            steps.append("Extract the current scope from the active reference files with jq into one subset JSON.")
        else:
            steps.append("Extract requires a non-empty scope.")
        return steps

    if mode == "cohort":
        if selected_scope:
            steps.append("Extract the current scope from the active reference files with jq into one subset JSON.")
            steps.append("Run cohort comparison on the extracted subset reference.")
        else:
            steps.append("Run cohort comparison directly on the full reference cohort.")
        return steps

    if mode == "patient":
        if patient_id:
            steps.append(f"Extract target patient {patient_id} from the active reference files with jq.")
            steps.append("Run patient-vs-reference ranking with -r -t.")
        else:
            steps.append("Patient mode requires exactly one target patient from Patient ID or Scope.")
        return steps

    return steps


def _attach_execution_steps(payload: Dict) -> Dict:
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        return payload
    enriched_plan = dict(plan)
    enriched_plan["execution_steps"] = _pheno_execution_steps(enriched_plan)
    enriched_payload = dict(payload)
    enriched_payload["plan"] = enriched_plan
    return enriched_payload


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
                    "include_terms, exclude_terms, similarity_metric_cohort, sort_by, max_out, align, render_heatmap, render_mds, reasoning. "
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
    parsed_mode = parsed.get("mode") or "cohort"
    plan = {
        "action": parsed.get("action") or "compare",
        "mode": parsed_mode,
        "data_dir": plan_request.data_dir,
        "patient_id": parsed.get("patient_id") or "",
        "selected_patient_ids": ",".join(parsed.get("selected_patient_ids") or []) if isinstance(parsed.get("selected_patient_ids"), list) else str(parsed.get("selected_patient_ids") or ""),
        "disease_filter": parsed.get("disease_filter") or "",
        "include_terms": _normalize_pheno_terms(",".join(parsed.get("include_terms") or [])) if isinstance(parsed.get("include_terms"), list) else _normalize_pheno_terms(str(parsed.get("include_terms") or "")),
        "exclude_terms": _normalize_pheno_terms(",".join(parsed.get("exclude_terms") or [])) if isinstance(parsed.get("exclude_terms"), list) else _normalize_pheno_terms(str(parsed.get("exclude_terms") or "")),
        "similarity_metric_cohort": _normalize_pheno_metric(str(parsed.get("similarity_metric_cohort") or "")),
        "sort_by": _normalize_pheno_metric(str(parsed.get("sort_by") or "")),
        "max_out": int(parsed.get("max_out") or 10),
        "align": bool(parsed.get("align", parsed_mode == "patient")),
        "render_heatmap": bool(parsed.get("render_heatmap", True)),
        "render_mds": bool(parsed.get("render_mds", True)),
    }
    return {"source": "lm_studio", "plan": plan, "reasoning": reasoning, "follow_up_suggestions": []}


def _plan_pheno_ranker(plan_request: PhenoRankerPlanRequest) -> Dict:
    deterministic = _plan_pheno_ranker_deterministic(plan_request)
    if not isinstance(deterministic.get("plan"), dict):
        return deterministic
    text = plan_request.text.strip().lower()
    if (
        deterministic["plan"]["patient_id"]
        or deterministic["plan"]["mode"] == "patient"
        or deterministic["plan"]["selected_patient_ids"]
        or deterministic["plan"]["disease_filter"]
        or deterministic["plan"]["include_terms"]
        or deterministic["plan"]["exclude_terms"]
        or "compare all" in text
        or "extract" in text
    ):
        return _attach_execution_steps(deterministic)
    llm_plan = _plan_pheno_ranker_llm(plan_request)
    if llm_plan is not None:
        return _attach_execution_steps(llm_plan)
    return _attach_execution_steps(deterministic)


def _pheno_ranker_job_dir() -> Path:
    job_dir = PHENO_RANKER_RUNS_DIR / uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _resolve_pheno_ranker_job_dir(job_id: str) -> Path:
    safe_job_id = Path(job_id).name
    job_dir = (PHENO_RANKER_RUNS_DIR / safe_job_id).resolve()
    runs_root = PHENO_RANKER_RUNS_DIR.resolve()
    if job_dir != runs_root and runs_root not in job_dir.parents:
        raise HTTPException(status_code=404, detail="Pheno-Ranker job not found.")
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Pheno-Ranker job not found.")
    return job_dir


def _alignment_bucket_from_json_path(json_path: str) -> str:
    root = (json_path or "").split(".", 1)[0]
    mapping = {
        "diseases": "diseases",
        "phenotypicFeatures": "phenotypicFeatures",
        "treatments": "treatments",
        "interventionsOrProcedures": "procedures",
        "procedures": "procedures",
        "exposures": "exposures",
        "measures": "measures",
        "sex": "sex",
        "ethnicity": "ethnicity",
        "id": "identifier",
    }
    return mapping.get(root, root or "other")


def _load_alignment_rows(job_dir: Path) -> List[Dict]:
    alignment_path = job_dir / "alignment.target.csv"
    if not alignment_path.exists() or not alignment_path.is_file():
        raise HTTPException(status_code=404, detail="Alignment output not found for this job.")

    rows: List[Dict] = []
    with alignment_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for raw_row in reader:
            reference_id = str(raw_row.get("id") or "").strip()
            json_path = str(raw_row.get("json-path") or "").strip()
            label = str(raw_row.get("label") or "").strip()
            bucket = _alignment_bucket_from_json_path(json_path)
            if not reference_id or not label or bucket == "identifier":
                continue
            ref_present = str(raw_row.get("ref") or "").strip() == "1"
            target_present = str(raw_row.get("tar") or "").strip() == "1"
            rows.append(
                {
                    "reference_id": reference_id,
                    "bucket": bucket,
                    "label": label,
                    "json_path": json_path,
                    "indicator": str(raw_row.get("indicator") or "").strip(),
                    "weight": str(raw_row.get("weight") or "").strip(),
                    "hamming_distance": str(raw_row.get("hamming-distance") or "").strip(),
                    "ref_present": ref_present,
                    "target_present": target_present,
                }
            )
    return rows


def _read_rank_rows(job_dir: Path) -> tuple[List[str], List[Dict[str, str]]]:
    rank_path = job_dir / "rank.txt"
    if not rank_path.exists() or not rank_path.is_file():
        raise HTTPException(status_code=404, detail="rank.txt not found for this job.")
    with rank_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        if len(fieldnames) < 2:
            raise HTTPException(status_code=500, detail="rank.txt has an unexpected TSV structure.")
        rows = []
        for row in reader:
            normalized = {str(key): str(value or "").strip() for key, value in row.items() if key}
            if any(normalized.values()):
                rows.append(normalized)
    return fieldnames, rows


def _detect_rank_metric_columns(headers: List[str], rows: List[Dict[str, str]]) -> List[str]:
    metric_headers: List[str] = []
    ignored = {"REFERENCE(ID)", "TARGET(ID)", "REFERENCE", "TARGET"}
    for header in headers:
        if header in ignored:
            continue
        values = [row.get(header, "") for row in rows[:10]]
        numeric_values = [value for value in values if value and re.fullmatch(r"-?\d+(?:\.\d+)?", value)]
        if numeric_values:
            metric_headers.append(header)
    return metric_headers


def _summarize_alignment_for_reference(rows: List[Dict], reference_id: str) -> Dict[str, Any]:
    current = [row for row in rows if row["reference_id"] == reference_id]
    shared = [row for row in current if row["ref_present"] and row["target_present"]]
    reference_only = [row for row in current if row["ref_present"] and not row["target_present"]]
    target_only = [row for row in current if row["target_present"] and not row["ref_present"]]

    def _bucket_counts(items: List[Dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            bucket = item["bucket"]
            counts[bucket] = counts.get(bucket, 0) + 1
        return counts

    def _top_labels(items: List[Dict], limit: int = 5) -> List[str]:
        labels: List[str] = []
        for item in items:
            label = item.get("label")
            if isinstance(label, str) and label and label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                break
        return labels

    return {
        "reference_id": reference_id,
        "shared_count": len(shared),
        "reference_only_count": len(reference_only),
        "target_only_count": len(target_only),
        "shared_bucket_counts": _bucket_counts(shared),
        "top_shared_labels": _top_labels(shared),
        "top_reference_only_labels": _top_labels(reference_only),
        "top_target_only_labels": _top_labels(target_only),
    }


def _explain_pheno_ranker_results(job_dir: Path, top_n: int = 3) -> Dict:
    headers, rows = _read_rank_rows(job_dir)
    if not rows:
        raise HTTPException(status_code=404, detail="rank.txt is empty for this job.")

    reference_key = "REFERENCE(ID)" if "REFERENCE(ID)" in headers else headers[0]
    target_key = "TARGET(ID)" if "TARGET(ID)" in headers else (headers[1] if len(headers) > 1 else headers[0])
    metric_headers = _detect_rank_metric_columns(headers, rows)
    target_id = rows[0].get(target_key, "")
    selected_rows = rows[: max(1, min(top_n, len(rows)))]

    alignment_rows: List[Dict] = []
    alignment_available = False
    try:
        alignment_rows = _load_alignment_rows(job_dir)
        alignment_available = True
    except HTTPException:
        alignment_available = False

    matches = []
    for row in selected_rows:
        reference_id = row.get(reference_key, "")
        metrics = {header: row.get(header, "") for header in metric_headers}
        match = {
            "reference_id": reference_id,
            "target_id": row.get(target_key, target_id),
            "metrics": metrics,
        }
        if alignment_available and reference_id:
            match["alignment"] = _summarize_alignment_for_reference(alignment_rows, reference_id)
        matches.append(match)

    summary_lines = [f"Top {len(matches)} matches for {target_id or 'the target patient'} from rank.txt."]
    for match in matches:
        line = match["reference_id"] or "unknown"
        if match["metrics"]:
            metric_text = ", ".join(f"{key}: {value}" for key, value in match["metrics"].items() if value != "")
            if metric_text:
                line += f" ({metric_text})"
        alignment = match.get("alignment")
        if isinstance(alignment, dict):
            bucket_counts = alignment.get("shared_bucket_counts") or {}
            bucket_text = ", ".join(f"{bucket}: {count}" for bucket, count in bucket_counts.items())
            if bucket_text:
                line += f" | shared variables: {bucket_text}"
        summary_lines.append(line)

    return {
        "job_id": job_dir.name,
        "mode": "patient",
        "target_id": target_id,
        "top_n": len(matches),
        "alignment_available": alignment_available,
        "metric_headers": metric_headers,
        "matches": matches,
        "summary_lines": summary_lines,
        "source": "deterministic",
    }


def _explain_pheno_ranker_results_llm(job_dir: Path, top_n: int = 3) -> Dict:
    deterministic = _explain_pheno_ranker_results(job_dir, top_n=top_n)
    if not _lm_studio_enabled():
        return {
            **deterministic,
            "source": "llm_unavailable",
            "llm_reply": "LM Studio is not enabled for Pheno-Ranker result explanations.",
        }

    model = _resolve_lm_studio_model()
    if not model:
        return {
            **deterministic,
            "source": "llm_unavailable",
            "llm_reply": "LM Studio is enabled, but no model is currently loaded.",
        }

    explanation_context = {
        "job_id": deterministic["job_id"],
        "mode": deterministic["mode"],
        "target_id": deterministic["target_id"],
        "top_n": deterministic["top_n"],
        "alignment_available": deterministic["alignment_available"],
        "metric_headers": deterministic["metric_headers"],
        "matches": deterministic["matches"],
        "summary_lines": deterministic["summary_lines"],
    }
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You explain Pheno-Ranker patient-mode results. "
                    "Use only the provided JSON evidence. "
                    "Do not invent metrics or variables. "
                    "Keep the explanation concise, factual, and clinically readable. "
                    "Prefer bullet points."
                ),
            },
            {
                "role": "user",
                "content": "Deterministic explanation JSON:\n%s" % json.dumps(explanation_context, ensure_ascii=True, separators=(",", ":")),
            },
        ],
    }
    try:
        response = _http_json(f"{_lm_studio_base_url()}/chat/completions", payload)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            **deterministic,
            "source": "llm_error",
            "llm_reply": "LM Studio returned an HTTP error while explaining these results.",
            "llm_error": {"status_code": exc.code, "detail": detail},
        }
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            **deterministic,
            "source": "llm_error",
            "llm_reply": "LM Studio could not be reached for this explanation.",
            "llm_error": {"detail": str(exc)},
        }

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return {
            **deterministic,
            "source": "llm_error",
            "llm_reply": "LM Studio returned an unexpected response for this explanation.",
            "llm_error": {"response": response},
        }
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        content = "\n".join(text_parts).strip()
    if not isinstance(content, str) or not content.strip():
        return {
            **deterministic,
            "source": "llm_error",
            "llm_reply": "LM Studio returned an empty explanation.",
        }

    return {
        **deterministic,
        "source": "lm_studio",
        "model": model,
        "llm_reply": content.strip(),
    }


def _run_plot_script(job_dir: Path, script_name: str) -> Dict[str, str]:
    script_path = PHENO_RANKER_R_DIR / script_name
    command = ["Rscript", str(script_path)]
    proc = subprocess.run(
        command,
        cwd=job_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    _write_step_logs(job_dir, f"plot_{Path(script_name).stem}", command, proc)
    return {
        "script": script_name,
        "returncode": str(proc.returncode),
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _write_step_logs(job_dir: Path, step_name: str, command: List[str], proc: subprocess.CompletedProcess[str]) -> None:
    safe_step = re.sub(r"[^a-z0-9._-]+", "_", step_name.strip().lower()) or "step"
    (job_dir / f"{safe_step}.command.txt").write_text(" ".join(command), encoding="utf-8")
    (job_dir / f"{safe_step}.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (job_dir / f"{safe_step}.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")


def _serialize_pheno_result(
    job_dir: Path,
    command: List[str],
    proc: subprocess.CompletedProcess[str],
    mode: str,
    plot_runs: List[Dict[str, str]],
    pre_commands: List[str] | None = None,
) -> Dict:
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
        "pre_commands": pre_commands or [],
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "plots": plot_runs,
        "files": files,
    }


def _jq_extract_records(reference_paths: List[Path], patient_ids: List[str], output_path: Path) -> tuple[List[str], subprocess.CompletedProcess[str], List[Dict]]:
    if not patient_ids:
        raise HTTPException(status_code=400, detail="At least one patient ID is required for scoped Pheno-Ranker extraction.")

    jq_filter = (
        "map(if type==\"array\" then . else [.] end) "
        "| flatten "
        "| map(select(type==\"object\" and (((.patient_id // .id // \"\") as $candidate | ($ids | index($candidate))) != null)))"
    )
    command = [
        str(JQ_BIN),
        "-s",
        "--argjson",
        "ids",
        json.dumps(patient_ids, ensure_ascii=True),
        jq_filter,
        *[str(path) for path in reference_paths],
    ]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    _write_step_logs(output_path.parent, f"jq_extract_{output_path.stem}", command, proc)
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "jq extraction failed.",
                "command": " ".join(command),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            },
        )
    try:
        parsed = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="jq extraction returned invalid JSON.") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=500, detail="jq extraction did not return a JSON array.")

    matched_ids = set()
    normalized_records: List[Dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        normalized_records.append(item)
        record_patient_id = _extract_record_patient_id(item)
        record_id = item.get("id")
        if isinstance(record_patient_id, str) and record_patient_id.strip():
            matched_ids.add(record_patient_id.strip())
        if isinstance(record_id, str) and record_id.strip():
            matched_ids.add(record_id.strip())

    missing_ids = [patient_id for patient_id in patient_ids if patient_id not in matched_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "One or more selected patient IDs were not found in the active Pheno-Ranker reference files.",
                "missing_patient_ids": missing_ids,
                "command": " ".join(command),
            },
        )

    if not normalized_records:
        raise HTTPException(status_code=404, detail="No records matched the selected patient IDs for Pheno-Ranker.")

    output_path.write_text(json.dumps(normalized_records, ensure_ascii=False, indent=2), encoding="utf-8")
    return command, proc, normalized_records


def _run_pheno_ranker(request: PhenoRankerRequest) -> Dict:
    if not PHENO_RANKER_BIN.exists():
        raise HTTPException(status_code=500, detail=f"Pheno-Ranker binary not found: {PHENO_RANKER_BIN}")

    job_dir = _pheno_ranker_job_dir()
    action = request.action.strip().lower() or "compare"
    mode = request.mode.strip().lower() or "cohort"
    records: List[Dict] = []
    selected_ids = _split_terms(request.selected_patient_ids)
    patient_id = request.patient_id.strip()
    valid_pheno_ids = set(_available_patient_ids(request.data_dir, limit=100000))
    selected_extract_command: List[str] | None = None
    selected_extract_proc: subprocess.CompletedProcess[str] | None = None
    invalid_scope_ids = [patient_id for patient_id in selected_ids if patient_id not in valid_pheno_ids]
    if invalid_scope_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Scope contains IDs that do not exist in the current Pheno-Ranker reference dataset.",
                "invalid_scope_ids": invalid_scope_ids,
            },
        )
    if action == "compare" and mode == "patient":
        if not patient_id and len(selected_ids) == 1:
            patient_id = selected_ids[0]
        elif len(selected_ids) > 1:
            raise HTTPException(status_code=400, detail="Patient mode expects exactly one patient in scope, or one explicit Patient ID.")
        selected_ids = []
    if mode == "patient" and patient_id and patient_id not in valid_pheno_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Patient ID does not exist in the current Pheno-Ranker reference dataset.",
                "invalid_patient_id": patient_id,
            },
        )
    if request.disease_filter.strip() or mode == "patient" or selected_ids:
        records = _load_pheno_ranker_records(request.data_dir)

    if request.disease_filter.strip():
        records = _filter_records_by_disease(records, request.disease_filter)
        if not records:
            raise HTTPException(status_code=404, detail="No records matched the selected disease filter for Pheno-Ranker.")

    use_temp_reference = bool(request.disease_filter.strip())
    if use_temp_reference:
        temp_reference_path = job_dir / "reference.json"
        temp_reference_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        reference_paths = [temp_reference_path]
    else:
        reference_paths = _resolve_pheno_ranker_reference_paths(request.data_dir)

    if selected_ids and action == "compare" and mode == "cohort":
        merged_reference_path = job_dir / "reference.selected.json"
        selected_extract_command, selected_extract_proc, _ = _jq_extract_records(reference_paths, selected_ids, merged_reference_path)
        reference_paths = [merged_reference_path]

    command = [str(PHENO_RANKER_BIN), "-r", *[str(path) for path in reference_paths]]
    output_path = job_dir / ("matrix.txt" if mode == "cohort" else "rank.txt")

    if action == "extract":
        if not selected_ids:
            raise HTTPException(status_code=400, detail="Extraction mode requires one or more selected patient IDs.")
        extract_path = job_dir / "reference.selected.json"
        extract_command, extract_proc, _ = _jq_extract_records(reference_paths, selected_ids, extract_path)
        return _serialize_pheno_result(job_dir, extract_command, extract_proc, "extract", [])

    if mode == "patient":
        target_records = records if records else _load_pheno_ranker_records(request.data_dir)
        target_record = _find_target_record(target_records, patient_id) or _find_target_record(_load_pheno_ranker_records(request.data_dir), patient_id)
        if target_record is None:
            raise HTTPException(status_code=404, detail=f"Patient not found for Pheno-Ranker target mode: {patient_id}")
        target_path = job_dir / "target.json"
        extract_command, extract_proc, target_records = _jq_extract_records(reference_paths, [patient_id], target_path)
        if len(target_records) != 1:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Target extraction did not resolve to exactly one patient.",
                    "patient_id": patient_id,
                    "matched_records": len(target_records),
                    "command": " ".join(extract_command),
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
    if action == "compare" and mode == "patient" and request.align:
        command.extend(["--align", str(job_dir / "alignment")])

    proc = subprocess.run(command, cwd=job_dir, capture_output=True, text=True, check=False)
    _write_step_logs(job_dir, "pheno_ranker_main", command, proc)
    if proc.returncode != 0:
        detail = {
            "message": "Pheno-Ranker command failed.",
            "command": " ".join(command),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        if selected_extract_command is not None and selected_extract_proc is not None:
            detail["selection_extract_command"] = " ".join(selected_extract_command)
            detail["selection_extract_stdout"] = selected_extract_proc.stdout
            detail["selection_extract_stderr"] = selected_extract_proc.stderr
        raise HTTPException(
            status_code=500,
            detail=detail,
        )

    plot_runs: List[Dict[str, str]] = []
    if mode == "cohort" and output_path.exists():
        if request.render_heatmap:
            plot_runs.append(_run_plot_script(job_dir, "heatmap.R"))
        if request.render_mds:
            plot_runs.append(_run_plot_script(job_dir, "mds.R"))

    pre_commands: List[str] = []
    if selected_extract_command is not None:
        pre_commands.append(" ".join(selected_extract_command))
    if mode == "patient":
        pre_commands.append(" ".join(extract_command))

    return _serialize_pheno_result(job_dir, command, proc, mode, plot_runs, pre_commands=pre_commands)


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


@app.get("/pheno-ranker/patient-ids")
def get_pheno_ranker_patient_ids(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    reference_files = _resolve_pheno_ranker_reference_paths(data_dir)
    return {
        "patient_ids": _available_patient_ids(data_dir, limit=100000),
        "reference_files": [str(path) for path in reference_files],
    }


@app.get("/pheno-ranker/results/{job_id}/{filename}")
def get_pheno_ranker_result(job_id: str, filename: str) -> FileResponse:
    job_dir = _resolve_pheno_ranker_job_dir(job_id)
    safe_filename = Path(filename).name
    file_path = (job_dir / safe_filename).resolve()
    if job_dir not in file_path.parents:
        raise HTTPException(status_code=404, detail="Result file not found.")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Result file not found.")
    return FileResponse(file_path)


@app.get("/pheno-ranker/alignment/{job_id}")
def get_pheno_ranker_alignment(
    job_id: str,
    reference_id: str = Query(..., min_length=1),
    target_id: str = Query(default=""),
) -> Dict:
    job_dir = _resolve_pheno_ranker_job_dir(job_id)
    rows = [row for row in _load_alignment_rows(job_dir) if row["reference_id"] == reference_id]
    if not rows:
        raise HTTPException(status_code=404, detail=f"No alignment details found for reference patient: {reference_id}")

    shared = [row for row in rows if row["ref_present"] and row["target_present"]]
    reference_only = [row for row in rows if row["ref_present"] and not row["target_present"]]
    target_only = [row for row in rows if row["target_present"] and not row["ref_present"]]

    def _bucket_counts(items: List[Dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            bucket = item["bucket"]
            counts[bucket] = counts.get(bucket, 0) + 1
        return counts

    return {
        "job_id": job_dir.name,
        "reference_id": reference_id,
        "target_id": target_id,
        "shared": shared,
        "reference_only": reference_only,
        "target_only": target_only,
        "shared_bucket_counts": _bucket_counts(shared),
        "reference_only_bucket_counts": _bucket_counts(reference_only),
        "target_only_bucket_counts": _bucket_counts(target_only),
    }


@app.get("/pheno-ranker/explain/{job_id}")
def explain_pheno_ranker_results(
    job_id: str,
    top_n: int = Query(default=3, ge=1, le=10),
) -> Dict:
    job_dir = _resolve_pheno_ranker_job_dir(job_id)
    return _explain_pheno_ranker_results(job_dir, top_n=top_n)


@app.get("/pheno-ranker/explain-llm/{job_id}")
def explain_pheno_ranker_results_llm(
    job_id: str,
    top_n: int = Query(default=3, ge=1, le=10),
) -> Dict:
    job_dir = _resolve_pheno_ranker_job_dir(job_id)
    return _explain_pheno_ranker_results_llm(job_dir, top_n=top_n)


@app.get("/dashboard")
def get_dashboard(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        return dashboard_summary(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
