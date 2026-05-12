import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatApiDetail } from "./api/client";
import type { ApiError, DatasetRecord } from "./api/types";
import { useAppStore } from "./store/appStore";
import { PhenoRanker } from "./features/pheno/PhenoRanker";
import { JobsDrawer } from "./features/jobs/JobsDrawer";
import { AnalysisTab } from "./features/analysis/AnalysisTab";
import { DashboardTab } from "./features/dashboard/DashboardTab";
import { QueryTab } from "./features/query/QueryTab";
import { DataAdminTab, UsersAdminTab } from "./features/admin/AdminTabs";

const tabs = [
  { id: "dashboard", label: "Dashboard", legacy: true },
  { id: "datasets", label: "Datasets", legacy: false },
  { id: "analysis", label: "Analysis", legacy: true },
  { id: "pheno", label: "Pheno-Ranker", legacy: false },
  { id: "query", label: "Query", legacy: true },
];

export function App() {
  const queryClient = useQueryClient();
  const activeTab = useAppStore((state) => state.activeTab);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const selectedDatasetIds = useAppStore((state) => state.selectedDatasetIds);
  const setSelectedDatasetIds = useAppStore((state) => state.setSelectedDatasetIds);
  const pendingDatasetIds = useAppStore((state) => state.pendingDatasetIds);
  const setPendingDatasetIds = useAppStore((state) => state.setPendingDatasetIds);
  const [loginError, setLoginError] = useState("");

  const authQuery = useQuery({
    queryKey: ["auth"],
    queryFn: api.auth,
  });

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: api.datasets,
    enabled: Boolean(authQuery.data?.authenticated),
  });

  useEffect(() => {
    const ids = datasetsQuery.data?.current_dataset_ids || [];
    if (ids.length) {
      setSelectedDatasetIds(ids);
      setPendingDatasetIds(ids);
    }
  }, [datasetsQuery.data?.current_dataset_ids, setPendingDatasetIds, setSelectedDatasetIds]);

  const selectDatasets = useMutation({
    mutationFn: api.selectDatasets,
    onSuccess: (payload) => {
      setSelectedDatasetIds(payload.current_dataset_ids || []);
      setPendingDatasetIds(payload.current_dataset_ids || []);
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
      void queryClient.invalidateQueries({ queryKey: ["pheno"] });
      void queryClient.invalidateQueries({ queryKey: ["saved-cohorts"] });
    },
  });

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["auth"] });
      void queryClient.clear();
    },
  });

  const selectedScopeId = useMemo(() => datasetScopeId(selectedDatasetIds), [selectedDatasetIds]);
  const pendingScopeId = useMemo(() => datasetScopeId(pendingDatasetIds), [pendingDatasetIds]);
  const selectedDatasets = useMemo(() => {
    const all = datasetsQuery.data?.datasets || [];
    const ids = new Set(selectedDatasetIds);
    return all.filter((dataset) => ids.has(dataset.dataset_id));
  }, [datasetsQuery.data?.datasets, selectedDatasetIds]);

  if (authQuery.isLoading) {
    return <CenteredStatus title="Loading React workspace" detail="Checking authentication state." />;
  }

  if (authQuery.error) {
    return <CenteredStatus title="Unable to open React workspace" detail={String((authQuery.error as Error).message || authQuery.error)} />;
  }

  if (!authQuery.data?.authenticated) {
    return <LoginGate onError={setLoginError} error={loginError} />;
  }

  return (
    <div className="react-app-shell">
      <header className="react-hero">
        <div>
          <div className="react-hero-label">Parallel React frontend</div>
          <h1>Patient Navigator</h1>
          <p>Pheno-Ranker is live here first. The legacy application remains available at <a href="/">/</a>.</p>
        </div>
        <div className="react-user-card">
          <strong>{authQuery.data.user?.display_name || authQuery.data.user?.username || "User"}</strong>
          <span>{authQuery.data.user?.role || "user"}</span>
          <JobsDrawer />
          {authQuery.data.enabled ? (
            <button type="button" className="query-chip" onClick={() => logout.mutate()} disabled={logout.isPending}>
              Sign out
            </button>
          ) : null}
        </div>
      </header>

      <nav className="tab-bar react-tab-bar" aria-label="React workspace sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`tab-btn${activeTab === tab.id ? " active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>

      <WorkspaceBar
        datasets={datasetsQuery.data?.datasets || []}
        activeDatasetIds={selectedDatasetIds}
        pendingDatasetIds={pendingDatasetIds}
        selectedDatasets={selectedDatasets}
        selectedScopeId={selectedScopeId}
        pendingScopeId={pendingScopeId}
        loading={datasetsQuery.isLoading || selectDatasets.isPending}
        error={datasetsQuery.error || selectDatasets.error}
        onSelectionChange={(ids) => setPendingDatasetIds(ids)}
        onApply={() => selectDatasets.mutate(pendingDatasetIds)}
      />

      <main>
        {activeTab === "dashboard" ? (
          <DashboardTab datasetId={selectedScopeId} selectedDatasets={selectedDatasets} />
        ) : activeTab === "pheno" ? (
          <PhenoRanker datasetId={selectedScopeId} selectedDatasets={selectedDatasets} />
        ) : activeTab === "analysis" ? (
          <AnalysisTab datasetId={selectedScopeId} selectedDatasets={selectedDatasets} />
        ) : activeTab === "query" ? (
          <QueryTab datasetId={selectedScopeId} selectedDatasets={selectedDatasets} />
        ) : activeTab === "data" ? (
          <DataAdminTab currentUser={authQuery.data.user} />
        ) : activeTab === "users" ? (
          <UsersAdminTab currentUser={authQuery.data.user} />
        ) : activeTab === "datasets" ? (
          <DatasetMatrix datasets={datasetsQuery.data?.datasets || []} activeDatasetIds={selectedDatasetIds} pendingDatasetIds={pendingDatasetIds} />
        ) : (
          <LegacyPlaceholder label={tabs.find((tab) => tab.id === activeTab)?.label || "This tab"} />
        )}
      </main>
    </div>
  );
}

