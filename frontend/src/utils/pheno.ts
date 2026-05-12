import type { PhenoFile, PhenoPlan, PhenoRunRequest } from "../api/types";

export type PhenoFormState = {
  prompt: string;
  action: string;
  mode: string;
  patientId: string;
  selectedPatientIds: string;
  includeTerms: string;
  excludeTerms: string;
  similarityMetricCohort: string;
  sortBy: string;
  maxOut: number;
  align: boolean;
  renderHeatmap: boolean;
  renderMds: boolean;
  renderGraph: boolean;
  graphMinWeight: string;
  graphMaxWeight: string;
};

export const defaultPhenoForm: PhenoFormState = {
  prompt: "Compare all patients by phenotypicFeatures and diseases excluding id",
  action: "compare",
  mode: "cohort",
  patientId: "",
  selectedPatientIds: "",
  includeTerms: "phenotypicFeatures,diseases",
  excludeTerms: "id",
  similarityMetricCohort: "hamming",
  sortBy: "",
  maxOut: 10,
  align: true,
  renderHeatmap: true,
  renderMds: true,
  renderGraph: true,
  graphMinWeight: "",
  graphMaxWeight: "",
};

export function splitTerms(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function optionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function applyPlanToForm(form: PhenoFormState, plan: PhenoPlan): PhenoFormState {
  return {
    ...form,
    action: plan.action || form.action,
    mode: plan.mode || form.mode,
    patientId: plan.patient_id || "",
    selectedPatientIds: plan.selected_patient_ids || form.selectedPatientIds,
    includeTerms: Array.isArray(plan.include_terms) ? plan.include_terms.join(",") : form.includeTerms,
    excludeTerms: Array.isArray(plan.exclude_terms) ? plan.exclude_terms.join(",") : form.excludeTerms,
    similarityMetricCohort: plan.similarity_metric_cohort || form.similarityMetricCohort,
    sortBy: plan.sort_by || form.sortBy,
    maxOut: typeof plan.max_out === "number" ? plan.max_out : form.maxOut,
    align: typeof plan.align === "boolean" ? plan.align : form.align,
    renderHeatmap: typeof plan.render_heatmap === "boolean" ? plan.render_heatmap : form.renderHeatmap,
    renderMds: typeof plan.render_mds === "boolean" ? plan.render_mds : form.renderMds,
    renderGraph: typeof plan.render_graph === "boolean" ? plan.render_graph : form.renderGraph,
    graphMinWeight: typeof plan.graph_min_weight === "number" ? String(plan.graph_min_weight) : form.graphMinWeight,
    graphMaxWeight: typeof plan.graph_max_weight === "number" ? String(plan.graph_max_weight) : form.graphMaxWeight,
  };
}

export function formToRunRequest(form: PhenoFormState, datasetId: string, selectedSavedCohortIds: string[]): PhenoRunRequest {
  return {
    prompt: form.prompt.trim(),
    action: form.action,
    mode: form.mode,
    dataset_id: datasetId,
    data_dir: datasetId,
    patient_id: form.patientId.trim(),
    selected_patient_ids: selectedSavedCohortIds.length ? "" : form.selectedPatientIds.trim(),
    selected_saved_cohort_ids: selectedSavedCohortIds,
    include_terms: splitTerms(form.includeTerms),
    exclude_terms: splitTerms(form.excludeTerms),
    similarity_metric_cohort: form.similarityMetricCohort,
    sort_by: form.sortBy,
    max_out: Number.isFinite(form.maxOut) ? form.maxOut : 10,
    align: form.align,
    render_heatmap: form.renderHeatmap,
    render_mds: form.renderMds,
    render_graph: form.renderGraph,
    graph_min_weight: optionalNumber(form.graphMinWeight),
    graph_max_weight: optionalNumber(form.graphMaxWeight),
  };
}

export function findResultFile(files: PhenoFile[] | undefined, names: string[]): PhenoFile | null {
  const items = Array.isArray(files) ? files : [];
  return items.find((file) => names.includes(file.name)) || null;
}

export function formatBytes(value: number | undefined): string {
  if (!value) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
