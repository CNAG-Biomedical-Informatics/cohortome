      import { escapeHtml, fallbackCopyText, renderActivityCard } from "/static/js/shared.js";
      import { createDashboardUi } from "/static/js/dashboard.js";
      import { createAnalysisSessionsUi } from "/static/js/analysis_sessions.js";
      import { createSavedCohortsUi } from "/static/js/saved_cohorts.js";
      import { createPhenoUi } from "/static/js/pheno.js";
      import { createQueryUi } from "/static/js/query.js";
      import { createAnalysisUi } from "/static/js/analysis.js";

      const appShellEl = document.getElementById("appShell");
      const authGateEl = document.getElementById("authGate");
      const authGateStatusEl = document.getElementById("authGateStatus");
      const heroAuthUtilityEl = document.getElementById("heroAuthUtility");
      const heroAuthIdentityEl = document.getElementById("heroAuthIdentity");
      const heroLogoutBtnEl = document.getElementById("heroLogoutBtn");
      const dashboardTabBtnEl = document.getElementById("dashboardTabBtn");
      const dataTabBtnEl = document.getElementById("dataTabBtn");
      const usersTabBtnEl = document.getElementById("usersTabBtn");
      const queryTabBtnEl = document.getElementById("queryTabBtn");
      const analysisTabBtnEl = document.getElementById("analysisTabBtn");
      const phenoTabBtnEl = document.getElementById("phenoTabBtn");
      const dashboardClinicalBtnEl = document.getElementById("dashboardClinicalBtn");
      const dashboardMolecularBtnEl = document.getElementById("dashboardMolecularBtn");
      const tabHelperTextEl = document.getElementById("tabHelperText");
      const dashboardTabEl = document.getElementById("dashboardTab");
      const dataTabEl = document.getElementById("dataTab");
      const usersTabEl = document.getElementById("usersTab");
      const queryTabEl = document.getElementById("queryTab");
      const analysisTabEl = document.getElementById("analysisTab");
      const phenoTabEl = document.getElementById("phenoTab");
      const dashboardClinicalPanelEl = document.getElementById("dashboardClinicalPanel");
      const dashboardMolecularPanelEl = document.getElementById("dashboardMolecularPanel");
      const contextDataDirEl = document.getElementById("contextDataDir");
      const contextCohortEl = document.getElementById("contextCohort");
      const contextLmModelEl = document.getElementById("contextLmModel");
      const contextScopeEl = document.getElementById("contextScope");
      const contextAuthEl = document.getElementById("contextAuth");
      const patientsEl = document.getElementById("patients");
      const dashboardEl = document.getElementById("dashboard");
      const detailEl = document.getElementById("detail");
      const dataDirEl = document.getElementById("dataDir");
      const loadStatusEl = document.getElementById("loadStatus");
      const queryReplyEl = document.getElementById("queryReply");
      const queryStatusEl = document.getElementById("queryStatus");
      const queryMetaEl = document.getElementById("queryMeta");
      const lmStatusEl = document.getElementById("lmStatus");
      const queryReasonEl = document.getElementById("queryReason");
      const queryActionsEl = document.getElementById("queryActions");
      const queryFollowupsEl = document.getElementById("queryFollowups");
      const queryExamplesEl = document.getElementById("queryExamples");
      const queryStarterPanelEl = document.getElementById("queryStarterPanel");
      const queryDiseaseBuilderBtnEl = document.getElementById("queryDiseaseBuilderBtn");
      const queryDiseasePanelEl = document.getElementById("queryDiseasePanel");
      const queryDiseaseTopChipsEl = document.getElementById("queryDiseaseTopChips");
      const queryDiseaseStatusEl = document.getElementById("queryDiseaseStatus");
      const queryDataEl = document.getElementById("queryData");
      const queryDetailsEl = document.getElementById("queryDetails");
      const queryThreadEl = document.getElementById("queryThread");
      const queryPlannerBtnEl = document.getElementById("queryPlannerBtn");
      const queryClearBtnEl = document.getElementById("queryClearBtn");
      const questionEl = document.getElementById("question");
      const askBtnEl = document.getElementById("askBtn");
      const analysisPromptEl = document.getElementById("analysisPrompt");
      const analysisRunBtnEl = document.getElementById("analysisRunBtn");
      const analysisExamplesEl = document.getElementById("analysisExamples");
      const analysisStarterPanelEl = document.getElementById("analysisStarterPanel");
      const analysisComposerExamplesBtnEl = document.getElementById("analysisComposerExamplesBtn");
      const molecularDashboardStatusEl = document.getElementById("molecularDashboardStatus");
      const molecularDashboardCardsEl = document.getElementById("molecularDashboardCards");
      const analysisMolecularDatasetListEl = document.getElementById("analysisMolecularDatasetList");
      const analysisMolecularGeneEl = document.getElementById("analysisMolecularGene");
      const analysisMolecularGenesEl = document.getElementById("analysisMolecularGenes");
      const analysisMolecularRunBtnEl = document.getElementById("analysisMolecularRunBtn");
      const analysisMolecularStatusEl = document.getElementById("analysisMolecularStatus");
      const analysisMolecularResultEl = document.getElementById("analysisMolecularResult");
      const analysisSelectedPatientIdsEl = document.getElementById("analysisSelectedPatientIds");
      const analysisSelectedPatientIdsSummaryEl = document.getElementById("analysisSelectedPatientIdsSummary");
      const analysisSelectedSavedCohortSelectionEl = document.getElementById("analysisSelectedSavedCohortSelection");
      const analysisCompareModeEl = document.getElementById("analysisCompareMode");
      const analysisCompareFieldEl = document.getElementById("analysisCompareField");
      const analysisCompareSelectedPatientIdsEl = document.getElementById("analysisCompareSelectedPatientIds");
      const analysisCompareSelectedPatientIdsSummaryEl = document.getElementById("analysisCompareSelectedPatientIdsSummary");
      const analysisCompareSavedCohortSelectionEl = document.getElementById("analysisCompareSavedCohortSelection");
      const savedCohortsEl = document.getElementById("savedCohorts");
      const phenoSavedCohortsEl = document.getElementById("phenoSavedCohorts");
      const analysisStatusEl = document.getElementById("analysisStatus");
      const analysisMetaEl = document.getElementById("analysisMeta");
      const analysisLmStatusEl = document.getElementById("analysisLmStatus");
      const analysisThreadEl = document.getElementById("analysisThread");
      const analysisSessionListEl = document.getElementById("analysisSessionList");
      const analysisNewSessionBtnEl = document.getElementById("analysisNewSessionBtn");
      const loadBtnEl = document.getElementById("loadBtn");
      const loadBtnIconEl = document.getElementById("loadBtnIcon");
      const loadBtnLabelEl = document.getElementById("loadBtnLabel");
      const datasetAdminControlsEl = document.getElementById("datasetAdminControls");
      const usersStatusEl = document.getElementById("usersStatus");
      const usersListEl = document.getElementById("usersList");
      const authUsernameEl = document.getElementById("authUsername");
      const authPasswordEl = document.getElementById("authPassword");
      const authLoginBtnEl = document.getElementById("authLoginBtn");
      const patientSearchEl = document.getElementById("patientSearch");
      const phenoActionEl = document.getElementById("phenoAction");
      const phenoModeEl = document.getElementById("phenoMode");
      const phenoPromptEl = document.getElementById("phenoPrompt");
      const phenoExamplesEl = document.getElementById("phenoExamples");
      const phenoPlanBtnEl = document.getElementById("phenoPlanBtn");
      const phenoPlanRunBtnEl = document.getElementById("phenoPlanRunBtn");
      const phenoPlanStatusEl = document.getElementById("phenoPlanStatus");
      const phenoPlanMetaEl = document.getElementById("phenoPlanMeta");
      const phenoManualOverrideNoteEl = document.getElementById("phenoManualOverrideNote");
      const phenoLmStatusEl = document.getElementById("phenoLmStatus");
      const phenoPlanDetailsEl = document.getElementById("phenoPlanDetails");
      const phenoPlanEl = document.getElementById("phenoPlan");
      const phenoPlanReasoningEl = document.getElementById("phenoPlanReasoning");
      const phenoReferenceFilesSummaryEl = document.getElementById("phenoReferenceFilesSummary");
      const phenoSavedCohortsSelectionEl = document.getElementById("phenoSavedCohortsSelection");
      const phenoPatientFieldEl = document.getElementById("phenoPatientField");
      const phenoPatientIdEl = document.getElementById("phenoPatientId");
      const phenoSelectedPatientIdsEl = document.getElementById("phenoSelectedPatientIds");
      const phenoSelectedPatientIdsSummaryEl = document.getElementById("phenoSelectedPatientIdsSummary");
      const phenoIncludeTermsEl = document.getElementById("phenoIncludeTerms");
      const phenoExcludeTermsEl = document.getElementById("phenoExcludeTerms");
      const phenoSimilarityMetricEl = document.getElementById("phenoSimilarityMetric");
      const phenoSortByEl = document.getElementById("phenoSortBy");
      const phenoMaxOutFieldEl = document.getElementById("phenoMaxOutField");
      const phenoMaxOutEl = document.getElementById("phenoMaxOut");
      const phenoAlignChecksEl = document.getElementById("phenoAlignChecks");
      const phenoAlignEl = document.getElementById("phenoAlign");
      const phenoRenderHeatmapEl = document.getElementById("phenoRenderHeatmap");
      const phenoRenderMdsEl = document.getElementById("phenoRenderMds");
      const phenoPlotChecksEl = document.getElementById("phenoPlotChecks");
      const phenoRunBtnEl = document.getElementById("phenoRunBtn");
      const phenoExplainBtnEl = document.getElementById("phenoExplainBtn");
      const phenoExplainLlmBtnEl = document.getElementById("phenoExplainLlmBtn");
      const phenoAnalysisBtnEl = document.getElementById("phenoAnalysisBtn");
      const phenoCopyIdsBtnEl = document.getElementById("phenoCopyIdsBtn");
      const phenoStatusEl = document.getElementById("phenoStatus");
      const phenoExplainCardEl = document.getElementById("phenoExplainCard");
      const phenoAlignmentCardEl = document.getElementById("phenoAlignmentCard");
      const phenoExplainDetailEl = document.getElementById("phenoExplainDetail");
      const phenoCommandEl = document.getElementById("phenoCommand");
      const phenoFilesEl = document.getElementById("phenoFiles");
      const phenoResultEmptyStateEl = document.getElementById("phenoResultEmptyState");
      const phenoResultWorkspaceEl = document.getElementById("phenoResultWorkspace");
      const phenoOutputDetailsEl = document.getElementById("phenoOutputDetails");
      const phenoOutputPreviewEl = document.getElementById("phenoOutputPreview");
      const phenoAlignmentDetailEl = document.getElementById("phenoAlignmentDetail");
      const phenoLogsEl = document.getElementById("phenoLogs");
      const phenoPreviewsEl = document.getElementById("phenoPreviews");
      const MAX_VISIBLE_PATIENTS = 80;
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
      let selectedPatientId = null;
      let currentPatients = [];
      let molecularDatasetsState = [];
      let selectedMolecularDatasets = [];
      let queryInFlight = false;
      let queryHistory = [];
      let queryTurns = [];
      let queryExecutionMode = "auto";
      let queryProgressTimer = null;
      let analysisInFlight = false;
      let loadInFlight = false;
      let phenoPlanProgressTimer = null;
      let phenoRunProgressTimer = null;
      let latestQueryPatientIds = [];
      let latestQueryRecordIds = [];
      let latestQueryIdType = "patient";
      let latestQueryPrompt = "";
      let latestQueryAnalysisPrompt = "";
      let analysisHistory = [];
      let analysisTurns = [];
      let analysisProgressTimer = null;
      let analysisExamplesPinnedOpen = false;
      let analysisExecutionMode = "auto";
      let analysisSessions = [];
      let currentAnalysisSessionId = "";
      let analysisSelectedSavedCohortId = "";
      let analysisCompareSavedCohortId = "";
      let phenoRankerPatientIds = [];
      let phenoReferenceFiles = [];
      let phenoSelectedSavedCohortIds = [];
      let dashboardSummaryState = null;
      let savedCohorts = [];
      let authState = {
        enabled: false,
        authenticated: true,
        user: { username: "local", role: "admin", display_name: "Local user" },
      };
      const MAX_VISIBLE_EXAMPLES = 8;
      const ACTIVE_TAB_STORAGE_KEY = "patient-navigator.active-tab";
      const DASHBOARD_SUBTAB_STORAGE_KEY = "patient-navigator.dashboard-subtab";
      const ANALYSIS_SESSIONS_STORAGE_KEY = "patient-navigator.analysis-sessions";
      const TAB_HELPER_TEXT = {
        dashboard: "Browse the loaded clinical and molecular data",
        data: "Admin-only shared dataset loading and refresh",
        users: "Admin-only read-only user visibility",
        query: "Build and refine cohorts (LLM-assisted, deterministic results)",
        analysis: "Interpret and compare cohorts (LLM-assisted insights)",
        pheno: "Compare patients or cohorts and inspect similarity results",
      };

      let currentDashboardSubtab = "clinical";

      function renderTabHelperText(tabName) {
        if (!tabHelperTextEl) {
          return;
        }
        if (tabName === "dashboard") {
          tabHelperTextEl.textContent = currentDashboardSubtab === "molecular"
            ? "Inspect loaded molecular datasets and quick transcriptomics summaries"
            : "Browse patients and orient yourself in the loaded clinical dataset";
          return;
        }
        tabHelperTextEl.textContent = TAB_HELPER_TEXT[tabName] || "";
      }

      function nowIso() {
        return new Date().toISOString();
      }

      function shortTimestamp(value) {
        if (!value) {
          return "Just now";
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
          return "Just now";
        }
        return parsed.toLocaleString([], {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
      }

      function analysisSessionId() {
        return `analysis-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      }

      function currentStorageNamespace() {
        if (authState.enabled) {
          if (authState.authenticated && authState.user && authState.user.username) {
            return `user.${authState.user.username}`;
          }
          return "user.signed-out";
        }
        return "user.local";
      }

      function createAnalysisSession(overrides) {
        const session = overrides || {};
        return {
          id: session.id || analysisSessionId(),
          title: typeof session.title === "string" ? session.title : "",
          dataDir: typeof session.dataDir === "string" ? session.dataDir : (dataDirEl && dataDirEl.value ? dataDirEl.value.trim() : ""),
          promptDraft: typeof session.promptDraft === "string" ? session.promptDraft : "Summarize the main clinical patterns in this cohort and tell me what stands out.",
          scope: typeof session.scope === "string" ? session.scope : "",
          compareMode: Boolean(session.compareMode),
          compareScope: typeof session.compareScope === "string" ? session.compareScope : "",
          savedCohortIdA: typeof session.savedCohortIdA === "string" ? session.savedCohortIdA : "",
          savedCohortIdB: typeof session.savedCohortIdB === "string" ? session.savedCohortIdB : "",
          history: Array.isArray(session.history) ? session.history : [],
          turns: Array.isArray(session.turns) ? session.turns : [],
          updatedAt: typeof session.updatedAt === "string" ? session.updatedAt : nowIso(),
        };
      }

      function currentAnalysisSession() {
        return analysisSessions.find((session) => session.id === currentAnalysisSessionId) || null;
      }

      function analysisSessionTitle(session) {
        const customTitle = String(session.title || "").trim();
        if (customTitle) {
          return customTitle;
        }
        const firstUserTurn = (session.turns || []).find((turn) => turn.role === "user" && turn.prompt);
        const raw = (firstUserTurn && firstUserTurn.prompt)
          || (session.compareMode ? "Compare cohorts" : "")
          || (String(session.scope || "").trim() ? "Scoped analysis" : "")
          || session.promptDraft
          || "New analysis";
        const trimmed = String(raw).trim();
        if (!trimmed) {
          return "New analysis";
        }
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

      const analysisSessionsUi = createAnalysisSessionsUi({
        refs: {
          analysisSessionListEl,
          analysisPromptEl,
          analysisSelectedPatientIdsEl,
          analysisCompareModeEl,
          analysisCompareSelectedPatientIdsEl,
          analysisSelectedSavedCohortSelectionEl,
          analysisCompareSavedCohortSelectionEl,
          analysisStatusEl,
          analysisMetaEl,
          dataDirEl,
        },
        helpers: {
          escapeHtml,
          shortTimestamp,
          nowIso,
        },
        callbacks: {
          createAnalysisSession,
          currentAnalysisSession,
          getStorageNamespace: currentStorageNamespace,
          renderAnalysisCompareMode,
          renderAnalysisScopeSummary,
          renderAnalysisCompareScopeSummary,
          renderAnalysisStarterPrompts,
          renderAnalysisThread,
          renderAnalysisMeta,
        },
        state: {
          get analysisSessions() { return analysisSessions; },
          set analysisSessions(value) { analysisSessions = value; },
          get currentAnalysisSessionId() { return currentAnalysisSessionId; },
          set currentAnalysisSessionId(value) { currentAnalysisSessionId = value; },
          get analysisHistory() { return analysisHistory; },
          set analysisHistory(value) { analysisHistory = value; },
          get analysisTurns() { return analysisTurns; },
          set analysisTurns(value) { analysisTurns = value; },
          get analysisExamplesPinnedOpen() { return analysisExamplesPinnedOpen; },
          set analysisExamplesPinnedOpen(value) { analysisExamplesPinnedOpen = value; },
          get analysisSelectedSavedCohortId() { return analysisSelectedSavedCohortId; },
          set analysisSelectedSavedCohortId(value) { analysisSelectedSavedCohortId = value; },
          get analysisCompareSavedCohortId() { return analysisCompareSavedCohortId; },
          set analysisCompareSavedCohortId(value) { analysisCompareSavedCohortId = value; },
        },
        constants: {
          ANALYSIS_SESSIONS_STORAGE_KEY,
        },
      });

      function persistAnalysisSessions() {
        analysisSessionsUi.persistAnalysisSessions();
      }

      async function loadAnalysisSessionsFromBackend() {
        return analysisSessionsUi.loadAnalysisSessionsFromBackend();
      }

      function renderAnalysisSessionList() {
        analysisSessionsUi.renderAnalysisSessionList();
      }

      function syncCurrentAnalysisSessionFromUi(options) {
        analysisSessionsUi.syncCurrentAnalysisSessionFromUi(options);
      }

      function applyAnalysisSession(session) {
        analysisSessionsUi.applyAnalysisSession(session);
      }

      function selectAnalysisSession(sessionId) {
        analysisSessionsUi.selectAnalysisSession(sessionId);
      }

      function createAndSelectAnalysisSession(overrides) {
        analysisSessionsUi.createAndSelectAnalysisSession(overrides);
      }

      function ensureAnalysisSessionsLoaded() {
        analysisSessionsUi.ensureAnalysisSessionsLoaded();
      }

      function renameAnalysisSession(sessionId) {
        analysisSessionsUi.renameAnalysisSession(sessionId);
      }

      function deleteAnalysisSessionById(sessionId) {
        analysisSessionsUi.deleteAnalysisSessionById(sessionId);
      }

      function prepareAnalysisSessionForDataDir(nextDataDir) {
        analysisSessionsUi.prepareAnalysisSessionForDataDir(nextDataDir);
      }

      function setActiveTab(tabName) {
        const showDashboard = tabName === "dashboard";
        const showData = tabName === "data";
        const showUsers = tabName === "users";
        const showQuery = tabName === "query";
        const showAnalysis = tabName === "analysis";
        const showPheno = tabName === "pheno";
        dashboardTabBtnEl.classList.toggle("active", showDashboard);
        dataTabBtnEl && dataTabBtnEl.classList.toggle("active", showData);
        usersTabBtnEl && usersTabBtnEl.classList.toggle("active", showUsers);
        queryTabBtnEl.classList.toggle("active", showQuery);
        analysisTabBtnEl.classList.toggle("active", showAnalysis);
        phenoTabBtnEl.classList.toggle("active", showPheno);
        dashboardTabEl.classList.toggle("active", showDashboard);
        dataTabEl && dataTabEl.classList.toggle("active", showData);
        usersTabEl && usersTabEl.classList.toggle("active", showUsers);
        queryTabEl.classList.toggle("active", showQuery);
        analysisTabEl.classList.toggle("active", showAnalysis);
        phenoTabEl.classList.toggle("active", showPheno);
        try {
          window.localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, tabName);
        } catch (_error) {
        }
        renderTabHelperText(tabName);
        renderGlobalContext();
      }

      function setDashboardSubtab(subtabName) {
        currentDashboardSubtab = subtabName === "molecular" ? "molecular" : "clinical";
        dashboardClinicalBtnEl && dashboardClinicalBtnEl.classList.toggle("active", currentDashboardSubtab === "clinical");
        dashboardMolecularBtnEl && dashboardMolecularBtnEl.classList.toggle("active", currentDashboardSubtab === "molecular");
        dashboardClinicalPanelEl && dashboardClinicalPanelEl.classList.toggle("active", currentDashboardSubtab === "clinical");
        dashboardMolecularPanelEl && dashboardMolecularPanelEl.classList.toggle("active", currentDashboardSubtab === "molecular");
        try {
          window.localStorage.setItem(DASHBOARD_SUBTAB_STORAGE_KEY, currentDashboardSubtab);
        } catch (_error) {
        }
        if (currentTabName() === "dashboard") {
          renderTabHelperText("dashboard");
          renderGlobalContext();
        }
      }

      function renderLoadButtonState() {
        if (!loadBtnEl) {
          return;
        }
        loadBtnEl.classList.toggle("is-loading", Boolean(loadInFlight));
        if (loadBtnLabelEl) {
          loadBtnLabelEl.textContent = loadInFlight ? "Loading..." : "Load dataset";
        }
        if (loadBtnIconEl) {
          loadBtnIconEl.innerHTML = loadInFlight
            ? '<span class="button-spinner" aria-hidden="true"></span>'
            : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                 <path d="M12 3v12"></path>
                 <path d="m7 10 5 5 5-5"></path>
                 <path d="M5 21h14"></path>
               </svg>`;
        }
      }

      function formatNumber(value) {
        return new Intl.NumberFormat().format(value);
      }

      function initializeExampleToggle(container, maxVisible = MAX_VISIBLE_EXAMPLES) {
        if (!container) {
          return;
        }
        const chips = Array.from(container.querySelectorAll(".query-chip"))
          .filter((chip) => !chip.classList.contains("badge") && !chip.classList.contains("query-chip-toggle"));
        if (chips.length <= maxVisible) {
          return;
        }
        chips.forEach((chip, index) => {
          chip.classList.toggle("is-extra-example", index >= maxVisible);
        });
        container.classList.add("is-collapsed");

        const toggleWrap = document.createElement("div");
        toggleWrap.className = "query-examples-toggle";

        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.className = "query-chip query-chip-toggle";
        toggleBtn.textContent = `See more (${chips.length - maxVisible})`;
        toggleBtn.addEventListener("click", () => {
          const expanded = container.classList.toggle("is-collapsed");
          toggleBtn.textContent = expanded ? `See more (${chips.length - maxVisible})` : "Show fewer";
        });

        toggleWrap.appendChild(toggleBtn);
        container.insertAdjacentElement("afterend", toggleWrap);
      }

      function renderStarterPanelVisibility(panelEl, composerToggleEl, hasTurns, pinnedOpen) {
        if (!panelEl || !composerToggleEl) {
          return;
        }
        const visible = hasTurns ? pinnedOpen : true;
        panelEl.hidden = !visible;
        panelEl.classList.toggle("is-hidden", !visible);
        const inlineToggle = panelEl.querySelector(".query-examples-toggle");
        if (inlineToggle) {
          inlineToggle.hidden = !visible;
          inlineToggle.classList.toggle("is-hidden", !visible);
        }
        const siblingToggle = panelEl.nextElementSibling && panelEl.nextElementSibling.classList && panelEl.nextElementSibling.classList.contains("query-examples-toggle")
          ? panelEl.nextElementSibling
          : null;
        if (siblingToggle) {
          siblingToggle.hidden = !visible;
          siblingToggle.classList.toggle("is-hidden", !visible);
        }
        composerToggleEl.hidden = !hasTurns;
        composerToggleEl.textContent = "Starter prompts";
      }

      function renderQueryStarterPrompts() {
        if (!queryStarterPanelEl) {
          return;
        }
        queryStarterPanelEl.hidden = false;
        const siblingToggle = queryStarterPanelEl.nextElementSibling && queryStarterPanelEl.nextElementSibling.classList && queryStarterPanelEl.nextElementSibling.classList.contains("query-examples-toggle")
          ? queryStarterPanelEl.nextElementSibling
          : null;
        if (siblingToggle) {
          siblingToggle.hidden = false;
        }
      }

      function renderQueryExecutionMode() {
        if (!queryPlannerBtnEl) {
          return;
        }
        const active = queryExecutionMode === "planner_only";
        queryPlannerBtnEl.classList.toggle("is-active", active);
        queryPlannerBtnEl.setAttribute("aria-pressed", active ? "true" : "false");
        queryPlannerBtnEl.title = active
          ? "Semantic planner is enabled for the next query."
          : "Skip deterministic matching for the next query and use the LLM planner first.";
      }

      function renderAnalysisStarterPrompts() {
        if (!analysisStarterPanelEl || !analysisComposerExamplesBtnEl) {
          return;
        }
        analysisStarterPanelEl.hidden = false;
        analysisStarterPanelEl.classList.remove("is-hidden");
        const inlineToggle = analysisStarterPanelEl.querySelector(".query-examples-toggle");
        if (inlineToggle) {
          inlineToggle.hidden = false;
          inlineToggle.classList.remove("is-hidden");
        }
        const siblingToggle = analysisStarterPanelEl.nextElementSibling && analysisStarterPanelEl.nextElementSibling.classList && analysisStarterPanelEl.nextElementSibling.classList.contains("query-examples-toggle")
          ? analysisStarterPanelEl.nextElementSibling
          : null;
        if (siblingToggle) {
          siblingToggle.hidden = false;
          siblingToggle.classList.remove("is-hidden");
        }
        analysisComposerExamplesBtnEl.hidden = !(Array.isArray(analysisTurns) && analysisTurns.length > 0);
        analysisComposerExamplesBtnEl.textContent = "Starter prompts";
      }

      function stopQueryProgressUpdates() {
        if (queryProgressTimer !== null) {
          window.clearInterval(queryProgressTimer);
          queryProgressTimer = null;
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
          const lastTurn = queryTurns[queryTurns.length - 1];
          if (!lastTurn || !lastTurn.pending) {
            stopQueryProgressUpdates();
            return;
          }
          const stage = stages[Math.min(index, stages.length - 1)];
          lastTurn.pendingLabel = stage.label;
          lastTurn.pendingDetail = stage.detail;
          renderQueryThread();
          if (index < stages.length - 1) {
            index += 1;
          }
        };
        applyStage();
        queryProgressTimer = window.setInterval(applyStage, 1400);
      }

      function stopAnalysisProgressUpdates() {
        if (analysisProgressTimer !== null) {
          window.clearInterval(analysisProgressTimer);
          analysisProgressTimer = null;
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
          const lastTurn = analysisTurns[analysisTurns.length - 1];
          if (!lastTurn || !lastTurn.pending) {
            stopAnalysisProgressUpdates();
            return;
          }
          const stage = stages[Math.min(index, stages.length - 1)];
          lastTurn.pendingLabel = stage.label;
          lastTurn.pendingDetail = stage.detail;
          renderAnalysisThread();
          if (index < stages.length - 1) {
            index += 1;
          }
        };
        applyStage();
        analysisProgressTimer = window.setInterval(applyStage, 1500);
      }

      function stopPhenoPlanProgressUpdates() {
        if (phenoPlanProgressTimer !== null) {
          window.clearInterval(phenoPlanProgressTimer);
          phenoPlanProgressTimer = null;
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
          phenoPlanStatusEl.className = "pheno-status loading";
          phenoPlanStatusEl.textContent = stage.label;
          phenoPlanEl.innerHTML = renderActivityCard(stage.label, stage.detail);
          phenoPlanReasoningEl.innerHTML = renderActivityCard("Planner reasoning", "Waiting for the interpreted plan and supporting rationale.");
          if (index < stages.length - 1) {
            index += 1;
          }
        };
        applyStage();
        phenoPlanProgressTimer = window.setInterval(applyStage, 1600);
      }

      function stopPhenoRunProgressUpdates() {
        if (phenoRunProgressTimer !== null) {
          window.clearInterval(phenoRunProgressTimer);
          phenoRunProgressTimer = null;
        }
      }

      function startPhenoRunProgressUpdates() {
        stopPhenoRunProgressUpdates();
        const patientMode = phenoModeEl.value === "patient";
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
          phenoStatusEl.className = "pheno-status loading";
          phenoStatusEl.textContent = stage.label;
          phenoOutputPreviewEl.innerHTML = renderActivityCard(stage.label, stage.detail);
          phenoPreviewsEl.innerHTML = renderActivityCard("Preparing plots", "Waiting for interactive cohort plots and result files from the active run.");
          if (index < stages.length - 1) {
            index += 1;
          }
        };
        applyStage();
        phenoRunProgressTimer = window.setInterval(applyStage, 1800);
      }

      const savedCohortsUi = createSavedCohortsUi({
        refs: {
          savedCohortsEl,
          phenoSavedCohortsEl,
          phenoSavedCohortsSelectionEl,
          phenoSelectedPatientIdsEl,
          phenoSelectedPatientIdsSummaryEl,
          analysisSelectedPatientIdsEl,
          analysisCompareModeEl,
          analysisCompareSelectedPatientIdsEl,
          analysisSelectedSavedCohortSelectionEl,
          analysisCompareSavedCohortSelectionEl,
          analysisStatusEl,
          phenoStatusEl,
          dataDirEl,
        },
        helpers: {
          escapeHtml,
        },
        callbacks: {
          setActiveTab,
          renderAnalysisScopeSummary,
          renderAnalysisCompareMode,
          renderAnalysisCompareScopeSummary,
          renderSelectedPatientIdsSummary,
          renderGlobalContext,
          currentTabName,
          queryStatusEl: () => queryStatusEl,
        },
        state: {
          get savedCohorts() { return savedCohorts; },
          set savedCohorts(value) { savedCohorts = value; },
          get phenoSelectedSavedCohortIds() { return phenoSelectedSavedCohortIds; },
          set phenoSelectedSavedCohortIds(value) { phenoSelectedSavedCohortIds = value; },
          get analysisSelectedSavedCohortId() { return analysisSelectedSavedCohortId; },
          set analysisSelectedSavedCohortId(value) { analysisSelectedSavedCohortId = value; },
          get analysisCompareSavedCohortId() { return analysisCompareSavedCohortId; },
          set analysisCompareSavedCohortId(value) { analysisCompareSavedCohortId = value; },
          get latestQueryPatientIds() { return latestQueryPatientIds; },
          get latestQueryRecordIds() { return latestQueryRecordIds; },
          get latestQueryPrompt() { return latestQueryPrompt; },
          get latestQueryIdType() { return latestQueryIdType; },
        },
      });

      function renderPhenoSavedCohortsSelection() {
        savedCohortsUi.renderPhenoSavedCohortsSelection();
      }

      function renderSavedCohorts() {
        savedCohortsUi.renderSavedCohorts();
      }

      async function loadSavedCohorts() {
        await savedCohortsUi.loadSavedCohorts();
      }

      async function saveLatestQueryAsCohort() {
        await savedCohortsUi.saveLatestQueryAsCohort();
      }

      function removeSavedCohortFromPheno(cohortId) {
        savedCohortsUi.removeSavedCohortFromPheno(cohortId);
      }

      function handleSavedCohortAction(button) {
        savedCohortsUi.handleSavedCohortAction(button);
      }

      async function loadLmStatus() {
        if (!lmStatusEl || !phenoLmStatusEl || !analysisLmStatusEl) {
          return;
        }
        try {
          const response = await fetch("/lm-status");
          if (!response.ok) {
            throw new Error("Unable to load LM status.");
          }
          const payload = await response.json();
          let text = "LM Studio: disabled";
          if (payload.enabled) {
            text = payload.model
              ? `LM Studio model: ${payload.model}`
              : "LM Studio: enabled, but no model is loaded";
          }
          lmStatusEl.textContent = text;
          phenoLmStatusEl.textContent = text;
          analysisLmStatusEl.textContent = text;
          if (contextLmModelEl) {
            contextLmModelEl.textContent = payload.enabled
              ? (payload.model || "Enabled, no model loaded")
              : "Disabled";
          }
        } catch (error) {
          const text = "LM Studio model: unavailable";
          lmStatusEl.textContent = text;
          phenoLmStatusEl.textContent = text;
          analysisLmStatusEl.textContent = text;
          if (contextLmModelEl) {
            contextLmModelEl.textContent = "Unavailable";
          }
        }
        renderGlobalContext();
      }

      function currentTabName() {
        if (phenoTabEl.classList.contains("active")) return "pheno";
        if (dataTabEl && dataTabEl.classList.contains("active")) return "data";
        if (usersTabEl && usersTabEl.classList.contains("active")) return "users";
        if (dashboardTabEl.classList.contains("active")) return "dashboard";
        if (analysisTabEl.classList.contains("active")) return "analysis";
        if (queryTabEl.classList.contains("active")) return "query";
        return "dashboard";
      }

      function summarizeScopeForTab(tabName) {
        const selectedAnalysisCohortA = Array.isArray(savedCohorts)
          ? savedCohorts.find((item) => item.id === analysisSelectedSavedCohortId)
          : null;
        const selectedAnalysisCohortB = Array.isArray(savedCohorts)
          ? savedCohorts.find((item) => item.id === analysisCompareSavedCohortId)
          : null;
        if (tabName === "pheno") {
          const ids = getCurrentScopeIds();
          if (!ids.length && !phenoSelectedSavedCohortIds.length) {
            return "Full cohort";
          }
          if (phenoSelectedSavedCohortIds.length) {
            return `${phenoSelectedSavedCohortIds.length} saved cohort${phenoSelectedSavedCohortIds.length === 1 ? "" : "s"}`;
          }
          return `${ids.length} IDs in Pheno scope`;
        }
        if (tabName === "analysis") {
          const ids = selectedAnalysisCohortA && Array.isArray(selectedAnalysisCohortA.patient_ids)
            ? selectedAnalysisCohortA.patient_ids.map((item) => String(item).trim()).filter(Boolean)
            : String(analysisSelectedPatientIdsEl.value || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
          const compareIds = selectedAnalysisCohortB && Array.isArray(selectedAnalysisCohortB.patient_ids)
            ? selectedAnalysisCohortB.patient_ids.map((item) => String(item).trim()).filter(Boolean)
            : String((analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value) || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
          if (analysisCompareModeEl && analysisCompareModeEl.checked) {
            const labelA = ids.length ? `${ids.length} in A` : "saved cohort A not set";
            const labelB = compareIds.length ? `${compareIds.length} in B` : "saved cohort B not set";
            return `${labelA} vs ${labelB}`;
          }
          if (!ids.length) {
            return "Full cohort";
          }
          return `${ids.length} IDs in Analysis scope`;
        }
        if (tabName === "dashboard" && currentDashboardSubtab === "molecular") {
          const ids = selectedAnalysisCohortA && Array.isArray(selectedAnalysisCohortA.patient_ids)
            ? selectedAnalysisCohortA.patient_ids.map((item) => String(item).trim()).filter(Boolean)
            : String(analysisSelectedPatientIdsEl.value || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
          const compareIds = selectedAnalysisCohortB && Array.isArray(selectedAnalysisCohortB.patient_ids)
            ? selectedAnalysisCohortB.patient_ids.map((item) => String(item).trim()).filter(Boolean)
            : String((analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value) || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
          if (analysisCompareModeEl && analysisCompareModeEl.checked) {
            const labelA = ids.length ? `${ids.length} in A` : "saved cohort A not set";
            const labelB = compareIds.length ? `${compareIds.length} in B` : "saved cohort B not set";
            return `${labelA} vs ${labelB}`;
          }
          if (!ids.length) {
            return "Full cohort";
          }
          return `${ids.length} IDs in Molecular scope`;
        }
        return "Full cohort";
      }

      function renderGlobalContext() {
        if (!contextDataDirEl || !contextCohortEl || !contextLmModelEl || !contextScopeEl) {
          return;
        }
        const rawDir = String(dataDirEl && dataDirEl.value ? dataDirEl.value : "").trim();
        contextDataDirEl.textContent = rawDir || "Not configured";

        if (dashboardSummaryState && dashboardSummaryState.totals) {
          const totals = dashboardSummaryState.totals;
          contextCohortEl.textContent = `${formatNumber(totals.patients || 0)} patients, ${formatNumber(totals.visits || 0)} timepoints`;
        } else if (currentPatients.length) {
          const totalVisits = currentPatients.reduce((sum, patient) => sum + Number(patient.visit_count || 0), 0);
          contextCohortEl.textContent = `${formatNumber(currentPatients.length)} patients, ${formatNumber(totalVisits)} timepoints`;
        } else if (loadInFlight) {
          contextCohortEl.textContent = "Loading...";
        } else {
          contextCohortEl.textContent = "No cohort loaded";
        }

        if (!contextLmModelEl.textContent.trim()) {
          contextLmModelEl.textContent = "Checking...";
        }
        contextScopeEl.textContent = summarizeScopeForTab(currentTabName());
        if (contextAuthEl) {
          if (!authState.enabled) {
            contextAuthEl.textContent = "Local user";
          } else if (authState.authenticated && authState.user) {
            contextAuthEl.textContent = `${authState.user.display_name || authState.user.username} (${authState.user.role || "user"})`;
          } else {
            contextAuthEl.textContent = "Signed out";
          }
        }
      }

      function canManageDataset() {
        if (!authState.enabled) return true;
        return Boolean(authState.authenticated && authState.user && authState.user.role === "admin");
      }

      function isWorkspaceAccessible() {
        return !authState.enabled || Boolean(authState.authenticated && authState.user);
      }

      function clearLoadedWorkspaceForSignedOutState() {
        currentPatients = [];
        selectedPatientId = null;
        dashboardSummaryState = null;
        molecularDatasetsState = [];
        selectedMolecularDatasets = [];
        savedCohorts = [];
        patientsEl.innerHTML = '<div class="empty">Sign in to access the shared clinical workspace.</div>';
        detailEl.innerHTML = '<div class="empty">Patient workspace hidden until you sign in.</div>';
        dashboardEl.innerHTML = '<div class="empty">Clinical dashboard hidden until you sign in.</div>';
        if (molecularDashboardCardsEl) {
          molecularDashboardCardsEl.innerHTML = '<div class="empty">Molecular dashboard hidden until you sign in.</div>';
        }
        if (molecularDashboardStatusEl) {
          molecularDashboardStatusEl.className = "query-status";
          molecularDashboardStatusEl.textContent = "Sign in to access shared molecular datasets.";
        }
      }

      async function loadAuthUsers() {
        if (!usersListEl || !usersStatusEl) return;
        if (!canManageDataset()) {
          usersStatusEl.className = "query-status";
          usersStatusEl.textContent = "Admin access required.";
          usersListEl.innerHTML = '<div class="empty">User administration is only visible to administrators.</div>';
          return;
        }
        usersStatusEl.className = "query-status loading";
        usersStatusEl.textContent = "Loading users...";
        try {
          const response = await fetch("/auth/users");
          if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || "Unable to load users.");
          }
          const payload = await response.json();
          const users = Array.isArray(payload.users) ? payload.users : [];
          usersStatusEl.className = "query-status";
          usersStatusEl.textContent = `${users.length} user${users.length === 1 ? "" : "s"} configured.`;
          if (!users.length) {
            usersListEl.innerHTML = '<div class="empty">No users configured.</div>';
            return;
          }
          usersListEl.innerHTML = users.map((user) => `
            <div class="analysis-session-card">
              <div class="analysis-session-main">
                <div class="analysis-session-title">${escapeHtml(user.display_name || user.username || "Unknown user")}</div>
                <div class="analysis-session-meta">
                  <div>${escapeHtml(user.username || "")}</div>
                  <div>${escapeHtml(user.role || "user")}</div>
                  <div>Auth source: local</div>
                </div>
              </div>
            </div>
          `).join("");
        } catch (error) {
          usersStatusEl.className = "query-status";
          usersStatusEl.textContent = error && error.message ? error.message : "Unable to load users.";
          usersListEl.innerHTML = '<div class="empty">User list unavailable.</div>';
        }
      }

      function updateLoadButtonAvailability() {
        if (!loadBtnEl) return;
        const blocked = !canManageDataset();
        loadBtnEl.disabled = Boolean(loadInFlight || blocked);
        renderLoadButtonState();
        if (blocked && !loadInFlight) {
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = "Admin sign-in required to load or refresh shared data.";
        }
      }

      function renderAuthUi() {
        if (!authState.enabled) {
          authGateEl && authGateEl.classList.add("is-hidden");
          appShellEl && appShellEl.classList.remove("is-hidden");
          heroAuthUtilityEl && heroAuthUtilityEl.classList.add("is-hidden");
          datasetAdminControlsEl && datasetAdminControlsEl.classList.remove("is-hidden");
          dataTabBtnEl && dataTabBtnEl.classList.remove("is-hidden");
          usersTabBtnEl && usersTabBtnEl.classList.remove("is-hidden");
          updateLoadButtonAvailability();
          renderGlobalContext();
          return;
        }
        const authenticated = Boolean(authState.authenticated && authState.user);
        authGateEl && authGateEl.classList.toggle("is-hidden", authenticated);
        appShellEl && appShellEl.classList.toggle("is-hidden", !authenticated);
        heroAuthUtilityEl && heroAuthUtilityEl.classList.toggle("is-hidden", !authenticated);
        heroLogoutBtnEl && heroLogoutBtnEl.classList.toggle("is-hidden", !authenticated);
        if (authenticated) {
          if (heroAuthIdentityEl) {
            heroAuthIdentityEl.textContent = `${authState.user.display_name || authState.user.username} (${authState.user.role || "user"})`;
          }
          if (authGateStatusEl) {
            authGateStatusEl.textContent = "Enter your credentials to open your private workspace.";
          }
          const admin = canManageDataset();
          dataTabBtnEl && dataTabBtnEl.classList.toggle("is-hidden", !admin);
          usersTabBtnEl && usersTabBtnEl.classList.toggle("is-hidden", !admin);
          datasetAdminControlsEl && datasetAdminControlsEl.classList.toggle("is-hidden", !admin);
          if (!admin && (currentTabName() === "data" || currentTabName() === "users")) {
            setActiveTab("dashboard");
          }
          if (admin) {
            void loadAuthUsers();
          }
        } else {
          if (heroAuthIdentityEl) {
            heroAuthIdentityEl.textContent = "Signed out";
          }
          dataTabBtnEl && dataTabBtnEl.classList.add("is-hidden");
          usersTabBtnEl && usersTabBtnEl.classList.add("is-hidden");
          datasetAdminControlsEl && datasetAdminControlsEl.classList.add("is-hidden");
          if (authGateStatusEl) {
            authGateStatusEl.textContent = "Enter your credentials to open your private workspace.";
          }
        }
        updateLoadButtonAvailability();
        renderGlobalContext();
      }

      async function refreshUserWorkspaceState() {
        if (!isWorkspaceAccessible()) {
          analysisSessions = [];
          currentAnalysisSessionId = "";
          analysisHistory = [];
          analysisTurns = [];
          renderAnalysisSessionList();
          renderAnalysisThread();
          return;
        }
        await loadSavedCohorts();
        analysisSessions = [];
        currentAnalysisSessionId = "";
        ensureAnalysisSessionsLoaded();
        const loaded = await loadAnalysisSessionsFromBackend();
        if (!loaded) {
          analysisSessions = [createAnalysisSession({ dataDir: dataDirEl.value.trim() })];
          currentAnalysisSessionId = analysisSessions[0].id;
          applyAnalysisSession(currentAnalysisSession());
        }
      }

      async function fetchAuthStatus() {
        try {
          const response = await fetch("/auth/me");
          if (!response.ok) throw new Error("Unable to check authentication.");
          const payload = await response.json();
          authState = {
            enabled: Boolean(payload.enabled),
            authenticated: Boolean(payload.authenticated),
            user: payload.user || null,
          };
        } catch (_error) {
          authState = {
            enabled: false,
            authenticated: true,
            user: { username: "local", role: "admin", display_name: "Local user" },
          };
        }
        renderAuthUi();
      }

      async function loginLocal() {
        if (!authState.enabled) return;
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
        clearLoadedWorkspaceForSignedOutState();
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = "Signed out.";
        await refreshUserWorkspaceState();
      }

      const analysisUi = createAnalysisUi({
        refs: {
          dataDirEl,
          analysisMetaEl,
          analysisThreadEl,
          analysisStatusEl,
          analysisRunBtnEl,
          analysisPromptEl,
          analysisSelectedPatientIdsEl,
          analysisCompareModeEl,
          analysisCompareSelectedPatientIdsEl,
          analysisCompareFieldEl,
        },
        helpers: {
          escapeHtml,
          renderQueryReply,
        },
        callbacks: {
          renderAnalysisStarterPrompts,
          syncCurrentAnalysisSessionFromUi,
          startAnalysisProgressUpdates,
          stopAnalysisProgressUpdates,
          renderGlobalContext,
          renderAnalysisScopeSummary,
          renderAnalysisCompareScopeSummary,
        },
        state: {
          get analysisInFlight() { return analysisInFlight; },
          set analysisInFlight(value) { analysisInFlight = value; },
          get analysisHistory() { return analysisHistory; },
          set analysisHistory(value) { analysisHistory = value; },
          get analysisTurns() { return analysisTurns; },
          set analysisTurns(value) { analysisTurns = value; },
          get analysisExecutionMode() { return analysisExecutionMode; },
          set analysisExecutionMode(value) { analysisExecutionMode = value; },
          get analysisExamplesPinnedOpen() { return analysisExamplesPinnedOpen; },
          set analysisExamplesPinnedOpen(value) { analysisExamplesPinnedOpen = value; },
          get savedCohorts() { return savedCohorts; },
          get analysisSelectedSavedCohortId() { return analysisSelectedSavedCohortId; },
          set analysisSelectedSavedCohortId(value) { analysisSelectedSavedCohortId = value; },
          get analysisCompareSavedCohortId() { return analysisCompareSavedCohortId; },
          set analysisCompareSavedCohortId(value) { analysisCompareSavedCohortId = value; },
        },
      });

      function renderAnalysisMeta(payload) {
        analysisUi.renderAnalysisMeta(payload);
      }

      function renderAnalysisCompareMode() {
        analysisUi.renderAnalysisCompareMode();
      }

      function analysisPromptRequestsPlots(prompt) {
        return analysisUi.analysisPromptRequestsPlots(prompt);
      }

      function analysisPayloadHasPlots(payload) {
        return analysisUi.analysisPayloadHasPlots(payload);
      }

      function renderAnalysisThread() {
        analysisUi.renderAnalysisThread();
      }

      async function runAnalysis() {
        return analysisUi.runAnalysis();
      }

      const dashboardUi = createDashboardUi({
        refs: {
          patientsEl,
          dashboardEl,
          detailEl,
          dataDirEl,
          molecularDashboardStatusEl,
          molecularDashboardCardsEl,
          analysisMolecularDatasetListEl,
          analysisMolecularGeneEl,
          analysisMolecularGenesEl,
          analysisMolecularStatusEl,
          analysisMolecularResultEl,
          analysisSelectedPatientIdsEl,
          analysisSelectedPatientIdsSummaryEl,
          analysisSelectedSavedCohortSelectionEl,
          analysisCompareModeEl,
          analysisCompareSelectedPatientIdsEl,
          analysisCompareSelectedPatientIdsSummaryEl,
          analysisCompareSavedCohortSelectionEl,
        },
        helpers: {
          escapeHtml,
          formatNumber,
        },
        callbacks: {
          renderGlobalContext,
          syncCurrentAnalysisSessionFromUi,
        },
        state: {
          get selectedPatientId() { return selectedPatientId; },
          set selectedPatientId(value) { selectedPatientId = value; },
          get currentPatients() { return currentPatients; },
          set currentPatients(value) { currentPatients = value; },
          get molecularDatasetsState() { return molecularDatasetsState; },
          set molecularDatasetsState(value) { molecularDatasetsState = value; },
          get selectedMolecularDatasets() { return selectedMolecularDatasets; },
          set selectedMolecularDatasets(value) { selectedMolecularDatasets = value; },
          get dashboardSummaryState() { return dashboardSummaryState; },
          set dashboardSummaryState(value) { dashboardSummaryState = value; },
          get savedCohorts() { return savedCohorts; },
          get analysisSelectedSavedCohortId() { return analysisSelectedSavedCohortId; },
          set analysisSelectedSavedCohortId(value) { analysisSelectedSavedCohortId = value; },
          get analysisCompareSavedCohortId() { return analysisCompareSavedCohortId; },
          set analysisCompareSavedCohortId(value) { analysisCompareSavedCohortId = value; },
        },
        constants: {
          MAX_VISIBLE_PATIENTS,
        },
      });

      function renderPatientList(items) {
        dashboardUi.renderPatientList(items);
      }

      function renderDetail(patient) {
        dashboardUi.renderDetail(patient);
      }

      function renderDashboard(summary) {
        dashboardUi.renderDashboard(summary);
      }

      function renderInlineCode(value) {
        const parts = String(value).split("`");
        return parts.map((part, index) => {
          if (index % 2 === 1) {
            return `<code>${escapeHtml(part)}</code>`;
          }
          return escapeHtml(part)
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>");
        }).join("");
      }

      const queryUi = createQueryUi({
        refs: {
          dataDirEl,
          queryReplyEl,
          queryStatusEl,
          queryMetaEl,
          queryReasonEl,
          queryActionsEl,
          queryFollowupsEl,
          queryDataEl,
          queryDetailsEl,
          queryThreadEl,
          questionEl,
          askBtnEl,
          queryTabEl,
          queryExamplesEl,
          queryDiseaseTopChipsEl,
          queryDiseaseStatusEl,
          analysisSelectedPatientIdsEl,
        },
        helpers: {
          escapeHtml,
          renderActivityCard,
          fallbackCopyText,
        },
        callbacks: {
          renderQueryStarterPrompts,
          renderQueryExecutionMode,
          startQueryProgressUpdates,
          stopQueryProgressUpdates,
          nextFrame,
          saveLatestQueryAsCohort,
          sendPatientIdsToPhenoRanker,
          sendPatientIdsToAnalysis,
          sendPromptToAnalysis,
          currentPatientsProvider: () => currentPatients,
          phenoRankerPatientIdsProvider: () => phenoRankerPatientIds,
          setLatestQueryState: (patch) => {
            if (Object.prototype.hasOwnProperty.call(patch, 'ids')) {
              latestQueryPatientIds = Array.isArray(patch.ids) ? patch.ids : [];
            }
            if (Object.prototype.hasOwnProperty.call(patch, 'recordIds')) {
              latestQueryRecordIds = Array.isArray(patch.recordIds) ? patch.recordIds : [];
            }
            if (Object.prototype.hasOwnProperty.call(patch, 'prompt')) {
              latestQueryPrompt = patch.prompt || '';
            }
            if (Object.prototype.hasOwnProperty.call(patch, 'analysisPrompt')) {
              latestQueryAnalysisPrompt = patch.analysisPrompt || '';
            }
            if (Object.prototype.hasOwnProperty.call(patch, 'idType')) {
              latestQueryIdType = patch.idType || 'patient';
            }
          },
        },
        state: {
          get queryInFlight() { return queryInFlight; },
          set queryInFlight(value) { queryInFlight = value; },
          get queryHistory() { return queryHistory; },
          set queryHistory(value) { queryHistory = value; },
          get queryTurns() { return queryTurns; },
          set queryTurns(value) { queryTurns = value; },
          get queryExecutionMode() { return queryExecutionMode; },
          set queryExecutionMode(value) { queryExecutionMode = value; },
          get latestQueryPatientIds() { return latestQueryPatientIds; },
          get latestQueryRecordIds() { return latestQueryRecordIds; },
        },
      });

      function renderQueryReply(payloadOrValue) {
        return queryUi.renderQueryReply(payloadOrValue);
      }

      function renderQueryMeta(payload) {
        queryUi.renderQueryMeta(payload);
      }

      function resetQueryWorkspace() {
        queryUi.resetQueryWorkspace();
      }

      function renderQueryThread() {
        queryUi.renderQueryThread();
      }

      function renderQueryReason(payload) {
        queryUi.renderQueryReason(payload);
      }

      function renderFollowupButtons(items) {
        queryFollowupsEl.innerHTML = '';
      }

      function renderQueryActions(payload) {
        queryUi.renderQueryActions(payload);
      }

      async function askQuery() {
        await queryUi.askQuery();
      }

      async function loadQueryDiseaseOptions() {
        await queryUi.loadDiseaseOptions();
      }

      function renderAnalysisScopeSummary() {
        dashboardUi.renderAnalysisScopeSummary();
      }

      function renderAnalysisCompareScopeSummary() {
        dashboardUi.renderAnalysisCompareScopeSummary();
      }

      function renderMolecularExpressionResult(payload) {
        dashboardUi.renderMolecularExpressionResult(payload);
      }

      function renderMolecularDashboardCards(datasets) {
        dashboardUi.renderMolecularDashboardCards(datasets);
      }

      async function loadMolecularDatasets() {
        await dashboardUi.loadMolecularDatasets();
      }

      async function runMolecularExpressionAnalysis() {
        await dashboardUi.runMolecularExpressionAnalysis();
      }

      function renderSelectedPatientIdsSummary() {
        phenoUi.renderSelectedPatientIdsSummary();
      }

      function sendPatientIdsToPhenoRanker() {
        const scopeIds = latestQueryRecordIds.length ? latestQueryRecordIds : latestQueryPatientIds;
        if (!scopeIds.length) {
          return;
        }
        phenoActionEl.value = "compare";
        phenoModeEl.value = "cohort";
        phenoSelectedPatientIdsEl.value = scopeIds.join(",");
        renderSelectedPatientIdsSummary();
        updatePhenoMode();
        setActiveTab("pheno");
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = latestQueryRecordIds.length
          ? `Loaded ${latestQueryRecordIds.length} sample IDs from the query result into the current Pheno-Ranker scope.`
          : `Loaded ${latestQueryPatientIds.length} patient IDs from the query result into the current Pheno-Ranker scope.`;
      }

      function sendPatientIdsToAnalysis() {
        const scopeIds = latestQueryRecordIds.length ? latestQueryRecordIds : latestQueryPatientIds;
        if (!scopeIds.length) {
          return;
        }
        analysisSelectedSavedCohortId = "";
        analysisSelectedPatientIdsEl.value = scopeIds.join(",");
        if (latestQueryAnalysisPrompt && !analysisPromptEl.value.trim()) {
          analysisPromptEl.value = latestQueryAnalysisPrompt;
        }
        renderAnalysisScopeSummary();
        setActiveTab("analysis");
        syncCurrentAnalysisSessionFromUi({ render: true });
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = latestQueryRecordIds.length
          ? `Loaded ${latestQueryRecordIds.length} sample IDs from Query into Analysis. Run the analysis prompt to interpret this cohort.`
          : `Loaded ${latestQueryPatientIds.length} patient IDs from Query into Analysis. Run the analysis prompt to interpret this cohort.`;
      }

      function sendPromptToAnalysis(prompt, options) {
        const settings = options || {};
        const normalizedPrompt = String(prompt || "").trim();
        if (!normalizedPrompt) {
          return;
        }
        analysisPromptEl.value = normalizedPrompt;
        analysisExecutionMode = settings.llmOnly ? "llm_only" : "auto";
        setActiveTab("analysis");
        renderAnalysisScopeSummary();
        syncCurrentAnalysisSessionFromUi({ render: true });
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = latestQueryPatientIds.length
          ? `Analysis prompt prepared for the ${latestQueryPatientIds.length}-ID cohort currently loaded from Query.`
          : "Analysis prompt prepared. Select a scope or use the full cohort.";
        analysisPromptEl.focus();
      }

      function nextFrame() {
        return new Promise((resolve) => {
          window.requestAnimationFrame(() => resolve());
        });
      }

      function getCurrentScopeIds() {
        return String(phenoSelectedPatientIdsEl.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      }

      const phenoUi = createPhenoUi({
        refs: {
          dataDirEl,
          phenoActionEl,
          phenoModeEl,
          phenoPromptEl,
          phenoPlanBtnEl,
          phenoPlanRunBtnEl,
          phenoPlanStatusEl,
          phenoPlanMetaEl,
          phenoManualOverrideNoteEl,
          phenoPlanDetailsEl,
          phenoPlanEl,
          phenoPlanReasoningEl,
          phenoReferenceFilesSummaryEl,
          phenoPatientFieldEl,
          phenoPatientIdEl,
          phenoSelectedPatientIdsEl,
          phenoSelectedPatientIdsSummaryEl,
          phenoIncludeTermsEl,
          phenoExcludeTermsEl,
          phenoSimilarityMetricEl,
          phenoSortByEl,
          phenoMaxOutFieldEl,
          phenoMaxOutEl,
          phenoAlignChecksEl,
          phenoAlignEl,
          phenoRenderHeatmapEl,
          phenoRenderMdsEl,
          phenoPlotChecksEl,
          phenoRunBtnEl,
          phenoExplainBtnEl,
          phenoExplainLlmBtnEl,
          phenoAnalysisBtnEl,
          phenoCopyIdsBtnEl,
          phenoStatusEl,
          phenoExplainCardEl,
          phenoAlignmentCardEl,
          phenoExplainDetailEl,
          phenoCommandEl,
          phenoFilesEl,
          phenoResultEmptyStateEl,
          phenoResultWorkspaceEl,
          phenoOutputDetailsEl,
          phenoOutputPreviewEl,
          phenoAlignmentDetailEl,
          phenoLogsEl,
          phenoPreviewsEl,
          analysisSelectedPatientIdsEl,
          analysisPromptEl,
          analysisStatusEl,
        },
        constants: {
          PHENO_BUCKET_STYLES,
          PHENO_COHORT_COLORS,
        },
        helpers: {
          escapeHtml,
          renderActivityCard,
          fallbackCopyText,
          renderQueryReply,
          nextFrame,
        },
        callbacks: {
          setActiveTab,
          renderGlobalContext,
          renderAnalysisScopeSummary,
          syncCurrentAnalysisSessionFromUi,
          startPhenoPlanProgressUpdates,
          stopPhenoPlanProgressUpdates,
          startPhenoRunProgressUpdates,
          stopPhenoRunProgressUpdates,
          getSelectedSavedCohortIds: () => phenoSelectedSavedCohortIds.slice(),
          getCurrentScopeIds,
          onPatientIdsLoaded: (ids) => { phenoRankerPatientIds = ids.slice(); },
          onReferenceFilesLoaded: (files) => { phenoReferenceFiles = files.slice(); },
        },
      });

      async function loadPhenoRankerPatientIds() {
        await phenoUi.loadPhenoRankerPatientIds();
      }

      function updatePhenoMode() {
        phenoUi.updatePhenoMode();
      }

      function updatePhenoExplainActions() {
        phenoUi.updatePhenoExplainActions();
      }

      function updatePhenoResultActions() {
        phenoUi.updatePhenoResultActions();
      }

      function updatePhenoRunAvailability() {
        phenoUi.updatePhenoRunAvailability();
      }

      function setPhenoResultWorkspaceVisible(visible) {
        phenoUi.setPhenoResultWorkspaceVisible(visible);
      }

      function resetPhenoRunWorkspace() {
        phenoUi.resetPhenoRunWorkspace();
      }

      function markPhenoManualOverride() {
        phenoUi.markPhenoManualOverride();
      }

      function clearPhenoManualOverrides() {
        phenoUi.setPhenoManualOverrides(false);
      }

      async function planPhenoRanker() {
        await phenoUi.planPhenoRanker();
      }

      async function planAndRunPhenoRanker() {
        await phenoUi.planAndRunPhenoRanker();
      }

      async function runPhenoRanker(usePromptPlanner = true) {
        await phenoUi.runPhenoRanker(usePromptPlanner);
      }

      async function copyPhenoMatchIds() {
        await phenoUi.copyPhenoMatchIds();
      }

      function sendPhenoMatchesToAnalysis() {
        phenoUi.sendPhenoMatchesToAnalysis();
      }

      async function explainPhenoResults() {
        await phenoUi.explainPhenoResults();
      }

      async function explainPhenoResultsWithLlm() {
        await phenoUi.explainPhenoResultsWithLlm();
      }

      async function loadPhenoAlignment(referenceId, targetId) {
        await phenoUi.loadPhenoAlignment(referenceId, targetId);
      }

      function renderPhenoAlignmentPlaceholder(message) {
        phenoUi.renderPhenoAlignmentPlaceholder(message);
      }

      function renderPhenoExplainPlaceholder(message) {
        phenoUi.renderPhenoExplainPlaceholder(message);
      }

      async function loadPatients(options = {}) {
        const { respectAdminGate = true } = options;
        if (loadInFlight) {
          return;
        }
        if (respectAdminGate && !canManageDataset()) {
          updateLoadButtonAvailability();
          return;
        }
        loadInFlight = true;
        renderGlobalContext();
        updateLoadButtonAvailability();
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Loading patients and dashboard...";
        await nextFrame();

        try {
          const dataDir = encodeURIComponent(dataDirEl.value.trim());
          prepareAnalysisSessionForDataDir(dataDirEl.value.trim());
          resetQueryWorkspace();
          await loadSavedCohorts();
          await loadQueryDiseaseOptions();
          await loadMolecularDatasets();
          await loadPhenoRankerPatientIds();
          const patientResponse = await fetch(`/patients?data_dir=${dataDir}`);
          if (!patientResponse.ok) {
            const error = await patientResponse.json();
            patientsEl.innerHTML = `<div class="empty">${error.detail}</div>`;
            detailEl.innerHTML = '<div class="empty">Fix the data directory and try again.</div>';
            dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
            dashboardSummaryState = null;
            loadStatusEl.className = "load-status";
            loadStatusEl.textContent = "Load failed.";
            renderGlobalContext();
            return;
          }

          const patients = await patientResponse.json();
          currentPatients = patients;
          if (!patients.length) {
            selectedPatientId = null;
            patientsEl.innerHTML = '<div class="empty">No patient records found in the selected directory.</div>';
            detailEl.innerHTML = '<div class="empty">No timeline to display.</div>';
            dashboardEl.innerHTML = '<div class="empty">No dashboard to display.</div>';
            dashboardSummaryState = null;
            loadStatusEl.className = "load-status";
            loadStatusEl.textContent = "No patients found.";
            renderGlobalContext();
            return;
          }

          renderPatientList(filterPatients(patientSearchEl.value));
          selectedPatientId = null;
          detailEl.innerHTML = '<div class="empty">Select a patient to inspect the patient workspace.</div>';
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = `Loaded ${patients.length} patients.`;
          renderGlobalContext();

          dashboardEl.innerHTML = '<div class="empty">Loading dashboard...</div>';
          window.setTimeout(() => {
            fetch(`/dashboard?data_dir=${dataDir}`)
            .then(async (response) => {
              if (!response.ok) {
                dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
                dashboardSummaryState = null;
                renderGlobalContext();
                return;
              }
              dashboardSummaryState = await response.json();
              renderDashboard(dashboardSummaryState);
              renderGlobalContext();
            })
            .catch(() => {
              dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
              dashboardSummaryState = null;
              renderGlobalContext();
            });
          }, 0);
        } catch (error) {
          patientsEl.innerHTML = '<div class="empty">Unable to load patients.</div>';
          detailEl.innerHTML = '<div class="empty">Patient workspace unavailable.</div>';
          dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
          dashboardSummaryState = null;
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = error && error.message ? error.message : "Load failed.";
          renderGlobalContext();
        } finally {
          loadInFlight = false;
          updateLoadButtonAvailability();
        }
      }

      function filterPatients(query) {
        const value = (query || "").trim().toLowerCase();
        if (!value) return currentPatients;
        return currentPatients.filter((patient) => patient.patient_id.toLowerCase().includes(value));
      }

      async function loadPatient(patientId) {
        selectedPatientId = patientId;
        const dataDir = encodeURIComponent(dataDirEl.value.trim());
        const response = await fetch(`/patients/${patientId}/navigator?data_dir=${dataDir}`);
        if (!response.ok) {
          const error = await response.json();
          detailEl.innerHTML = `<div class="empty">${error.detail}</div>`;
          return;
        }
        const patient = await response.json();
        renderDetail(patient);
        renderPatientList(filterPatients(patientSearchEl.value));
      }

      loadBtnEl.addEventListener("click", () => loadPatients({ respectAdminGate: true }));
      authLoginBtnEl && authLoginBtnEl.addEventListener("click", loginLocal);
      heroLogoutBtnEl && heroLogoutBtnEl.addEventListener("click", logoutLocal);
      authPasswordEl && authPasswordEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          loginLocal();
        }
      });
      askBtnEl.addEventListener("click", askQuery);
      queryPlannerBtnEl && queryPlannerBtnEl.addEventListener("click", () => {
        queryExecutionMode = queryExecutionMode === "planner_only" ? "auto" : "planner_only";
        renderQueryExecutionMode();
      });
      queryDiseaseBuilderBtnEl && queryDiseaseBuilderBtnEl.addEventListener("click", () => {
        const willOpen = !queryDiseasePanelEl || queryDiseasePanelEl.classList.contains("is-hidden");
        if (queryDiseasePanelEl) queryDiseasePanelEl.classList.toggle("is-hidden", !willOpen);
        queryDiseaseBuilderBtnEl.classList.toggle("is-active", willOpen);
      });
      queryClearBtnEl && queryClearBtnEl.addEventListener("click", () => {
        resetQueryWorkspace();
        if (queryDiseasePanelEl) queryDiseasePanelEl.classList.add("is-hidden");
        queryDiseaseBuilderBtnEl && queryDiseaseBuilderBtnEl.classList.remove("is-active");
        queryStatusEl.className = "query-status";
        queryStatusEl.textContent = "Query thread cleared.";
      });
      analysisRunBtnEl.addEventListener("click", runAnalysis);
      analysisComposerExamplesBtnEl && analysisComposerExamplesBtnEl.addEventListener("click", () => {
        analysisExamplesPinnedOpen = true;
        renderAnalysisStarterPrompts();
        if (analysisStarterPanelEl && !analysisStarterPanelEl.hidden) {
          analysisStarterPanelEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
      analysisNewSessionBtnEl && analysisNewSessionBtnEl.addEventListener("click", () => {
        createAndSelectAnalysisSession({ dataDir: dataDirEl.value.trim() });
      });
      dashboardTabBtnEl.addEventListener("click", () => setActiveTab("dashboard"));
      dataTabBtnEl && dataTabBtnEl.addEventListener("click", () => setActiveTab("data"));
      usersTabBtnEl && usersTabBtnEl.addEventListener("click", () => {
        setActiveTab("users");
        void loadAuthUsers();
      });
      queryTabBtnEl.addEventListener("click", () => setActiveTab("query"));
      analysisTabBtnEl.addEventListener("click", () => setActiveTab("analysis"));
      phenoTabBtnEl.addEventListener("click", () => setActiveTab("pheno"));
      dashboardClinicalBtnEl && dashboardClinicalBtnEl.addEventListener("click", () => setDashboardSubtab("clinical"));
      dashboardMolecularBtnEl && dashboardMolecularBtnEl.addEventListener("click", () => setDashboardSubtab("molecular"));
      phenoPlanBtnEl.addEventListener("click", planPhenoRanker);
      phenoPlanRunBtnEl.addEventListener("click", planAndRunPhenoRanker);
      phenoRunBtnEl.addEventListener("click", runPhenoRanker);
      phenoAnalysisBtnEl.addEventListener("click", sendPhenoMatchesToAnalysis);
      phenoCopyIdsBtnEl.addEventListener("click", copyPhenoMatchIds);
      phenoExplainBtnEl.addEventListener("click", explainPhenoResults);
      phenoExplainLlmBtnEl.addEventListener("click", explainPhenoResultsWithLlm);
      phenoModeEl.addEventListener("change", () => {
        markPhenoManualOverride();
        updatePhenoMode();
      });
      phenoActionEl.addEventListener("change", () => {
        markPhenoManualOverride();
        updatePhenoMode();
      });
      updatePhenoExplainActions();
      updatePhenoResultActions();
      updatePhenoRunAvailability();
      phenoSelectedPatientIdsEl.addEventListener("input", () => {
        markPhenoManualOverride();
        renderSelectedPatientIdsSummary();
      });
      [
        phenoPatientIdEl,
        phenoIncludeTermsEl,
        phenoExcludeTermsEl,
        phenoSimilarityMetricEl,
        phenoSortByEl,
        phenoMaxOutEl,
      ].forEach((element) => {
        element && element.addEventListener("input", markPhenoManualOverride);
      });
      [
        phenoAlignEl,
        phenoRenderHeatmapEl,
        phenoRenderMdsEl,
      ].forEach((element) => {
        element && element.addEventListener("change", markPhenoManualOverride);
      });
      analysisSelectedPatientIdsEl.addEventListener("input", renderAnalysisScopeSummary);
      analysisCompareModeEl && analysisCompareModeEl.addEventListener("change", renderAnalysisCompareMode);
      analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.addEventListener("input", renderAnalysisCompareScopeSummary);
      analysisPromptEl.addEventListener("input", () => syncCurrentAnalysisSessionFromUi({ render: true }));
      analysisMolecularDatasetListEl && analysisMolecularDatasetListEl.addEventListener("change", (event) => {
        const checkbox = event.target.closest('input[type="checkbox"]');
        if (!checkbox) {
          return;
        }
        dashboardUi.handleMolecularDatasetSelectionChange();
      });
      analysisMolecularGeneEl && analysisMolecularGeneEl.addEventListener("input", () => {
        dashboardUi.handleMolecularGeneInput();
      });
      analysisMolecularRunBtnEl && analysisMolecularRunBtnEl.addEventListener("click", runMolecularExpressionAnalysis);
      initializeExampleToggle(queryExamplesEl);
      initializeExampleToggle(phenoExamplesEl);
      initializeExampleToggle(analysisExamplesEl);
      renderQueryStarterPrompts();
      renderAnalysisStarterPrompts();
      setDashboardSubtab(currentDashboardSubtab);
      try {
        const savedTab = window.localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
        const savedDashboardSubtab = window.localStorage.getItem(DASHBOARD_SUBTAB_STORAGE_KEY);
        if (savedDashboardSubtab && ["clinical", "molecular"].includes(savedDashboardSubtab)) {
          setDashboardSubtab(savedDashboardSubtab);
        }
        if (savedTab && ["dashboard", "cohort", "molecular", "data", "users", "query", "analysis", "pheno"].includes(savedTab)) {
          if (savedTab === "cohort") {
            setDashboardSubtab("clinical");
            setActiveTab("dashboard");
          } else if (savedTab === "molecular") {
            setDashboardSubtab("molecular");
            setActiveTab("dashboard");
          } else if ((savedTab === "data" || savedTab === "users") && authState.enabled && !canManageDataset()) {
            setActiveTab("dashboard");
          } else {
            setActiveTab(savedTab);
          }
        }
      } catch (_error) {
      }
      window.__patientNavigatorLoadPatients = loadPatients;
      window.__patientNavigatorAskQuery = askQuery;
      patientsEl.addEventListener("click", (event) => {
        const card = event.target.closest(".patient-card");
        if (!card || !patientsEl.contains(card)) {
          return;
        }
        loadPatient(card.dataset.patientId);
      });
      queryExamplesEl.addEventListener("click", (event) => {
        queryUi.handleQueryExamplesClick(event);
      });
      queryFollowupsEl.addEventListener("click", (event) => {
        queryUi.handleQueryFollowupsClick(event);
      });
      analysisExamplesEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-analysis-prompt]");
        if (!button || !analysisExamplesEl.contains(button)) {
          return;
        }
        analysisPromptEl.value = button.dataset.analysisPrompt;
        if (button.dataset.analysisLlmOnly === "true") {
          analysisExecutionMode = "llm_only";
        } else if (button.dataset.analysisDeterministic === "true") {
          analysisExecutionMode = "deterministic";
        } else {
          analysisExecutionMode = "auto";
        }
        analysisExamplesPinnedOpen = false;
        syncCurrentAnalysisSessionFromUi({ render: true });
        renderAnalysisStarterPrompts();
        analysisPromptEl.focus();
      });
      analysisPromptEl && analysisPromptEl.addEventListener("input", () => {
        analysisExecutionMode = "auto";
      });
      analysisSessionListEl && analysisSessionListEl.addEventListener("click", (event) => {
        const deleteButton = event.target.closest("[data-analysis-session-delete]");
        if (deleteButton && analysisSessionListEl.contains(deleteButton)) {
          deleteAnalysisSessionById(deleteButton.dataset.analysisSessionDelete || "");
          return;
        }
        const renameButton = event.target.closest("[data-analysis-session-rename]");
        if (renameButton && analysisSessionListEl.contains(renameButton)) {
          renameAnalysisSession(renameButton.dataset.analysisSessionRename || "");
          return;
        }
        const button = event.target.closest("[data-analysis-session-id]");
        if (!button || !analysisSessionListEl.contains(button)) {
          return;
        }
        selectAnalysisSession(button.dataset.analysisSessionId || "");
      });
      phenoExamplesEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-pheno-prompt]");
        if (!button || !phenoExamplesEl.contains(button)) {
          return;
        }
        phenoPromptEl.value = button.dataset.phenoPrompt;
        clearPhenoManualOverrides();
        updatePhenoRunAvailability();
        phenoPromptEl.focus();
      });
      phenoPromptEl.addEventListener("input", () => {
        clearPhenoManualOverrides();
        updatePhenoRunAvailability();
      });
      phenoPreviewsEl.addEventListener("click", (event) => {
        phenoUi.handlePreviewsClick(event);
      });
      document.addEventListener("click", (event) => {
        queryUi.handleDocumentClick(event);
      });
      savedCohortsEl && savedCohortsEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-saved-cohort-action]");
        if (!button || !savedCohortsEl.contains(button)) {
          return;
        }
        handleSavedCohortAction(button);
      });
      analysisSelectedSavedCohortSelectionEl && analysisSelectedSavedCohortSelectionEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-analysis-clear-saved-cohort]");
        if (!button || !analysisSelectedSavedCohortSelectionEl.contains(button)) {
          return;
        }
        savedCohortsUi.clearSavedCohortFromAnalysis("a");
      });
      analysisCompareSavedCohortSelectionEl && analysisCompareSavedCohortSelectionEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-analysis-clear-saved-cohort]");
        if (!button || !analysisCompareSavedCohortSelectionEl.contains(button)) {
          return;
        }
        savedCohortsUi.clearSavedCohortFromAnalysis("b");
      });
      phenoSavedCohortsEl && phenoSavedCohortsEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-saved-cohort-action]");
        if (!button || !phenoSavedCohortsEl.contains(button)) {
          return;
        }
        handleSavedCohortAction(button);
      });
      phenoSavedCohortsSelectionEl && phenoSavedCohortsSelectionEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-pheno-selected-cohort-id]");
        if (!button || !phenoSavedCohortsSelectionEl.contains(button)) {
          return;
        }
        removeSavedCohortFromPheno(button.dataset.phenoSelectedCohortId || "");
      });
      phenoOutputPreviewEl.addEventListener("click", (event) => {
        phenoUi.handleOutputPreviewClick(event);
      });
      questionEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          askQuery();
        }
      });
      questionEl.addEventListener("input", () => {
        renderQueryExecutionMode();
      });
      analysisPromptEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          runAnalysis();
        }
      });
      patientSearchEl.addEventListener("input", () => renderPatientList(filterPatients(patientSearchEl.value)));
      updatePhenoMode();
      renderSelectedPatientIdsSummary();
      renderQueryExecutionMode();
      setPhenoResultWorkspaceVisible(false);
      renderPhenoSavedCohortsSelection();
      ensureAnalysisSessionsLoaded();
      void loadAnalysisSessionsFromBackend();
      renderAnalysisCompareMode();
      renderAnalysisCompareScopeSummary();
      loadLmStatus();
      void fetchAuthStatus().then(async () => {
        if (!isWorkspaceAccessible()) {
          clearLoadedWorkspaceForSignedOutState();
          return;
        }
        await refreshUserWorkspaceState();
        await loadPatients({ respectAdminGate: false });
      });
      renderGlobalContext();
      renderPhenoAlignmentPlaceholder("Run patient mode, then click one row in rank.txt to inspect matched variables for that pair.");
      renderPhenoExplainPlaceholder("Run patient mode, then click Explain results to summarize the top matches from rank.txt.");
    
