import React from 'react';

export function SettingsPanel({ actions }) {
  return (
    <>
      <div className="user-settings-header">
        <strong>Settings</strong>
        <button
          id="userSettingsCloseBtn"
          onClick={actions.userSettingsCloseBtnClick}
          type="button"
          className="icon-button"
          aria-label="Close settings"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M18 6 6 18"></path>
            <path d="m6 6 12 12"></path>
          </svg>
        </button>
      </div>
      <div className="user-settings-body">
        <nav className="user-settings-nav" aria-label="Settings sections"></nav>
        <div className="user-settings-content">
          <section data-settings-page="appearance" aria-labelledby="settingsAppearanceTitle" hidden>
            <h3 id="settingsAppearanceTitle">Appearance &amp; plots</h3>
            <div className="user-settings-grid"></div>
          </section>
          <section data-settings-page="general" aria-labelledby="settingsGeneralTitle">
            <h3 id="settingsGeneralTitle">General</h3>
            <div className="user-settings-grid"></div>
          </section>
          <section data-settings-page="query" aria-labelledby="settingsQueryTitle" hidden>
            <h3 id="settingsQueryTitle">Query &amp; AI</h3>
            <div className="user-settings-grid"></div>
            <details id="localAgentsSettings" hidden></details>
          </section>
          <section data-settings-page="jobs" aria-labelledby="settingsJobsTitle" hidden>
            <h3 id="settingsJobsTitle">Jobs &amp; storage</h3>
            <div className="user-settings-grid"></div>
            <section id="resourceStorageSettings" hidden></section>
            <section id="exportLimitsSettings" hidden></section>
            <div className="user-settings-danger">
              <strong>Delete saved data</strong>
              <p className="section-note">
                These actions delete data, not preferences. Each requires confirmation.
              </p>
              <p className="section-note">
                Clearing chats keeps generated runs and files. Delete generated runs separately to
                remove their results and files; active runs are kept.
              </p>
              <div className="user-settings-danger-actions">
                <button
                  id="userDeleteChatsBtn"
                  onClick={actions.userDeleteChatsBtnClick}
                  type="button"
                  className="danger-btn"
                >
                  Clear chat history…
                </button>
                <button
                  id="userDeleteJobsBtn"
                  onClick={actions.userDeleteJobsBtnClick}
                  type="button"
                  className="danger-btn"
                >
                  Delete generated runs
                </button>
                <button
                  id="userDeleteCohortsBtn"
                  onClick={actions.userDeleteCohortsBtnClick}
                  type="button"
                  className="danger-btn"
                >
                  Delete saved cohorts
                </button>
              </div>
            </div>
          </section>
          <section data-settings-page="analysis" aria-labelledby="settingsAnalysisTitle" hidden>
            <h3 id="settingsAnalysisTitle">Analysis &amp; Pheno-Ranker</h3>
            <div className="user-settings-grid"></div>
          </section>
          <section data-settings-page="about" aria-labelledby="settingsAccountTitle" hidden>
            <h3 id="settingsAccountTitle">Account &amp; About</h3>
            <div id="userSettingsAuthSummary" className="user-settings-auth-summary">
              <strong>Authentication</strong>
              <div className="section-note">Loading authentication details...</div>
            </div>
            <details id="settingsAbout" onToggle={actions.aboutToggled}></details>
          </section>
        </div>
      </div>
      <div className="user-settings-footer">
        <div id="userSettingsStatus" className="section-note">
          Preferences are saved per signed-in user.
        </div>
        <span id="userSettingsDirty" role="status" aria-live="polite"></span>
        <div className="user-settings-actions">
          <button
            id="userSettingsResetBtn"
            onClick={actions.userSettingsResetBtnClick}
            type="button"
            className="secondary-btn"
          >
            Restore defaults
          </button>
          <button id="userSettingsSaveBtn" onClick={actions.userSettingsSaveBtnClick} type="button">
            Save changes
          </button>
        </div>
      </div>
    </>
  );
}
