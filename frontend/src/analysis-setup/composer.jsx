import React from 'react';
export function AnalysisComposer() {
  return (
    <div id="analysisComposer" className="analysis-composer">
      <div className="analysis-composer-header">
        <div className="composer-heading-group">
          <strong id="analysisComposerTitle">Run Analysis</strong>
          <div className="context-mode-switch" role="group" aria-label="Analysis question context">
            <button
              id="analysisContextWorkspaceBtn"
              type="button"
              className="context-mode-option is-active"
              aria-pressed="true"
              title="Use the current Analysis scope and governed workspace context."
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
                  <ellipse cx="12" cy="6" rx="7" ry="3"></ellipse>
                  <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"></path>
                  <path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"></path>
                </svg>
              </span>
              <span>Workspace</span>
            </button>
            <button
              id="analysisContextGeneralBtn"
              type="button"
              className="context-mode-option"
              aria-pressed="false"
              title="Ask the model without workspace, cohort, assay, or analysis context."
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
                  <path d="M8 9h8"></path>
                  <path d="M8 13h5"></path>
                  <path d="M6 4h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-4 4v-4H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path>
                </svg>
              </span>
              <span>General question</span>
            </button>
          </div>
        </div>
      </div>
      <div className="analysis-flow-cue">Results and follow-up questions will appear below.</div>
      <div className="analysis-picker">
        <div id="analysisMethodPicker" className="analysis-picker-copy">
          <label htmlFor="analysisMethodSelect">What analysis would you like to run?</label>
          <select id="analysisMethodSelect" aria-describedby="analysisMethodDescription">
            <option value="summary">Describe my cohort · No LLM needed</option>
          </select>
          <p id="analysisMethodDescription" className="section-note">
            Summarize the patients and clinical patterns in your current scope.
          </p>
        </div>
        <div className="analysis-picker-copy is-hidden">
          <div className="analysis-picker-eyebrow">Analysis picker</div>
          <strong id="analysisCatalogDisclosureTitle">Choose analysis</strong>
          <div id="analysisCatalogDisclosureNote" className="section-note">
            Use the catalog to configure the prompt, mode, and required inputs.
          </div>
          <div id="analysisCatalogStatus" className="section-note">
            Loading curated analyses...
          </div>
        </div>
        <div className="analysis-picker-actions">
          <button id="analysisCatalogBrowseBtn" type="button" className="query-chip">
            Browse method details
          </button>
          <button id="analysisComposerExamplesBtn" type="button" className="query-chip">
            Prompt examples
          </button>
        </div>
        <div
          id="analysisCatalogList"
          className="analysis-catalog-featured is-hidden"
          aria-hidden="true"
        >
          <div className="empty">Loading curated analyses...</div>
        </div>
        <div id="analysisCatalogAssayParking">
          <div id="analysisCatalogAssayPanel" className="analysis-assay-panel is-hidden">
            <div className="analysis-assay-panel-header">
              <div className="analysis-assay-panel-heading">Requirements</div>
              <strong id="analysisCatalogAssayTitle">Analysis setup</strong>
            </div>
            <div id="analysisCatalogAssayNote" className="analysis-assay-panel-note">
              Select an analysis to see its required inputs.
            </div>
            <div id="analysisCatalogSetupBadges" className="analysis-catalog-tags"></div>
            <div
              id="analysisSetupChecklist"
              className="analysis-setup-checklist"
              aria-live="polite"
            ></div>
            <div id="analysisCatalogAssayStatus" className="analysis-setup-status">
              Checking transcriptomics assays...
            </div>
            <div id="analysisCatalogAssayDatasetList" className="assay-dataset-select">
              <div className="empty">No assay loaded</div>
            </div>
          </div>
        </div>
      </div>
      <details id="analysisMeasurementComparison" className="section-card">
        <summary>Compare two measurements · Exploratory association</summary>
        <div id="associationExamples" className="section-note" hidden></div>
        <p className="section-note">
          Explore correlation across two modalities in one dataset. Exact sample links, one
          observation per patient; no normalization or causal inference. Matrices must be at most 64
          MiB and 1,000 samples. Use normalized RNA values for biological interpretation.
        </p>
        <div className="assay-grid">
          <div>
            <label htmlFor="associationAssayX">X modality / measurement matrix</label>
            <select id="associationAssayX"></select>
            <label htmlFor="associationSearchX">Search X features</label>
            <input
              id="associationSearchX"
              type="search"
              placeholder="Name, description or ID"
              disabled
            />
            <label htmlFor="associationFeatureX">X feature ID</label>
            <select
              id="associationFeatureX"
              aria-describedby="associationFeatureStatusX associationDescriptionX"
              disabled
            >
              <option value="">Choose a matrix first</option>
            </select>
            <p id="associationDescriptionX" className="section-note" role="status" />
            <div id="associationFeatureStatusX" className="note" role="status"></div>
          </div>
          <div>
            <label htmlFor="associationAssayY">Y modality / measurement matrix</label>
            <select id="associationAssayY"></select>
            <label htmlFor="associationSearchY">Search Y features</label>
            <input
              id="associationSearchY"
              type="search"
              placeholder="Name, description or ID"
              disabled
            />
            <label htmlFor="associationFeatureY">Y feature ID</label>
            <select
              id="associationFeatureY"
              aria-describedby="associationFeatureStatusY associationDescriptionY"
              disabled
            >
              <option value="">Choose a matrix first</option>
            </select>
            <p id="associationDescriptionY" className="section-note" role="status" />
            <div id="associationFeatureStatusY" className="note" role="status"></div>
          </div>
        </div>
        <button
          id="associationOpenBtn"
          type="button"
          className="query-chip query-chip-deterministic"
        >
          Use these measurements
        </button>
        <p id="associationStatus" className="section-note" role="status">
          Choose two measurements to fill the analysis prompt. Review the question and scope, then
          select Run analysis. Keep A/B comparison off.
        </p>
      </details>
      <div id="analysisRequestHome">
        <div id="analysisRequestComposer"></div>
      </div>
    </div>
  );
}
