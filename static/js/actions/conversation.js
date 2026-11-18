export function createConversationActions(app) {
  return {
    ChatsDrawer: {
      selectChats: (event) => app.chatDeletionUi.selectChats(event),
      newFolder: (event) => app.chatFoldersUi.newFolder(event),
      analysisChatsDrawerCloseBtnClick() {
        app.setAnalysisChatsDrawerOpen(false);
      },
      analysisChatsDrawerClick(event) {
        const closeTrigger = event.target.closest(
          "[data-analysis-chats-close='true']",
        );
        if (
          closeTrigger &&
          app.refs.analysisChatsDrawerEl.contains(closeTrigger)
        ) {
          app.setAnalysisChatsDrawerOpen(false);
        }
      },
      analysisSessionListClick(event) {
        void app.chatFoldersUi.folderAction(event);
        app.chatDeletionUi.selectionAction(event);
        void app.querySessionsUi.chatAction(event);
        void app.phenoSessionsUi.chatAction(event);
        const deleteButton = event.target.closest(
          "[data-analysis-session-delete]",
        );
        if (
          deleteButton &&
          app.refs.analysisSessionListEl.contains(deleteButton)
        ) {
          app.analysisSessionsUi.deleteAnalysisSessionById(
            deleteButton.dataset.analysisSessionDelete || "",
          );
          return;
        }
        const renameButton = event.target.closest(
          "[data-analysis-session-rename]",
        );
        if (
          renameButton &&
          app.refs.analysisSessionListEl.contains(renameButton)
        ) {
          app.analysisSessionsUi.renameAnalysisSession(
            renameButton.dataset.analysisSessionRename || "",
          );
          return;
        }
        const button = event.target.closest("[data-analysis-session-id]");
        if (!button || !app.refs.analysisSessionListEl.contains(button)) {
          return;
        }
        app.analysisSessionsUi.selectAnalysisSession(
          button.dataset.analysisSessionId || "",
        );
        app.navigationUi.setActiveTab("analysis");
        if (
          !document
            .getElementById("analysisChatDock")
            .contains(app.refs.analysisSessionListEl)
        )
          app.setAnalysisChatsDrawerOpen(false);
      },
    },
    QueryShell: {
      retrySave: (event) => app.querySessionsUi.retrySave(event),
      queryThreadClick(event) {
        if (event.target.closest("[data-clarid-toggle], [data-clarid-copy]")) {
          void app.dashboardUi.handleClaridAction(event);
        }
      },
      queryExamplesClick(event) {
        app.queryUi.handleQueryExamplesClick(event);
      },
      queryFollowupsClick(event) {
        app.queryUi.handleQueryFollowupsClick(event);
      },
    },
    PhenoShell: {
      draftEdited: (event) => app.phenoSessionsUi.draftEdited(event),
      selectTurn: (event) => app.phenoSessionsUi.selectTurn(event),
      reloadChat: (event) => app.phenoSessionsUi.reloadChat(event),
      saveChat: (event) => app.phenoSessionsUi.saveChat(event),
      phenoAnalysisBtnClick() {
        app.phenoUi.sendPhenoMatchesToAnalysis();
      },
      phenoCopyIdsBtnClick() {
        void app.phenoUi.copyPhenoMatchIds();
      },
      phenoExplainBtnClick() {
        void app.phenoUi.explainPhenoResults();
      },
      phenoExplainLlmBtnClick() {
        void app.phenoUi.explainPhenoResultsWithLlm();
      },
      phenoPreviewsClick(event) {
        app.phenoUi.handlePreviewsClick(event);
      },
      phenoOutputPreviewClick(event) {
        app.phenoUi.handleOutputPreviewClick(event);
      },
    },
    PhenoSetup: {
      manualEdit: () => app.phenoUi.markPhenoManualOverride(),
      graphOptionChanged() {
        app.phenoUi.markPhenoManualOverride();
        app.phenoUi.updatePhenoGraphOptions();
      },
      phenoPlanBtnClick() {
        void app.phenoUi.planPhenoRanker();
      },
      phenoModeChange() {
        app.phenoUi.updatePhenoMode();
        app.phenoUi.markPhenoManualOverride();
        app.phenoUi.updatePhenoRunAvailability();
      },
      phenoActionChange() {
        app.phenoUi.markPhenoManualOverride();
        app.phenoUi.updatePhenoMode();
        app.phenoUi.updatePhenoRunAvailability();
      },
      phenoSelectedPatientIdsInput() {
        app.state.phenoQuerySelection = null;
        app.phenoUi.markPhenoManualOverride();
        app.phenoUi.renderSelectedPatientIdsSummary();
        app.phenoUi.updatePhenoRunAvailability();
      },
      phenoSimilarityMetricInput() {
        app.phenoUi.markPhenoManualOverride();
        app.phenoUi.updatePhenoGraphOptions();
      },
      phenoSimilarityMetricChange() {
        app.phenoUi.updatePhenoGraphOptions();
      },
      phenoPlanFollowupsClick(event) {
        app.phenoUi.handlePhenoPlanFollowUpsClick(event);
      },
      phenoSavedCohortsClick(event) {
        const button = event.target.closest("[data-saved-cohort-action]");
        if (!button || !app.refs.phenoSavedCohortsEl.contains(button)) {
          return;
        }
        app.savedCohortsUi.handleSavedCohortAction(button);
      },
      phenoSavedCohortsSelectionClick(event) {
        const button = event.target.closest("[data-pheno-selected-cohort-id]");
        if (
          !button ||
          !app.refs.phenoSavedCohortsSelectionEl.contains(button)
        ) {
          return;
        }
        app.savedCohortsUi.removeSavedCohortFromPheno(
          button.dataset.phenoSelectedCohortId || "",
        );
      },
    },
  };
}
