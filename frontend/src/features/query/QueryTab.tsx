import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, formatApiDetail } from "../../api/client";
import type { ApiError, DatasetRecord, JsonValue, QueryRunResponse } from "../../api/types";

type QueryTurn = {
  id: string;
  prompt: string;
  response: QueryRunResponse | null;
  error?: string;
};

type ScopedContext = {
  patientIds: string[];
  recordIds: string[];
  idType: string;
};

const examples = [
  "Tell me the list of patients in the workspace",
  "List diseases in this workspace",
  "List medications in this workspace",
  "How many timepoints are in this workspace?",
  "What happened to this workspace over time?",
];

export function QueryTab({ datasetId, selectedDatasets }: { datasetId: string; selectedDatasets: DatasetRecord[] }) {
  const [prompt, setPrompt] = useState("");
  const [queryMode, setQueryMode] = useState("auto");
  const [granularityMode, setGranularityMode] = useState("detailed");
  const [followMemory, setFollowMemory] = useState(false);
  const [scopedContext, setScopedContext] = useState<ScopedContext>({ patientIds: [], recordIds: [], idType: "patient" });
  const [turns, setTurns] = useState<QueryTurn[]>([]);

  const run = useMutation({
    mutationFn: () => api.queryRun({
      q: prompt.trim(),
      dataset_id: datasetId,
      query_mode: queryMode,
      granularity_mode: granularityMode,
      history: turns.slice(-6).flatMap((turn) => [
        { role: "user", content: turn.prompt },
        { role: "assistant", content: turn.response?.reply || "" },
      ]),
      scoped_patient_ids: followMemory ? scopedContext.patientIds : [],
      scoped_record_ids: followMemory ? scopedContext.recordIds : [],
      scoped_id_type: scopedContext.idType,
    }),
    onSuccess: (response) => {
      const nextContext = contextFromQueryResponse(response);
      if (nextContext.patientIds.length || nextContext.recordIds.length) {
        setScopedContext(nextContext);
      }
      setTurns((current) => [...current, { id: `${Date.now()}`, prompt: prompt.trim(), response }]);
      setPrompt("");
    },
    onError: (error) => {
      setTurns((current) => [
        ...current,
        {
          id: `${Date.now()}`,
          prompt: prompt.trim(),
          response: null,
          error: formatApiDetail((error as ApiError).detail) || (error as Error).message,
        },
      ]);
    },
  });

  const blocker = !datasetId ? "Select and apply a workspace before querying." : !prompt.trim() ? "Enter a query first." : "";
  const scopedLabel = useMemo(() => {
    const total = scopedContext.recordIds.length || scopedContext.patientIds.length;
    return total ? `${total} ${scopedContext.recordIds.length ? "records" : "patients"}` : "Full workspace";
  }, [scopedContext]);

  return (
    <section className="react-query-layout">
      <div className="section-heading">
        <div>
          <label>Query</label>
          <h2>React workspace query</h2>
          <p className="section-note">
            Workspace: {selectedDatasets.map((dataset) => dataset.name || dataset.dataset_id).join(", ") || datasetId || "none"}.
          </p>
        </div>
        <a className="query-chip" href="/#queryTab">Open legacy Query</a>
      </div>

      <section className="pheno-result-card react-query-console">
        <div className="query-examples">
          {examples.map((example) => (
            <button key={example} type="button" className="query-chip query-chip-deterministic" onClick={() => setPrompt(example)}>
              {example}
            </button>
          ))}
        </div>
        <textarea rows={4} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask a workspace question" />
        <div className="react-query-controls">
          <label>
            <span>Mode</span>
            <select value={queryMode} onChange={(event) => setQueryMode(event.target.value)}>
              <option value="auto">Auto</option>
              <option value="planner_only">Planner only</option>
            </select>
          </label>
          <label>
            <span>Disclosure</span>
            <select value={granularityMode} onChange={(event) => setGranularityMode(event.target.value)}>
              <option value="detailed">Detailed</option>
              <option value="summary">Summary</option>
            </select>
          </label>
          <label className="react-checkbox">
            <input type="checkbox" checked={followMemory} onChange={(event) => setFollowMemory(event.target.checked)} disabled={!scopedContext.patientIds.length && !scopedContext.recordIds.length} />
            <span>Use previous scope: {scopedLabel}</span>
          </label>
          <button type="button" disabled={Boolean(blocker) || run.isPending} onClick={() => run.mutate()}>
            <span>{run.isPending ? "Asking..." : "Ask"}</span>
          </button>
        </div>
        {blocker ? <div className="query-status">{blocker}</div> : null}
      </section>

      <section className="analysis-thread react-query-thread">
        {turns.length ? turns.map((turn) => (
          <QueryTurnCard key={turn.id} turn={turn} onFollowup={(value) => setPrompt(value)} />
        )) : <div className="empty">Ask a query to start the React query thread.</div>}
      </section>
    </section>
  );
}

