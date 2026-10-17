from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import DEFAULT_DATA_DIR
from app.pheno import normalize_pheno_terms


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class QueryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class QueryRequest(BaseModel):
    q: str = Field(min_length=1, max_length=12000, description="Natural-language workspace query.", examples=["How many patients take biologics in this workspace?"])
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID to query against.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
    query_mode: str = Field(default="auto", description="Query execution mode. Supported values include auto, deterministic_only, and planner_only.")
    granularity_mode: str = Field(default="detailed", description="Disclosure mode requested by the Query UI. Supported values currently include summary and detailed.")
    history: List[QueryTurn] = Field(default_factory=list, max_length=16)
    scoped_patient_ids: List[str] = Field(default_factory=list, max_length=100, description="Legacy bounded prior-subset patient IDs. Prefer scoped_result_handle for paged Query results.")
    scoped_record_ids: List[str] = Field(default_factory=list, max_length=100, description="Legacy bounded prior-subset sample or record IDs. Prefer scoped_result_handle for paged Query results.")
    scoped_id_type: str = Field(default="patient", description="The primary ID level used by the carried scoped context.")
    scoped_result_handle: str = Field(default="", max_length=96, pattern=r"^(?:|qr_[A-Za-z0-9_-]+)$", description="Opaque user-scoped Query result handle used for follow-up filtering without resending identifiers.")

    @field_validator("scoped_patient_ids", "scoped_record_ids")
    @classmethod
    def _bound_legacy_query_ids(cls, values):
        if any(len(str(value or "")) > 256 for value in values or []):
            raise ValueError("Query scope identifiers must be 256 characters or fewer.")
        return values


class GeneralLlmRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        max_length=12000,
        description="General-knowledge question sent without workspace or dataset context.",
        examples=["What is aspirin?"],
    )
    history: List[QueryTurn] = Field(default_factory=list, description="Recent turns from General question mode only.")


class UserSettingsResponse(BaseModel):
    plot_palette: Literal["default", "okabe-ito", "muted"] = "default"
    heatmap_palette: Literal["default", "viridis", "cividis"] = "default"
    diverging_palette: Literal["default", "blue-orange", "purple-green"] = "default"
    appearance: Literal["light", "dark", "system"] = "light"
    version: int = 1
    landing_tab_mode: Literal["fixed", "last"] = "fixed"
    landing_tab: Literal["dashboard", "datasets", "query", "analysis", "pheno"] = "dashboard"
    query_disclosure_default: Literal["summary", "detailed"] = "detailed"
    query_default_mode: Literal["auto", "planner_only"] = "auto"
    latest_query_details: bool = True
    analysis_auto_open_jobs: bool = True
    job_notifications: bool = True
    run_history_retention_days: Literal[0, 7, 30, 90, 180, 365] = 30
    pheno_default_metric: Literal["", "hamming", "jaccard"] = ""
    pheno_advanced_open: bool = False
    pheno_render_heatmap: bool = True
    pheno_render_mds: bool = True
    pheno_render_umap: bool = False
    pheno_render_graph: bool = True
    dashboard_assays_open: bool = False
    dataset_compact_view: bool = False
    llm_provider_id: str = "system-default"


class UserSettingsUpdateRequest(BaseModel):
    plot_palette: Literal["default", "okabe-ito", "muted"] | None = None
    heatmap_palette: Literal["default", "viridis", "cividis"] | None = None
    diverging_palette: Literal["default", "blue-orange", "purple-green"] | None = None
    appearance: Literal["light", "dark", "system"] | None = None
    landing_tab_mode: Literal["fixed", "last"] | None = None
    landing_tab: Literal["dashboard", "datasets", "query", "analysis", "pheno"] | None = None
    query_disclosure_default: Literal["summary", "detailed"] | None = None
    query_default_mode: Literal["auto", "planner_only"] | None = None
    latest_query_details: bool | None = None
    analysis_auto_open_jobs: bool | None = None
    job_notifications: bool | None = None
    run_history_retention_days: Literal[0, 7, 30, 90, 180, 365] | None = None
    pheno_default_metric: Literal["", "hamming", "jaccard"] | None = None
    pheno_advanced_open: bool | None = None
    pheno_render_heatmap: bool | None = None
    pheno_render_mds: bool | None = None
    pheno_render_umap: bool | None = None
    pheno_render_graph: bool | None = None
    dashboard_assays_open: bool | None = None
    dataset_compact_view: bool | None = None
    llm_provider_id: str | None = None


