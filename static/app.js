import { escapeHtml, fallbackCopyText, renderActivityCard } from "/static/js/shared.js";
import { createAppRefs } from "/static/js/app_refs.js";
import { createAppState } from "/static/js/app_state.js";
import { nowIso, shortTimestamp, currentStorageNamespace, createAnalysisSession, formatNumber } from "/static/js/app_helpers.js";
import { createNavigationUi } from "/static/js/app_navigation.js";
import { createWorkspaceUi } from "/static/js/workspace_ui.js";
import { createAuthUi } from "/static/js/auth_ui.js";
import { createUsersAdminUi } from "/static/js/users_admin_ui.js";
import { createDatasetsUi } from "/static/js/datasets_ui.js";
import { createAnalysisCatalogUi } from "/static/js/analysis_catalog_ui.js";
import { createJobsUi } from "/static/js/jobs_ui.js";
import { createDashboardUi } from "/static/js/dashboard.js";
import { createAnalysisSessionsUi } from "/static/js/analysis_sessions.js";
import { createSavedCohortsUi } from "/static/js/saved_cohorts.js";
import { createPhenoUi } from "/static/js/pheno.js";
import { createQueryUi } from "/static/js/query.js";
import { createAnalysisUi } from "/static/js/analysis.js";
import { createUserSettingsUi } from "/static/js/user_settings.js";

const refs = createAppRefs(document);
const state = createAppState();

const MAX_VISIBLE_PATIENTS = 80;
const MAX_VISIBLE_EXAMPLES = 8;
const ACTIVE_TAB_STORAGE_KEY = "patient-navigator.active-tab";
const DASHBOARD_SUBTAB_STORAGE_KEY = "patient-navigator.dashboard-subtab";
const ANALYSIS_SESSIONS_STORAGE_KEY = "patient-navigator.analysis-sessions";
const ANALYSIS_SIDEBAR_COLLAPSED_STORAGE_KEY = "patient-navigator.analysis-sidebar-collapsed";
const TAB_HELPER_TEXT = {
  dashboard: "Browse the loaded clinical and molecular data",
  datasets: "Choose the authorized datasets that define your active workspace scope",
  data: "Admin-only dataset visibility and access policy management",
  users: "Admin-only read-only user visibility",
  query: "Build and refine cohorts (LLM-assisted, deterministic results)",
  analysis: "Interpret and compare cohorts (LLM-assisted insights)",
  pheno: "Compare patients or cohorts and inspect similarity results",
};

const PHENO_BUCKET_STYLES = {
  diseases: { bg: "#dbeafe", ink: "#1d4ed8" },
  phenotypicFeatures: { bg: "#dcfce7", ink: "#166534" },
  treatments: { bg: "#fef3c7", ink: "#92400e" },
  procedures: { bg: "#fee2e2", ink: "#b91c1c" },
  exposures: { bg: "#ede9fe", ink: "#6d28d9" },
  measures: { bg: "#cffafe", ink: "#0f766e" },
  sex: { bg: "#fce7f3", ink: "#be185d" },
  ethnicity: { bg: "#e0f2fe", ink: "#0369a1" },
  identifier: { bg: "#f3f4f6", ink: "#111827" },
  other: { bg: "#e5e7eb", ink: "#374151" },
};

const PHENO_COHORT_COLORS = [
  "#2563eb",
  "#ea580c",
  "#16a34a",
  "#7c3aed",
  "#dc2626",
  "#0891b2",
  "#ca8a04",
  "#4f46e5",
];

let navigationUi;
let workspaceUi;
let authUi;
let usersAdminUi;
let datasetsUi;
let analysisCatalogUi;
let jobsUi;
let dashboardUi;
let analysisSessionsUi;
let savedCohortsUi;
let phenoUi;
let queryUi;
let analysisUi;
let userSettingsUi;

function isMultiDatasetWorkspace() {
  return state.currentDatasetIds.length > 1;
}

function currentAnalysisSession() {
  return state.analysisSessions.find((session) => session.id === state.currentAnalysisSessionId) || null;
}

function makeAnalysisSession(overrides = {}) {
  return createAnalysisSession(overrides, refs.dataDirEl && refs.dataDirEl.value ? refs.dataDirEl.value.trim() : "");
}

function setLatestQueryState(patch) {
  if (Object.prototype.hasOwnProperty.call(patch, "ids")) {
    state.latestQueryPatientIds = Array.isArray(patch.ids) ? patch.ids : [];
  }
  if (Object.prototype.hasOwnProperty.call(patch, "recordIds")) {
    state.latestQueryRecordIds = Array.isArray(patch.recordIds) ? patch.recordIds : [];
  }
  if (Object.prototype.hasOwnProperty.call(patch, "prompt")) {
    state.latestQueryPrompt = patch.prompt || "";
  }
  if (Object.prototype.hasOwnProperty.call(patch, "analysisPrompt")) {
    state.latestQueryAnalysisPrompt = patch.analysisPrompt || "";
  }
  if (Object.prototype.hasOwnProperty.call(patch, "idType")) {
    state.latestQueryIdType = patch.idType || "patient";
  }
}

function setLatestScopedContext(patch) {
  state.latestScopedContext = {
    patientIds: Array.isArray(patch && patch.patientIds) ? patch.patientIds : state.latestScopedContext.patientIds,
    recordIds: Array.isArray(patch && patch.recordIds) ? patch.recordIds : state.latestScopedContext.recordIds,
    idType: patch && patch.idType ? patch.idType : state.latestScopedContext.idType,
    sourceTab: patch && patch.sourceTab ? patch.sourceTab : state.latestScopedContext.sourceTab,
    prompt: patch && typeof patch.prompt === "string" ? patch.prompt : state.latestScopedContext.prompt,
  };
}

function renderQueryReply(payloadOrValue) {
  return queryUi.renderQueryReply(payloadOrValue);
}

function sendPatientIdsToPhenoRanker() {
  const scopeIds = state.latestQueryRecordIds.length ? state.latestQueryRecordIds : state.latestQueryPatientIds;
  if (!scopeIds.length) {
    return;
  }
  refs.phenoActionEl.value = "compare";
  refs.phenoModeEl.value = "cohort";
  refs.phenoSelectedPatientIdsEl.value = scopeIds.join(",");
  phenoUi.renderSelectedPatientIdsSummary();
  phenoUi.updatePhenoMode();
  navigationUi.setActiveTab("pheno");
  refs.phenoStatusEl.className = "pheno-status";
  refs.phenoStatusEl.textContent = state.latestQueryRecordIds.length
    ? `Loaded ${state.latestQueryRecordIds.length} sample IDs from the query result into the current Pheno-Ranker scope.`
    : `Loaded ${state.latestQueryPatientIds.length} patient IDs from the query result into the current Pheno-Ranker scope.`;
}

function sendPatientIdsToAnalysis() {
  const scopeIds = state.latestQueryRecordIds.length ? state.latestQueryRecordIds : state.latestQueryPatientIds;
  if (!scopeIds.length) {
    return;
  }
  state.analysisSelectedSavedCohortId = "";
  refs.analysisSelectedPatientIdsEl.value = scopeIds.join(",");
  if (state.latestQueryAnalysisPrompt && !refs.analysisPromptEl.value.trim()) {
    refs.analysisPromptEl.value = state.latestQueryAnalysisPrompt;
  }
  dashboardUi.renderAnalysisScopeSummary();
  navigationUi.setActiveTab("analysis");
  analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  refs.analysisStatusEl.className = "query-status";
  refs.analysisStatusEl.textContent = state.latestQueryRecordIds.length
    ? `Loaded ${state.latestQueryRecordIds.length} sample IDs from Query into Analysis. Run the analysis prompt to interpret this workspace.`
    : `Loaded ${state.latestQueryPatientIds.length} patient IDs from Query into Analysis. Run the analysis prompt to interpret this workspace.`;
}

