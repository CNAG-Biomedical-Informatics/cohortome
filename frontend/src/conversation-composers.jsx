import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { PhenoComposer } from './pheno-composer.jsx';
import { PhenoSetup } from './pheno-setup.jsx';
import { AnalysisSetup } from './analysis-setup.jsx';

// Mount before app_refs captures controls. Inputs remain uncontrolled so saved
// drafts and existing request controllers share one native value, not two states.
function submitOnEnter(event, submit) {
  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
    event.preventDefault();
    submit();
  }
}

function QueryComposer({ actions }) {
  return (
    <>
      <div className="query-composer-header">
        <div className="composer-heading-group">
          <strong id="queryComposerTitle">Ask a question</strong>
          <div className="context-mode-switch" role="group" aria-label="Question context">
            <button
              id="queryContextWorkspaceBtn"
              onClick={actions.workspace}
              type="button"
              className="context-mode-option is-active"
              aria-pressed="true"
              title="Use the active workspace and its governed dataset context."
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
              id="queryContextGeneralBtn"
              onClick={actions.general}
              type="button"
              className="context-mode-option"
              aria-pressed="false"
              title="Ask the model without workspace or dataset context."
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
        <div className="query-composer-actions">
          <button
            id="queryComposerExamplesBtn"
            onClick={actions.prompts}
            type="button"
            className="query-chip"
            hidden
            aria-expanded="false"
            aria-controls="queryStarterPanel"
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
                <path d="M9 18h6"></path>
                <path d="M10 22h4"></path>
                <path d="M12 2a7 7 0 0 0-4 12.74V16h8v-1.26A7 7 0 0 0 12 2Z"></path>
              </svg>
            </span>
            <span>Prompts</span>
          </button>
          <button
            id="queryPlannerBtn"
            onClick={actions.planner}
            type="button"
            className="query-chip query-chip-planner"
            title="Skip deterministic matching for the next query and use the LLM planner first."
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
                <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3Z"></path>
                <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z"></path>
              </svg>
            </span>
            <span>Use LLM planner</span>
          </button>
          <button
            id="queryMemoryBtn"
            onClick={actions.memory}
            type="button"
            className="query-chip"
            title="When enabled, patient-oriented follow-up queries can reuse the previous Query result instead of the full workspace."
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
                <path d="M12 8v5l3 3"></path>
                <circle cx="12" cy="12" r="9"></circle>
              </svg>
            </span>
            <span>Prompt scope: workspace</span>
          </button>
          <button
            id="queryDiseaseBuilderBtn"
            onClick={actions.disease}
            type="button"
            className="query-chip query-chip-deterministic"
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
                <path d="M21 21l-4.35-4.35"></path>
                <circle cx="11" cy="11" r="6"></circle>
              </svg>
            </span>
            <span>Disease cohort</span>
          </button>
          <button
            id="queryClearBtn"
            onClick={actions.clear}
            type="button"
            className="query-chip secondary-btn"
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
                <path d="M12 5v14M5 12h14"></path>
              </svg>
            </span>
            <span>New Query chat</span>
          </button>
        </div>
      </div>
      <div id="queryStarterHost" className="query-starter-host is-hidden" hidden></div>
      <div id="queryDiseasePanel" className="is-hidden">
        <div id="queryDiseaseTopChips" className="query-composer-disease-chips"></div>
        <div id="queryDiseaseStatus" className="section-note">
          Click a disease to preload a deterministic workspace query.
        </div>
      </div>
      <div className="query-row">
        <textarea
          id="question"
          aria-label="Query prompt"
          onInput={actions.edited}
          onKeyDown={(event) => submitOnEnter(event, actions.ask)}
        />
        <button id="askBtn" onClick={actions.ask} type="button">
          <span className="button-icon" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M22 2 11 13"></path>
              <path d="m22 2-7 20-4-9-9-4Z"></path>
            </svg>
          </span>
          <span>Ask</span>
        </button>
      </div>
      <div className="section-note">
        Workspace patient lookup accepts a patient ID, human-readable ClarID, or ClarID stub:{' '}
        <code>Show patient &lt;identifier&gt;</code>.
      </div>
      <div id="queryStatus" className="query-status is-hidden" aria-live="polite"></div>
    </>
  );
}
function AnalysisComposer({ actions }) {
  return (
    <>
      <div className="analysis-continue-header">
        <strong>Continue the conversation</strong>
        <button
          id="analysisEditSetupBtn"
          type="button"
          className="query-chip"
          onClick={actions.editSetup}
        >
          Edit setup
        </button>
      </div>
      <p id="analysisRunReview" className="section-note" role="status"></p>
      <div className="query-row">
        <details id="analysisRequestDetails" className="analysis-request-details">
          <summary>Review or edit the analysis request</summary>
          <textarea
            id="analysisPrompt"
            onInput={actions.edited}
            onKeyDown={(event) => submitOnEnter(event, actions.run)}
            aria-label="Analysis request"
            defaultValue="Summarize the main clinical patterns in this workspace and tell me what stands out."
          />
        </details>
        <button id="analysisRunBtn" type="button" onClick={() => actions.run()}>
          <span className="button-icon" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m5 3 14 9-14 9V3Z"></path>
            </svg>
          </span>
          <span id="analysisRunBtnLabel">Run analysis</span>
        </button>
      </div>
      <div id="analysisComposerStatus" className="query-status is-hidden"></div>
    </>
  );
}
export function mountConversationComposers({
  shellActions,
  queryActions,
  analysisActions,
  phenoActions,
}) {
  for (const [id, Component, props] of [
    ['analysisSetupDisclosure', AnalysisSetup, { shellActions }],
    ['queryComposer', QueryComposer, { actions: queryActions }],
    ['analysisRequestComposer', AnalysisComposer, { actions: analysisActions }],
    ['phenoRunPanel', PhenoComposer, { actions: phenoActions }],
    ['phenoSetupDetails', PhenoSetup, { actions: shellActions.PhenoSetup }],
  ]) {
    const host = document.getElementById(id);
    if (host) flushSync(() => createRoot(host).render(<Component {...props} />));
  }
}
