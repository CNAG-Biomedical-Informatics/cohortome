import React from 'react';

export function PhenoSetup() {
  return (
    <>
      <div className="pheno-setup-body">
        <div id="phenoPatientField" className="is-hidden">
          <label htmlFor="phenoPatientId">Patient or visit to match</label>
          <input
            id="phenoPatientId"
            list="phenoPatientChoices"
            placeholder="Search available patient or visit IDs"
            autoComplete="off"
          />
          <datalist id="phenoPatientChoices"></datalist>
        </div>
        <details className="pheno-setup-saved-cohorts">
          <summary className="pheno-setup-saved-cohorts-header">
            <span className="section-heading-inline">
              <span className="section-heading-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M19 21H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
                  <path d="M16 17V3"></path>
                  <path d="M11 7H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-5"></path>
                </svg>
              </span>
              <span>Saved Cohorts</span>
            </span>
          </summary>
          <div id="phenoSavedCohortsSelection" className="section-note">
            No saved cohorts attached as separate references.
          </div>
          <div id="phenoSavedCohorts" className="empty">
            No saved cohorts yet.
          </div>
        </details>
        <details id="phenoAdvancedOptions" className="query-section pheno-advanced-options">
          <summary className="pheno-advanced-summary">
            <span className="section-heading-inline">
              <span className="section-heading-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M4 21v-7"></path>
                  <path d="M4 10V3"></path>
                  <path d="M12 21v-9"></path>
                  <path d="M12 8V3"></path>
                  <path d="M20 21v-5"></path>
                  <path d="M20 12V3"></path>
                  <path d="M2 14h4"></path>
                  <path d="M10 8h4"></path>
                  <path d="M18 16h4"></path>
                </svg>
              </span>
              <span>Customize comparison</span>
            </span>
          </summary>
          <div className="pheno-advanced-grid">
            <div className="pheno-grid">
              <div>
                <label htmlFor="phenoIncludeTerms">Compare using</label>
                <input
                  id="phenoIncludeTerms"
                  placeholder="All supported terms, or diseases,phenotypicFeatures,treatments"
                />
              </div>
              <div>
                <label htmlFor="phenoSelectedPatientIds">Manual selection (optional)</label>
                <input
                  id="phenoSelectedPatientIds"
                  placeholder="Comma-separated IDs; empty uses the full workspace"
                />
              </div>
              <div>
                <label htmlFor="phenoAction">Action</label>
                <select id="phenoAction">
                  <option value="compare">Compare</option>
                  <option value="extract">Extract patients of interest</option>
                </select>
              </div>
              <div className="is-hidden">
                <label htmlFor="phenoMode">Mode</label>
                <select id="phenoMode">
                  <option value="cohort">Cohort mode (-r)</option>
                  <option value="patient">Patient mode (-r -t)</option>
                </select>
              </div>
              <div>
                <label htmlFor="phenoExcludeTerms">Exclude terms</label>
                <input id="phenoExcludeTerms" placeholder="sex,ethnicity,exposures,id" />
              </div>
              <div>
                <label htmlFor="phenoSimilarityMetric">Cohort metric</label>
                <select id="phenoSimilarityMetric">
                  <option value="">Default</option>
                  <option value="hamming">Hamming</option>
                  <option value="jaccard">Jaccard</option>
                </select>
              </div>
              <div>
                <label htmlFor="phenoSortBy">Sort by</label>
                <select id="phenoSortBy">
                  <option value="">Default</option>
                  <option value="hamming">Hamming</option>
                  <option value="jaccard">Jaccard</option>
                </select>
              </div>
              <div id="phenoMaxOutField">
                <label htmlFor="phenoMaxOut">Max output rows</label>
                <input id="phenoMaxOut" type="number" min="1" defaultValue="10" />
              </div>
            </div>
            <div className="pheno-checks is-hidden" id="phenoAlignChecks">
              <label>
                <input id="phenoAlign" type="checkbox" defaultChecked /> Generate alignment files
                (--align)
              </label>
            </div>
            <div className="pheno-checks" id="phenoPlotChecks">
              <label>
                <input id="phenoRenderHeatmap" type="checkbox" defaultChecked /> Render heatmap
              </label>
              <label>
                <input id="phenoRenderMds" type="checkbox" defaultChecked /> Render MDS
              </label>
              <label>
                <input id="phenoRenderGraph" type="checkbox" defaultChecked /> Render graph
              </label>
            </div>
            <div className="pheno-advanced-grid is-hidden" id="phenoGraphOptions">
              <div>
                <label htmlFor="phenoGraphMinWeight">Graph min edge weight</label>
                <input id="phenoGraphMinWeight" type="number" step="0.001" placeholder="optional" />
              </div>
              <div>
                <label htmlFor="phenoGraphMaxWeight">Graph max edge weight</label>
                <input id="phenoGraphMaxWeight" type="number" step="0.001" placeholder="optional" />
              </div>
            </div>
          </div>
        </details>
        <details id="phenoTechnicalDetails" className="query-section">
          <summary>Technical details</summary>
          <div id="phenoSelectedPatientIdsSummary" className="section-note">
            Scope: full workspace.
          </div>
          <div id="phenoReferenceFilesSummary" className="section-note">
            Active workspace files: loading...
          </div>
          <div className="pheno-actions pheno-actions-primary pheno-setup-actions">
            <button id="phenoPlanBtn" type="button" className="query-chip">
              <span className="button-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 20h9"></path>
                  <path d="M12 4h9"></path>
                  <path d="M3 5h4"></path>
                  <path d="M3 12h18"></path>
                  <path d="M3 19h4"></path>
                  <path d="m7 4 4 8-4 8"></path>
                </svg>
              </span>
              <span>Preview plan</span>
            </button>
          </div>
          <div id="phenoLmStatus" className="section-note">
            LM Studio model: checking...
          </div>
          <div id="phenoPlanStatus" className="pheno-status"></div>
          <div id="phenoPlanMeta" className="query-meta"></div>
          <div className="pheno-result-card pheno-setup-plan-card">
            <details id="phenoPlanDetails">
              <summary>
                <h3 className="section-heading-inline">
                  <span className="section-heading-icon" aria-hidden="true">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M9 18h6"></path>
                      <path d="M10 22h4"></path>
                      <path d="M12 2a7 7 0 0 0-4 12.75c.6.43 1 1.09 1 1.83V18h6v-1.42c0-.74.4-1.4 1-1.83A7 7 0 0 0 12 2z"></path>
                    </svg>
                  </span>
                  <span>Plan preview</span>
                </h3>
              </summary>
              <div className="pheno-interpretation-grid">
                <div>
                  <h4>Interpreted Plan</h4>
                  <pre id="phenoPlan">No interpreted plan yet.</pre>
                </div>
                <div>
                  <h4>Planner Reasoning</h4>
                  <div id="phenoPlanReasoning" className="empty">
                    No planner reasoning yet.
                  </div>
                </div>
              </div>
              <div
                id="phenoPlanFollowups"
                className="query-followups is-hidden"
                aria-live="polite"
              ></div>
            </details>
          </div>
        </details>
      </div>
    </>
  );
}
