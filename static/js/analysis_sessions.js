export function createAnalysisSessionsUi(ctx) {
  const { refs, helpers, callbacks, state, constants } = ctx;
  const {
    analysisSessionListEl,
    analysisPromptEl,
    analysisSelectedPatientIdsEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
    analysisStatusEl,
    analysisMetaEl,
    dataDirEl,
  } = refs;
  const { escapeHtml, shortTimestamp, nowIso } = helpers;
  const {
    createAnalysisSession,
    currentAnalysisSession,
    getStorageNamespace,
    renderAnalysisCompareMode,
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
    renderAnalysisStarterPrompts,
    renderAnalysisThread,
    renderAnalysisMeta,
  } = callbacks;
  const { ANALYSIS_SESSIONS_STORAGE_KEY } = constants;

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
      || "New analysis";
    const trimmed = String(raw).trim();
    if (!trimmed) return "New analysis";
    return trimmed.length > 56 ? `${trimmed.slice(0, 56)}...` : trimmed;
  }

  function analysisSessionScopeSummary(session) {
    const scopeCount = String(session.scope || "").split(",").map((item) => item.trim()).filter(Boolean).length;
    const compareCount = String(session.compareScope || "").split(",").map((item) => item.trim()).filter(Boolean).length;
    if (session.compareMode) {
      const aLabel = scopeCount ? `${scopeCount} in A` : "full cohort in A";
      const bLabel = compareCount ? `${compareCount} in B` : "full cohort in B";
      return `${aLabel} vs ${bLabel}`;
    }
    return scopeCount ? `${scopeCount} IDs in scope` : "Full cohort";
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

  async function upsertAnalysisSessionToBackend(session) {
    try {
      await fetch("/analysis-sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: session.id,
          title: session.title || "",
          data_dir: session.dataDir || "",
          prompt_draft: session.promptDraft || "",
          scope: session.scope || "",
          compare_mode: Boolean(session.compareMode),
          compare_scope: session.compareScope || "",
          history: Array.isArray(session.history) ? session.history : [],
          turns: Array.isArray(session.turns) ? session.turns : [],
          updated_at: session.updatedAt || "",
        }),
      });
    } catch (_error) {
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

  async function deleteAnalysisSessionFromBackend(sessionId) {
    try {
      await fetch(`/analysis-sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    } catch (_error) {
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
        dataDir: item.data_dir,
        promptDraft: item.prompt_draft,
        scope: item.scope,
        compareMode: item.compare_mode,
        compareScope: item.compare_scope,
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
    if (!state.analysisSessions.length) {
      analysisSessionListEl.innerHTML = '<div class="empty">No analysis sessions yet.</div>';
      return;
    }
    const ordered = state.analysisSessions.slice().sort((left, right) => String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")));
    analysisSessionListEl.innerHTML = ordered.map((session) => {
      const dataDir = String(session.dataDir || "").trim();
      const dirLabel = dataDir ? dataDir.split("/").filter(Boolean).slice(-1)[0] : "No dataset";
      const turnCount = Array.isArray(session.turns) ? session.turns.length : 0;
      const active = session.id === state.currentAnalysisSessionId ? " is-active" : "";
      return `
        <div class="analysis-session-card${active}">
          <button type="button" class="analysis-session-main" data-analysis-session-id="${escapeHtml(session.id)}">
            <div class="analysis-session-title">${escapeHtml(analysisSessionTitle(session))}</div>
            <div class="analysis-session-meta">
              <div>${escapeHtml(dirLabel)}</div>
              <div>${escapeHtml(analysisSessionScopeSummary(session))}</div>
              <div>${escapeHtml(String(turnCount))} turns • ${escapeHtml(shortTimestamp(session.updatedAt))}</div>
            </div>
          </button>
          <div class="analysis-session-actions">
            <button type="button" class="analysis-session-icon" data-analysis-session-rename="${escapeHtml(session.id)}" title="Rename analysis">✎</button>
            <button type="button" class="analysis-session-icon" data-analysis-session-delete="${escapeHtml(session.id)}" title="Delete analysis">×</button>
          </div>
        </div>
      `;
    }).join("");
  }

  function syncCurrentAnalysisSessionFromUi(options) {
    const settings = options || {};
    const session = currentAnalysisSession();
    if (!session) return;
    session.promptDraft = analysisPromptEl.value;
    session.scope = analysisSelectedPatientIdsEl.value.trim();
    session.compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    session.compareScope = analysisCompareSelectedPatientIdsEl ? analysisCompareSelectedPatientIdsEl.value.trim() : "";
    session.dataDir = dataDirEl && dataDirEl.value ? dataDirEl.value.trim() : session.dataDir;
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
    analysisSelectedPatientIdsEl.value = session.scope || "";
    if (analysisCompareModeEl) analysisCompareModeEl.checked = Boolean(session.compareMode);
    if (analysisCompareSelectedPatientIdsEl) analysisCompareSelectedPatientIdsEl.value = session.compareScope || "";
    state.analysisHistory = Array.isArray(session.history) ? session.history : [];
    state.analysisTurns = Array.isArray(session.turns) ? session.turns : [];
    renderAnalysisCompareMode();
    renderAnalysisScopeSummary();
    renderAnalysisCompareScopeSummary();
    renderAnalysisStarterPrompts();
    renderAnalysisThread();
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
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = `Loaded analysis session: ${analysisSessionTitle(session)}.`;
  }

  function createAndSelectAnalysisSession(overrides) {
    syncCurrentAnalysisSessionFromUi({ touch: false, render: false });
    const session = createAnalysisSession(overrides);
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

  function deleteAnalysisSessionById(sessionId) {
    const session = state.analysisSessions.find((item) => item.id === sessionId);
    if (!session) return;
    const confirmed = window.confirm(`Delete analysis session "${analysisSessionTitle(session)}"?`);
    if (!confirmed) return;
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
    void deleteAnalysisSessionFromBackend(sessionId);
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = "Analysis session deleted.";
  }

  function prepareAnalysisSessionForDataDir(nextDataDir) {
    ensureAnalysisSessionsLoaded();
    const session = currentAnalysisSession();
    if (!session) return;
    const normalizedNext = String(nextDataDir || "").trim();
    const normalizedCurrent = String(session.dataDir || "").trim();
    const hasWork = (session.turns || []).length > 0 || (session.history || []).length > 0;
    if (normalizedCurrent && normalizedCurrent !== normalizedNext && hasWork) {
      createAndSelectAnalysisSession({ dataDir: normalizedNext, promptDraft: analysisPromptEl.value || "Summarize the main clinical patterns in this cohort and tell me what stands out." });
      return;
    }
    session.dataDir = normalizedNext;
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  return {
    persistAnalysisSessions,
    loadAnalysisSessionsFromBackend,
    renderAnalysisSessionList,
    syncCurrentAnalysisSessionFromUi,
    applyAnalysisSession,
    selectAnalysisSession,
    createAndSelectAnalysisSession,
    ensureAnalysisSessionsLoaded,
    renameAnalysisSession,
    deleteAnalysisSessionById,
    prepareAnalysisSessionForDataDir,
  };
}
