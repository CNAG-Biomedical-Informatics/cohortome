from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import DEFAULT_DATA_DIR
from app.pheno import normalize_pheno_terms


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class QueryTurn(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    q: str = Field(description="Natural-language workspace query.", examples=["How many patients take biologics in this workspace?"])
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID to query against.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    query_mode: str = Field(default="auto", description="Query execution mode. Supported values include auto and planner_only.")
    history: List[QueryTurn] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    prompt: str = Field(description="Natural-language analysis prompt.", examples=["Summarize the main workspace patterns and tell me what stands out."])
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for the analysis workspace.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    selected_patient_ids: str = Field(default="", description="Comma-separated scope IDs for cohort A. May contain sample or patient IDs depending on the source tab.")
    compare_mode: bool = Field(default=False, description="Whether to run a compare-mode analysis using cohort A vs cohort B.")
    compare_selected_patient_ids: str = Field(default="", description="Comma-separated scope IDs for cohort B when compare_mode is enabled.")
    llm_only: bool = Field(default=False, description="Force LLM-only analysis mode.")
    deterministic_only: bool = Field(default=False, description="Force deterministic-only analysis mode.")
    history: List[QueryTurn] = Field(default_factory=list)


class MolecularExpressionRequest(BaseModel):
    dataset_name: str = Field(description="Name of the molecular dataset to inspect.")
    gene_id: str = Field(description="Gene identifier or symbol to summarize.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for molecular lookups.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    selected_patient_ids: str = Field(default="", description="Optional comma-separated scope IDs for cohort A filtering.")
    compare_selected_patient_ids: str = Field(default="", description="Optional comma-separated scope IDs for cohort B filtering.")


class AnalysisSessionRequest(BaseModel):
    id: str = Field(description="Client-generated analysis session identifier.")
    title: str = Field(default="", description="Optional user-facing session title.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for the session.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    prompt_draft: str = Field(default="", description="Current draft prompt stored for the session.")
    scope: str = Field(default="", description="Comma-separated scope IDs for cohort A.")
    saved_cohort_id_a: str = Field(default="", description="Saved cohort ID currently assigned to cohort A, if any.")
    compare_mode: bool = Field(default=False, description="Whether the session is in compare mode.")
    compare_scope: str = Field(default="", description="Comma-separated scope IDs for cohort B.")
    saved_cohort_id_b: str = Field(default="", description="Saved cohort ID currently assigned to cohort B, if any.")
    history: List[Dict[str, Any]] = Field(default_factory=list)
    turns: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = Field(default="", description="Last-updated timestamp in ISO 8601 format.")
    created_at: str = Field(default="", description="Creation timestamp in ISO 8601 format.")


class AnalysisSessionRenameRequest(BaseModel):
    title: str = Field(default="", description="New title for the analysis session.")


class PhenoRankerRequest(BaseModel):
    action: str = Field(default="compare", description="Pheno-Ranker action, typically compare.")
    mode: str = Field(default="cohort", description="Pheno-Ranker mode, such as cohort or patient.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for the workspace.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    patient_id: str = Field(default="", description="Single target sample/patient ID for patient mode.")
    selected_patient_ids: str = Field(default="", description="Comma-separated scope IDs for cohort mode.")
    selected_saved_cohort_ids: List[str] = Field(default_factory=list)
    disease_filter: str = Field(default="", description="Optional disease label filter for eligible reference files.")
    include_terms: List[str] = Field(default_factory=list)
    exclude_terms: List[str] = Field(default_factory=list)
    similarity_metric_cohort: str = Field(default="", description="Similarity metric to use for cohort comparison.")
    sort_by: str = Field(default="", description="Sort strategy for rank output.")
    max_out: int = Field(default=10, description="Maximum number of ranked output matches to keep.")
    align: bool = Field(default=True, description="Whether to compute term alignment details.")
    render_heatmap: bool = Field(default=True, description="Whether to generate the interactive heatmap artifact.")
    render_mds: bool = Field(default=True, description="Whether to generate the interactive MDS artifact.")

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
    text: str = Field(description="Natural-language instruction to convert into a Pheno-Ranker plan.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for planning.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    selected_patient_ids: str = Field(default="", description="Optional comma-separated scope IDs already selected in the UI.")


class SavedCohortRequest(BaseModel):
    name: str = Field(default="", description="User-facing saved cohort name.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID where the cohort was created.")
    dataset_ids: List[str] = Field(default_factory=list)
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Legacy dataset directory fallback. Prefer dataset_id.")
    sample_ids: List[str] = Field(default_factory=list, description="Canonical sample/record IDs stored for the cohort.")
    patient_ids: List[str] = Field(default_factory=list, description="Derived patient IDs stored alongside the cohort.")
    id_type: str = Field(default="sample", description="Canonical ID level used by the cohort payload.")
    source_kind: str = Field(default="manual", description="How the cohort was created, for example manual or query.")
    source_prompt: str = Field(default="", description="Source prompt when the cohort came from Query.")


class LoginRequest(BaseModel):
    username: str = Field(default="", description="Local username.")
    password: str = Field(default="", description="Local password.")


class DatasetSelectionRequest(BaseModel):
    dataset_id: str = Field(default="", description="Single dataset ID for backward compatibility.")
    dataset_ids: List[str] = Field(default_factory=list, description="One or more dataset IDs that define the active workspace.")


class DatasetRegistrationRequest(BaseModel):
    name: str = Field(default="", description="Human-readable dataset name.")
    root_path: str = Field(default="", description="Dataset root directory containing clinical/ and molecular/ subdirectories.")
    description: str = Field(default="", description="Optional dataset description shown in the UI.")
    visibility: str = Field(default="all_authenticated", description="Dataset visibility policy: all_authenticated, restricted, or admin_only.")
    allowed_users: List[str] = Field(default_factory=list, description="Usernames with direct access when visibility is restricted.")
    allowed_groups: List[str] = Field(default_factory=list, description="Groups with access when visibility is restricted.")
    enabled: bool = Field(default=True, description="Whether the dataset can be selected in the UI.")


class DatasetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, description="Updated human-readable dataset name.")
    root_path: str | None = Field(default=None, description="Updated dataset root directory.")
    description: str | None = Field(default=None, description="Updated UI description.")
    visibility: str | None = Field(default=None, description="Updated visibility policy.")
    allowed_users: List[str] | None = Field(default=None, description="Replacement direct-access username list.")
    allowed_groups: List[str] | None = Field(default=None, description="Replacement allowed-group list.")
    enabled: bool | None = Field(default=None, description="Whether the dataset remains selectable.")


class AuthUserResponse(FlexibleModel):
    username: str
    role: str
    display_name: str
    groups: List[str] = Field(default_factory=list)


class AuthStatusResponse(BaseModel):
    enabled: bool
    authenticated: bool
    user: AuthUserResponse | None = None


class AuthDiagnosticsResponse(BaseModel):
    enabled: bool
    mode: str
    user_count: int
    usernames: List[str] = Field(default_factory=list)
    roles: Dict[str, str] = Field(default_factory=dict)
    groups: Dict[str, List[str]] = Field(default_factory=dict)
    source: str


class AuthUsersResponse(BaseModel):
    mode: str
    users: List[AuthUserResponse] = Field(default_factory=list)


class DatasetRecordResponse(FlexibleModel):
    dataset_id: str
    name: str
    description: str = ""
    root_path: str
    enabled: bool
    visibility: str
    allowed_users: List[str] = Field(default_factory=list)
    allowed_groups: List[str] = Field(default_factory=list)
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""


class DatasetsResponse(BaseModel):
    datasets: List[DatasetRecordResponse] = Field(default_factory=list)
    current_dataset_id: str = ""
    current_dataset_ids: List[str] = Field(default_factory=list)
    current_dataset_scope_id: str = ""
    current_dataset: DatasetRecordResponse | None = None


class DatasetSelectionResponse(BaseModel):
    selected: bool
    current_dataset_id: str = ""
    current_dataset_ids: List[str] = Field(default_factory=list)
    current_dataset_scope_id: str = ""


class SavedCohortSourceResponse(BaseModel):
    kind: str = ""
    prompt: str = ""


class SavedCohortResponse(FlexibleModel):
    id: str
    name: str
    dataset_id: str = ""
    dataset_ids: List[str] = Field(default_factory=list)
    data_dir: str = ""
    id_type: str = "sample"
    sample_ids: List[str] = Field(default_factory=list)
    patient_ids: List[str] = Field(default_factory=list)
    sample_count: int = 0
    patient_count: int = 0
    is_full_dataset: bool = False
    source: SavedCohortSourceResponse = Field(default_factory=SavedCohortSourceResponse)
    created_at: str = ""
    updated_at: str = ""


class SavedCohortsResponse(BaseModel):
    cohorts: List[SavedCohortResponse] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


class PatientSummaryResponse(FlexibleModel):
    patient_id: str = ""


class LmStatusResponse(BaseModel):
    enabled: bool
    base_url: str
    model: str | None = None


class MolecularDatasetResponse(FlexibleModel):
    dataset_name: str = ""


class MolecularDatasetsResponse(BaseModel):
    datasets: List[MolecularDatasetResponse] = Field(default_factory=list)
