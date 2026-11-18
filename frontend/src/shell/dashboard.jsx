import React from 'react';

export function DashboardShell({ actions }) {
  return (
    <section id="dashboardTab" className="tab-panel active">
      <section id="dashboardPatientsPanel" className="dashboard-subpanel patient-overview">
        <div id="patientOverviewRoot"></div>
        <div id="patientOverviewDetail"></div>
      </section>
      <section id="dashboardTimelinePanel" className="dashboard-subpanel">
        <div className="controls dashboard-panel-frame dashboard-timeline-panel-frame">
          <div className="dashboard-timeline-main">
            <div id="dashboardTimeline" className="empty">
              Load dataset to build the patient timeline.
            </div>
            <div className="dashboard-timeline-lower">
              <div className="detail-shell dashboard-section-card">
                <div className="dashboard-section-header">
                  <div>
                    <div className="dashboard-card-eyebrow">Timeline inspector</div>
                    <h3>Inspection</h3>
                  </div>
                  <details className="inline-view-help">
                    <summary aria-label="How to inspect a patient" title="How to inspect a patient">
                      ?
                    </summary>
                    <p>
                      Click a patient span, a timeline marker, or Inspect to review the patient and
                      their available data.
                    </p>
                  </details>
                </div>
                <div id="detail" onClick={actions.detailClick} className="empty">
                  Select a patient in the plot to see their information.
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section id="dashboardClinicalPanel" className="dashboard-subpanel active">
        <div className="controls dashboard-panel-frame">
          <div className="dashboard-clinical-stack">
            <section className="dashboard-section-card">
              <div id="dashboard" className="empty">
                Load dataset to build the dashboard.
              </div>
            </section>
          </div>
        </div>
      </section>
      <section id="dashboardAssaysPanel" className="dashboard-subpanel">
        <div className="controls dashboard-panel-frame">
          <div id="assayOverviewView">
            <div id="assayDashboardStatus" className="query-status assay-status-strip">
              Checking assays...
            </div>
            <div id="assayDashboardOverview" className="assay-overview-panel">
              <div className="empty">Load assays to review modality coverage.</div>
            </div>
            <section className="assay-browser" aria-labelledby="assayTypesHeading">
              <div className="assay-modality-section-header">
                <strong id="assayTypesHeading">Browse assays</strong>
              </div>
              <div
                id="assayModalityTabs"
                onClick={actions.assayModalityTabsClick}
                className="assay-modality-tabs"
                role="group"
                aria-label="Filter assays by modality"
              ></div>
              <div id="assayDashboardCards" className="assay-dashboard-grid">
                <div className="empty">No assays loaded.</div>
              </div>
              <div id="variantPanelCards" className="assay-dashboard-grid" hidden></div>
            </section>
            <details id="transcriptomicsQuickExpressionPanel" className="query-section">
              <summary>
                <span className="section-heading-inline">
                  <span
                    className="section-heading-icon"
                    data-modality-symbol="transcriptomics"
                    aria-hidden="true"
                  ></span>
                  <span>Transcriptomics quick expression</span>
                </span>
              </summary>
              <div className="section-note">
                A deterministic raw-count transcriptomics lookup using the current Analysis scope.
                Other expression data types stay in the inventory and their compatible curated
                Analysis tools.
              </div>
              <div className="assay-grid" style={{ marginTop: '12px' }}>
                <div>
                  <label>Raw-count transcriptomics assays</label>
                  <div id="analysisAssayDatasetList" className="assay-dataset-select">
                    <div className="empty">No assay loaded</div>
                  </div>
                </div>
                <div>
                  <label htmlFor="analysisAssayGene">Gene ID</label>
                  <input
                    id="analysisAssayGene"
                    onInput={actions.analysisAssayGeneInput}
                    list="analysisAssayGenes"
                    placeholder="e.g. ENSG00000169429"
                  />
                  <datalist id="analysisAssayGenes"></datalist>
                </div>
              </div>
              <div className="query-row" style={{ marginTop: '12px' }}>
                <button
                  id="analysisAssayRunBtn"
                  onClick={actions.analysisAssayRunBtnClick}
                  type="button"
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
                      <path d="M4 19h16"></path>
                      <path d="M6 15 10 9l4 3 4-6"></path>
                    </svg>
                  </span>
                  <span>Show expression</span>
                </button>
              </div>
              <div id="analysisAssayStatus" className="query-status" style={{ marginTop: '10px' }}>
                Choose an assay and gene to inspect expression in the current Analysis scope.
              </div>
              <div
                id="analysisAssayResult"
                className="assay-result empty"
                style={{ marginTop: '12px' }}
              >
                No transcriptomics expression summary yet.
              </div>
            </details>
          </div>
          <section
            id="variantBrowser"
            className="variant-browser"
            hidden
            aria-label="Variant browser"
          ></section>
        </div>
      </section>
      <section id="dashboardImagingPanel" className="dashboard-subpanel">
        <div className="controls dashboard-panel-frame">
          <div className="dashboard-view-heading">
            <h2>Imaging</h2>
            <span id="dicomDashboardStatus" className="dashboard-count" role="status"></span>
            <details className="inline-view-help">
              <summary aria-label="About imaging">?</summary>
              <p>
                Counts describe listed imaging studies, not individual images. Viewer availability
                is shown below.
              </p>
            </details>
          </div>
          <section id="dicomDashboardPanel" className="dicom-dashboard-panel">
            <div className="assay-modality-section-header">
              <strong>Imaging studies</strong>
            </div>
            <div id="dicomDashboardHealth" className="dicom-health-panel">
              <div className="empty">DICOM viewer status not checked.</div>
            </div>
            <div id="dicomDashboardStudies" className="dicom-study-grid">
              <div className="empty">No DICOM studies configured.</div>
            </div>
          </section>
          <h3>Derived imaging measurements</h3>
          <p className="section-note">
            Values extracted from images, such as volumes or lesion counts—not additional images.
          </p>
          <div id="imagingDashboardCards" className="assay-dashboard-grid">
            <div className="empty">Load a workspace to check imaging measurements.</div>
          </div>
        </div>
      </section>
      <section id="dashboardMultimodalPanel" className="dashboard-subpanel">
        <div className="controls dashboard-panel-frame">
          <div className="multimodal-heading dashboard-view-heading">
            <h2>Multimodal</h2>
            <span id="multimodalHeadingCount" className="dashboard-count" role="status"></span>
            <details className="inline-view-help">
              <summary aria-label="About multimodal coverage">?</summary>
              <p>
                Find patients with the required data types and save the matching cohort. Coverage
                describes availability, not data quality or matching visits.{' '}
                <span id="multimodalReadinessSummary"></span>
              </p>
            </details>
            <details id="multimodalMoreOptions" className="query-inline-actions">
              <summary>More options</summary>
              <div className="query-actions">
                <button
                  id="multimodalCompareShortcut"
                  onClick={actions.compareMeasurements}
                  type="button"
                  className="query-chip query-chip-deterministic"
                >
                  Compare measurements in Analysis
                </button>
              </div>
            </details>
          </div>
          <section id="multimodalReadinessPanel" className="multimodal-readiness-panel">
            <div id="multimodalReadinessStatus" className="query-status assay-status-strip">
              Checking multimodal readiness...
            </div>
            <div id="multimodalReadinessContent" className="multimodal-readiness-content">
              <div className="empty">Load a workspace to review multimodal readiness.</div>
            </div>
          </section>
          <section id="multimodalMatrixPanel" className="multimodal-matrix-panel">
            <div className="assay-modality-section-header">
              <strong>Feature availability preview</strong>
              <span className="query-chip badge">Whole workspace</span>
            </div>
            <div id="multimodalMatrixStatus" className="query-status assay-status-strip">
              Building multimodal feature matrix...
            </div>
            <div id="multimodalMatrixContent" className="multimodal-matrix-content">
              <div className="empty">Load a workspace to preview linked feature values.</div>
            </div>
          </section>
        </div>
      </section>
    </section>
  );
}
