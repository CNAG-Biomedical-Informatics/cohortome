import React from 'react';
import { ArtifactDownloads, EvidenceCard } from '../analysis-result-parts.jsx';
import { ImagePreview, Card, Notes } from './presentation.jsx';
export function PathwayResults({ model: m, turnIndex }) {
  const c = m.context || {},
    id = (suffix) => `analysis-plot-${turnIndex}-${suffix}`;
  const downloads = <ArtifactDownloads artifacts={m.downloads} />;
  return (
    <>
      <Card title="Hallmark Pathway Enrichment">
        <Notes
          items={[
            `MSigDB Hallmark enrichment for ${c.dataset_name || 'the selected assay'} using a DESeq2-ranked comparison.`,
            `Higher in Cohort A: ${m.positiveText}`,
            `Higher in Cohort B: ${m.negativeText}`,
          ]}
        />
        <ImagePreview
          artifact={m.plotArtifact}
          alt="Hallmark pathway enrichment plot"
          empty="Pathway enrichment plot preview unavailable."
        />
        {downloads}
      </Card>
      <EvidenceCard
        id={id('pathway-summary')}
        title="Pathway Enrichment Summary"
        items={m.summaryItems}
      />
    </>
  );
}
