import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatApiDetail } from "../../api/client";
import type { ApiError, DatasetRecord, JobRecord, PhenoFile, PhenoPlanResponse, PhenoRunResponse, SavedCohort } from "../../api/types";
import { useAppStore } from "../../store/appStore";
import { applyPlanToForm, defaultPhenoForm, findResultFile, formToRunRequest, formatBytes, splitTerms, type PhenoFormState } from "../../utils/pheno";
import { PhenoGraphPreview } from "./PhenoGraphPreview";
import { PhenoTextPreview } from "./PhenoTextPreview";

export function PhenoRanker({ datasetId, selectedDatasets }: { datasetId: string; selectedDatasets: DatasetRecord[] }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PhenoFormState>(defaultPhenoForm);
  const [planPayload, setPlanPayload] = useState<PhenoPlanResponse | null>(null);
  const [runPayload, setRunPayload] = useState<PhenoRunResponse | null>(null);
  const [status, setStatus] = useState("Describe a run, preview the plan, then run Pheno-Ranker.");
  const selectedSavedCohortIds = useAppStore((state) => state.selectedSavedCohortIds);
  const setSelectedSavedCohortIds = useAppStore((state) => state.setSelectedSavedCohortIds);

  const savedCohorts = useQuery({
    queryKey: ["saved-cohorts", datasetId],
    queryFn: api.savedCohorts,
    enabled: Boolean(datasetId),
  });

  const patientIds = useQuery({
    queryKey: ["pheno", "patient-ids", datasetId],
    queryFn: () => api.phenoPatientIds(datasetId),
    enabled: Boolean(datasetId),
  });

  const jobs = useQuery({
    queryKey: ["jobs", "pheno"],
    queryFn: api.jobs,
    refetchInterval: (query) => {
      const active = query.state.data?.jobs?.some((job) => job.feature === "pheno" && ["queued", "running"].includes(job.status));
      return active ? 2500 : false;
    },
  });

  useEffect(() => {
    if (!jobs.data?.jobs?.length) return;
    const completed = jobs.data.jobs.find((job) => job.feature === "pheno" && job.status === "completed" && job.result_available);
    if (completed && !runPayload) {
      void api.job(completed.job_id).then((detail) => {
        if (detail.result_payload) {
          setRunPayload(detail.result_payload);
          setStatus(`Loaded completed Pheno-Ranker job ${detail.job_code || detail.job_id}.`);
        }
      }).catch(() => {
        setStatus(`Completed Pheno-Ranker job ${completed.job_code || completed.job_id} is available in the jobs drawer.`);
      });
    }
  }, [jobs.data?.jobs, runPayload]);

  const plan = useMutation({
    mutationFn: () => api.phenoPlan(form.prompt, datasetId, form.selectedPatientIds),
    onSuccess: (payload) => {
      setPlanPayload(payload);
      if (payload.plan) {
        setForm((current) => applyPlanToForm(current, payload.plan || {}));
        setStatus("Plan ready. Review the settings, then run Pheno-Ranker.");
      } else {
        setStatus("Planner returned guidance but no runnable plan.");
      }
    },
    onError: (error) => setStatus(formatError(error)),
  });

  const run = useMutation({
    mutationFn: () => api.phenoRun(formToRunRequest(form, datasetId, selectedSavedCohortIds)),
    onSuccess: (payload) => {
      setRunPayload(payload);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      if (payload.data?.execution === "queued") {
        setStatus(payload.reply || `Queued Pheno-Ranker job ${payload.job_code || payload.job_id}.`);
      } else {
        setStatus(`Completed ${payload.mode || form.mode} run ${payload.job_id || ""}. ${payload.scope_expansion_note || ""}`.trim());
      }
    },
    onError: (error) => setStatus(formatError(error)),
  });

  const activeJob = useMemo(() => {
    return jobs.data?.jobs?.find((job) => job.feature === "pheno" && ["queued", "running"].includes(job.status)) || null;
  }, [jobs.data?.jobs]);

  const patientOptions = patientIds.data?.record_ids?.slice(0, 25) || [];
  const selectedCohorts = (savedCohorts.data?.cohorts || []).filter((cohort) => selectedSavedCohortIds.includes(cohort.id));
  const blockingIssue = getBlockingIssue(form, datasetId, selectedSavedCohortIds);
  const files = runPayload?.files || [];

  return (
    <section className="react-pheno-layout">
      <div className="section-heading">
        <div>
          <label>Pheno-Ranker</label>
          <h2>React Pheno-Ranker workflow</h2>
          <p className="section-note">
            Scope: {selectedDatasets.map((dataset) => dataset.name || dataset.dataset_id).join(", ") || datasetId || "none"}.
            {patientIds.data ? ` ${patientIds.data.record_ids.length} reference records available.` : ""}
          </p>
        </div>
        <a className="query-chip" href="/#phenoTab">Open legacy Pheno-Ranker</a>
      </div>

      <div className="pheno-background-job-banner saved-cohort-inline-status">
        {activeJob ? `Background Pheno-Ranker run in progress: ${activeJob.job_code || activeJob.job_id}.` : status}
      </div>

      <div className="react-pheno-grid">
        <form
          className="pheno-result-card react-pheno-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!blockingIssue) run.mutate();
          }}
        >
          <label htmlFor="reactPhenoPrompt">Describe run</label>
          <textarea
            id="reactPhenoPrompt"
            rows={4}
            value={form.prompt}
            onChange={(event) => {
              setFormField(setForm, "prompt", event.target.value);
              setPlanPayload(null);
            }}
          />

          <div className="query-examples">
            {[
              "Compare all patients by phenotypicFeatures and diseases excluding id",
              "Compare all patients by disease using jaccard and generate graph",
              "Find closest matches to SYN005:week_0 by disease",
            ].map((example) => (
              <button key={example} type="button" className="query-chip query-chip-deterministic" onClick={() => setFormField(setForm, "prompt", example)}>
                {example}
              </button>
            ))}
          </div>

          <div className="pheno-actions pheno-actions-primary">
            <button type="button" className="query-chip" onClick={() => plan.mutate()} disabled={!datasetId || plan.isPending || !form.prompt.trim()}>
              <span>{plan.isPending ? "Previewing..." : "Preview plan"}</span>
            </button>
            <button type="submit" disabled={!datasetId || run.isPending || Boolean(blockingIssue)}>
              <span>{run.isPending ? "Running..." : "Run Pheno-Ranker"}</span>
            </button>
          </div>
          {blockingIssue ? <div className="query-status">{blockingIssue}</div> : null}

          <details className="query-section pheno-advanced-options" open>
            <summary className="pheno-advanced-summary">
              <span>Advanced options</span>
            </summary>
            <div className="pheno-advanced-grid">
              <SelectField label="Action" value={form.action} onChange={(value) => setFormField(setForm, "action", value)} options={[["compare", "Compare"], ["extract", "Extract"]]} />
              <SelectField label="Mode" value={form.mode} onChange={(value) => setFormField(setForm, "mode", value)} options={[["cohort", "Cohort"], ["patient", "Patient"]]} />
              <InputField label="Patient ID" value={form.patientId} onChange={(value) => setFormField(setForm, "patientId", value)} list="reactPhenoPatientIds" disabled={form.mode !== "patient"} />
              <datalist id="reactPhenoPatientIds">
                {patientOptions.map((id) => <option key={id} value={id} />)}
              </datalist>
              <InputField label="Scope IDs" value={form.selectedPatientIds} onChange={(value) => setFormField(setForm, "selectedPatientIds", value)} disabled={selectedSavedCohortIds.length > 0} />
              <InputField label="Include terms" value={form.includeTerms} onChange={(value) => setFormField(setForm, "includeTerms", value)} />
              <InputField label="Exclude terms" value={form.excludeTerms} onChange={(value) => setFormField(setForm, "excludeTerms", value)} />
              <SelectField label="Cohort metric" value={form.similarityMetricCohort} onChange={(value) => setFormField(setForm, "similarityMetricCohort", value)} options={[["hamming", "Hamming"], ["jaccard", "Jaccard"]]} />
              <SelectField label="Sort by" value={form.sortBy} onChange={(value) => setFormField(setForm, "sortBy", value)} options={[["", "Default"], ["hamming", "Hamming"], ["jaccard", "Jaccard"]]} />
              <InputField label="Max output rows" value={String(form.maxOut)} onChange={(value) => setFormField(setForm, "maxOut", Number(value || 10))} type="number" />
              <InputField label="Graph min edge weight" value={form.graphMinWeight} onChange={(value) => setFormField(setForm, "graphMinWeight", value)} type="number" step="0.001" />
              <InputField label="Graph max edge weight" value={form.graphMaxWeight} onChange={(value) => setFormField(setForm, "graphMaxWeight", value)} type="number" step="0.001" />
            </div>
            <div className="pheno-checks">
              <CheckboxField label="Generate alignment files" checked={form.align} onChange={(value) => setFormField(setForm, "align", value)} disabled={form.mode !== "patient"} />
              <CheckboxField label="Render heatmap" checked={form.renderHeatmap} onChange={(value) => setFormField(setForm, "renderHeatmap", value)} />
              <CheckboxField label="Render MDS" checked={form.renderMds} onChange={(value) => setFormField(setForm, "renderMds", value)} />
              <CheckboxField label="Render graph" checked={form.renderGraph} onChange={(value) => setFormField(setForm, "renderGraph", value)} />
            </div>
          </details>

          <SavedCohortPicker
            cohorts={savedCohorts.data?.cohorts || []}
            selected={selectedSavedCohortIds}
            onChange={setSelectedSavedCohortIds}
          />
        </form>

        <aside className="pheno-result-card react-pheno-plan-card">
          <h3>Current plan</h3>
          <pre>{JSON.stringify(formToRunRequest(form, datasetId, selectedSavedCohortIds), null, 2)}</pre>
          {planPayload?.reasoning?.length ? (
            <div className="react-reasoning">
              <h4>Planner reasoning</h4>
              <ul>
                {planPayload.reasoning.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
              </ul>
            </div>
          ) : null}
          {selectedCohorts.length ? (
            <div className="query-meta">
              Saved cohorts: {selectedCohorts.map((cohort) => cohort.name).join(", ")}
            </div>
          ) : null}
        </aside>
      </div>

      <PhenoResult payload={runPayload} files={files} activeJob={activeJob} />
    </section>
  );
}