class AnalysisRequest(BaseModel):
    custom_script: str = Field(default="", max_length=131072)
    script_language: Literal["python", "r"] = "python"
    input_contract_id: str = Field(default="", max_length=64)
    sandbox_image_id: str = Field(default="", max_length=80)
    custom_assay_ids: List[str] = Field(default_factory=list, max_length=4)
    measurement: str = Field(default="", max_length=512, description="Exact clinical measurement label selected from workspace inputs.")
    prompt: str = Field(description="Natural-language analysis prompt.", examples=["Summarize the main workspace patterns and tell me what stands out."])
    catalog_item_id: str = Field(default="", description="Optional Analysis Catalog item identifier used for structured curated analyses.")
    analysis_session_id: str = Field(default="", description="Current Analysis session identifier used to associate queued jobs back to the active session.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for the analysis workspace.")
    assay_id: str = Field(default="", description="Selected assay identifier for curated analyses that require one explicit transcriptomics source.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
    selected_patient_ids: str = Field(default="", description="Comma-separated scope IDs for cohort A. May contain sample or patient IDs depending on the source tab.")
    query_result_handle: str = Field(default="", max_length=96, pattern=r"^(?:|qr_[A-Za-z0-9_-]+)$", description="Opaque Query result handle resolved server-side as cohort A.")
    scope_metadata: Dict[str, Any] = Field(default_factory=dict, description="Saved-cohort-shaped metadata for the Cohort A selection, including sample IDs, patient IDs, and source.")
    compare_mode: bool = Field(default=False, description="Whether to run a compare-mode analysis using cohort A vs cohort B.")
    compare_selected_patient_ids: str = Field(default="", description="Comma-separated scope IDs for cohort B when compare_mode is enabled.")
    compare_scope_metadata: Dict[str, Any] = Field(default_factory=dict, description="Saved-cohort-shaped metadata for the Cohort B selection.")
    llm_only: bool = Field(default=False, description="Force LLM-only analysis mode.")
    deterministic_only: bool = Field(default=False, description="Force deterministic-only analysis mode.")
    history: List[QueryTurn] = Field(default_factory=list)


class AssayExpressionRequest(BaseModel):
    assay_id: str = Field(description="Assay identifier to inspect.")
    gene_id: str = Field(description="Gene identifier or symbol to summarize.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for assay lookups.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
    selected_patient_ids: str = Field(default="", description="Optional comma-separated scope IDs for cohort A filtering.")
    compare_selected_patient_ids: str = Field(default="", description="Optional comma-separated scope IDs for cohort B filtering.")


class QuerySessionRequest(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(default=0, ge=0)
    title: str = Field(default="", max_length=200)
    title_custom: bool = False
    dataset_id: str = Field(default="", max_length=2000)
    prompt_draft: str = Field(default="", max_length=20000)
    context_mode: Literal["workspace", "general"] = "workspace"
    execution_mode: Literal["auto", "planner_only", "deterministic_only"] = "auto"
    history: List[Dict[str, Any]] = Field(default_factory=list, max_length=16)
    turns: List[Dict[str, Any]] = Field(default_factory=list, max_length=200)


class AnalysisSessionRequest(BaseModel):
    script_draft: Dict[str, Any] = Field(default_factory=dict)
    measurement: str = Field(default="", max_length=512)
    id: str = Field(description="Client-generated analysis session identifier.")
    title: str = Field(default="", description="Optional user-facing session title.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for the session.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
    workspace_fingerprint: Dict[str, Any] = Field(default_factory=dict, description="Workspace fingerprint snapshot captured when the session was first bound.")
    catalog_item_id: str = Field(default="", description="Selected Analysis Catalog item for this session, if any.")
    prompt_draft: str = Field(default="", description="Current draft prompt stored for the session.")
    framing: Dict[str, Any] = Field(default_factory=dict, description="Draft research question and exploratory/hypothesis-driven purpose; run snapshots are stored in conversation turns.")
    context_mode: Literal["workspace", "general"] = Field(default="workspace", description="Whether the saved composer is using workspace context or general knowledge.")
    scope: str = Field(default="", description="Comma-separated scope IDs for cohort A.")
    scope_metadata: Dict[str, Any] = Field(default_factory=dict, description="Saved-cohort-shaped metadata for Cohort A.")
    saved_cohort_id_a: str = Field(default="", description="Saved cohort ID currently assigned to cohort A, if any.")
    compare_mode: bool = Field(default=False, description="Whether the session is in compare mode.")
    compare_scope: str = Field(default="", description="Comma-separated scope IDs for cohort B.")
    compare_scope_metadata: Dict[str, Any] = Field(default_factory=dict, description="Saved-cohort-shaped metadata for Cohort B.")
    saved_cohort_id_b: str = Field(default="", description="Saved cohort ID currently assigned to cohort B, if any.")
    history: List[Dict[str, Any]] = Field(default_factory=list)
    turns: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = Field(default="", description="Last-updated timestamp in ISO 8601 format.")
    created_at: str = Field(default="", description="Creation timestamp in ISO 8601 format.")


class AnalysisSessionRenameRequest(BaseModel):
    title: str = Field(default="", description="New title for the analysis session.")


class PhenoRankerRequest(BaseModel):
    prompt: str = Field(default="", description="Current Pheno-Ranker prompt used for run metadata and queued job labels.")
    action: str = Field(default="compare", description="Pheno-Ranker action, typically compare.")
    mode: str = Field(default="cohort", description="Pheno-Ranker mode, such as cohort or patient.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for the workspace.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
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
    render_umap: bool = Field(default=False, description="Opt-in cohort UMAP projection of precomputed distances.")
    render_graph: bool = Field(default=True, description="Whether to generate the interactive Cytoscape graph artifact.")
    graph_min_weight: float | None = Field(default=None, description="Optional minimum edge weight for Pheno-Ranker graph export.")
    graph_max_weight: float | None = Field(default=None, description="Optional maximum edge weight for Pheno-Ranker graph export.")
    granularity_ceiling: str = Field(default="detailed", description="Internal workspace ceiling used to guard Pheno-Ranker access.")
    ai_provider_access: str = Field(default="detailed_allowed", description="Effective AI provider policy used for Pheno-Ranker planner/explanation paths.")

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

    @field_validator("graph_min_weight", "graph_max_weight", mode="before")
    @classmethod
    def _coerce_optional_graph_weight(cls, value):
        if value is None or value == "":
            return None
        return value

    @model_validator(mode="after")
    def _validate_graph_weight_range(self):
        if self.graph_min_weight is not None and self.graph_max_weight is not None and self.graph_min_weight > self.graph_max_weight:
            raise ValueError("Graph minimum edge weight cannot be greater than maximum edge weight.")
        return self


class PhenoRankerPlanRequest(BaseModel):
    text: str = Field(description="Natural-language instruction to convert into a Pheno-Ranker plan.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID for planning.")
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
    selected_patient_ids: str = Field(default="", description="Optional comma-separated scope IDs already selected in the UI.")


class CohortMember(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=200)
    patient_id: str = Field(min_length=1, max_length=512)
    sample_id: str = Field(default="", max_length=512)


class SavedCohortRequest(BaseModel):
    members: List[CohortMember] | None = Field(default=None, max_length=100000)
    name: str = Field(default="", description="User-facing saved cohort name.")
    dataset_id: str = Field(default="", description="Dataset ID or multi-dataset scope ID where the cohort was created.")
    dataset_ids: List[str] = Field(default_factory=list)
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Manual dataset directory fallback. Prefer dataset_id.")
    sample_ids: List[str] = Field(default_factory=list, max_length=2500, description="Legacy bounded canonical sample/record IDs. Prefer result_handle for Query results.")
    patient_ids: List[str] = Field(default_factory=list, max_length=2500, description="Legacy bounded derived patient IDs. Prefer result_handle for Query results.")
    result_handle: str = Field(default="", max_length=96, pattern=r"^(?:|qr_[A-Za-z0-9_-]+)$", description="Opaque Query result handle resolved server-side when saving a Query cohort.")
    id_type: str = Field(default="sample", description="Canonical ID level used by the cohort payload.")
    source_kind: str = Field(default="manual", description="How the cohort was created, for example manual or query.")
    source_prompt: str = Field(default="", description="Source prompt when the cohort came from Query.")


class QualifiedCohortMember(CohortMember):
    patient_key: str
    sample_key: str = ""


class LoginRequest(BaseModel):
    username: str = Field(default="", description="Local username.")
    password: str = Field(default="", description="Local password.")


class AuthUserCreateRequest(BaseModel):
    username: str = Field(default="", description="Unique local username.")
    password: str = Field(default="", description="Initial local password.")
    display_name: str = Field(default="", description="User-facing display name.")
    email: str = Field(default="", description="Optional email address used for self-service password reset.")
    role: str = Field(default="user", description="Application role: user or admin.")
    groups: List[str] = Field(default_factory=list, description="Application groups used for dataset authorization.")
    enabled: bool = Field(default=True, description="Whether the user can sign in.")


class AuthUserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, description="Updated display name.")
    email: str | None = Field(default=None, description="Updated email address used for self-service password reset.")
    role: str | None = Field(default=None, description="Updated application role.")
    groups: List[str] | None = Field(default=None, description="Replacement application groups.")
    enabled: bool | None = Field(default=None, description="Whether the user can sign in.")


class AuthPasswordResetRequest(BaseModel):
    password: str = Field(default="", description="Replacement local password.")


class AuthPasswordResetStartRequest(BaseModel):
    identifier: str = Field(default="", description="Username or email address for password reset.")


class AuthPasswordResetConfirmRequest(BaseModel):
    token: str = Field(default="", description="Password reset token from the reset link.")
    password: str = Field(default="", description="New local password.")


class AuthPasswordResetResponse(BaseModel):
    ok: bool = True
    message: str


class LmProviderCreateRequest(BaseModel):
    id: str = Field(default="", description="Stable provider ID used by persisted user settings.")
    label: str = Field(default="", description="User-facing provider label.")
    base_url: str = Field(default="", description="OpenAI-compatible API base URL, normally ending in /v1.")
    model: str = Field(default="", description="Model ID. Leave empty to use the first model reported by the provider.")
    api_key: str = Field(default="", description="Write-only API key. It is never returned by the API.", json_schema_extra={"writeOnly": True})
    timeout_seconds: float = Field(default=30, description="Provider request timeout in seconds.")
    enabled: bool = Field(default=True, description="Whether users may select and use this provider.")
    data_boundary: Literal["local", "external"] = Field(default="external", description="Explicit deployment boundary used for private-data policy.")


class LmProviderUpdateRequest(BaseModel):
    label: str | None = Field(default=None, description="Updated user-facing provider label.")
    base_url: str | None = Field(default=None, description="Updated OpenAI-compatible API base URL.")
    model: str | None = Field(default=None, description="Updated model ID; an empty value enables model discovery.")
    api_key: str | None = Field(default=None, description="Replacement write-only API key. Empty values retain the stored key.", json_schema_extra={"writeOnly": True})
    timeout_seconds: float | None = Field(default=None, description="Updated provider request timeout in seconds.")
    enabled: bool | None = Field(default=None, description="Whether users may select and use this provider.")
    data_boundary: Literal["local", "external"] | None = Field(default=None, description="Updated deployment boundary.")


class LmProviderResponse(FlexibleModel):
    id: str
    label: str
    base_url: str
    model: str | None = None
    enabled: bool = True
    data_boundary: Literal["local", "external"] = "external"
    source: str = "configuration"
    managed: bool = False
    timeout_seconds: float = 30
    api_key_configured: bool = False


class LmProvidersResponse(BaseModel):
    providers: List[LmProviderResponse] = Field(default_factory=list)
    registry_error: str = ""


class DatasetSelectionRequest(BaseModel):
    dataset_id: str = Field(default="", description="Single dataset ID for backward compatibility.")
    dataset_ids: List[str] = Field(default_factory=list, description="Dataset IDs that define the active workspace. An empty list unloads it.")


class DatasetRegistrationRequest(BaseModel):
    name: str = Field(default="", description="Human-readable dataset name.")
    root_path: str = Field(default="", description="Dataset root directory containing clinical/ and assays/ subdirectories.")
    description: str = Field(default="", description="Optional dataset description shown in the UI.")
    visibility: str = Field(default="all_authenticated", description="Dataset visibility policy: all_authenticated, restricted, or admin_only.")
    data_classification: str = Field(default="private", description="Data egress classification: public or private. Private data cannot be sent to external AI providers.")
    allowed_users: List[str] = Field(default_factory=list, description="Usernames with direct access when visibility is restricted.")
    allowed_groups: List[str] = Field(default_factory=list, description="Groups with access when visibility is restricted.")
    query_granularity_ceiling: str = Field(default="summary", description="Maximum Query thread mode allowed for this dataset: summary or detailed.")
    ai_provider_access: str = Field(default="detailed_allowed", description="Maximum AI provider disclosure allowed after applying data classification and provider boundary.")
    enabled: bool = Field(default=True, description="Whether the dataset can be selected in the UI.")


class DatasetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, description="Updated human-readable dataset name.")
    root_path: str | None = Field(default=None, description="Updated dataset root directory.")
    description: str | None = Field(default=None, description="Updated UI description.")
    visibility: str | None = Field(default=None, description="Updated visibility policy.")
    data_classification: str | None = Field(default=None, description="Updated data egress classification: public or private.")
    allowed_users: List[str] | None = Field(default=None, description="Replacement direct-access username list.")
    allowed_groups: List[str] | None = Field(default=None, description="Replacement allowed-group list.")
    query_granularity_ceiling: str | None = Field(default=None, description="Updated maximum Query thread mode for this dataset.")
    ai_provider_access: str | None = Field(default=None, description="Updated maximum AI provider access mode.")
    enabled: bool | None = Field(default=None, description="Whether the dataset remains selectable.")


class AuthUserResponse(FlexibleModel):
    username: str
    role: str
    display_name: str
    email: str = ""
    groups: List[str] = Field(default_factory=list)
    enabled: bool = True
    auth_source: str = "local"
    login_method: str = "local"


class AuthStatusResponse(BaseModel):
    enabled: bool
    mode: str = "none"
    provider: str = "none"
    authenticated: bool
    local_login_enabled: bool = False
    password_reset_enabled: bool = False
    user: AuthUserResponse | None = None


class AuthDiagnosticsResponse(BaseModel):
    enabled: bool
    mode: str
    provider: str = "none"
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
    root_path: str = ""
    enabled: bool
    visibility: str
    data_classification: str = "private"
    allowed_users: List[str] = Field(default_factory=list)
    allowed_groups: List[str] = Field(default_factory=list)
    query_granularity_ceiling: str = "summary"
    ai_provider_access: str = "detailed_allowed"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    query_store_status: Dict[str, Any] = Field(default_factory=dict)


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
    members: List[QualifiedCohortMember] | None = None
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
    id: str = ""
    deleted_count: int = 0
    deleted_generated_data: bool = False
    related_job_count: int = 0
    deleted_job_count: int = 0
    kept_job_count: int = 0
    skipped_active_count: int = 0


class PatientSummaryResponse(FlexibleModel):
    patient_id: str = ""


class LmStatusResponse(BaseModel):
    enabled: bool
    available: bool = False
    status: str = "disabled"
    base_url: str
    model: str | None = None
    detail: str = ""
    selected_provider_id: str = "system-default"
    provider: Dict[str, Any] = Field(default_factory=dict)
    providers: List[Dict[str, Any]] = Field(default_factory=list)


class AssayDatasetResponse(FlexibleModel):
    assay_id: str = ""


class AssayDatasetsResponse(BaseModel):
    datasets: List[AssayDatasetResponse] = Field(default_factory=list)


class AssayReadinessResponse(FlexibleModel):
    workspace: Dict[str, Any] = Field(default_factory=dict)
    modalities: List[Dict[str, Any]] = Field(default_factory=list)
    pairwise_overlaps: List[Dict[str, Any]] = Field(default_factory=list)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)


class AssayFeatureMatrixResponse(FlexibleModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    missingness: List[Dict[str, Any]] = Field(default_factory=list)
    feature_groups: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)


class DicomStudyResponse(FlexibleModel):
    study_instance_uid: str = ""


class DicomStudiesResponse(BaseModel):
    enabled: bool = False
    studies: List[DicomStudyResponse] = Field(default_factory=list)


class DicomStatusResponse(FlexibleModel):
    enabled: bool = False
    study_count: int = 0
