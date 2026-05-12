import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatApiDetail } from "../../api/client";
import type { AnalysisCatalogItem, AnalysisRunResponse, ApiError, DatasetRecord, MolecularDatasetRecord, SavedCohort } from "../../api/types";

type AnalysisTurn = {
  id: string;
  prompt: string;
  itemName: string;
  response: AnalysisRunResponse | null;
  error?: string;
};

export function AnalysisTab({ datasetId, selectedDatasets }: { datasetId: string; selectedDatasets: DatasetRecord[] }) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [compareMode, setCompareMode] = useState(false);
  const [cohortAId, setCohortAId] = useState("");
  const [cohortBId, setCohortBId] = useState("");
  const [molecularDatasetName, setMolecularDatasetName] = useState("");
  const [turns, setTurns] = useState<AnalysisTurn[]>([]);

  const catalog = useQuery({
    queryKey: ["analysis-catalog", datasetId],
    queryFn: () => api.analysisCatalog(datasetId),
    enabled: Boolean(datasetId),
  });

  const savedCohorts = useQuery({
    queryKey: ["saved-cohorts", datasetId],
    queryFn: api.savedCohorts,
    enabled: Boolean(datasetId),
  });

  const molecularDatasets = useQuery({
    queryKey: ["molecular-datasets", datasetId],
    queryFn: () => api.molecularDatasets(datasetId),
    enabled: Boolean(datasetId),
  });

  const selectedItem = useMemo(() => {
    return (catalog.data?.items || []).find((item) => item.id === selectedItemId) || null;
  }, [catalog.data?.items, selectedItemId]);

  useEffect(() => {
    if (!selectedItem) return;
    setPrompt(selectedItem.default_prompt || "");
    setCompareMode(Boolean(selectedItem.default_compare_mode));
    if (!selectedItem.requires_molecular) {
      setMolecularDatasetName("");
    }
  }, [selectedItem]);

  useEffect(() => {
    const first = molecularDatasets.data?.datasets?.[0];
    if (first && selectedItem?.requires_molecular && !molecularDatasetName) {
      setMolecularDatasetName(molecularDatasetLabel(first));
    }
  }, [molecularDatasets.data?.datasets, molecularDatasetName, selectedItem]);

  const run = useMutation({
    mutationFn: async () => {
      const cohortA = cohortById(savedCohorts.data?.cohorts || [], cohortAId);
      const cohortB = cohortById(savedCohorts.data?.cohorts || [], cohortBId);
      return api.analysisRun({
        prompt: prompt.trim(),
        catalog_item_id: selectedItem?.id || "",
        dataset_id: datasetId,
        molecular_dataset_name: molecularDatasetName,
        selected_patient_ids: cohortIds(cohortA),
        compare_mode: compareMode,
        compare_selected_patient_ids: compareMode ? cohortIds(cohortB) : "",
        llm_only: selectedItem?.execution_mode === "llm_only",
        deterministic_only: selectedItem?.execution_mode === "deterministic",
        history: turns.slice(-6).flatMap((turn) => [
          { role: "user", content: turn.prompt },
          { role: "assistant", content: turn.response?.reply || "" },
        ]),
      });
    },
    onSuccess: (response) => {
      setTurns((current) => [
        ...current,
        {
          id: `${Date.now()}`,
          prompt: prompt.trim(),
          itemName: selectedItem?.name || "Analysis",
          response,
        },
      ]);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      setTurns((current) => [
        ...current,
        {
          id: `${Date.now()}`,
          prompt: prompt.trim(),
          itemName: selectedItem?.name || "Analysis",
          response: null,
          error: formatApiDetail((error as ApiError).detail) || (error as Error).message,
        },
      ]);
    },
  });

  const items = catalog.data?.items || [];
  const filteredItems = items.filter((item) => itemMatches(item, query, filter));
  const categories = Array.from(new Set(items.map((item) => item.category || "General"))).sort();
  const blocker = analysisBlocker({
    datasetId,
    selectedItem,
    prompt,
    compareMode,
    cohortAId,
    cohortBId,
    molecularDatasetName,
  });

  return (
    <section className="react-analysis-layout">
      <div className="section-heading">
        <div>
          <label>Analysis</label>
          <h2>React Analysis Catalog</h2>
          <p className="section-note">
            Workspace: {selectedDatasets.map((dataset) => dataset.name || dataset.dataset_id).join(", ") || datasetId || "none"}.
            {catalog.data?.workspace ? ` ${catalog.data.workspace.molecular_dataset_count || 0} molecular datasets.` : ""}
          </p>
        </div>
        <a className="query-chip" href="/#analysisTab">Open legacy Analysis</a>
      </div>

      <div className="react-analysis-grid">
        <aside className="pheno-result-card react-analysis-catalog">
          <div className="react-analysis-search">
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search analyses" />
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="available">Ready</option>
              <option value="blocked">Blocked</option>
              {categories.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
          </div>
          <div className="query-meta">
            {catalog.isLoading ? "Loading catalog..." : `${filteredItems.length} of ${items.length} analyses`}
          </div>
          {catalog.error ? <div className="query-status">{(catalog.error as Error).message}</div> : null}
          <div className="react-analysis-card-list">
            {filteredItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`analysis-catalog-card react-analysis-card${selectedItemId === item.id ? " selected" : ""}${item.available === false ? " blocked" : ""}`}
                onClick={() => setSelectedItemId(item.id)}
              >
                <div className="analysis-catalog-card-main">
                  <strong>{item.name}</strong>
                  <span>{item.description || item.guidance || item.id}</span>
                </div>
                <div className="analysis-catalog-card-meta">
                  <span className="query-chip badge">{item.category || "General"}</span>
                  <span className="query-chip badge">{runnerLabel(item.runner_type)}</span>
                  {item.execution_backend === "job" ? <span className="query-chip badge">Background job</span> : null}
                  {item.available === false ? <span className="query-chip badge">Blocked</span> : <span className="query-chip badge">Ready</span>}
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="pheno-result-card react-analysis-setup">
          <h3>{selectedItem?.name || "Select an analysis"}</h3>
          {selectedItem ? (
            <>
              <div className={`query-status ${selectedItem.available === false ? "" : "is-ready"}`}>
                {selectedItem.available === false ? selectedItem.unavailable_reason || "This analysis is not ready." : readinessText(selectedItem)}
              </div>
              {selectedItem.workspace_requirements?.length ? (
                <div className="react-analysis-requirements">
                  {selectedItem.workspace_requirements.map((item) => <span key={item} className="query-chip badge">{item}</span>)}
                </div>
              ) : null}
              <label htmlFor="reactAnalysisPrompt">Prompt</label>
              <textarea id="reactAnalysisPrompt" rows={5} value={prompt} onChange={(event) => setPrompt(event.target.value)} />

              {selectedItem.requires_molecular ? (
                <div>
                  <label>Molecular dataset</label>
                  <select value={molecularDatasetName} onChange={(event) => setMolecularDatasetName(event.target.value)}>
                    <option value="">Select molecular dataset</option>
                    {(molecularDatasets.data?.datasets || []).map((dataset) => {
                      const label = molecularDatasetLabel(dataset);
                      return <option key={label} value={label}>{label}</option>;
                    })}
                  </select>
                </div>
              ) : null}

              {selectedItem.supports_compare_mode || selectedItem.default_compare_mode ? (
                <div className="react-analysis-compare">
                  <label className="react-checkbox">
                    <input type="checkbox" checked={compareMode} onChange={(event) => setCompareMode(event.target.checked)} />
                    <span>Compare Cohort A and Cohort B</span>
                  </label>
                  <div className="pheno-advanced-grid">
                    <CohortSelect label="Cohort A" value={cohortAId} cohorts={savedCohorts.data?.cohorts || []} onChange={setCohortAId} />
                    <CohortSelect label="Cohort B" value={cohortBId} cohorts={savedCohorts.data?.cohorts || []} onChange={setCohortBId} disabled={!compareMode} />
                  </div>
                </div>
              ) : null}

              {blocker ? <div className="query-status">{blocker}</div> : null}
              <div className="pheno-actions pheno-actions-primary">
                <button type="button" disabled={Boolean(blocker) || run.isPending} onClick={() => run.mutate()}>
                  <span>{run.isPending ? "Running..." : selectedItem.execution_backend === "job" ? "Queue analysis" : "Run analysis"}</span>
                </button>
              </div>
            </>
          ) : (
            <div className="empty">Choose an analysis from the catalog to see setup requirements.</div>
          )}
        </section>
      </div>

      <section className="react-analysis-thread">
        {turns.length ? turns.map((turn) => <AnalysisTurnCard key={turn.id} turn={turn} />) : <div className="empty">Run an analysis to start the React analysis thread.</div>}
      </section>
    </section>
  );
}

