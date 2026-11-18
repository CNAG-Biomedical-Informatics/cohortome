import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

function Icon({ kind }) {
  return (
    <span className="button-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {kind === 'save' ? (
          <>
            <path d="M5 5h14v14H5z" />
            <path d="M8 5v6h8V5" />
            <path d="M9 19v-5h6v5" />
          </>
        ) : kind === 'copy' ? (
          <>
            <rect x="9" y="9" width="10" height="10" rx="2" />
            <path d="M5 15V5a2 2 0 0 1 2-2h10" />
          </>
        ) : (
          <>
            <path d="M8 17 18 7" />
            <path d="M9 7h9v9" />
            <path d="M5 5h6" />
            <path d="M5 11v8h8" />
          </>
        )}
      </svg>
    </span>
  );
}
export function QueryActions({ model: m }) {
  if (!m) return null;
  const button = (action, label, classes = '', icon) => (
    <button type="button" className={`query-chip ${classes}`} data-query-action={action}>
      {icon && <Icon kind={icon} />}
      <span className="query-action-label">{label}</span>
    </button>
  );
  return (
    <div className="query-actions query-actions-inline" style={{ marginTop: 12 }}>
      {m.openAnalysis &&
        button('use-analysis', 'Open in Analysis', 'action query-workflow-primary', 'open')}
      {m.saveCohort &&
        button(
          'save-cohort',
          'Save cohort',
          'query-chip-deterministic query-workflow-secondary',
          'save',
        )}
      {m.moreActions ? (
        <details className="query-inline-actions">
          <summary>
            <span>More options</span>
          </summary>
          <div className="query-actions">
            {m.canSummarize && button('clinical-summary', 'Apply to scope')}
            {m.canCopyIds && button('copy-ids', 'Copy patient IDs', 'query-chip-planner', 'copy')}
            {m.canUsePheno && button('use-pheno', 'Open in Pheno-Ranker', 'action', 'open')}
            {m.incompatiblePheno && (
              <span className="query-chip badge">
                This result is grouped at patient level. Pheno-Ranker needs the original record IDs
                or timepoints.
              </span>
            )}
          </div>
        </details>
      ) : m.resultHandle && m.saveCohort ? (
        <span className="section-note-inline">
          Save this result as a cohort before using it in Pheno-Ranker.
        </span>
      ) : null}
    </div>
  );
}
export function createQueryActionsView(host) {
  const root = createRoot(host);
  return {
    render(model) {
      flushSync(() => root.render(<QueryActions model={model} />));
    },
  };
}
