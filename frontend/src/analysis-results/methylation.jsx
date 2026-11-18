import React from 'react';
import { ArtifactDownloads } from '../analysis-result-parts.jsx';
import { Metrics, ImagePreview, Card, Notes } from './presentation.jsx';
export function MethylationResults({ model: m, turnIndex }) {
  const downloads = <ArtifactDownloads artifacts={m.downloads} />;
  const qc = m.kind === 'qc',
    kind = qc ? 'qc' : 'differential';
  return (
    <>
      {m.panel && (
        <div
          data-methylation-panel-summary="true"
          style={{
            gridColumn: '1 / -1',
          }}
        >
          <Metrics kind="panel" items={m.panel.metrics} />
          <p className="section-note">{m.panel.note}</p>
        </div>
      )}
      <Metrics kind={kind} items={m.metrics} />
      <Card
        title={qc ? 'Methylation QC and PCA' : 'Differential Methylation Volcano Plot'}
        data-methylation-result={qc ? 'qc-pca' : 'differential'}
      >
        <Notes items={m.notes} />
        <ImagePreview
          artifact={m.plotArtifact}
          alt={qc ? 'Methylation PCA plot' : 'Differential methylation volcano plot'}
          empty={
            qc
              ? 'Methylation PCA preview unavailable.'
              : 'Differential methylation volcano plot preview unavailable.'
          }
        />
        {downloads}
      </Card>
    </>
  );
}
