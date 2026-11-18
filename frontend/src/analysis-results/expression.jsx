import React from 'react';
import { ArtifactDownloads } from '../analysis-result-parts.jsx';
import { Metrics, Card, Notes } from './presentation.jsx';
import { ArtifactViews } from './artifact-views.jsx';
function Heatmap({ m, turnIndex }) {
  if (!m.heatmapArtifact) return null;
  return (
    <Card title="Top Differentially Expressed Genes Heatmap">
      <p className="section-note">
        Standardized expression heatmap for the top DESeq2-ranked genes across both cohorts.
      </p>
      <div className="analysis-heatmap-legend" aria-label="Heatmap legend">
        <span className="analysis-heatmap-legend-label">Lower expression</span>
        <span className="analysis-heatmap-legend-scale" aria-hidden="true" />
        <span className="analysis-heatmap-legend-label">Higher expression</span>
      </div>
      <p className="section-note">
        Blue means lower relative expression for that gene, white is near the gene-level average,
        and red means higher relative expression.
      </p>
      <ArtifactViews
        kind="de-heatmap"
        turnIndex={turnIndex}
        plot={m.heatmapArtifact}
        table={m.heatmapTableArtifact}
        clustering={m.heatmapClusteringArtifact}
        label="Differential expression heatmap views"
        alt="Top differentially expressed genes heatmap"
      />
    </Card>
  );
}
export function ExpressionResults({ model: m, turnIndex }) {
  const c = m.context || {};
  const downloads = <ArtifactDownloads artifacts={m.downloads} />;
  return (
    <>
      <Metrics kind="differential-expression" items={m.metrics} />
      <Card
        title={`${m.isLimmaVoom ? 'limma-voom' : 'DESeq2'} Differential Expression`}
        data-analysis-result="differential-expression"
      >
        <Notes
          items={[
            `Transcriptomic differential expression for ${c.dataset_name || 'the selected assay'}. ${m.methodText}`,
            m.topHitText,
          ]}
        />
        <ArtifactViews
          turnIndex={turnIndex}
          plot={m.plotArtifact}
          table={m.volcanoArtifact}
          label="Differential expression plot views"
          alt="Differential expression volcano plot"
          empty="Volcano plot preview unavailable."
        />
        {downloads}
      </Card>
      <Heatmap m={m} turnIndex={turnIndex} />
    </>
  );
}