function PhenoResult({ payload, files, activeJob }: { payload: PhenoRunResponse | null; files: PhenoFile[]; activeJob: JobRecord | null }) {
  const previewFile = findResultFile(files, ["rank.txt", "matrix.txt", "reference.selected.json"]);
  const graphFile = findResultFile(files, ["graph.json"]);
  const mdsFile = findResultFile(files, ["mds_points.tsv"]);

  if (!payload && !activeJob) {
    return <div className="pheno-result-card pheno-empty-state">Preview a plan or run Pheno-Ranker to reveal outputs, plots, and diagnostics.</div>;
  }

  if (activeJob && !payload) {
    return <div className="pheno-result-card pheno-empty-state">Background job is {activeJob.status}. Results will appear when the job completes.</div>;
  }

  return (
    <div className="react-pheno-results">
      <section className="pheno-result-card">
        <h3>Output files</h3>
        <div className="pheno-files">
          {files.length ? files.map((file) => (
            <a key={file.name} className="query-chip" href={file.url} target="_blank" rel="noreferrer">
              {file.name}{file.size ? ` (${formatBytes(file.size)})` : ""}
            </a>
          )) : <div className="empty">No output files available.</div>}
        </div>
      </section>

      <section className="pheno-result-card pheno-result-card-full">
        <h3>Output preview</h3>
        {previewFile ? <PhenoTextPreview file={previewFile} /> : <div className="empty">No text preview available.</div>}
      </section>

      {mdsFile ? (
        <section className="pheno-result-card pheno-result-card-full">
          <h3>MDS coordinates</h3>
          <PhenoTextPreview file={mdsFile} maxLines={12} />
        </section>
      ) : null}

      {graphFile ? (
        <section className="pheno-result-card pheno-result-card-full">
          <h3>Graph preview</h3>
          <PhenoGraphPreview file={graphFile} metric={payload?.similarity_metric_cohort || ""} />
        </section>
      ) : null}

      <section className="pheno-result-card pheno-result-card-full">
        <h3>Command</h3>
        <pre>{payload?.command || "No command metadata."}</pre>
      </section>

      <section className="pheno-result-card pheno-result-card-full">
        <h3>Logs</h3>
        <pre>{[payload?.stderr, ...(payload?.plots || []).map((plot) => `${plot.script || "plot"}\nstdout:\n${plot.stdout || ""}\nstderr:\n${plot.stderr || ""}`)].filter(Boolean).join("\n\n") || "No diagnostic logs."}</pre>
      </section>
    </div>
  );
}

