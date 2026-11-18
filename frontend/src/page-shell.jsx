import { DashboardShell } from './shell/dashboard.jsx';
import { DatasetsShell, DataManagementShell, CohortsShell } from './shell/datasets.jsx';
import { UsersShell, ModelsShell } from './shell/admin.jsx';
import { QueryShell } from './shell/query.jsx';
import { PhenoShell } from './shell/pheno.jsx';
import { AnalysisShell } from './shell/analysis.jsx';
import { ChatsDrawer, MoveChatDialog, DeleteChatDialog } from './shell/chats.jsx';
import { JobsDrawer, RunHistoryDrawer } from './shell/jobs.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

// Mounted once before view roots and controllers capture their stable hosts.
function PageShell({
  shellActions,
  branding,
  auth_enabled,
  datasets,
  current_dataset_id,
  default_data_dir,
  onNewChat,
  onChatSearch,
}) {
  return (
    <>
      <main>
        <div id="authBrandHero" className={`hero hero-auth${auth_enabled ? '' : ' is-hidden'}`}>
          <div className="hero-brand">
            {branding.logo_url && (
              <>
                <img className="hero-logo" src={branding.logo_url} alt={branding.logo_alt} />
              </>
            )}
            <div className="hero-copy">
              {branding.name === 'COHORTome' ? (
                <>
                  <h1 className="brand-wordmark" aria-label="COHORTome">
                    <span className="brand-wordmark-primary">COHORT</span>
                    <span className="brand-wordmark-secondary">ome</span>
                  </h1>
                </>
              ) : (
                <>
                  <h1>{branding.name}</h1>
                </>
              )}
              <p>{branding.subtitle}</p>
              <div className="hero-powered-by">Open-source research workspace</div>
            </div>
          </div>
        </div>

        <section
          id="authGate"
          className={`auth-gate${auth_enabled ? '' : ' is-hidden'}`}
          data-logo-url={branding.logo_url || ''}
          data-logo-alt={branding.logo_alt}
        ></section>

        <div id="appShell" className={auth_enabled ? 'is-hidden' : undefined}>
          <div className="hero app-header">
            <div className="hero-brand">
              {branding.logo_url && (
                <>
                  <img className="hero-logo" src={branding.logo_url} alt={branding.logo_alt} />
                </>
              )}
              <div className="hero-copy">
                {branding.name === 'COHORTome' ? (
                  <>
                    <h1 className="brand-wordmark" aria-label="COHORTome">
                      <span className="brand-wordmark-primary">COHORT</span>
                      <span className="brand-wordmark-secondary">ome</span>
                    </h1>
                  </>
                ) : (
                  <>
                    <h1>{branding.name}</h1>
                  </>
                )}
              </div>
            </div>
            <div className="context-bar" id="globalContextBar" aria-label="Workspace status">
              <details id="contextDatasets" className="context-pill context-datasets">
                <summary aria-label="Show active datasets">
                  <span className="context-datasets-label">
                    Datasets{' '}
                    <span id="contextDatasetCount" className="context-dataset-count">
                      0
                    </span>
                    <span aria-hidden="true">⌄</span>
                  </span>
                  <strong id="contextDataDir">{default_data_dir}</strong>
                </summary>
                <div className="context-datasets-menu">
                  <h3>Active datasets</h3>
                  <ul id="contextDatasetList"></ul>
                </div>
              </details>
              <div className="context-pill">
                <span>Workspace</span>
                <strong id="contextCohort">Loading...</strong>
              </div>
              <div className="context-pill">
                <span>LLM</span>
                <strong id="contextLmModel">Checking...</strong>
              </div>
              <div className="context-pill">
                <span>Scope</span>
                <strong id="contextScope">Full workspace</strong>
              </div>
            </div>
            <div id="heroAuthUtility" className="hero-utility is-hidden"></div>
          </div>

          <div
            id="userSettingsPanel"
            onInput={shellActions.SettingsPanel?.edited}
            onChange={shellActions.SettingsPanel?.edited}
            className="user-settings-panel is-hidden"
            role="dialog"
            aria-label="User settings"
          ></div>

          <ChatsDrawer
            actions={shellActions.ChatsDrawer}
            onNewChat={onNewChat}
            onChatSearch={onChatSearch}
          />

          <MoveChatDialog />
          <DeleteChatDialog />

          <div className="app-workbench">
            <aside
              className="app-sidebar"
              aria-label="Primary navigation"
              data-help-url={branding.help_url}
              data-brand-name={branding.name}
            >
              <div id="analysisChatDock" hidden></div>
            </aside>

            <div className="app-content">
              <DashboardShell actions={shellActions.DashboardShell} />

              <CohortsShell actions={shellActions.CohortsShell} />
              <DatasetsShell
                actions={shellActions.DatasetsShell}
                datasets={datasets}
                current_dataset_id={current_dataset_id}
              />

              <DataManagementShell actions={shellActions.DataManagementShell} />

              <dialog
                id="deploymentAppearanceDialog"
                className="deployment-appearance"
                aria-labelledby="deploymentAppearanceTitle"
              ></dialog>

              <UsersShell actions={shellActions.UsersShell} />

              <ModelsShell actions={shellActions.ModelsShell} />

              <QueryShell actions={shellActions.QueryShell} />

              <PhenoShell actions={shellActions.PhenoShell} />

              <AnalysisShell actions={shellActions.AnalysisShell} />
            </div>
          </div>
        </div>
      </main>
      <JobsDrawer actions={shellActions.JobsDrawer} />
      <RunHistoryDrawer actions={shellActions.RunHistoryDrawer} />
    </>
  );
}
export function mountPageShell({ shellActions, onNewChat, onChatSearch } = {}) {
  const config = JSON.parse(document.getElementById('applicationConfig').textContent);
  flushSync(() =>
    createRoot(document.getElementById('applicationRoot')).render(
      <PageShell
        {...config}
        shellActions={shellActions}
        onNewChat={onNewChat}
        onChatSearch={onChatSearch}
      />,
    ),
  );
}