function sendPromptToAnalysis(prompt, options) {
  const settings = options || {};
  const normalizedPrompt = String(prompt || "").trim();
  if (!normalizedPrompt) {
    return;
  }
  refs.analysisPromptEl.value = normalizedPrompt;
  state.analysisExecutionMode = settings.llmOnly ? "llm_only" : "auto";
  state.analysisSelectedCatalogItemId = "";
  analysisCatalogUi.renderAnalysisCatalogMolecularPanel();
  navigationUi.setActiveTab("analysis");
  dashboardUi.renderAnalysisScopeSummary();
  analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  refs.analysisStatusEl.className = "query-status";
  refs.analysisStatusEl.textContent = state.latestQueryPatientIds.length
    ? `Analysis prompt prepared for the ${state.latestQueryPatientIds.length}-ID workspace currently loaded from Query.`
    : "Analysis prompt prepared. Select a scope or use the full workspace.";
  refs.analysisPromptEl.focus();
}

function shouldAutoOpenJobsAfterSubmission() {
  return !state.userSettings || state.userSettings.analysis_auto_open_jobs !== false;
}

function setAnalysisSidebarCollapsed(collapsed, options = {}) {
  if (!refs.analysisShellEl) return;
  const isCollapsed = Boolean(collapsed);
  refs.analysisShellEl.classList.toggle("analysis-sidebar-collapsed", isCollapsed);
  if (refs.analysisSidebarToggleBtnEl) {
    refs.analysisSidebarToggleBtnEl.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    refs.analysisSidebarToggleBtnEl.setAttribute("aria-label", isCollapsed ? "Expand Analysis Chats" : "Collapse Analysis Chats");
    refs.analysisSidebarToggleBtnEl.title = isCollapsed ? "Expand Analysis Chats" : "Collapse Analysis Chats";
  }
  if (options.persist !== false) {
    try {
      window.localStorage.setItem(ANALYSIS_SIDEBAR_COLLAPSED_STORAGE_KEY, isCollapsed ? "1" : "0");
    } catch (_error) {
      // Ignore storage failures; the visual state still updates.
    }
  }
}

function initializeAnalysisSidebarCollapsed() {
  let collapsed = false;
  try {
    collapsed = window.localStorage.getItem(ANALYSIS_SIDEBAR_COLLAPSED_STORAGE_KEY) === "1";
  } catch (_error) {
    collapsed = false;
  }
  setAnalysisSidebarCollapsed(collapsed, { persist: false });
}

function stopQueryProgressUpdates() {
  if (state.queryProgressTimer !== null) {
    window.clearInterval(state.queryProgressTimer);
    state.queryProgressTimer = null;
  }
}

function queryPendingStages() {
  return [
    { label: "Parsing request", detail: "Interpreting the cohort question and selecting the right query path." },
    { label: "Checking cohort facts", detail: "Reviewing counts, patient IDs, and dataset-backed matches." },
    { label: "Preparing answer", detail: "Formatting the reply, actions, and follow-up suggestions." },
  ];
}

function startQueryProgressUpdates() {
  stopQueryProgressUpdates();
  const stages = queryPendingStages();
  let index = 0;
  const applyStage = () => {
    const lastTurn = state.queryTurns[state.queryTurns.length - 1];
    if (!lastTurn || !lastTurn.pending) {
      stopQueryProgressUpdates();
      return;
    }
    const stage = stages[Math.min(index, stages.length - 1)];
    lastTurn.pendingLabel = stage.label;
    lastTurn.pendingDetail = stage.detail;
    queryUi.renderQueryThread();
    if (index < stages.length - 1) {
      index += 1;
    }
  };
  applyStage();
  state.queryProgressTimer = window.setInterval(applyStage, 1400);
}

function stopAnalysisProgressUpdates() {
  if (state.analysisProgressTimer !== null) {
    window.clearInterval(state.analysisProgressTimer);
    state.analysisProgressTimer = null;
  }
}

function analysisPendingStages(compareMode, showPlots) {
  if (showPlots) {
    return [
      { label: "Parsing request", detail: "Interpreting the analysis prompt and identifying the deterministic analysis path." },
      { label: compareMode ? "Comparing cohorts" : "Computing analysis", detail: compareMode ? "Preparing both cohort contexts and computing the requested comparison plots." : "Computing the requested analysis and preparing the related plots." },
      { label: "Preparing answer", detail: "Formatting the explanation, metadata, and visual outputs for the thread." },
    ];
  }
  return [
    { label: "Parsing request", detail: "Interpreting the analysis prompt and assembling the relevant cohort context." },
    { label: compareMode ? "Comparing cohorts" : "Checking cohort context", detail: compareMode ? "Reviewing the selected comparison cohorts and their main differences." : "Reviewing the selected cohort and its main clinical context." },
    { label: "Preparing answer", detail: "Formatting the analysis reply and supporting context." },
  ];
}

function startAnalysisProgressUpdates(compareMode, showPlots) {
  stopAnalysisProgressUpdates();
  const stages = analysisPendingStages(compareMode, showPlots);
  let index = 0;
  const applyStage = () => {
    const lastTurn = state.analysisTurns[state.analysisTurns.length - 1];
    if (!lastTurn || !lastTurn.pending) {
      stopAnalysisProgressUpdates();
      return;
    }
    const stage = stages[Math.min(index, stages.length - 1)];
    lastTurn.pendingLabel = stage.label;
    lastTurn.pendingDetail = stage.detail;
    analysisUi.renderAnalysisThread();
    if (index < stages.length - 1) {
      index += 1;
    }
  };
  applyStage();
  state.analysisProgressTimer = window.setInterval(applyStage, 1500);
}

function stopPhenoPlanProgressUpdates() {
  if (state.phenoPlanProgressTimer !== null) {
    window.clearInterval(state.phenoPlanProgressTimer);
    state.phenoPlanProgressTimer = null;
  }
}

function startPhenoPlanProgressUpdates() {
  stopPhenoPlanProgressUpdates();
  const stages = [
    { label: "Interpreting request", detail: "Reading the natural-language request and extracting a runnable Pheno-Ranker plan." },
    { label: "Checking scope", detail: "Aligning the request with the current dataset and selected patient scope." },
    { label: "Preparing plan", detail: "Formatting the interpreted command, options, and reasoning for review." },
  ];
  let index = 0;
  const applyStage = () => {
    const stage = stages[Math.min(index, stages.length - 1)];
    refs.phenoPlanStatusEl.className = "pheno-status loading";
    refs.phenoPlanStatusEl.textContent = stage.label;
    refs.phenoPlanEl.innerHTML = renderActivityCard(stage.label, stage.detail);
    refs.phenoPlanReasoningEl.innerHTML = renderActivityCard("Planner reasoning", "Waiting for the interpreted plan and supporting rationale.");
    if (index < stages.length - 1) {
      index += 1;
    }
  };
  applyStage();
  state.phenoPlanProgressTimer = window.setInterval(applyStage, 1600);
}

function stopPhenoRunProgressUpdates() {
  if (state.phenoRunProgressTimer !== null) {
    window.clearInterval(state.phenoRunProgressTimer);
    state.phenoRunProgressTimer = null;
  }
}

