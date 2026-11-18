export function createWorkspaceActions(app) {
  return {
    DatasetsShell: {
      dataDirChange() {
        app.state.pendingDatasetIds = app.datasetsUi.selectedDatasetIdsFromUi();
        app.datasetsUi.renderDatasetPicker();
        app.datasetsUi.renderDatasetAdminList();
        app.datasetsUi.renderDatasetScopeSummary();
        app.datasetsUi.renderLoadButtonState();
        app.authUi.updateLoadButtonAvailability();
      },
      loadBtnClick() {
        void app.workspaceUi.loadPatients({ respectAdminGate: true });
      },
    },
    CohortsShell: {
      chooseLibraryAction: (event) =>
        app.savedCohortsUi.library.chooseLibraryAction(event),
      keyLibrary: (event) => app.savedCohortsUi.library.keyLibrary(event),
      refreshLibrary: (event) =>
        app.savedCohortsUi.library.refreshLibrary(event),
      pageLibrary: (event) => app.savedCohortsUi.library.pageLibrary(event),
      searchLibrary: (event) => app.savedCohortsUi.library.searchLibrary(event),
    },
    DashboardShell: {
      compareMeasurements() {
        document.getElementById("multimodalMoreOptions").open = false;
        app.navigationUi.setActiveTab("analysis");
        app.analysisUi.setContextMode("workspace");
        const method = document.getElementById("analysisMethodSelect");
        if (method.value !== "association") {
          app.analysisCatalogUi.chooseMethod("association");
        }
        const panel = document.getElementById("analysisMeasurementComparison");
        panel.open = true;
        panel.scrollIntoView({ block: "center" });
        document.getElementById("associationAssayX").focus();
      },
      assayModalityTabsClick(event) {
        const button = event.target.closest("[data-assay-modality-filter]");
        if (!button || !app.refs.assayModalityTabsEl.contains(button)) {
          return;
        }
        app.dashboardUi.handleAssayModalityFilter(
          button.dataset.assayModalityFilter || "all",
        );
      },
      analysisAssayGeneInput() {
        app.dashboardUi.handleAssayFeatureInput();
      },
      analysisAssayRunBtnClick() {
        void app.dashboardUi.runAssayExpressionAnalysis();
      },
      detailClick(event) {
        if (event.target.closest("[data-clarid-toggle], [data-clarid-copy]")) {
          void app.dashboardUi.handleClaridAction(event);
        }
      },
    },
  };
}