function QueryTurnCard({ turn, onFollowup }: { turn: QueryTurn; onFollowup: (value: string) => void }) {
  return (
    <>
      <article className="analysis-turn analysis-turn-user">
        <div className="analysis-turn-label">You</div>
        <div className="analysis-turn-body"><p>{turn.prompt}</p></div>
      </article>
      <article className={`analysis-turn ${turn.error ? "analysis-turn-error" : "analysis-turn-assistant"}`}>
        <div className="analysis-turn-label">Query</div>
        <div className="analysis-turn-meta">
          {turn.response?.intent ? <span className="query-chip badge">{turn.response.intent}</span> : null}
          {typeof turn.response?.data?.granularity_applied === "string" ? <span className="query-chip badge">Disclosure: {turn.response.data.granularity_applied}</span> : null}
        </div>
        <div className="analysis-turn-body">
          {turn.error ? <div className="query-status">{turn.error}</div> : null}
          {turn.response?.reply ? <div className="react-query-reply">{turn.response.reply}</div> : null}
          {turn.response?.data ? <StructuredQueryData data={turn.response.data} /> : null}
          {turn.response?.followups?.length ? (
            <div className="query-followups">
              {turn.response.followups.map((item) => (
                <button key={item} type="button" className="query-chip" onClick={() => onFollowup(item)}>
                  {item}
                </button>
              ))}
            </div>
          ) : null}
          {turn.response?.data ? (
            <details className="query-section">
              <summary>Show query data</summary>
              <pre>{JSON.stringify(turn.response.data, null, 2)}</pre>
            </details>
          ) : null}
        </div>
      </article>
    </>
  );
}

function StructuredQueryData({ data }: { data: Record<string, JsonValue> }) {
  if (Array.isArray(data.patients) && data.patients.length) {
    return <SimpleTable rows={data.patients.slice(0, 80) as Array<Record<string, JsonValue>>} columns={["patient_id", "sex", "visit_count", "medication_count"]} />;
  }
  if (Array.isArray(data.diseases) && data.diseases.length) {
    return <SimpleTable rows={data.diseases.slice(0, 80) as Array<Record<string, JsonValue>>} columns={["disease", "patient_count"]} />;
  }
  if (Array.isArray(data.medications) && data.medications.length) {
    return <SimpleTable rows={data.medications.slice(0, 80) as Array<Record<string, JsonValue>>} columns={["medication", "patient_count"]} />;
  }
  if (Array.isArray(data.patient_ids) && data.patient_ids.length) {
    return <div className="query-meta">Matched IDs: {(data.patient_ids as string[]).slice(0, 30).join(", ")}{(data.patient_ids as string[]).length > 30 ? "..." : ""}</div>;
  }
  return null;
}

function SimpleTable({ rows, columns }: { rows: Array<Record<string, JsonValue>>; columns: string[] }) {
  return (
    <table>
      <thead>
        <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function contextFromQueryResponse(response: QueryRunResponse): ScopedContext {
  const data = response.data || {};
  const patientIds = arrayOfStrings(data.patient_ids);
  const recordIds = arrayOfStrings(data.record_ids).length ? arrayOfStrings(data.record_ids) : arrayOfStrings(data.sample_ids);
  return {
    patientIds,
    recordIds,
    idType: recordIds.length ? "sample" : "patient",
  };
}

function arrayOfStrings(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean) : [];
}
