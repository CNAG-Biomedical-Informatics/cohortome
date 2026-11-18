import React from 'react';

export function QuestionContext({ surface, onWorkspace, onGeneral }) {
  const analysis = surface === 'analysis';
  return (
    <div
      className="context-mode-switch"
      role="group"
      aria-label={analysis ? 'Analysis question context' : 'Question context'}
    >
      <button
        id={`${surface}ContextWorkspaceBtn`}
        onClick={onWorkspace}
        type="button"
        className="context-mode-option is-active"
        aria-pressed="true"
        title={
          analysis
            ? 'Use the current Analysis scope and governed workspace context.'
            : 'Use the active workspace and its governed dataset context.'
        }
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
        id={`${surface}ContextGeneralBtn`}
        onClick={onGeneral}
        type="button"
        className="context-mode-option"
        aria-pressed="false"
        title={
          analysis
            ? 'Ask the model without workspace, cohort, assay, or analysis context.'
            : 'Ask the model without workspace or dataset context.'
        }
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
  );
}
