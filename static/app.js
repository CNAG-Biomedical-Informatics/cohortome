import { escapeHtml, fallbackCopyText, renderActivityCard } from "/static/js/shared.js";
import { createAppRefs } from "/static/js/app_refs.js";
import { createAppState } from "/static/js/app_state.js";
import { nowIso, shortTimestamp, currentStorageNamespace, createAnalysisSession, createSelectionMetadata, formatNumber } from "/static/js/app_helpers.js";
import { createNavigationUi } from "/static/js/app_navigation.js";
import { initializeNavigationShell } from "/static/js/navigation_shell.js";
import { createWorkspaceUi } from "/static/js/workspace_ui.js";
import { createAuthUi } from "/static/js/auth_ui.js";
import { createUsersAdminUi } from "/static/js/users_admin_ui.js";
import { createModelsAdminUi } from "/static/js/models_admin_ui.js";
import { createDatasetsUi } from "/static/js/datasets_ui.js";
import { createAnalysisCatalogUi } from "/static/js/analysis_catalog_ui.js";
import { createJobsUi } from "/static/js/jobs_ui.js";
import { createDashboardUi } from "/static/js/dashboard.js";
import { createAnalysisSessionsUi } from "/static/js/analysis_sessions.js";
import { createSavedCohortsUi } from "/static/js/saved_cohorts.js";
import { createPhenoUi } from "/static/js/pheno.js";
import { createQueryUi } from "/static/js/query.js";
import { createQuerySessionsUi } from "/static/js/query_sessions.js";
import { createPhenoSessionsUi } from "/static/js/pheno_sessions.js";
import { createChatFoldersUi } from "/static/js/chat_folders.js";
import { createChatDeletionUi } from "/static/js/chat_deletion.js";
import { createAnalysisUi } from "/static/js/analysis.js";
import { createUserSettingsUi } from "/static/js/user_settings.js";
import { createDeploymentBrandingUi } from "/static/js/deployment_branding.js";
import { createProjectsUi } from "/static/js/projects.js";
import { createPatientOverview } from "/static/js/patient_overview.js";

const refs = createAppRefs(document);
const state = createAppState();
const deploymentBrandingUi = createDeploymentBrandingUi();

