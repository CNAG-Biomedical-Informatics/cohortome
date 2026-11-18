export function createNavigationActions(app) {
  return {
    Rail: {
      projectViewRef: { current: null },
      openHistory() {
        app.jobsUi.setRunHistoryDrawerOpen(true);
        void app.jobsUi.loadRunHistory();
      },
      openChats() {
        app.setAnalysisChatsDrawerOpen(true);
      },
      logout() {
        void app.authUi.logoutLocal();
      },
      settings() {
        app.userSettingsUi.renderUserSettingsForm();
        app.userSettingsUi.setPanelOpen(true);
      },
    },
    JobsDrawer: {
      jobsDrawerCloseBtnClick() {
        app.jobsUi.setJobsDrawerOpen(false);
      },
      jobsDrawerClick(event) {
        const closeTrigger = event.target.closest(
          "[data-jobs-drawer-close='true']",
        );
        if (closeTrigger && app.refs.jobsDrawerEl.contains(closeTrigger)) {
          app.jobsUi.setJobsDrawerOpen(false);
          return;
        }
        const deleteButton = event.target.closest("[data-job-delete]");
        if (deleteButton && app.refs.jobsDrawerEl.contains(deleteButton)) {
          void app.jobsUi
            .deleteJob(deleteButton.dataset.jobDelete || "")
            .catch((error) => {
              app.refs.jobsDrawerStatusEl.textContent =
                error && error.message
                  ? error.message
                  : "Unable to delete job.";
            });
          return;
        }
        const openButton = event.target.closest(
          "[data-job-open-result], [data-job-open-pheno]",
        );
        if (!openButton || !app.refs.jobsDrawerEl.contains(openButton)) {
          return;
        }
        void app.jobsUi
          .openJobResult(
            openButton.dataset.jobOpenResult ||
              openButton.dataset.jobOpenPheno ||
              "",
          )
          .catch((error) => {
            const isPheno = Boolean(openButton.dataset.jobOpenPheno);
            const statusEl = isPheno
              ? app.refs.phenoStatusEl
              : app.refs.analysisStatusEl;
            statusEl.className = "query-status";
            statusEl.textContent =
              error && error.message
                ? error.message
                : "Unable to load job result.";
          });
      },
    },
    RunHistoryDrawer: {
      openQueue() {
        app.jobsUi.setJobsDrawerOpen(true);
        void app.jobsUi.loadRecentJobs();
      },
      runHistoryDrawerCloseBtnClick() {
        app.jobsUi.setRunHistoryDrawerOpen(false);
      },
      runHistoryDeleteAllBtnClick() {
        void app.jobsUi.deleteRunHistory();
      },
      runHistoryDrawerClick(event) {
        const closeTrigger = event.target.closest(
          "[data-run-history-drawer-close='true']",
        );
        if (
          closeTrigger &&
          app.refs.runHistoryDrawerEl.contains(closeTrigger)
        ) {
          app.jobsUi.setRunHistoryDrawerOpen(false);
          return;
        }
        const deleteButton = event.target.closest("[data-run-history-delete]");
        if (
          deleteButton &&
          app.refs.runHistoryDrawerEl.contains(deleteButton)
        ) {
          void app.jobsUi
            .deleteJob(deleteButton.dataset.runHistoryDelete || "", {
              surface: "run-history",
            })
            .catch((error) => {
              app.refs.runHistoryDrawerStatusEl.textContent =
                error && error.message
                  ? error.message
                  : "Unable to delete generated run.";
            });
          return;
        }
        const openButton = event.target.closest(
          "[data-job-open-result], [data-job-open-pheno]",
        );
        if (!openButton || !app.refs.runHistoryDrawerEl.contains(openButton)) {
          return;
        }
        void app.jobsUi
          .openJobResult(
            openButton.dataset.jobOpenResult ||
              openButton.dataset.jobOpenPheno ||
              "",
          )
          .catch((error) => {
            const isPheno = Boolean(openButton.dataset.jobOpenPheno);
            const statusEl = isPheno
              ? app.refs.phenoStatusEl
              : app.refs.analysisStatusEl;
            statusEl.className = "query-status";
            statusEl.textContent =
              error && error.message
                ? error.message
                : "Unable to load generated run.";
          });
      },
    },
  };
}
