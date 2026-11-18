import React from 'react';
import { renderSupplemental } from './shared/view-root.js';
import { ClarID } from './clarid.jsx';

export function renderWelcomeView(host, canOpenDemo) {
  renderSupplemental(
    host,
    <section className="workspace-welcome">
      <h2>Explore a cohort</h2>
      <p>
        {canOpenDemo
          ? 'Open the synthetic demo to explore patients, assays and analyses, or choose your own datasets.'
          : 'Choose datasets to start exploring patients, assays and analyses.'}
      </p>
      <div className="saved-cohort-actions">
        {canOpenDemo && (
          <button type="button" className="primary-btn" data-open-demo="">
            Open demo
          </button>
        )}
        <button type="button" className="secondary-btn" data-choose-datasets="">
          Choose datasets
        </button>
      </div>
      <p role="status" />
    </section>,
  );
}
export function renderPatientRoster(host, { items, total, limit, compact, feedback }) {
  renderSupplemental(
    host,
    items.length ? (
      <>
        {feedback && (
          <div className="clarid-search-feedback" role="status">
            <strong>ClarID recognized</strong>
            <span>{feedback.summary}</span>
            <span>Patient {feedback.patientId}</span>
          </div>
        )}
        {total > limit && (
          <div className="section-note">
            Showing first {limit} of {total} matching patients. Use search to narrow the list.
          </div>
        )}
        {items.map((p) => (
          <div
            key={p.patient_id}
            className={`patient-card ${compact ? 'patient-card-compact' : ''} ${p.active ? 'active' : ''}`}
            data-patient-id={p.patient_id}
          >
            {compact ? (
              <>
                <div className="patient-card-compact-main">
                  <strong>{p.patient_id}</strong>
                  <span>
                    <ClarID clarid={p.clarid} />
                  </span>
                </div>
                <div className="patient-card-compact-meta">
                  <span>{p.recordText}</span>
                  <span>{p.sex || 'sex n/a'}</span>
                  <span>{p.evidence?.diseases?.count || 0} dx</span>
                </div>
              </>
            ) : (
              <>
                <div className="patient-card-identity">
                  <strong>{p.patient_id}</strong>
                  <ClarID clarid={p.clarid} compact={false} />
                </div>
                <div>
                  {p.datasetLabel && <span className="pill">{p.datasetLabel}</span>}
                  <span className="pill">{p.recordText}</span>
                  <span className="pill">{p.sex || 'sex: n/a'}</span>
                  <span className="pill">{p.evidence?.diseases?.count || 0} diseases</span>
                </div>
                <small>
                  {p.first_event_date || '?'} to {p.last_event_date || '?'}
                </small>
              </>
            )}
          </div>
        ))}
      </>
    ) : (
      <div className="empty">No patients match the current filter.</div>
    ),
  );
}
export function renderPatientDetail(host, { patient: p, datasetLabel, person, preview, clarid }) {
  const context = p.patient_context || {},
    visits = (p.visits || []).slice(0, 8),
    fragments = p.key_fragments || [];
  renderSupplemental(
    host,
    <>
      <div className="workspace-grid">
        <div className="workspace-card">
          <div className="patient-detail-identity">
            <p>
              <strong>{p.patient_id}</strong>
            </p>
            <ClarID clarid={clarid} compact={false} />
          </div>
          {datasetLabel && <p>Datasets: {datasetLabel}</p>}
          <p>
            Sex: {context.sex || 'n/a'} | DOB: {context.date_of_birth || 'n/a'} | Vital status:{' '}
            {context.vital_status || 'n/a'}
          </p>
          <p>Sources: {(context.source_files || []).join(', ') || 'n/a'}</p>
          <h3>Available evidence</h3>
          <div className="evidence-grid">
            {[
              ['diseases', 'Diseases'],
              ['phenotypic_features', 'Phenotypes'],
              ['measures', 'Measures'],
              ['treatments', 'Treatments'],
              ['procedures', 'Procedures'],
              ['exposures', 'Exposures'],
            ].map(([key, label]) => {
              const bucket = p.evidence?.[key] || {};
              return (
                <div key={key} className="evidence-card">
                  <strong>{label}</strong>
                  <div>{bucket.count || 0} items</div>
                  <small>{(bucket.examples || []).slice(0, 2).join(' | ') || 'No examples'}</small>
                </div>
              );
            })}
          </div>
        </div>
        <div className="workspace-card">
          <h3>{person ? 'Clinical record overview' : 'Visit overview'}</h3>
          <ul className="mini-list">
            {visits.length ? (
              visits.map((visit, index) => (
                <li key={index}>
                  <div>
                    <strong>{visit.visit_id}</strong>
                    <small>
                      {visit.event_date || 'undated'} ·{' '}
                      {visit.diagnosis || visit.event_type || 'event'}
                    </small>
                  </div>
                  <span>{visit.key_fragments?.length || 0} fragments</span>
                </li>
              ))
            ) : (
              <li>
                <small>No {person ? 'clinical records' : 'visits'} found.</small>
              </li>
            )}
          </ul>
        </div>
      </div>
      <div className="workspace-card" style={{ marginTop: 16 }}>
        <h3>Key Fragments</h3>
        <div className="fragment-grid">
          {fragments.length ? (
            fragments.map((fragment, index) => (
              <div key={index} className="fragment-card">
                <strong>{fragment.label}</strong>
                <div>
                  <span className="pill">{fragment.category}</span>
                  <span className="pill">{fragment.visit_id}</span>
                </div>
                <small>
                  {fragment.source_file}#{fragment.record_index} · {fragment.path}
                </small>
              </div>
            ))
          ) : (
            <div className="empty">No key fragments available.</div>
          )}
        </div>
        <details>
          <summary>Show structured patient preview</summary>
          <pre>{JSON.stringify(preview, null, 2)}</pre>
        </details>
      </div>
    </>,
  );
}
