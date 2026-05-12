import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { JobRecord } from "../../api/types";

export function JobsDrawer() {
  const [open, setOpen] = useState(false);
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: (query) => {
      const active = query.state.data?.jobs?.some((job) => isActiveJob(job));
      return active ? 3000 : false;
    },
  });
  const items = jobs.data?.jobs || [];
  const activeCount = items.filter(isActiveJob).length;
  const activeJobs = useMemo(() => items.filter(isActiveJob), [items]);
  const recentJobs = useMemo(() => items.filter((job) => !isActiveJob(job)), [items]);

  return (
    <div className="react-jobs">
      <button type="button" className={`query-chip react-jobs-button${activeCount ? " has-running-jobs" : ""}`} onClick={() => setOpen(true)}>
        <span>Jobs</span>
        {activeCount ? <span className="jobs-drawer-count">{activeCount}</span> : null}
      </button>
      {open ? (
        <aside className="react-jobs-drawer" aria-label="Background jobs">
          <div className="react-jobs-drawer-header">
            <div>
              <strong>Background jobs</strong>
              <span>{activeCount ? `${activeCount} still running` : `${items.length} recent jobs`}</span>
            </div>
            <button type="button" className="query-chip" onClick={() => setOpen(false)}>Close</button>
          </div>
          {jobs.isLoading ? <div className="empty">Loading jobs...</div> : null}
          {jobs.error ? <div className="query-status">{(jobs.error as Error).message}</div> : null}
          {!jobs.isLoading && !items.length ? <div className="empty">No background jobs yet.</div> : null}
          <JobGroup title="Active" jobs={activeJobs} />
          <JobGroup title="Recent" jobs={recentJobs} />
        </aside>
      ) : null}
    </div>
  );
}

function JobGroup({ title, jobs }: { title: string; jobs: JobRecord[] }) {
  if (!jobs.length) return null;
  return (
    <section className="react-job-group">
      <div className="job-group-title">{title}</div>
      <div className="job-group-list">
        {jobs.map((job) => <JobCard key={job.job_id} job={job} />)}
      </div>
    </section>
  );
}

function JobCard({ job }: { job: JobRecord }) {
  const meta = [
    job.job_code,
    job.dataset_id ? `dataset ${job.dataset_id}` : "",
    job.feature,
    formatDuration(job),
  ].filter(Boolean);
  return (
    <article className="job-card">
      <div className="job-card-topline">
        <span className={`job-status-chip is-${job.status || "queued"}`}>{job.status || "queued"}</span>
        <span className="job-card-time">{job.submitted_at || "Submitted just now"}</span>
      </div>
      <div className="job-card-header">
        <div className="job-card-title">
          <strong>{job.name || "Background job"}</strong>
          <div className="job-card-subtitle">{meta.join(" · ")}</div>
        </div>
      </div>
      {job.prompt ? <div className="job-card-prompt">{job.prompt}</div> : null}
      {job.reply_preview ? <div className="job-card-preview">{job.reply_preview}</div> : null}
      {job.error ? <div className="job-card-error">{job.error}</div> : null}
      {job.artifacts?.length ? (
        <details className="job-card-artifacts">
          <summary>Result files</summary>
          <div className="job-card-artifact-links">
            {job.artifacts.map((artifact) => artifact.url && artifact.name ? (
              <a key={`${job.job_id}-${artifact.name}`} className="query-chip" href={artifact.url} target="_blank" rel="noreferrer">
                {artifact.name}
              </a>
            ) : null)}
          </div>
        </details>
      ) : null}
    </article>
  );
}

function isActiveJob(job: JobRecord) {
  return ["queued", "running"].includes(String(job.status || "").trim());
}

function formatDuration(job: JobRecord): string {
  if (!job.started_at || !job.completed_at) return "";
  const started = Date.parse(job.started_at);
  const completed = Date.parse(job.completed_at);
  if (!Number.isFinite(started) || !Number.isFinite(completed) || completed <= started) return "";
  const seconds = Math.max(1, Math.round((completed - started) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}
