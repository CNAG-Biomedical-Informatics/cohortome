export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type AuthUser = {
  username: string;
  role?: string;
  display_name?: string;
  groups?: string[];
  enabled?: boolean;
  auth_source?: string;
};

export type AuthStatus = {
  enabled: boolean;
  authenticated: boolean;
  user?: AuthUser;
};

export type DatasetRecord = {
  dataset_id: string;
  name?: string;
  description?: string;
  root_path?: string;
  enabled?: boolean;
  visibility?: string;
  query_granularity_ceiling?: string;
  ai_provider_access?: string;
  query_store_status?: {
    ready?: boolean;
    status?: string;
    state?: string;
    message?: string;
    last_error?: string;
  };
  content_tags?: string[];
  content_summary?: string;
  content_counts?: {
    patients?: number;
    timepoints?: number;
    molecular_datasets?: number;
  };
};

export type DatasetsResponse = {
  datasets: DatasetRecord[];
  current_dataset_id?: string;
  current_dataset_ids?: string[];
  current_dataset_scope_id?: string;
  current_dataset?: DatasetRecord | null;
};

export type AuthUsersResponse = {
  mode?: string;
  users: AuthUser[];
};

export type SavedCohort = {
  id: string;
  name: string;
  sample_ids?: string[];
  patient_ids?: string[];
  id_type?: string;
  dataset_id?: string;
  is_full_dataset?: boolean;
  source_kind?: string;
  source_prompt?: string;
};

export type SavedCohortsResponse = {
  cohorts: SavedCohort[];
};

export type JobRecord = {
  job_id: string;
  job_code?: string;
  status: string;
  feature?: string;
  name?: string;
  prompt?: string;
  dataset_id?: string;
  result_available?: boolean;
  result_payload?: PhenoRunResponse;
  reply_preview?: string;
  submitted_at?: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
  error?: string;
  artifacts?: Array<{ name?: string; url?: string; size?: number }>;
};

export type JobsResponse = {
  jobs: JobRecord[];
};

export type AnalysisCatalogItem = {
  id: string;
  name: string;
  category?: string;
  kind?: string;
  description?: string;
  guidance?: string;
  default_prompt?: string;
  execution_mode?: string;
  execution_backend?: string;
  runner_type?: string;
  runner_ref?: string;
  expected_runtime?: string;
  default_compare_mode?: boolean;
  supports_compare_mode?: boolean;
  requires_detailed_access?: boolean;
  requires_molecular?: boolean;
  available?: boolean;
  unavailable_reason?: string;
  workspace_requirements?: string[];
  tags?: string[];
};

export type AnalysisCatalogResponse = {
  items: AnalysisCatalogItem[];
  workspace?: {
    granularity_ceiling?: string;
    ai_provider_access?: string;
    has_molecular_datasets?: boolean;
    molecular_dataset_count?: number;
  };
};

export type MolecularDatasetRecord = {
  name: string;
  dataset_name?: string;
  sample_count?: number;
  patient_count?: number;
  gene_count?: number;
  modality?: string;
};

export type MolecularDatasetsResponse = {
  datasets: MolecularDatasetRecord[];
};

export type EvidenceBucket = {
  count?: number;
  examples?: string[];
};

export type EvidenceInventory = {
  diseases?: EvidenceBucket;
  phenotypic_features?: EvidenceBucket;
  measures?: EvidenceBucket;
  treatments?: EvidenceBucket;
  procedures?: EvidenceBucket;
  exposures?: EvidenceBucket;
};

export type PatientSummary = {
  patient_id: string;
  sex?: string;
  vital_status?: string;
  visit_count?: number;
  first_event_date?: string;
  last_event_date?: string;
  evidence?: EvidenceInventory;
  source_files?: string[];
  dataset_names?: string[];
};

export type PatientVisit = {
  visit_id: string;
  event_date?: string;
  event_type?: string;
  diagnosis?: string;
  disease_label?: string;
  evidence?: EvidenceInventory;
};

