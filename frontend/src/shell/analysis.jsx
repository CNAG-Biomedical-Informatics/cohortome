import React from 'react';

export function AnalysisShell({ actions }) {
  return (
    <section id="analysisTab" className="tab-panel">
      <div id="analysisShell" className="analysis-shell">
        <div className="controls analysis-main">
          <div className="analysis-chat-bar">
            <div className="analysis-chat-current">
              <strong id="analysisCurrentChatTitle">New chat</strong>
              <small id="analysisCurrentChatMeta">No turns yet.</small>
              <small id="analysisChatPersistence" role="status"></small>
            </div>
          </div>
          <div id="analysisChatSaveMessage" className="query-chat-notice" hidden>
            <span id="analysisChatSaveError"></span>
            <button id="analysisChatSaveRetry" className="query-chip" type="button">
              Retry save
            </button>
          </div>
          <div className="analysis-workspace-bar">
            <div id="analysisStatus" className="analysis-workspace-status"></div>
            <div id="analysisLmStatus" className="analysis-workspace-status">
              LM Studio model: checking...
            </div>
          </div>
          <div
            id="analysisFlowBar"
            onClick={actions.analysisFlowBarClick}
            className="analysis-flow-bar"
            aria-label="Analysis workflow"
          >
            <button
              type="button"
              className="analysis-flow-step"
              data-analysis-flow-target="catalog"
            >
              <span className="analysis-flow-step-index">1</span>
              <span className="analysis-flow-step-copy">
                <span>Method</span>
                <strong>Choose analysis</strong>
              </span>
            </button>
            <button type="button" className="analysis-flow-step" data-analysis-flow-target="scope">
              <span className="analysis-flow-step-index">2</span>
              <span className="analysis-flow-step-copy">
                <span>Patients</span>
                <strong>Full workspace</strong>
              </span>
            </button>
            <button
              type="button"
              className="analysis-flow-step"
              data-analysis-flow-target="requirements"
            >
              <span className="analysis-flow-step-index">3</span>
              <span className="analysis-flow-step-copy">
                <span>Inputs</span>
                <strong>Not required</strong>
              </span>
            </button>
            <button type="button" className="analysis-flow-step" data-analysis-flow-target="prompt">
              <span className="analysis-flow-step-index">4</span>
              <span className="analysis-flow-step-copy">
                <span>Review</span>
                <strong>Ready</strong>
              </span>
            </button>
            <button
              type="button"
              className="analysis-flow-step"
              data-analysis-flow-target="results"
            >
              <span className="analysis-flow-step-index">5</span>
              <span className="analysis-flow-step-copy">
                <span>Results</span>
                <strong>Empty</strong>
              </span>
            </button>
          </div>
          <details
            id="analysisSetupDisclosure"
            className="analysis-setup-disclosure"
            open
          ></details>
          <div className="analysis-history-header analysis-results-header">
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
                  <path d="M12 8v4l3 3"></path>
                  <path d="M3.05 11a9 9 0 1 1 .5 4"></path>
                  <path d="M3 4v7h7"></path>
                </svg>
              </span>
              <span>Results & follow-up</span>
            </span>
            <small>Generated responses, plots, and follow-up prompts appear here.</small>
          </div>
          <div
            id="analysisThread"
            onClick={actions.analysisThreadClick}
            className="analysis-thread"
          >
            <div className="empty">
              Run an analysis prompt to start a threaded analysis workspace.
            </div>
          </div>
          <div id="analysisContinueHost"></div>
        </div>
      </div>
    </section>
  );
}
