import React from 'react';
import { renderSupplemental as render } from './shared/view-root.js';

export function renderPhenoReadinessView(host, title, parts) {
  render(
    host,
    <>
      <strong>{title}</strong>
      <div>{parts.join(' · ')}</div>
    </>,
  );
}

export function renderPhenoFiles(host, labels = [], empty = 'None') {
  render(
    host,
    labels.length ? (
      <div className="file-label-row">
        <span className="query-chip badge">Active workspace files ({labels.length})</span>
        {labels.map((label, index) => (
          <span key={index} className="query-chip query-chip-deterministic badge">
            {label}
          </span>
        ))}
      </div>
    ) : (
      <>
        <span className="query-chip badge">Active workspace files</span>{' '}
        <span className="section-note-inline">{empty}</span>
      </>
    ),
  );
}

export function renderPhenoLegend(host, items) {
  render(
    host,
    items.map((item) => (
      <span key={item.key} className="pheno-cohort-chip" style={{ '--cohort-color': item.color }}>
        <span className="pheno-cohort-chip-swatch" aria-hidden="true" />
        {item.label}
      </span>
    )),
  );
}

export function renderPhenoRunning(host, { queued, label, active }) {
  render(
    host,
    <>
      <span className="button-spinner" aria-hidden="true" />
      <div>
        <strong>{queued ? 'Pheno-Ranker queued' : 'Pheno-Ranker is running'}</strong>
        <span>
          {queued
            ? 'Waiting for a worker. This run has not started yet.'
            : 'Your request is being processed. Results will appear when it finishes.'}
          {label ? ` · ${label}` : ''}
        </span>
      </div>
      {active && (
        <button type="button" className="query-chip" data-pheno-view-job="">
          View job
        </button>
      )}
    </>,
  );
}
