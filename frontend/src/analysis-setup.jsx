import React from 'react';

export function AnalysisSetup() {
  return <>
<summary>Edit setup <span className="section-note">Method, patients and inputs</span></summary>
            <div id="analysisDatasetScope" className="section-note">Workspace dataset: current selection.</div>
            <details id="analysisWorkspaceSetup" className="analysis-setup-card">
              <summary className="analysis-setup-summary">
                <div className="analysis-setup-summary-copy">
                  <strong>Patients and cohorts</strong>
                  <div className="section-note">Use the full workspace or choose a subset.</div>
                </div>
                <div className="analysis-setup-summary-body">
                  <div id="analysisSelectedPatientIdsSummary" className="section-note">Scope: full workspace.</div>
                  <div id="analysisSelectedSavedCohortSelection" className="section-note is-hidden"></div>
                  <div id="analysisCompareSelectedPatientIdsSummary" className="section-note is-hidden">Cohort B: select a saved cohort from Saved Cohorts to compare.</div>
                  <div id="analysisCompareSavedCohortSelection" className="section-note is-hidden"></div>
                </div>
              </summary>
              <div className="analysis-setup-body">
                <div>
                  <label htmlFor="analysisSelectedPatientIds">Scope</label>
                  <input id="analysisSelectedPatientIds" placeholder="Full workspace by default, or provide patient/original record IDs"/>
                </div>
                <div className="pheno-checks analysis-setup-checks">
                  <label><input id="analysisCompareMode" type="checkbox"/> Compare against a second cohort</label>
                </div>
                <div id="analysisCompareField" className="analysis-setup-compare" style={{display:'none'}}>
                  <input id="analysisCompareSelectedPatientIds" type="hidden" defaultValue=""/>
                </div>
                <details className="analysis-setup-saved-cohorts">
                  <summary className="analysis-setup-saved-cohorts-header">
                    <strong>Saved Cohorts</strong>
                    <span className="section-note">Attach existing saved cohorts as Cohort A or Cohort B.</span>
                  </summary>
                  <div id="savedCohorts" className="empty">No saved cohorts yet.</div>
                </details>
                <div id="analysisStarterPanel" className="analysis-starter-panel">
                  <div className="analysis-starter-header">
                    <div>
                      <label htmlFor="analysisPrompt">Analysis</label>
                      <div className="section-note">Use curated analyses for structured runs, or use quick prompts for simpler open-ended interpretation.</div>
                    </div>
                  </div>
                  <div className="analysis-catalog-shell">
                    <div className="analysis-catalog-block">
                      <div className="analysis-catalog-block-header">
                        <strong>Quick prompts</strong>
                        <span className="section-note">Questions you can ask directly without using a catalog tool.</span>
                      </div>
                      <div className="section-note">Prompt types: <span className="query-chip query-chip-deterministic badge">Deterministic summary</span> <span className="query-chip query-chip-planner badge">LLM-planned</span> <span className="query-chip query-chip-llm badge">LLM interpretation</span></div>
                      <div className="query-examples" id="analysisExamples">
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="Summarize the main clinical patterns in this workspace and tell me what stands out."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Main workspace patterns</span></button>
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="What stands out in treatment usage over time?"><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Treatment usage over time</span></button>
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="Show the main disease burden, medication burden, and visit distribution in this workspace."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Disease, medication, and visit burden</span></button>
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="Describe how this workspace changes over time and point out the most active periods."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>How the workspace changes over time</span></button>
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="Which patient subgroups look most distinct within the current analysis scope?"><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Distinct patient subgroups</span></button>
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="Summarize the top diseases and medications and tell me which patterns are most concentrated."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Top diseases and medications</span></button>
                        <button type="button" className="query-chip query-chip-deterministic" data-analysis-deterministic="true" data-analysis-prompt="Which numeric longitudinal measures are available in the current analysis scope?"><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Available longitudinal measures</span></button>
                        <button type="button" className="query-chip query-chip-planner" data-analysis-prompt="Tell me which diseases and medications most separate the active analysis scopes."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>What separates A from B</span></button>
                        <button type="button" className="query-chip query-chip-planner" data-analysis-prompt="Compare the active analysis scopes and focus on temporal differences and possible treatment-intensity differences."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Temporal and treatment-intensity differences</span></button>
                        <button type="button" className="query-chip query-chip-planner" data-analysis-prompt="Compare the active analysis scopes by disease burden, medication burden, and timepoint distribution."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Compare A vs B core profiles</span></button>
                        <button type="button" className="query-chip query-chip-llm" data-analysis-llm-only="true" data-analysis-prompt="Interpret the disease and medication profiles in this workspace and summarize the main themes."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Interpret disease and medication profiles</span></button>
                        <button type="button" className="query-chip query-chip-llm" data-analysis-llm-only="true" data-analysis-prompt="Write a concise workspace briefing for a clinician, including what stands out and what needs validation."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Clinician-facing workspace briefing</span></button>
                        <button type="button" className="query-chip query-chip-llm" data-analysis-llm-only="true" data-analysis-prompt="Write a short clinician-facing summary combining the current analysis scope profile and the observed transcriptomics expression findings."><span className="analysis-domain-icons" aria-hidden="true"><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span className="analysis-domain-icon" data-modality-symbol="assay" aria-hidden="true"></span></span><span>Clinical + assay summary</span></button>
                        <button type="button" className="query-chip query-chip-llm" data-analysis-llm-only="true" data-analysis-prompt="Compare the active analysis scopes like a clinical reviewer and summarize the main similarities, differences, and uncertainties."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Clinical review of A vs B</span></button>
                        <button type="button" className="query-chip query-chip-llm" data-analysis-llm-only="true" data-analysis-prompt="Interpret the selected workspace subset as a possible clinical subgroup and explain what evidence supports that interpretation."><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span><span>Interpret selected subgroup</span></button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </details>
            <div id="analysisStarterHost"></div>
            <div id="analysisCatalogDrawer" className="analysis-catalog-drawer is-hidden" aria-hidden="true">
              <div className="analysis-catalog-drawer-backdrop" data-analysis-catalog-close="true"></div>
              <div className="analysis-catalog-drawer-panel" role="dialog" aria-modal="true" aria-labelledby="analysisCatalogDrawerTitle">
                <div className="analysis-catalog-drawer-header">
                  <div>
                    <strong id="analysisCatalogDrawerTitle">Analysis Catalog</strong>
                    <div className="section-note">Curated, structured analyses that preconfigure the current Analysis thread.</div>
                  </div>
                  <button id="analysisCatalogDrawerCloseBtn" type="button" className="query-chip">Close</button>
                </div>
                <div className="analysis-catalog-toolbar analysis-catalog-toolbar-drawer">
                  <label className="analysis-catalog-search">
                    <span className="analysis-catalog-search-label">Search</span>
                    <input id="analysisCatalogDrawerSearch" type="search" placeholder="Find tools by name, tag, runner, or description"/>
                  </label>
                  <div id="analysisCatalogDrawerFilters" className="analysis-catalog-filters" role="tablist" aria-label="Analysis Catalog filters">
                    <button type="button" className="query-chip is-active" data-analysis-catalog-filter="all" aria-pressed="true">All</button>
                    <button type="button" className="query-chip" data-analysis-catalog-filter="clinical" aria-pressed="false"><span className="analysis-domain-icon" data-modality-symbol="clinical" aria-hidden="true"></span>Clinical</button>
                    <button type="button" className="query-chip" data-analysis-catalog-filter="assay" aria-pressed="false"><span className="analysis-domain-icon" data-modality-symbol="assay" aria-hidden="true"></span>Assays</button>
                    <button type="button" className="query-chip" data-analysis-catalog-filter="workflow" aria-pressed="false">Workflow</button>
                    <button type="button" className="query-chip" data-analysis-catalog-filter="background" aria-pressed="false">Background</button>
                    <button type="button" className="query-chip" data-analysis-catalog-filter="external" aria-pressed="false">External</button>
                  </div>
                </div>
                <div id="analysisCatalogDrawerList" className="analysis-catalog-list">
                  <div className="empty">Loading curated analyses...</div>
                </div>
              </div>
            </div>
            <div id="analysisComposer" className="analysis-composer">
              <div className="analysis-composer-header">
                <div className="composer-heading-group">
                  <strong id="analysisComposerTitle">Run Analysis</strong>
                  <div className="context-mode-switch" role="group" aria-label="Analysis question context">
                    <button id="analysisContextWorkspaceBtn" type="button" className="context-mode-option is-active" aria-pressed="true" title="Use the current Analysis scope and governed workspace context.">
                      <span className="button-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="6" rx="7" ry="3"></ellipse><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"></path><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"></path></svg>
                      </span>
                      <span>Workspace</span>
                    </button>
                    <button id="analysisContextGeneralBtn" type="button" className="context-mode-option" aria-pressed="false" title="Ask the model without workspace, cohort, assay, or analysis context.">
                      <span className="button-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 9h8"></path><path d="M8 13h5"></path><path d="M6 4h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-4 4v-4H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path></svg>
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
                  <select id="analysisMethodSelect" aria-describedby="analysisMethodDescription"><option value="summary">Describe my cohort · No LLM needed</option></select>
                  <p id="analysisMethodDescription" className="section-note">Summarize the patients and clinical patterns in your current scope.</p>
                </div>
                <div className="analysis-picker-copy is-hidden">
                  <div className="analysis-picker-eyebrow">Analysis picker</div>
                  <strong id="analysisCatalogDisclosureTitle">Choose analysis</strong>
                  <div id="analysisCatalogDisclosureNote" className="section-note">Use the catalog to configure the prompt, mode, and required inputs.</div>
                  <div id="analysisCatalogStatus" className="section-note">Loading curated analyses...</div>
                </div>
                <div className="analysis-picker-actions">
                  <button id="analysisCatalogBrowseBtn" type="button" className="query-chip">Browse method details</button>
                  <button id="analysisComposerExamplesBtn" type="button" className="query-chip">Prompt examples</button>
                </div>
                <div id="analysisCatalogList" className="analysis-catalog-featured is-hidden" aria-hidden="true">
                  <div className="empty">Loading curated analyses...</div>
                </div>
                <div id="analysisCatalogAssayParking">
                  <div id="analysisCatalogAssayPanel" className="analysis-assay-panel is-hidden">
                    <div className="analysis-assay-panel-header">
                      <div className="analysis-assay-panel-heading">Requirements</div>
                      <strong id="analysisCatalogAssayTitle">Analysis setup</strong>
                    </div>
                    <div id="analysisCatalogAssayNote" className="analysis-assay-panel-note">Select an analysis to see its required inputs.</div>
                    <div id="analysisCatalogSetupBadges" className="analysis-catalog-tags"></div>
                    <div id="analysisSetupChecklist" className="analysis-setup-checklist" aria-live="polite"></div>
                    <div id="analysisCatalogAssayStatus" className="analysis-setup-status">Checking transcriptomics assays...</div>
                    <div id="analysisCatalogAssayDatasetList" className="assay-dataset-select">
                      <div className="empty">No assay loaded</div>
                    </div>
                  </div>
                </div>
              </div>
            <details id="analysisMeasurementComparison" className="section-card">
              <summary>Compare two measurements · Exploratory association</summary>
              <div id="associationExamples" className="section-note" hidden></div>
              <p className="section-note">Explore correlation across two modalities in one dataset. Exact sample links, one observation per patient; no normalization or causal inference. Matrices must be at most 64 MiB and 1,000 samples. Use normalized RNA values for biological interpretation.</p>
              <div className="assay-grid">
                <div><label htmlFor="associationAssayX">X modality / measurement matrix</label><select id="associationAssayX"></select><label htmlFor="associationSearchX">Search X feature IDs</label><input id="associationSearchX" type="search" placeholder="Filter available IDs" disabled/><label htmlFor="associationFeatureX">X feature ID</label><select id="associationFeatureX" aria-describedby="associationFeatureStatusX" disabled><option value="">Choose a matrix first</option></select><div id="associationFeatureStatusX" className="note" role="status"></div></div>
                <div><label htmlFor="associationAssayY">Y modality / measurement matrix</label><select id="associationAssayY"></select><label htmlFor="associationSearchY">Search Y feature IDs</label><input id="associationSearchY" type="search" placeholder="Filter available IDs" disabled/><label htmlFor="associationFeatureY">Y feature ID</label><select id="associationFeatureY" aria-describedby="associationFeatureStatusY" disabled><option value="">Choose a matrix first</option></select><div id="associationFeatureStatusY" className="note" role="status"></div></div>
              </div>
              <button id="associationOpenBtn" type="button" className="query-chip query-chip-deterministic">Use these measurements</button>
              <p id="associationStatus" className="section-note" role="status">Choose two measurements to fill the analysis prompt. Review the question and scope, then select Run analysis. Keep A/B comparison off.</p>
            </details>
              <div id="analysisRequestHome">
              <div id="analysisRequestComposer"></div>
              </div>
            </div>
  </>;
}
