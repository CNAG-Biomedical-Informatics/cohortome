import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatApiDetail } from "../../api/client";
import type { ApiError, AuthUser, DatasetRecord } from "../../api/types";

export function DataAdminTab({ currentUser }: { currentUser?: AuthUser }) {
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const isAdmin = currentUser?.role === "admin";

  if (!isAdmin) {
    return <AdminShell title="Data Admin"><div className="empty">Dataset administration is only visible to administrators.</div></AdminShell>;
  }

  return (
    <AdminShell title="Data Admin">
      {datasets.error ? <div className="query-status">{(datasets.error as Error).message}</div> : null}
      <div className="react-admin-grid">
        {(datasets.data?.datasets || []).map((dataset) => (
          <DatasetAdminCard
            key={dataset.dataset_id}
            dataset={dataset}
            onSaved={() => {
              void queryClient.invalidateQueries({ queryKey: ["datasets"] });
            }}
          />
        ))}
      </div>
    </AdminShell>
  );
}

export function UsersAdminTab({ currentUser }: { currentUser?: AuthUser }) {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: api.users, enabled: currentUser?.role === "admin" });
  const [status, setStatus] = useState("");
  const [createForm, setCreateForm] = useState({ username: "", password: "", display_name: "", role: "user", groups: "", enabled: true });
  const isAdmin = currentUser?.role === "admin";

  const create = useMutation({
    mutationFn: () => api.createUser({ ...createForm, groups: splitCsv(createForm.groups) }),
    onSuccess: (user) => {
      setStatus(`User ${user.username} created.`);
      setCreateForm({ username: "", password: "", display_name: "", role: "user", groups: "", enabled: true });
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: (error) => setStatus(formatApiDetail((error as ApiError).detail) || (error as Error).message),
  });

  if (!isAdmin) {
    return <AdminShell title="Users"><div className="empty">User administration is only visible to administrators.</div></AdminShell>;
  }

  return (
    <AdminShell title="Users">
      <div className="query-status">{status || (users.data ? `${users.data.users.length} users configured.` : "Loading users...")}</div>
      <section className="pheno-result-card react-admin-form">
        <h3>Create user</h3>
        <div className="pheno-advanced-grid">
          <Input label="Username" value={createForm.username} onChange={(value) => setCreateForm((current) => ({ ...current, username: value }))} />
          <Input label="Display name" value={createForm.display_name} onChange={(value) => setCreateForm((current) => ({ ...current, display_name: value }))} />
          <Input label="Password" type="password" value={createForm.password} onChange={(value) => setCreateForm((current) => ({ ...current, password: value }))} />
          <Select label="Role" value={createForm.role} onChange={(value) => setCreateForm((current) => ({ ...current, role: value }))} options={[["user", "User"], ["admin", "Admin"]]} />
          <Input label="Groups" value={createForm.groups} onChange={(value) => setCreateForm((current) => ({ ...current, groups: value }))} />
          <label className="react-checkbox">
            <input type="checkbox" checked={createForm.enabled} onChange={(event) => setCreateForm((current) => ({ ...current, enabled: event.target.checked }))} />
            <span>Enabled</span>
          </label>
        </div>
        <button type="button" disabled={create.isPending || !createForm.username || !createForm.password} onClick={() => create.mutate()}>
          <span>{create.isPending ? "Creating..." : "Create user"}</span>
        </button>
      </section>
      <div className="react-admin-grid">
        {(users.data?.users || []).map((user) => (
          <UserAdminCard
            key={user.username}
            user={user}
            currentUsername={currentUser?.username || ""}
            onStatus={setStatus}
            onSaved={() => {
              void queryClient.invalidateQueries({ queryKey: ["users"] });
              void queryClient.invalidateQueries({ queryKey: ["datasets"] });
            }}
          />
        ))}
      </div>
    </AdminShell>
  );
}

