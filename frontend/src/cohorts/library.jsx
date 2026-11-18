import React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import { Icon, Action, Exports } from './actions.jsx';
export function LibraryCard({ item }) {
  const date = new Date(item.created_at);
  return (
    <article className="cohort-library-card">
      <div className="cohort-card-top">
        <span className="cohort-card-symbol">
          <Icon name="cohort" />
        </span>
        <span className={`cohort-card-state ${item.available ? 'is-loaded' : ''}`}>
          {item.available ? 'Datasets loaded' : 'Datasets not loaded'}
        </span>
        <details className="cohort-card-menu cohort-card-manage">
          <summary aria-label={`Manage ${item.name}`} title="Manage cohort">
            <Icon name="more" />
          </summary>
          <div className="cohort-card-menu-items">
            <Action item={item} action="rename" icons>
              Rename
            </Action>
            <Action item={item} action="delete" icons>
              Delete
            </Action>
          </div>
        </details>
      </div>
      <h3>{item.name}</h3>
      <div className="cohort-library-datasets">
        {item.labels.map((label, i) => (
          <span key={i}>{label}</span>
        ))}
      </div>
      <dl className="cohort-card-counts">
        <div>
          <dt>Patients</dt>
          <dd>{Number(item.patient_count || 0).toLocaleString()}</dd>
        </div>
        <div>
          <dt>Samples</dt>
          <dd>{Number(item.sample_count || 0).toLocaleString()}</dd>
        </div>
      </dl>
      <div className="cohort-card-actions saved-cohort-actions">
        <Action item={item} action="inspect" icons>
          Members
        </Action>
        <Action item={item} action="clinical-summary" icons disabled={!item.available}>
          Apply to scope
        </Action>
        <details className="cohort-card-menu cohort-library-more">
          <summary>
            <Icon name="download" />
            Export
          </summary>
          <div className="cohort-card-menu-items">
            <Exports item={item} />
          </div>
        </details>
      </div>
      <div className="cohort-card-footer">
        <small>
          Created {Number.isNaN(date.getTime()) ? 'date unavailable' : date.toLocaleDateString()}
        </small>
        <div className="saved-cohort-actions">
          {item.available ? (
            <>
              <span className="cohort-card-use-label">Use in</span>
              <Action item={item} action="load-analysis" icons>
                Analysis
              </Action>
              <Action item={item} action="load-pheno" icons>
                Pheno-Ranker
              </Action>
            </>
          ) : (
            <Action item={item} action="load-datasets" icons>
              Add required datasets
            </Action>
          )}
        </div>
      </div>
    </article>
  );
}

export function createCohortLibraryView(host, pages, suggestions) {
  const root = createRoot(host);
  return {
    render(m) {
      root.render(
        <>
          {m.items.length ? (
            <div className="cohort-library-grid">
              {m.items.map((item) => (
                <LibraryCard key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <div className="empty">
              {m.hasItems
                ? 'No cohorts match your search.'
                : 'No accessible saved cohorts. Save a patient or sample selection to create one.'}
            </div>
          )}
          {suggestions &&
            createPortal(
              m.suggestions.map((item) => (
                <option key={item.id} value={item.name} label={item.labels.join(' · ')} />
              )),
              suggestions,
            )}
          {pages &&
            createPortal(
              m.total > m.pageSize ? (
                <>
                  <button
                    type="button"
                    className="query-chip"
                    data-page="-1"
                    disabled={m.page === 0}
                  >
                    Previous
                  </button>
                  <span>
                    {m.page * m.pageSize + 1}–{Math.min(m.total, (m.page + 1) * m.pageSize)} of{' '}
                    {m.total}
                  </span>
                  <button
                    type="button"
                    className="query-chip"
                    data-page="1"
                    disabled={(m.page + 1) * m.pageSize >= m.total}
                  >
                    Next
                  </button>
                </>
              ) : null,
              pages,
            )}
        </>,
      );
    },
  };
}
