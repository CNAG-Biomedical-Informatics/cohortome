import {renderNotice} from '/static/js/react/ui.js';
import { escapeHtml, fallbackCopyText } from "/static/js/shared.js";
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
import { createClinicalSummaryUi } from '/static/js/clinical_summary.js';
import { createCohortScopeUi } from '/static/js/cohort_scope.js';

import {mountPageShell,mountConversationComposers,mountNavigationShell,mountAdminCreationForms,mountApplicationPanels} from '/static/js/react/ui.js';

import { createConversationActions } from './js/actions/conversation.js';
import { createAnalysisActions } from './js/actions/analysis.js';
import { createWorkspaceActions } from './js/actions/workspace.js';
import { createAdministrationActions } from './js/actions/administration.js';
import { createNavigationActions } from './js/actions/navigation.js';

// The shell mounts first so the controllers can resolve their DOM hosts.
const actionContext = {};
const shellActions = {
  ...createConversationActions(actionContext),
  ...createAnalysisActions(actionContext),
  ...createWorkspaceActions(actionContext),
  ...createAdministrationActions(actionContext),
  ...createNavigationActions(actionContext),
};
mountPageShell({
  shellActions,
  onChatSearch() { analysisSessionsUi.renderAnalysisSessionList(); },
  onNewChat(kind) {
    if (kind === 'query') { void querySessionsUi.newChat(); return; }
    if (kind === 'pheno') { void phenoSessionsUi.newChat(); return; }
    document.getElementById('analysisChatSearch').value = '';
    analysisSessionsUi.createAndSelectAnalysisSession({ dataDir: refs.dataDirEl.value.trim() });
    navigationUi.setActiveTab('analysis');
    if (!document.getElementById('analysisChatDock').contains(refs.analysisSessionListEl)) setAnalysisChatsDrawerOpen(false);
  },
});
mountApplicationPanels(shellActions);
mountConversationComposers({
  shellActions,
  analysisActions: {
    run: () => analysisUi.runAnalysis(),
    editSetup: () => analysisUi.editSetup(),
    edited() {
      analysisCatalogUi.renderAnalysisCatalogAssayPanel();
      analysisSessionsUi.syncCurrentAnalysisSessionFromUi({ render: true });
    },
  },
  phenoActions: {
    edited: () => phenoUi.handlePhenoPromptEdited(),
    run: () => phenoUi.runPhenoRanker(),
    planRun: () => phenoUi.planAndRunPhenoRanker(),
  },
  queryActions: {
    edited() { analysisCatalogUi.renderQueryExecutionMode(); querySessionsUi.draftEdited(); },
    ask() {
      void queryUi.askQuery();
    },
    workspace() {
      queryUi.setContextMode("workspace");
    },
    general() {
      queryUi.setContextMode("general");
    },
    prompts() {
      queryUi.togglePromptLibrary();
    },
    planner() {
      queryUi.setExecutionMode(state.queryExecutionMode === "planner_only" ? "auto" : "planner_only");
      analysisCatalogUi.renderQueryExecutionMode();
    },
    memory() {
      if (state.queryGranularityMode !== "detailed") {
        analysisCatalogUi.renderQueryExecutionMode();
        return;
      }
      state.queryFollowMemoryEnabled = !state.queryFollowMemoryEnabled;
      analysisCatalogUi.renderQueryExecutionMode();
    },
    disease() {
      const willOpen = !refs.queryDiseasePanelEl || refs.queryDiseasePanelEl.classList.contains("is-hidden");
      if (refs.queryDiseasePanelEl) refs.queryDiseasePanelEl.classList.toggle("is-hidden", !willOpen);
      refs.queryDiseaseBuilderBtnEl.classList.toggle("is-active", willOpen);
    },
    clear() {
      void querySessionsUi.newChat();
    },
  },
});
mountNavigationShell({
  actions: shellActions.Rail,
  onNavigate(tab) {
    if (tab === 'admin' && refs.adminTabBtnEl.classList.contains('active')) {
      refs.adminTabBtnEl.setAttribute('aria-expanded', String(refs.adminTabBtnEl.getAttribute('aria-expanded') !== 'true'));
      return;
    }
    navigationUi.setActiveTab(tab);
    if (tab === 'users') void usersAdminUi.loadAuthUsers();
    if (tab === 'models' || (tab === 'admin' && navigationUi.currentTabName() === 'models')) {
      void modelsAdminUi.loadModels();
    }
  },
  onDashboardNavigate(tab) {
    if (tab === 'timeline') {
      state.timelinePatientFilter = ''; state.timelinePatientSearch = '';
      state.timelineDatasetFilter = ''; state.timelinePage = 0;
    }
    navigationUi.setDashboardSubtab(tab);
    if (tab === 'timeline') dashboardUi.renderDashboardTimeline(state.dashboardSummaryState || state.dashboardSummary || {});
  },
});
mountAdminCreationForms(shellActions);
const refs = createAppRefs(document);
const state = createAppState();
const deploymentBrandingUi = createDeploymentBrandingUi();

