import React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import { ModalityIcon } from './assay-overview.jsx';
import { modalityLabel } from '../../static/js/modalities.js';

const types = {
  included: { label: 'Included', path: 'M5 12l4 4L19 6' },
  archive: { label: 'Ready to install', path: 'M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5' },
  source: { label: 'Fetch & prepare', path: 'M12 3v9m-3-3 3 3 3-3M5 16l3 3-3 3M11 19h8' },
};
const modeOf = (r) => (types[r.install_mode] ? r.install_mode : 'archive');
function TypeIcon({ mode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={types[mode].path} />
    </svg>
  );
}
function safeLink(value) {
  try {
    const u = new URL(value);
    return ['https:', 'http:'].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
function Resource({ r, repository, busy, category }) {
  const mode = modeOf(r),
    source = safeLink(r.source_page);
  return (
    <article
      className={`resource-card${r.included ? ' resource-card-included' : ''}`}
      data-install-mode={mode}
      hidden={category !== 'all' && category !== mode}
    >
      <div className="resource-card-heading">
        <span className="resource-card-symbol">
          <ModalityIcon modality={r.synthetic ? 'clinical' : 'assay'} />
        </span>
        <div>
          <h4>{r.name}</h4>
          <span className="resource-card-meta">
            {mode === 'included'
              ? 'No download needed'
              : `${((r.source_bytes || r.archive_bytes) / 1e6).toFixed(2)} MB${mode === 'source' ? ' source download' : ''}`}{' '}
            <span aria-hidden="true">·</span> {r.version}
            {r.synthetic ? ' · Synthetic' : ''}
          </span>
        </div>
        <span className="resource-kind resource-install-kind">
          <TypeIcon mode={mode} />
          {types[mode].label}
        </span>
      </div>
      <p className="resource-description">{r.description}</p>
      <div className="resource-modalities" aria-label={r.modalities}>
        {(r.modality_keys || []).map((key) => (
          <span key={key}>
            <ModalityIcon modality={key} />
            {modalityLabel(key)}
          </span>
        ))}
      </div>
      <div className="resource-card-bottom">
        <details className="view-help">
          <summary>Source &amp; terms</summary>
          <p>{r.terms}</p>
          {source && (
            <a href={source} target="_blank" rel="noopener noreferrer">
              {r.source_label} study record
            </a>
          )}
          <a
            href={`https://github.com/${repository}/tree/main/datasets/${encodeURIComponent(r.dataset_id)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Preparation and source documentation
          </a>
        </details>
        <button
          type="button"
          className={r.included ? 'resource-included' : 'resource-install-button'}
          data-resource={r.dataset_id}
          data-source={mode === 'source'}
          data-included={!!r.included}
          disabled={busy || r.included || r.compatible === false}
        >
          {r.included
            ? '✓ Included'
            : r.compatible === false
              ? 'Requires app update'
              : mode === 'source'
                ? '↓ Fetch and prepare'
                : '↓ Download and install'}
        </button>
      </div>
    </article>
  );
}
export function createResourcesView(host, filters) {
  const root = createRoot(host);
  return {
    render({ resources = [], repository = '', busy = false, category = 'all', loading = false }) {
      root.render(
        <>
          {loading ? (
            <p className="section-note">Loading catalogue…</p>
          ) : (
            resources
              .slice()
              .sort((a, b) => Number(!!a.included) - Number(!!b.included))
              .map((r) => (
                <Resource
                  key={r.dataset_id}
                  r={r}
                  repository={repository}
                  busy={busy}
                  category={category}
                />
              ))
          )}
          {filters &&
            createPortal(
              loading
                ? null
                : ['all', ...Object.keys(types)].map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className="query-chip"
                      data-category={mode}
                      aria-pressed={category === mode}
                    >
                      {mode !== 'all' && <TypeIcon mode={mode} />}{' '}
                      {mode === 'all' ? 'All' : types[mode].label}
                      <span>
                        {resources.filter((r) => mode === 'all' || modeOf(r) === mode).length}
                      </span>
                    </button>
                  )),
              filters,
            )}
        </>,
      );
    },
  };
}
