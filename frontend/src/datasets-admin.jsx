import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ModalityIcon } from './assay-overview.jsx';

function BulkToolbar({ bulk }) {
  const all = useRef(null),
    menu = useRef(null);
  const count = bulk.selected.size;
  useEffect(() => {
    all.current.indeterminate = count > 0 && count < bulk.total;
  }, [count, bulk.total]);
  useEffect(() => {
    const close = (event) => {
      if (!menu.current?.contains(event.target)) menu.current.open = false;
    };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);
  useEffect(() => {
    if (!count) menu.current.open = false;
  }, [count]);
  const action = (fn) => () => {
    menu.current.open = false;
    fn();
  };
  return (
    <div className="dataset-bulk-toolbar">
      <label>
        <input
          ref={all}
          type="checkbox"
          data-select-all=""
          checked={bulk.total > 0 && count === bulk.total}
          disabled={!bulk.total}
          onChange={(e) => bulk.selectAll(e.target.checked)}
        />{' '}
        Select all
      </label>
      <div className="dataset-bulk-selection" data-selection="" hidden={!count}>
        <span data-count="" aria-live="polite">
          {count} selected
        </span>
        <details
          ref={menu}
          className="dataset-bulk-menu"
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault();
              menu.current.open = false;
              menu.current.querySelector('summary').focus();
            }
          }}
        >
          <summary>
            Actions <span aria-hidden="true">▾</span>
          </summary>
          <div className="dataset-bulk-options">
            <span className="dataset-bulk-group">Data</span>
            <button
              type="button"
              data-prepare=""
              disabled={!bulk.preparable}
              title={
                bulk.preparable
                  ? 'Rebuild stores that are not ready.'
                  : 'Selected stores are already ready or being built.'
              }
              onClick={action(bulk.prepare)}
            >
              {bulk.preparable ? `Rebuild DuckDB (${bulk.preparable})` : 'Rebuild DuckDB'}
            </button>
            <span className="dataset-bulk-group">Permissions</span>
            <button type="button" data-edit="" disabled={!count} onClick={action(bulk.review)}>
              Change AI permissions…
            </button>
          </div>
        </details>
        <button
          type="button"
          className="query-chip secondary-btn"
          data-clear=""
          onClick={() => {
            bulk.selectAll(false);
            all.current.focus();
          }}
        >
          Clear
        </button>
      </div>
      <span role="status" data-status="">
        {bulk.notice}
      </span>
    </div>
  );
}

