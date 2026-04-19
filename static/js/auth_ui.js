export function createAuthUi(ctx) {
  const { refs, state, callbacks } = ctx;
  const {
    appShellEl,
    authGateEl,
    authBrandHeroEl,
    authGateStatusEl,
    heroAuthUtilityEl,
    heroAuthIdentityEl,
    heroLogoutBtnEl,
    datasetsTabBtnEl,
    dataTabBtnEl,
    usersTabBtnEl,
    jobsDrawerBtnEl,
    datasetAdminControlsEl,
    usersCreateCardEl,
    loadStatusEl,
    dataDirEl,
    patientsEl,
    detailEl,
    dashboardEl,
    molecularDashboardCardsEl,
    molecularDashboardStatusEl,
    authUsernameEl,
    authPasswordEl,
  } = refs;
  const {
    renderLoadButtonState,
    renderJobsDrawer,
    renderGlobalContext,
    currentTabName,
    setActiveTab,
    loadAuthUsers,
    loadRecentJobs,
    loadSavedCohorts,
    loadAnalysisCatalog,
    renderAnalysisSessionList,
    renderAnalysisThread,
    renderAnalysisCatalog,
    createAnalysisSession,
    ensureAnalysisSessionsLoaded,
    loadAnalysisSessionsFromBackend,
    applyAnalysisSession,
    loadDatasets,
    loadPatients,
  } = callbacks;

  function canManageDataset() {
    if (!state.authState.enabled) return true;
    if (!(state.authState.authenticated && state.authState.user)) {
      return false;
    }
    if (String(state.authState.user.role || "").trim().toLowerCase() === "admin") {
      return true;
    }
    const groups = Array.isArray(state.authState.user.groups) ? state.authState.user.groups : [];
    return groups.some((group) => String(group || "").trim().toLowerCase() === "admin");
  }

  function isWorkspaceAccessible() {
    return !state.authState.enabled || Boolean(state.authState.authenticated && state.authState.user);
  }

  function clearLoadedWorkspaceForSignedOutState() {
    state.currentPatients = [];
    state.selectedPatientId = null;
    state.dashboardSummaryState = null;
    state.molecularDatasetsState = [];
    state.selectedMolecularDatasets = [];
    state.savedCohorts = [];
    if (patientsEl) {
      patientsEl.innerHTML = '<div class="empty">Sign in to access the shared clinical workspace.</div>';
    }
    if (detailEl) {
      detailEl.innerHTML = '<div class="empty">Patient workspace hidden until you sign in.</div>';
    }
    if (dashboardEl) {
      dashboardEl.innerHTML = '<div class="empty">Clinical dashboard hidden until you sign in.</div>';
    }
    if (molecularDashboardCardsEl) {
      molecularDashboardCardsEl.innerHTML = '<div class="empty">Molecular dashboard hidden until you sign in.</div>';
    }
    if (molecularDashboardStatusEl) {
      molecularDashboardStatusEl.className = "query-status";
      molecularDashboardStatusEl.textContent = "Sign in to access shared molecular datasets.";
    }
  }

  function updateLoadButtonAvailability() {
    if (!refs.loadBtnEl) return;
    const blocked = !isWorkspaceAccessible();
    refs.loadBtnEl.disabled = Boolean(state.loadInFlight || blocked);
    renderLoadButtonState();
    if (blocked && !state.loadInFlight && loadStatusEl) {
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = "Sign in to load your authorized dataset scope.";
    }
  }

  function renderAuthUi() {
    if (!state.authState.enabled) {
      authBrandHeroEl && authBrandHeroEl.classList.add("is-hidden");
      authGateEl && authGateEl.classList.add("is-hidden");
      appShellEl && appShellEl.classList.remove("is-hidden");
      heroAuthUtilityEl && heroAuthUtilityEl.classList.remove("is-hidden");
      heroLogoutBtnEl && heroLogoutBtnEl.classList.add("is-hidden");
      jobsDrawerBtnEl && jobsDrawerBtnEl.classList.remove("is-hidden");
      if (heroAuthIdentityEl) {
        heroAuthIdentityEl.textContent = "Local user";
      }
      datasetAdminControlsEl && datasetAdminControlsEl.classList.remove("is-hidden");
      datasetsTabBtnEl && datasetsTabBtnEl.classList.remove("is-hidden");
      dataTabBtnEl && dataTabBtnEl.classList.remove("is-hidden");
      usersTabBtnEl && usersTabBtnEl.classList.remove("is-hidden");
      usersCreateCardEl && usersCreateCardEl.classList.remove("is-hidden");
      updateLoadButtonAvailability();
      renderJobsDrawer();
      renderGlobalContext();
      return;
    }
    const authenticated = Boolean(state.authState.authenticated && state.authState.user);
    authBrandHeroEl && authBrandHeroEl.classList.toggle("is-hidden", authenticated);
    authGateEl && authGateEl.classList.toggle("is-hidden", authenticated);
    appShellEl && appShellEl.classList.toggle("is-hidden", !authenticated);
    heroAuthUtilityEl && heroAuthUtilityEl.classList.toggle("is-hidden", !authenticated);
    heroLogoutBtnEl && heroLogoutBtnEl.classList.toggle("is-hidden", !authenticated);
    if (authenticated) {
      if (heroAuthIdentityEl) {
        heroAuthIdentityEl.textContent = `${state.authState.user.display_name || state.authState.user.username} (${state.authState.user.role || "user"})`;
      }
      if (authGateStatusEl) {
        authGateStatusEl.textContent = "Enter your credentials to open your private workspace.";
      }
      const admin = canManageDataset();
      datasetsTabBtnEl && datasetsTabBtnEl.classList.remove("is-hidden");
      dataTabBtnEl && dataTabBtnEl.classList.toggle("is-hidden", !admin);
      usersTabBtnEl && usersTabBtnEl.classList.toggle("is-hidden", !admin);
      datasetAdminControlsEl && datasetAdminControlsEl.classList.toggle("is-hidden", !admin);
      usersCreateCardEl && usersCreateCardEl.classList.toggle("is-hidden", !admin);
      if (!admin && (currentTabName() === "data" || currentTabName() === "users")) {
        setActiveTab("datasets");
      }
      if (admin) {
        void loadAuthUsers();
      }
    } else {
      if (heroAuthIdentityEl) {
        heroAuthIdentityEl.textContent = "Signed out";
      }
      datasetsTabBtnEl && datasetsTabBtnEl.classList.add("is-hidden");
      dataTabBtnEl && dataTabBtnEl.classList.add("is-hidden");
      usersTabBtnEl && usersTabBtnEl.classList.add("is-hidden");
      datasetAdminControlsEl && datasetAdminControlsEl.classList.add("is-hidden");
      usersCreateCardEl && usersCreateCardEl.classList.add("is-hidden");
      if (authGateStatusEl) {
        authGateStatusEl.textContent = "Enter your credentials to open your private workspace.";
      }
    }
    updateLoadButtonAvailability();
    renderJobsDrawer();
    renderGlobalContext();
  }

  async function refreshUserWorkspaceState() {
    if (!isWorkspaceAccessible()) {
      state.analysisSessions = [];
      state.currentAnalysisSessionId = "";
      state.analysisHistory = [];
      state.analysisTurns = [];
      state.analysisCatalogItems = [];
      state.analysisCatalogWorkspace = null;
      renderAnalysisSessionList();
      renderAnalysisThread();
      renderAnalysisCatalog();
      return;
    }
    await loadSavedCohorts();
    await loadAnalysisCatalog();
    state.analysisSessions = [];
    state.currentAnalysisSessionId = "";
    ensureAnalysisSessionsLoaded();
    const loaded = await loadAnalysisSessionsFromBackend();
    if (!loaded) {
      const currentDataDir = dataDirEl && dataDirEl.value ? dataDirEl.value.trim() : "";
      state.analysisSessions = [createAnalysisSession({ dataDir: currentDataDir })];
      state.currentAnalysisSessionId = state.analysisSessions[0].id;
      applyAnalysisSession(state.analysisSessions[0]);
    }
  }

  async function fetchAuthStatus() {
    try {
      const response = await fetch("/auth/me");
      if (!response.ok) throw new Error("Unable to check authentication.");
      const payload = await response.json();
      state.authState = {
        enabled: Boolean(payload.enabled),
        authenticated: Boolean(payload.authenticated),
        user: payload.user || null,
      };
    } catch (_error) {
      state.authState = {
        enabled: false,
        authenticated: true,
        user: { username: "local", role: "admin", display_name: "Local user" },
      };
    }
    renderAuthUi();
    if (!state.authState.enabled || state.authState.authenticated) {
      void loadRecentJobs({ silent: true });
    } else {
      state.recentJobs = [];
      renderJobsDrawer();
    }
  }

  async function loginLocal() {
    if (!state.authState.enabled) return;
    const username = String(authUsernameEl && authUsernameEl.value ? authUsernameEl.value : "").trim();
    const password = String(authPasswordEl && authPasswordEl.value ? authPasswordEl.value : "");
    if (authGateStatusEl) {
      authGateStatusEl.textContent = "Signing in...";
    }
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        const raw = await response.text();
        let message = "Sign-in failed.";
        try {
          const parsed = JSON.parse(raw);
          message = parsed.detail || parsed.message || message;
        } catch (_error) {
          message = raw || message;
        }
        throw new Error(message);
      }
      if (authPasswordEl) authPasswordEl.value = "";
      await fetchAuthStatus();
      await loadDatasets();
      await refreshUserWorkspaceState();
      await loadPatients({ respectAdminGate: false });
    } catch (error) {
      if (authGateStatusEl) {
        authGateStatusEl.textContent = error && error.message ? error.message : "Sign-in failed.";
      }
    }
  }

  async function logoutLocal() {
    try {
      await fetch("/auth/logout", { method: "POST" });
    } catch (_error) {
    }
    await fetchAuthStatus();
    await loadDatasets();
    clearLoadedWorkspaceForSignedOutState();
    if (loadStatusEl) {
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = "Signed out.";
    }
    await refreshUserWorkspaceState();
  }

  return {
    canManageDataset,
    isWorkspaceAccessible,
    clearLoadedWorkspaceForSignedOutState,
    updateLoadButtonAvailability,
    renderAuthUi,
    refreshUserWorkspaceState,
    fetchAuthStatus,
    loginLocal,
    logoutLocal,
  };
}