const MAX_VISIBLE_PATIENTS = 80;
const MAX_VISIBLE_EXAMPLES = 8;
const ACTIVE_TAB_STORAGE_KEY = "cohortome.active-tab";
const DASHBOARD_SUBTAB_STORAGE_KEY = "cohortome.dashboard-subtab";
const ANALYSIS_SESSIONS_STORAGE_KEY = "cohortome.analysis-sessions";
const ANALYSIS_SIDEBAR_COLLAPSED_STORAGE_KEY = "cohortome.analysis-sidebar-collapsed";
const TAB_HELPER_TEXT = {
  dashboard: "Browse the loaded clinical, assay, imaging, and multimodal workspace data",
  timeline: "Review longitudinal patient events and select patients for downstream analysis",
  clinical: "Review the clinical workspace overview",
  assay: "Inspect loaded assay modalities, DICOM status, and expression coverage",
  datasets: "Choose the authorized datasets that define your active workspace scope",
  cohorts: "Find saved patient and sample groups across your datasets",
  data: "Admin-only dataset visibility and access policy management",
  users: "Admin-only local user and group management",
  models: "Admin-only approved LLM endpoint registry and health",
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
let modelsAdminUi;
let datasetsUi;
let analysisCatalogUi;
let jobsUi;
let dashboardUi;
let analysisSessionsUi;
let savedCohortsUi;
let phenoUi;
let queryUi;
let querySessionsUi;
let phenoSessionsUi;
let chatFoldersUi;
let chatDeletionUi;
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

async function restoreChatWorkspace(scope) {
  if (state.loadInFlight || state.queryInFlight || state.analysisInFlight) {
    throw new Error('Wait for the current operation to finish before changing workspace.');
  }
  const ids = scope.startsWith('scope--') ? scope.slice('scope--'.length).split('--') : [scope];
  if (!ids.length || ids.some(id => !state.availableDatasets.some(item => item.dataset_id === id))) {
    throw new Error('An original dataset is unavailable or you no longer have access to it.');
  }
  state.pendingDatasetIds = ids;
  // Use the normal loading path: it checks data availability and permissions
  // before persisting the selection. Never restore only a subset of the scope.
  await workspaceUi.loadPatients();
  if (state.currentDatasetScopeId !== scope) {
    throw new Error('The original workspace could not be loaded. Check its availability in Datasets.');
  }
}

function clearDatasetScopedContent(options = {}) {
  const signedOut = options.signedOut === true;
  if (signedOut) querySessionsUi?.clear();
  if (signedOut) savedCohortsUi?.clearLibrary();
  if (signedOut) phenoSessionsUi?.clear();
  if (signedOut) { chatDeletionUi?.clear(); chatFoldersUi?.clear(); }
  const clearSelection = options.clearSelection === true;
  const nextScopeId = String(options.nextScopeId || "").trim();
  state.workspaceRevision += 1;
  stopQueryProgressUpdates();
  stopAnalysisProgressUpdates();
  state.queryInFlight = false;
  state.analysisInFlight = false;
  state.currentPatients = [];
  state.selectedPatientId = null;
  state.dashboardSummaryState = null;
  state.dashboardSummary = null;
  state.timelinePatientFilter = '';
  state.timelinePatientSearch = '';
  state.timelineDatasetFilter = '';
  state.timelinePage = 0;
  state.savedCohorts = [];
  state.phenoRankerPatientIds = [];
  state.phenoReferenceFiles = [];
  state.phenoSelectedSavedCohortIds = [];
  state.analysisCatalogItems = [];
  state.analysisCatalogWorkspace = null;
  state.analysisSelectedCatalogItemId = "";
  if (clearSelection) {
    state.currentDatasetIds = [];
    state.pendingDatasetIds = [];
    state.currentDatasetScopeId = "";
    state.availableDatasets = signedOut ? [] : state.availableDatasets;
    if (refs.dataDirEl) refs.dataDirEl.dataset.scopeId = "";
  }
  if (refs.patientSearchEl) refs.patientSearchEl.value = "";
  if (refs.askBtnEl) refs.askBtnEl.disabled = false;
  if (refs.analysisRunBtnEl) refs.analysisRunBtnEl.disabled = false;
  if (refs.phenoSelectedPatientIdsEl) refs.phenoSelectedPatientIdsEl.value = "";

  if (queryUi) queryUi.resetQueryWorkspace();
  if (phenoUi) phenoUi.clearDatasetWorkspace();
  if (dashboardUi) dashboardUi.clearDatasetWorkspaceViews({ signedOut });
  if (savedCohortsUi) savedCohortsUi.renderSavedCohorts();
  if (analysisSessionsUi) analysisSessionsUi.prepareAnalysisSessionForDataDir(nextScopeId);
  if (analysisCatalogUi) analysisCatalogUi.renderAnalysisCatalog();

  const patientMessage = signedOut ? "Sign in to access the shared clinical workspace." : (nextScopeId ? "Loading selected workspace..." : "No dataset selected.");
  const detailMessage = signedOut ? "Patient workspace hidden until you sign in." : (nextScopeId ? "Loading patient workspace..." : "Select a workspace to inspect the patient workspace.");
  const dashboardMessage = signedOut ? "Clinical dashboard hidden until you sign in." : (nextScopeId ? "Loading dashboard..." : "Select a workspace to inspect the dashboard.");
  const timelineMessage = signedOut ? "Timeline hidden until you sign in." : (nextScopeId ? "Loading timeline..." : "Select a workspace to inspect the timeline.");
  if (refs.patientsEl) refs.patientsEl.innerHTML = `<div class="empty">${patientMessage}</div>`;
  if (refs.detailEl) refs.detailEl.innerHTML = `<div class="empty">${detailMessage}</div>`;
  if (refs.dashboardEl) refs.dashboardEl.innerHTML = `<div class="empty">${dashboardMessage}</div>`;
  if (refs.dashboardTimelineEl) refs.dashboardTimelineEl.innerHTML = `<div class="empty">${timelineMessage}</div>`;
}

function setLatestQueryState(patch) {
  if (Object.prototype.hasOwnProperty.call(patch, "ids")) {
    state.latestQueryPatientIds = Array.isArray(patch.ids) ? patch.ids : [];
  }
  if (Object.prototype.hasOwnProperty.call(patch, "recordIds")) {
    state.latestQueryRecordIds = Array.isArray(patch.recordIds) ? patch.recordIds : [];
  }
  if (Object.prototype.hasOwnProperty.call(patch, "resultHandle")) {
    state.latestQueryResultHandle = String(patch.resultHandle || "").trim();
  }
  if (Object.prototype.hasOwnProperty.call(patch, "totalCount")) {
    state.latestQueryTotalCount = Math.max(0, Number(patch.totalCount || 0));
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
    resultHandle: patch && Object.prototype.hasOwnProperty.call(patch, "resultHandle")
      ? String(patch.resultHandle || "").trim()
      : String(state.latestScopedContext.resultHandle || ""),
    totalCount: patch && Object.prototype.hasOwnProperty.call(patch, "totalCount")
      ? Math.max(0, Number(patch.totalCount || 0))
      : Math.max(0, Number(state.latestScopedContext.totalCount || 0)),
    idType: patch && patch.idType ? patch.idType : state.latestScopedContext.idType,
    sourceTab: patch && patch.sourceTab ? patch.sourceTab : state.latestScopedContext.sourceTab,
    prompt: patch && typeof patch.prompt === "string" ? patch.prompt : state.latestScopedContext.prompt,
  };
}

function currentAnalysisDatasetMetadata() {
  const datasetIds = Array.isArray(state.currentDatasetIds) ? state.currentDatasetIds.slice() : [];
  const datasetId = typeof datasetsUi !== "undefined" && datasetsUi && typeof datasetsUi.currentDatasetSelectionKey === "function"
    ? String(datasetsUi.currentDatasetSelectionKey() || "").trim()
    : "";
  return {
    datasetId,
    datasetIds,
    dataDir: refs.dataDirEl && refs.dataDirEl.value ? refs.dataDirEl.value.trim() : "",
  };
}

function setAnalysisScopeMetadataFromSelection(options = {}) {
  const source = options && typeof options === "object" ? options : {};
  const dataset = currentAnalysisDatasetMetadata();
  const metadata = createSelectionMetadata({
    ...dataset,
    ...source,
  });
  if (source.side === "b") {
    state.analysisCompareScopeMetadata = metadata;
  } else {
    state.analysisScopeMetadata = metadata;
  }
  return metadata;
}

function clearAnalysisScopeMetadata(side = "a") {
  if (side === "b") {
    state.analysisCompareScopeMetadata = {};
  } else {
    state.analysisScopeMetadata = {};
  }
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
  const resultHandle = String(state.latestQueryResultHandle || "").trim();
  if (!scopeIds.length && !resultHandle) {
    return;
  }
  state.analysisSelectedSavedCohortId = "";
  analysisUi.setContextMode("workspace");
  refs.analysisSelectedPatientIdsEl.value = scopeIds.join(",");
  setAnalysisScopeMetadataFromSelection({
    sampleIds: state.latestQueryRecordIds,
    patientIds: state.latestQueryPatientIds,
    queryResultHandle: resultHandle,
    patientCount: state.latestQueryIdType === "sample"
      ? 0
      : state.latestQueryTotalCount || state.latestQueryPatientIds.length,
    sampleCount: state.latestQueryIdType === "sample"
      ? state.latestQueryTotalCount || state.latestQueryRecordIds.length
      : state.latestQueryRecordIds.length,
    idType: state.latestQueryRecordIds.length ? "sample" : state.latestQueryIdType,
    sourceKind: "query",
    sourcePrompt: state.latestQueryPrompt,
  });
  if (state.latestQueryAnalysisPrompt && !refs.analysisPromptEl.value.trim()) {
    refs.analysisPromptEl.value = state.latestQueryAnalysisPrompt;
  }
  dashboardUi.renderAnalysisScopeSummary();
  navigationUi.setActiveTab("analysis");
  analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  refs.analysisStatusEl.className = "query-status";
  const resultUnit = state.latestQueryIdType === "sample" ? "sample" : "patient";
  refs.analysisStatusEl.textContent = resultHandle
    ? `Loaded the ${state.latestQueryTotalCount}-${resultUnit} Query result into Analysis without expanding its identifiers in the browser. Run the analysis prompt to interpret this workspace.`
    : state.latestQueryRecordIds.length
    ? `Loaded ${state.latestQueryRecordIds.length} sample IDs from Query into Analysis. Run the analysis prompt to interpret this workspace.`
    : `Loaded ${state.latestQueryPatientIds.length} patient IDs from Query into Analysis. Run the analysis prompt to interpret this workspace.`;
}

function sendPatientIdsToAnalysisFromSource(patientIds, options = {}) {
  const ids = Array.isArray(patientIds)
    ? patientIds.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  if (!ids.length) {
    return;
  }
  const sourceLabel = String(options.sourceLabel || "Dashboard").trim() || "Dashboard";
  state.analysisSelectedSavedCohortId = "";
  analysisUi.setContextMode("workspace");
  refs.analysisSelectedPatientIdsEl.value = ids.join(",");
  setAnalysisScopeMetadataFromSelection({
    sampleIds: Array.isArray(options.sampleIds) ? options.sampleIds : [],
    patientIds: ids,
    idType: Array.isArray(options.sampleIds) && options.sampleIds.length ? "sample" : "patient",
    sourceKind: String(options.sourceKind || sourceLabel.toLowerCase().replace(/[^a-z0-9]+/g, "_")).trim(),
    sourcePrompt: String(options.sourcePrompt || `${sourceLabel} selection (${ids.length} patients)`).trim(),
  });
  dashboardUi.renderAnalysisScopeSummary();
  navigationUi.setActiveTab("analysis");
  analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  refs.analysisStatusEl.className = "query-status";
  refs.analysisStatusEl.textContent = `Loaded ${ids.length} patient ID${ids.length === 1 ? "" : "s"} from ${sourceLabel} into Analysis. Run the analysis prompt to interpret this workspace.`;
}


function sendPromptToAnalysis(prompt, options) {
  const settings = options || {};
  const normalizedPrompt = String(prompt || "").trim();
  if (!normalizedPrompt) {
    return;
  }
  refs.analysisPromptEl.value = normalizedPrompt;
  analysisUi.setContextMode("workspace");
  state.analysisExecutionMode = settings.llmOnly ? "llm_only" : "auto";
  state.analysisSelectedCatalogItemId = "";
  analysisCatalogUi.renderAnalysisCatalogAssayPanel();
  navigationUi.setActiveTab("analysis");
  dashboardUi.renderAnalysisScopeSummary();
  analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  refs.analysisStatusEl.className = "query-status";
  refs.analysisStatusEl.textContent = settings.statusMessage
    ? String(settings.statusMessage)
    : (state.latestQueryResultHandle
      ? `Analysis prompt prepared for the ${state.latestQueryTotalCount}-${state.latestQueryIdType === "sample" ? "sample" : "patient"} Query result currently in scope.`
      : state.latestQueryPatientIds.length
      ? `Analysis prompt prepared for the ${state.latestQueryPatientIds.length}-ID workspace currently loaded from Query.`
      : "Analysis prompt prepared. Select a scope or use the full workspace.");
  refs.analysisPromptEl.focus();
}

function shouldAutoOpenJobsAfterSubmission() {
  return !state.userSettings || state.userSettings.analysis_auto_open_jobs !== false;
}

function setAnalysisSidebarCollapsed(collapsed, options = {}) {
  if (!refs.analysisSidebarEl) return;
  const isCollapsed = Boolean(collapsed);
  refs.analysisSidebarEl.classList.toggle("analysis-sidebar-collapsed", isCollapsed);
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
  setAnalysisSidebarCollapsed(false, { persist: false });
  const wide = window.matchMedia("(min-width: 901px)");
  const dock = document.getElementById("analysisChatDock");
  const panel = refs.analysisChatsDrawerEl.querySelector(".analysis-chats-drawer-panel");
  const update = () => {
    (wide.matches ? dock : refs.analysisChatsDrawerEl).appendChild(panel);
    dock.hidden = !wide.matches;
    panel.setAttribute("role", wide.matches ? "complementary" : "dialog");
    if (wide.matches) panel.removeAttribute("aria-modal");
    else panel.setAttribute("aria-modal", "true");
    const closeChatsLabel = wide.matches ? "Hide chats" : "Close chats";
    refs.analysisChatsDrawerCloseBtnEl.setAttribute("aria-label", closeChatsLabel);
    refs.analysisChatsDrawerCloseBtnEl.title = closeChatsLabel;
    refs.analysisChatsDrawerEl.classList.add("is-hidden");
    refs.analysisChatsDrawerEl.setAttribute("aria-hidden", "true");
    refs.analysisChatsDrawerBtnEl.setAttribute("aria-expanded", String(wide.matches));
  };
  wide.addEventListener("change", update);
  update();
}

function setAnalysisChatsDrawerOpen(open) {
  if (!refs.analysisChatsDrawerEl) return;
  const dock = document.getElementById("analysisChatDock");
  if (dock?.querySelector(".analysis-chats-drawer-panel")) {
    dock.hidden = !open;
    refs.analysisChatsDrawerBtnEl.setAttribute("aria-expanded", String(open));
    return;
  }
  refs.analysisChatsDrawerEl.classList.toggle("is-hidden", !open);
  refs.analysisChatsDrawerEl.setAttribute("aria-hidden", open ? "false" : "true");
  refs.analysisChatsDrawerBtnEl.setAttribute("aria-expanded", String(open));
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
    loadCohortLibrary: () => savedCohortsUi?.loadLibrary(),
    renderChatList: () => analysisSessionsUi?.renderAnalysisSessionList(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    closeJobSurfaces: () => {
      if (jobsUi) {
        jobsUi.closeJobSurfaces();
      }
    },
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
    sendPatientIdsToAnalysis: (patientIds, options) => sendPatientIdsToAnalysisFromSource(patientIds, options),
    saveIdsAsCohort: (options) => savedCohortsUi.saveIdsAsCohort(options),
    sendPromptToAnalysis,
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
    renderAnalysisCatalogAssayPanel: () => analysisCatalogUi.renderAnalysisCatalogAssayPanel(),
    setDashboardSubtab: (subtabName) => navigationUi.setDashboardSubtab(subtabName),
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

modelsAdminUi = createModelsAdminUi({
  refs,
  callbacks: {
    onProvidersChanged: async () => {
      await workspaceUi.loadLmStatus();
      userSettingsUi.renderUserSettingsForm();
    },
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
    renderAssayDatasetSelector: () => dashboardUi.renderAssayDatasetSelector(),
    renderAnalysisCompareMode: () => analysisUi.renderAnalysisCompareMode(),
    syncCurrentAnalysisSessionFromUi: (options) => analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options),
    currentDatasetSelectionKey: () => datasetsUi.currentDatasetSelectionKey(),
    isWorkspaceAccessible: () => authUi.isWorkspaceAccessible(),
    assayDatasetOverlap: (datasetName) => dashboardUi.assayDatasetOverlap(datasetName),
    setAnalysisContextMode: (value) => analysisUi.setContextMode(value),
    refreshBackgroundWorkerStatus: async () => {
      if (!jobsUi) return;
      await jobsUi.loadBackgroundWorkerStatus();
      analysisCatalogUi.renderAnalysisCatalog();
    },
  },
});

savedCohortsUi = createSavedCohortsUi({
  refs,
  helpers: {
    escapeHtml,
  },
  callbacks: {
    restoreWorkspace: restoreChatWorkspace,
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
    setAnalysisScopeMetadataFromSelection,
    clearAnalysisScopeMetadata,
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
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
    saveQueryChat: () => querySessionsUi?.save(),
    detachQueryChat: () => querySessionsUi?.detach(),
    queryContinuationIssue: () => querySessionsUi?.continuationIssue(),
    renderQueryExecutionMode: () => analysisCatalogUi.renderQueryExecutionMode(),
    startQueryProgressUpdates,
    stopQueryProgressUpdates,
    nextFrame: () => workspaceUi.nextFrame(),
    saveLatestQueryAsCohort: () => savedCohortsUi.saveLatestQueryAsCohort(),
    sendPatientIdsToPhenoRanker,
    sendPatientIdsToAnalysis,
    sendPromptToAnalysis,
    currentPatientsProvider: () => state.currentPatients,
    claridIdentityMarkup: (patient) => dashboardUi.claridIdentityMarkup(patient, true),
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
    prepareScriptForRun: () => analysisCatalogUi.prepareScriptForRun(),
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
          ? `Background run ${label} submitted. Queue opened.`
          : `Background run ${label} submitted. Open Queue to monitor progress.`;
      }
    },
    renderAnalysisFlowBar: () => analysisCatalogUi.renderAnalysisFlowBar(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    renderAnalysisScopeSummary: () => dashboardUi.renderAnalysisScopeSummary(),
    renderAnalysisCompareScopeSummary: () => dashboardUi.renderAnalysisCompareScopeSummary(),
    currentDatasetSelectionKey: () => datasetsUi.currentDatasetSelectionKey(),
    assayDatasetOverlap: (datasetName) => dashboardUi.assayDatasetOverlap(datasetName),
    renderAnalysisCatalogAssayPanel: () => analysisCatalogUi.renderAnalysisCatalogAssayPanel(),
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
    restoreWorkspace: restoreChatWorkspace,
    queryChatEntries: () => [...(querySessionsUi?.entries() || []), ...(phenoSessionsUi?.entries() || [])],
    renderPhenoChatCard: item => phenoSessionsUi.renderCard(item),
    chatOrganizationActions: (kind, id) => chatFoldersUi?.actions(kind, id) || '',
    organizeChats: (items, row, search) => {
      const renderRow = (item, dates) => chatDeletionUi ? chatDeletionUi.row(item, row(item, dates)) : row(item, dates);
      return (chatDeletionUi?.toolbar() || '') + (chatFoldersUi ? chatFoldersUi.organize(items, renderRow, search) : items.map(item => renderRow(item)).join(''));
    },
    renderQueryChatCard: (item) => querySessionsUi.renderCard(item),
    createAnalysisSession: makeAnalysisSession,
    currentAnalysisSession,
    currentDatasetSelectionKey: () => datasetsUi.currentDatasetSelectionKey(),
    getStorageNamespace: () => currentStorageNamespace(state.authState),
    renderAnalysisCompareMode: () => analysisUi.renderAnalysisCompareMode(),
    renderAnalysisScopeSummary: () => dashboardUi.renderAnalysisScopeSummary(),
    renderAnalysisCompareScopeSummary: () => dashboardUi.renderAnalysisCompareScopeSummary(),
    renderAnalysisStarterPrompts: () => analysisCatalogUi.renderAnalysisStarterPrompts(),
    renderAnalysisThread: () => analysisUi.renderAnalysisThread(),
    renderAnalysisMeta: (payload) => analysisUi.renderAnalysisMeta(payload),
    renderAnalysisFlowBar: () => analysisCatalogUi.renderAnalysisFlowBar(),
    renderAnalysisContextMode: () => analysisUi.renderAnalysisContextMode(),
  },
  state,
  constants: {
    ANALYSIS_SESSIONS_STORAGE_KEY,
  },
});

querySessionsUi = createQuerySessionsUi({ state, refs, query: queryUi, escapeHtml,
  restoreWorkspace: restoreChatWorkspace,
  organizationActions: (kind, id) => chatFoldersUi?.actions(kind, id) || '',
  openQuery: () => navigationUi.setActiveTab('query'),
  closeDrawer: () => {
    if (!document.getElementById('analysisChatDock').contains(refs.analysisSessionListEl)) setAnalysisChatsDrawerOpen(false);
  },
  renderList: () => analysisSessionsUi.renderAnalysisSessionList(),
});

chatFoldersUi = createChatFoldersUi({ escapeHtml, renderList: () => analysisSessionsUi.renderAnalysisSessionList() });
chatDeletionUi = createChatDeletionUi({ state, escapeHtml,
  render: () => analysisSessionsUi.renderAnalysisSessionList(),
  entries: () => [...state.analysisSessions, ...querySessionsUi.entries(), ...(phenoSessionsUi?.entries() || [])],
  pins: () => chatFoldersUi.pins(),
  prepare: async () => {
    if (phenoUi.chatBusy()) throw new Error('Wait for Pheno-Ranker to finish before deleting chats.');
    if (!await phenoSessionsUi.save()) throw new Error('Save or resolve the Pheno-Ranker chat first.');
    if (!await querySessionsUi.save()) throw new Error('Save or resolve the current Query chat before deleting.');
    await analysisSessionsUi.flushCurrentForProject();
  },
  forget: item => {
    if (item.chatKind === 'query') querySessionsUi.forgetDeletedChats([item.id]);
    else if (item.chatKind === 'pheno') phenoSessionsUi.forgetDeletedChats([item.id]);
    else analysisSessionsUi.forgetDeletedChats([item.id]);
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
    phenoChatIssue: () => phenoSessionsUi?.issue() || '',
    beforePhenoChatRun: () => phenoSessionsUi?.beforeRun() ?? true,
    onPhenoChatResult: payload => phenoSessionsUi?.record('result', payload),
    onPhenoChatQueued: payload => phenoSessionsUi?.record('queued', payload),
    onPhenoChatRunError: payload => phenoSessionsUi?.record('error', payload),
    onPhenoChatExplanation: payload => { void phenoSessionsUi?.record('explanation', payload); },
    onPhenoExplanationStatus: update => phenoSessionsUi?.explanationStatus(update),
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
          ? `Background Pheno-Ranker run ${label} submitted. Queue opened.`
          : `Background Pheno-Ranker run ${label} submitted. Open Queue to monitor progress.`;
      }
    },
    handlePhenoJobCompletion: () => {
      void jobsUi.loadRunHistory({ silent: true });
    },
    saveIdsAsCohort: (options) => savedCohortsUi.saveIdsAsCohort(options),
    setAnalysisScopeMetadataFromSelection,
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

phenoSessionsUi = createPhenoSessionsUi({state, refs, pheno:phenoUi, escapeHtml,
  restoreWorkspace: restoreChatWorkspace,
  renderList:() => analysisSessionsUi.renderAnalysisSessionList(),
  openTab:(savedChat = false) => {
    navigationUi.setActiveTab('pheno', {savedChat});
    if (!document.getElementById('analysisChatDock').contains(refs.analysisSessionListEl)) setAnalysisChatsDrawerOpen(false);
  },
  actions:(kind,id) => chatFoldersUi?.actions(kind,id) || '',
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
    onBackgroundWorkerStatusChanged: () => analysisCatalogUi.renderAnalysisCatalog(),
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
    currentDatasetSelectionKey: (datasetIds) => datasetsUi.currentDatasetSelectionKey(datasetIds),
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
    loadAssayDatasets: (options) => dashboardUi.loadAssayDatasets(options),
    loadPhenoRankerPatientIds: () => phenoUi.loadPhenoRankerPatientIds(),
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
    renderPatientList: (items) => dashboardUi.renderPatientList(items),
    renderDetail: (patient) => dashboardUi.renderDetail(patient),
    renderDashboard: (summary) => dashboardUi.renderDashboard(summary),
    isWorkspaceAccessible: () => authUi.isWorkspaceAccessible(),
    updateLoadButtonAvailability: () => authUi.updateLoadButtonAvailability(),
    applyUserSettings: (options) => userSettingsUi.applyUserSettings(options),
    clearDatasetScopedContent,
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
    loadAssayDatasets: () => dashboardUi.loadAssayDatasets(),
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
    syncDeploymentBranding: (auth) => deploymentBrandingUi.syncAuth(auth),
    renderLoadButtonState: () => datasetsUi.renderLoadButtonState(),
    renderJobsDrawer: () => jobsUi.renderJobsDrawer(),
    renderRunHistoryDrawer: () => jobsUi.renderRunHistoryDrawer(),
    renderGlobalContext: () => workspaceUi.renderGlobalContext(),
    currentTabName: () => navigationUi.currentTabName(),
    setActiveTab: (tabName) => navigationUi.setActiveTab(tabName),
    loadAuthUsers: () => usersAdminUi.loadAuthUsers(),
    loadRecentJobs: (options) => jobsUi.loadRecentJobs(options),
    loadRunHistory: (options) => jobsUi.loadRunHistory(options),
    loadSavedCohorts: () => savedCohortsUi.loadSavedCohorts(),
    loadAnalysisCatalog: () => analysisCatalogUi.loadAnalysisCatalog(),
    renderAnalysisSessionList: () => analysisSessionsUi.renderAnalysisSessionList(),
    renderAnalysisThread: () => analysisUi.renderAnalysisThread(),
    renderAnalysisCatalog: () => analysisCatalogUi.renderAnalysisCatalog(),
    createAnalysisSession: makeAnalysisSession,
    ensureAnalysisSessionsLoaded: () => analysisSessionsUi.ensureAnalysisSessionsLoaded(),
    loadAnalysisSessionsFromBackend: async () => {
      await chatFoldersUi.load();
      await querySessionsUi.load();
      await phenoSessionsUi.load();
      return analysisSessionsUi.loadAnalysisSessionsFromBackend();
    },
    applyAnalysisSession: (session) => analysisSessionsUi.applyAnalysisSession(session),
    loadDatasets: () => datasetsUi.loadDatasets(),
    loadPatients: (options) => workspaceUi.loadPatients(options),
    loadUserSettings: (options) => userSettingsUi.loadUserSettings(options),
    applyUserSettings: (options) => userSettingsUi.applyUserSettings(options),
    loadLmStatus: () => workspaceUi.loadLmStatus(),
    clearDatasetScopedContent,
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
    refreshLmStatus: () => workspaceUi.loadLmStatus(),
    refreshUserDataAfterDelete: async (kind) => {
      if (kind === "chats") {
        analysisSessionsUi.resetAnalysisSessionsAfterBulkDelete();
        analysisUi.renderAnalysisThread();
        analysisCatalogUi.renderAnalysisCatalog();
      } else if (kind === "jobs") {
        await jobsUi.loadRecentJobs({ silent: true });
        await jobsUi.loadRunHistory({ silent: true });
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
    const removeButton = event.target.closest("[data-dataset-remove]");
    if (removeButton && refs.datasetAdminListEl.contains(removeButton)) {
      event.preventDefault();
      datasetsUi.removeDataset(removeButton.dataset.datasetRemove);
      return;
    }
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
    const collapsed = Boolean(refs.analysisSidebarEl && refs.analysisSidebarEl.classList.contains("analysis-sidebar-collapsed"));
    setAnalysisSidebarCollapsed(!collapsed);
  });
  refs.analysisChatsDrawerBtnEl && refs.analysisChatsDrawerBtnEl.addEventListener("click", () => {
    setAnalysisChatsDrawerOpen(true);
  });
  refs.analysisChatsDrawerCloseBtnEl && refs.analysisChatsDrawerCloseBtnEl.addEventListener("click", () => {
    setAnalysisChatsDrawerOpen(false);
  });
  refs.analysisChatsDrawerEl && refs.analysisChatsDrawerEl.addEventListener("click", (event) => {
    const closeTrigger = event.target.closest("[data-analysis-chats-close='true']");
    if (closeTrigger && refs.analysisChatsDrawerEl.contains(closeTrigger)) {
      setAnalysisChatsDrawerOpen(false);
    }
  });

  refs.authLoginBtnEl && refs.authLoginBtnEl.addEventListener("click", () => {
    void authUi.loginLocal();
  });
  refs.authOidcLoginBtnEl && refs.authOidcLoginBtnEl.addEventListener("click", () => {
    authUi.loginOidc();
  });
  refs.authForgotPasswordBtnEl && refs.authForgotPasswordBtnEl.addEventListener("click", () => {
    authUi.setPasswordResetPanelOpen(true, "request");
  });
  refs.authPasswordResetRequestBtnEl && refs.authPasswordResetRequestBtnEl.addEventListener("click", () => {
    void authUi.requestPasswordReset();
  });
  refs.authPasswordResetCancelBtnEl && refs.authPasswordResetCancelBtnEl.addEventListener("click", () => {
    authUi.setPasswordResetPanelOpen(false);
  });
  refs.authPasswordResetConfirmBtnEl && refs.authPasswordResetConfirmBtnEl.addEventListener("click", () => {
    void authUi.confirmPasswordReset();
  });
  refs.authPasswordResetConfirmCancelBtnEl && refs.authPasswordResetConfirmCancelBtnEl.addEventListener("click", () => {
    authUi.clearPasswordResetTokenFromLocation();
    authUi.setPasswordResetPanelOpen(false);
  });
  refs.heroLogoutBtnEl && refs.heroLogoutBtnEl.addEventListener("click", () => {
    void authUi.logoutLocal();
  });
  refs.userSettingsBtnEl && refs.userSettingsBtnEl.addEventListener("click", () => {
    userSettingsUi.renderUserSettingsForm();
    userSettingsUi.setPanelOpen(true);
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
    chatDeletionUi.open();
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
  refs.authPasswordResetIdentifierEl && refs.authPasswordResetIdentifierEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void authUi.requestPasswordReset();
    }
  });
  refs.authPasswordResetConfirmPasswordEl && refs.authPasswordResetConfirmPasswordEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void authUi.confirmPasswordReset();
    }
  });

  refs.askBtnEl && refs.askBtnEl.addEventListener("click", () => {
    void queryUi.askQuery();
  });
  refs.queryContextWorkspaceBtnEl && refs.queryContextWorkspaceBtnEl.addEventListener("click", () => {
    queryUi.setContextMode("workspace");
  });
  refs.queryContextGeneralBtnEl && refs.queryContextGeneralBtnEl.addEventListener("click", () => {
    queryUi.setContextMode("general");
  });
  refs.queryComposerExamplesBtnEl && refs.queryComposerExamplesBtnEl.addEventListener("click", () => {
    queryUi.togglePromptLibrary();
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
    void querySessionsUi.newChat();
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
    } else if (target === "analysis" || target === "choose" || target === "setup" || target === "catalog") {
      document.getElementById("analysisMethodSelect").focus();
      document.getElementById("analysisMethodPicker").scrollIntoView({ block: "center" });
    } else if (target === "prompt") {
      document.getElementById("analysisRequestDetails").open = true;
      refs.analysisPromptEl && refs.analysisPromptEl.focus();
      refs.analysisPromptEl && refs.analysisPromptEl.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (target === "requirements") {
      if (document.getElementById("analysisMethodSelect").value === "association") {
        const panel = document.getElementById("analysisMeasurementComparison");
        panel.open = true;
        panel.scrollIntoView({ block: "center" });
        document.getElementById("associationAssayX").focus();
      } else if (state.analysisSelectedCatalogItemId) {
        analysisCatalogUi.focusFirstIncompleteAnalysisSetup();
        refs.analysisCatalogAssayPanelEl.scrollIntoView({ block: "center" });
      } else {
        document.getElementById("analysisMethodDescription").scrollIntoView({ block: "center" });
      }
    } else if (target === "run") {
      refs.analysisPromptEl && refs.analysisPromptEl.focus();
      refs.analysisPromptEl && refs.analysisPromptEl.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (target === "results") {
      refs.analysisThreadEl && refs.analysisThreadEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  document.getElementById("analysisMeasurementComparison").addEventListener("change", () => analysisCatalogUi.renderAnalysisFlowBar());
  refs.analysisComposerExamplesBtnEl && refs.analysisComposerExamplesBtnEl.addEventListener("click", () => {
    state.analysisExamplesPinnedOpen = true;
    analysisCatalogUi.renderAnalysisStarterPrompts();
    if (refs.analysisStarterPanelEl && !refs.analysisStarterPanelEl.hidden) {
      refs.analysisStarterPanelEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  refs.analysisNewSessionBtnEl && refs.analysisNewSessionBtnEl.addEventListener("click", () => {
    const choices = document.getElementById('newChatChoices');
    choices.hidden = !choices.hidden;
    refs.analysisNewSessionBtnEl.setAttribute('aria-expanded', String(!choices.hidden));
    if (!choices.hidden) document.getElementById('newQueryChatBtn').focus();
  });
  const closeNewChatChoices = () => {
    document.getElementById('newChatChoices').hidden = true;
    refs.analysisNewSessionBtnEl.setAttribute('aria-expanded', 'false');
  };
  document.getElementById('newQueryChatBtn').addEventListener('click', () => {
    closeNewChatChoices();
    void querySessionsUi.newChat();
  });
  document.getElementById('newPhenoChatBtn').addEventListener('click', () => {
    closeNewChatChoices();
    void phenoSessionsUi.newChat();
  });
  document.getElementById('newAnalysisChatBtn').addEventListener('click', () => {
    closeNewChatChoices();
    document.getElementById("analysisChatSearch").value = "";
    analysisSessionsUi.createAndSelectAnalysisSession({ dataDir: refs.dataDirEl.value.trim() });
    navigationUi.setActiveTab("analysis");
    if (!document.getElementById("analysisChatDock").contains(refs.analysisSessionListEl)) setAnalysisChatsDrawerOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !document.getElementById('newChatChoices').hidden) {
      closeNewChatChoices(); refs.analysisNewSessionBtnEl.focus();
    }
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('#newChatChoices, #analysisNewSessionBtn')) closeNewChatChoices();
  });

  refs.dashboardTabBtnEl && refs.dashboardTabBtnEl.addEventListener("click", () => {
    navigationUi.setActiveTab("dashboard");
  });
  refs.datasetsTabBtnEl && refs.datasetsTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("datasets"));
  refs.cohortsTabBtnEl?.addEventListener('click', () => navigationUi.setActiveTab('cohorts'));
  refs.adminTabBtnEl && refs.adminTabBtnEl.addEventListener("click", () => {
    if (refs.adminTabBtnEl.classList.contains("active")) {
      refs.adminTabBtnEl.setAttribute("aria-expanded", String(refs.adminTabBtnEl.getAttribute("aria-expanded") !== "true"));
    } else {
      navigationUi.setActiveTab("admin");
      if (navigationUi.currentTabName() === "models") void modelsAdminUi.loadModels();
    }
  });
  refs.usersTabBtnEl && refs.usersTabBtnEl.addEventListener("click", () => {
    navigationUi.setActiveTab("users");
    void usersAdminUi.loadAuthUsers();
  });
  refs.dataTabBtnEl?.addEventListener("click", () => navigationUi.setActiveTab("data"));
  refs.modelsTabBtnEl && refs.modelsTabBtnEl.addEventListener("click", () => {
    navigationUi.setActiveTab("models");
    void modelsAdminUi.loadModels();
  });
  refs.modelCreateBtnEl && refs.modelCreateBtnEl.addEventListener("click", () => {
    void modelsAdminUi.createModel();
  });
  refs.modelsListEl && refs.modelsListEl.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-lm-provider-action]");
    if (!trigger) return;
    const id = String(trigger.dataset.lmProvider || "");
    const action = String(trigger.dataset.lmProviderAction || "");
    if (!id) return;
    if (action === "save") void modelsAdminUi.saveModel(id);
    else if (action === "test") void modelsAdminUi.testModel(id);
    else if (action === "delete") void modelsAdminUi.deleteModel(id);
  });
  refs.queryTabBtnEl && refs.queryTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("query"));
  refs.analysisTabBtnEl && refs.analysisTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("analysis"));
  refs.phenoTabBtnEl && refs.phenoTabBtnEl.addEventListener("click", () => navigationUi.setActiveTab("pheno"));
  refs.dashboardClinicalBtnEl && refs.dashboardClinicalBtnEl.addEventListener("click", () => navigationUi.setDashboardSubtab("clinical"));
  refs.dashboardTimelineBtnEl?.addEventListener('click', () => {
    state.timelinePatientFilter = ''; state.timelinePatientSearch = ''; state.timelineDatasetFilter = ''; state.timelinePage = 0;
    navigationUi.setDashboardSubtab('timeline');
    dashboardUi.renderDashboard(state.dashboardSummaryState || state.dashboardSummary || {});
  });
  refs.dashboardAssaysBtnEl && refs.dashboardAssaysBtnEl.addEventListener("click", () => navigationUi.setDashboardSubtab("assays"));
  refs.dashboardImagingBtnEl && refs.dashboardImagingBtnEl.addEventListener("click", () => navigationUi.setDashboardSubtab("imaging"));
  refs.dashboardMultimodalBtnEl && refs.dashboardMultimodalBtnEl.addEventListener("click", () => navigationUi.setDashboardSubtab("multimodal"));

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
    phenoUi.updatePhenoMode();
    phenoUi.markPhenoManualOverride();
    phenoUi.updatePhenoRunAvailability();
  });
  refs.phenoActionEl && refs.phenoActionEl.addEventListener("change", () => {
    phenoUi.markPhenoManualOverride();
    phenoUi.updatePhenoMode();
    phenoUi.updatePhenoRunAvailability();
  });
  refs.phenoSelectedPatientIdsEl && refs.phenoSelectedPatientIdsEl.addEventListener("input", () => {
    phenoUi.markPhenoManualOverride();
    phenoUi.renderSelectedPatientIdsSummary();
    phenoUi.updatePhenoRunAvailability();
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
    const ids = refs.analysisSelectedPatientIdsEl.value.split(",").map((item) => item.trim()).filter(Boolean);
    const hasSampleIds = ids.some((item) => item.includes(":"));
    setAnalysisScopeMetadataFromSelection({
      sampleIds: hasSampleIds ? ids : [],
      patientIds: hasSampleIds ? [] : ids,
      idType: hasSampleIds ? "sample" : "patient",
      sourceKind: "manual",
      sourcePrompt: "Manual Analysis scope",
    });
    dashboardUi.renderAnalysisScopeSummary();
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisCompareModeEl && refs.analysisCompareModeEl.addEventListener("change", () => {
    analysisUi.renderAnalysisCompareMode();
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisCompareSelectedPatientIdsEl && refs.analysisCompareSelectedPatientIdsEl.addEventListener("input", () => {
    const ids = refs.analysisCompareSelectedPatientIdsEl.value.split(",").map((item) => item.trim()).filter(Boolean);
    const hasSampleIds = ids.some((item) => item.includes(":"));
    setAnalysisScopeMetadataFromSelection({
      side: "b",
      sampleIds: hasSampleIds ? ids : [],
      patientIds: hasSampleIds ? [] : ids,
      idType: hasSampleIds ? "sample" : "patient",
      sourceKind: "manual",
      sourcePrompt: "Manual Analysis Cohort B scope",
    });
    dashboardUi.renderAnalysisCompareScopeSummary();
    analysisCatalogUi.renderAnalysisCatalog();
  });
  refs.analysisPromptEl && refs.analysisPromptEl.addEventListener("input", () => {
    // Editing an example or follow-up must preserve its selected execution mode.
    // Method selection and completed runs handle mode resets explicitly.
    analysisCatalogUi.renderAnalysisCatalogAssayPanel();
    analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
  });
  refs.analysisContextWorkspaceBtnEl && refs.analysisContextWorkspaceBtnEl.addEventListener("click", () => {
    analysisUi.setContextMode("workspace");
  });
  document.getElementById("multimodalCompareShortcut").addEventListener("click", () => {
    navigationUi.setActiveTab("analysis");
    analysisUi.setContextMode("workspace");
    const method = document.getElementById("analysisMethodSelect");
    if (method.value !== "association") {
      method.value = "association";
      method.dispatchEvent(new Event("change"));
    }
    const panel = document.getElementById("analysisMeasurementComparison");
    panel.open = true;
    panel.scrollIntoView({ block: "center" });
    document.getElementById("associationAssayX").focus();
  });
  refs.analysisContextGeneralBtnEl && refs.analysisContextGeneralBtnEl.addEventListener("click", () => {
    analysisUi.setContextMode("general");
  });

  const handleAssayDatasetListChange = (event) => {
    const checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox) {
      return;
    }
    dashboardUi.handleAssayDatasetSelectionChange(event.currentTarget, checkbox);
    analysisCatalogUi.renderAnalysisCatalogAssayPanel();
    analysisCatalogUi.renderAnalysisCatalog();
  };
  refs.analysisAssayDatasetListEl && refs.analysisAssayDatasetListEl.addEventListener("change", handleAssayDatasetListChange);
  refs.analysisCatalogAssayDatasetListEl && refs.analysisCatalogAssayDatasetListEl.addEventListener("change", handleAssayDatasetListChange);
  refs.analysisCatalogAssayPanelEl && refs.analysisCatalogAssayPanelEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-analysis-setup-action]");
    if (!button || !refs.analysisCatalogAssayPanelEl.contains(button)) return;
    void analysisCatalogUi.handleAnalysisSetupAction(button.dataset.analysisSetupAction || "");
  });
  refs.assayModalityTabsEl && refs.assayModalityTabsEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-assay-modality-filter]");
    if (!button || !refs.assayModalityTabsEl.contains(button)) {
      return;
    }
    dashboardUi.handleAssayModalityFilter(button.dataset.assayModalityFilter || "all");
  });
  refs.analysisAssayGeneEl && refs.analysisAssayGeneEl.addEventListener("input", () => {
    dashboardUi.handleAssayFeatureInput();
  });
  refs.analysisAssayRunBtnEl && refs.analysisAssayRunBtnEl.addEventListener("click", () => {
    void dashboardUi.runAssayExpressionAnalysis();
  });

  refs.patientsEl && refs.patientsEl.addEventListener("click", (event) => {
    if (event.target.closest("[data-clarid-toggle], [data-clarid-copy]")) {
      void dashboardUi.handleClaridAction(event);
      return;
    }
    const card = event.target.closest(".patient-card");
    if (!card || !refs.patientsEl.contains(card)) {
      return;
    }
    void workspaceUi.loadPatient(card.dataset.patientId);
  });
  refs.queryThreadEl && refs.queryThreadEl.addEventListener("click", (event) => {
    if (event.target.closest("[data-clarid-toggle], [data-clarid-copy]")) {
      void dashboardUi.handleClaridAction(event);
    }
  });
  refs.detailEl && refs.detailEl.addEventListener("click", (event) => {
    if (event.target.closest("[data-clarid-toggle], [data-clarid-copy]")) {
      void dashboardUi.handleClaridAction(event);
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".clarid-identity")) dashboardUi.closeClaridPopovers();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") dashboardUi.closeClaridPopovers();
  });
  window.addEventListener('resize', () => dashboardUi.closeClaridPopovers());
  document.addEventListener('scroll', event => {
    if (!event.target.closest?.('.clarid-popover')) dashboardUi.closeClaridPopovers();
  }, true);
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
    analysisUi.setContextMode("workspace");
    state.analysisExecutionMode = button.dataset.analysisLlmOnly === "true"
      ? "llm_only"
      : (button.dataset.analysisDeterministic === "true" ? "deterministic" : "planner_only");
    state.analysisSelectedCatalogItemId = "";
    analysisCatalogUi.renderAnalysisCatalogAssayPanel();
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
    const deleteButton = event.target.closest("[data-job-delete]");
    if (deleteButton && refs.jobsDrawerEl.contains(deleteButton)) {
      void jobsUi.deleteJob(deleteButton.dataset.jobDelete || "").catch((error) => {
        refs.jobsDrawerStatusEl.textContent = error && error.message ? error.message : "Unable to delete job.";
      });
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

  refs.runHistoryDrawerBtnEl && refs.runHistoryDrawerBtnEl.addEventListener("click", () => {
    jobsUi.setRunHistoryDrawerOpen(true);
    void jobsUi.loadRunHistory();
  });
  refs.runHistoryDrawerCloseBtnEl && refs.runHistoryDrawerCloseBtnEl.addEventListener("click", () => {
    jobsUi.setRunHistoryDrawerOpen(false);
  });
  refs.runHistoryDeleteAllBtnEl && refs.runHistoryDeleteAllBtnEl.addEventListener("click", () => {
    void jobsUi.deleteRunHistory();
  });
  refs.runHistoryDrawerEl && refs.runHistoryDrawerEl.addEventListener("click", (event) => {
    const closeTrigger = event.target.closest("[data-run-history-drawer-close='true']");
    if (closeTrigger && refs.runHistoryDrawerEl.contains(closeTrigger)) {
      jobsUi.setRunHistoryDrawerOpen(false);
      return;
    }
    const deleteButton = event.target.closest("[data-run-history-delete]");
    if (deleteButton && refs.runHistoryDrawerEl.contains(deleteButton)) {
      void jobsUi.deleteJob(deleteButton.dataset.runHistoryDelete || "", { surface: "run-history" }).catch((error) => {
        refs.runHistoryDrawerStatusEl.textContent = error && error.message ? error.message : "Unable to delete generated run.";
      });
      return;
    }
    const openButton = event.target.closest("[data-job-open-result], [data-job-open-pheno]");
    if (!openButton || !refs.runHistoryDrawerEl.contains(openButton)) {
      return;
    }
    void jobsUi.openJobResult(openButton.dataset.jobOpenResult || openButton.dataset.jobOpenPheno || "").catch((error) => {
      const isPheno = Boolean(openButton.dataset.jobOpenPheno);
      const statusEl = isPheno ? refs.phenoStatusEl : refs.analysisStatusEl;
      statusEl.className = "query-status";
      statusEl.textContent = error && error.message ? error.message : "Unable to load generated run.";
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
    navigationUi.setActiveTab("analysis");
    if (!document.getElementById("analysisChatDock").contains(refs.analysisSessionListEl)) setAnalysisChatsDrawerOpen(false);
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
  refs.phenoPlanFollowupsEl && refs.phenoPlanFollowupsEl.addEventListener("click", (event) => {
    phenoUi.handlePhenoPlanFollowUpsClick(event);
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
    if (savedDashboardSubtab && ["patients", "clinical", "assays", "imaging", "multimodal", "timeline"].includes(savedDashboardSubtab)) {
      navigationUi.setDashboardSubtab(savedDashboardSubtab);
    }
    if (savedTab && ["dashboard", "cohort", "assays", "datasets", "cohorts", "data", "users", "models", "query", "analysis", "pheno"].includes(savedTab)) {
      if (savedTab === "cohort") {
        navigationUi.setDashboardSubtab("clinical");
        navigationUi.setActiveTab("dashboard");
      } else if (savedTab === "assays") {
        navigationUi.setDashboardSubtab("assays");
        navigationUi.setActiveTab("dashboard");
      } else if (["data", "users", "models"].includes(savedTab) && state.authState.enabled && !authUi.canManageDataset()) {
        navigationUi.setActiveTab("datasets");
      } else {
        navigationUi.setActiveTab(savedTab);
        if (savedTab === "models") {
          void modelsAdminUi.loadModels();
        }
      }
    }
  } catch (_error) {
  }
}

function initializeUiShell() {
  analysisCatalogUi.initializeExampleToggle(refs.queryExamplesEl);
  analysisCatalogUi.initializeExampleToggle(refs.phenoExamplesEl);
  analysisCatalogUi.initializeExampleToggle(refs.analysisExamplesEl);
  queryUi.renderQueryStarterPrompts();
  analysisCatalogUi.renderAnalysisStarterPrompts();
  initializeAnalysisSidebarCollapsed();
  initializeNavigationShell();
  navigationUi.setDashboardSubtab(state.currentDashboardSubtab);
  applyStoredTabPreferences();
  phenoUi.updatePhenoExplainActions();
  phenoUi.updatePhenoResultActions();
  phenoUi.updatePhenoRunAvailability();
  phenoUi.updatePhenoRunAvailability();
  phenoUi.updatePhenoMode();
  phenoUi.renderSelectedPatientIdsSummary();
  analysisCatalogUi.renderQueryExecutionMode();
  queryUi.renderQueryContextMode();
  phenoUi.setPhenoResultWorkspaceVisible(false);
  savedCohortsUi.renderPhenoSavedCohortsSelection();
  analysisSessionsUi.ensureAnalysisSessionsLoaded();
  void analysisSessionsUi.loadAnalysisSessionsFromBackend();
  void querySessionsUi.load();
  void phenoSessionsUi.load();
  void chatFoldersUi.load();
  analysisUi.renderAnalysisCompareMode();
  analysisUi.renderAnalysisContextMode();
  dashboardUi.renderAnalysisCompareScopeSummary();
  workspaceUi.renderGlobalContext();
  phenoUi.renderPhenoAlignmentPlaceholder("Run patient mode, then click one row in rank.txt to inspect matched variables for that pair.");
  phenoUi.renderPhenoExplainPlaceholder("Run patient mode, then click Explain results to summarize the top matches from rank.txt.");
}

async function bootstrap() {
  bindEvents();
  createPatientOverview({state, navigation:navigationUi, escapeHtml,
    scope:() => datasetsUi.currentDatasetSelectionKey(),
    openTimeline:async (patientId, datasetId) => {
      state.timelinePatientFilter = JSON.stringify([datasetId, patientId]);
      state.timelineDatasetFilter = ''; state.timelinePatientSearch = ''; state.timelinePage = 0;
      navigationUi.setDashboardSubtab('timeline');
      dashboardUi.renderDashboard(state.dashboardSummaryState || state.dashboardSummary || {});
    }});
  initializeUiShell();
  window.__cohortomeLoadPatients = (options) => workspaceUi.loadPatients(options);
  window.__cohortomeAskQuery = () => queryUi.askQuery();
  await workspaceUi.loadLmStatus();
  await authUi.fetchAuthStatus();
  if (!authUi.isWorkspaceAccessible()) {
    authUi.clearLoadedWorkspaceForSignedOutState();
    return;
  }
  await userSettingsUi.loadUserSettings({ applyNavigation: false });
  await workspaceUi.loadLmStatus();
  await datasetsUi.loadDatasets();
  await workspaceUi.loadPatients({ respectAdminGate: false, targetDatasetIds: state.currentDatasetIds.slice() });
  await authUi.refreshUserWorkspaceState();
  userSettingsUi.applyUserSettings({ applyNavigation: true });
  createProjectsUi({state, refs, sessions:analysisSessionsUi, query:queryUi,
    workspace:workspaceUi, datasets:datasetsUi, navigation:navigationUi});
}

void bootstrap();