export type PatientContext = PatientSummary & {
  age_at_first_visit?: string;
  patient_notes?: Record<string, JsonValue>;
  visits?: PatientVisit[];
};

export type DashboardSummary = {
  totals?: {
    patients?: number;
    visits?: number;
    avg_visits_per_patient?: number;
    source_files?: number;
  };
  sex_counts?: Record<string, number>;
  visit_distribution?: Record<string, number>;
  top_medications?: Array<{ medication?: string; patient_count?: number; value?: number; label?: string }>;
  top_diseases?: Array<{ disease?: string; patient_count?: number; value?: number; label?: string }>;
  patients?: PatientSummary[];
  timelines?: Array<Record<string, JsonValue>>;
};

export type QueryRunRequest = {
  q: string;
  dataset_id?: string;
  query_mode?: string;
  granularity_mode?: string;
  history?: Array<{ role: string; content: string }>;
  scoped_patient_ids?: string[];
  scoped_record_ids?: string[];
  scoped_id_type?: string;
};

export type QueryRunResponse = {
  intent?: string;
  reply?: string;
  data?: Record<string, JsonValue>;
  followups?: string[];
};

export type AnalysisRunRequest = {
  prompt: string;
  catalog_item_id?: string;
  analysis_session_id?: string;
  dataset_id?: string;
  molecular_dataset_name?: string;
  selected_patient_ids?: string;
  compare_mode?: boolean;
  compare_selected_patient_ids?: string;
  llm_only?: boolean;
  deterministic_only?: boolean;
  history?: Array<{ role: string; content: string }>;
};

export type AnalysisRunResponse = {
  intent?: string;
  reply?: string;
  data?: Record<string, JsonValue>;
  model?: string;
  prompt?: string;
};

export type PhenoFile = {
  name: string;
  size?: number;
  url: string;
};

export type PhenoPlan = {
  action?: string;
  mode?: string;
  patient_id?: string;
  selected_patient_ids?: string;
  selected_saved_cohort_ids?: string[];
  include_terms?: string[];
  exclude_terms?: string[];
  similarity_metric_cohort?: string;
  sort_by?: string;
  max_out?: number;
  align?: boolean;
  render_heatmap?: boolean;
  render_mds?: boolean;
  render_graph?: boolean;
  graph_min_weight?: number | null;
  graph_max_weight?: number | null;
};

export type PhenoPlanResponse = {
  plan?: PhenoPlan;
  reasoning?: string[];
  source?: string;
  model?: string;
  data?: Record<string, JsonValue>;
};

export type PhenoPatientIdsResponse = {
  patient_ids: string[];
  record_ids: string[];
  reference_files: string[];
};

export type PhenoRunRequest = {
  prompt: string;
  action: string;
  mode: string;
  dataset_id?: string;
  data_dir?: string;
  patient_id: string;
  selected_patient_ids: string;
  selected_saved_cohort_ids: string[];
  include_terms: string[];
  exclude_terms: string[];
  similarity_metric_cohort: string;
  sort_by: string;
  max_out: number;
  align: boolean;
  render_heatmap: boolean;
  render_mds: boolean;
  render_graph: boolean;
  graph_min_weight: number | null;
  graph_max_weight: number | null;
};

export type PhenoRunResponse = {
  intent?: string;
  job_id?: string;
  job_code?: string;
  status?: string;
  feature?: string;
  mode?: string;
  dataset_id?: string;
  command?: string;
  pre_commands?: string[];
  returncode?: number;
  stdout?: string;
  stderr?: string;
  files?: PhenoFile[];
  plots?: Array<{ script?: string; stdout?: string; stderr?: string }>;
  similarity_metric_cohort?: string;
  scope_expansion_note?: string;
  graph_min_weight?: number | null;
  graph_max_weight?: number | null;
  resolved_sample_count?: number;
  background_threshold?: number;
  reply?: string;
  data?: {
    execution?: string;
    job_id?: string;
    job_status?: string;
    job_code?: string;
    feature?: string;
  };
};

export type ApiError = Error & {
  status?: number;
  detail?: unknown;
};