function DatasetAdminCard({ dataset, onSaved }: { dataset: DatasetRecord; onSaved: () => void }) {
  const [form, setForm] = useState(datasetForm(dataset));
  const [status, setStatus] = useState("");

  useEffect(() => setForm(datasetForm(dataset)), [dataset]);

  const save = useMutation({
    mutationFn: () => api.updateDataset(dataset.dataset_id, {
      name: form.name,
      description: form.description,
      visibility: form.visibility,
      allowed_users: splitCsv(form.allowedUsers),
      allowed_groups: splitCsv(form.allowedGroups),
      query_granularity_ceiling: form.queryGranularity,
      ai_provider_access: effectiveAiAccess(form.visibility, form.aiProviderAccess),
      enabled: form.enabled,
    } as Partial<DatasetRecord>),
    onSuccess: () => {
      setStatus("Settings saved.");
      onSaved();
    },
    onError: (error) => setStatus(formatApiDetail((error as ApiError).detail) || (error as Error).message),
  });

  const prepare = useMutation({
    mutationFn: () => api.prepareDatasetStore(dataset.dataset_id),
    onSuccess: () => {
      setStatus("DuckDB store prepared.");
      onSaved();
    },
    onError: (error) => setStatus(formatApiDetail((error as ApiError).detail) || (error as Error).message),
  });

  return (
    <article className="dataset-card react-admin-card">
      <div className="dataset-card-title">
        <strong>{dataset.name || dataset.dataset_id}</strong>
        <span>{dataset.dataset_id}</span>
      </div>
      <div className="pheno-advanced-grid">
        <Input label="Name" value={form.name} onChange={(value) => setForm((current) => ({ ...current, name: value }))} />
        <Select label="Visibility" value={form.visibility} onChange={(value) => setForm((current) => ({ ...current, visibility: value }))} options={[["all_authenticated", "All authenticated"], ["restricted", "Restricted"], ["admin_only", "Admin only"]]} />
        <Input label="Allowed groups" value={form.allowedGroups} onChange={(value) => setForm((current) => ({ ...current, allowedGroups: value }))} />
        <Input label="Allowed users" value={form.allowedUsers} onChange={(value) => setForm((current) => ({ ...current, allowedUsers: value }))} />
        <Select label="Query detail" value={form.queryGranularity} onChange={(value) => setForm((current) => ({ ...current, queryGranularity: value }))} options={[["summary", "Summary only"], ["detailed", "Detailed allowed"]]} />
        <Select label="AI provider" value={form.aiProviderAccess} onChange={(value) => setForm((current) => ({ ...current, aiProviderAccess: value }))} options={[["detailed_allowed", "Detailed allowed"], ["safe_summary", "Safe summary"], ["blocked", "Blocked"]]} />
      </div>
      <label>Description</label>
      <textarea rows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
      <label className="react-checkbox">
        <input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} />
        <span>Enabled</span>
      </label>
      <div className="dataset-card-meta">
        <span>Store: {storeLabel(dataset)}</span>
        <span>{dataset.content_counts?.patients ?? "?"} patients</span>
        <span>{dataset.content_counts?.timepoints ?? "?"} timepoints</span>
      </div>
      <div className="pheno-actions pheno-actions-primary">
        <button type="button" className="query-chip" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving..." : "Save settings"}</button>
        <button type="button" className="query-chip" disabled={prepare.isPending} onClick={() => prepare.mutate()}>{prepare.isPending ? "Preparing..." : storeReady(dataset) ? "Rebuild store" : "Prepare store"}</button>
      </div>
      {status ? <div className="query-status">{status}</div> : null}
    </article>
  );
}

