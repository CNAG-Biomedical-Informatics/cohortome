import React from 'react';
import { Plot } from '../analysis-result-parts.jsx';
import { ImagePreview } from './presentation.jsx';

// Stable attributes are used by the controller for lazy chart loading.
export function ArtifactViews({
  kind = 'de',
  turnIndex,
  plot,
  table,
  clustering,
  prefix = '',
  label,
  alt,
  empty,
}) {
  const heatmap = kind === 'de-heatmap',
    pathway = kind === 'pathway';
  const dataName = heatmap ? 'heatmap' : pathway ? 'pathway' : 'volcano';
  const dataProps = {
    [`data-${dataName}-url`]: table?.url || '',
    ...(heatmap ? { 'data-heatmap-clustering-url': clustering?.url || '' } : {}),
  };
  const plotId = `analysis-plot-${turnIndex}-${heatmap ? 'de-heatmap' : pathway ? 'workflow-pathway' : 'de-volcano'}`;
  const imageName = heatmap
    ? 'top_genes_heatmap.png'
    : pathway
      ? 'pathway_plot.png'
      : 'volcano_plot.png';
  const tableName = heatmap
    ? 'top_genes_heatmap.tsv'
    : pathway
      ? 'pathway_results.tsv'
      : 'volcano_points.tsv';
  return (
    <>
      <div className="analysis-view-tabs" role="tablist" aria-label={label}>
        <button
          type="button"
          className="analysis-view-tab is-active"
          {...{ [`data-${kind}-view-btn`]: 'png' }}
          data-turn-index={turnIndex}
          role="tab"
          aria-selected="true"
        >
          Original PNG
        </button>
        <button
          type="button"
          className={`analysis-view-tab${table ? '' : ' is-disabled'}`}
          {...{ [`data-${kind}-view-btn`]: 'interactive' }}
          data-turn-index={turnIndex}
          {...dataProps}
          role="tab"
          aria-selected="false"
          disabled={!table}
        >
          Interactive {heatmap ? 'heatmap' : 'plot'}
        </button>
      </div>
      <div
        className="analysis-view-panel is-active"
        {...{ [`data-${kind}-view-panel`]: 'png' }}
        data-turn-index={turnIndex}
      >
        <ImagePreview artifact={plot} alt={alt} empty={empty} />
      </div>
      <div
        className="analysis-view-panel"
        {...{ [`data-${kind}-view-panel`]: 'interactive' }}
        data-turn-index={turnIndex}
        {...dataProps}
      >
        {table ? (
          <>
            {heatmap ? (
              <div className="analysis-heatmap-interactive">
                <div className="analysis-heatmap-dendrogram" id={`${plotId}-dendrogram`} />
                <Plot id={plotId} height={520} />
              </div>
            ) : (
              <Plot id={plotId} height={440} />
            )}
            <p className="section-note" style={{ marginTop: 10 }}>
              Interactive view rendered from <code>{prefix + tableName}</code>. The canonical
              artifact remains <code>{prefix + imageName}</code>.
            </p>
          </>
        ) : (
          <div className="empty">
            Interactive {heatmap ? 'heatmap' : pathway ? 'pathway plot' : 'volcano plot'}{' '}
            unavailable.
          </div>
        )}
      </div>
    </>
  );
}
