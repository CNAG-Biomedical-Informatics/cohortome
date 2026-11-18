import React from 'react';

export function DatasetsShell({ datasets, current_dataset_id }) {
  return (
    <section id="datasetsTab" className="tab-panel">
      <div className="controls dashboard-loader">
        <div className="dashboard-loader-row dataset-loader-row">
          <div>
            <label htmlFor="dataDir">Datasets</label>
            <div className="section-note">
              Select at least one authorized dataset. The active workspace cannot be empty.
            </div>
          </div>
          <div id="datasetPickerShell" className="dataset-picker-shell">
            <select
              defaultValue={[current_dataset_id]}
              id="dataDir"
              multiple
              size="4"
              className="dataset-picker-native"
            >
              {datasets.map((dataset) => (
                <option key={dataset.dataset_id} value={dataset.dataset_id}>
                  {dataset.name}
                </option>
              ))}
            </select>
            <div
              id="datasetPickerLegend"
              className="dataset-trait-legend is-hidden"
              aria-label="Dataset trait legend"
            ></div>
            <div id="datasetPicker" className="dataset-picker-list">
              <div className="empty">No dataset available.</div>
            </div>
          </div>
          <button id="loadBtn" type="button">
            <span id="loadBtnIcon" className="button-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 3v12"></path>
                <path d="m7 10 5 5 5-5"></path>
                <path d="M5 21h14"></path>
              </svg>
            </span>
            <span id="loadBtnLabel">Load dataset</span>
          </button>
        </div>
        <div id="loadStatus" className="load-status" role="status" aria-live="polite">
          Select at least one dataset, then click Apply workspace.
        </div>
        <div id="datasetScopeSummary" className="section-note">
          Active workspace: no dataset loaded yet.
        </div>
        <div className="section-note">
          Dataset selection defines the current workspace scope for Query, Analysis, Dashboard, and
          Pheno-Ranker.
        </div>
      </div>
    </section>
  );
}

export function DataManagementShell() {
  return (
    <section id="dataTab" className="tab-panel">
      <div className="controls dashboard-loader">
        <h3>Data management</h3>
        <button
          id="resourceAdd"
          type="button"
          className="query-chip is-hidden"
          aria-haspopup="dialog"
          aria-controls="resourcePanel"
        >
          ＋ Add dataset
        </button>
        <dialog id="resourcePanel" className="resource-dialog" aria-labelledby="resourceTitle">
          <header className="resource-dialog-header">
            <div>
              <h2 id="resourceTitle">Add dataset</h2>
              <p>Install a prepared dataset or import your own package.</p>
            </div>
            <button
              id="resourceClose"
              type="button"
              className="icon-button"
              aria-label="Close add dataset"
            >
              ×
            </button>
          </header>
          <div className="resource-dialog-body">
            <div className="resource-toolbar">
              <h3>Available datasets</h3>
              <button
                id="resourceBrowse"
                type="button"
                className="query-chip"
                aria-label="Refresh available datasets"
              >
                Refresh
              </button>
              <button id="resourceImport" type="button" className="query-chip">
                Import ZIP…
              </button>
              <input
                id="resourceFile"
                type="file"
                accept=".zip,application/zip"
                className="is-hidden"
              />
            </div>
            <p id="resourceCatalogueStatus" className="section-note" role="status"></p>
            <div
              id="resourceFilters"
              className="resource-filters"
              role="group"
              aria-label="Dataset installation type"
            ></div>
            <p id="resourceFilterEmpty" className="section-note" hidden>
              No datasets in this category.
            </p>
            <div id="resourceList" className="resource-catalogue"></div>
            <details id="resourceAccess" className="view-help resource-access">
              <summary>Private repository access</summary>
              <label htmlFor="resourceToken">Repository read token</label>
              <input
                id="resourceToken"
                type="password"
                autoComplete="off"
                spellCheck="false"
                placeholder="Optional for public releases"
              />
              <p>Only needed for private downloads. Used once, never saved.</p>
            </details>
            <details className="view-help">
              <summary>Package requirements</summary>
              <p>
                Use a COHORTome resource ZIP, up to 1 GiB (4 GiB extracted). Installation validates
                files and prepares DuckDB without changing your workspace. New imports have AI
                access blocked; review their policies in Admin → Data.
              </p>
            </details>
          </div>
          <footer className="resource-dialog-footer">
            <strong id="resourceResultTitle" className="resource-result-title is-hidden"></strong>
            <p id="resourceStatus" className="section-note" role="status" aria-live="polite">
              Select a dataset to install.
            </p>
            <progress
              id="resourceProgress"
              className="is-hidden"
              aria-label="Dataset download progress"
            ></progress>
            <div className="saved-cohort-actions">
              <button id="resourceCancel" type="button" className="query-chip is-hidden">
                Cancel
              </button>
              <button id="resourceSelect" type="button" className="query-chip is-hidden">
                Add to workspace selection
              </button>
            </div>
          </footer>
        </dialog>
        <dialog
          id="resourceTerms"
          className="dataset-remove-dialog resource-terms-dialog"
          aria-labelledby="resourceTermsTitle"
          aria-describedby="resourceTermsDescription"
        ></dialog>
        <div id="datasetAdminControls">
          <h4>Installed datasets</h4>
          <p className="section-note">Open a dataset to manage its preparation and policies.</p>
          <div id="datasetAdminList" className="dataset-picker-list">
            <div className="empty">No installed datasets available.</div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function CohortsShell() {
  return (
    <section id="cohortsTab" className="tab-panel">
      <div className="controls">
        <div className="cohort-library-heading">
          <h2>Cohorts</h2>
          <span>Saved patient and sample groups</span>
        </div>
        <div className="cohort-library-toolbar">
          <div className="cohort-library-search">
            <span className="button-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              >
                <circle cx="10" cy="10" r="6" />
                <path d="m15 15 6 6" />
              </svg>
            </span>
            <input
              id="cohortLibrarySearch"
              type="text"
              list="cohortLibrarySuggestions"
              autoComplete="off"
              aria-label="Search cohorts"
              placeholder="Choose a cohort or search…"
            />
          </div>
          <datalist id="cohortLibrarySuggestions"></datalist>
          <button
            id="cohortLibraryRefresh"
            type="button"
            className="query-chip"
            aria-label="Refresh cohorts"
            title="Refresh cohorts"
          >
            <span className="button-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2" />
              </svg>
            </span>
          </button>
        </div>
        <details className="view-help">
          <summary>About saved cohorts</summary>
          <p>
            Inspect membership, export data, or open a cohort in an analysis tool. Create cohorts
            from Query, Multimodal, or Pheno-Ranker selections.
          </p>
        </details>
        <p id="cohortLibraryStatus" className="section-note" role="status"></p>
        <div id="cohortLibraryList"></div>
        <div id="cohortLibraryPages" className="saved-cohort-actions"></div>
      </div>
    </section>
  );
}
