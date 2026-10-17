import { addChatMenuIcons } from './chat_folders.js';
import { addWorkspaceRestoreAction } from './workspace_restore.js';

export function createAnalysisSessionsUi(ctx) {
  const { refs, helpers, callbacks, state, constants } = ctx;
  const {
    analysisSessionListEl,
    analysisPromptEl,
    analysisSelectedPatientIdsEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
    analysisSelectedSavedCohortSelectionEl,
    analysisCompareSavedCohortSelectionEl,
    analysisStatusEl,
    analysisMetaEl,
    analysisSessionDeleteDialogEl,
    analysisSessionDeleteCloseBtnEl,
    analysisSessionDeleteSummaryEl,
    analysisSessionDeleteStatusEl,
    analysisSessionDeleteOnlyBtnEl,
    analysisSessionDeleteAllBtnEl,
    analysisCurrentChatTitleEl,
    analysisCurrentChatMetaEl,
    dataDirEl,
  } = refs;
  const { escapeHtml, shortTimestamp, nowIso } = helpers;
  const {
    createAnalysisSession,
    currentAnalysisSession,
    currentDatasetSelectionKey,
    getStorageNamespace,
    renderAnalysisCompareMode,
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
    renderAnalysisStarterPrompts,
    renderAnalysisThread,
    renderAnalysisMeta,
    renderAnalysisFlowBar,
    renderAnalysisContextMode,
  } = callbacks;
  const { ANALYSIS_SESSIONS_STORAGE_KEY } = constants;
  let pendingDeleteSessionId = "";
  let deleteInFlight = false;
  const chatSearch = document.getElementById("analysisChatSearch");
  chatSearch?.addEventListener("input", renderAnalysisSessionList);

  function analysisSessionsStorageKey() {
    const namespace = typeof getStorageNamespace === "function" ? String(getStorageNamespace() || "").trim() : "";
    return namespace ? `${ANALYSIS_SESSIONS_STORAGE_KEY}.${namespace}` : ANALYSIS_SESSIONS_STORAGE_KEY;
  }

  function analysisSessionTitle(session) {
    const customTitle = String(session.title || "").trim();
    if (customTitle) return customTitle;
    const firstUserTurn = (session.turns || []).find((turn) => turn.role === "user" && turn.prompt);
    const raw = (firstUserTurn && firstUserTurn.prompt)
      || (session.compareMode ? "Compare cohorts" : "")
      || (String(session.scope || "").trim() ? "Scoped analysis" : "")
      || session.promptDraft
      || "New chat";
    const trimmed = String(raw).trim();
    if (!trimmed) return "New chat";
    return trimmed.length > 56 ? `${trimmed.slice(0, 56)}...` : trimmed;
  }

  function analysisSessionScopeSummary(session) {
    if (session.contextMode === "general") return "General questions";
    const scopeCount = String(session.scope || "").split(",").map((item) => item.trim()).filter(Boolean).length;
    const compareCount = String(session.compareScope || "").split(",").map((item) => item.trim()).filter(Boolean).length;
    if (session.compareMode) {
      const aLabel = scopeCount ? `${scopeCount} in A` : "full cohort in A";
      const bLabel = compareCount ? `${compareCount} in B` : "full cohort in B";
      return `${aLabel} vs ${bLabel}`;
    }
    return scopeCount ? `${scopeCount} IDs in scope` : "Full cohort";
  }

  function analysisWorkspaceStatusLabel(session) {
    const status = session && session.workspaceStatus && typeof session.workspaceStatus === "object" ? session.workspaceStatus : {};
    const value = String(status.state || "").trim();
    if (value === "stale") return "Workspace changed";
    if (value === "unavailable") return "Workspace unavailable";
    return "";
  }

  function setDeleteDialogOpen(open) {
    if (!analysisSessionDeleteDialogEl) return;
    analysisSessionDeleteDialogEl.classList.toggle("is-hidden", !open);
    analysisSessionDeleteDialogEl.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function resetDeleteDialogStatus() {
    if (!analysisSessionDeleteStatusEl) return;
    analysisSessionDeleteStatusEl.className = "query-status is-hidden";
    analysisSessionDeleteStatusEl.textContent = "";
  }

  function setDeleteDialogBusy(busy) {
    deleteInFlight = busy;
    if (analysisSessionDeleteCloseBtnEl) analysisSessionDeleteCloseBtnEl.disabled = busy;
    if (analysisSessionDeleteOnlyBtnEl) analysisSessionDeleteOnlyBtnEl.disabled = busy;
    if (analysisSessionDeleteAllBtnEl) analysisSessionDeleteAllBtnEl.disabled = busy;
  }

  function closeDeleteDialog() {
    if (deleteInFlight) return;
    pendingDeleteSessionId = "";
    resetDeleteDialogStatus();
    setDeleteDialogOpen(false);
  }

  function openDeleteDialog(sessionId) {
    const session = state.analysisSessions.find((item) => item.id === sessionId);
    if (!session || !analysisSessionDeleteDialogEl) return;
    pendingDeleteSessionId = sessionId;
    resetDeleteDialogStatus();
    setDeleteDialogBusy(false);
    if (analysisSessionDeleteSummaryEl) {
      const linkedJobs = Array.isArray(state.recentJobs)
        ? state.recentJobs.filter((item) => String(item && item.analysis_session_id ? item.analysis_session_id : "").trim() === sessionId)
        : [];
      const activeJobs = linkedJobs.filter((item) => ["queued", "running"].includes(String(item && item.status ? item.status : "").trim()));
      const linkedText = linkedJobs.length
        ? ` This chat has ${linkedJobs.length} linked generated run${linkedJobs.length === 1 ? "" : "s"}${activeJobs.length ? `, including ${activeJobs.length} active` : ""}.`
        : "";
      analysisSessionDeleteSummaryEl.textContent = `Delete chat "${analysisSessionTitle(session)}"?${linkedText}`;
    }
    setDeleteDialogOpen(true);
  }

  function timeValue(value) {
    const parsed = Date.parse(String(value || ""));
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function persistAnalysisSessions() {
    try {
      window.localStorage.setItem(
        analysisSessionsStorageKey(),
        JSON.stringify({
          currentId: state.currentAnalysisSessionId,
          sessions: state.analysisSessions,
        })
      );
    } catch (_error) {
    }
  }

  async function upsertAnalysisSessionToBackend(session, strict = false) {
    try {
      const response = await fetch("/analysis-sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: session.id,
          title: session.title || "",
          dataset_id: session.datasetId || "",
          data_dir: session.dataDir || "",
          workspace_fingerprint: session.workspaceFingerprint || {},
          catalog_item_id: session.catalogItemId || "",
          measurement: session.measurement || "",
          script_draft: session.scriptDraft || {},
          prompt_draft: session.promptDraft || "",
          framing: session.framing || {},
          context_mode: session.contextMode === "general" ? "general" : "workspace",
          scope: session.scope || "",
          scope_metadata: session.scopeMetadata || {},
          saved_cohort_id_a: session.savedCohortIdA || "",
          compare_mode: Boolean(session.compareMode),
          compare_scope: session.compareScope || "",
          compare_scope_metadata: session.compareScopeMetadata || {},
          saved_cohort_id_b: session.savedCohortIdB || "",
          history: Array.isArray(session.history) ? session.history : [],
          turns: Array.isArray(session.turns) ? session.turns : [],
          updated_at: session.updatedAt || "",
        }),
      });
      if (strict && !response.ok) {
        const payload = await response.json().catch(() => ({}));
        const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail || '');
        throw new Error(`Unable to save the current analysis conversation (${response.status}). ${detail}`);
      }
    } catch (_error) {
      if (strict) throw _error;
    }
  }

  async function renameAnalysisSessionInBackend(sessionId, title) {
    try {
      await fetch(`/analysis-sessions/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
    } catch (_error) {
    }
  }

  async function deleteAnalysisSessionFromBackend(sessionId, options) {
    const settings = options || {};
    const deleteGeneratedData = Boolean(settings.deleteGeneratedData);
    const keepGeneratedJobs = Boolean(settings.keepGeneratedJobs);
    try {
      const query = new URLSearchParams({
        delete_generated_data: deleteGeneratedData ? "true" : "false",
        keep_generated_jobs: keepGeneratedJobs ? "true" : "false",
      });
      const response = await fetch(
        `/analysis-sessions/${encodeURIComponent(sessionId)}?${query.toString()}`,
        { method: "DELETE" }
      );
      if (!response.ok) {
        let detail = "Unable to delete analysis session.";
        try {
          const payload = await response.json();
          if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
            detail = payload.detail.trim();
          }
        } catch (_error) {
        }
        throw new Error(detail);
      }
      return await response.json();
    } catch (error) {
      throw error instanceof Error ? error : new Error("Unable to delete analysis session.");
    }
  }

  async function loadAnalysisSessionsFromBackend() {
    try {
      const response = await fetch("/analysis-sessions");
      if (!response.ok) return false;
      const payload = await response.json();
      const backendSessions = Array.isArray(payload.sessions) ? payload.sessions.map((item) => createAnalysisSession({
        id: item.id,
        title: item.title,
        datasetId: item.dataset_id,
        dataDir: item.data_dir,
        workspaceFingerprint: item.workspace_fingerprint,
        workspaceStatus: item.workspace_status,
        catalogItemId: item.catalog_item_id,
        measurement: item.measurement,
        scriptDraft: item.script_draft,
        promptDraft: item.prompt_draft,
        framing: item.framing,
        contextMode: item.context_mode,
        scope: item.scope,
        scopeMetadata: item.scope_metadata,
        savedCohortIdA: item.saved_cohort_id_a,
        compareMode: item.compare_mode,
        compareScope: item.compare_scope,
        compareScopeMetadata: item.compare_scope_metadata,
        savedCohortIdB: item.saved_cohort_id_b,
        history: item.history,
        turns: item.turns,
        updatedAt: item.updated_at,
      })) : [];
      const localSessions = Array.isArray(state.analysisSessions) ? state.analysisSessions.slice() : [];
      const merged = new Map();
      backendSessions.forEach((session) => {
        merged.set(session.id, session);
      });
      localSessions.forEach((session) => {
        const existing = merged.get(session.id);
        if (!existing || timeValue(session.updatedAt) > timeValue(existing.updatedAt)) {
          merged.set(session.id, createAnalysisSession(session));
        }
      });
      const sessions = Array.from(merged.values());
      if (!sessions.length) return false;
      state.analysisSessions = sessions;
      if (!state.analysisSessions.some((session) => session.id === state.currentAnalysisSessionId)) {
        state.currentAnalysisSessionId = state.analysisSessions[0].id;
      }
      applyAnalysisSession(currentAnalysisSession() || state.analysisSessions[0]);
      persistAnalysisSessions();
      localSessions.forEach((session) => {
        const backend = backendSessions.find((item) => item.id === session.id);
        if (!backend || timeValue(session.updatedAt) > timeValue(backend.updatedAt)) {
          void upsertAnalysisSessionToBackend(session);
        }
      });
      return true;
    } catch (_error) {
      return false;
    }
  }

  function renderAnalysisSessionList() {
    if (!analysisSessionListEl) return;
    renderCurrentAnalysisChatBar();
    const allSessions = [...state.analysisSessions, ...(callbacks.queryChatEntries?.() || [])];
    if (!allSessions.length && !callbacks.organizeChats) {
      analysisSessionListEl.innerHTML = '<div class="empty">No chats yet.</div>';
      return;
    }
    const search = (chatSearch?.value || "").trim().toLocaleLowerCase();
    const ordered = allSessions.filter(session => !search ||
      [analysisSessionTitle(session), session.promptDraft, ...(session.turns || []).filter(turn => turn.role === "user").map(turn => turn.prompt)]
        .join(" ").toLocaleLowerCase().includes(search))
      .sort((left, right) => String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")));
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
    let previousGroup = "";
    const renderRow = (session, showDate = true) => {
      const active = session.id === state.currentAnalysisSessionId && document.getElementById('analysisTab').classList.contains('active') ? " is-active" : "";
      const workspaceLabel = analysisWorkspaceStatusLabel(session);
      const date = new Date(session.updatedAt);
      const group = date >= today ? "Today" : date >= yesterday ? "Yesterday" : "Older";
      const heading = showDate && group !== previousGroup ? `<h4 class="analysis-chat-date">${group}</h4>` : "";
      previousGroup = group;
      if (session.chatKind === 'query') return heading + callbacks.renderQueryChatCard(session);
      if (session.chatKind === 'pheno') return heading + callbacks.renderPhenoChatCard(session);
      const turns = session.turns || [];
      const last = turns.filter(turn => turn.role === "assistant").at(-1);
      const activeRun = turns.find(turn => turn.pending || ["queued", "running"].includes(turn.payload?.data?.job_status)
        || turn.payload?.data?.execution === "queued");
      const status = activeRun ? (activeRun.pending || activeRun.payload?.data?.job_status === "running" ? "Running" : "Queued")
        : last?.payload?.intent === "analysis_error" || last?.payload?.data?.job_status === "failed" ? "Failed" : workspaceLabel;
      return `
        ${heading}
        <div class="analysis-session-card${active}">
          <button type="button" class="analysis-session-main" data-analysis-session-id="${escapeHtml(session.id)}" ${active ? 'aria-current="true"' : ''} title="${escapeHtml(analysisSessionTitle(session))}">
            <div class="analysis-session-title"><span class="chat-type-icon" title="Analysis chat" aria-label="Analysis chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 3v17h17M9 16v-4m5 4V6m5 10V9"/></svg></span>${escapeHtml(analysisSessionTitle(session))}</div>
            ${status ? `<small class="analysis-chat-status">${escapeHtml(status)}</small>` : ''}
          </button>
          <details class="analysis-chat-menu"><summary aria-label="Actions for ${escapeHtml(analysisSessionTitle(session))}">⋯</summary><div>
            ${callbacks.chatOrganizationActions?.('analysis', session.id) || ''}
            <button type="button" data-analysis-session-rename="${escapeHtml(session.id)}">Rename</button>
            <button type="button" data-analysis-session-delete="${escapeHtml(session.id)}">Delete</button>
          </div></details>
        </div>
      `;
    };
    analysisSessionListEl.innerHTML = callbacks.organizeChats
      ? callbacks.organizeChats(ordered, renderRow, search)
      : ordered.map(session => renderRow(session)).join('') || '<div class="empty">No matching chats.</div>';
    addChatMenuIcons(analysisSessionListEl);
  }

  function renderCurrentAnalysisChatBar() {
    const session = currentAnalysisSession();
    if (analysisCurrentChatTitleEl) {
      analysisCurrentChatTitleEl.textContent = session ? analysisSessionTitle(session) : "New chat";
    }
    if (analysisCurrentChatMetaEl) {
      if (!session) {
        analysisCurrentChatMetaEl.textContent = "No turns yet.";
        return;
      }
      const turnCount = Array.isArray(session.turns) ? session.turns.length : 0;
      analysisCurrentChatMetaEl.textContent = `${analysisSessionScopeSummary(session)} · ${turnCount} turns · ${shortTimestamp(session.updatedAt)}`;
    }
  }

  function syncCurrentAnalysisSessionFromUi(options) {
    const settings = options || {};
    const session = currentAnalysisSession();
    if (!session) return;
    const activeScope = typeof currentDatasetSelectionKey === "function"
      ? String(currentDatasetSelectionKey() || "").trim() : "";
    // A reopened chat may be inspected from another workspace, but current
    // controls must not overwrite its original selections or result context.
    if (session.datasetId && activeScope && session.datasetId !== activeScope) return;
    session.promptDraft = analysisPromptEl.value;
    session.contextMode = state.analysisContextMode === "general" ? "general" : "workspace";
    if (!session.datasetId) {
      session.datasetId = typeof currentDatasetSelectionKey === "function"
        ? String(currentDatasetSelectionKey() || "").trim() : "";
    }
    session.catalogItemId = state.analysisSelectedCatalogItemId || "";
    session.measurement = state.analysisMeasurement || "";
    session.scriptDraft = state.analysisScriptDraft || {};
    session.scope = analysisSelectedPatientIdsEl.value.trim();
    session.scopeMetadata = state.analysisScopeMetadata && typeof state.analysisScopeMetadata === "object" ? state.analysisScopeMetadata : {};
    session.compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    session.compareScope = analysisCompareSelectedPatientIdsEl ? analysisCompareSelectedPatientIdsEl.value.trim() : "";
    session.compareScopeMetadata = state.analysisCompareScopeMetadata && typeof state.analysisCompareScopeMetadata === "object" ? state.analysisCompareScopeMetadata : {};
    session.savedCohortIdA = state.analysisSelectedSavedCohortId || "";
    session.savedCohortIdB = state.analysisCompareSavedCohortId || "";
    if (!session.dataDir) session.dataDir = dataDirEl && dataDirEl.value ? dataDirEl.value.trim() : "";
    session.history = state.analysisHistory;
    session.turns = state.analysisTurns;
    session.updatedAt = settings.touch === false ? session.updatedAt : nowIso();
    persistAnalysisSessions();
    void upsertAnalysisSessionToBackend(session);
    if (settings.render !== false) renderAnalysisSessionList();
  }

  function applyAnalysisSession(session) {
    state.analysisExamplesPinnedOpen = false;
    analysisPromptEl.value = session.promptDraft || "";
    state.analysisContextMode = session.contextMode === "general" ? "general" : "workspace";
    state.analysisSelectedCatalogItemId = String(session.catalogItemId || "").trim();
    state.analysisMeasurement = session.measurement || "";
    state.analysisScriptDraft = session.scriptDraft || {};
    analysisSelectedPatientIdsEl.value = session.scope || "";
    state.analysisScopeMetadata = session.scopeMetadata && typeof session.scopeMetadata === "object" ? session.scopeMetadata : {};
    if (analysisCompareModeEl) analysisCompareModeEl.checked = Boolean(session.compareMode);
    if (analysisCompareSelectedPatientIdsEl) analysisCompareSelectedPatientIdsEl.value = session.compareScope || "";
    state.analysisCompareScopeMetadata = session.compareScopeMetadata && typeof session.compareScopeMetadata === "object" ? session.compareScopeMetadata : {};
    state.analysisSelectedSavedCohortId = String(session.savedCohortIdA || "").trim();
    state.analysisCompareSavedCohortId = String(session.savedCohortIdB || "").trim();
    state.analysisHistory = Array.isArray(session.history) ? session.history : [];
    state.analysisTurns = Array.isArray(session.turns) ? session.turns : [];
    renderAnalysisCompareMode();
    renderAnalysisScopeSummary();
    renderAnalysisCompareScopeSummary();
    renderAnalysisStarterPrompts();
    renderAnalysisThread();
    if (typeof renderAnalysisContextMode === "function") renderAnalysisContextMode();
    if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
    const latestAssistantTurn = state.analysisTurns.slice().reverse().find((turn) => turn.role === "assistant" && turn.payload && !turn.pending);
    if (latestAssistantTurn && latestAssistantTurn.payload) {
      renderAnalysisMeta(latestAssistantTurn.payload);
    } else if (analysisMetaEl) {
      analysisMetaEl.innerHTML = "";
    }
    renderAnalysisSessionList();
  }

  function selectAnalysisSession(sessionId) {
    syncCurrentAnalysisSessionFromUi({ touch: false, render: false });
    const session = state.analysisSessions.find((item) => item.id === sessionId);
    if (!session) return;
    state.currentAnalysisSessionId = session.id;
    applyAnalysisSession(session);
    persistAnalysisSessions();
    const workspaceStatus = session.workspaceStatus && typeof session.workspaceStatus === "object" ? session.workspaceStatus : {};
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = workspaceStatus.state === "stale" || workspaceStatus.state === "unavailable"
      ? String(workspaceStatus.message || "This analysis session no longer matches the current workspace.")
      : `Loaded analysis session: ${analysisSessionTitle(session)}.`;
    addWorkspaceRestoreAction(analysisStatusEl, { scope: session.datasetId,
      currentScope: currentDatasetSelectionKey(), restore: callbacks.restoreWorkspace,
      reopen: () => selectAnalysisSession(sessionId) });
  }

  function createAndSelectAnalysisSession(overrides) {
    syncCurrentAnalysisSessionFromUi({ touch: false, render: false });
    const session = createAnalysisSession({
      ...(overrides || {}),
      datasetId: typeof currentDatasetSelectionKey === "function" ? String(currentDatasetSelectionKey() || "").trim() : "",
    });
    state.analysisSessions = state.analysisSessions.concat([session]);
    state.currentAnalysisSessionId = session.id;
    applyAnalysisSession(session);
    persistAnalysisSessions();
    void upsertAnalysisSessionToBackend(session);
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = "Started a new analysis session.";
  }

  function ensureAnalysisSessionsLoaded() {
    if (state.analysisSessions.length) return;
    let stored = null;
    try {
      stored = JSON.parse(window.localStorage.getItem(analysisSessionsStorageKey()) || "null");
    } catch (_error) {
      stored = null;
    }
    const sessions = stored && Array.isArray(stored.sessions) ? stored.sessions.map((item) => createAnalysisSession(item)) : [];
    state.analysisSessions = sessions.length ? sessions : [createAnalysisSession()];
    state.currentAnalysisSessionId = stored && typeof stored.currentId === "string" ? stored.currentId : state.analysisSessions[0].id;
    if (!state.analysisSessions.some((session) => session.id === state.currentAnalysisSessionId)) {
      state.currentAnalysisSessionId = state.analysisSessions[0].id;
    }
    applyAnalysisSession(currentAnalysisSession());
  }

  function resetAnalysisSessionsAfterBulkDelete() {
    try {
      window.localStorage.removeItem(analysisSessionsStorageKey());
    } catch (_error) {
    }
    const session = createAnalysisSession({ dataDir: dataDirEl && dataDirEl.value ? dataDirEl.value.trim() : "" });
    state.analysisSessions = [session];
    state.currentAnalysisSessionId = session.id;
    applyAnalysisSession(session);
    persistAnalysisSessions();
  }

  function renameAnalysisSession(sessionId) {
    const session = state.analysisSessions.find((item) => item.id === sessionId);
    if (!session) return;
    const nextTitle = window.prompt("Analysis session title", String(session.title || analysisSessionTitle(session)));
    if (nextTitle === null) return;
    session.title = String(nextTitle || "").trim();
    session.updatedAt = nowIso();
    persistAnalysisSessions();
    renderAnalysisSessionList();
    if (session.id === state.currentAnalysisSessionId) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = `Renamed analysis session to "${analysisSessionTitle(session)}".`;
    }
    void renameAnalysisSessionInBackend(session.id, session.title);
    void upsertAnalysisSessionToBackend(session);
  }

  async function confirmDeleteAnalysisSession(deleteGeneratedData) {
    const sessionId = String(pendingDeleteSessionId || "").trim();
    if (!sessionId || deleteInFlight) return;
    const session = state.analysisSessions.find((item) => item.id === sessionId);
    if (!session) {
      closeDeleteDialog();
      return;
    }
    setDeleteDialogBusy(true);
    resetDeleteDialogStatus();
    let missingOnBackend = false;
    let deletePayload = null;
    try {
      deletePayload = await deleteAnalysisSessionFromBackend(sessionId, {
        deleteGeneratedData,
        keepGeneratedJobs: !deleteGeneratedData,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to delete analysis session.";
      if (message === "Analysis session not found.") {
        missingOnBackend = true;
      } else {
        if (analysisSessionDeleteStatusEl) {
          analysisSessionDeleteStatusEl.className = "query-status error";
          analysisSessionDeleteStatusEl.textContent = message;
        }
        setDeleteDialogBusy(false);
        return;
      }
    }
    if (deleteGeneratedData && deletePayload && Number(deletePayload.deleted_job_count || 0) > 0 && Array.isArray(state.recentJobs)) {
      state.recentJobs = state.recentJobs.filter((item) => String(item && item.analysis_session_id ? item.analysis_session_id : "").trim() !== sessionId);
    }
    state.analysisSessions = state.analysisSessions.filter((item) => item.id !== sessionId);
    if (!state.analysisSessions.length) {
      createAndSelectAnalysisSession({ dataDir: dataDirEl.value.trim() });
    } else if (state.currentAnalysisSessionId === sessionId) {
      state.currentAnalysisSessionId = state.analysisSessions[0].id;
      applyAnalysisSession(currentAnalysisSession());
    } else {
      renderAnalysisSessionList();
      persistAnalysisSessions();
    }
    persistAnalysisSessions();
    setDeleteDialogBusy(false);
    closeDeleteDialog();
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = missingOnBackend
      ? "Removed stale local analysis session."
      : deleteGeneratedData
        ? "Analysis session and generated data deleted."
        : "Analysis session deleted.";
  }

  function deleteAnalysisSessionById(sessionId) {
    openDeleteDialog(sessionId);
  }

  function prepareAnalysisSessionForDataDir(nextDataDir) {
    ensureAnalysisSessionsLoaded();
    const session = currentAnalysisSession();
    if (!session) return;
    const normalizedNext = String(nextDataDir || "").trim();
    const normalizedCurrent = String(session.dataDir || "").trim();
    const hasWork = (session.turns || []).length > 0 || (session.history || []).length > 0;
    const hasDatasetScope = Boolean(
      String(session.scope || "").trim()
      || String(session.compareScope || "").trim()
      || String(session.savedCohortIdA || "").trim()
      || String(session.savedCohortIdB || "").trim()
      || String(session.catalogItemId || "").trim()
      || Object.keys(session.scopeMetadata || {}).length
      || Object.keys(session.compareScopeMetadata || {}).length
    );
    if (normalizedCurrent !== normalizedNext && (hasWork || hasDatasetScope)) {
      createAndSelectAnalysisSession({ dataDir: normalizedNext, promptDraft: analysisPromptEl.value || "Summarize the main clinical patterns in this cohort and tell me what stands out." });
      return;
    }
    session.dataDir = normalizedNext;
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  analysisSessionDeleteCloseBtnEl && analysisSessionDeleteCloseBtnEl.addEventListener("click", () => {
    closeDeleteDialog();
  });
  analysisSessionDeleteOnlyBtnEl && analysisSessionDeleteOnlyBtnEl.addEventListener("click", () => {
    void confirmDeleteAnalysisSession(false);
  });
  analysisSessionDeleteAllBtnEl && analysisSessionDeleteAllBtnEl.addEventListener("click", () => {
    void confirmDeleteAnalysisSession(true);
  });
  analysisSessionDeleteDialogEl && analysisSessionDeleteDialogEl.addEventListener("click", (event) => {
    const closeTrigger = event.target.closest("[data-analysis-session-delete-close='true']");
    if (closeTrigger && analysisSessionDeleteDialogEl.contains(closeTrigger)) {
      closeDeleteDialog();
    }
  });

  return {
    async flushCurrentForProject() {
      if (!state.currentDatasetIds.length) return;
      ensureAnalysisSessionsLoaded();
      syncCurrentAnalysisSessionFromUi({render: false});
      const session = currentAnalysisSession();
      if (session) await upsertAnalysisSessionToBackend(session, true);
      return session;
    },
    persistAnalysisSessions,
    loadAnalysisSessionsFromBackend,
    renderAnalysisSessionList,
    renderCurrentAnalysisChatBar,
    syncCurrentAnalysisSessionFromUi,
    applyAnalysisSession,
    selectAnalysisSession,
    createAndSelectAnalysisSession,
    ensureAnalysisSessionsLoaded,
    resetAnalysisSessionsAfterBulkDelete,
    forgetDeletedChats(ids) {
      state.analysisSessions = state.analysisSessions.filter(item => !ids.includes(item.id));
      if (!state.analysisSessions.length) resetAnalysisSessionsAfterBulkDelete();
      else if (ids.includes(state.currentAnalysisSessionId)) {
        state.currentAnalysisSessionId = state.analysisSessions[0].id;
        applyAnalysisSession(state.analysisSessions[0]);
      }
      persistAnalysisSessions();
      renderAnalysisSessionList();
    },
    renameAnalysisSession,
    deleteAnalysisSessionById,
    prepareAnalysisSessionForDataDir,
  };
}