function startPhenoRunProgressUpdates() {
  stopPhenoRunProgressUpdates();
  const patientMode = refs.phenoModeEl.value === "patient";
  const stages = patientMode
    ? [
        { label: "Preparing run", detail: "Building the patient-comparison command and validating the selected scope." },
        { label: "Running similarity job", detail: "Executing the comparison and waiting for rank and alignment outputs." },
        { label: "Collecting outputs", detail: "Loading previews, logs, and result files from the completed run." },
      ]
    : [
        { label: "Preparing run", detail: "Building the cohort or extraction command and validating the selected scope." },
        { label: "Running Pheno-Ranker", detail: "Executing the job and waiting for result files and plots." },
        { label: "Collecting outputs", detail: "Loading previews, logs, and result files from the completed run." },
      ];
  let index = 0;
  const applyStage = () => {
    const stage = stages[Math.min(index, stages.length - 1)];
    refs.phenoStatusEl.className = "pheno-status loading";
    refs.phenoStatusEl.textContent = stage.label;
    refs.phenoOutputPreviewEl.innerHTML = renderActivityCard(stage.label, stage.detail);
    refs.phenoPreviewsEl.innerHTML = renderActivityCard("Preparing plots", "Waiting for interactive cohort plots and result files from the active run.");
    if (index < stages.length - 1) {
      index += 1;
    }
  };
  applyStage();
  state.phenoRunProgressTimer = window.setInterval(applyStage, 1800);
}

navigationUi = createNavigationUi({
  refs,
  state,
  constants: {
    ACTIVE_TAB_STORAGE_KEY,
    DASHBOARD_SUBTAB_STORAGE_KEY,
    TAB_HELPER_TEXT,
  },
  callbacks: {
    effectiveQueryGranularityCeiling: (datasetIds) => datasetsUi.effectiveQueryGranularityCeiling(datasetIds),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
  },
});

dashboardUi = createDashboardUi({
  refs,
  helpers: {
    escapeHtml,
    formatNumber,
  },
  callbacks: {
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    syncCurrentAnalysisSessionFromUi: (options) => analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options),
    isMultiDatasetWorkspace,
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
    renderAnalysisCatalogMolecularPanel: () => analysisCatalogUi.renderAnalysisCatalogMolecularPanel(),
  },
  state,
  constants: {
    MAX_VISIBLE_PATIENTS,
  },
});

usersAdminUi = createUsersAdminUi({
  refs,
  state,
  callbacks: {
    canManageDataset: () => authUi.canManageDataset(),
    renderDatasetAdminList: () => datasetsUi.renderDatasetAdminList(),
  },
});

analysisCatalogUi = createAnalysisCatalogUi({
  refs,
  state,
  helpers: {
    escapeHtml,
  },
  constants: {
    MAX_VISIBLE_EXAMPLES,
  },
  callbacks: {
    queryWorkspacePolicyExplanation: () => datasetsUi.queryWorkspacePolicyExplanation(),
    renderMolecularDatasetSelector: () => dashboardUi.renderMolecularDatasetSelector(),
    renderAnalysisCompareMode: () => analysisUi.renderAnalysisCompareMode(),
    syncCurrentAnalysisSessionFromUi: (options) => analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options),
    currentDatasetSelectionKey: () => datasetsUi.currentDatasetSelectionKey(),
    isWorkspaceAccessible: () => authUi.isWorkspaceAccessible(),
    molecularDatasetOverlap: (datasetName) => dashboardUi.molecularDatasetOverlap(datasetName),
  },
});

savedCohortsUi = createSavedCohortsUi({
  refs,
  helpers: {
    escapeHtml,
  },
  callbacks: {
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    renderAnalysisScopeSummary: () => dashboardUi.renderAnalysisScopeSummary(),
    renderAnalysisCompareMode: () => analysisUi.renderAnalysisCompareMode(),
    renderAnalysisCompareScopeSummary: () => dashboardUi.renderAnalysisCompareScopeSummary(),
    renderSelectedPatientIdsSummary: () => phenoUi.renderSelectedPatientIdsSummary(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    datasetLabelsForIds: (ids) => datasetsUi.datasetLabelsForIds(ids),
    currentDatasetIds: () => state.currentDatasetIds.slice(),
    currentTabName: () => navigationUi.currentTabName(),
    queryStatusEl: () => refs.queryStatusEl,
  },
  state,
});

queryUi = createQueryUi({
  refs,
  helpers: {
    escapeHtml,
    renderActivityCard,
    fallbackCopyText,
  },
  callbacks: {
    renderQueryStarterPrompts: () => analysisCatalogUi.renderQueryStarterPrompts(),
    renderQueryExecutionMode: () => analysisCatalogUi.renderQueryExecutionMode(),
    startQueryProgressUpdates,
    stopQueryProgressUpdates,
    nextFrame: () => workspaceUi.nextFrame(),
    saveLatestQueryAsCohort: () => savedCohortsUi.saveLatestQueryAsCohort(),
    sendPatientIdsToPhenoRanker,
    sendPatientIdsToAnalysis,
    sendPromptToAnalysis,
    currentPatientsProvider: () => state.currentPatients,
    phenoRankerPatientIdsProvider: () => state.phenoRankerPatientIds,
    isMultiDatasetWorkspace,
    setLatestQueryState,
    setLatestScopedContext,
  },
  state,
});

analysisUi = createAnalysisUi({
  refs,
  helpers: {
    escapeHtml,
    renderQueryReply,
  },
  callbacks: {
    renderAnalysisStarterPrompts: () => analysisCatalogUi.renderAnalysisStarterPrompts(),
    syncCurrentAnalysisSessionFromUi: (options) => analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options),
    startAnalysisProgressUpdates,
    stopAnalysisProgressUpdates,
    handleAnalysisJobSubmission: (payload) => {
      const autoOpenJobs = shouldAutoOpenJobsAfterSubmission();
      if (autoOpenJobs) {
        jobsUi.setJobsDrawerOpen(true);
        void jobsUi.loadRecentJobs();
      } else {
        void jobsUi.loadRecentJobs({ silent: true });
      }
      if (payload && payload.data && (payload.data.job_code || payload.data.job_id)) {
        refs.analysisStatusEl.className = "query-status";
        const label = String(payload.data.job_code || payload.data.job_id || "").trim();
        refs.analysisStatusEl.textContent = autoOpenJobs
          ? `Background job ${label} submitted. Jobs opened.`
          : `Background job ${label} submitted. Open Jobs to monitor progress.`;
      }
    },
    renderAnalysisFlowBar: () => analysisCatalogUi.renderAnalysisFlowBar(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    renderAnalysisScopeSummary: () => dashboardUi.renderAnalysisScopeSummary(),
    renderAnalysisCompareScopeSummary: () => dashboardUi.renderAnalysisCompareScopeSummary(),
    molecularDatasetOverlap: (datasetName) => dashboardUi.molecularDatasetOverlap(datasetName),
  },
  state,
});

analysisSessionsUi = createAnalysisSessionsUi({
  refs,
  helpers: {
    escapeHtml,
    shortTimestamp,
    nowIso,
  },
  callbacks: {
    createAnalysisSession: makeAnalysisSession,
    currentAnalysisSession,
    getStorageNamespace: () => currentStorageNamespace(state.authState),
    renderAnalysisCompareMode: () => analysisUi.renderAnalysisCompareMode(),
    renderAnalysisScopeSummary: () => dashboardUi.renderAnalysisScopeSummary(),
    renderAnalysisCompareScopeSummary: () => dashboardUi.renderAnalysisCompareScopeSummary(),
    renderAnalysisStarterPrompts: () => analysisCatalogUi.renderAnalysisStarterPrompts(),
    renderAnalysisThread: () => analysisUi.renderAnalysisThread(),
    renderAnalysisMeta: (payload) => analysisUi.renderAnalysisMeta(payload),
    renderAnalysisFlowBar: () => analysisCatalogUi.renderAnalysisFlowBar(),
  },
  state,
  constants: {
    ANALYSIS_SESSIONS_STORAGE_KEY,
  },
});

phenoUi = createPhenoUi({
  refs,
  constants: {
    PHENO_BUCKET_STYLES,
    PHENO_COHORT_COLORS,
  },
  helpers: {
    escapeHtml,
    renderActivityCard,
    fallbackCopyText,
    renderQueryReply,
    nextFrame: () => workspaceUi.nextFrame(),
  },
  callbacks: {
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    renderAnalysisScopeSummary: () => dashboardUi.renderAnalysisScopeSummary(),
    syncCurrentAnalysisSessionFromUi: (options) => analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options),
    startPhenoPlanProgressUpdates,
    stopPhenoPlanProgressUpdates,
    startPhenoRunProgressUpdates,
    stopPhenoRunProgressUpdates,
    handlePhenoJobSubmission: (payload) => {
      const autoOpenJobs = shouldAutoOpenJobsAfterSubmission();
      if (autoOpenJobs) {
        jobsUi.setJobsDrawerOpen(true);
        void jobsUi.loadRecentJobs();
      } else {
        void jobsUi.loadRecentJobs({ silent: true });
      }
      if (payload && payload.data && (payload.data.job_code || payload.data.job_id)) {
        refs.phenoStatusEl.className = "pheno-status";
        const label = String(payload.data.job_code || payload.data.job_id || "").trim();
        refs.phenoStatusEl.textContent = autoOpenJobs
          ? `Background Pheno-Ranker run ${label} submitted. Jobs opened.`
          : `Background Pheno-Ranker run ${label} submitted. Open Jobs to monitor progress.`;
      }
    },
    saveIdsAsCohort: (options) => savedCohortsUi.saveIdsAsCohort(options),
    getSelectedSavedCohortIds: () => state.phenoSelectedSavedCohortIds.slice(),
    setSelectedSavedCohortIds: (ids) => {
      state.phenoSelectedSavedCohortIds = Array.isArray(ids) ? ids.slice() : [];
      savedCohortsUi.renderPhenoSavedCohortsSelection();
    },
    getCurrentScopeIds: () => workspaceUi.getCurrentScopeIds(),
    onPatientIdsLoaded: (ids) => { state.phenoRankerPatientIds = ids.slice(); },
    onReferenceFilesLoaded: (files) => { state.phenoReferenceFiles = files.slice(); },
  },
  state,
});