function SavedCohortPicker({ cohorts, selected, onChange }: { cohorts: SavedCohort[]; selected: string[]; onChange: (ids: string[]) => void }) {
  if (!cohorts.length) {
    return <div className="empty">No saved cohorts available for this workspace.</div>;
  }
  return (
    <details className="pheno-setup-saved-cohorts">
      <summary className="pheno-setup-saved-cohorts-header">Saved cohorts</summary>
      <div className="react-dataset-pills">
        {cohorts.map((cohort) => (
          <label key={cohort.id} className={`query-chip react-check-chip${selected.includes(cohort.id) ? " active" : ""}`}>
            <input
              type="checkbox"
              checked={selected.includes(cohort.id)}
              onChange={() => onChange(selected.includes(cohort.id) ? selected.filter((id) => id !== cohort.id) : [...selected, cohort.id])}
            />
            <span>{cohort.name}</span>
          </label>
        ))}
      </div>
    </details>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void }) {
  return (
    <div>
      <label>{label}</label>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </div>
  );
}

function InputField({ label, value, onChange, type = "text", disabled = false, list, step }: { label: string; value: string; onChange: (value: string) => void; type?: string; disabled?: boolean; list?: string; step?: string }) {
  return (
    <div>
      <label>{label}</label>
      <input value={value} onChange={(event) => onChange(event.target.value)} type={type} disabled={disabled} list={list} step={step} />
    </div>
  );
}

function CheckboxField({ label, checked, onChange, disabled = false }: { label: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <label className="react-checkbox">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function setFormField<K extends keyof PhenoFormState>(
  setter: React.Dispatch<React.SetStateAction<PhenoFormState>>,
  key: K,
  value: PhenoFormState[K],
) {
  setter((current) => ({ ...current, [key]: value }));
}

function getBlockingIssue(form: PhenoFormState, datasetId: string, selectedSavedCohortIds: string[]): string {
  if (!datasetId) return "Select and apply at least one dataset before running Pheno-Ranker.";
  if (!form.prompt.trim()) return "Describe a Pheno-Ranker request first.";
  if (splitTerms(form.includeTerms).length && splitTerms(form.excludeTerms).length) {
    return "Pheno-Ranker cannot combine include and exclude filters in the same run. Clear one field.";
  }
  if (form.mode === "patient" && !form.patientId.trim() && !form.selectedPatientIds.trim() && !selectedSavedCohortIds.length) {
    return "Patient mode needs one explicit Patient ID or one selected scope ID.";
  }
  return "";
}

function formatError(error: unknown): string {
  const apiError = error as ApiError;
  return formatApiDetail(apiError.detail) || (error as Error).message || "Request failed.";
}
