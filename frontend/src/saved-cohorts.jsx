import { Icon, Action, Exports } from './cohorts/actions.jsx';
export { createCohortLibraryView } from './cohorts/library.jsx';
export { requestCohortName, inspectCohortMembers } from './cohorts/dialogs.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';

function SavedCohorts({ items, mode, notice }) {
  return (
    <>
      {notice && <div className="saved-cohort-inline-status">{notice}</div>}
      {!items.length ? (
        <div className="empty">No saved cohorts yet.</div>
      ) : (
        <div className="saved-cohort-list">
          {items.map((item) => (
            <div className="saved-cohort-card" key={item.id}>
              <strong>{item.name || 'Unnamed cohort'}</strong>
              <small>
                {item.patientCount} patients • {item.sampleCount} samples • source:{' '}
                {item.source?.kind || 'manual'}
              </small>
              {!!item.datasetLabels.length && <small>{item.datasetLabels.join(', ')}</small>}
              <small>{item.preview}</small>
              <div className="saved-cohort-actions">
                <Action item={item} action="clinical-summary">
                  Apply to scope
                </Action>
                <Action
                  item={item}
                  action={mode === 'pheno' ? 'load-pheno' : 'load-analysis'}
                  className="action"
                >
                  {mode === 'pheno' ? 'Use in Pheno-Ranker' : 'Use as Cohort A'}
                </Action>
                {mode === 'analysis' && (
                  <Action item={item} action="load-analysis-b" className="action">
                    Use as Cohort B
                  </Action>
                )}
                <Action item={item} action="copy">
                  Copy IDs
                </Action>
                <Action item={item} action="rename">
                  Rename
                </Action>
                <Exports item={item} />
                {item.active && (
                  <span
                    className="query-chip badge"
                    title="Detach this cohort from the current Analysis or Pheno state before deleting it here."
                  >
                    In use here
                  </span>
                )}
                <Action
                  item={item}
                  action="delete"
                  disabled={item.active}
                  title={
                    item.active
                      ? 'Detach this cohort from the current Analysis or Pheno state before deleting it here.'
                      : undefined
                  }
                >
                  Delete
                </Action>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
export function createSavedCohortsView(host) {
  const root = createRoot(host);
  return {
    render(model) {
      root.render(<SavedCohorts {...model} />);
    },
  };
}
export function createCohortReferencesView(host) {
  const root = createRoot(host);
  return {
    render(items) {
      root.render(
        items.length ? (
          <div className="saved-cohort-actions">
            <span className="query-chip badge">Separate references</span>
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                className="query-chip query-chip-deterministic"
                data-pheno-selected-cohort-id={item.id}
              >
                {item.name || 'Unnamed cohort'} ×
              </button>
            ))}
          </div>
        ) : (
          'No saved cohorts attached as separate references.'
        ),
      );
    },
  };
}
