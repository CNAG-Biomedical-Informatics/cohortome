export function createAuthUi(ctx) {
  const { refs, state, callbacks } = ctx;
  const {
    appShellEl,
    authGateEl,
    authBrandHeroEl,
    authGateStatusEl,
    authLoginLabelEl,
    authOidcFormEl,
    authOidcLoginLabelEl,
    heroAuthUtilityEl,
    heroAuthIdentityEl,
    heroLogoutBtnEl,
    datasetsTabBtnEl,
    dataTabBtnEl,
    usersTabBtnEl,
    modelsTabBtnEl,
    jobsDrawerBtnEl,
    runHistoryDrawerBtnEl,
    datasetAdminControlsEl,
    usersCreateCardEl,
    loadStatusEl,
    dataDirEl,
    patientsEl,
    detailEl,
    dashboardEl,
    dashboardTimelineEl,
    molecularDashboardCardsEl,
    molecularDashboardStatusEl,
    authUsernameEl,
    authPasswordEl,
    authPasswordResetPromptEl,
    authForgotPasswordBtnEl,
    authPasswordResetUnavailableEl,
    authPasswordResetPanelEl,
    authPasswordResetRequestFormEl,
    authPasswordResetConfirmFormEl,
    authPasswordResetIdentifierEl,
    authPasswordResetNewPasswordEl,
    authPasswordResetConfirmPasswordEl,
    authPasswordResetStatusEl,
  } = refs;
  const {
    renderLoadButtonState,
    renderJobsDrawer,
    renderRunHistoryDrawer,
    renderGlobalContext,
    currentTabName,
    setActiveTab,
    loadAuthUsers,
    loadRecentJobs,
    loadRunHistory,
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
    prepareStartupWorkspaceSelection,
    startupDefaultDatasetIds,
    loadPatients,
    loadUserSettings,
    applyUserSettings,
    loadLmStatus,
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

  function passwordResetTokenFromLocation() {
    try {
      return new URLSearchParams(window.location.search).get("password_reset_token") || "";
    } catch (_error) {
      return "";
    }
  }

  function clearPasswordResetTokenFromLocation() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("password_reset_token");
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    } catch (_error) {
    }
  }

  function setPasswordResetPanelOpen(open, mode = "request") {
    const enabled = Boolean(state.authState && state.authState.passwordResetEnabled);
    const shouldOpen = Boolean(open && enabled);
    authPasswordResetPanelEl && authPasswordResetPanelEl.classList.toggle("is-hidden", !shouldOpen);
    authPasswordResetPromptEl && authPasswordResetPromptEl.classList.toggle("is-hidden", shouldOpen || !enabled);
    authPasswordResetRequestFormEl && authPasswordResetRequestFormEl.classList.toggle("is-hidden", mode !== "request");
    authPasswordResetConfirmFormEl && authPasswordResetConfirmFormEl.classList.toggle("is-hidden", mode !== "confirm");
    if (shouldOpen && authPasswordResetStatusEl) {
      authPasswordResetStatusEl.className = "section-note";
      authPasswordResetStatusEl.textContent = mode === "confirm"
        ? "Enter a new password for this account."
        : "Enter your username or email to receive a reset link.";
    }
  }

  function renderPasswordResetUi() {
    const enabled = Boolean(state.authState && state.authState.passwordResetEnabled);
    const authenticated = Boolean(state.authState && state.authState.authenticated && state.authState.user);
    const mode = String(state.authState && state.authState.mode || "none");
    const localLoginEnabled = Boolean(state.authState && state.authState.localLoginEnabled);
    const token = passwordResetTokenFromLocation();
    if (mode === "oidc" && !localLoginEnabled) {
      authPasswordResetUnavailableEl && authPasswordResetUnavailableEl.classList.add("is-hidden");
      authPasswordResetPromptEl && authPasswordResetPromptEl.classList.add("is-hidden");
      setPasswordResetPanelOpen(false);
      return;
    }
    authPasswordResetUnavailableEl && authPasswordResetUnavailableEl.classList.toggle("is-hidden", authenticated || enabled);
    if (!enabled || authenticated) {
      setPasswordResetPanelOpen(false);
      authPasswordResetPromptEl && authPasswordResetPromptEl.classList.add("is-hidden");
      return;
    }
    if (token) {
      setPasswordResetPanelOpen(true, "confirm");
      return;
    }
    authPasswordResetPromptEl && authPasswordResetPromptEl.classList.remove("is-hidden");
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
    if (dashboardTimelineEl) {
      dashboardTimelineEl.innerHTML = '<div class="empty">Timeline hidden until you sign in.</div>';
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
    const mode = String(state.authState && state.authState.mode || (state.authState.enabled ? "local" : "none"));
    const provider = String(state.authState && state.authState.provider || mode || "local");
    const oidcMode = mode === "oidc";
    const localLoginEnabled = Boolean(state.authState && state.authState.localLoginEnabled);
    const showLocalLogin = !oidcMode || localLoginEnabled;
    authOidcFormEl && authOidcFormEl.classList.toggle("is-hidden", !oidcMode);
    if (authOidcLoginLabelEl) {
      authOidcLoginLabelEl.textContent = `Sign in with ${provider}`;
    }
    authUsernameEl && authUsernameEl.classList.toggle("is-hidden", !showLocalLogin);
    authPasswordEl && authPasswordEl.classList.toggle("is-hidden", !showLocalLogin);
    if (authLoginLabelEl) {
      authLoginLabelEl.textContent = "Sign in with password";
    }
    if (!state.authState.enabled) {
      authBrandHeroEl && authBrandHeroEl.classList.add("is-hidden");
      authGateEl && authGateEl.classList.add("is-hidden");
      appShellEl && appShellEl.classList.remove("is-hidden");
      heroAuthUtilityEl && heroAuthUtilityEl.classList.remove("is-hidden");
      heroLogoutBtnEl && heroLogoutBtnEl.classList.add("is-hidden");
      jobsDrawerBtnEl && jobsDrawerBtnEl.classList.remove("is-hidden");
      runHistoryDrawerBtnEl && runHistoryDrawerBtnEl.classList.remove("is-hidden");
      if (heroAuthIdentityEl) {
        heroAuthIdentityEl.textContent = "Local user";
      }
      datasetAdminControlsEl && datasetAdminControlsEl.classList.remove("is-hidden");
      datasetsTabBtnEl && datasetsTabBtnEl.classList.remove("is-hidden");
      dataTabBtnEl && dataTabBtnEl.classList.remove("is-hidden");
      usersTabBtnEl && usersTabBtnEl.classList.remove("is-hidden");
      modelsTabBtnEl && modelsTabBtnEl.classList.remove("is-hidden");
      usersCreateCardEl && usersCreateCardEl.classList.remove("is-hidden");
      updateLoadButtonAvailability();
      renderJobsDrawer();
      renderGlobalContext();
      renderPasswordResetUi();
      return;
    }
    const authenticated = Boolean(state.authState.authenticated && state.authState.user);
    authBrandHeroEl && authBrandHeroEl.classList.toggle("is-hidden", authenticated);
    authGateEl && authGateEl.classList.toggle("is-hidden", authenticated);
    appShellEl && appShellEl.classList.toggle("is-hidden", !authenticated);
    heroAuthUtilityEl && heroAuthUtilityEl.classList.toggle("is-hidden", !authenticated);
      heroLogoutBtnEl && heroLogoutBtnEl.classList.toggle("is-hidden", !authenticated);
      jobsDrawerBtnEl && jobsDrawerBtnEl.classList.toggle("is-hidden", !authenticated);
      runHistoryDrawerBtnEl && runHistoryDrawerBtnEl.classList.toggle("is-hidden", !authenticated);
    if (authenticated) {
      if (heroAuthIdentityEl) {
        heroAuthIdentityEl.textContent = `${state.authState.user.display_name || state.authState.user.username} (${state.authState.user.role || "user"})`;
      }
      if (authGateStatusEl) {
        authGateStatusEl.textContent = oidcMode
          ? (localLoginEnabled ? `Use ${provider} or a local password to open your private workspace.` : `Use ${provider} to open your private workspace.`)
          : "Enter your credentials to open your private workspace.";
      }
      const admin = canManageDataset();
      datasetsTabBtnEl && datasetsTabBtnEl.classList.remove("is-hidden");
      dataTabBtnEl && dataTabBtnEl.classList.toggle("is-hidden", !admin);
      usersTabBtnEl && usersTabBtnEl.classList.toggle("is-hidden", !admin);
      modelsTabBtnEl && modelsTabBtnEl.classList.toggle("is-hidden", !admin);
      datasetAdminControlsEl && datasetAdminControlsEl.classList.toggle("is-hidden", !admin);
      usersCreateCardEl && usersCreateCardEl.classList.toggle("is-hidden", !admin);
      if (!admin && (currentTabName() === "data" || currentTabName() === "users" || currentTabName() === "models")) {
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
      modelsTabBtnEl && modelsTabBtnEl.classList.add("is-hidden");
      datasetAdminControlsEl && datasetAdminControlsEl.classList.add("is-hidden");
      usersCreateCardEl && usersCreateCardEl.classList.add("is-hidden");
      if (authGateStatusEl) {
        authGateStatusEl.textContent = oidcMode
          ? (localLoginEnabled ? `Use ${provider} or a local password to open your private workspace.` : `Use ${provider} to open your private workspace.`)
          : "Enter your credentials to open your private workspace.";
      }
    }
    updateLoadButtonAvailability();
    renderJobsDrawer();
    if (typeof renderRunHistoryDrawer === "function") {
      renderRunHistoryDrawer();
    }
    renderGlobalContext();
    renderPasswordResetUi();
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
        mode: String(payload.mode || (payload.enabled ? "local" : "none")),
        provider: String(payload.provider || payload.mode || "local"),
        authenticated: Boolean(payload.authenticated),
        localLoginEnabled: Boolean(payload.local_login_enabled),
        passwordResetEnabled: Boolean(payload.password_reset_enabled),
        user: payload.user || null,
      };
    } catch (_error) {
      state.authState = {
        enabled: false,
        mode: "none",
        provider: "none",
        authenticated: true,
        localLoginEnabled: false,
        passwordResetEnabled: false,
        user: { username: "local", role: "admin", display_name: "Local user" },
      };
    }
    renderAuthUi();
    if (!state.authState.enabled || state.authState.authenticated) {
      void loadRecentJobs({ silent: true });
      if (typeof loadRunHistory === "function") {
        void loadRunHistory({ silent: true });
      }
    } else {
      state.recentJobs = [];
      state.runHistory = [];
      renderJobsDrawer();
      if (typeof renderRunHistoryDrawer === "function") {
        renderRunHistoryDrawer();
      }
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
      if (typeof loadUserSettings === "function") {
        await loadUserSettings({ applyNavigation: false });
      }
      if (typeof loadLmStatus === "function") {
        await loadLmStatus();
      }
      await loadDatasets();
      prepareStartupWorkspaceSelection();
      await loadPatients({ respectAdminGate: false, targetDatasetIds: startupDefaultDatasetIds() });
      await refreshUserWorkspaceState();
      if (typeof applyUserSettings === "function") {
        applyUserSettings({ applyNavigation: true });
      }
    } catch (error) {
      if (authGateStatusEl) {
        authGateStatusEl.textContent = error && error.message ? error.message : "Sign-in failed.";
      }
    }
  }

  function loginOidc() {
    window.location.href = "/auth/login";
  }

  async function requestPasswordReset() {
    if (!state.authState.enabled || !state.authState.passwordResetEnabled) return;
    const identifier = String(authPasswordResetIdentifierEl && authPasswordResetIdentifierEl.value ? authPasswordResetIdentifierEl.value : "").trim();
    if (authPasswordResetStatusEl) {
      authPasswordResetStatusEl.className = "section-note";
      authPasswordResetStatusEl.textContent = "Sending reset instructions...";
    }
    try {
      const response = await fetch("/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || "Unable to request password reset.");
      }
      if (authPasswordResetStatusEl) {
        authPasswordResetStatusEl.className = "section-note";
        authPasswordResetStatusEl.textContent = payload.message || "If an account exists, reset instructions were sent.";
      }
    } catch (error) {
      if (authPasswordResetStatusEl) {
        authPasswordResetStatusEl.className = "section-note is-warning";
        authPasswordResetStatusEl.textContent = error && error.message ? error.message : "Unable to request password reset.";
      }
    }
  }

  async function confirmPasswordReset() {
    if (!state.authState.enabled || !state.authState.passwordResetEnabled) return;
    const token = passwordResetTokenFromLocation();
    const password = String(authPasswordResetNewPasswordEl && authPasswordResetNewPasswordEl.value ? authPasswordResetNewPasswordEl.value : "");
    const confirmPassword = String(authPasswordResetConfirmPasswordEl && authPasswordResetConfirmPasswordEl.value ? authPasswordResetConfirmPasswordEl.value : "");
    if (!password || password !== confirmPassword) {
      if (authPasswordResetStatusEl) {
        authPasswordResetStatusEl.className = "section-note is-warning";
        authPasswordResetStatusEl.textContent = "Enter the same new password twice.";
      }
      return;
    }
    if (authPasswordResetStatusEl) {
      authPasswordResetStatusEl.className = "section-note";
      authPasswordResetStatusEl.textContent = "Resetting password...";
    }
    try {
      const response = await fetch("/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || "Unable to reset password.");
      }
      if (authPasswordResetNewPasswordEl) authPasswordResetNewPasswordEl.value = "";
      if (authPasswordResetConfirmPasswordEl) authPasswordResetConfirmPasswordEl.value = "";
      clearPasswordResetTokenFromLocation();
      setPasswordResetPanelOpen(false);
      if (authGateStatusEl) {
        authGateStatusEl.textContent = payload.message || "Password reset. You can sign in with the new password.";
      }
    } catch (error) {
      if (authPasswordResetStatusEl) {
        authPasswordResetStatusEl.className = "section-note is-warning";
        authPasswordResetStatusEl.textContent = error && error.message ? error.message : "Unable to reset password.";
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
    loginOidc,
    setPasswordResetPanelOpen,
    requestPasswordReset,
    confirmPasswordReset,
    clearPasswordResetTokenFromLocation,
    logoutLocal,
  };
}