jobsUi = createJobsUi({
  refs,
  state,
  helpers: {
    escapeHtml,
  },
  callbacks: {
    currentAnalysisSessionId: () => state.currentAnalysisSessionId,
    currentDatasetScopeId: () => state.currentDatasetScopeId,
    analysisPayloadHasPlots: (payload) => analysisUi.analysisPayloadHasPlots(payload),
    selectAnalysisSession: (sessionId) => analysisSessionsUi.selectAnalysisSession(sessionId),
    createAndSelectAnalysisSession: (overrides) => analysisSessionsUi.createAndSelectAnalysisSession(overrides),
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    renderAnalysisMeta: (payload) => analysisUi.renderAnalysisMeta(payload),
    renderAnalysisThread: () => analysisUi.renderAnalysisThread(),
    scrollAnalysisTurnIntoView: (turnIndex) => analysisUi.scrollAnalysisTurnIntoView(turnIndex),
    syncCurrentAnalysisSessionFromUi: (options) => analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options),
    loadCompletedPhenoJob: (jobPayload, resultPayload) => phenoUi.loadCompletedPhenoJob(jobPayload, resultPayload),
    renderPhenoBackgroundJobBanner: () => phenoUi.renderPhenoBackgroundJobBanner(),
  },
});

workspaceUi = createWorkspaceUi({
  refs,
  state,
  helpers: {
    formatNumber,
  },
  callbacks: {
    currentTabName: () => navigationUi.currentTabName(),
    currentDatasetRecord: () => datasetsUi.currentDatasetRecord(),
    datasetScopeLabel: () => datasetsUi.datasetScopeLabel(),
    pendingDatasetSelectionIds: () => datasetsUi.pendingDatasetSelectionIds(),
    currentDatasetSelectionKey: () => datasetsUi.currentDatasetSelectionKey(),
    renderDatasetPicker: () => datasetsUi.renderDatasetPicker(),
    renderDatasetAdminList: () => datasetsUi.renderDatasetAdminList(),
    renderDatasetScopeSummary: () => datasetsUi.renderDatasetScopeSummary(),
    renderLoadButtonState: () => datasetsUi.renderLoadButtonState(),
    prepareAnalysisSessionForDataDir: (value) => analysisSessionsUi.prepareAnalysisSessionForDataDir(value),
    resetQueryWorkspace: () => queryUi.resetQueryWorkspace(),
    syncQueryGranularityWithWorkspacePolicy: (options) => datasetsUi.syncQueryGranularityWithWorkspacePolicy(options),
    loadAnalysisCatalog: () => analysisCatalogUi.loadAnalysisCatalog(),
    loadSavedCohorts: () => savedCohortsUi.loadSavedCohorts(),
    loadQueryDiseaseOptions: () => queryUi.loadDiseaseOptions(),
    loadMolecularDatasets: () => dashboardUi.loadMolecularDatasets(),
    loadPhenoRankerPatientIds: () => phenoUi.loadPhenoRankerPatientIds(),
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
    renderPatientList: (items) => dashboardUi.renderPatientList(items),
    renderDetail: (patient) => dashboardUi.renderDetail(patient),
    renderDashboard: (summary) => dashboardUi.renderDashboard(summary),
    isWorkspaceAccessible: () => authUi.isWorkspaceAccessible(),
    updateLoadButtonAvailability: () => authUi.updateLoadButtonAvailability(),
    applyUserSettings: (options) => userSettingsUi.applyUserSettings(options),
  },
});

