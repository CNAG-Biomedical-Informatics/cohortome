import { modalityIcon } from './modalities.js';

export function createNavigationUi(ctx) {
  const { refs, state, constants, callbacks } = ctx;
  const {
    dashboardTabBtnEl,
    datasetsTabBtnEl,
    cohortsTabBtnEl,
    cohortsTabEl,
    adminTabBtnEl,
    usersTabBtnEl,
    modelsTabBtnEl,
    queryTabBtnEl,
    analysisTabBtnEl,
    phenoTabBtnEl,
    dashboardClinicalBtnEl,
    dashboardPatientsBtnEl,
    dashboardPatientsPanelEl,
    dashboardAssaysBtnEl,
    dashboardImagingBtnEl,
    dashboardMultimodalBtnEl,
    dashboardTimelineBtnEl,
    tabHelperTextEl,
    dashboardTabEl,
    datasetsTabEl,
    usersTabEl,
    modelsTabEl,
    queryTabEl,
    analysisTabEl,
    phenoTabEl,
    dashboardClinicalPanelEl,
    dashboardAssaysPanelEl,
    dashboardImagingPanelEl,
    dashboardMultimodalPanelEl,
    dashboardTimelinePanelEl,
    loadStatusEl,
  } = refs;
  const { ACTIVE_TAB_STORAGE_KEY, DASHBOARD_SUBTAB_STORAGE_KEY, TAB_HELPER_TEXT } = constants;
  const { effectiveQueryGranularityCeiling, renderGlobalContext, closeJobSurfaces } = callbacks;
  for (const [button, modality] of [[dashboardClinicalBtnEl, 'clinical'], [dashboardAssaysBtnEl, 'assay'], [dashboardImagingBtnEl, 'imaging']]) {
    const icon = button?.querySelector('.dashboard-subtab-icon, .button-icon');
    if (icon) icon.innerHTML = modalityIcon(modality, '');
  }

  function renderTabHelperText(tabName) {
    if (!tabHelperTextEl) {
      return;
    }
    if (tabName === "dashboard") {
      const helperText = {
        clinical: "Browse patients and orient yourself in the loaded clinical dataset",
        patients: "Find a patient and inspect their available samples and assays",
        assays: "Inspect laboratory assays and transcriptomics quick summaries",
        imaging: "Review imaging studies, DICOM viewer status, and derived measurements",
        multimodal: "Review cross-modal readiness, sample-level feature joins, missingness, and provenance",
        timeline: "Review clinical records, BFF event domains, and assay coverage",
      };
      tabHelperTextEl.textContent = helperText[state.currentDashboardSubtab] || helperText.clinical;
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

  function setActiveTab(tabName, { savedChat = false } = {}) {
    if (tabName === "admin") {
      const current = currentTabName();
      tabName = ["data", "users", "models"].includes(current) ? current : "data";
    }
    if (tabName === "pheno" && !savedChat && !phenoTabAvailable()) {
      renderPhenoTabAvailability();
      if (loadStatusEl) {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = "Pheno-Ranker requires Detailed workspace access.";
      }
      return;
    }
    const showDashboard = tabName === "dashboard";
    const showDatasets = tabName === "datasets";
    const showCohorts = tabName === "cohorts";
    cohortsTabBtnEl?.classList.toggle('active', showCohorts);
    cohortsTabBtnEl?.setAttribute('aria-current', showCohorts ? 'page' : 'false');
    cohortsTabEl?.classList.toggle('active', showCohorts);
    const showUsers = tabName === "users";
    const showModels = tabName === "models";
    const showData = tabName === "data";
    const showAdmin = showData || showUsers || showModels;
    refs.dataTabBtnEl?.classList.toggle("active", showData);
    refs.dataTabBtnEl?.setAttribute("aria-current", showData ? "page" : "false");
    refs.dataTabEl?.classList.toggle("active", showData);
    const showQuery = tabName === "query";
    const showAnalysis = tabName === "analysis";
    const showPheno = tabName === "pheno";
    dashboardTabBtnEl && dashboardTabBtnEl.classList.toggle("active", showDashboard);
    datasetsTabBtnEl && datasetsTabBtnEl.classList.toggle("active", showDatasets);
    adminTabBtnEl && adminTabBtnEl.classList.toggle("active", showAdmin);
    usersTabBtnEl && usersTabBtnEl.classList.toggle("active", showUsers);
    modelsTabBtnEl && modelsTabBtnEl.classList.toggle("active", showModels);
    queryTabBtnEl && queryTabBtnEl.classList.toggle("active", showQuery);
    analysisTabBtnEl && analysisTabBtnEl.classList.toggle("active", showAnalysis);
    phenoTabBtnEl && phenoTabBtnEl.classList.toggle("active", showPheno);
    dashboardTabBtnEl && dashboardTabBtnEl.setAttribute("aria-current", showDashboard ? "page" : "false");
    dashboardTabBtnEl && dashboardTabBtnEl.setAttribute("aria-expanded", showDashboard ? "true" : "false");
    datasetsTabBtnEl && datasetsTabBtnEl.setAttribute("aria-current", showDatasets ? "page" : "false");
    adminTabBtnEl && adminTabBtnEl.setAttribute("aria-current", showAdmin ? "page" : "false");
    adminTabBtnEl && adminTabBtnEl.setAttribute("aria-expanded", showAdmin ? "true" : "false");
    usersTabBtnEl && usersTabBtnEl.setAttribute("aria-current", showUsers ? "page" : "false");
    modelsTabBtnEl && modelsTabBtnEl.setAttribute("aria-current", showModels ? "page" : "false");
    queryTabBtnEl && queryTabBtnEl.setAttribute("aria-current", showQuery ? "page" : "false");
    analysisTabBtnEl && analysisTabBtnEl.setAttribute("aria-current", showAnalysis ? "page" : "false");
    phenoTabBtnEl && phenoTabBtnEl.setAttribute("aria-current", showPheno ? "page" : "false");
    dashboardTabEl && dashboardTabEl.classList.toggle("active", showDashboard);
    datasetsTabEl && datasetsTabEl.classList.toggle("active", showDatasets);
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
    callbacks.renderChatList?.();
    if (showCohorts) void callbacks.loadCohortLibrary?.();
  }

  function setDashboardSubtab(subtabName) {
    state.currentDashboardSubtab = ["patients", "assays", "imaging", "multimodal", "timeline"].includes(subtabName) ? subtabName : "clinical";
    const patientView = state.currentDashboardSubtab === 'patients';
    dashboardPatientsBtnEl && dashboardPatientsBtnEl.classList.toggle("active", patientView);
    dashboardPatientsPanelEl && dashboardPatientsPanelEl.classList.toggle("active", patientView);
    document.getElementById('patientOverviewDetail').hidden = state.currentDashboardSubtab === 'timeline';
    document.getElementById('patientOverviewViewBtn').setAttribute('aria-pressed', String(state.currentDashboardSubtab !== 'timeline'));
    dashboardTimelineBtnEl?.setAttribute('aria-pressed', String(state.currentDashboardSubtab === 'timeline'));
    dashboardImagingBtnEl && dashboardImagingBtnEl.classList.toggle("active", state.currentDashboardSubtab === "imaging");
    dashboardImagingPanelEl && dashboardImagingPanelEl.classList.toggle("active", state.currentDashboardSubtab === "imaging");
    dashboardClinicalBtnEl && dashboardClinicalBtnEl.classList.toggle("active", state.currentDashboardSubtab === "clinical");
    dashboardAssaysBtnEl && dashboardAssaysBtnEl.classList.toggle("active", state.currentDashboardSubtab === "assays");
    dashboardMultimodalBtnEl && dashboardMultimodalBtnEl.classList.toggle("active", state.currentDashboardSubtab === "multimodal");
    dashboardTimelineBtnEl && dashboardTimelineBtnEl.classList.toggle("active", state.currentDashboardSubtab === "timeline");
    dashboardClinicalPanelEl && dashboardClinicalPanelEl.classList.toggle("active", state.currentDashboardSubtab === "clinical");
    dashboardAssaysPanelEl && dashboardAssaysPanelEl.classList.toggle("active", state.currentDashboardSubtab === "assays");
    dashboardMultimodalPanelEl && dashboardMultimodalPanelEl.classList.toggle("active", state.currentDashboardSubtab === "multimodal");
    dashboardTimelinePanelEl && dashboardTimelinePanelEl.classList.toggle("active", state.currentDashboardSubtab === "timeline");
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
    if (refs.dataTabEl?.classList.contains("active")) return "data";
    if (cohortsTabEl?.classList.contains('active')) return 'cohorts';
    if (phenoTabEl && phenoTabEl.classList.contains("active")) return "pheno";
    if (datasetsTabEl && datasetsTabEl.classList.contains("active")) return "datasets";
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
