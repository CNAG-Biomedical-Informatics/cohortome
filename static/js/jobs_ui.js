export function createJobsUi(ctx) {
  const { refs, state, helpers, callbacks } = ctx;
  const {
    jobsDrawerBtnEl,
    jobsDrawerCountEl,
    jobsDrawerEl,
    jobsWorkerStatusEl,
    jobsDrawerStatusEl,
    jobsDrawerListEl,
    runHistoryDrawerBtnEl,
    runHistoryDrawerCountEl,
    runHistoryDrawerEl,
    runHistoryWorkerStatusEl,
    runHistoryDrawerStatusEl,
    runHistoryDrawerListEl,
    runHistoryDeleteAllBtnEl,
    analysisStatusEl,
    dataDirEl,
  } = refs;
  const { escapeHtml } = helpers;
  const {
    currentAnalysisSessionId,
    currentDatasetScopeId,
    analysisPayloadHasPlots,
    selectAnalysisSession,
    createAndSelectAnalysisSession,
    setActiveTab,
    renderAnalysisMeta,
    renderAnalysisThread,
    scrollAnalysisTurnIntoView,
    syncCurrentAnalysisSessionFromUi,
    loadCompletedPhenoJob,
    renderPhenoBackgroundJobBanner,
    onBackgroundWorkerStatusChanged,
  } = callbacks;

  function setJobsDrawerOpen(open) {
    if (!jobsDrawerEl) return;
    if (open) {
      setRunHistoryDrawerOpen(false);
    }
    jobsDrawerEl.classList.toggle("is-hidden", !open);
    jobsDrawerEl.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function setRunHistoryDrawerOpen(open) {
    if (!runHistoryDrawerEl) return;
    if (open) {
      setJobsDrawerOpen(false);
    }
    runHistoryDrawerEl.classList.toggle("is-hidden", !open);
    runHistoryDrawerEl.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function closeJobSurfaces() {
    if (jobsDrawerEl) {
      jobsDrawerEl.classList.add("is-hidden");
      jobsDrawerEl.setAttribute("aria-hidden", "true");
    }
    if (runHistoryDrawerEl) {
      runHistoryDrawerEl.classList.add("is-hidden");
      runHistoryDrawerEl.setAttribute("aria-hidden", "true");
    }
  }

  function runningJobCount() {
    return Array.isArray(state.recentJobs)
      ? state.recentJobs.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : ""))).length
      : 0;
  }

  function terminalRunCount() {
    return Array.isArray(state.runHistory)
      ? state.runHistory.filter((item) => ["completed", "failed", "cancelled"].includes(String(item && item.status ? item.status : ""))).length
      : 0;
  }

  function renderJobsButton() {
    if (!jobsDrawerBtnEl || !jobsDrawerCountEl) {
      return;
    }
    const running = runningJobCount();
    if (!state.authState || !state.authState.authenticated) {
      jobsDrawerBtnEl.classList.add("is-hidden");
      jobsDrawerCountEl.textContent = "";
      return;
    }
    jobsDrawerBtnEl.classList.remove("is-hidden");
    jobsDrawerCountEl.textContent = running ? String(running) : "";
    jobsDrawerBtnEl.classList.toggle("has-running-jobs", running > 0);
    jobsDrawerCountEl.classList.toggle("is-hidden", running === 0);
  }

  function renderRunHistoryButton() {
    if (!runHistoryDrawerBtnEl || !runHistoryDrawerCountEl) {
      return;
    }
    if (!state.authState || !state.authState.authenticated) {
      runHistoryDrawerBtnEl.classList.add("is-hidden");
      runHistoryDrawerCountEl.textContent = "";
      return;
    }
    const count = Array.isArray(state.runHistory) ? state.runHistory.length : 0;
    runHistoryDrawerBtnEl.classList.remove("is-hidden");
    runHistoryDrawerCountEl.textContent = count ? String(count) : "";
    runHistoryDrawerCountEl.classList.toggle("is-hidden", count === 0);
  }

  function renderJobStatusChip(item) {
    const status = String(item && item.status ? item.status : "queued").trim();
    const css = ["queued", "running", "completed", "failed", "cancelled"].includes(status)
      ? `is-${status}`
      : "";
    return `<span class="job-status-chip ${css}">${escapeHtml(status)}</span>`;
  }

  function renderBackgroundWorkerStatus() {
    const targets = [jobsWorkerStatusEl, runHistoryWorkerStatusEl].filter(Boolean);
    const status = state.backgroundWorkerStatus && typeof state.backgroundWorkerStatus === "object"
      ? state.backgroundWorkerStatus
      : null;
    targets.forEach((target) => {
      target.classList.remove("is-online", "is-offline", "is-checking");
      if (!status) {
        target.classList.add("is-checking");
        target.textContent = "Checking background workers…";
        return;
      }
      const workerCount = Math.max(0, Number(status.worker_count || 0));
      const busyCount = Math.max(0, Number(status.busy_worker_count || 0));
      if (status.available) {
        target.classList.add("is-online");
        const activity = busyCount > 0
          ? `${busyCount} working`
          : "idle";
        target.textContent = `Background workers: Online · ${workerCount} ${workerCount === 1 ? "worker" : "workers"} · ${activity}`;
        return;
      }
      target.classList.add("is-offline");
      const reason = status.redis_available
        ? "no worker online"
        : status.dependencies_available
          ? "Redis unavailable"
          : "RQ/Redis support unavailable";
      target.textContent = `Background workers: Offline · ${reason}`;
    });
  }

  function renderExecutionChip(item, surface) {
    if (String(surface || "") !== "run-history") {
      return "";
    }
    const backend = String(item && item.execution_backend ? item.execution_backend : "").trim().toLowerCase();
    const hasQueueId = Boolean(String(item && item.rq_job_id ? item.rq_job_id : "").trim());
    const isBackground = backend === "job" || hasQueueId;
    const label = isBackground ? "Background" : "Direct";
    const css = isBackground ? "is-background" : "is-direct";
    return `<span class="job-execution-chip ${css}">${label}</span>`;
  }

  function renderJobGroup(title, items, options = {}) {
    if (!Array.isArray(items) || !items.length) return "";
    return `<section class="job-group"><div class="job-group-title">${escapeHtml(title)}</div><div class="job-group-list">${items.map((item) => renderJobCard(item, options)).join("")}</div></section>`;
  }

  function actionIcon(name) {
    if (name === "open") {
      return `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M14 3h7v7"></path>
          <path d="M10 14 21 3"></path>
          <path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"></path>
        </svg>
      `;
    }
    if (name === "pheno") {
      return `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M7 7h10v10H7z"></path>
          <path d="M4 12h3"></path>
          <path d="M17 12h3"></path>
          <path d="M12 4v3"></path>
          <path d="M12 17v3"></path>
          <path d="M9 10h6"></path>
          <path d="M9 14h6"></path>
        </svg>
      `;
    }
    return `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 6h18"></path>
        <path d="M8 6V4h8v2"></path>
        <path d="M19 6l-1 14H6L5 6"></path>
        <path d="M10 11v5"></path>
        <path d="M14 11v5"></path>
      </svg>
    `;
  }

  function renderIconAction({ attribute, value, label, icon, tone = "" }) {
    const classes = ["job-card-action-icon"];
    if (tone) classes.push(tone);
    return `<button type="button" class="${classes.join(" ")}" ${attribute}="${escapeHtml(value || "")}" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">${actionIcon(icon)}</button>`;
  }

  function formatJobDuration(item) {
    const started = String(item && item.started_at ? item.started_at : "").trim();
    const completed = String(item && item.completed_at ? item.completed_at : "").trim();
    if (!started || !completed) {
      return "";
    }
    const startMs = Date.parse(started);
    const endMs = Date.parse(completed);
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
      return "";
    }
    const totalSeconds = Math.max(1, Math.round((endMs - startMs) / 1000));
    if (totalSeconds < 60) {
      return `${totalSeconds}s`;
    }
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return seconds > 0
        ? `${hours}h ${minutes}m ${seconds}s`
        : `${hours}h ${minutes}m`;
    }
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }

  function renderJobCard(item, options = {}) {
    const surface = String(options.surface || "jobs").trim();
    const submitted = String(item && item.submitted_at ? item.submitted_at : "").trim();
    const duration = formatJobDuration(item);
    const artifacts = Array.isArray(item && item.artifacts) ? item.artifacts : [];
    const prompt = String(item && item.prompt ? item.prompt : "").trim();
    const datasetId = String(item && item.dataset_id ? item.dataset_id : "").trim();
    const assayDatasetName = String(item && item.assay_id ? item.assay_id : "").trim();
    const sessionTitle = String(item && item.analysis_session_title ? item.analysis_session_title : "").trim();
    const metaBits = [];
    if (item && item.job_code) metaBits.push(String(item.job_code));
    if (datasetId) metaBits.push(`dataset ${datasetId}`);
    if (assayDatasetName) metaBits.push(`assay ${assayDatasetName}`);
    if (sessionTitle) metaBits.push(sessionTitle);
    const actions = [];
    const feature = String(item && item.feature ? item.feature : "").trim();
    const workspaceMatches = String(currentDatasetScopeId ? currentDatasetScopeId() : "").trim() === String(item && item.dataset_id ? item.dataset_id : "").trim();
    if (item && item.result_available && feature === "analysis") {
      actions.push(renderIconAction({ attribute: "data-job-open-result", value: item.job_id || "", label: "Open result", icon: "open", tone: "action" }));
    } else if (item && item.result_available && feature === "pheno" && workspaceMatches) {
      actions.push(renderIconAction({ attribute: "data-job-open-pheno", value: item.job_id || "", label: "Open in Pheno-Ranker", icon: "pheno", tone: "action" }));
    }
    if (item && ["completed", "failed", "cancelled"].includes(String(item.status || "").trim())) {
      const attribute = surface === "run-history" ? "data-run-history-delete" : "data-job-delete";
      actions.push(renderIconAction({ attribute, value: item.job_id || "", label: "Delete generated run", icon: "delete", tone: "danger" }));
    }
    const artifactLinks = artifacts.map((artifact) => {
      const url = String(artifact && artifact.url ? artifact.url : "").trim();
      const name = String(artifact && artifact.name ? artifact.name : "").trim();
      if (!url || !name) return "";
      return `<a class="query-chip" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>`;
    }).filter(Boolean);
    const artifactsHtml = artifactLinks.length
      ? `
        <details class="job-card-artifacts">
          <summary>Result files</summary>
          <div class="job-card-artifact-links">${artifactLinks.join("")}</div>
        </details>
      `
      : "";
    return `
      <article class="job-card">
        <div class="job-card-topline">
          <div class="job-card-badges">
            ${renderJobStatusChip(item)}
            ${renderExecutionChip(item, surface)}
          </div>
          <span class="job-card-time">${escapeHtml(submitted || "Submitted just now")}${duration ? ` · ${escapeHtml(duration)}` : ""}</span>
        </div>
        <div class="job-card-header">
          <div class="job-card-title">
            <strong>${escapeHtml(String(item && item.name ? item.name : "Generated run"))}</strong>
            <div class="job-card-subtitle">${escapeHtml(metaBits.join(" · "))}</div>
          </div>
        </div>
        ${prompt ? `<div class="job-card-prompt">${escapeHtml(prompt)}</div>` : ""}
        ${item && item.reply_preview ? `<div class="job-card-preview">${escapeHtml(String(item.reply_preview))}</div>` : ""}
        ${(item && item.result_available && feature === "pheno" && !workspaceMatches) ? `<div class="job-card-preview">Load the original workspace to reopen this Pheno-Ranker run.</div>` : ""}
        ${item && item.error ? `<div class="job-card-error">${escapeHtml(String(item.error))}</div>` : ""}
        ${(actions.length || artifactLinks.length) ? `
          <div class="job-card-footer">
            ${actions.length ? `<div class="job-card-actions">${actions.join("")}</div>` : ""}
            ${artifactsHtml}
          </div>
        ` : ""}
      </article>
    `;
  }

  function renderJobsDrawer() {
    renderJobsButton();
    renderBackgroundWorkerStatus();
    if (!jobsDrawerListEl) {
      return;
    }
    if (!state.authState || !state.authState.authenticated) {
      jobsDrawerListEl.innerHTML = '<div class="empty">Sign in to view the queue.</div>';
      if (jobsDrawerStatusEl) jobsDrawerStatusEl.textContent = "Queue unavailable.";
      return;
    }
    if (!Array.isArray(state.recentJobs) || !state.recentJobs.length) {
      jobsDrawerListEl.innerHTML = '<div class="empty">No queued or background runs.</div>';
      if (jobsDrawerStatusEl) jobsDrawerStatusEl.textContent = "No queued or background runs.";
      return;
    }
    const running = runningJobCount();
    if (jobsDrawerStatusEl) {
      jobsDrawerStatusEl.textContent = running
        ? `${running} run${running === 1 ? "" : "s"} still running.`
        : `${state.recentJobs.length} background run${state.recentJobs.length === 1 ? "" : "s"}.`;
    }
    const activeItems = state.recentJobs.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : "")));
    const doneItems = state.recentJobs.filter((item) => !["queued", "running"].includes(String(item && item.status ? item.status : "")));
    jobsDrawerListEl.innerHTML = [
      renderJobGroup("Active", activeItems, { surface: "jobs" }),
      renderJobGroup("Recent", doneItems, { surface: "jobs" }),
    ].filter(Boolean).join("");
  }

  function renderRunHistoryDrawer() {
    renderRunHistoryButton();
    renderBackgroundWorkerStatus();
    if (!runHistoryDrawerListEl) {
      return;
    }
    if (!state.authState || !state.authState.authenticated) {
      runHistoryDrawerListEl.innerHTML = '<div class="empty">Sign in to view run history.</div>';
      if (runHistoryDrawerStatusEl) runHistoryDrawerStatusEl.textContent = "Run history unavailable.";
      if (runHistoryDeleteAllBtnEl) runHistoryDeleteAllBtnEl.disabled = true;
      return;
    }
    const items = Array.isArray(state.runHistory) ? state.runHistory : [];
    const terminal = terminalRunCount();
    if (runHistoryDeleteAllBtnEl) runHistoryDeleteAllBtnEl.disabled = terminal === 0;
    if (!items.length) {
      runHistoryDrawerListEl.innerHTML = '<div class="empty">No generated runs yet.</div>';
      if (runHistoryDrawerStatusEl) runHistoryDrawerStatusEl.textContent = "No generated runs yet.";
      return;
    }
    const activeItems = items.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : "")));
    const doneItems = items.filter((item) => !["queued", "running"].includes(String(item && item.status ? item.status : "")));
    if (runHistoryDrawerStatusEl) {
      const activeCopy = activeItems.length ? ` ${activeItems.length} active run${activeItems.length === 1 ? "" : "s"} kept until finished.` : "";
      runHistoryDrawerStatusEl.textContent = `${items.length} generated run${items.length === 1 ? "" : "s"}.${activeCopy}`;
    }
    runHistoryDrawerListEl.innerHTML = [
      renderJobGroup("Active", activeItems, { surface: "run-history" }),
      renderJobGroup("Completed", doneItems, { surface: "run-history" }),
    ].filter(Boolean).join("");
  }

  function scheduleJobsPolling() {
    if (state.jobsPollTimer) {
      window.clearTimeout(state.jobsPollTimer);
      state.jobsPollTimer = null;
    }
    if (!runningJobCount()) {
      return;
    }
    state.jobsPollTimer = window.setTimeout(() => {
      void loadRecentJobs({ silent: true });
    }, 3000);
  }

  function withArtifactVersion(url, version) {
    const rawUrl = String(url || "").trim();
    const rawVersion = String(version || "").trim();
    if (!rawUrl || !rawVersion) return rawUrl;
    const separator = rawUrl.includes("?") ? "&" : "?";
    return `${rawUrl}${separator}v=${encodeURIComponent(rawVersion)}`;
  }

  function versionedJobArtifacts(artifacts, version) {
    return (Array.isArray(artifacts) ? artifacts : []).map((artifact) => ({
      ...artifact,
      url: withArtifactVersion(artifact && artifact.url ? artifact.url : "", version),
    }));
  }

  async function hydrateCompletedAnalysisJobsForCurrentSession() {
    const sessionId = String(currentAnalysisSessionId() || "").trim();
    if (!sessionId || !Array.isArray(state.analysisTurns) || !state.analysisTurns.length) {
      return;
    }
    const queuedTurnJobIds = new Set(
      state.analysisTurns
        .filter((turn) => {
          const data = turn && turn.payload ? turn.payload.data : null;
          return turn && turn.role === "assistant"
            && data
            && String(data.execution || "").trim() === "queued"
            && String(data.job_id || "").trim();
        })
        .map((turn) => String(turn.payload.data.job_id || "").trim())
    );
    if (!queuedTurnJobIds.size) {
      return;
    }
    const completedJobs = state.recentJobs.filter((item) =>
      item
      && String(item.analysis_session_id || "").trim() === sessionId
      && String(item.status || "").trim() === "completed"
      && Boolean(item.result_available)
      && queuedTurnJobIds.has(String(item.job_id || "").trim())
    );
    for (const item of completedJobs) {
      const jobId = String(item && item.job_id ? item.job_id : "").trim();
      if (!jobId) continue;
      try {
        const response = await fetch(`/jobs/${encodeURIComponent(jobId)}`);
        if (!response.ok) continue;
        const payload = await response.json();
        const resultPayload = payload && payload.result_payload ? payload.result_payload : null;
        if (!resultPayload || !resultPayload.data) continue;
        const artifactVersion = String(payload.updated_at || payload.completed_at || payload.job_id || "").trim();
        resultPayload.data.job_id = String(payload.job_id || resultPayload.data.job_id || "");
        resultPayload.data.job_status = String(payload.status || resultPayload.data.job_status || "");
        resultPayload.data.job_code = String(payload.job_code || resultPayload.data.job_code || "");
        resultPayload.data.artifacts = versionedJobArtifacts(payload.artifacts, artifactVersion);
        resultPayload.data.assay_id = String(payload.assay_id || resultPayload.data.assay_id || "");
        const turnIndex = state.analysisTurns.findIndex((turn) => {
          const data = turn && turn.payload ? turn.payload.data : null;
          return turn
            && turn.role === "assistant"
            && data
            && String(data.job_id || "").trim() === jobId
            && String(data.execution || "").trim() === "queued";
        });
        if (turnIndex < 0) continue;
        state.analysisTurns[turnIndex] = {
          role: "assistant",
          payload: resultPayload,
          showPlots: analysisPayloadHasPlots(resultPayload),
        };
        renderAnalysisMeta(resultPayload);
        renderAnalysisThread();
        syncCurrentAnalysisSessionFromUi({ render: true });
        if (analysisStatusEl) {
          analysisStatusEl.className = "query-status";
          analysisStatusEl.textContent = `Background run ${String(payload.job_code || jobId).trim()} completed.`;
        }
      } catch (_error) {
      }
    }
  }

  async function loadRecentJobs(options = {}) {
    const silent = Boolean(options.silent);
    if (!state.authState || !state.authState.authenticated) {
      state.recentJobs = [];
      renderJobsDrawer();
      renderRunHistoryDrawer();
      if (typeof renderPhenoBackgroundJobBanner === "function") {
        renderPhenoBackgroundJobBanner();
      }
      return;
    }
    void loadBackgroundWorkerStatus();
    if (!silent && jobsDrawerStatusEl) {
      jobsDrawerStatusEl.textContent = "Loading queue...";
    }
    try {
      const response = await fetch("/jobs");
      if (!response.ok) {
        throw new Error("Unable to load queue.");
      }
      const payload = await response.json();
      state.recentJobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      void loadRunHistory({ silent: true, skipWorkerStatus: true });
      void hydrateCompletedAnalysisJobsForCurrentSession();
      renderJobsDrawer();
      if (typeof renderPhenoBackgroundJobBanner === "function") {
        renderPhenoBackgroundJobBanner();
      }
      scheduleJobsPolling();
    } catch (error) {
      if (!silent && jobsDrawerStatusEl) {
        jobsDrawerStatusEl.textContent = error && error.message ? error.message : "Unable to load queue.";
      }
    }
  }

  async function loadRunHistory(options = {}) {
    const silent = Boolean(options.silent);
    if (!options.skipWorkerStatus) {
      void loadBackgroundWorkerStatus();
    }
    if (!state.authState || !state.authState.authenticated) {
      state.runHistory = [];
      renderRunHistoryDrawer();
      return;
    }
    if (!silent && runHistoryDrawerStatusEl) {
      runHistoryDrawerStatusEl.textContent = "Loading run history...";
    }
    try {
      const response = await fetch("/run-history");
      if (!response.ok) {
        throw new Error("Unable to load run history.");
      }
      const payload = await response.json();
      state.runHistory = Array.isArray(payload.runs) ? payload.runs : [];
      renderRunHistoryDrawer();
      const expiredDeleted = Number(payload.expired_deleted_count || 0);
      if (expiredDeleted > 0 && runHistoryDrawerStatusEl) {
        runHistoryDrawerStatusEl.textContent = `Removed ${expiredDeleted} expired generated run${expiredDeleted === 1 ? "" : "s"} based on your retention setting.`;
      }
    } catch (error) {
      if (!silent && runHistoryDrawerStatusEl) {
        runHistoryDrawerStatusEl.textContent = error && error.message ? error.message : "Unable to load run history.";
      }
    }
  }

  async function loadBackgroundWorkerStatus() {
    if (!state.authState || !state.authState.authenticated) {
      state.backgroundWorkerStatus = null;
      renderBackgroundWorkerStatus();
      return;
    }
    try {
      const response = await fetch("/jobs/status");
      if (!response.ok) throw new Error("Unable to inspect background workers.");
      state.backgroundWorkerStatus = await response.json();
    } catch (_error) {
      state.backgroundWorkerStatus = {
        available: false,
        dependencies_available: true,
        redis_available: false,
        worker_count: 0,
        busy_worker_count: 0,
        activity: "offline",
      };
    }
    renderBackgroundWorkerStatus();
    if (typeof onBackgroundWorkerStatusChanged === "function") {
      onBackgroundWorkerStatusChanged(state.backgroundWorkerStatus);
    }
  }

  async function openJobResult(jobId) {
    const normalized = String(jobId || "").trim();
    if (!normalized) return;
    const response = await fetch(`/jobs/${encodeURIComponent(normalized)}`);
    if (!response.ok) {
      throw new Error("Unable to load run result.");
    }
    const payload = await response.json();
    if (!payload || !payload.result_payload) {
      throw new Error("This run does not have a completed result yet.");
    }
    const feature = String(payload.feature || "").trim();
    if (feature === "pheno") {
      const currentWorkspaceId = String(currentDatasetScopeId ? currentDatasetScopeId() : "").trim();
      const jobWorkspaceId = String(payload.dataset_id || "").trim();
      if (!currentWorkspaceId || currentWorkspaceId !== jobWorkspaceId) {
        throw new Error("Load the original workspace to reopen this Pheno-Ranker run.");
      }
      setJobsDrawerOpen(false);
      setRunHistoryDrawerOpen(false);
      setActiveTab("pheno");
      await loadCompletedPhenoJob(payload, payload.result_payload);
      return;
    }
    setJobsDrawerOpen(false);
    setRunHistoryDrawerOpen(false);
    setActiveTab("analysis");
    const sessionId = String(payload.analysis_session_id || "").trim();
    const existingSession = sessionId
      ? state.analysisSessions.find((item) => item.id === sessionId)
      : null;
    if (existingSession) {
      selectAnalysisSession(sessionId);
    } else if (sessionId) {
      createAndSelectAnalysisSession({
        id: sessionId,
        title: String(payload.name || payload.catalog_item_name || "Recovered analysis result").trim(),
        promptDraft: String(payload.prompt || "").trim(),
        dataDir: dataDirEl && dataDirEl.value ? dataDirEl.value.trim() : "",
        history: [],
        turns: [],
      });
    }
    const resultPayload = payload.result_payload;
    if (resultPayload && resultPayload.data) {
      const artifactVersion = String(payload.updated_at || payload.completed_at || payload.job_id || "").trim();
      resultPayload.data.job_id = String(payload.job_id || resultPayload.data.job_id || "");
      resultPayload.data.job_status = String(payload.status || resultPayload.data.job_status || "");
      resultPayload.data.job_code = String(payload.job_code || resultPayload.data.job_code || "");
      resultPayload.data.artifacts = versionedJobArtifacts(payload.artifacts, artifactVersion);
      resultPayload.data.assay_id = String(payload.assay_id || resultPayload.data.assay_id || "");
    }
    const existingIndex = Array.isArray(state.analysisTurns)
      ? state.analysisTurns.findIndex((turn) => {
          const data = turn && turn.payload ? turn.payload.data : null;
          return turn && turn.role === "assistant"
            && data
            && String(data.job_id || "") === normalized;
        })
      : -1;
    const turn = { role: "assistant", payload: resultPayload, showPlots: analysisPayloadHasPlots(resultPayload) };
    let resultTurnIndex = existingIndex;
    if (existingIndex >= 0) {
      state.analysisTurns[existingIndex] = turn;
    } else {
      state.analysisTurns.push(turn);
      resultTurnIndex = state.analysisTurns.length - 1;
    }
    state.analysisHistory.push({ role: "assistant", content: resultPayload.reply || "" });
    state.analysisHistory = state.analysisHistory.slice(-8);
    renderAnalysisMeta(resultPayload);
    renderAnalysisThread();
    if (typeof scrollAnalysisTurnIntoView === "function") {
      scrollAnalysisTurnIntoView(resultTurnIndex);
    }
    syncCurrentAnalysisSessionFromUi({ render: true });
    if (analysisStatusEl) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Loaded completed run result into Analysis.";
    }
  }

  async function deleteJob(jobId, options = {}) {
    const normalized = String(jobId || "").trim();
    if (!normalized) return;
    const surface = String(options.surface || "jobs").trim();
    const endpoint = surface === "run-history" ? "/run-history" : "/jobs";
    if (!window.confirm("Delete this generated run and its artifacts?")) {
      return;
    }
    const response = await fetch(`${endpoint}/${encodeURIComponent(normalized)}`, { method: "DELETE" });
    if (!response.ok) {
      let detail = "Unable to delete run.";
      try {
        const payload = await response.json();
        if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
          detail = payload.detail.trim();
        }
      } catch (_error) {
      }
      throw new Error(detail);
    }
    state.recentJobs = (Array.isArray(state.recentJobs) ? state.recentJobs : [])
      .filter((item) => String(item && item.job_id ? item.job_id : "").trim() !== normalized);
    state.runHistory = (Array.isArray(state.runHistory) ? state.runHistory : [])
      .filter((item) => String(item && item.job_id ? item.job_id : "").trim() !== normalized);
    renderJobsDrawer();
    renderRunHistoryDrawer();
    if (typeof renderPhenoBackgroundJobBanner === "function") {
      renderPhenoBackgroundJobBanner();
    }
    if (surface === "run-history" && runHistoryDrawerStatusEl) {
      runHistoryDrawerStatusEl.textContent = "Generated run deleted.";
    } else if (jobsDrawerStatusEl) {
      jobsDrawerStatusEl.textContent = "Background run deleted.";
    }
  }

  async function deleteRunHistory() {
    if (!window.confirm("Delete all completed, failed, and cancelled generated runs plus artifacts? Active runs will be kept.")) {
      return;
    }
    if (runHistoryDeleteAllBtnEl) runHistoryDeleteAllBtnEl.disabled = true;
    if (runHistoryDrawerStatusEl) runHistoryDrawerStatusEl.textContent = "Deleting generated runs...";
    try {
      const response = await fetch("/run-history", { method: "DELETE" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to delete generated runs.");
      }
      await loadRecentJobs({ silent: true });
      await loadRunHistory({ silent: true });
      const skipped = payload.skipped_active_count ? ` ${payload.skipped_active_count} active run${payload.skipped_active_count === 1 ? "" : "s"} kept.` : "";
      if (runHistoryDrawerStatusEl) {
        runHistoryDrawerStatusEl.textContent = `Deleted ${payload.deleted_count || 0} generated run${payload.deleted_count === 1 ? "" : "s"}.${skipped}`;
      }
    } catch (error) {
      if (runHistoryDrawerStatusEl) {
        runHistoryDrawerStatusEl.textContent = error && error.message ? error.message : "Unable to delete generated runs.";
      }
    } finally {
      if (runHistoryDeleteAllBtnEl) runHistoryDeleteAllBtnEl.disabled = terminalRunCount() === 0;
    }
  }

  return {
    setJobsDrawerOpen,
    setRunHistoryDrawerOpen,
    closeJobSurfaces,
    runningJobCount,
    terminalRunCount,
    renderJobsButton,
    renderRunHistoryButton,
    renderJobStatusChip,
    renderBackgroundWorkerStatus,
    renderJobGroup,
    renderJobCard,
    renderJobsDrawer,
    renderRunHistoryDrawer,
    scheduleJobsPolling,
    withArtifactVersion,
    versionedJobArtifacts,
    hydrateCompletedAnalysisJobsForCurrentSession,
    loadRecentJobs,
    loadRunHistory,
    loadBackgroundWorkerStatus,
    openJobResult,
    deleteJob,
    deleteRunHistory,
  };
}