datasetsUi = createDatasetsUi({
  refs,
  state,
  helpers: {
    escapeHtml,
  },
  callbacks: {
    canManageDataset: () => authUi.canManageDataset(),
    isWorkspaceAccessible: () => authUi.isWorkspaceAccessible(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    prepareAnalysisSessionForDataDir: (value) => analysisSessionsUi.prepareAnalysisSessionForDataDir(value),
    resetQueryWorkspace: () => queryUi.resetQueryWorkspace(),
    loadAnalysisCatalog: () => analysisCatalogUi.loadAnalysisCatalog(),
    loadSavedCohorts: () => savedCohortsUi.loadSavedCohorts(),
    loadQueryDiseaseOptions: () => queryUi.loadDiseaseOptions(),
    loadMolecularDatasets: () => dashboardUi.loadMolecularDatasets(),
    loadPhenoRankerPatientIds: () => phenoUi.loadPhenoRankerPatientIds(),
    renderPhenoTabAvailability: () => navigationUi.renderPhenoTabAvailability(),
    currentTabName: () => navigationUi.currentTabName(),
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    renderQueryExecutionMode: () => analysisCatalogUi.renderQueryExecutionMode(),
    loadAuthUsers: () => usersAdminUi.loadAuthUsers(),
    updateLoadButtonAvailability: () => authUi.updateLoadButtonAvailability(),
  },
});

authUi = createAuthUi({
  refs,
  state,
  callbacks: {
    renderLoadButtonState: () => datasetsUi.renderLoadButtonState(),
    renderJobsDrawer: () => jobsUi.renderJobsDrawer(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    currentTabName: () => navigationUi.currentTabName(),
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    loadAuthUsers: () => usersAdminUi.loadAuthUsers(),
    loadRecentJobs: (options) => jobsUi.loadRecentJobs(options),
    loadSavedCohorts: () => savedCohortsUi.loadSavedCohorts(),
    loadAnalysisCatalog: () => analysisCatalogUi.loadAnalysisCatalog(),
    renderAnalysisSessionList: () => analysisSessionsUi.renderAnalysisSessionList(),
    renderAnalysisThread: () => analysisUi.renderAnalysisThread(),
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
    createAnalysisSession: makeAnalysisSession,
    ensureAnalysisSessionsLoaded: () => analysisSessionsUi.ensureAnalysisSessionsLoaded(),
    loadAnalysisSessionsFromBackend: () => analysisSessionsUi.loadAnalysisSessionsFromBackend(),
    applyAnalysisSession: (session) => analysisSessionsUi.applyAnalysisSession(session),
    loadDatasets: () => datasetsUi.loadDatasets(),
    prepareStartupWorkspaceSelection: () => datasetsUi.prepareStartupWorkspaceSelection(),
    startupDefaultDatasetIds: () => datasetsUi.startupDefaultDatasetIds(),
    loadPatients: (options) => workspaceUi.loadPatients(options),
    loadUserSettings: (options) => userSettingsUi.loadUserSettings(options),
    applyUserSettings: (options) => userSettingsUi.applyUserSettings(options),
  },
});

userSettingsUi = createUserSettingsUi({
  refs,
  state,
  callbacks: {
    effectiveQueryGranularityCeiling: () => datasetsUi.effectiveQueryGranularityCeiling(),
    renderQueryExecutionMode: () => analysisCatalogUi.renderQueryExecutionMode(),
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    setDashboardSubtab: (subtabName) => navigationUi.setDashboardSubtab(subtabName),
    updatePhenoGraphOptions: () => phenoUi.updatePhenoGraphOptions(),
    refreshUserDataAfterDelete: async (kind) => {
      if (kind === "chats") {
        analysisSessionsUi.resetAnalysisSessionsAfterBulkDelete();
        analysisUi.renderAnalysisThread();
        analysisCatalogUi.renderAnalysisCatalog();
      } else if (kind === "jobs") {
        await jobsUi.loadRecentJobs({ silent: true });
      } else if (kind === "cohorts") {
        await savedCohortsUi.loadSavedCohorts();
        dashboardUi.renderAnalysisScopeSummary();
        dashboardUi.renderAnalysisCompareScopeSummary();
        savedCohortsUi.renderPhenoSavedCohortsSelection();
        analysisCatalogUi.renderAnalysisCatalog();
      }
    },
  },
});

function bindEvents() {
  refs.dataDirEl && refs.dataDirEl.addEventListener("change", () => {
    state.pendingDatasetIds = datasetsUi.selectedDatasetIdsFromUi();
    datasetsUi.renderDatasetPicker();
    datasetsUi.renderDatasetAdminList();
    datasetsUi.renderDatasetScopeSummary();
    datasetsUi.renderLoadButtonState();
    authUi.updateLoadButtonAvailability();
  });

  refs.datasetPickerEl && refs.datasetPickerEl.addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-dataset-checkbox]");
    if (!checkbox || !refs.datasetPickerEl.contains(checkbox)) {
      return;
    }
    datasetsUi.syncDatasetSelectionFromPicker();
  });

  refs.datasetAdminListEl && refs.datasetAdminListEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-dataset-save]");
    if (!button || !refs.datasetAdminListEl.contains(button)) {
      const prepareButton = event.target.closest("[data-dataset-prepare]");
      if (!prepareButton || !refs.datasetAdminListEl.contains(prepareButton)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      void datasetsUi.prepareDatasetStore(prepareButton.getAttribute("data-dataset-prepare") || "");
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    void datasetsUi.saveDatasetAccess(button.getAttribute("data-dataset-save") || "");
  });

  refs.loadBtnEl && refs.loadBtnEl.addEventListener("click", () => {
    void workspaceUi.loadPatients({ respectAdminGate: true });
  });

  refs.analysisSidebarToggleBtnEl && refs.analysisSidebarToggleBtnEl.addEventListener("click", () => {
    const collapsed = Boolean(refs.analysisShellEl && refs.analysisShellEl.classList.contains("analysis-sidebar-collapsed"));
    setAnalysisSidebarCollapsed(!collapsed);
  });

  refs.authLoginBtnEl && refs.authLoginBtnEl.addEventListener("click", () => {
    void authUi.loginLocal();
  });
  refs.heroLogoutBtnEl && refs.heroLogoutBtnEl.addEventListener("click", () => {
    void authUi.logoutLocal();
  });
  refs.userSettingsBtnEl && refs.userSettingsBtnEl.addEventListener("click", () => {
    userSettingsUi.setPanelOpen(true);
    userSettingsUi.renderUserSettingsForm();
  });
  refs.userSettingsCloseBtnEl && refs.userSettingsCloseBtnEl.addEventListener("click", () => {
    userSettingsUi.setPanelOpen(false);
  });
  refs.userSettingsSaveBtnEl && refs.userSettingsSaveBtnEl.addEventListener("click", () => {
    void userSettingsUi.saveUserSettings().catch((error) => {
      if (refs.userSettingsStatusEl) {
        refs.userSettingsStatusEl.className = "section-note is-warning";
        refs.userSettingsStatusEl.textContent = error && error.message ? error.message : "Unable to save user settings.";
      }
    });
  });
  refs.userSettingsResetBtnEl && refs.userSettingsResetBtnEl.addEventListener("click", () => {
    void userSettingsUi.resetUserSettings().catch((error) => {
      if (refs.userSettingsStatusEl) {
        refs.userSettingsStatusEl.className = "section-note is-warning";
        refs.userSettingsStatusEl.textContent = error && error.message ? error.message : "Unable to reset user settings.";
      }
    });
  });
  refs.userDeleteChatsBtnEl && refs.userDeleteChatsBtnEl.addEventListener("click", () => {
    void userSettingsUi.deleteUserData("chats");
  });
  refs.userDeleteJobsBtnEl && refs.userDeleteJobsBtnEl.addEventListener("click", () => {
    void userSettingsUi.deleteUserData("jobs");
  });
  refs.userDeleteCohortsBtnEl && refs.userDeleteCohortsBtnEl.addEventListener("click", () => {
    void userSettingsUi.deleteUserData("cohorts");
  });
  refs.authPasswordEl && refs.authPasswordEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void authUi.loginLocal();
    }
  });

  refs.askBtnEl && refs.askBtnEl.addEventListener("click", () => {
    void queryUi.askQuery();
  });
  refs.queryPlannerBtnEl && refs.queryPlannerBtnEl.addEventListener("click", () => {
    queryUi.setExecutionMode(state.queryExecutionMode === "planner_only" ? "auto" : "planner_only");
    analysisCatalogUi.renderQueryExecutionMode();
  });
  refs.queryMemoryBtnEl && refs.queryMemoryBtnEl.addEventListener("click", () => {
    if (state.queryGranularityMode !== "detailed") {
      analysisCatalogUi.renderQueryExecutionMode();
      return;
    }
    state.queryFollowMemoryEnabled = !state.queryFollowMemoryEnabled;
    analysisCatalogUi.renderQueryExecutionMode();
  });
  refs.queryDiseaseBuilderBtnEl && refs.queryDiseaseBuilderBtnEl.addEventListener("click", () => {
    const willOpen = !refs.queryDiseasePanelEl || refs.queryDiseasePanelEl.classList.contains("is-hidden");
    if (refs.queryDiseasePanelEl) refs.queryDiseasePanelEl.classList.toggle("is-hidden", !willOpen);
    refs.queryDiseaseBuilderBtnEl.classList.toggle("is-active", willOpen);
  });
  refs.queryClearBtnEl && refs.queryClearBtnEl.addEventListener("click", () => {
    queryUi.resetQueryWorkspace();
    state.queryFollowMemoryEnabled = false;
    if (refs.queryDiseasePanelEl) refs.queryDiseasePanelEl.classList.add("is-hidden");
    refs.queryDiseaseBuilderBtnEl && refs.queryDiseaseBuilderBtnEl.classList.remove("is-active");
    refs.queryStatusEl.className = "query-status";
    refs.queryStatusEl.textContent = "Query thread cleared.";
    analysisCatalogUi.renderQueryExecutionMode();
  });

  refs.analysisRunBtnEl && refs.analysisRunBtnEl.addEventListener("click", () => {
    void analysisUi.runAnalysis();
  });
  refs.analysisFlowBarEl && refs.analysisFlowBarEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-flow-target]");
    if (!button || !refs.analysisFlowBarEl.contains(button)) {
      return;
    }
    const target = String(button.dataset.analysisFlowTarget || "");
    if (target === "scope") {
      const setup = document.querySelector("#analysisTab .analysis-setup-card");
      if (setup) {
        setup.open = true;
        setup.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } else if (target === "analysis" || target === "choose") {
      analysisCatalogUi.setAnalysisCatalogDrawerOpen(true);
    } else if (target === "prompt") {
      refs.analysisPromptEl && refs.analysisPromptEl.focus();
      refs.analysisPromptEl && refs.analysisPromptEl.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (target === "requirements") {
      if (refs.analysisCatalogMolecularPanelEl && !refs.analysisCatalogMolecularPanelEl.classList.contains("is-hidden")) {
        refs.analysisCatalogMolecularPanelEl.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        analysisCatalogUi.setAnalysisCatalogDrawerOpen(true);
      }
    } else if (target === "run") {
      refs.analysisPromptEl && refs.analysisPromptEl.focus();
      refs.analysisPromptEl && refs.analysisPromptEl.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (target === "results") {
      refs.analysisThreadEl && refs.analysisThreadEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  refs.analysisComposerExamplesBtnEl && refs.analysisComposerExamplesBtnEl.addEventListener("click", () => {
    state.analysisExamplesPinnedOpen = true;
    analysisCatalogUi.renderAnalysisStarterPrompts();
    if (refs.analysisStarterPanelEl && !refs.analysisStarterPanelEl.hidden) {
      refs.analysisStarterPanelEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  refs.analysisNewSessionBtnEl && refs.analysisNewSessionBtnEl.addEventListener("click", () => {
    analysisSessionsUi.createAndSelectAnalysisSession({ dataDir: refs.dataDirEl.value.trim() });
  });

  refs.dashboardTabBtnEl && refs.dashboardTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("dashboard"));
  refs.datasetsTabBtnEl && refs.datasetsTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("datasets"));
  refs.dataTabBtnEl && refs.dataTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("data"));
  refs.usersTabBtnEl && refs.usersTabBtnEl.addEventListener("click", () => {
    navigationUi.setActiveTab("users");
    void usersAdminUi.loadAuthUsers();
  });
  refs.queryTabBtnEl && refs.queryTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("query"));
  refs.analysisTabBtnEl && refs.analysisTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("analysis"));
  refs.phenoTabBtnEl && refs.phenoTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("pheno"));
  refs.dashboardClinicalBtnEl && refs.dashboardClinicalBtnEl.addEventListener("click", () => navigationUi.setDashboardSubtab("clinical"));
  refs.dashboardMolecularBtnEl && refs.dashboardMolecularBtnEl.addEventListener("click", () => navigationUi.setDashboardSubtab("molecular"));

  refs.userCreateBtnEl && refs.userCreateBtnEl.addEventListener("click", () => {
    void usersAdminUi.createAuthUser();
  });
  refs.usersListEl && refs.usersListEl.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-auth-user-action]");
    if (!trigger) {
      return;
    }
    const action = String(trigger.dataset.authUserAction || "");
    const username = String(trigger.dataset.authUser || "");
    if (!username) {
      return;
    }
    if (action === "save") {
      void usersAdminUi.saveAuthUser(username);
    } else if (action === "reset-password") {
      void usersAdminUi.resetAuthUserPassword(username);
    } else if (action === "delete") {
      void usersAdminUi.deleteAuthUser(username);
    }
  });

  refs.phenoPlanBtnEl && refs.phenoPlanBtnEl.addEventListener("click", () => {
    void phenoUi.planPhenoRanker();
  });
  refs.phenoPlanRunBtnEl && refs.phenoPlanRunBtnEl.addEventListener("click", () => {
    void phenoUi.planAndRunPhenoRanker();
  });
  refs.phenoRunBtnEl && refs.phenoRunBtnEl.addEventListener("click", () => {
    void phenoUi.runPhenoRanker();
  });
  refs.phenoFlowBarEl && refs.phenoFlowBarEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-pheno-flow-target]");
    if (!button || !refs.phenoFlowBarEl.contains(button)) {
      return;
    }
    const target = String(button.dataset.phenoFlowTarget || "");
    if (target === "scope" || target === "setup") {
      if (refs.phenoSetupDetailsEl) {
        refs.phenoSetupDetailsEl.open = true;
        refs.phenoSetupDetailsEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } else if (target === "plan") {
      if (refs.phenoSetupDetailsEl) refs.phenoSetupDetailsEl.open = true;
      if (refs.phenoPlanDetailsEl) {
        refs.phenoPlanDetailsEl.open = true;
        refs.phenoPlanDetailsEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    } else if (target === "run") {
      refs.phenoRunPanelEl && refs.phenoRunPanelEl.scrollIntoView({ behavior: "smooth", block: "center" });
      refs.phenoPromptEl && refs.phenoPromptEl.focus();
    } else if (target === "results") {
      const resultTarget = refs.phenoResultWorkspaceEl && !refs.phenoResultWorkspaceEl.classList.contains("is-hidden")
        ? refs.phenoResultWorkspaceEl
        : refs.phenoResultEmptyStateEl;
      resultTarget && resultTarget.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  refs.phenoAnalysisBtnEl && refs.phenoAnalysisBtnEl.addEventListener("click", () => {
    phenoUi.sendPhenoMatchesToAnalysis();
  });
  refs.phenoCopyIdsBtnEl && refs.phenoCopyIdsBtnEl.addEventListener("click", () => {
    void phenoUi.copyPhenoMatchIds();
  });
  refs.phenoExplainBtnEl && refs.phenoExplainBtnEl.addEventListener("click", () => {
    void phenoUi.explainPhenoResults();
  });
  refs.phenoExplainLlmBtnEl && refs.phenoExplainLlmBtnEl.addEventListener("click", () => {
    void phenoUi.explainPhenoResultsWithLlm();
  });
  refs.phenoModeEl && refs.phenoModeEl.addEventListener("change", () => {
    phenoUi.markPhenoManualOverride();
    phenoUi.updatePhenoMode();
    phenoUi.renderPhenoFlowBar();
  });
  refs.phenoActionEl && refs.phenoActionEl.addEventListener("change", () => {
    phenoUi.markPhenoManualOverride();
    phenoUi.updatePhenoMode();
    phenoUi.renderPhenoFlowBar();
  });
  refs.phenoSelectedPatientIdsEl && refs.phenoSelectedPatientIdsEl.addEventListener("input", () => {
    phenoUi.markPhenoManualOverride();
    phenoUi.renderSelectedPatientIdsSummary();
    phenoUi.renderPhenoFlowBar();
  });
  [
    refs.phenoPatientIdEl,
    refs.phenoIncludeTermsEl,
    refs.phenoExcludeTermsEl,
    refs.phenoSimilarityMetricEl,
    refs.phenoSortByEl,
    refs.phenoMaxOutEl,
    refs.phenoGraphMinWeightEl,
    refs.phenoGraphMaxWeightEl,
  ].forEach((element) => {
    element && element.addEventListener("input", () => phenoUi.markPhenoManualOverride());
  });
  refs.phenoSimilarityMetricEl && refs.phenoSimilarityMetricEl.addEventListener("input", () => {
    phenoUi.updatePhenoGraphOptions();
  });
  refs.phenoSimilarityMetricEl && refs.phenoSimilarityMetricEl.addEventListener("change", () => {
    phenoUi.updatePhenoGraphOptions();
  });
  [
    refs.phenoAlignEl,
    refs.phenoRenderHeatmapEl,
    refs.phenoRenderMdsEl,
    refs.phenoRenderGraphEl,
  ].forEach((element) => {
    element && element.addEventListener("change", () => {
      phenoUi.markPhenoManualOverride();
      phenoUi.updatePhenoGraphOptions();
    });
  });

  refs.analysisSelectedPatientIdsEl && refs.analysisSelectedPatientIdsEl.addEventListener("input", () => {
    dashboardUi.renderAnalysisScopeSummary();
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisCompareModeEl && refs.analysisCompareModeEl.addEventListener("change", () => {
    analysisUi.renderAnalysisCompareMode();
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisCompareSelectedPatientIdsEl && refs.analysisCompareSelectedPatientIdsEl.addEventListener("input", () => {
    dashboardUi.renderAnalysisCompareScopeSummary();
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisPromptEl && refs.analysisPromptEl.addEventListener("input", () => {
    state.analysisExecutionMode = "auto";
    state.analysisSelectedCatalogItemId = "";
    analysisCatalogUi.renderAnalysisCatalogMolecularPanel();
    analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  });

  const handleMolecularDatasetListChange = (event) => {
    const checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox) {
      return;
    }
    dashboardUi.handleMolecularDatasetSelectionChange(event.currentTarget, checkbox);
    analysisCatalogUi.renderAnalysisCatalogMolecularPanel();
    analysisCatalogUi.renderAnalysisCatalog();
  };
  refs.analysisMolecularDatasetListEl && refs.analysisMolecularDatasetListEl.addEventListener("change", handleMolecularDatasetListChange);
  refs.analysisCatalogMolecularDatasetListEl && refs.analysisCatalogMolecularDatasetListEl.addEventListener("change", handleMolecularDatasetListChange);
  refs.analysisMolecularGeneEl && refs.analysisMolecularGeneEl.addEventListener("input", () => {
    dashboardUi.handleMolecularGeneInput();
  });
  refs.analysisMolecularRunBtnEl && refs.analysisMolecularRunBtnEl.addEventListener("click", () => {
    void dashboardUi.runMolecularExpressionAnalysis();
  });

  refs.patientsEl && refs.patientsEl.addEventListener("click", (event) => {
    const card = event.target.closest(".patient-card");
    if (!card || !refs.patientsEl.contains(card)) {
      return;
    }
    void workspaceUi.loadPatient(card.dataset.patientId);
  });
  refs.patientSearchEl && refs.patientSearchEl.addEventListener("input", () => {
    dashboardUi.renderPatientList(workspaceUi.filterPatients(refs.patientSearchEl.value));
  });

  refs.queryExamplesEl && refs.queryExamplesEl.addEventListener("click", (event) => {
    queryUi.handleQueryExamplesClick(event);
  });
  refs.queryFollowupsEl && refs.queryFollowupsEl.addEventListener("click", (event) => {
    queryUi.handleQueryFollowupsClick(event);
  });
  document.addEventListener("click", (event) => {
    queryUi.handleDocumentClick(event);
  });

  refs.analysisExamplesEl && refs.analysisExamplesEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-prompt]");
    if (!button || !refs.analysisExamplesEl.contains(button)) {
      return;
    }
    refs.analysisPromptEl.value = button.dataset.analysisPrompt || "";
    state.analysisExecutionMode = button.dataset.analysisLlmOnly === "true"
      ? "llm_only"
      : (button.dataset.analysisDeterministic === "true" ? "deterministic" : "planner_only");
    state.analysisSelectedCatalogItemId = "";
    analysisCatalogUi.renderAnalysisCatalogMolecularPanel();
    state.analysisExamplesPinnedOpen = false;
    analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
    analysisCatalogUi.renderAnalysisStarterPrompts();
    if ((state.analysisExecutionMode === "planner_only" || state.analysisExecutionMode === "llm_only") && (!state.lmStatus || state.lmStatus.available !== true)) {
      refs.analysisStatusEl.className = "query-status";
      refs.analysisStatusEl.textContent = state.analysisExecutionMode === "planner_only"
        ? "LLM planner unavailable. Start an LLM model or choose a deterministic analysis."
        : "LLM unavailable. Start an LLM model or choose a deterministic analysis.";
    }
    refs.analysisPromptEl.focus();
  });
  refs.analysisCatalogListEl && refs.analysisCatalogListEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-catalog-id]");
    if (!button || !refs.analysisCatalogListEl.contains(button)) {
      return;
    }
    analysisCatalogUi.applyAnalysisCatalogItemById(button.dataset.analysisCatalogId || "");
  });
  refs.analysisCatalogDrawerListEl && refs.analysisCatalogDrawerListEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-catalog-id]");
    if (!button || !refs.analysisCatalogDrawerListEl.contains(button)) {
      return;
    }
    analysisCatalogUi.applyAnalysisCatalogItemById(button.dataset.analysisCatalogId || "");
  });
  refs.analysisCatalogBrowseBtnEl && refs.analysisCatalogBrowseBtnEl.addEventListener("click", () => {
    analysisCatalogUi.setAnalysisCatalogDrawerOpen(true);
  });
  refs.analysisCatalogSearchEl && refs.analysisCatalogSearchEl.addEventListener("input", () => {
    analysisCatalogUi.setAnalysisCatalogSearch(refs.analysisCatalogSearchEl.value || "");
  });
  refs.analysisCatalogDrawerSearchEl && refs.analysisCatalogDrawerSearchEl.addEventListener("input", () => {
    analysisCatalogUi.setAnalysisCatalogSearch(refs.analysisCatalogDrawerSearchEl.value || "");
  });
  refs.analysisCatalogFiltersEl && refs.analysisCatalogFiltersEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-catalog-filter]");
    if (!button || !refs.analysisCatalogFiltersEl.contains(button)) {
      return;
    }
    analysisCatalogUi.setAnalysisCatalogFilter(button.dataset.analysisCatalogFilter || "all");
  });
  refs.analysisCatalogDrawerFiltersEl && refs.analysisCatalogDrawerFiltersEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-catalog-filter]");
    if (!button || !refs.analysisCatalogDrawerFiltersEl.contains(button)) {
      return;
    }
    analysisCatalogUi.setAnalysisCatalogFilter(button.dataset.analysisCatalogFilter || "all");
  });
  refs.analysisCatalogDrawerCloseBtnEl && refs.analysisCatalogDrawerCloseBtnEl.addEventListener("click", () => {
    analysisCatalogUi.setAnalysisCatalogDrawerOpen(false);
  });
  refs.analysisCatalogDrawerEl && refs.analysisCatalogDrawerEl.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-analysis-catalog-close='true']");
    if (!trigger || !refs.analysisCatalogDrawerEl.contains(trigger)) {
      return;
    }
    analysisCatalogUi.setAnalysisCatalogDrawerOpen(false);
  });

  refs.jobsDrawerBtnEl && refs.jobsDrawerBtnEl.addEventListener("click", () => {
    jobsUi.setJobsDrawerOpen(true);
    void jobsUi.loadRecentJobs();
  });
  refs.jobsDrawerCloseBtnEl && refs.jobsDrawerCloseBtnEl.addEventListener("click", () => {
    jobsUi.setJobsDrawerOpen(false);
  });
  refs.jobsDrawerEl && refs.jobsDrawerEl.addEventListener("click", (event) => {
    const closeTrigger = event.target.closest("[data-jobs-drawer-close='true']");
    if (closeTrigger && refs.jobsDrawerEl.contains(closeTrigger)) {
      jobsUi.setJobsDrawerOpen(false);
      return;
    }
    const openButton = event.target.closest("[data-job-open-result], [data-job-open-pheno]");
    if (!openButton || !refs.jobsDrawerEl.contains(openButton)) {
      return;
    }
    void jobsUi.openJobResult(openButton.dataset.jobOpenResult || openButton.dataset.jobOpenPheno || "").catch((error) => {
      const isPheno = Boolean(openButton.dataset.jobOpenPheno);
      const statusEl = isPheno ? refs.phenoStatusEl : refs.analysisStatusEl;
      statusEl.className = "query-status";
      statusEl.textContent = error && error.message ? error.message : "Unable to load job result.";
    });
  });

  refs.analysisThreadEl && refs.analysisThreadEl.addEventListener("click", (event) => {
    analysisUi.handleAnalysisResultBoardClick(event);
    analysisUi.handleAnalysisPlotViewClick(event);
    analysisUi.handleAnalysisFollowUpsClick(event);
  });
  refs.analysisSessionListEl && refs.analysisSessionListEl.addEventListener("click", (event) => {
    const deleteButton = event.target.closest("[data-analysis-session-delete]");
    if (deleteButton && refs.analysisSessionListEl.contains(deleteButton)) {
      analysisSessionsUi.deleteAnalysisSessionById(deleteButton.dataset.analysisSessionDelete || "");
      return;
    }
    const renameButton = event.target.closest("[data-analysis-session-rename]");
    if (renameButton && refs.analysisSessionListEl.contains(renameButton)) {
      analysisSessionsUi.renameAnalysisSession(renameButton.dataset.analysisSessionRename || "");
      return;
    }
    const button = event.target.closest("[data-analysis-session-id]");
    if (!button || !refs.analysisSessionListEl.contains(button)) {
      return;
    }
    analysisSessionsUi.selectAnalysisSession(button.dataset.analysisSessionId || "");
  });

  refs.phenoExamplesEl && refs.phenoExamplesEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-pheno-prompt]");
    if (!button || !refs.phenoExamplesEl.contains(button)) {
      return;
    }
    refs.phenoPromptEl.value = button.dataset.phenoPrompt || "";
    phenoUi.handlePhenoPromptEdited();
    refs.phenoPromptEl.focus();
  });
  refs.phenoPromptEl && refs.phenoPromptEl.addEventListener("input", () => {
    phenoUi.handlePhenoPromptEdited();
  });
  refs.phenoPreviewsEl && refs.phenoPreviewsEl.addEventListener("click", (event) => {
    phenoUi.handlePreviewsClick(event);
  });
  refs.phenoOutputPreviewEl && refs.phenoOutputPreviewEl.addEventListener("click", (event) => {
    phenoUi.handleOutputPreviewClick(event);
  });

  refs.savedCohortsEl && refs.savedCohortsEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-saved-cohort-action]");
    if (!button || !refs.savedCohortsEl.contains(button)) {
      return;
    }
    savedCohortsUi.handleSavedCohortAction(button);
  });
  refs.analysisSelectedSavedCohortSelectionEl && refs.analysisSelectedSavedCohortSelectionEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-clear-saved-cohort]");
    if (!button || !refs.analysisSelectedSavedCohortSelectionEl.contains(button)) {
      return;
    }
    savedCohortsUi.clearSavedCohortFromAnalysis("a");
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisCompareSavedCohortSelectionEl && refs.analysisCompareSavedCohortSelectionEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-clear-saved-cohort]");
    if (!button || !refs.analysisCompareSavedCohortSelectionEl.contains(button)) {
      return;
    }
    savedCohortsUi.clearSavedCohortFromAnalysis("b");
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.phenoSavedCohortsEl && refs.phenoSavedCohortsEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-saved-cohort-action]");
    if (!button || !refs.phenoSavedCohortsEl.contains(button)) {
      return;
    }
    savedCohortsUi.handleSavedCohortAction(button);
  });
  refs.phenoSavedCohortsSelectionEl && refs.phenoSavedCohortsSelectionEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-pheno-selected-cohort-id]");
    if (!button || !refs.phenoSavedCohortsSelectionEl.contains(button)) {
      return;
    }
    savedCohortsUi.removeSavedCohortFromPheno(button.dataset.phenoSelectedCohortId || "");
  });

  refs.questionEl && refs.questionEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void queryUi.askQuery();
    }
  });
  refs.questionEl && refs.questionEl.addEventListener("input", () => {
    analysisCatalogUi.renderQueryExecutionMode();
  });
  refs.analysisPromptEl && refs.analysisPromptEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void analysisUi.runAnalysis();
    }
  });
}

