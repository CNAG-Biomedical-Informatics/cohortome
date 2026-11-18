import React from 'react';
import { renderSupplemental as render } from './shared/view-root.js';

function AssayScope({ scope: s }) {
  const values = Array.isArray(s.values) ? s.values : [];
  const number = (value) => (typeof value === 'number' ? value.toFixed(1) : 'n/a');
  return (
    <div className="assay-scope-card">
      <h4>{s.label || 'Scope'}</h4>
      <div className="assay-stats">
        {[
          `Samples: ${s.sample_count || 0}`,
          `Patients: ${s.patient_count || 0}`,
          `Mean: ${number(s.mean)}`,
          `Median: ${number(s.median)}`,
          `Range: ${s.min ?? 'n/a'} to ${s.max ?? 'n/a'}`,
        ].map((text) => (
          <span key={text} className="query-chip badge">
            {text}
          </span>
        ))}
      </div>
      {values.length ? (
        <>
          <div className="assay-table-wrap">
            <table className="assay-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Sample</th>
                  <th>Raw count</th>
                </tr>
              </thead>
              <tbody>
                {values.slice(0, 8).map((item, index) => (
                  <tr key={index}>
                    <td>{item.patient_id}</td>
                    <td>{item.sample_id}</td>
                    <td>{String(item.raw_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {values.length > 8 && (
            <div className="section-note">Showing 8 of {values.length} measurements.</div>
          )}
        </>
      ) : (
        <div className="empty">No assay samples matched this scope for the selected gene.</div>
      )}
    </div>
  );
}

export function renderExpressionPreview(host, payloads = []) {
  render(
    host,
    payloads.length
      ? payloads.map((item, index) => {
          const title = [item.gene_id, item.gene_symbol, item.gene_name]
            .map((value) => String(value || '').trim())
            .filter(Boolean)
            .join(' • ');
          return (
            <div key={index} className="transcriptomics-expression-card">
              <div className="assay-result-header">
                <strong>
                  {item.ensembl_url ? (
                    <a
                      className="assay-result-gene-link"
                      href={item.ensembl_url}
                      target="_blank"
                      rel="noopener"
                      title={title}
                    >
                      {item.gene_id}
                    </a>
                  ) : (
                    <span title={title}>{item.gene_id}</span>
                  )}
                </strong>
                {item.gene_symbol && item.gene_symbol !== item.gene_id && (
                  <span className="query-chip badge">{item.gene_symbol}</span>
                )}
                <span className="query-chip badge">{item.dataset_name}</span>
              </div>
              <div className="assay-result-grid">
                <AssayScope scope={item.scope_a} />
                {item.scope_b && <AssayScope scope={item.scope_b} />}
              </div>
            </div>
          );
        })
      : 'No transcriptomics expression summary yet.',
  );
}