function CohortSelect({ label, value, cohorts, onChange, disabled = false }: { label: string; value: string; cohorts: SavedCohort[]; onChange: (value: string) => void; disabled?: boolean }) {
  return (
    <div>
      <label>{label}</label>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="">Full workspace</option>
        {cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}
      </select>
    </div>
  );
}

function AnalysisTurnCard({ turn }: { turn: AnalysisTurn }) {
  const data = turn.response?.data || {};
  const queued = data.execution === "queued";
  return (
    <article className={`analysis-turn ${turn.error ? "analysis-turn-error" : "analysis-turn-assistant"}`}>
      <div className="analysis-turn-label">{turn.itemName}</div>
      <div className="analysis-turn-body">
        <p><strong>Prompt:</strong> {turn.prompt}</p>
        {turn.error ? <div className="query-status">{turn.error}</div> : null}
        {turn.response?.reply ? <div className="react-analysis-reply">{turn.response.reply}</div> : null}
        {queued ? <div className="query-status">Queued job {String(data.job_code || data.job_id || "")}. Track it in Jobs.</div> : null}
        {Object.keys(data).length ? (
          <details className="query-section">
            <summary>Show analysis data</summary>
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </details>
        ) : null}
      </div>
    </article>
  );
}

function itemMatches(item: AnalysisCatalogItem, query: string, filter: string): boolean {
  if (filter === "available" && item.available === false) return false;
  if (filter === "blocked" && item.available !== false) return false;
  if (!["all", "available", "blocked"].includes(filter) && (item.category || "General") !== filter) return false;
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [
    item.name,
    item.description,
    item.guidance,
    item.category,
    item.runner_type,
    ...(item.tags || []),
  ].join(" ").toLowerCase().includes(needle);
}

