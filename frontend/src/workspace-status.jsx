import React from 'react';
import { renderSupplemental as render } from './shared/view-root.js';

export function renderDatasetNames(host, names) {
  render(
    host,
    (names.length ? names : ['No active datasets']).map((name, index) => (
      <li key={index}>{name}</li>
    )),
  );
}

export function renderLoadIcon(host, loading) {
  render(
    host,
    loading ? (
      <span className="button-spinner" aria-hidden="true" />
    ) : (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 3v12" />
        <path d="m7 10 5 5 5-5" />
        <path d="M5 21h14" />
      </svg>
    ),
  );
}

export function renderWorkspaceNotice(host, { kind, label, detail, retry }) {
  render(
    host,
    <div
      className={`workspace-notice workspace-notice-${kind}`}
      data-workspace-state={kind}
      role="status"
      aria-live="polite"
      aria-busy={kind === 'loading'}
    >
      <strong>
        {kind === 'loading'
          ? `Loading ${label.toLowerCase()}`
          : kind === 'empty'
            ? 'No patient records'
            : `${label} unavailable`}
      </strong>
      <p>{detail}</p>
      {retry && (
        <button type="button" className="query-chip" data-dashboard-retry="true" onClick={retry}>
          Retry dashboard
        </button>
      )}
    </div>,
  );
}