function LoginGate({ error, onError }: { error: string; onError: (error: string) => void }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: () => {
      onError("");
      void queryClient.invalidateQueries({ queryKey: ["auth"] });
    },
    onError: (err) => onError((err as Error).message || "Login failed."),
  });

  return (
    <div className="auth-gate react-auth-gate">
      <div className="auth-gate-card">
        <div className="auth-gate-copy">
          <div className="auth-gate-heading">
            <img className="auth-gate-heading-logo" src="/static/img/patient-navigator-logo.png" alt="Patient Navigator logo" />
            <h1>Patient Navigator</h1>
          </div>
          <p>Authentication is required before opening the React workspace.</p>
        </div>
        <form
          className="auth-gate-form"
          onSubmit={(event) => {
            event.preventDefault();
            login.mutate();
          }}
        >
          <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" autoComplete="username" />
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" autoComplete="current-password" />
          <button type="submit" disabled={login.isPending}>
            <span>{login.isPending ? "Signing in..." : "Sign in"}</span>
          </button>
        </form>
        {error ? <div className="query-status">{error}</div> : null}
      </div>
    </div>
  );
}

function WorkspaceBar({
  datasets,
  activeDatasetIds,
  pendingDatasetIds,
  selectedDatasets,
  selectedScopeId,
  pendingScopeId,
  loading,
  error,
  onSelectionChange,
  onApply,
}: {
  datasets: DatasetRecord[];
  activeDatasetIds: string[];
  pendingDatasetIds: string[];
  selectedDatasets: DatasetRecord[];
  selectedScopeId: string;
  pendingScopeId: string;
  loading: boolean;
  error: unknown;
  onSelectionChange: (ids: string[]) => void;
  onApply: () => void;
}) {
  function toggleDataset(id: string) {
    if (pendingDatasetIds.includes(id)) {
      const next = pendingDatasetIds.filter((item) => item !== id);
      onSelectionChange(next.length ? next : pendingDatasetIds);
      return;
    }
    onSelectionChange([...pendingDatasetIds, id]);
  }

  const hasPendingChange = datasetScopeId(activeDatasetIds) !== datasetScopeId(pendingDatasetIds);
  const blocker = pendingStoreBlocker(datasets, pendingDatasetIds);

  return (
    <section className="react-workspace-bar">
      <div className="react-workspace-summary">
        <span>Active workspace</span>
        <strong>{selectedDatasets.map((dataset) => dataset.name || dataset.dataset_id).join(", ") || selectedScopeId || "No dataset selected"}</strong>
        {hasPendingChange ? <small>Pending: {pendingScopeId}</small> : null}
      </div>
      <div className="react-dataset-pills">
        {datasets.map((dataset) => (
          <label key={dataset.dataset_id} className={`query-chip react-check-chip${pendingDatasetIds.includes(dataset.dataset_id) ? " active" : ""}${activeDatasetIds.includes(dataset.dataset_id) ? " is-current" : ""}`}>
            <input type="checkbox" checked={pendingDatasetIds.includes(dataset.dataset_id)} onChange={() => toggleDataset(dataset.dataset_id)} />
            <span>{dataset.name || dataset.dataset_id}</span>
            <DatasetStoreBadge dataset={dataset} />
          </label>
        ))}
      </div>
      <button type="button" onClick={onApply} disabled={loading || pendingDatasetIds.length === 0 || Boolean(blocker)}>
        <span>{loading ? "Applying..." : hasPendingChange ? "Apply workspace" : "Reload workspace"}</span>
      </button>
      {blocker ? <div className="query-status">{blocker}</div> : null}
      {error ? <div className="query-status">{formatApiDetail((error as ApiError).detail) || (error as Error).message}</div> : null}
    </section>
  );
}

