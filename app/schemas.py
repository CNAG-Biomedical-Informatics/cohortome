from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from app.config import DEFAULT_DATA_DIR
from app.pheno import normalize_pheno_terms


class QueryTurn(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    q: str
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    query_mode: str = "auto"
    history: List[QueryTurn] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    prompt: str
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    selected_patient_ids: str = ""
    compare_mode: bool = False
    compare_selected_patient_ids: str = ""
    llm_only: bool = False
    deterministic_only: bool = False
    history: List[QueryTurn] = Field(default_factory=list)


class MolecularExpressionRequest(BaseModel):
    dataset_name: str
    gene_id: str
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    selected_patient_ids: str = ""
    compare_selected_patient_ids: str = ""


class AnalysisSessionRequest(BaseModel):
    id: str
    title: str = ""
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    prompt_draft: str = ""
    scope: str = ""
    saved_cohort_id_a: str = ""
    compare_mode: bool = False
    compare_scope: str = ""
    saved_cohort_id_b: str = ""
    history: List[Dict[str, Any]] = Field(default_factory=list)
    turns: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = ""
    created_at: str = ""


class AnalysisSessionRenameRequest(BaseModel):
    title: str = ""


class PhenoRankerRequest(BaseModel):
    action: str = "compare"
    mode: str = "cohort"
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    patient_id: str = ""
    selected_patient_ids: str = ""
    selected_saved_cohort_ids: List[str] = Field(default_factory=list)
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
            return normalize_pheno_terms(value)
        return list(value)


class PhenoRankerPlanRequest(BaseModel):
    text: str
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    selected_patient_ids: str = ""


class SavedCohortRequest(BaseModel):
    name: str = ""
    dataset_id: str = ""
    data_dir: str = DEFAULT_DATA_DIR
    sample_ids: List[str] = Field(default_factory=list)
    patient_ids: List[str] = Field(default_factory=list)
    id_type: str = "sample"
    source_kind: str = "manual"
    source_prompt: str = ""


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class DatasetSelectionRequest(BaseModel):
    dataset_id: str = ""
    dataset_ids: List[str] = Field(default_factory=list)


class DatasetRegistrationRequest(BaseModel):
    name: str = ""
    root_path: str = ""
    description: str = ""
    visibility: str = "all_authenticated"
    allowed_users: List[str] = Field(default_factory=list)
    allowed_groups: List[str] = Field(default_factory=list)
    enabled: bool = True


class DatasetUpdateRequest(BaseModel):
    name: str | None = None
    root_path: str | None = None
    description: str | None = None
    visibility: str | None = None
    allowed_users: List[str] | None = None
    allowed_groups: List[str] | None = None
    enabled: bool | None = None
