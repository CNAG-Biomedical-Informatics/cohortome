import React, { useLayoutEffect, useRef } from 'react';

export function ArtifactDownloads({ title = 'Result files', artifacts = [] }) {
  const files = artifacts.filter(
    (item) => item && String(item.name || '').trim() && String(item.url || '').trim(),
  );
  if (!files.length) return null;
  return (
    <details className="query-section analysis-artifact-downloads">
      <summary>
        <span className="analysis-section-label">
          <svg
            className="analysis-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
          >
            <path d="M4 4h16v16H4zM4 10h16M10 4v16" />
          </svg>
          <span>{title}</span>
        </span>
        <span className="analysis-file-count">
          {files.length} file{files.length === 1 ? '' : 's'}
        </span>
      </summary>
      <ul className="analysis-result-files">
        {files.map((item, index) => {
          const name = String(item.name).trim(),
            extension = name.split('.').pop().toUpperCase();
          const format =
            /^[A-Z0-9]{1,8}$/.test(extension) && name.includes('.') ? extension : 'FILE';
          return (
            <li key={index}>
              <a
                className="analysis-result-file"
                href={String(item.url).trim()}
                target="_blank"
                rel="noopener"
                aria-label={`${name} — open in a new tab`}
              >
                <span className="analysis-file-format" aria-hidden="true">
                  {format}
                </span>
                <span className="analysis-file-name">{name}</span>
                <span className="analysis-file-action" aria-hidden="true">
                  Open
                </span>
              </a>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

export function Plot({ id, height }) {
  const host = useRef(null);
  useLayoutEffect(() => {
    const node = host.current;
    return () => {
      if (node?.classList.contains('js-plotly-plot')) window.Plotly?.purge?.(node);
    };
  }, [id]);
  // Plotly owns the children; React owns the stable host and its lifecycle.
  return <div ref={host} className="analysis-plot-frame" id={id} style={{ height }} />;
}

export function EvidenceCard({ id, title, items }) {
  if (!items.length)
    return (
      <div className="viz-card">
        <h3>{title}</h3>
        <div className="empty">No data.</div>
      </div>
    );
  return (
    <section className="viz-card analysis-evidence-card">
      <h3>{title}</h3>
      <div className="analysis-evidence-layout">
        <div>
          <Plot id={id} height={Math.max(240, items.length * 28 + 90)} />
        </div>
        <div className="assay-table-wrap">
          <table className="assay-table">
            <caption className="section-note">Values shown in the plot</caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index}>
                  <th scope="row">{String(item.label)}</th>
                  <td>{String(item.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
