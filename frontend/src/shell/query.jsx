import React from 'react';

export function QueryShell() {
  return (
    <section id="queryTab" className="tab-panel">
      <div className="controls">
        <div className="analysis-chat-bar">
          <div className="analysis-chat-current">
            <strong id="queryCurrentChatTitle">New chat</strong>
            <small id="queryChatPersistence" role="status"></small>
          </div>
        </div>
        <div id="lmStatus" className="section-note">
          LM Studio model: checking...
        </div>
        <div id="queryStarterTopHost">
          <div id="queryStarterPanel" className="query-starter-panel">
            <div className="query-starter-header">
              <div>
                <label htmlFor="question">Ask a question</label>
                <div className="section-note">
                  Use Query to find workspace subsets, counts, and patient lists. Use Analysis to
                  interpret a selected scope or saved cohort.
                </div>
              </div>
            </div>
            <div className="section-note">
              Prompt types:{' '}
              <span className="query-chip query-chip-deterministic badge">Deterministic</span>{' '}
              <span className="query-chip query-chip-planner badge">LLM-planned</span>{' '}
              <span className="query-chip query-chip-llm badge">LLM interpretation</span>
            </div>
            <div className="query-examples" id="queryExamples">
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Tell me the list of patients in the workspace"
              >
                List all patients in the workspace
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="How many patients have Crohn Disease?"
              >
                How many patients have Crohn Disease?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Which patients have Infliximab?"
              >
                Which patients have Infliximab?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Which patients do not have Crohn Disease but take Infliximab?"
              >
                Patients without Crohn but with Infliximab
              </button>
              <button
                type="button"
                className="query-chip query-chip-planner"
                data-prompt="How many patients take biologics?"
              >
                How many patients take biologics?
              </button>
              <button
                type="button"
                className="query-chip query-chip-planner"
                data-prompt="Which patients take biologics?"
              >
                Which patients take biologics?
              </button>
              <button
                type="button"
                className="query-chip query-chip-llm"
                data-analysis-handoff="true"
                data-analysis-llm-only="true"
                data-analysis-prompt="Interpret this workspace like a clinician and summarize the main patterns."
              >
                Interpret this workspace in Analysis
              </button>
              <button
                type="button"
                className="query-chip query-chip-llm"
                data-analysis-handoff="true"
                data-analysis-llm-only="true"
                data-analysis-prompt="What are the main clinical themes in this dataset? Summarize them in a table."
              >
                Main clinical themes in Analysis
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Which patients take more than 1 medication?"
              >
                Which patients take more than 1 medication?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="How many patients take exactly 1 medication?"
              >
                How many patients take exactly 1 medication?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Which patients have no medications?"
              >
                Which patients have no medications?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="List medications in this workspace"
              >
                List medications in this workspace
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="List diseases in this workspace"
              >
                List diseases in this workspace
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Show patient SYN007"
              >
                Show patient SYN007
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="How many timepoints are in this workspace?"
              >
                How many timepoints are in this workspace?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="What happened to this workspace over time?"
              >
                What happened to this workspace over time?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Which patients have more than 1 timepoint?"
              >
                Which patients have more than 1 timepoint?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="How many timepoints mention Ocrelizumab?"
              >
                How many timepoints mention Ocrelizumab?
              </button>
              <button
                type="button"
                className="query-chip query-chip-deterministic"
                data-prompt="Show the timeline for patient SYN007"
              >
                Show the timeline for patient SYN007
              </button>
              <button
                type="button"
                className="query-chip query-chip-planner"
                data-prompt="How many patients take anti-TNF treatments?"
              >
                How many patients take anti-TNF treatments?
              </button>
              <button
                type="button"
                className="query-chip query-chip-planner"
                data-prompt="Which patients take anti-TNF treatments?"
              >
                Which patients take anti-TNF treatments?
              </button>
              <button
                type="button"
                className="query-chip query-chip-planner"
                data-prompt="How many patients take biologics but do not take steroids?"
              >
                How many patients take biologics but do not take steroids?
              </button>
              <button
                type="button"
                className="query-chip query-chip-llm"
                data-analysis-handoff="true"
                data-analysis-llm-only="true"
                data-analysis-prompt="Summarize the main treatment patterns in this workspace and explain what stands out clinically."
              >
                Summarize treatment patterns in Analysis
              </button>
              <button
                type="button"
                className="query-chip query-chip-llm"
                data-analysis-handoff="true"
                data-analysis-llm-only="true"
                data-analysis-prompt="What evidence supports the main workspace summary?"
              >
                Evidence-supported summary in Analysis
              </button>
            </div>
          </div>
        </div>
        <div className="analysis-history-header">
          <div className="query-thread-mode" aria-label="Query thread mode">
            <span id="queryThreadModeLabel" className="query-thread-mode-label">
              Workspace mode
            </span>
            <span id="queryGranularityModeValue" className="query-thread-mode-value">
              Detailed
            </span>
            <button
              id="queryPolicyInfoBtn"
              type="button"
              className="query-policy-info is-hidden"
              aria-label="Workspace policy details"
              title="Workspace policy details"
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
                  <circle cx="12" cy="12" r="9"></circle>
                  <path d="M12 10v6"></path>
                  <path d="M12 7h.01"></path>
                </svg>
              </span>
            </button>
          </div>
        </div>
        <div id="queryChatContextNotice" className="query-chat-notice" hidden></div>
        <div id="queryChatMessage" className="query-chat-notice" hidden>
          <span id="queryChatMessageText"></span>
          <button id="queryChatSaveRetry" type="button" className="query-chip" hidden>
            Retry save
          </button>
        </div>
        <div id="queryThread" className="analysis-thread">
          <div className="empty">
            Ask a query to start a conversational thread. Recent text history is kept, but
            previous-result memory is opt-in.
          </div>
        </div>
        <div id="queryComposer" className="query-composer"></div>
        <details id="queryLatestDetails" className="query-section">
          <summary>Latest query details</summary>
          <div id="queryReply" className="is-hidden" aria-hidden="true">
            Ask about medications, diseases, or a patient timeline.
          </div>
          <div id="queryReason" className="empty">
            Run a query to see how the answer was produced.
          </div>
          <div id="queryFollowups" className="query-followups"></div>
          <details id="queryDetails" className="query-section" style={{ marginTop: '12px' }}>
            <summary>Show structured data</summary>
            <pre id="queryData"></pre>
          </details>
        </details>
      </div>
    </section>
  );
}