function UserAdminCard({ user, currentUsername, onStatus, onSaved }: { user: AuthUser; currentUsername: string; onStatus: (status: string) => void; onSaved: () => void }) {
  const [form, setForm] = useState(userForm(user));
  const [password, setPassword] = useState("");

  useEffect(() => setForm(userForm(user)), [user]);

  const save = useMutation({
    mutationFn: () => api.updateUser(user.username, { ...form, groups: splitCsv(form.groups) }),
    onSuccess: (updated) => {
      onStatus(`User ${updated.username} updated.`);
      onSaved();
    },
    onError: (error) => onStatus(formatApiDetail((error as ApiError).detail) || (error as Error).message),
  });
  const reset = useMutation({
    mutationFn: () => api.resetUserPassword(user.username, password),
    onSuccess: (updated) => {
      setPassword("");
      onStatus(`Password reset for ${updated.username}.`);
    },
    onError: (error) => onStatus(formatApiDetail((error as ApiError).detail) || (error as Error).message),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteUser(user.username),
    onSuccess: () => {
      onStatus(`User ${user.username} deleted.`);
      onSaved();
    },
    onError: (error) => onStatus(formatApiDetail((error as ApiError).detail) || (error as Error).message),
  });

  const isSelf = currentUsername === user.username;
  return (
    <article className="dataset-card react-admin-card">
      <div className="dataset-card-title">
        <strong>{user.display_name || user.username}</strong>
        <span>{user.username}</span>
      </div>
      <div className="pheno-advanced-grid">
        <Input label="Display name" value={form.display_name} onChange={(value) => setForm((current) => ({ ...current, display_name: value }))} />
        <Select label="Role" value={form.role} onChange={(value) => setForm((current) => ({ ...current, role: value }))} options={[["user", "User"], ["admin", "Admin"]]} />
        <Input label="Groups" value={form.groups} onChange={(value) => setForm((current) => ({ ...current, groups: value }))} />
        <label className="react-checkbox">
          <input type="checkbox" checked={form.enabled} disabled={isSelf} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} />
          <span>Enabled</span>
        </label>
      </div>
      <div className="pheno-actions pheno-actions-primary">
        <button type="button" className="query-chip" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving..." : "Save"}</button>
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="New password" />
        <button type="button" className="query-chip" disabled={reset.isPending || !password} onClick={() => reset.mutate()}>{reset.isPending ? "Resetting..." : "Reset password"}</button>
        <button type="button" className="query-chip query-chip-llm" disabled={remove.isPending || isSelf} onClick={() => remove.mutate()}>{remove.isPending ? "Deleting..." : "Delete"}</button>
      </div>
    </article>
  );
}

function AdminShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="react-admin-layout">
      <div className="section-heading">
        <div>
          <label>Admin</label>
          <h2>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

function Input({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <div>
      <label>{label}</label>
      <input type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) {
  return (
    <div>
      <label>{label}</label>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </div>
  );
}

function datasetForm(dataset: DatasetRecord) {
  return {
    name: dataset.name || "",
    description: dataset.description || "",
    visibility: dataset.visibility || "all_authenticated",
    allowedUsers: (dataset.allowed_users || []).join(", "),
    allowedGroups: (dataset.allowed_groups || []).join(", "),
    queryGranularity: dataset.query_granularity_ceiling || "summary",
    aiProviderAccess: dataset.ai_provider_access || "detailed_allowed",
    enabled: dataset.enabled !== false,
  };
}

function userForm(user: AuthUser) {
  return {
    display_name: user.display_name || user.username,
    role: user.role || "user",
    groups: (user.groups || []).join(", "),
    enabled: user.enabled !== false,
  };
}

function splitCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function effectiveAiAccess(visibility: string, requested: string): string {
  if (visibility === "restricted" || visibility === "admin_only") {
    return requested === "blocked" ? "blocked" : "safe_summary";
  }
  return requested;
}

function storeReady(dataset: DatasetRecord): boolean {
  const status = dataset.query_store_status || {};
  const label = String(status.status || status.state || "").toLowerCase();
  return Boolean(status.ready) || label === "ready" || label === "current";
}

function storeLabel(dataset: DatasetRecord): string {
  if (storeReady(dataset)) return "Ready";
  const status = dataset.query_store_status || {};
  return String(status.status || status.state || "not built").replaceAll("_", " ");
}
