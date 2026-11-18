import {mountJobNotice} from './react/ui.js';
import {createJobsView} from './react/ui.js';

export function createJobsUi(ctx) {
  const { refs, state, callbacks } = ctx;
  window.addEventListener('cohortome:mcp-run', () => {
    void loadRecentJobs({silent:true});
    void loadRunHistory({silent:true});
  });
  let observedUser = "";
  let observedStatuses = new Map();
  let notice = null;
  function notifyTransitions(jobs, user) {
    if (observedUser !== user) {
      observedStatuses.clear();
      notice?.();
      observedUser = user;
    }
    const finished = jobs.filter((job) => ["queued", "running"].includes(observedStatuses.get(job.job_id))
      && ["completed", "failed"].includes(job.status));
    observedStatuses = new Map(jobs.map((job) => [job.job_id, job.status]));
    if (!finished.length || state.userSettings?.job_notifications === false) return;
    notice?.();
    const failed=finished.filter(job=>job.status==="failed").length;
    notice=mountJobNotice(`Background runs: ${finished.length-failed} completed, ${failed} failed.`,()=>setRunHistoryDrawerOpen(true));
  }
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
  const jobsView = jobsDrawerListEl ? createJobsView(jobsDrawerListEl) : null;
  const historyView = runHistoryDrawerListEl ? createJobsView(runHistoryDrawerListEl) : null;
  const {
    currentAnalysisSessionId,
    currentDatasetScopeId,
    analysisPayloadHasPlots,
    selectAnalysisSession,
    createAndSelectAnalysisSession,
    setActiveTab,
    renderAnalysisMeta,
    renderAnalysisThread,
    renderAnalysisFlowBar,
    setAnalysisComposerStatus,
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
    if (!state.authState?.authenticated) {
      notice?.();
      observedStatuses.clear();
      observedUser = "";
    }
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
    if (runHistoryDrawerBtnEl) {
      runHistoryDrawerBtnEl.setAttribute("aria-label", running ? `Runs, ${running} active jobs` : "Runs");
      runHistoryDrawerBtnEl.title = running ? `Runs — ${running} active jobs` : "Runs — history and active jobs";
    }
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
      const reason = status.backend === "local" ? "desktop runner unavailable" : status.redis_available
        ? "no worker online"
        : status.dependencies_available
          ? "Redis unavailable"
          : "RQ/Redis support unavailable";
      target.textContent = `Background workers: Offline · ${reason}`;
    });
  }


  function renderJobsDrawer() {
    renderJobsButton();
    renderBackgroundWorkerStatus();
    if (!jobsDrawerListEl) {
      return;
    }
    if (!state.authState || !state.authState.authenticated) {
      jobsView.render({message:'Sign in to view the queue.'});
      if (jobsDrawerStatusEl) jobsDrawerStatusEl.textContent = "Queue unavailable.";
      return;
    }
    if (!Array.isArray(state.recentJobs) || !state.recentJobs.length) {
      jobsView.render({message:'No queued or background runs.'});
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
    jobsView.render({groups:[{title:'Active',items:activeItems},{title:'Recent',items:doneItems}],workspace:currentDatasetScopeId?.()});
  }

  function renderRunHistoryDrawer() {
    renderRunHistoryButton();
    renderBackgroundWorkerStatus();
    if (!runHistoryDrawerListEl) {
      return;
    }
    if (!state.authState || !state.authState.authenticated) {
      historyView.render({message:'Sign in to view run history.'});
      if (runHistoryDrawerStatusEl) runHistoryDrawerStatusEl.textContent = "Run history unavailable.";
      if (runHistoryDeleteAllBtnEl) runHistoryDeleteAllBtnEl.disabled = true;
      return;
    }
    const items = Array.isArray(state.runHistory) ? state.runHistory : [];
    const terminal = terminalRunCount();
    if (runHistoryDeleteAllBtnEl) runHistoryDeleteAllBtnEl.disabled = terminal === 0;
    if (!items.length) {
      historyView.render({message:'No generated runs yet.'});
      if (runHistoryDrawerStatusEl) runHistoryDrawerStatusEl.textContent = "No generated runs yet.";
      return;
    }
    const activeItems = items.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : "")));
    const doneItems = items.filter((item) => !["queued", "running"].includes(String(item && item.status ? item.status : "")));
    if (runHistoryDrawerStatusEl) {
      const activeCopy = activeItems.length ? ` ${activeItems.length} active run${activeItems.length === 1 ? "" : "s"} kept until finished.` : "";
      runHistoryDrawerStatusEl.textContent = `${items.length} generated run${items.length === 1 ? "" : "s"}.${activeCopy}`;
    }
    historyView.render({groups:[{title:'Active',items:activeItems},{title:'Completed',items:doneItems}],surface:'run-history',workspace:currentDatasetScopeId?.()});
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
        if (sessionId !== String(currentAnalysisSessionId() || '').trim()) return;
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
          ...state.analysisTurns[turnIndex],
          role: "assistant",
          payload: resultPayload,
          showPlots: analysisPayloadHasPlots(resultPayload),
        };
        renderAnalysisMeta(resultPayload);
        renderAnalysisThread();
        renderAnalysisFlowBar();
        setAnalysisComposerStatus('Background analysis completed. Results are shown above.');
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
    const authSnapshot = state.authState;
    if (!state.authState || !state.authState.authenticated) {
      observedStatuses.clear();
      observedUser = "";
      notice?.();
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
      if (state.authState !== authSnapshot || !state.authState?.authenticated) return;
      state.recentJobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      notifyTransitions(state.recentJobs, String(authSnapshot.user?.id || authSnapshot.user?.username || "local"));
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
      turn.framing = state.analysisTurns[existingIndex].framing;
      state.analysisTurns[existingIndex] = turn;
    } else {
      state.analysisTurns.push(turn);
      resultTurnIndex = state.analysisTurns.length - 1;
    }
    state.analysisHistory.push({ role: "assistant", content: resultPayload.reply || "" });
    state.analysisHistory = state.analysisHistory.slice(-8);
    renderAnalysisMeta(resultPayload);
    renderAnalysisThread();
    renderAnalysisFlowBar();
    setAnalysisComposerStatus('Loaded completed analysis result.');
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
    renderBackgroundWorkerStatus,
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