function DatasetCard({ d, desktop, bulk, onDicom }) {
  const values = () => ({
    visibility: d.visibility,
    classification: d.dataClassification,
    groups: d.allowedGroups.join(', '),
    users: d.allowedUsers.join(', '),
    'query-granularity': d.granularity,
    'ai-provider-access': d.aiAccess,
  });
  const [draft, setDraft] = useState(values);
  // Feedback and bulk selection renders must not discard unsaved edits.
  useEffect(() => setDraft(values()), [d.dataset]);
  const field = (name) => ({
    id: `dataset-${name}-${d.datasetId}`,
    [`data-dataset-${name}`]: d.datasetId,
    value: draft[name],
    onChange: (e) => setDraft((prev) => ({ ...prev, [name]: e.target.value })),
  });
  const select = (name, label, options, hidden = false) => (
    <div className={`dataset-picker-access-row${hidden ? ' is-hidden' : ''}`}>
      <label htmlFor={`dataset-${name}-${d.datasetId}`}>{label}</label>
      <select {...field(name)}>
        {options.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </div>
  );
  const tags = (
    <>
      <span className="dataset-picker-tag">{d.datasetId}</span>
      <span className="dataset-picker-tag">{d.access}</span>
      <span className="dataset-picker-tag">{d.dataClassification} data</span>
    </>
  );
  return (
    <details
      className={`dataset-admin-card${bulk.selected.has(d.datasetId) ? ' is-bulk-selected' : ''}`}
      data-dataset-admin-card={d.datasetId}
    >
      <summary className="dataset-admin-summary">
        <input
          type="checkbox"
          value={d.datasetId}
          aria-label={`Select ${d.name}`}
          checked={bulk.selected.has(d.datasetId)}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => bulk.toggle(d.datasetId, e.target.checked)}
        />
        <span className="dataset-admin-summary-main">
          <span className="dataset-picker-title">{d.name}</span>
          <span className="dataset-picker-meta">{tags}</span>
        </span>
        <span
          className={`dataset-picker-tag ${d.storeReady ? 'dataset-picker-tag-ready' : d.storeState === 'failed' ? 'dataset-picker-tag-danger' : 'dataset-picker-tag-warning'}`}
        >
          {d.storeLabel}
        </span>
      </summary>
      <div className="dataset-admin-body">
        <button
          type="button"
          className="query-chip secondary-btn dataset-about-button"
          data-dataset-about={d.datasetId}
        >
          ⓘ About this dataset
        </button>
        <div className="dataset-picker-title">
          <span>{d.name}</span>
        </div>
        <div className="dataset-picker-meta">
          {tags}
          {d.contentTags.map((tag, i) => (
            <span key={i} className="dataset-picker-tag dataset-picker-tag-content">
              {tag}
            </span>
          ))}
          {!desktop && !!d.allowedGroups.length && (
            <span className="dataset-picker-tag">groups: {d.allowedGroups.join(', ')}</span>
          )}
          {!desktop && !!d.allowedUsers.length && (
            <span className="dataset-picker-tag">users: {d.allowedUsers.join(', ')}</span>
          )}
        </div>
        {d.description && <div className="dataset-picker-description">{d.description}</div>}
        <div className="dataset-picker-access">
          <div className="dataset-policy-section">
            <div className="dataset-policy-heading">
              {desktop ? 'Data classification and detail' : 'Access and classification'}
            </div>
            <div className="section-note">
              {desktop
                ? 'This desktop workspace has one local owner. Classification and model policies still control how data may be shared.'
                : 'Visibility controls who can use the dataset inside COHORTome. Classification controls whether its data may be sent outside this deployment.'}
            </div>
            {select(
              'visibility',
              'Visibility',
              [
                ['all_authenticated', 'All authenticated users'],
                ['restricted', 'Restricted'],
                ['admin_only', 'Admin only'],
              ],
              desktop,
            )}
            {select('classification', 'Data classification', [
              ['private', 'Private data'],
              ['public', 'Public data'],
            ])}
            {['groups', 'users'].map((name) => (
              <div key={name} className={`dataset-picker-access-row${desktop ? ' is-hidden' : ''}`}>
                <label htmlFor={`dataset-${name}-${d.datasetId}`}>Allowed {name}</label>
                <input
                  {...field(name)}
                  placeholder={name === 'groups' ? 'e.g. cnag, ibd-team' : 'e.g. mrueda, alice'}
                />
              </div>
            ))}
            {select('query-granularity', 'In-app detail ceiling', [
              ['summary', 'Summary only'],
              ['detailed', 'Detailed allowed'],
            ])}
            <div className={`dataset-picker-access-row${desktop ? ' is-hidden' : ''}`}>
              <label>Users with access</label>
              <div className="identity-tags">
                {(d.effectiveUsers.length
                  ? d.effectiveUsers
                  : ['No currently configured local users match this policy']
                ).map((label, i) => (
                  <span key={i} className="identity-tag">
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="dataset-policy-section dataset-policy-section-muted">
            <div className="dataset-policy-heading">AI Providers</div>
            <div className="section-note">
              Sets the maximum context an eligible provider may receive. Private data is never sent
              to a provider marked external.
            </div>
            {select('ai-provider-access', 'Provider context ceiling', [
              ['detailed_allowed', 'Detailed allowed'],
              ['safe_summary', 'Safe summary'],
              ['blocked', 'Blocked'],
            ])}
            <div className="dataset-picker-access-row">
              <label>Current behavior</label>
              <div className="dataset-policy-placeholder">{d.behavior}</div>
            </div>
          </div>
          <div className="dataset-policy-section dataset-policy-section-muted">
            <div className="dataset-policy-heading">Query store</div>
            <div className="section-note">
              COHORTome builds this local DuckDB index automatically when a dataset is added or
              first used. Rebuild it only after source files or mappings change.
            </div>
            <div className="dataset-picker-access-row">
              <label>Current status</label>
              <div className="identity-tags">
                <span className="identity-tag">{d.storeLabel}</span>
              </div>
            </div>
            <div className="dataset-picker-access-row">
              <label>Details</label>
              <div className="dataset-policy-placeholder">{d.storeDetail}</div>
            </div>
          </div>
          <section className="dataset-imaging-setup" aria-label="Imaging">
            <div className="dataset-imaging-copy">
              <div className="dataset-policy-heading">
                <ModalityIcon modality="imaging" /> Imaging
              </div>
              <div className="section-note">Connect existing DICOM files; files stay in place.</div>
            </div>
            <button
              type="button"
              className="query-chip"
              data-dataset-dicom={d.datasetId}
              onClick={() => onDicom(d.datasetId)}
            >
              Link folder…
            </button>
          </section>
          <div className="dataset-picker-access-actions">
            <button type="button" className="secondary-btn" data-dataset-save={d.datasetId}>
              Save settings
            </button>
            <button
              type="button"
              className="secondary-btn"
              data-dataset-prepare={d.datasetId}
              disabled={d.storeBuilding}
            >
              {d.storeButtonLabel}
            </button>
            <button
              type="button"
              className="query-chip danger-btn"
              data-dataset-remove={d.datasetId}
              disabled={d.bundled}
              title={d.bundled ? 'Bundled datasets cannot be removed.' : undefined}
            >
              Remove dataset…
            </button>
          </div>
          {d.feedback?.text && (
            <div
              className={`dataset-admin-feedback${d.feedback.tone === 'error' ? ' is-error' : ''}`}
            >
              {d.feedback.text}
            </div>
          )}
        </div>
      </div>
    </details>
  );
}

export function createDatasetsAdminView(host, onDicom) {
  const root = createRoot(host);
  return {
    render({ datasets = [], desktop = false, bulk, message }) {
      root.render(
        message ? (
          <div className="empty">{message}</div>
        ) : (
          <>
            <BulkToolbar bulk={bulk} />
            {datasets.map((d) => (
              <DatasetCard
                key={d.datasetId}
                d={d}
                desktop={desktop}
                bulk={bulk}
                onDicom={onDicom}
              />
            ))}
          </>
        ),
      );
    },
  };
}
