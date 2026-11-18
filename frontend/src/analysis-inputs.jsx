import React from 'react';
import { renderSupplemental as render } from './shared/view-root.js';
import { useLayoutEffect, useRef } from 'react';

export function renderScopeSource(host, side, cohort) {
  render(
    host,
    cohort ? (
      <>
        <span className="query-chip badge">Cohort {side.toUpperCase()} source</span>{' '}
        <button
          type="button"
          className="query-chip query-chip-deterministic"
          data-analysis-clear-saved-cohort={side}
        >
          {cohort.name || 'Saved cohort'} ×
        </button>
      </>
    ) : null,
  );
}

function AssayChoice({ item }) {
  const input = useRef(null);
  // Native change delegation owns this form. Do not reset the user's click
  // before that handler has read it; reconcile restored selections on render.
  useLayoutEffect(() => {
    input.current.checked = item.checked;
  }, [item]);
  return (
    <label className="assay-dataset-option">
      <input ref={input} type="checkbox" value={item.value} defaultChecked={item.checked} />
      <span>
        <strong>{item.label}</strong>
        <small>{item.description}</small>
      </span>
    </label>
  );
}

export function renderAssayChoices(host, groups, empty) {
  render(
    host,
    groups.length ? (
      groups.map((group) => (
        <div key={group.label} className="assay-modality-group">
          <div className="assay-modality-group-title">{group.label}</div>
          {group.items.map((item) => (
            <AssayChoice key={item.value} item={item} />
          ))}
        </div>
      ))
    ) : (
      <div className="empty">{empty}</div>
    ),
  );
}

export function renderAssociationExamples(host, visible) {
  render(
    host,
    visible ? (
      <>
        <strong>Try a synthetic comparison</strong>
        <p>
          These examples explore how two simulated measurements vary together. They are not
          biological findings.
        </p>
        <button
          type="button"
          className="query-chip"
          data-example-x="CD4_T_cells_fraction"
          data-example-y="CRP_mg_L"
        >
          CD4 T cells × C-reactive protein
        </button>
        <p>Compare a cell fraction with a soluble protein measurement.</p>
        <button
          type="button"
          className="query-chip"
          data-example-x="B_cells_fraction"
          data-example-y="Anti_dsDNA_IU_mL"
        >
          B cells × anti-double-stranded DNA antibodies
        </button>
        <p>
          Compare a cell fraction with an antibody measurement. Neither example runs until you
          review it in Analysis.
        </p>
      </>
    ) : null,
  );
}
