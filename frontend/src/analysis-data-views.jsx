import React from 'react';
import { renderSupplemental } from './shared/view-root.js';
import { ModalityIcon } from './shared/modality-icon.jsx';
import { modalityColor } from '../../static/js/modalities.js';
import { formatAssayModality } from '../../static/js/assay_labels.js';

function Checks({ items = [], title, limit }) {
  return (
    !!items.length && (
      <div className="assay-card-section">
        <strong>{title}</strong>
        <div className="multimodal-issue-list">
          {items.slice(0, limit).map((item, index) => (
            <div key={index} className={`query-status ${item.severity === 'error' ? 'error' : ''}`}>
              {item.message || `${title} warning.`}
            </div>
          ))}
        </div>
      </div>
    )
  );
}
function Readiness({ modalities = [], issues = [] }) {
  const valid = (value) => value != null && Number.isFinite(Number(value)) && Number(value) >= 0;
  const max = Math.max(
    1,
    ...modalities
      .filter((item) => valid(item.patient_count))
      .map((item) => Number(item.patient_count)),
  );
  return (
    <>
      <section className="multimodal-coverage" />
      <div className="assay-card-section">
        <div className="assay-coverage-chart">
          <strong>Patients by data type · whole workspace</strong>
          {modalities.length ? (
            modalities.map((item, index) => (
              <div key={index} className="assay-coverage-row">
                <span>
                  <ModalityIcon modality={item.key} />
                  {item.label || item.key || 'Modality'}
                </span>
                <div className="assay-coverage-track" aria-hidden="true">
                  <i
                    style={{
                      width: `${valid(item.patient_count) ? (Number(item.patient_count) / max) * 100 : 0}%`,
                      background: modalityColor(item.key),
                    }}
                  />
                </div>
                <strong>
                  {valid(item.patient_count)
                    ? `${Number(item.patient_count).toLocaleString()} ${Number(item.patient_count) === 1 ? 'patient' : 'patients'}`
                    : 'Not reported'}
                </strong>
              </div>
            ))
          ) : (
            <p className="empty">No coverage reported.</p>
          )}
        </div>
        <p className="section-note">Patients may appear in several types.</p>
        <details>
          <summary>Detailed coverage counts</summary>
          <div className="assay-table-wrap">
            <table className="assay-table multimodal-readiness-table">
              <thead>
                <tr>
                  {[
                    'Modality',
                    'Resources',
                    'Patients',
                    'Samples',
                    'Features',
                    'Clinical overlap',
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {modalities.length ? (
                  modalities.map((item, index) => (
                    <tr key={index}>
                      <td>
                        <strong>{item.label || item.key || 'Modality'}</strong>
                      </td>
                      {[
                        Number(item.dataset_count || 0) + Number(item.study_count || 0),
                        item.patient_count || 0,
                        item.sample_count || 0,
                        item.feature_count || 0,
                        item.clinical_overlap_count || 0,
                      ].map((value, i) => (
                        <td key={i}>{String(value)}</td>
                      ))}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>No modalities found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </details>
      </div>
      <Checks title="Linkage checks" items={issues} limit={5} />
    </>
  );
}
function Missingness({ rows, count, columns }) {
  const table = (items) => (
    <div className="assay-table-wrap">
      <table className="assay-table">
        <thead>
          <tr>
            <th>Field / feature</th>
            <th>Available</th>
            <th>No linked value</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const column = columns.find((c) => c.key === item.key) || {},
              missing = Number(item.missing_count || 0);
            return (
              <tr key={index}>
                <td>
                  <ModalityIcon modality={column.modality || column.source || 'clinical'} />
                  {item.label || item.key || 'Field'}
                  <small className="matrix-field-source">
                    {column.dataset_name || column.source || ''}
                  </small>
                </td>
                <td>
                  {count - missing} / {count}
                </td>
                <td>
                  {missing}{' '}
                  <span className="section-note">({((missing / count) * 100).toFixed(1)}%)</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
  if (!count) return <p className="empty">No records available for this preview.</p>;
  if (!rows.length) return <p className="empty">No fields available for this preview.</p>;
  return (
    <div className="assay-card-section">
      <p className="section-note">
        {rows.length} fields checked · {rows.filter((r) => !Number(r.missing_count || 0)).length}{' '}
        complete. Largest gaps first.
      </p>
      {table(rows.slice(0, 6))}
      {rows.length > 6 && (
        <details>
          <summary>Show {rows.length - 6} more fields</summary>
          {table(rows.slice(6))}
        </details>
      )}
    </div>
  );
}
function Matrix({ source }) {
  const count = Number(source.metadata?.row_count || 0),
    groups = source.feature_groups || [];
  const rows = (source.missingness || [])
    .slice()
    .sort((a, b) => Number(b.missing_count || 0) - Number(a.missing_count || 0));
  return (
    <>
      <p className="section-note">
        Automatic preview: up to three features per assay, plus clinical fields. Independent of the
        patient selection above.
      </p>
      <details className="view-help matrix-preview-help">
        <summary
          aria-label="How feature availability is calculated"
          title="How feature availability is calculated"
        >
          ?
        </summary>
        <p>
          Counts refer to {count} matrix rows: clinical sample/visit records, or patients when no
          samples are listed. One patient can contribute several rows.
        </p>
        <p>
          Assay values require an exact sample ID match. “No linked value” can mean an absent
          measurement or an unmatched identifier—not that the patient lacks the assay. Empty
          clinical fields also count as unlinked values; a recorded zero counts as available.
        </p>
        <p>
          This preview is not a dataset-wide missingness estimate or a quality-control assessment.
          Use Coverage above to find patients with particular data types.
        </p>
      </details>
      <Missingness rows={rows} count={count} columns={source.columns || []} />
      <details className="assay-card-section">
        <summary>Feature groups and provenance</summary>
        <div className="assay-card-section">
          <strong>Provenance</strong>
          <div className="multimodal-feature-group-list">
            {groups.length ? (
              groups.map((item, index) => (
                <div key={index} className="multimodal-feature-group">
                  <strong>{item.label || item.dataset_name || 'Feature group'}</strong>
                  <span className="query-chip badge">
                    {formatAssayModality(item.modality || 'assay')}
                  </span>
                  <small>
                    {item.feature_count_selected || 0} columns ·{' '}
                    {item.exact_sample_match_count || 0} exact sample matches
                  </small>
                </div>
              ))
            ) : (
              <div className="empty">No feature groups selected.</div>
            )}
          </div>
        </div>
      </details>
      <Checks title="Matrix checks" items={source.warnings} limit={4} />
    </>
  );
}
export function renderReadinessView(host, model) {
  renderSupplemental(host, <Readiness {...model} />);
}
export function renderMatrixView(host, source) {
  renderSupplemental(host, <Matrix source={source} />);
}
