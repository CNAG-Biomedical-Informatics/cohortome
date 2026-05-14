export function createNavigationUi(ctx) {
  const { refs, state, constants, callbacks } = ctx;
  const {
    dashboardTabBtnEl,
    datasetsTabBtnEl,
    dataTabBtnEl,
    usersTabBtnEl,
    modelsTabBtnEl,
    queryTabBtnEl,
    analysisTabBtnEl,
    phenoTabBtnEl,
    dashboardClinicalBtnEl,
    dashboardMolecularBtnEl,
    tabHelperTextEl,
    dashboardTabEl,
    datasetsTabEl,
    dataTabEl,
    usersTabEl,
    modelsTabEl,
    queryTabEl,
    analysisTabEl,
    phenoTabEl,
    dashboardClinicalPanelEl,
    dashboardMolecularPanelEl,
    loadStatusEl,
  } = refs;
  const { ACTIVE_TAB_STORAGE_KEY, DASHBOARD_SUBTAB_STORAGE_KEY, TAB_HELPER_TEXT } = constants;
  const { effectiveQueryGranularityCeiling, renderGlobalContext, closeJobSurfaces } = callbacks;

  function renderTabHelperText(tabName) {
    if (!tabHelperTextEl) {
      return;
    }
    if (tabName === "dashboard") {
      tabHelperTextEl.textContent = state.currentDashboardSubtab === "molecular"
        ? "Inspect loaded molecular datasets and quick transcriptomics summaries"
        : "Browse patients and orient yourself in the loaded clinical dataset";
      return;
    }
    tabHelperTextEl.textContent = TAB_HELPER_TEXT[tabName] || "";
  }

  function phenoTabAvailable(datasetIds = state.currentDatasetIds) {
    return effectiveQueryGranularityCeiling(datasetIds) === "detailed";
  }

  function renderPhenoTabAvailability() {
    if (!phenoTabBtnEl) {
      return;
    }
    const available = phenoTabAvailable();
    phenoTabBtnEl.classList.toggle("is-disabled", !available);
    phenoTabBtnEl.setAttribute("aria-disabled", available ? "false" : "true");
    phenoTabBtnEl.title = available
      ? "Open Pheno-Ranker."
      : "Pheno-Ranker requires Detailed workspace access.";
  }

  function setActiveTab(tabName) {
    if (tabName === "pheno" && !phenoTabAvailable()) {
      renderPhenoTabAvailability();
      if (loadStatusEl) {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = "Pheno-Ranker requires Detailed workspace access.";
      }
      return;
    }
    const showDashboard = tabName === "dashboard";
    const showDatasets = tabName === "datasets";
    const showData = tabName === "data";
    const showUsers = tabName === "users";
    const showModels = tabName === "models";
    const showQuery = tabName === "query";
    const showAnalysis = tabName === "analysis";
    const showPheno = tabName === "pheno";
    dashboardTabBtnEl && dashboardTabBtnEl.classList.toggle("active", showDashboard);
    datasetsTabBtnEl && datasetsTabBtnEl.classList.toggle("active", showDatasets);
    dataTabBtnEl && dataTabBtnEl.classList.toggle("active", showData);
    usersTabBtnEl && usersTabBtnEl.classList.toggle("active", showUsers);
    modelsTabBtnEl && modelsTabBtnEl.classList.toggle("active", showModels);
    queryTabBtnEl && queryTabBtnEl.classList.toggle("active", showQuery);
    analysisTabBtnEl && analysisTabBtnEl.classList.toggle("active", showAnalysis);
    phenoTabBtnEl && phenoTabBtnEl.classList.toggle("active", showPheno);
    dashboardTabBtnEl && dashboardTabBtnEl.setAttribute("aria-current", showDashboard ? "page" : "false");
    datasetsTabBtnEl && datasetsTabBtnEl.setAttribute("aria-current", showDatasets ? "page" : "false");
    dataTabBtnEl && dataTabBtnEl.setAttribute("aria-current", showData ? "page" : "false");
    usersTabBtnEl && usersTabBtnEl.setAttribute("aria-current", showUsers ? "page" : "false");
    modelsTabBtnEl && modelsTabBtnEl.setAttribute("aria-current", showModels ? "page" : "false");
    queryTabBtnEl && queryTabBtnEl.setAttribute("aria-current", showQuery ? "page" : "false");
    analysisTabBtnEl && analysisTabBtnEl.setAttribute("aria-current", showAnalysis ? "page" : "false");
    phenoTabBtnEl && phenoTabBtnEl.setAttribute("aria-current", showPheno ? "page" : "false");
    dashboardTabEl && dashboardTabEl.classList.toggle("active", showDashboard);
    datasetsTabEl && datasetsTabEl.classList.toggle("active", showDatasets);
    dataTabEl && dataTabEl.classList.toggle("active", showData);
    usersTabEl && usersTabEl.classList.toggle("active", showUsers);
    modelsTabEl && modelsTabEl.classList.toggle("active", showModels);
    queryTabEl && queryTabEl.classList.toggle("active", showQuery);
    analysisTabEl && analysisTabEl.classList.toggle("active", showAnalysis);
    phenoTabEl && phenoTabEl.classList.toggle("active", showPheno);
    try {
      window.localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, tabName);
    } catch (_error) {
    }
    if (typeof closeJobSurfaces === "function") {
      closeJobSurfaces();
    }
    renderTabHelperText(tabName);
    renderGlobalContext();
  }

  function setDashboardSubtab(subtabName) {
    state.currentDashboardSubtab = subtabName === "molecular" ? "molecular" : "clinical";
    dashboardClinicalBtnEl && dashboardClinicalBtnEl.classList.toggle("active", state.currentDashboardSubtab === "clinical");
    dashboardMolecularBtnEl && dashboardMolecularBtnEl.classList.toggle("active", state.currentDashboardSubtab === "molecular");
    dashboardClinicalPanelEl && dashboardClinicalPanelEl.classList.toggle("active", state.currentDashboardSubtab === "clinical");
    dashboardMolecularPanelEl && dashboardMolecularPanelEl.classList.toggle("active", state.currentDashboardSubtab === "molecular");
    try {
      window.localStorage.setItem(DASHBOARD_SUBTAB_STORAGE_KEY, state.currentDashboardSubtab);
    } catch (_error) {
    }
    if (currentTabName() === "dashboard") {
      renderTabHelperText("dashboard");
      renderGlobalContext();
    }
  }

  function currentTabName() {
    if (phenoTabEl && phenoTabEl.classList.contains("active")) return "pheno";
    if (datasetsTabEl && datasetsTabEl.classList.contains("active")) return "datasets";
    if (dataTabEl && dataTabEl.classList.contains("active")) return "data";
    if (usersTabEl && usersTabEl.classList.contains("active")) return "users";
    if (modelsTabEl && modelsTabEl.classList.contains("active")) return "models";
    if (dashboardTabEl && dashboardTabEl.classList.contains("active")) return "dashboard";
    if (analysisTabEl && analysisTabEl.classList.contains("active")) return "analysis";
    if (queryTabEl && queryTabEl.classList.contains("active")) return "query";
    return "dashboard";
  }

  return {
    renderTabHelperText,
    phenoTabAvailable,
    renderPhenoTabAvailability,
    setActiveTab,
    setDashboardSubtab,
    currentTabName,
  };
}