function applyStoredTabPreferences() {
  try {
    const savedTab = window.localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
    const savedDashboardSubtab = window.localStorage.getItem(DASHBOARD_SUBTAB_STORAGE_KEY);
    if (savedDashboardSubtab && ["clinical", "molecular"].includes(savedDashboardSubtab)) {
      navigationUi.setDashboardSubtab(savedDashboardSubtab);
    }
    if (savedTab && ["dashboard", "cohort", "molecular", "datasets", "data", "users", "query", "analysis", "pheno"].includes(savedTab)) {
      if (savedTab === "cohort") {
        navigationUi.setDashboardSubtab("clinical");
        navigationUi.setActiveTab("dashboard");
      } else if (savedTab === "molecular") {
        navigationUi.setDashboardSubtab("molecular");
        navigationUi.setActiveTab("dashboard");
      } else if ((savedTab === "data" || savedTab === "users") && state.authState.enabled && !authUi.canManageDataset()) {
        navigationUi.setActiveTab("datasets");
      } else {
        navigationUi.setActiveTab(savedTab);
      }
    }
  } catch (_error) {
  }
}

function initializeUiShell() {
  analysisCatalogUi.initializeExampleToggle(refs.queryExamplesEl);
  analysisCatalogUi.initializeExampleToggle(refs.phenoExamplesEl);
  analysisCatalogUi.initializeExampleToggle(refs.analysisExamplesEl);
  analysisCatalogUi.renderQueryStarterPrompts();
  analysisCatalogUi.renderAnalysisStarterPrompts();
  initializeAnalysisSidebarCollapsed();
  navigationUi.setDashboardSubtab(state.currentDashboardSubtab);
  applyStoredTabPreferences();
  phenoUi.updatePhenoExplainActions();
  phenoUi.updatePhenoResultActions();
  phenoUi.updatePhenoRunAvailability();
  phenoUi.renderPhenoFlowBar();
  phenoUi.updatePhenoMode();
  phenoUi.renderSelectedPatientIdsSummary();
  analysisCatalogUi.renderQueryExecutionMode();
  phenoUi.setPhenoResultWorkspaceVisible(false);
  savedCohortsUi.renderPhenoSavedCohortsSelection();
  analysisSessionsUi.ensureAnalysisSessionsLoaded();
  void analysisSessionsUi.loadAnalysisSessionsFromBackend();
  analysisUi.renderAnalysisCompareMode();
  dashboardUi.renderAnalysisCompareScopeSummary();
  workspaceUi.renderGlobalContext();
  phenoUi.renderPhenoAlignmentPlaceholder("Run patient mode, then click one row in rank.txt to inspect matched variables for that pair.");
  phenoUi.renderPhenoExplainPlaceholder("Run patient mode, then click Explain results to summarize the top matches from rank.txt.");
}

async function bootstrap() {
  bindEvents();
  initializeUiShell();
  window.__patientNavigatorLoadPatients = (options) => workspaceUi.loadPatients(options);
  window.__patientNavigatorAskQuery = () => queryUi.askQuery();
  await workspaceUi.loadLmStatus();
  await authUi.fetchAuthStatus();
  if (!authUi.isWorkspaceAccessible()) {
    authUi.clearLoadedWorkspaceForSignedOutState();
    return;
  }
  await userSettingsUi.loadUserSettings({ applyNavigation: false });
  await datasetsUi.loadDatasets();
  datasetsUi.prepareStartupWorkspaceSelection();
  await workspaceUi.loadPatients({ respectAdminGate: false, targetDatasetIds: datasetsUi.startupDefaultDatasetIds() });
  await authUi.refreshUserWorkspaceState();
  userSettingsUi.applyUserSettings({ applyNavigation: true });
}

void bootstrap();
