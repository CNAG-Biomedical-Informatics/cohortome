import type {
  ApiError,
  AuthStatus,
  AuthUser,
  AuthUsersResponse,
  AnalysisCatalogResponse,
  AnalysisRunRequest,
  AnalysisRunResponse,
  DatasetsResponse,
  DashboardSummary,
  JobRecord,
  JobsResponse,
  MolecularDatasetsResponse,
  PatientContext,
  PatientSummary,
  QueryRunRequest,
  QueryRunResponse,
  PhenoPatientIdsResponse,
  PhenoPlanResponse,
  PhenoRunRequest,
  PhenoRunResponse,
  SavedCohortsResponse,
} from "./types";

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload ? (payload as { detail: unknown }).detail : payload;
    const error = new Error(formatApiDetail(detail) || response.statusText) as ApiError;
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  return payload as T;
}

export function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
    return JSON.stringify(detail, null, 2);
  }
  return "";
}

export const api = {
  auth: () => request<AuthStatus>("/auth/me"),
  login: (username: string, password: string) =>
    request<AuthStatus>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<AuthStatus>("/auth/logout", { method: "POST" }),
  users: () => request<AuthUsersResponse>("/auth/users"),
  createUser: (payload: { username: string; password: string; display_name: string; role: string; groups: string[]; enabled: boolean }) =>
    request<AuthUser>("/auth/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUser: (username: string, payload: { display_name: string; role: string; groups: string[]; enabled: boolean }) =>
    request<AuthUser>(`/auth/users/${encodeURIComponent(username)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  resetUserPassword: (username: string, password: string) =>
    request<AuthUser>(`/auth/users/${encodeURIComponent(username)}/password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  deleteUser: (username: string) =>
    request<{ deleted: boolean; id: string }>(`/auth/users/${encodeURIComponent(username)}`, { method: "DELETE" }),
  datasets: () => request<DatasetsResponse>("/datasets"),
  updateDataset: (datasetId: string, payload: Partial<DatasetRecord>) =>
    request<DatasetRecord>(`/datasets/${encodeURIComponent(datasetId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  prepareDatasetStore: (datasetId: string) =>
    request<DatasetRecord>(`/datasets/${encodeURIComponent(datasetId)}/prepare-store`, { method: "POST" }),
  selectDatasets: (datasetIds: string[]) =>
    request<DatasetsResponse>("/datasets/select", {
      method: "POST",
      body: JSON.stringify({ dataset_ids: datasetIds }),
    }),
  savedCohorts: () => request<SavedCohortsResponse>("/saved-cohorts"),
  jobs: () => request<JobsResponse>("/jobs"),
  job: (jobId: string) => request<JobRecord>(`/jobs/${encodeURIComponent(jobId)}`),
  analysisCatalog: (datasetId: string) =>
    request<AnalysisCatalogResponse>(`/analysis/catalog?dataset_id=${encodeURIComponent(datasetId)}`),
  molecularDatasets: (datasetId: string) =>
    request<MolecularDatasetsResponse>(`/molecular/datasets?dataset_id=${encodeURIComponent(datasetId)}`),
  dashboard: (datasetId: string) =>
    request<DashboardSummary>(`/dashboard?dataset_id=${encodeURIComponent(datasetId)}`),
  patients: (datasetId: string) =>
    request<PatientSummary[]>(`/patients?dataset_id=${encodeURIComponent(datasetId)}`),
  patient: (datasetId: string, patientId: string) =>
    request<PatientContext>(`/patients/${encodeURIComponent(patientId)}?dataset_id=${encodeURIComponent(datasetId)}`),
  queryRun: (payload: QueryRunRequest) =>
    request<QueryRunResponse>("/query", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  analysisRun: (payload: AnalysisRunRequest) =>
    request<AnalysisRunResponse>("/analysis", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  phenoPatientIds: (datasetId: string) =>
    request<PhenoPatientIdsResponse>(`/pheno-ranker/patient-ids?dataset_id=${encodeURIComponent(datasetId)}`),
  phenoPlan: (text: string, datasetId: string, selectedPatientIds: string) =>
    request<PhenoPlanResponse>("/pheno-ranker/plan", {
      method: "POST",
      body: JSON.stringify({
        text,
        dataset_id: datasetId,
        selected_patient_ids: selectedPatientIds,
      }),
    }),
  phenoRun: (payload: PhenoRunRequest) =>
    request<PhenoRunResponse>("/pheno-ranker/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
