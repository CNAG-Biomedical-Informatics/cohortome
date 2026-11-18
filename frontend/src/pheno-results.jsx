import { Activity } from './activity.jsx';
import React, { useLayoutEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

function safeUrl(value) {
  try {
    const u = new URL(value, window.location.href);
    return ['http:', 'https:'].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
function Output({ model: m }) {
  if (m.kind === 'files')
    return m.files?.length ? (
      <ul className="pheno-file-list">
        {m.files.map((file, i) => (
          <li key={i}>
            {safeUrl(file.url) ? (
              <a href={safeUrl(file.url)} target="_blank" rel="noreferrer">
                {file.name}
              </a>
            ) : (
              file.name
            )}{' '}
            ({file.size} bytes)
          </li>
        ))}
      </ul>
    ) : (
      <div className="empty">No output files yet.</div>
    );
  if (m.kind === 'text')
    return (
      <>
        {m.note && <div className="section-note">{m.note}</div>}
        <pre>{m.text}</pre>
      </>
    );
  if (m.kind === 'table')
    return (
      <>
        <div className="section-note">{m.note}</div>
        <div className="pheno-output-table-wrap">
          <table className="pheno-output-table">
            <thead>
              <tr>
                {m.headers.map((cell, i) => (
                  <th key={i}>
                    <button
                      type="button"
                      className="pheno-sort-btn"
                      data-pheno-sort-index={i}
                      data-active={i === m.sortIndex ? 'true' : 'false'}
                    >
                      {cell}
                      {i === m.sortIndex ? (m.sortDirection === 'asc' ? ' ▲' : ' ▼') : ''}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {m.rows.map(({ row, key, referenceId, targetId, selected }) => (
                <tr
                  key={key}
                  className={
                    m.interactive ? `is-clickable${selected ? ' is-selected' : ''}` : undefined
                  }
                  data-pheno-reference-id={m.interactive ? referenceId : undefined}
                  data-pheno-target-id={m.interactive ? targetId : undefined}
                >
                  {row.map((cell, i) => (
                    <td key={i}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  if (m.kind === 'activity') return <Activity {...m.activity} />;
  return <div className="empty">{m.message}</div>;
}
function PlotCard({ kind }) {
  const host = useRef(null),
    graph = kind === 'graph',
    heatmap = kind === 'heatmap';
  const name = { mds: 'MDS', umap: 'UMAP', graph: 'Graph', heatmap: 'Heatmap' }[kind];
  const prefix = `pheno${{ mds: 'Mds', umap: 'Umap', graph: 'Graph', heatmap: 'Heatmap' }[kind]}`;
  useLayoutEffect(() => {
    const node = host.current;
    return () => {
      node?.querySelectorAll('.js-plotly-plot').forEach((plot) => window.Plotly?.purge?.(plot));
      const plot = node?.querySelector('.pheno-graph-plot');
      plot?._cy?.destroy();
    };
  }, []);
  return (
    <details
      ref={host}
      className="pheno-preview-card pheno-preview-card-full pheno-preview-details"
      open
    >
      <summary className="pheno-preview-summary">
        <strong>Interactive {name}</strong>
      </summary>
      <div className="pheno-preview-body">
        {!heatmap && (
          <div className="pheno-result-card-toolbar">
            <div className="pheno-actions pheno-actions-secondary">
              {[
                ['analysis', 'Open selection in Analysis'],
                ['save-cohort', 'Save cohort'],
                ['copy', 'Copy selected IDs'],
              ].map(([action, label]) => (
                <button
                  key={action}
                  type="button"
                  className={`query-chip${action === 'save-cohort' ? ' query-chip-deterministic' : ''}`}
                  data-pheno-plot-action={action}
                  data-pheno-plot-kind={kind}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
        {graph && (
          <div className="pheno-graph-controls">
            <label className="pheno-graph-threshold-label" htmlFor="phenoGraphThreshold">
              <span id="phenoGraphThresholdLabel">Displayed edges</span>
              <input
                id="phenoGraphThreshold"
                type="range"
                min="0"
                max="0"
                step="1"
                defaultValue="0"
              />
            </label>
            <label className="pheno-graph-select-label" htmlFor="phenoGraphTopK">
              <span>Neighbors per node</span>
              <select id="phenoGraphTopK" defaultValue="1">
                {[1, 2, 3, 4, 9999].map((n) => (
                  <option key={n} value={n}>
                    {n === 9999 ? 'All' : `Top ${n}`}
                  </option>
                ))}
              </select>
            </label>
            <label className="pheno-graph-select-label" htmlFor="phenoGraphEdgeLabels">
              <span>Edge values</span>
              <select id="phenoGraphEdgeLabels" defaultValue="selected">
                <option value="off">Off</option>
                <option value="selected">Selected</option>
                <option value="visible">Visible</option>
              </select>
            </label>
            <label className="pheno-graph-checkbox">
              <input id="phenoGraphLargestComponent" type="checkbox" defaultChecked /> Largest
              component only
            </label>
            <div id="phenoGraphThresholdMeta" className="section-note-inline">
              Loading graph filter…
            </div>
          </div>
        )}
        {!heatmap && <div id={`${prefix}CohortLegend`} className="pheno-cohort-legend is-hidden" />}
        <div id={`${prefix}Plot`} className={`pheno-mds-plot${graph ? ' pheno-graph-plot' : ''}`} />
        <div className="section-note" id={`${prefix}SelectionNote`}>
          {heatmap
            ? 'Use Plotly zoom, pan, and hover tools to inspect the cohort matrix.'
            : graph
              ? 'Line width and opacity encode edge value. Click an edge to inspect it or switch Edge values to Visible.'
              : 'Select points with box or lasso to reuse them in Analysis or save them as a cohort.'}
        </div>
        {kind === 'umap' && (
          <p className="section-note">
            UMAP emphasizes local neighbourhoods. Distances between clusters do not directly
            represent the original distances.
          </p>
        )}
      </div>
    </details>
  );
}
export function createPhenoResultView(host) {
  if (!host) return { render() {}, warning() {} };
  const root = createRoot(host);
  let generation = 0,
    current = {},
    warning = '';
  const paint = () =>
    flushSync(() =>
      root.render(
        <>
          {warning && (
            <p className="section-note" role="status">
              {warning}
            </p>
          )}
          {current.kind === 'plots' ? (
            current.kinds.map((kind) => <PlotCard key={`${generation}:${kind}`} kind={kind} />)
          ) : (
            <Output model={current} />
          )}
        </>,
      ),
    );
  return {
    render(model) {
      current = model;
      warning = '';
      if (model.kind === 'plots') generation++;
      paint();
    },
    warning(message) {
      warning = message;
      paint();
    },
  };
}
