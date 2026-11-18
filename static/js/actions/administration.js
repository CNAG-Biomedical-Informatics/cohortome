export function createAdministrationActions(app) {
  return {
    DataManagementShell: {
      useDataset: (event) => app.datasetsUi.resourceInstaller.useDataset(event),
      cancelInstall: (event) =>
        app.datasetsUi.resourceInstaller.cancelInstall(event),
      importArchive: (event) =>
        app.datasetsUi.resourceInstaller.importArchive(event),
      downloadResource: (event) =>
        app.datasetsUi.resourceInstaller.downloadResource(event),
      refreshResources: (event) =>
        app.datasetsUi.resourceInstaller.refreshResources(event),
      pickArchive: (event) =>
        app.datasetsUi.resourceInstaller.pickArchive(event),
      closedResources: (event) =>
        app.datasetsUi.resourceInstaller.closedResources(event),
      closeResources: (event) =>
        app.datasetsUi.resourceInstaller.closeResources(event),
      openResources: (event) =>
        app.datasetsUi.resourceInstaller.openResources(event),
      filterResources: (event) =>
        app.datasetsUi.resourceInstaller.filterResources(event),
      datasetAdminListClick(event) {
        const removeButton = event.target.closest("[data-dataset-remove]");
        if (
          removeButton &&
          app.refs.datasetAdminListEl.contains(removeButton)
        ) {
          event.preventDefault();
          app.datasetsUi.removeDataset(removeButton.dataset.datasetRemove);
          return;
        }
        const button = event.target.closest("[data-dataset-save]");
        if (!button || !app.refs.datasetAdminListEl.contains(button)) {
          const prepareButton = event.target.closest("[data-dataset-prepare]");
          if (
            !prepareButton ||
            !app.refs.datasetAdminListEl.contains(prepareButton)
          ) {
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          void app.datasetsUi.prepareDatasetStore(
            prepareButton.getAttribute("data-dataset-prepare") || "",
          );
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        void app.datasetsUi.saveDatasetAccess(
          button.getAttribute("data-dataset-save") || "",
        );
      },
    },
    SettingsPanel: {
      edited: () => app.userSettingsUi.updateDirtyStatus(),
      aboutToggled: () => app.userSettingsUi.loadAboutWhenOpen(),
      userSettingsCloseBtnClick() {
        app.userSettingsUi.setPanelOpen(false);
      },
      userSettingsSaveBtnClick() {
        void app.userSettingsUi.saveUserSettings().catch((error) => {
          if (app.refs.userSettingsStatusEl) {
            app.refs.userSettingsStatusEl.className = "section-note is-warning";
            app.refs.userSettingsStatusEl.textContent =
              error && error.message
                ? error.message
                : "Unable to save user settings.";
          }
        });
      },
      userSettingsResetBtnClick() {
        void app.userSettingsUi.resetUserSettings().catch((error) => {
          if (app.refs.userSettingsStatusEl) {
            app.refs.userSettingsStatusEl.className = "section-note is-warning";
            app.refs.userSettingsStatusEl.textContent =
              error && error.message
                ? error.message
                : "Unable to reset user settings.";
          }
        });
      },
      userDeleteChatsBtnClick() {
        app.chatDeletionUi.open();
      },
      userDeleteJobsBtnClick() {
        void app.userSettingsUi.deleteUserData("jobs");
      },
      userDeleteCohortsBtnClick() {
        void app.userSettingsUi.deleteUserData("cohorts");
      },
    },
    AuthPanel: {
      authLoginBtnClick() {
        void app.authUi.loginLocal();
      },
      authOidcLoginBtnClick() {
        app.authUi.loginOidc();
      },
      authForgotPasswordBtnClick() {
        app.authUi.setPasswordResetPanelOpen(true, "request");
      },
      authPasswordResetRequestBtnClick() {
        void app.authUi.requestPasswordReset();
      },
      authPasswordResetCancelBtnClick() {
        app.authUi.setPasswordResetPanelOpen(false);
      },
      authPasswordResetConfirmBtnClick() {
        void app.authUi.confirmPasswordReset();
      },
      authPasswordResetConfirmCancelBtnClick() {
        app.authUi.clearPasswordResetTokenFromLocation();
        app.authUi.setPasswordResetPanelOpen(false);
      },
      authPasswordKeyDown(event) {
        if (event.key === "Enter") {
          event.preventDefault();
          void app.authUi.loginLocal();
        }
      },
      authPasswordResetIdentifierKeyDown(event) {
        if (event.key === "Enter") {
          event.preventDefault();
          void app.authUi.requestPasswordReset();
        }
      },
      authPasswordResetConfirmPasswordKeyDown(event) {
        if (event.key === "Enter") {
          event.preventDefault();
          void app.authUi.confirmPasswordReset();
        }
      },
    },
    CreateProvider: {
      modelCreateBtnClick() {
        void app.modelsAdminUi.createModel();
      },
    },
    ModelsShell: {
      modelsListClick(event) {
        const trigger = event.target.closest("[data-lm-provider-action]");
        if (!trigger) return;
        const id = String(trigger.dataset.lmProvider || "");
        const action = String(trigger.dataset.lmProviderAction || "");
        if (!id) return;
        if (action === "save") void app.modelsAdminUi.saveModel(id);
        else if (action === "test") void app.modelsAdminUi.testModel(id);
        else if (action === "delete") void app.modelsAdminUi.deleteModel(id);
      },
    },
    CreateUser: {
      userCreateBtnClick() {
        void app.usersAdminUi.createAuthUser();
      },
    },
    UsersShell: {
      usersListClick(event) {
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
          void app.usersAdminUi.saveAuthUser(username);
        } else if (action === "reset-password") {
          void app.usersAdminUi.resetAuthUserPassword(username);
        } else if (action === "delete") {
          void app.usersAdminUi.deleteAuthUser(username);
        }
      },
    },
  };
}
