export function createJobsUi(ctx) {
  const { refs, state, helpers, callbacks } = ctx;
  const {
    jobsDrawerBtnEl,
    jobsDrawerCountEl,
    jobsFloatingPillEl,
    jobsFloatingPillCountEl,
    jobsDrawerEl,
    jobsDrawerStatusEl,
    jobsDrawerListEl,
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
    syncCurrentAnalysisSessionFromUi,
    loadCompletedPhenoJob,
    renderPhenoBackgroundJobBanner,
  } = callbacks;

  function setJobsDrawerOpen(open) {
    if (!jobsDrawerEl) return;
    jobsDrawerEl.classList.toggle("is-hidden", !open);
    jobsDrawerEl.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function runningJobCount() {
    return Array.isArray(state.recentJobs)
      ? state.recentJobs.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : ""))).length
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
      if (jobsFloatingPillEl && jobsFloatingPillCountEl) {
        jobsFloatingPillEl.classList.add("is-hidden");
        jobsFloatingPillCountEl.textContent = "";
      }
      return;
    }
    jobsDrawerBtnEl.classList.remove("is-hidden");
    jobsDrawerCountEl.textContent = running ? String(running) : "";
    jobsDrawerBtnEl.classList.toggle("has-running-jobs", running > 0);
    jobsDrawerCountEl.classList.toggle("is-hidden", running === 0);
    if (jobsFloatingPillEl && jobsFloatingPillCountEl) {
      jobsFloatingPillEl.classList.toggle("is-hidden", running === 0);
      jobsFloatingPillCountEl.textContent = running ? String(running) : "";
      jobsFloatingPillCountEl.classList.toggle("is-hidden", running === 0);
    }
  }

  function renderJobStatusChip(item) {
    const status = String(item && item.status ? item.status : "queued").trim();
    const css = ["completed", "failed", "cancelled"].includes(status) ? `query-chip-${status}` : "query-chip-planner";
    return `<span class="query-chip badge ${css}">${escapeHtml(status)}</span>`;
  }

  function renderJobGroup(title, items) {
    if (!Array.isArray(items) || !items.length) return "";
    return `<section class="job-group"><div class="job-group-title">${escapeHtml(title)}</div><div class="job-group-list">${items.map(renderJobCard).join("")}</div></section>`;
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

  function renderJobCard(item) {
    const submitted = String(item && item.submitted_at ? item.submitted_at : "").trim();
    const duration = formatJobDuration(item);
    const artifacts = Array.isArray(item && item.artifacts) ? item.artifacts : [];
    const prompt = String(item && item.prompt ? item.prompt : "").trim();
    const datasetId = String(item && item.dataset_id ? item.dataset_id : "").trim();
    const molecularDatasetName = String(item && item.molecular_dataset_name ? item.molecular_dataset_name : "").trim();
    const sessionTitle = String(item && item.analysis_session_title ? item.analysis_session_title : "").trim();
    const metaBits = [];
    if (item && item.job_code) metaBits.push(String(item.job_code));
    if (datasetId) metaBits.push(`dataset ${datasetId}`);
    if (molecularDatasetName) metaBits.push(`molecular ${molecularDatasetName}`);
    if (sessionTitle) metaBits.push(sessionTitle);
    const actions = [];
    const feature = String(item && item.feature ? item.feature : "").trim();
    const workspaceMatches = String(currentDatasetScopeId ? currentDatasetScopeId() : "").trim() === String(item && item.dataset_id ? item.dataset_id : "").trim();
    if (item && item.result_available && feature === "analysis") {
      actions.push(`<button type="button" class="query-chip action" data-job-open-result="${escapeHtml(item.job_id || "")}">Open result</button>`);
    } else if (item && item.result_available && feature === "pheno" && workspaceMatches) {
      actions.push(`<button type="button" class="query-chip action" data-job-open-pheno="${escapeHtml(item.job_id || "")}">Open in Pheno</button>`);
    }
    const artifactLinks = artifacts.map((artifact) => {
      const url = String(artifact && artifact.url ? artifact.url : "").trim();
      const name = String(artifact && artifact.name ? artifact.name : "").trim();
      if (!url || !name) return "";
      return `<a class="query-chip" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>`;
    }).filter(Boolean);
    return `
      <article class="job-card">
        <div class="job-card-topline">
          ${renderJobStatusChip(item)}
          <span class="job-card-time">${escapeHtml(submitted || "Submitted just now")}${duration ? ` · ${escapeHtml(duration)}` : ""}</span>
        </div>
        <div class="job-card-header">
          <div class="job-card-title">
            <strong>${escapeHtml(String(item && item.name ? item.name : "Background job"))}</strong>
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
            ${artifactLinks.length ? `<div class="job-card-artifacts">${artifactLinks.join("")}</div>` : ""}
          </div>
        ` : ""}
      </article>
    `;
  }

  function renderJobsDrawer() {
    renderJobsButton();
    if (!jobsDrawerListEl) {
      return;
    }
    if (!state.authState || !state.authState.authenticated) {
      jobsDrawerListEl.innerHTML = '<div class="empty">Sign in to view background jobs.</div>';
      if (jobsDrawerStatusEl) jobsDrawerStatusEl.textContent = "Jobs unavailable.";
      return;
    }
    if (!Array.isArray(state.recentJobs) || !state.recentJobs.length) {
      jobsDrawerListEl.innerHTML = '<div class="empty">No background jobs yet.</div>';
      if (jobsDrawerStatusEl) jobsDrawerStatusEl.textContent = "No background jobs yet.";
      return;
    }
    const running = runningJobCount();
    if (jobsDrawerStatusEl) {
      jobsDrawerStatusEl.textContent = running
        ? `${running} job${running === 1 ? "" : "s"} still running.`
        : `${state.recentJobs.length} recent job${state.recentJobs.length === 1 ? "" : "s"}.`;
    }
    const activeItems = state.recentJobs.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : "")));
    const doneItems = state.recentJobs.filter((item) => !["queued", "running"].includes(String(item && item.status ? item.status : "")));
    jobsDrawerListEl.innerHTML = [
      renderJobGroup("Active", activeItems),
      renderJobGroup("Recent", doneItems),
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
        resultPayload.data.molecular_dataset_name = String(payload.molecular_dataset_name || resultPayload.data.molecular_dataset_name || "");
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
          analysisStatusEl.textContent = `Background job ${String(payload.job_code || jobId).trim()} completed.`;
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
      if (typeof renderPhenoBackgroundJobBanner === "function") {
        renderPhenoBackgroundJobBanner();
      }
      return;
    }
    if (!silent && jobsDrawerStatusEl) {
      jobsDrawerStatusEl.textContent = "Loading recent jobs...";
    }
    try {
      const response = await fetch("/jobs");
      if (!response.ok) {
        throw new Error("Unable to load jobs.");
      }
      const payload = await response.json();
      state.recentJobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      void hydrateCompletedAnalysisJobsForCurrentSession();
      renderJobsDrawer();
      if (typeof renderPhenoBackgroundJobBanner === "function") {
        renderPhenoBackgroundJobBanner();
      }
      scheduleJobsPolling();
    } catch (error) {
      if (!silent && jobsDrawerStatusEl) {
        jobsDrawerStatusEl.textContent = error && error.message ? error.message : "Unable to load jobs.";
      }
    }
  }

  async function openJobResult(jobId) {
    const normalized = String(jobId || "").trim();
    if (!normalized) return;
    const response = await fetch(`/jobs/${encodeURIComponent(normalized)}`);
    if (!response.ok) {
      throw new Error("Unable to load job result.");
    }
    const payload = await response.json();
    if (!payload || !payload.result_payload) {
      throw new Error("This job does not have a completed result yet.");
    }
    const feature = String(payload.feature || "").trim();
    if (feature === "pheno") {
      const currentWorkspaceId = String(currentDatasetScopeId ? currentDatasetScopeId() : "").trim();
      const jobWorkspaceId = String(payload.dataset_id || "").trim();
      if (!currentWorkspaceId || currentWorkspaceId !== jobWorkspaceId) {
        throw new Error("Load the original workspace to reopen this Pheno-Ranker run.");
      }
      setJobsDrawerOpen(false);
      setActiveTab("pheno");
      await loadCompletedPhenoJob(payload, payload.result_payload);
      return;
    }
    setJobsDrawerOpen(false);
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
      resultPayload.data.molecular_dataset_name = String(payload.molecular_dataset_name || resultPayload.data.molecular_dataset_name || "");
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
    if (existingIndex >= 0) {
      state.analysisTurns[existingIndex] = turn;
    } else {
      state.analysisTurns.push(turn);
    }
    state.analysisHistory.push({ role: "assistant", content: resultPayload.reply || "" });
    state.analysisHistory = state.analysisHistory.slice(-8);
    renderAnalysisMeta(resultPayload);
    renderAnalysisThread();
    syncCurrentAnalysisSessionFromUi({ render: true });
    if (analysisStatusEl) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Loaded completed job result into Analysis.";
    }
  }

  return {
    setJobsDrawerOpen,
    runningJobCount,
    renderJobsButton,
    renderJobStatusChip,
    renderJobGroup,
    renderJobCard,
    renderJobsDrawer,
    scheduleJobsPolling,
    withArtifactVersion,
    versionedJobArtifacts,
    hydrateCompletedAnalysisJobsForCurrentSession,
    loadRecentJobs,
    openJobResult,
  };
}