function DatasetMatrix({ datasets, activeDatasetIds, pendingDatasetIds }: { datasets: DatasetRecord[]; activeDatasetIds: string[]; pendingDatasetIds: string[] }) {
  return (
    <section className="react-panel">
      <div className="section-heading">
        <div>
          <label>Datasets</label>
          <h2>Authorized workspace datasets</h2>
        </div>
      </div>
      <div className="dataset-grid">
        {datasets.map((dataset) => (
          <article key={dataset.dataset_id} className={`dataset-card${activeDatasetIds.includes(dataset.dataset_id) ? " selected" : ""}${pendingDatasetIds.includes(dataset.dataset_id) ? " pending" : ""}`}>
            <div className="dataset-card-title">
              <strong>{dataset.name || dataset.dataset_id}</strong>
              <span>{dataset.dataset_id}</span>
            </div>
            <p>{dataset.content_summary || dataset.description || "No content summary available."}</p>
            <div className="dataset-card-tags">
              <DatasetStoreBadge dataset={dataset} />
              <span className="query-chip badge">{dataset.query_granularity_ceiling === "detailed" ? "Detailed" : "Summary"}</span>
              <span className="query-chip badge">{dataset.ai_provider_access || "AI default"}</span>
            </div>
            <div className="dataset-card-meta">
              <span>{dataset.content_counts?.patients ?? "?"} patients</span>
              <span>{dataset.content_counts?.timepoints ?? "?"} timepoints</span>
              <span>{dataset.content_counts?.molecular_datasets ?? 0} molecular</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function LegacyPlaceholder({ label }: { label: string }) {
  return (
    <section className="react-panel">
      <div className="empty">
        {label} still lives in the legacy frontend during the first migration slice. Open <a href="/">the current app</a> for that workflow.
      </div>
    </section>
  );
}

function CenteredStatus({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="react-centered-status">
      <h1>{title}</h1>
      <p>{detail}</p>
    </div>
  );
}

function datasetScopeId(ids: string[]): string {
  const clean = ids.map((id) => id.trim()).filter(Boolean);
  if (!clean.length) return "";
  return clean.length === 1 ? clean[0] : clean.sort().join("+");
}

function normalizedStoreStatus(dataset: DatasetRecord) {
  const status = dataset.query_store_status || {};
  const label = String(status.status || status.state || "not_built").trim().toLowerCase();
  return {
    ready: Boolean(status.ready) || label === "ready" || label === "current",
    label,
    detail: String(status.last_error || status.message || "").trim(),
  };
}

function DatasetStoreBadge({ dataset }: { dataset: DatasetRecord }) {
  const status = normalizedStoreStatus(dataset);
  return (
    <span className={`query-chip badge react-store-badge ${status.ready ? "is-ready" : "is-blocked"}`} title={status.detail}>
      {status.ready ? "Prepared" : status.label.replaceAll("_", " ")}
    </span>
  );
}

function pendingStoreBlocker(datasets: DatasetRecord[], pendingIds: string[]): string {
  const selected = new Set(pendingIds);
  const blocked = datasets.find((dataset) => selected.has(dataset.dataset_id) && !normalizedStoreStatus(dataset).ready);
  if (!blocked) return "";
  const status = normalizedStoreStatus(blocked);
  const label = blocked.name || blocked.dataset_id;
  return `Cannot apply workspace: dataset store for "${label}" is ${status.label.replaceAll("_", " ")}. Prepare it in Data Admin first.`;
}