const MAX_VISIBLE_PATIENTS = 80;
const MAX_VISIBLE_EXAMPLES = 8;
const ACTIVE_TAB_STORAGE_KEY = "cohortome.active-tab";
const DASHBOARD_SUBTAB_STORAGE_KEY = "cohortome.dashboard-subtab";
const ANALYSIS_SESSIONS_STORAGE_KEY = "cohortome.analysis-sessions";
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
let patientOverviewUi;
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

async function addCohortDatasets(requiredIds) {
  if (state.loadInFlight || state.queryInFlight || state.analysisInFlight) {
    throw new Error('Wait for the current operation to finish before changing workspace.');
  }
  if (!requiredIds?.length || requiredIds.some(id => !state.availableDatasets.some(item => item.dataset_id === id))) {
    throw new Error('A required dataset is unavailable or you no longer have access to it.');
  }
  const previousPending = state.pendingDatasetIds.slice();
  const ids = [...new Set([...state.currentDatasetIds, ...requiredIds])];
  const added = ids.length - state.currentDatasetIds.length;
  if (!added) return 0;
  state.pendingDatasetIds = ids;
  try {
    await workspaceUi.loadPatients();
    if (ids.length !== state.currentDatasetIds.length || !ids.every(id => state.currentDatasetIds.includes(id))) {
      throw new Error('Required datasets could not be added. Check their availability in Datasets.');
    }
  } catch (error) {
    state.pendingDatasetIds = previousPending;
    throw error;
  }
  return added;
}

