import React from 'react';

export function PhenoShell() {
  return (
    <section id="phenoTab" className="tab-panel">
      <div className="controls">
        <div className="analysis-chat-bar">
          <div className="analysis-chat-current">
            <strong id="phenoChatTitle">New chat</strong>
            <small id="phenoChatStatus" role="status"></small>
          </div>
          <button id="phenoChatSave" className="query-chip is-hidden" type="button">
            Retry save
          </button>
          <button id="phenoChatReload" className="query-chip is-hidden" type="button">
            Reload saved chat
          </button>
        </div>
        <label htmlFor="phenoMode">Pheno-Ranker</label>
        <div className="pheno-mode-picker" role="group" aria-label="Pheno-Ranker mode">
          <button type="button" data-pheno-mode="cohort" aria-pressed="true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              aria-hidden="true"
            >
              <circle cx="9" cy="7" r="3" />
              <path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 13a5 5 0 0 1 3 5v3" />
            </svg>
            <span>
              <strong>Cohort comparison</strong>
              <small>Compare patients with one another</small>
            </span>
          </button>
          <button type="button" data-pheno-mode="patient" aria-pressed="false">
            <svg
              viewBox="0 0 32 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              aria-hidden="true"
            >
              <circle cx="6" cy="7" r="3" />
              <path d="M1 21v-3a5 5 0 0 1 10 0v3M13 9h6l-2-2M19 15h-6l2 2" />
              <circle cx="25" cy="7" r="3" />
              <path d="M20 21v-3a5 5 0 0 1 10 0v3" />
            </svg>
            <span>
              <strong>Patient ranking</strong>
              <small>Find similar patients for one patient</small>
            </span>
          </button>
        </div>
        <div id="phenoSetupDetails"></div>
        <div id="phenoRunPanel" className="query-section"></div>
        <div id="phenoStatus" className="pheno-status"></div>
        <div id="phenoResultEmptyState" className="pheno-result-card pheno-empty-state">
          <strong>No run yet.</strong>
        </div>
        <div
          id="phenoChatHistory"
          className="analysis-thread"
          aria-label="Pheno-Ranker conversation"
        ></div>
        <div id="phenoResultWorkspace" className="is-hidden">
          <div className="pheno-result-grid">
            <div className="pheno-result-card pheno-result-card-full">
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
                    <path d="M3 3v18h18"></path>
                    <path d="M18 17V9"></path>
                    <path d="M13 17V5"></path>
                    <path d="M8 17v-3"></path>
                  </svg>
                </span>
                <span>Plots</span>
              </h3>
              <div id="phenoPreviews" className="pheno-preview-grid"></div>
            </div>
          </div>
          <div className="pheno-result-grid">
            <div
              id="phenoExplainCard"
              className="pheno-result-card pheno-result-card-full is-hidden"
            >
              <div className="pheno-result-card-toolbar">
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
                      <path d="M12 3v18"></path>
                      <path d="M3 12h18"></path>
                      <path d="m19 5-14 14"></path>
                      <path d="m5 5 14 14"></path>
                    </svg>
                  </span>
                  <span>Explain Results</span>
                </h3>
                <div className="pheno-actions pheno-actions-secondary">
                  <button id="phenoAnalysisBtn" type="button" className="query-chip">
                    <span className="button-icon" aria-hidden="true">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M8 17 18 7"></path>
                        <path d="M9 7h9v9"></path>
                        <path d="M5 5h6"></path>
                        <path d="M5 11v8h8"></path>
                      </svg>
                    </span>
                    <span>Open matches in Analysis</span>
                  </button>
                  <button id="phenoCopyIdsBtn" type="button" className="query-chip">
                    <span className="button-icon" aria-hidden="true">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <rect x="9" y="9" width="10" height="10" rx="2"></rect>
                        <path d="M5 15V5a2 2 0 0 1 2-2h10"></path>
                      </svg>
                    </span>
                    <span>Copy match IDs</span>
                  </button>
                  <button id="phenoExplainBtn" type="button" className="query-chip">
                    <span className="button-icon" aria-hidden="true">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M12 3a7 7 0 0 0-4 12.75c.6.43 1 1.09 1 1.83V19h6v-1.42c0-.74.4-1.4 1-1.83A7 7 0 0 0 12 3z"></path>
                        <path d="M9 22h6"></path>
                      </svg>
                    </span>
                    <span>Explain results</span>
                  </button>
                  <button id="phenoExplainLlmBtn" type="button" className="query-chip">
                    <span className="button-icon" aria-hidden="true">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M9.5 9a2.5 2.5 0 1 1 5 0c0 1.5-2.5 2-2.5 4"></path>
                        <path d="M12 17h.01"></path>
                        <path d="M4 5h16v14H4z"></path>
                      </svg>
                    </span>
                    <span>Explain with LLM</span>
                  </button>
                </div>
              </div>
              <div id="phenoExplainDetail" className="empty">
                Run patient mode, then click <code>Explain results</code> to summarize the top
                matches from <code>rank.txt</code>.
              </div>
            </div>
          </div>
          <div className="pheno-result-grid">
            <div className="pheno-result-card">
              <details id="phenoOutputDetails" open>
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
                        <path d="M3 5h18"></path>
                        <path d="M3 12h18"></path>
                        <path d="M3 19h18"></path>
                      </svg>
                    </span>
                    <span>Output Preview</span>
                  </h3>
                </summary>
                <div id="phenoOutputPreview" className="empty">
                  No output preview yet.
                </div>
              </details>
            </div>
            <div id="phenoAlignmentCard" className="pheno-result-card is-hidden">
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
                    <path d="m16 18 6-6-6-6"></path>
                    <path d="m8 6-6 6 6 6"></path>
                    <path d="M14.5 4 9.5 20"></path>
                  </svg>
                </span>
                <span>Alignment Details</span>
              </h3>
              <div id="phenoAlignmentDetail" className="empty">
                Run patient mode, then click one row in <code>rank.txt</code> to inspect matched
                variables for that pair.
              </div>
            </div>
          </div>
          <div className="pheno-result-grid pheno-result-grid-secondary">
            <div className="pheno-result-card">
              <details>
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
                        <path d="M8 9h8"></path>
                        <path d="M8 13h6"></path>
                        <path d="M10 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"></path>
                        <path d="m14 3 6 6"></path>
                        <path d="M14 3v6h6"></path>
                      </svg>
                    </span>
                    <span>Command</span>
                  </h3>
                </summary>
                <pre id="phenoCommand">No run yet.</pre>
              </details>
            </div>
            <div className="pheno-result-card">
              <details>
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
                        <path d="M14 3v4a2 2 0 0 0 2 2h4"></path>
                        <path d="M5 8V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-3"></path>
                        <path d="M4 15h6"></path>
                        <path d="m7 12-3 3 3 3"></path>
                      </svg>
                    </span>
                    <span>Files</span>
                  </h3>
                </summary>
                <div id="phenoFiles" className="empty">
                  No output files yet.
                </div>
              </details>
            </div>
            <div className="pheno-result-card">
              <details>
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
                        <path d="M8 6h13"></path>
                        <path d="M8 12h13"></path>
                        <path d="M8 18h13"></path>
                        <path d="M3 6h.01"></path>
                        <path d="M3 12h.01"></path>
                        <path d="M3 18h.01"></path>
                      </svg>
                    </span>
                    <span>Logs</span>
                  </h3>
                </summary>
                <pre id="phenoLogs">No logs yet.</pre>
              </details>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