function analysisBlocker({
  datasetId,
  selectedItem,
  prompt,
  compareMode,
  cohortAId,
  cohortBId,
  molecularDatasetName,
}: {
  datasetId: string;
  selectedItem: AnalysisCatalogItem | null;
  prompt: string;
  compareMode: boolean;
  cohortAId: string;
  cohortBId: string;
  molecularDatasetName: string;
}): string {
  if (!datasetId) return "Select and apply a workspace before running analysis.";
  if (!selectedItem) return "Select an analysis first.";
  if (selectedItem.available === false) return selectedItem.unavailable_reason || "This analysis is not ready.";
  if (!prompt.trim()) return "Enter an analysis prompt.";
  if (selectedItem.requires_molecular && !molecularDatasetName) return "Select one molecular dataset for this analysis.";
  if (compareMode && cohortAId && cohortAId === cohortBId) return "Cohort A and Cohort B must be different saved cohorts.";
  return "";
}

function cohortById(cohorts: SavedCohort[], id: string): SavedCohort | null {
  return cohorts.find((cohort) => cohort.id === id) || null;
}

function cohortIds(cohort: SavedCohort | null): string {
  if (!cohort) return "";
  const ids = cohort.sample_ids?.length ? cohort.sample_ids : cohort.patient_ids || [];
  return ids.join(",");
}

function molecularDatasetLabel(dataset: MolecularDatasetRecord): string {
  return dataset.name || dataset.dataset_name || "";
}

function runnerLabel(value: string | undefined): string {
  const normalized = String(value || "builtin").trim();
  return normalized === "builtin" ? "Built-in" : normalized;
}

function readinessText(item: AnalysisCatalogItem): string {
  if (item.default_compare_mode) return "Ready. Select Cohort A and Cohort B before running.";
  if (item.requires_molecular) return "Ready. Select one molecular dataset before running.";
  return "Ready to run.";
}
