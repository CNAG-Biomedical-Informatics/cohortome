import React from 'react';
import { ArtifactDownloads, EvidenceCard } from '../analysis-result-parts.jsx';
import { Card, Notes } from './presentation.jsx';
import { ArtifactViews } from './artifact-views.jsx';
export function WorkflowResults({ model: m, turnIndex }) {
  const c = m.context || {},
    id = (suffix) => `analysis-plot-${turnIndex}-${suffix}`;
  const downloads = <ArtifactDownloads artifacts={m.downloads} />;
  return (
    <>
      <Card title="Transcriptomics Signature Workflow">
        <p className="section-note">
          Curated DESeq2 differential expression followed by Hallmark pathway enrichment for{' '}
          {c.dataset_name || 'the selected assay'}.
        </p>
        {downloads}
      </Card>
      <Card title="Step 1: DESeq2 Differential Expression">
        <ArtifactViews
          turnIndex={turnIndex}
          plot={m.dePlotArtifact}
          table={m.deVolcanoArtifact}
          prefix="workflow/01-deseq2/"
          label="Workflow DESeq2 volcano plot views"
          alt="Workflow DESeq2 volcano plot"
          empty="DESeq2 volcano plot preview unavailable."
        />
        {m.deHeatmapArtifact && (
          <div
            style={{
              marginTop: 12,
            }}
          >
            <ArtifactViews
              kind="de-heatmap"
              turnIndex={turnIndex}
              plot={m.deHeatmapArtifact}
              table={m.deHeatmapTableArtifact}
              clustering={m.deHeatmapClusteringArtifact}
              prefix="workflow/01-deseq2/"
              label="Workflow DESeq2 heatmap views"
              alt="Workflow DESeq2 heatmap"
            />
          </div>
        )}
      </Card>
      <EvidenceCard
        id={id('workflow-de-summary')}
        title="DESeq2 Summary"
        items={m.deSummaryItems}
      />
      <Card title="Step 2: Hallmark Pathway Enrichment">
        <Notes
          items={[`Higher in Cohort A: ${m.positiveText}`, `Higher in Cohort B: ${m.negativeText}`]}
        />
        <ArtifactViews
          kind="pathway"
          turnIndex={turnIndex}
          plot={m.pathwayPlotArtifact}
          table={m.pathwayResultsArtifact}
          prefix="workflow/02-hallmark/"
          label="Workflow Hallmark pathway views"
          alt="Workflow Hallmark pathway enrichment plot"
          empty="Pathway enrichment plot preview unavailable."
        />
      </Card>
      <EvidenceCard
        id={id('workflow-pathway-summary')}
        title="Hallmark Summary"
        items={m.pathwaySummaryItems}
      />
    </>
  );
}