function clearDatasetScopedContent(options = {}) {
  const signedOut = options.signedOut === true;
  if (signedOut) querySessionsUi?.clear();
  if (signedOut) savedCohortsUi?.clearLibrary();
  if (signedOut) phenoSessionsUi?.clear();
  if (signedOut) { chatDeletionUi?.clear(); chatFoldersUi?.clear(); }
  const clearSelection = options.clearSelection === true;
  const nextScopeId = String(options.nextScopeId || "").trim();
  // Capture the current setup before clearing workspace views. A same-workspace
  // reload must not replace a saved method with the empty loading controls.
  if (analysisSessionsUi) analysisSessionsUi.prepareAnalysisSessionForDataDir(nextScopeId);
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
  if (analysisSessionsUi) analysisSessionsUi.applyAnalysisSession(currentAnalysisSession());
  if (analysisCatalogUi) analysisCatalogUi.renderAnalysisCatalog();

  const patientMessage = signedOut ? "Sign in to access the shared clinical workspace." : (nextScopeId ? "Loading selected workspace..." : "No dataset selected.");
  const detailMessage = signedOut ? "Patient workspace hidden until you sign in." : (nextScopeId ? "Loading patient workspace..." : "Select a workspace to inspect the patient workspace.");
  const dashboardMessage = signedOut ? "Clinical dashboard hidden until you sign in." : (nextScopeId ? "Loading dashboard..." : "Select a workspace to inspect the dashboard.");
  const timelineMessage = signedOut ? "Timeline hidden until you sign in." : (nextScopeId ? "Loading timeline..." : "Select a workspace to inspect the timeline.");
  dashboardUi?.resetDashboardViews();
  renderNotice(refs.patientsEl,patientMessage);
  renderNotice(refs.detailEl,detailMessage);
  renderNotice(refs.dashboardEl,dashboardMessage);
  renderNotice(refs.dashboardTimelineEl,timelineMessage);
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

function sendPatientIdsToPhenoRanker() {
  const scopeIds = state.latestQueryRecordIds.length ? state.latestQueryRecordIds : state.latestQueryPatientIds;
  const idType = state.latestQueryRecordIds.length ? 'sample' : state.latestQueryIdType;
  const handle = String(state.latestQueryResultHandle || '');
  if (!scopeIds.length && !handle) {
    return;
  }
  refs.phenoActionEl.value = "compare";
  state.phenoSelectedSavedCohortIds = [];
  state.phenoQuerySelection = {
    ...createSelectionMetadata({...currentAnalysisDatasetMetadata(),
      patientIds:state.latestQueryPatientIds, sampleIds:state.latestQueryRecordIds,
      queryResultHandle:handle, idType,
      patientCount:idType === 'sample' ? undefined : state.latestQueryTotalCount || state.latestQueryPatientIds.length,
      sampleCount:idType === 'sample' ? state.latestQueryTotalCount || state.latestQueryRecordIds.length : 0,
      sourceKind:'query', sourcePrompt:state.latestQueryPrompt}),
    // Pheno-Ranker's request/session transport still uses these aliases.
    handle, count:state.latestQueryTotalCount, idType,
  };
  savedCohortsUi.renderPhenoSavedCohortsSelection();
  refs.phenoModeEl.value = "cohort";
  refs.phenoSelectedPatientIdsEl.value = scopeIds.join(",");
  phenoUi.renderSelectedPatientIdsSummary();
  phenoUi.updatePhenoMode();
  navigationUi.setActiveTab("pheno");
  refs.phenoStatusEl.className = "pheno-status";
  refs.phenoStatusEl.textContent = handle
    ? `Loaded all ${state.latestQueryTotalCount} matching ${state.latestQueryIdType === 'sample' ? 'samples' : 'patients'} from Query. Identifiers remain server-side.`
    : state.latestQueryRecordIds.length
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

function initializeChatDock() {
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
    phenoUi.showPlanProgress(stage.label, stage.detail);
    phenoUi.renderPlanningProgress();
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
    phenoUi.renderRunProgress(stage.label, stage.detail);
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
    refreshPatientOverview: () => patientOverviewUi?.refresh(),
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
    addRequiredDatasets: addCohortDatasets,
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
    queryReplyModel: (...args)=>queryUi.queryReplyModel(...args),
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
    chatCardModel: item => item.chatKind === 'pheno' ? phenoSessionsUi.cardModel(item) : querySessionsUi.cardModel(item),
    chatOrganization: () => chatFoldersUi?.snapshot(),
    chatSelection: () => chatDeletionUi?.snapshot(),
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
    fallbackCopyText,
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
    renderAnalysisFlowBar: () => analysisCatalogUi.renderAnalysisFlowBar(),
    setAnalysisComposerStatus: message => analysisUi.setAnalysisComposerStatus(message),
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
    refreshPatientOverview: () => patientOverviewUi?.refresh(),
    canManageDataset: () => authUi.canManageDataset(),
    loadDatasets: (options) => datasetsUi.loadDatasets(options),
    openDatasets: () => navigationUi.setActiveTab('datasets'),
    currentTabName: () => navigationUi.currentTabName(),
    currentDatasetRecord: () => datasetsUi.currentDatasetRecord(),
    datasetScopeLabel: () => datasetsUi.datasetScopeLabel(),
    pendingDatasetSelectionIds: () => datasetsUi.pendingDatasetSelectionIds(),
    currentDatasetSelectionKey: (datasetIds) => datasetsUi.currentDatasetSelectionKey(datasetIds),
    renderDatasetPicker: () => datasetsUi.renderDatasetPicker(),
    renderDatasetAdminList: () => datasetsUi.renderDatasetAdminList(),
    renderDatasetScopeSummary: () => datasetsUi.renderDatasetScopeSummary(),
    renderAnalysisDatasetScope: () => datasetsUi.renderAnalysisDatasetScope(),
    restoreAnalysisSetup: () => {
      const session = currentAnalysisSession();
      if (session?.datasetId === datasetsUi.currentDatasetSelectionKey()) analysisSessionsUi.applyAnalysisSession(session);
    },
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
    resetDashboardViews: () => dashboardUi.resetDashboardViews(),
    resetPatientInspectorView: () => dashboardUi.resetPatientInspectorView(),
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
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".clarid-identity")) dashboardUi.closeClaridPopovers();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") dashboardUi.closeClaridPopovers();
  });
  window.addEventListener('resize', () => dashboardUi.closeClaridPopovers());
  // Ignore automatic chat scrolling while a reply settles; dismiss on user scrolling.
  for (const eventName of ['wheel', 'touchmove']) {
    document.addEventListener(eventName, event => {
      if (!event.target.closest?.('.clarid-popover')) dashboardUi.closeClaridPopovers();
    }, {capture: true, passive: true});
  }
  document.addEventListener("click", event => queryUi.handleDocumentClick(event));
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
  initializeChatDock();
  initializeNavigationShell();
  applyStoredTabPreferences();
  navigationUi.setDashboardSubtab(state.currentDashboardSubtab);
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
  createCohortScopeUi({state, escapeHtml, renderGlobalContext: () => workspaceUi.renderGlobalContext()});
  createClinicalSummaryUi({state, navigation:navigationUi,
    renderDashboard: summary => dashboardUi.renderDashboard(summary),
    renderGlobalContext: () => workspaceUi.renderGlobalContext()});
  patientOverviewUi = createPatientOverview({state, navigation:navigationUi, escapeHtml,
    saveIdsAsCohort: options => savedCohortsUi.saveIdsAsCohort(options),
    scope:() => datasetsUi.currentDatasetSelectionKey(),
    openTimeline:async (patientId, datasetId) => {
      state.timelinePatientFilter = JSON.stringify([datasetId, patientId]);
      state.timelineDatasetFilter = ''; state.timelinePatientSearch = ''; state.timelinePage = 0;
      navigationUi.setDashboardSubtab('timeline');
      dashboardUi.renderDashboardTimeline(state.dashboardSummaryState || state.dashboardSummary || {});
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
  createProjectsUi({view:shellActions.Rail.projectViewRef.current, state, refs, sessions:analysisSessionsUi, query:queryUi,
    workspace:workspaceUi, datasets:datasetsUi, navigation:navigationUi});
}

Object.assign(actionContext, {
  jobsUi,
  setAnalysisChatsDrawerOpen,
  authUi,
  userSettingsUi,
  savedCohortsUi,
  state,
  datasetsUi,
  workspaceUi,
  refs,
  chatDeletionUi,
  chatFoldersUi,
  querySessionsUi,
  phenoSessionsUi,
  analysisSessionsUi,
  navigationUi,
  analysisUi,
  analysisCatalogUi,
  modelsAdminUi,
  usersAdminUi,
  phenoUi,
  setAnalysisScopeMetadataFromSelection,
  dashboardUi,
  queryUi,
});
void bootstrap();
