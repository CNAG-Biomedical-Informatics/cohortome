import { createAnalysisSeries } from './analysis-series.js';
import {
  buildHeatmapRowCluster,
  flattenHeatmapClusterOrder,
  buildHeatmapClusterTreeFromR,
  buildHeatmapDendrogramSvg,
} from './heatmap-clustering.js';
// Chart-only module. Controllers retain requests, chat state and run execution.
export function createAnalysisCharts({
  ANALYSIS_PLOT_COLORS,
  escapeHtml,
  parseAnalysisTsv,
  rankedQuantitativeAssayResults,
  finiteAnalysisNumber,
  state,
  isQuantitativeAssayWilcoxonContextMode,
  isDifferentialExpressionContextMode,
  isPathwayEnrichmentContextMode,
}) {
  const {
    buildHorizontalBar,
    buildKaplanMeierPlot,
    buildTrajectoryPlot,
    buildTrajectoryComparisonPlot,
    buildTrajectoryComparisonSeries,
    buildExploratoryVolcanoPlot,
    buildDifferentialExpressionVolcanoPlot,
    buildDifferentialExpressionHeatmap,
    buildHallmarkPathwayPlot,
    buildQuantitativeAssayWilcoxonPlot,
  } = createAnalysisSeries({
    ANALYSIS_PLOT_COLORS,
    escapeHtml,
    rankedQuantitativeAssayResults,
    finiteAnalysisNumber,
  });
  function basePlotConfig() {
    return {
      displayModeBar: true,
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: [
        'toImage',
        'select2d',
        'lasso2d',
        'hoverCompareCartesian',
        'hoverClosestCartesian',
        'toggleSpikelines',
      ],
    };
  }

  function plotlyAvailable() {
    return (
      typeof window !== 'undefined' && window.Plotly && typeof window.Plotly.newPlot === 'function'
    );
  }

  function mountPlot(targetId, traces, layout) {
    const el = document.getElementById(targetId);
    if (!el) return;
    if (!plotlyAvailable()) {
      el.innerHTML = '<div class="empty">Plot rendering unavailable.</div>';
      return;
    }
    window.CohortomeTheme.newPlot(el, traces, layout, basePlotConfig());
  }

  async function loadTabularArtifactRows(url) {
    const response = await fetch(String(url || ''));
    if (!response.ok) {
      throw new Error('Unable to load interactive plot data.');
    }
    const text = await response.text();
    return parseAnalysisTsv(text);
  }

  async function loadJsonArtifact(url) {
    const response = await fetch(String(url || ''));
    if (!response.ok) {
      throw new Error('Unable to load interactive plot metadata.');
    }
    return response.json();
  }

  async function mountDifferentialExpressionInteractivePlot(turnIndex, payload) {
    const panelEl = document.querySelector(
      `[data-de-view-panel="interactive"][data-turn-index="${turnIndex}"]`,
    );
    if (!panelEl || panelEl.dataset.loaded === 'true' || panelEl.dataset.loading === 'true') {
      return;
    }
    const plotEl = document.getElementById(`analysis-plot-${turnIndex}-de-volcano`);
    if (!plotEl) return;
    const artifactUrl = String(panelEl.dataset.volcanoUrl || '').trim();
    if (!artifactUrl) {
      plotEl.innerHTML = '<div class="empty">Interactive volcano plot unavailable.</div>';
      panelEl.dataset.loaded = 'true';
      return;
    }
    panelEl.dataset.loading = 'true';
    plotEl.innerHTML = '<div class="empty">Loading interactive plot...</div>';
    try {
      const rows = await loadTabularArtifactRows(artifactUrl);
      const context = payload && payload.data ? payload.data.context : null;
      const volcano = buildDifferentialExpressionVolcanoPlot(
        rows,
        context && context.dataset_name ? context.dataset_name : '',
      );
      mountPlot(`analysis-plot-${turnIndex}-de-volcano`, volcano.traces, volcano.layout);
      panelEl.dataset.loaded = 'true';
    } catch (_error) {
      plotEl.innerHTML = '<div class="empty">Unable to render the interactive volcano plot.</div>';
    } finally {
      panelEl.dataset.loading = 'false';
    }
  }

  async function mountDifferentialExpressionInteractiveHeatmap(turnIndex, payload) {
    const panelEl = document.querySelector(
      `[data-de-heatmap-view-panel="interactive"][data-turn-index="${turnIndex}"]`,
    );
    if (!panelEl || panelEl.dataset.loaded === 'true' || panelEl.dataset.loading === 'true') {
      return;
    }
    const plotEl = document.getElementById(`analysis-plot-${turnIndex}-de-heatmap`);
    if (!plotEl) return;
    const artifactUrl = String(panelEl.dataset.heatmapUrl || '').trim();
    if (!artifactUrl) {
      plotEl.innerHTML = '<div class="empty">Interactive heatmap unavailable.</div>';
      panelEl.dataset.loaded = 'true';
      return;
    }
    panelEl.dataset.loading = 'true';
    plotEl.innerHTML = '<div class="empty">Loading interactive heatmap...</div>';
    try {
      const clusteringUrl = String(panelEl.dataset.heatmapClusteringUrl || '').trim();
      const [rows, clusteringPayload] = await Promise.all([
        loadTabularArtifactRows(artifactUrl),
        clusteringUrl ? loadJsonArtifact(clusteringUrl).catch(() => null) : Promise.resolve(null),
      ]);
      const context = payload && payload.data ? payload.data.context : null;
      const sampleNames = rows.length
        ? Object.keys(rows[0]).filter((key) => key !== 'gene_id')
        : [];
      const exactClusterRoot = buildHeatmapClusterTreeFromR(clusteringPayload);
      const exportedOrder = Array.isArray(clusteringPayload && clusteringPayload.order)
        ? clusteringPayload.order
            .map((value) => Number(value) - 1)
            .filter((value) => Number.isInteger(value) && value >= 0)
        : [];
      const fallbackClusterRoot = !exactClusterRoot
        ? buildHeatmapRowCluster(rows, sampleNames)
        : null;
      const clusterRoot = exactClusterRoot || fallbackClusterRoot;
      const rowOrder = exportedOrder.length
        ? exportedOrder
        : clusterRoot
          ? flattenHeatmapClusterOrder(clusterRoot)
          : rows.map((_, index) => index);
      const orderedRows = rowOrder.map((index) => rows[index]).filter(Boolean);
      const dendrogramEl = document.getElementById(
        `analysis-plot-${turnIndex}-de-heatmap-dendrogram`,
      );
      if (dendrogramEl) {
        dendrogramEl.innerHTML = clusterRoot
          ? buildHeatmapDendrogramSvg(clusterRoot, orderedRows)
          : '<div class="empty">Dendrogram unavailable.</div>';
      }
      const heatmap = buildDifferentialExpressionHeatmap(
        orderedRows,
        context && context.dataset_name ? context.dataset_name : '',
      );
      mountPlot(`analysis-plot-${turnIndex}-de-heatmap`, heatmap.traces, heatmap.layout);
      panelEl.dataset.loaded = 'true';
    } catch (_error) {
      plotEl.innerHTML = '<div class="empty">Unable to render the interactive heatmap.</div>';
    } finally {
      panelEl.dataset.loading = 'false';
    }
  }

  async function mountHallmarkInteractivePlot(turnIndex, payload) {
    const panelEl = document.querySelector(
      `[data-pathway-view-panel="interactive"][data-turn-index="${turnIndex}"]`,
    );
    if (!panelEl || panelEl.dataset.loaded === 'true' || panelEl.dataset.loading === 'true') {
      return;
    }
    const plotEl = document.getElementById(`analysis-plot-${turnIndex}-workflow-pathway`);
    if (!plotEl) return;
    const artifactUrl = String(panelEl.dataset.pathwayUrl || '').trim();
    if (!artifactUrl) {
      plotEl.innerHTML = '<div class="empty">Interactive pathway plot unavailable.</div>';
      panelEl.dataset.loaded = 'true';
      return;
    }
    panelEl.dataset.loading = 'true';
    plotEl.innerHTML = '<div class="empty">Loading interactive pathway plot...</div>';
    try {
      const rows = await loadTabularArtifactRows(artifactUrl);
      const context = payload && payload.data ? payload.data.context : null;
      const hallmarkContext =
        context && context.hallmark && typeof context.hallmark === 'object'
          ? context.hallmark
          : null;
      const pathway = buildHallmarkPathwayPlot(
        rows,
        hallmarkContext && hallmarkContext.dataset_name ? hallmarkContext.dataset_name : '',
      );
      mountPlot(`analysis-plot-${turnIndex}-workflow-pathway`, pathway.traces, pathway.layout);
      panelEl.dataset.loaded = 'true';
    } catch (_error) {
      plotEl.innerHTML = '<div class="empty">Unable to render the interactive pathway plot.</div>';
    } finally {
      panelEl.dataset.loading = 'false';
    }
  }

  function mountAnalysisPlots() {
    state.analysisTurns.forEach((turn, turnIndex) => {
      if (!turn || !turn.showPlots || !turn.payload || !turn.payload.data) return;
      const context = turn.payload.data.context;
      if (!context) return;
      if (context.mode === 'cross_modal_association') {
        const points = context.points || [];
        const traces = (context.groups || []).map((group) => {
          const subset = points.filter((point) => point.group === group.label);
          return {
            type: 'scatter',
            mode: 'markers',
            name: group.label,
            x: subset.map((point) => point.x),
            y: subset.map((point) => point.y),
            marker: { size: 9, opacity: 0.8 },
          };
        });
        mountPlot(`analysis-plot-${turnIndex}-association`, traces, {
          height: 420,
          xaxis: { title: context.parameters.feature_x },
          yaxis: { title: context.parameters.feature_y },
          margin: { l: 70, r: 25, b: 80, t: 30 },
          legend: { orientation: 'h', y: -0.25 },
        });
        return;
      }
      if (context.mode === 'transcriptomics_medication_compare') {
        (context.comparisons || []).forEach((item, comparisonIndex) => {
          const points = Array.isArray(item.exploratory_volcano_points)
            ? item.exploratory_volcano_points
            : [];
          if (!points.length) return;
          const volcano = buildExploratoryVolcanoPlot(
            points,
            `${item.medication_a || 'A'} vs ${item.medication_b || 'B'}`,
          );
          mountPlot(
            `analysis-plot-${turnIndex}-assay-volcano-${comparisonIndex}`,
            volcano.traces,
            volcano.layout,
          );
        });
        return;
      }
      if (isQuantitativeAssayWilcoxonContextMode(context.mode)) {
        const effectPlot = buildQuantitativeAssayWilcoxonPlot(
          context.results,
          String(context.assay_label || context.dataset_name || 'Quantitative assay'),
        );
        mountPlot(
          `analysis-plot-${turnIndex}-quantitative-assay-wilcoxon`,
          effectPlot.traces,
          effectPlot.layout,
        );
        return;
      }
      if (isDifferentialExpressionContextMode(context.mode)) {
        const summary = buildHorizontalBar(
          [
            { label: 'Cohort A samples', value: Number(context.cohort_a_sample_count || 0) },
            { label: 'Cohort B samples', value: Number(context.cohort_b_sample_count || 0) },
            { label: 'Genes tested', value: Number(context.gene_count || 0) },
            { label: 'Significant genes', value: Number(context.significant_gene_count || 0) },
          ],
          'label',
          'value',
          '#2563eb',
        );
        mountPlot(`analysis-plot-${turnIndex}-de-summary`, summary.traces, summary.layout);
        return;
      }
      if (isPathwayEnrichmentContextMode(context.mode)) {
        const summary = buildHorizontalBar(
          [
            { label: 'Cohort A samples', value: Number(context.cohort_a_sample_count || 0) },
            { label: 'Cohort B samples', value: Number(context.cohort_b_sample_count || 0) },
            { label: 'Ranked genes', value: Number(context.ranked_gene_count || 0) },
            { label: 'Pathways tested', value: Number(context.pathway_count || 0) },
            {
              label: 'Significant pathways',
              value: Number(context.significant_pathway_count || 0),
            },
          ],
          'label',
          'value',
          '#2563eb',
        );
        mountPlot(`analysis-plot-${turnIndex}-pathway-summary`, summary.traces, summary.layout);
        return;
      }
      if (context.mode === 'workflow_transcriptomics_signature') {
        const deContext =
          context.deseq2 && typeof context.deseq2 === 'object' ? context.deseq2 : {};
        const hallmarkContext =
          context.hallmark && typeof context.hallmark === 'object' ? context.hallmark : {};
        const deSummary = buildHorizontalBar(
          [
            { label: 'Cohort A samples', value: Number(deContext.cohort_a_sample_count || 0) },
            { label: 'Cohort B samples', value: Number(deContext.cohort_b_sample_count || 0) },
            { label: 'Genes tested', value: Number(deContext.gene_count || 0) },
            { label: 'Significant genes', value: Number(deContext.significant_gene_count || 0) },
          ],
          'label',
          'value',
          '#2563eb',
        );
        mountPlot(
          `analysis-plot-${turnIndex}-workflow-de-summary`,
          deSummary.traces,
          deSummary.layout,
        );
        const pathwaySummary = buildHorizontalBar(
          [
            { label: 'Ranked genes', value: Number(hallmarkContext.ranked_gene_count || 0) },
            { label: 'Pathways tested', value: Number(hallmarkContext.pathway_count || 0) },
            {
              label: 'Significant pathways',
              value: Number(hallmarkContext.significant_pathway_count || 0),
            },
          ],
          'label',
          'value',
          '#059669',
        );
        mountPlot(
          `analysis-plot-${turnIndex}-workflow-pathway-summary`,
          pathwaySummary.traces,
          pathwaySummary.layout,
        );
        return;
      }
      if (context.mode === 'trajectory_compare' || context.mode === 'trajectory_compare_response') {
        const comparison = buildTrajectoryComparisonPlot(
          buildTrajectoryComparisonSeries(context),
          context.time_axis_label,
        );
        mountPlot(
          `analysis-plot-${turnIndex}-trajectory-compare`,
          comparison.traces,
          comparison.layout,
        );
        return;
      }
      if (context.mode === 'trajectory' || context.mode === 'trajectory_response') {
        const trajectory = buildTrajectoryPlot(
          context.patient_series || [],
          {
            label: context.treatment ? 'Median response' : 'Cohort median',
            points: context.summary_points || [],
          },
          context.time_axis_label,
        );
        mountPlot(`analysis-plot-${turnIndex}-trajectory`, trajectory.traces, trajectory.layout);
        const coverage = buildHorizontalBar(
          [
            { label: 'Patients', value: Number(context.patient_count || 0) },
            { label: 'Summary points', value: Number((context.summary_points || []).length) },
          ],
          'label',
          'value',
          '#2563eb',
        );
        mountPlot(
          `analysis-plot-${turnIndex}-trajectory-coverage`,
          coverage.traces,
          coverage.layout,
        );
        return;
      }
      if (context.mode === 'survival_compare') {
        const cohortA = context.cohort_a || {};
        const cohortB = context.cohort_b || {};
        const survival = buildKaplanMeierPlot([
          {
            label: `Cohort A (${cohortA.patient_count || 0} patients)`,
            points: cohortA.curve_points || [],
          },
          {
            label: `Cohort B (${cohortB.patient_count || 0} patients)`,
            points: cohortB.curve_points || [],
          },
        ]);
        mountPlot(`analysis-plot-${turnIndex}-survival-compare`, survival.traces, survival.layout);
        const aSummary = buildHorizontalBar(
          [
            { label: 'Patients', value: Number(cohortA.patient_count || 0) },
            { label: 'Events', value: Number(cohortA.event_count || 0) },
            { label: 'Censored', value: Number(cohortA.censored_count || 0) },
          ],
          'label',
          'value',
          '#2563eb',
        );
        const bSummary = buildHorizontalBar(
          [
            { label: 'Patients', value: Number(cohortB.patient_count || 0) },
            { label: 'Events', value: Number(cohortB.event_count || 0) },
            { label: 'Censored', value: Number(cohortB.censored_count || 0) },
          ],
          'label',
          'value',
          '#0ea5e9',
        );
        mountPlot(`analysis-plot-${turnIndex}-survival-a`, aSummary.traces, aSummary.layout);
        mountPlot(`analysis-plot-${turnIndex}-survival-b`, bSummary.traces, bSummary.layout);
        return;
      }
      if (context.mode === 'survival') {
        const survival = buildKaplanMeierPlot([
          {
            label:
              `${context.measure || 'Measure'} ${context.operator || ''} ${context.threshold || ''}`.trim(),
            points: context.curve_points || [],
          },
        ]);
        mountPlot(`analysis-plot-${turnIndex}-survival`, survival.traces, survival.layout);
        const summary = buildHorizontalBar(
          [
            { label: 'Patients', value: Number(context.patient_count || 0) },
            { label: 'Events', value: Number(context.event_count || 0) },
            { label: 'Censored', value: Number(context.censored_count || 0) },
          ],
          'label',
          'value',
          '#2563eb',
        );
        const median = buildHorizontalBar(
          [{ label: 'Median days', value: Number(context.median_survival_days || 0) }],
          'label',
          'value',
          '#0ea5e9',
        );
        mountPlot(`analysis-plot-${turnIndex}-survival-summary`, summary.traces, summary.layout);
        mountPlot(`analysis-plot-${turnIndex}-survival-median`, median.traces, median.layout);
        return;
      }
      if (context.mode === 'compare') {
        const cohortA = context.cohort_a || {};
        const cohortB = context.cohort_b || {};
        const overviewA = buildHorizontalBar(
          [
            {
              label: 'Patients',
              value: Number((cohortA.overview && cohortA.overview.patient_count) || 0),
            },
            {
              label: 'Timepoints',
              value: Number((cohortA.overview && cohortA.overview.timepoint_count) || 0),
            },
          ],
          'label',
          'value',
          '#2563eb',
        );
        const overviewB = buildHorizontalBar(
          [
            {
              label: 'Patients',
              value: Number((cohortB.overview && cohortB.overview.patient_count) || 0),
            },
            {
              label: 'Timepoints',
              value: Number((cohortB.overview && cohortB.overview.timepoint_count) || 0),
            },
          ],
          'label',
          'value',
          '#0ea5e9',
        );
        const disease = buildHorizontalBar(
          (context.disease_deltas || []).slice(0, 8).map((item) => ({
            label:
              item.delta > 0
                ? `${item.label} (A)`
                : item.delta < 0
                  ? `${item.label} (B)`
                  : `${item.label} (=)`,
            value: Math.abs(Number(item.delta || 0)),
          })),
          'label',
          'value',
          '#0ea5e9',
        );
        const medication = buildHorizontalBar(
          (context.medication_deltas || []).slice(0, 8).map((item) => ({
            label:
              item.delta > 0
                ? `${item.label} (A)`
                : item.delta < 0
                  ? `${item.label} (B)`
                  : `${item.label} (=)`,
            value: Math.abs(Number(item.delta || 0)),
          })),
          'label',
          'value',
          '#7c3aed',
        );
        overviewA.traces[0].meta = { cohortome_group: 0 };
        overviewB.traces[0].meta = { cohortome_group: 1 };
        mountPlot(`analysis-plot-${turnIndex}-compare-a`, overviewA.traces, overviewA.layout);
        mountPlot(`analysis-plot-${turnIndex}-compare-b`, overviewB.traces, overviewB.layout);
        mountPlot(`analysis-plot-${turnIndex}-compare-disease`, disease.traces, disease.layout);
        mountPlot(
          `analysis-plot-${turnIndex}-compare-medication`,
          medication.traces,
          medication.layout,
        );
        return;
      }
      const disease = buildHorizontalBar(
        (context.top_diseases || [])
          .slice(0, 8)
          .map((item) => ({ label: item.disease, value: item.patient_count })),
        'label',
        'value',
        '#0ea5e9',
      );
      const medication = buildHorizontalBar(
        (context.top_medications || [])
          .slice(0, 8)
          .map((item) => ({ label: item.medication, value: item.patient_count })),
        'label',
        'value',
        '#2563eb',
      );
      const period = buildHorizontalBar(
        (context.timepoints_by_period || [])
          .slice(0, 12)
          .map((item) => ({ label: item.period, value: item.timepoint_count })),
        'label',
        'value',
        '#7c3aed',
      );
      const visits = buildHorizontalBar(
        (context.visit_distribution || [])
          .slice(0, 12)
          .map((item) => ({ label: item.label, value: item.value })),
        'label',
        'value',
        '#059669',
      );
      mountPlot(`analysis-plot-${turnIndex}-summary-disease`, disease.traces, disease.layout);
      mountPlot(
        `analysis-plot-${turnIndex}-summary-medication`,
        medication.traces,
        medication.layout,
      );
      mountPlot(`analysis-plot-${turnIndex}-summary-period`, period.traces, period.layout);
      mountPlot(`analysis-plot-${turnIndex}-summary-visits`, visits.traces, visits.layout);
    });
  }
  return {
    mountDifferentialExpressionInteractivePlot,
    mountDifferentialExpressionInteractiveHeatmap,
    mountHallmarkInteractivePlot,
    mountAnalysisPlots,
  };
}
