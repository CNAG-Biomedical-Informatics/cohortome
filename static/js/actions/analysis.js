export function createAnalysisActions(app) {
  return {
    AnalysisShell: {
      analysisFlowBarClick(event) {
        const button = event.target.closest("[data-analysis-flow-target]");
        if (!button || !app.refs.analysisFlowBarEl.contains(button)) {
          return;
        }
        const target = String(button.dataset.analysisFlowTarget || "");
        if (target !== "results") app.analysisUi.openAnalysisSetup();
        if (target === "scope") {
          const setup = document.querySelector(
            "#analysisTab .analysis-setup-card",
          );
          if (setup) {
            setup.open = true;
            setup.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        } else if (
          target === "analysis" ||
          target === "choose" ||
          target === "setup" ||
          target === "catalog"
        ) {
          document.getElementById("analysisMethodSelect").focus();
          document
            .getElementById("analysisMethodPicker")
            .scrollIntoView({ block: "center" });
        } else if (target === "prompt") {
          document.getElementById("analysisRequestDetails").open = true;
          app.refs.analysisPromptEl && app.refs.analysisPromptEl.focus();
          app.refs.analysisPromptEl &&
            app.refs.analysisPromptEl.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
        } else if (target === "requirements") {
          if (
            document.getElementById("analysisMethodSelect").value ===
            "association"
          ) {
            const panel = document.getElementById(
              "analysisMeasurementComparison",
            );
            panel.open = true;
            panel.scrollIntoView({ block: "center" });
            document.getElementById("associationAssayX").focus();
          } else if (app.state.analysisSelectedCatalogItemId) {
            app.analysisCatalogUi.focusFirstIncompleteAnalysisSetup();
            app.refs.analysisCatalogAssayPanelEl.scrollIntoView({
              block: "center",
            });
          } else {
            document
              .getElementById("analysisMethodDescription")
              .scrollIntoView({ block: "center" });
          }
        } else if (target === "run") {
          app.refs.analysisPromptEl && app.refs.analysisPromptEl.focus();
          app.refs.analysisPromptEl &&
            app.refs.analysisPromptEl.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
        } else if (target === "results") {
          app.refs.analysisThreadEl &&
            app.refs.analysisThreadEl.scrollIntoView({
              behavior: "smooth",
              block: "start",
            });
        }
      },
      analysisThreadClick(event) {
        app.analysisUi.handleAnalysisResultBoardClick(event);
        app.analysisUi.handleAnalysisPlotViewClick(event);
        app.analysisUi.handleAnalysisFollowUpsClick(event);
      },
    },
    AnalysisComposer: {
      chooseMethod: (event) =>
        app.analysisCatalogUi.chooseMethod(event.target.value),
      measurementChanged: () => app.analysisCatalogUi.renderAnalysisFlowBar(),
      analysisComposerExamplesBtnClick() {
        app.state.analysisExamplesPinnedOpen = true;
        app.analysisCatalogUi.renderAnalysisStarterPrompts();
        if (
          app.refs.analysisStarterPanelEl &&
          !app.refs.analysisStarterPanelEl.hidden
        ) {
          app.refs.analysisStarterPanelEl.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }
      },
      analysisContextWorkspaceBtnClick() {
        app.analysisUi.setContextMode("workspace");
      },
      analysisContextGeneralBtnClick() {
        app.analysisUi.setContextMode("general");
      },
      analysisCatalogAssayPanelClick(event) {
        const button = event.target.closest("[data-analysis-setup-action]");
        if (!button || !app.refs.analysisCatalogAssayPanelEl.contains(button))
          return;
        void app.analysisCatalogUi.handleAnalysisSetupAction(
          button.dataset.analysisSetupAction || "",
        );
      },
      analysisCatalogListClick(event) {
        const button = event.target.closest("[data-analysis-catalog-id]");
        if (!button || !app.refs.analysisCatalogListEl.contains(button)) {
          return;
        }
        app.analysisCatalogUi.applyAnalysisCatalogItemById(
          button.dataset.analysisCatalogId || "",
        );
      },
      analysisCatalogBrowseBtnClick() {
        app.analysisCatalogUi.setAnalysisCatalogDrawerOpen(true);
      },
    },
    PatientScopeSetup: {
      example(event) {
        const button = event.target.closest("[data-analysis-prompt]");
        if (!button || !app.refs.analysisExamplesEl.contains(button)) {
          return;
        }
        app.refs.analysisPromptEl.value = button.dataset.analysisPrompt || "";
        app.analysisUi.setContextMode("workspace");
        app.state.analysisExecutionMode =
          button.dataset.analysisLlmOnly === "true"
            ? "llm_only"
            : button.dataset.analysisDeterministic === "true"
              ? "deterministic"
              : "planner_only";
        app.state.analysisSelectedCatalogItemId = "";
        app.analysisCatalogUi.renderAnalysisCatalogAssayPanel();
        app.state.analysisExamplesPinnedOpen = false;
        app.analysisSessionsUi.syncCurrentAnalysisSessionFromUi({
          render: true,
        });
        app.analysisCatalogUi.renderAnalysisStarterPrompts();
        if (
          (app.state.analysisExecutionMode === "planner_only" ||
            app.state.analysisExecutionMode === "llm_only") &&
          (!app.state.lmStatus || app.state.lmStatus.available !== true)
        ) {
          app.refs.analysisStatusEl.className = "query-status";
          app.refs.analysisStatusEl.textContent =
            app.state.analysisExecutionMode === "planner_only"
              ? "LLM planner unavailable. Start an LLM model or choose a deterministic analysis."
              : "LLM unavailable. Start an LLM model or choose a deterministic analysis.";
        }
        app.refs.analysisPromptEl.focus();
      },
      analysisSelectedPatientIdsInput() {
        const ids = app.refs.analysisSelectedPatientIdsEl.value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        const hasSampleIds = ids.some((item) => item.includes(":"));
        app.setAnalysisScopeMetadataFromSelection({
          sampleIds: hasSampleIds ? ids : [],
          patientIds: hasSampleIds ? [] : ids,
          idType: hasSampleIds ? "sample" : "patient",
          sourceKind: "manual",
          sourcePrompt: "Manual Analysis scope",
        });
        app.dashboardUi.renderAnalysisScopeSummary();
        app.analysisCatalogUi.renderAnalysisCatalog();
      },
      analysisCompareModeChange() {
        app.analysisUi.renderAnalysisCompareMode();
        app.analysisCatalogUi.renderAnalysisCatalog();
      },
      analysisCompareSelectedPatientIdsInput() {
        const ids = app.refs.analysisCompareSelectedPatientIdsEl.value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        const hasSampleIds = ids.some((item) => item.includes(":"));
        app.setAnalysisScopeMetadataFromSelection({
          side: "b",
          sampleIds: hasSampleIds ? ids : [],
          patientIds: hasSampleIds ? [] : ids,
          idType: hasSampleIds ? "sample" : "patient",
          sourceKind: "manual",
          sourcePrompt: "Manual Analysis Cohort B scope",
        });
        app.dashboardUi.renderAnalysisCompareScopeSummary();
        app.analysisCatalogUi.renderAnalysisCatalog();
      },
      savedCohortsClick(event) {
        const button = event.target.closest("[data-saved-cohort-action]");
        if (!button || !app.refs.savedCohortsEl.contains(button)) {
          return;
        }
        app.savedCohortsUi.handleSavedCohortAction(button);
      },
      analysisSelectedSavedCohortSelectionClick(event) {
        const button = event.target.closest(
          "[data-analysis-clear-saved-cohort]",
        );
        if (
          !button ||
          !app.refs.analysisSelectedSavedCohortSelectionEl.contains(button)
        ) {
          return;
        }
        app.savedCohortsUi.clearSavedCohortFromAnalysis("a");
        app.analysisCatalogUi.renderAnalysisCatalog();
      },
      analysisCompareSavedCohortSelectionClick(event) {
        const button = event.target.closest(
          "[data-analysis-clear-saved-cohort]",
        );
        if (
          !button ||
          !app.refs.analysisCompareSavedCohortSelectionEl.contains(button)
        ) {
          return;
        }
        app.savedCohortsUi.clearSavedCohortFromAnalysis("b");
        app.analysisCatalogUi.renderAnalysisCatalog();
      },
    },
    CatalogueDrawer: {
      analysisCatalogDrawerListClick(event) {
        const button = event.target.closest("[data-analysis-catalog-id]");
        if (!button || !app.refs.analysisCatalogDrawerListEl.contains(button)) {
          return;
        }
        app.analysisCatalogUi.applyAnalysisCatalogItemById(
          button.dataset.analysisCatalogId || "",
        );
      },
      analysisCatalogDrawerSearchInput() {
        app.analysisCatalogUi.setAnalysisCatalogSearch(
          app.refs.analysisCatalogDrawerSearchEl.value || "",
        );
      },
      analysisCatalogDrawerFiltersClick(event) {
        const button = event.target.closest("[data-analysis-catalog-filter]");
        if (
          !button ||
          !app.refs.analysisCatalogDrawerFiltersEl.contains(button)
        ) {
          return;
        }
        app.analysisCatalogUi.setAnalysisCatalogFilter(
          button.dataset.analysisCatalogFilter || "all",
        );
      },
      analysisCatalogDrawerCloseBtnClick() {
        app.analysisCatalogUi.setAnalysisCatalogDrawerOpen(false);
      },
      analysisCatalogDrawerClick(event) {
        const trigger = event.target.closest(
          "[data-analysis-catalog-close='true']",
        );
        if (!trigger || !app.refs.analysisCatalogDrawerEl.contains(trigger)) {
          return;
        }
        app.analysisCatalogUi.setAnalysisCatalogDrawerOpen(false);
      },
    },
  };
}
