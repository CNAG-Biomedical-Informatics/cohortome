export function createAnalysisUi(ctx) {
  const { refs, helpers, callbacks, state } = ctx;
  const {
    analysisMetaEl,
    analysisThreadEl,
    analysisStatusEl,
    analysisComposerStatusEl,
    analysisRunBtnEl,
    analysisPromptEl,
    analysisSelectedPatientIdsEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
  } = refs;
  const { escapeHtml, renderQueryReply } = helpers;
  const {
    renderAnalysisStarterPrompts,
    syncCurrentAnalysisSessionFromUi,
    startAnalysisProgressUpdates,
    stopAnalysisProgressUpdates,
    handleAnalysisJobSubmission,
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
    renderAnalysisFlowBar,
    currentDatasetSelectionKey,
    assayDatasetOverlap,
  } = callbacks;

  const ANALYSIS_PLOT_COLORS = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed", "#dc2626", "#d97706"];

  function analysisWorkspaceKey() {
    const selected = typeof currentDatasetSelectionKey === "function" ? String(currentDatasetSelectionKey() || "").trim() : "";
    if (selected) return selected;
    const scopeId = refs.dataDirEl && refs.dataDirEl.dataset ? String(refs.dataDirEl.dataset.scopeId || "").trim() : "";
    if (scopeId) return scopeId;
    return refs.dataDirEl ? String(refs.dataDirEl.value || "").trim() : "";
  }

  function requiresSingleSelectedAssayDataset(itemId) {
    const normalized = String(itemId || "").trim();
    return normalized === "transcriptomics-deseq2-differential-expression"
      || normalized === "transcriptomics-hallmark-pathway-enrichment"
      || normalized === "transcriptomics-signature-workflow";
  }

  function isDifferentialExpressionContextMode(mode) {
    const normalized = String(mode || "").trim();
    return normalized === "external_rscript_transcriptomics_deseq2_differential_expression";
  }

  function isPathwayEnrichmentContextMode(mode) {
    return String(mode || "").trim() === "external_rscript_transcriptomics_hallmark_pathway_enrichment";
  }

  function prettyHallmarkLabel(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    const withoutPrefix = raw.replace(/^HALLMARK_/, "");
    return withoutPrefix
      .split("_")
      .filter(Boolean)
      .map((part) => {
        const upper = part.toUpperCase();
        if (["TNFA", "NFKB", "IL2", "MTOR", "PI3K", "AKT", "DNA", "UV"].includes(upper)) return upper;
        const lower = part.toLowerCase();
        return lower.charAt(0).toUpperCase() + lower.slice(1);
      })
      .join(" ");
  }

  function plotPlaceholder(id, height = 320) {
    return `<div class="analysis-plot-frame" id="${id}" style="height:${height}px;"></div>`;
  }

  function basePlotLayout(overrides) {
    return {
      margin: { t: 28, r: 24, b: 84, l: 56 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "#f8fbff",
      font: { family: "inherit", color: "#132238", size: 12 },
      xaxis: {
        automargin: true,
        gridcolor: "rgba(148,163,184,0.2)",
        zeroline: false,
        linecolor: "#cbd5e1",
        tickfont: { color: "#61758c" },
        title: { font: { color: "#61758c", size: 12 } },
      },
      yaxis: {
        automargin: true,
        gridcolor: "rgba(148,163,184,0.2)",
        zeroline: false,
        linecolor: "#cbd5e1",
        tickfont: { color: "#61758c" },
        title: { font: { color: "#61758c", size: 12 } },
      },
      legend: {
        orientation: "h",
        yanchor: "bottom",
        y: 1.02,
        xanchor: "left",
        x: 0,
      },
      hoverlabel: { bgcolor: "#132238", font: { color: "#f8fafc" } },
      ...overrides,
    };
  }

  function basePlotConfig() {
    return {
      displayModeBar: true,
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: [
        "toImage",
        "select2d",
        "lasso2d",
        "hoverCompareCartesian",
        "hoverClosestCartesian",
        "toggleSpikelines",
      ],
    };
  }

  function formatTimeToEventLabel(context) {
    const eventName = String(context && context.event_name ? context.event_name : "").trim();
    if (eventName) return eventName;
    const measure = String(context && context.measure ? context.measure : "").trim();
    const operator = String(context && context.operator ? context.operator : "").trim();
    const threshold = context && context.threshold !== undefined && context.threshold !== null
      ? String(context.threshold).trim()
      : "";
    if (measure && operator && threshold) return `${measure} ${operator} ${threshold}`;
    if (measure) return measure;
    return "defined event";
  }

  function renderBarChartCard(id, title, items, labelKey, valueKey) {
    if (!items.length) return `<div class="viz-card"><h3>${escapeHtml(title)}</h3><div class="empty">No data.</div></div>`;
    return `<div class="viz-card"><h3>${escapeHtml(title)}</h3>${plotPlaceholder(id, Math.max(240, items.length * 28 + 90))}</div>`;
  }

  function renderArtifactDownloads(title, artifacts) {
    const links = (Array.isArray(artifacts) ? artifacts : [])
      .filter(Boolean)
      .map((item) => {
        const name = String(item && item.name ? item.name : "").trim();
        const url = String(item && item.url ? item.url : "").trim();
        if (!name || !url) return "";
        return `<a class="query-chip" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>`;
      })
      .filter(Boolean)
      .join("");
    if (!links) return "";
    return `<details class="query-section analysis-artifact-downloads"><summary><span class="analysis-section-label">${renderAnalysisIcon("data")}<span>${escapeHtml(title || "Result files")}</span></span></summary><div class="analysis-catalog-tags">${links}</div></details>`;
  }

  function renderAnalysisPlotsMarkup(payload, turnIndex) {
    const data = payload && payload.data ? payload.data : null;
    const context = data && data.context ? data.context : null;
    const artifacts = Array.isArray(data && data.artifacts) ? data.artifacts : [];
    if (!context) return '<div class="empty">No analysis plots available.</div>';
    if (context.mode === "workflow_transcriptomics_signature") {
      const findArtifact = (suffix) => artifacts.find((item) => String(item && item.name ? item.name : "").endsWith(suffix));
      const deContext = context.deseq2 && typeof context.deseq2 === "object" ? context.deseq2 : {};
      const hallmarkContext = context.hallmark && typeof context.hallmark === "object" ? context.hallmark : {};
      const dePlotArtifact = findArtifact("workflow/01-deseq2/volcano_plot.png");
      const deHeatmapArtifact = findArtifact("workflow/01-deseq2/top_genes_heatmap.png");
      const deHeatmapTableArtifact = findArtifact("workflow/01-deseq2/top_genes_heatmap.tsv");
      const deHeatmapClusteringArtifact = findArtifact("workflow/01-deseq2/top_genes_heatmap_clustering.json");
      const deResultsArtifact = findArtifact("workflow/01-deseq2/de_results.tsv");
      const deVolcanoArtifact = findArtifact("workflow/01-deseq2/volcano_points.tsv");
      const deSummaryArtifact = findArtifact("workflow/01-deseq2/summary.json");
      const pathwayPlotArtifact = findArtifact("workflow/02-hallmark/pathway_plot.png");
      const pathwayResultsArtifact = findArtifact("workflow/02-hallmark/pathway_results.tsv");
      const rankingsArtifact = findArtifact("workflow/02-hallmark/gene_rankings.tsv");
      const pathwaySummaryArtifact = findArtifact("workflow/02-hallmark/summary.json");
      const workflowManifestArtifact = findArtifact("workflow/manifest.json");
      const downloads = renderArtifactDownloads("Result files", [
        workflowManifestArtifact,
        dePlotArtifact,
        deHeatmapArtifact,
        deVolcanoArtifact,
        deHeatmapTableArtifact,
        deHeatmapClusteringArtifact,
        deResultsArtifact,
        deSummaryArtifact,
        pathwayPlotArtifact,
        pathwayResultsArtifact,
        rankingsArtifact,
        pathwaySummaryArtifact,
      ]);
      const deSummaryItems = [
        { label: "Cohort A samples", value: Number(deContext.cohort_a_sample_count || 0) },
        { label: "Cohort B samples", value: Number(deContext.cohort_b_sample_count || 0) },
        { label: "Genes tested", value: Number(deContext.gene_count || 0) },
        { label: "Significant genes", value: Number(deContext.significant_gene_count || 0) },
      ];
      const pathwaySummaryItems = [
        { label: "Ranked genes", value: Number(hallmarkContext.ranked_gene_count || 0) },
        { label: "Pathways tested", value: Number(hallmarkContext.pathway_count || 0) },
        { label: "Significant pathways", value: Number(hallmarkContext.significant_pathway_count || 0) },
      ];
      const positiveText = Array.isArray(hallmarkContext.top_positive_pathway_labels) && hallmarkContext.top_positive_pathway_labels.length
        ? hallmarkContext.top_positive_pathway_labels.map((item) => prettyHallmarkLabel(item)).join(", ")
        : "none at BH < 0.05";
      const negativeText = Array.isArray(hallmarkContext.top_negative_pathway_labels) && hallmarkContext.top_negative_pathway_labels.length
        ? hallmarkContext.top_negative_pathway_labels.map((item) => prettyHallmarkLabel(item)).join(", ")
        : "none at BH < 0.05";
      return `
        <div class="viz-card" style="grid-column: 1 / -1;">
          <h3>Transcriptomics Signature Workflow</h3>
          <p class="section-note">Curated DESeq2 differential expression followed by Hallmark pathway enrichment for ${escapeHtml(String(context.dataset_name || "the selected assay"))}.</p>
          ${downloads}
        </div>
        <div class="viz-card" style="grid-column: 1 / -1;">
          <h3>Step 1: DESeq2 Differential Expression</h3>
          <div class="analysis-view-tabs" role="tablist" aria-label="Workflow DESeq2 volcano plot views">
            <button type="button" class="analysis-view-tab is-active" data-de-view-btn="png" data-turn-index="${turnIndex}" role="tab" aria-selected="true">Original PNG</button>
            <button type="button" class="analysis-view-tab${deVolcanoArtifact ? "" : " is-disabled"}" data-de-view-btn="interactive" data-turn-index="${turnIndex}" data-volcano-url="${escapeHtml(String(deVolcanoArtifact && deVolcanoArtifact.url ? deVolcanoArtifact.url : ""))}" role="tab" aria-selected="false"${deVolcanoArtifact ? "" : " disabled"}>Interactive plot</button>
          </div>
          <div class="analysis-view-panel is-active" data-de-view-panel="png" data-turn-index="${turnIndex}">
            ${dePlotArtifact ? `<div class="analysis-artifact-image-frame"><img class="analysis-artifact-image" src="${escapeHtml(String(dePlotArtifact.url || ""))}" alt="Workflow DESeq2 volcano plot"></div>` : '<div class="empty">DESeq2 volcano plot preview unavailable.</div>'}
          </div>
          <div class="analysis-view-panel" data-de-view-panel="interactive" data-turn-index="${turnIndex}" data-volcano-url="${escapeHtml(String(deVolcanoArtifact && deVolcanoArtifact.url ? deVolcanoArtifact.url : ""))}">
            ${deVolcanoArtifact ? `${plotPlaceholder(`analysis-plot-${turnIndex}-de-volcano`, 440)}<p class="section-note" style="margin-top:10px;">Interactive view rendered from <code>workflow/01-deseq2/volcano_points.tsv</code>. The canonical artifact remains <code>workflow/01-deseq2/volcano_plot.png</code>.</p>` : '<div class="empty">Interactive volcano plot unavailable.</div>'}
          </div>
          ${deHeatmapArtifact ? `<div style="margin-top:12px;"><div class="analysis-view-tabs" role="tablist" aria-label="Workflow DESeq2 heatmap views"><button type="button" class="analysis-view-tab is-active" data-de-heatmap-view-btn="png" data-turn-index="${turnIndex}" role="tab" aria-selected="true">Original PNG</button><button type="button" class="analysis-view-tab${deHeatmapTableArtifact ? "" : " is-disabled"}" data-de-heatmap-view-btn="interactive" data-turn-index="${turnIndex}" data-heatmap-url="${escapeHtml(String(deHeatmapTableArtifact && deHeatmapTableArtifact.url ? deHeatmapTableArtifact.url : ""))}" data-heatmap-clustering-url="${escapeHtml(String(deHeatmapClusteringArtifact && deHeatmapClusteringArtifact.url ? deHeatmapClusteringArtifact.url : ""))}" role="tab" aria-selected="false"${deHeatmapTableArtifact ? "" : " disabled"}>Interactive heatmap</button></div><div class="analysis-view-panel is-active" data-de-heatmap-view-panel="png" data-turn-index="${turnIndex}"><div class="analysis-artifact-image-frame"><img class="analysis-artifact-image" src="${escapeHtml(String(deHeatmapArtifact.url || ""))}" alt="Workflow DESeq2 heatmap"></div></div><div class="analysis-view-panel" data-de-heatmap-view-panel="interactive" data-turn-index="${turnIndex}" data-heatmap-url="${escapeHtml(String(deHeatmapTableArtifact && deHeatmapTableArtifact.url ? deHeatmapTableArtifact.url : ""))}" data-heatmap-clustering-url="${escapeHtml(String(deHeatmapClusteringArtifact && deHeatmapClusteringArtifact.url ? deHeatmapClusteringArtifact.url : ""))}">${deHeatmapTableArtifact ? `<div class="analysis-heatmap-interactive"><div class="analysis-heatmap-dendrogram" id="analysis-plot-${turnIndex}-de-heatmap-dendrogram"></div>${plotPlaceholder(`analysis-plot-${turnIndex}-de-heatmap`, 520)}</div><p class="section-note" style="margin-top:10px;">Interactive view rendered from <code>workflow/01-deseq2/top_genes_heatmap.tsv</code>. The canonical artifact remains <code>workflow/01-deseq2/top_genes_heatmap.png</code>.</p>` : '<div class="empty">Interactive heatmap unavailable.</div>'}</div></div></div>` : ""}
        </div>
        ${renderBarChartCard(`analysis-plot-${turnIndex}-workflow-de-summary`, "DESeq2 Summary", deSummaryItems, "label", "value")}
        <div class="viz-card" style="grid-column: 1 / -1;">
          <h3>Step 2: Hallmark Pathway Enrichment</h3>
          <p class="section-note">Higher in Cohort A: ${escapeHtml(positiveText)}</p>
          <p class="section-note">Higher in Cohort B: ${escapeHtml(negativeText)}</p>
          <div class="analysis-view-tabs" role="tablist" aria-label="Workflow Hallmark pathway views">
            <button type="button" class="analysis-view-tab is-active" data-pathway-view-btn="png" data-turn-index="${turnIndex}" role="tab" aria-selected="true">Original PNG</button>
            <button type="button" class="analysis-view-tab${pathwayResultsArtifact ? "" : " is-disabled"}" data-pathway-view-btn="interactive" data-turn-index="${turnIndex}" data-pathway-url="${escapeHtml(String(pathwayResultsArtifact && pathwayResultsArtifact.url ? pathwayResultsArtifact.url : ""))}" role="tab" aria-selected="false"${pathwayResultsArtifact ? "" : " disabled"}>Interactive plot</button>
          </div>
          <div class="analysis-view-panel is-active" data-pathway-view-panel="png" data-turn-index="${turnIndex}">
            ${pathwayPlotArtifact ? `<div class="analysis-artifact-image-frame"><img class="analysis-artifact-image" src="${escapeHtml(String(pathwayPlotArtifact.url || ""))}" alt="Workflow Hallmark pathway enrichment plot"></div>` : '<div class="empty">Pathway enrichment plot preview unavailable.</div>'}
          </div>
          <div class="analysis-view-panel" data-pathway-view-panel="interactive" data-turn-index="${turnIndex}" data-pathway-url="${escapeHtml(String(pathwayResultsArtifact && pathwayResultsArtifact.url ? pathwayResultsArtifact.url : ""))}">
            ${pathwayResultsArtifact ? `${plotPlaceholder(`analysis-plot-${turnIndex}-workflow-pathway`, 440)}<p class="section-note" style="margin-top:10px;">Interactive view rendered from <code>workflow/02-hallmark/pathway_results.tsv</code>. The canonical artifact remains <code>workflow/02-hallmark/pathway_plot.png</code>.</p>` : '<div class="empty">Interactive pathway plot unavailable.</div>'}
          </div>
        </div>
        ${renderBarChartCard(`analysis-plot-${turnIndex}-workflow-pathway-summary`, "Hallmark Summary", pathwaySummaryItems, "label", "value")}
      `;
    }
    if (isDifferentialExpressionContextMode(context.mode)) {
      const plotArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "volcano_plot.png");
      const heatmapArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "top_genes_heatmap.png");
      const heatmapTableArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "top_genes_heatmap.tsv");
      const heatmapClusteringArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "top_genes_heatmap_clustering.json");
      const resultsArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "de_results.tsv");
      const volcanoArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "volcano_points.tsv");
      const summaryArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "summary.json");
      const downloads = renderArtifactDownloads("Result files", [plotArtifact, heatmapArtifact, heatmapTableArtifact, heatmapClusteringArtifact, resultsArtifact, volcanoArtifact, summaryArtifact]);
      const summaryItems = [
        { label: "Dataset", value: String(context.dataset_name || "n/a") },
        { label: "Cohort A samples", value: Number(context.cohort_a_sample_count || 0) },
        { label: "Cohort B samples", value: Number(context.cohort_b_sample_count || 0) },
        { label: "Genes tested", value: Number(context.gene_count || 0) },
        { label: "Significant genes", value: Number(context.significant_gene_count || 0) },
      ];
      return `
        <div class="viz-card" style="grid-column: 1 / -1;">
          <h3>Differential Expression Volcano Plot</h3>
          <p class="section-note">Transcriptomic differential expression for ${escapeHtml(String(context.dataset_name || "the selected assay"))}.</p>
          <div class="analysis-view-tabs" role="tablist" aria-label="Differential expression plot views">
            <button type="button" class="analysis-view-tab is-active" data-de-view-btn="png" data-turn-index="${turnIndex}" role="tab" aria-selected="true">Original PNG</button>
            <button type="button" class="analysis-view-tab${volcanoArtifact ? "" : " is-disabled"}" data-de-view-btn="interactive" data-turn-index="${turnIndex}" data-volcano-url="${escapeHtml(String(volcanoArtifact && volcanoArtifact.url ? volcanoArtifact.url : ""))}" role="tab" aria-selected="false"${volcanoArtifact ? "" : " disabled"}>Interactive plot</button>
          </div>
          <div class="analysis-view-panel is-active" data-de-view-panel="png" data-turn-index="${turnIndex}">
            ${plotArtifact ? `<div class="analysis-artifact-image-frame"><img class="analysis-artifact-image" src="${escapeHtml(String(plotArtifact.url || ""))}" alt="Differential expression volcano plot"></div>` : '<div class="empty">Volcano plot preview unavailable.</div>'}
          </div>
          <div class="analysis-view-panel" data-de-view-panel="interactive" data-turn-index="${turnIndex}" data-volcano-url="${escapeHtml(String(volcanoArtifact && volcanoArtifact.url ? volcanoArtifact.url : ""))}">
            ${volcanoArtifact ? `${plotPlaceholder(`analysis-plot-${turnIndex}-de-volcano`, 440)}<p class="section-note" style="margin-top:10px;">Interactive view rendered from <code>volcano_points.tsv</code>. The canonical artifact remains <code>volcano_plot.png</code>.</p>` : '<div class="empty">Interactive volcano plot unavailable.</div>'}
          </div>
          ${downloads}
        </div>
        ${heatmapArtifact ? `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Top Differentially Expressed Genes Heatmap</h3><p class="section-note">Standardized expression heatmap for the top DESeq2-ranked genes across both cohorts.</p><div class="analysis-heatmap-legend" aria-label="Heatmap legend"><span class="analysis-heatmap-legend-label">Lower expression</span><span class="analysis-heatmap-legend-scale" aria-hidden="true"></span><span class="analysis-heatmap-legend-label">Higher expression</span></div><p class="section-note">Blue means lower relative expression for that gene, white is near the gene-level average, and red means higher relative expression.</p><div class="analysis-view-tabs" role="tablist" aria-label="Differential expression heatmap views"><button type="button" class="analysis-view-tab is-active" data-de-heatmap-view-btn="png" data-turn-index="${turnIndex}" role="tab" aria-selected="true">Original PNG</button><button type="button" class="analysis-view-tab${heatmapTableArtifact ? "" : " is-disabled"}" data-de-heatmap-view-btn="interactive" data-turn-index="${turnIndex}" data-heatmap-url="${escapeHtml(String(heatmapTableArtifact && heatmapTableArtifact.url ? heatmapTableArtifact.url : ""))}" data-heatmap-clustering-url="${escapeHtml(String(heatmapClusteringArtifact && heatmapClusteringArtifact.url ? heatmapClusteringArtifact.url : ""))}" role="tab" aria-selected="false"${heatmapTableArtifact ? "" : " disabled"}>Interactive heatmap</button></div><div class="analysis-view-panel is-active" data-de-heatmap-view-panel="png" data-turn-index="${turnIndex}"><div class="analysis-artifact-image-frame"><img class="analysis-artifact-image" src="${escapeHtml(String(heatmapArtifact.url || ""))}" alt="Top differentially expressed genes heatmap"></div></div><div class="analysis-view-panel" data-de-heatmap-view-panel="interactive" data-turn-index="${turnIndex}" data-heatmap-url="${escapeHtml(String(heatmapTableArtifact && heatmapTableArtifact.url ? heatmapTableArtifact.url : ""))}" data-heatmap-clustering-url="${escapeHtml(String(heatmapClusteringArtifact && heatmapClusteringArtifact.url ? heatmapClusteringArtifact.url : ""))}">${heatmapTableArtifact ? `<div class="analysis-heatmap-interactive"><div class="analysis-heatmap-dendrogram" id="analysis-plot-${turnIndex}-de-heatmap-dendrogram"></div>${plotPlaceholder(`analysis-plot-${turnIndex}-de-heatmap`, 520)}</div><p class="section-note" style="margin-top:10px;">Interactive view rendered from <code>top_genes_heatmap.tsv</code>. The canonical artifact remains <code>top_genes_heatmap.png</code>.</p>` : '<div class="empty">Interactive heatmap unavailable.</div>'}</div></div>` : ""}
        ${renderBarChartCard(`analysis-plot-${turnIndex}-de-summary`, "Differential Expression Summary", summaryItems, "label", "value")}
      `;
    }
    if (isPathwayEnrichmentContextMode(context.mode)) {
      const plotArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "pathway_plot.png");
      const resultsArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "pathway_results.tsv");
      const rankingsArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "gene_rankings.tsv");
      const summaryArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "summary.json");
      const downloads = renderArtifactDownloads("Result files", [plotArtifact, resultsArtifact, rankingsArtifact, summaryArtifact]);
      const summaryItems = [
        { label: "Dataset", value: String(context.dataset_name || "n/a") },
        { label: "Cohort A samples", value: Number(context.cohort_a_sample_count || 0) },
        { label: "Cohort B samples", value: Number(context.cohort_b_sample_count || 0) },
        { label: "Ranked genes", value: Number(context.ranked_gene_count || 0) },
        { label: "Pathways tested", value: Number(context.pathway_count || 0) },
        { label: "Significant pathways", value: Number(context.significant_pathway_count || 0) },
      ];
      const positiveText = Array.isArray(context.top_positive_pathway_labels) && context.top_positive_pathway_labels.length
        ? context.top_positive_pathway_labels.map((item) => prettyHallmarkLabel(item)).join(", ")
        : Array.isArray(context.top_positive_pathways) && context.top_positive_pathways.length
          ? context.top_positive_pathways.map((item) => prettyHallmarkLabel(item)).join(", ")
          : "none at BH < 0.05";
      const negativeText = Array.isArray(context.top_negative_pathway_labels) && context.top_negative_pathway_labels.length
        ? context.top_negative_pathway_labels.map((item) => prettyHallmarkLabel(item)).join(", ")
        : Array.isArray(context.top_negative_pathways) && context.top_negative_pathways.length
          ? context.top_negative_pathways.map((item) => prettyHallmarkLabel(item)).join(", ")
          : "none at BH < 0.05";
      return `
        <div class="viz-card" style="grid-column: 1 / -1;">
          <h3>Hallmark Pathway Enrichment</h3>
          <p class="section-note">MSigDB Hallmark enrichment for ${escapeHtml(String(context.dataset_name || "the selected assay"))} using a DESeq2-ranked comparison.</p>
          <p class="section-note">Higher in Cohort A: ${escapeHtml(positiveText)}</p>
          <p class="section-note">Higher in Cohort B: ${escapeHtml(negativeText)}</p>
          ${plotArtifact ? `<div class="analysis-artifact-image-frame"><img class="analysis-artifact-image" src="${escapeHtml(String(plotArtifact.url || ""))}" alt="Hallmark pathway enrichment plot"></div>` : '<div class="empty">Pathway enrichment plot preview unavailable.</div>'}
          ${downloads}
        </div>
        ${renderBarChartCard(`analysis-plot-${turnIndex}-pathway-summary`, "Pathway Enrichment Summary", summaryItems, "label", "value")}
      `;
    }
    if (context.mode === "transcriptomics_medication_compare") {
      const comparisons = Array.isArray(context.comparisons) ? context.comparisons : [];
      const cards = comparisons.map((item, index) => {
        const title = `${item.medication_a || "Group A"} vs ${item.medication_b || "Group B"}`;
        const note = context.exploratory_note || "Exploratory transcriptomics comparison.";
        const thresholdNote = `Coloring is exploratory: red = log2FC >= 1 and p <= 0.05, blue = log2FC <= -1 and p <= 0.05, gray = everything else. Positive log2FC means higher in ${item.medication_a || "Group A"}; negative log2FC means higher in ${item.medication_b || "Group B"}.`;
        return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Exploratory Volcano Plot: ${escapeHtml(title)}</h3><p class="section-note">${escapeHtml(note)}</p><p class="section-note">${escapeHtml(thresholdNote)}</p>${plotPlaceholder(`analysis-plot-${turnIndex}-assay-volcano-${index}`, 420)}</div>`;
      });
      return cards.join("") || '<div class="empty">No exploratory transcriptomics comparison plot available.</div>';
    }
    if (context.mode === "trajectory_compare" || context.mode === "trajectory_compare_response") {
      const unit = context.unit ? ` (${context.unit})` : "";
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Trajectory Comparison${unit}</h3>${plotPlaceholder(`analysis-plot-${turnIndex}-trajectory-compare`, 400)}</div>`;
    }
    if (context.mode === "trajectory" || context.mode === "trajectory_response") {
      const unit = context.unit ? ` (${context.unit})` : "";
      const heading = context.treatment ? `Response to ${context.treatment}${unit}` : `Trajectory of ${context.measure || "measure"}${unit}`;
      const coverageItems = [
        { label: "Patients", value: Number(context.patient_count || 0) },
        { label: "Summary points", value: Number((context.summary_points || []).length) },
      ];
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>${escapeHtml(heading)}</h3>${plotPlaceholder(`analysis-plot-${turnIndex}-trajectory`, 400)}</div>${renderBarChartCard(`analysis-plot-${turnIndex}-trajectory-coverage`, "Trajectory Coverage", coverageItems, "label", "value")}`;
    }
    if (context.mode === "survival_compare") {
      const eventLabel = formatTimeToEventLabel(context);
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Kaplan-Meier Time-to-Event Comparison</h3><p class="section-note">Event: ${escapeHtml(eventLabel)}</p>${plotPlaceholder(`analysis-plot-${turnIndex}-survival-compare`, 360)}</div>`;
    }
    if (context.mode === "survival") {
      const eventLabel = formatTimeToEventLabel(context);
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Kaplan-Meier Time-to-Event Analysis</h3><p class="section-note">Event: ${escapeHtml(eventLabel)}</p>${plotPlaceholder(`analysis-plot-${turnIndex}-survival`, 360)}</div>`;
    }
    if (context.mode === "compare") {
      const cohortA = context.cohort_a || {};
      const cohortB = context.cohort_b || {};
      const overviewItems = [
        { label: "Patients", value: Number((cohortA.overview && cohortA.overview.patient_count) || 0) },
        { label: "Timepoints", value: Number((cohortA.overview && cohortA.overview.timepoint_count) || 0) },
        { label: "Patients", value: Number((cohortB.overview && cohortB.overview.patient_count) || 0) },
        { label: "Timepoints", value: Number((cohortB.overview && cohortB.overview.timepoint_count) || 0) },
      ];
      const diseaseDeltaItems = (context.disease_deltas || []).slice(0, 8).map((item) => ({ label: item.delta > 0 ? `${item.label} (A)` : item.delta < 0 ? `${item.label} (B)` : `${item.label} (=)`, value: Math.abs(Number(item.delta || 0)) }));
      const medicationDeltaItems = (context.medication_deltas || []).slice(0, 8).map((item) => ({ label: item.delta > 0 ? `${item.label} (A)` : item.delta < 0 ? `${item.label} (B)` : `${item.label} (=)`, value: Math.abs(Number(item.delta || 0)) }));
      return `${renderBarChartCard(`analysis-plot-${turnIndex}-compare-a`, "Cohort A Profile", overviewItems.slice(0, 2), "label", "value")}${renderBarChartCard(`analysis-plot-${turnIndex}-compare-b`, "Cohort B Profile", overviewItems.slice(2), "label", "value")}${renderBarChartCard(`analysis-plot-${turnIndex}-compare-disease`, "Disease Differences", diseaseDeltaItems, "label", "value")}${renderBarChartCard(`analysis-plot-${turnIndex}-compare-medication`, "Medication Differences", medicationDeltaItems, "label", "value")}`;
    }
    const diseaseItems = (context.top_diseases || []).slice(0, 8).map((item) => ({ label: item.disease, value: item.patient_count }));
    const medicationItems = (context.top_medications || []).slice(0, 8).map((item) => ({ label: item.medication, value: item.patient_count }));
    const periodItems = (context.timepoints_by_period || []).slice(0, 12).map((item) => ({ label: item.period, value: item.timepoint_count }));
    const visitItems = (context.visit_distribution || []).slice(0, 12).map((item) => ({ label: item.label, value: item.value }));
    return `${renderBarChartCard(`analysis-plot-${turnIndex}-summary-disease`, "Top Diseases", diseaseItems, "label", "value")}${renderBarChartCard(`analysis-plot-${turnIndex}-summary-medication`, "Top Medications", medicationItems, "label", "value")}${renderBarChartCard(`analysis-plot-${turnIndex}-summary-period`, "Timepoints Over Time", periodItems, "label", "value")}${renderBarChartCard(`analysis-plot-${turnIndex}-summary-visits`, "Visits Per Patient", visitItems, "label", "value")}`;
  }

  function plotlyAvailable() {
    return typeof window !== "undefined" && window.Plotly && typeof window.Plotly.newPlot === "function";
  }

  function mountPlot(targetId, traces, layout) {
    const el = document.getElementById(targetId);
    if (!el) return;
    if (!plotlyAvailable()) {
      el.innerHTML = '<div class="empty">Plot rendering unavailable.</div>';
      return;
    }
    window.Plotly.newPlot(el, traces, layout, basePlotConfig());
  }

  function buildHorizontalBar(items, labelKey, valueKey, color) {
    return {
      traces: [{
        type: "bar",
        orientation: "h",
        y: items.map((item) => item[labelKey]),
        x: items.map((item) => Number(item[valueKey] || 0)),
        marker: { color, line: { color, width: 1 } },
        hovertemplate: "%{y}: %{x}<extra></extra>",
      }],
      layout: basePlotLayout({
        margin: { t: 18, r: 24, b: 36, l: 140 },
      }),
    };
  }

  function buildKaplanMeierPlot(seriesList) {
    const series = (Array.isArray(seriesList) ? seriesList : []).filter((item) => Array.isArray(item.points) && item.points.length);
    const traces = series.map((item, index) => ({
      type: "scatter",
      mode: "lines",
      name: item.label || `Series ${index + 1}`,
      line: {
        color: ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
        width: 3,
        shape: "hv",
      },
      x: item.points.map((point) => Number(point.time_days || 0)),
      y: item.points.map((point) => Number(point.survival_probability || 0)),
      hovertemplate: `${escapeHtml(item.label || `Series ${index + 1}`)}<br>Days: %{x}<br>Survival: %{y:.2%}<extra></extra>`,
    }));
    return {
      traces,
      layout: basePlotLayout({
        xaxis: {
          ...basePlotLayout().xaxis,
          title: { text: "Days since first dated observation of the selected measure", font: { color: "#61758c", size: 12 } },
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: "Event-free probability", font: { color: "#61758c", size: 12 } },
          tickformat: ".0%",
          range: [0, 1],
        },
      }),
    };
  }

  function buildTrajectoryPlot(seriesList, summarySeries, xAxisTitle) {
    const patientSeries = (Array.isArray(seriesList) ? seriesList : []).filter((item) => Array.isArray(item.points) && item.points.length);
    const summary = summarySeries && Array.isArray(summarySeries.points) ? summarySeries.points : [];
    const labels = Array.from(new Set(patientSeries.flatMap((item) => item.points.map((point) => String(point.x_label || point.x || ""))).concat(summary.map((point) => String(point.x_label || point.x || "")))));
    const traces = patientSeries.slice(0, 12).map((item, index) => ({
      type: "scatter",
      mode: "lines+markers",
      name: item.label || `Patient ${index + 1}`,
      showlegend: false,
      opacity: 0.35,
      line: {
        color: ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
        width: 1.5,
      },
      marker: { size: 5 },
      x: item.points.map((point) => String(point.x_label || point.x || "")),
      y: item.points.map((point) => Number(point.value || 0)),
      hovertemplate: "%{x}<br>%{y}<extra></extra>",
    }));
    traces.push({
      type: "scatter",
      mode: "lines+markers",
      name: summarySeries.label || "Cohort median",
      line: { color: "#1d4ed8", width: 3 },
      marker: { size: 7, color: "#1d4ed8" },
      x: summary.map((point) => String(point.x_label || point.x || "")),
      y: summary.map((point) => Number(point.value || 0)),
      hovertemplate: `${escapeHtml(summarySeries.label || "Cohort median")}<br>%{x}<br>%{y}<extra></extra>`,
    });
    return {
      traces,
      layout: basePlotLayout({
        margin: { t: 28, r: 24, b: 112, l: 56 },
        xaxis: {
          ...basePlotLayout().xaxis,
          type: "category",
          categoryorder: "array",
          categoryarray: labels,
          tickangle: -35,
          title: { text: xAxisTitle || "Days since first dated observation", font: { color: "#61758c", size: 12 } },
        },
      }),
    };
  }

  function buildTrajectoryComparisonPlot(seriesList, xAxisTitle) {
    const series = (Array.isArray(seriesList) ? seriesList : []).filter((item) => Array.isArray(item.points) && item.points.length);
    const labels = Array.from(new Set(series.flatMap((item) => item.points.map((point) => String(point.x_label || point.x || "")))));
    const traces = series.map((item, index) => ({
      type: "scatter",
      mode: "lines+markers",
      name: item.label || `Series ${index + 1}`,
      showlegend: item.showLegend !== false,
      opacity: item.opacity !== undefined ? item.opacity : 1,
      line: {
        color: item.lineColor || ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
        width: item.lineWidth || 3,
      },
      marker: {
        size: item.markerSize || 7,
        color: item.lineColor || ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
      },
      x: item.points.map((point) => String(point.x_label || point.x || "")),
      y: item.points.map((point) => Number(point.value || 0)),
      hovertemplate: `${escapeHtml(item.label || `Series ${index + 1}`)}<br>%{x}<br>%{y}<extra></extra>`,
    }));
    return {
      traces,
      layout: basePlotLayout({
        margin: { t: 28, r: 24, b: 112, l: 56 },
        xaxis: {
          ...basePlotLayout().xaxis,
          type: "category",
          categoryorder: "array",
          categoryarray: labels,
          tickangle: -35,
          title: { text: xAxisTitle || "Days since first dated observation", font: { color: "#61758c", size: 12 } },
        },
      }),
    };
  }

  function buildTrajectoryComparisonSeries(context) {
    const cohortA = context.cohort_a || {};
    const cohortB = context.cohort_b || {};
    const patientSeriesA = Array.isArray(cohortA.patient_series) ? cohortA.patient_series : [];
    const patientSeriesB = Array.isArray(cohortB.patient_series) ? cohortB.patient_series : [];
    const totalPatientSeries = patientSeriesA.length + patientSeriesB.length;
    const includePatientLines = totalPatientSeries > 0 && totalPatientSeries <= 50;
    const output = [];

    if (includePatientLines) {
      patientSeriesA.forEach((item, index) => {
        output.push({
          label: `Cohort A · ${item.patient_id || `Patient ${index + 1}`}`,
          points: item.points || [],
          lineColor: "#2563eb",
          opacity: 0.28,
          lineWidth: 1.4,
          markerSize: 4,
          showLegend: false,
        });
      });
      patientSeriesB.forEach((item, index) => {
        output.push({
          label: `Cohort B · ${item.patient_id || `Patient ${index + 1}`}`,
          points: item.points || [],
          lineColor: "#dc2626",
          opacity: 0.28,
          lineWidth: 1.4,
          markerSize: 4,
          showLegend: false,
        });
      });
    }

    output.push({
      label: "Cohort A median",
      points: cohortA.summary_points || [],
      lineColor: "#1d4ed8",
      opacity: 1,
      lineWidth: 3,
      markerSize: 7,
      showLegend: true,
    });
    output.push({
      label: "Cohort B median",
      points: cohortB.summary_points || [],
      lineColor: "#b91c1c",
      opacity: 1,
      lineWidth: 3,
      markerSize: 7,
      showLegend: true,
    });
    return output;
  }

  function buildExploratoryVolcanoPlot(points, comparisonLabel) {
    const rows = (Array.isArray(points) ? points : []).filter((item) => item && item.gene_id !== undefined);
    const colors = rows.map((item) => {
      const log2fc = Number(item.log2_fold_change || 0);
      const negLog10P = Number(item.neg_log10_p || 0);
      const significant = negLog10P >= 1.3;
      const largeEffect = Math.abs(log2fc) >= 1;
      if (!(significant && largeEffect)) return "#94a3b8";
      return log2fc > 0 ? "#dc2626" : "#2563eb";
    });
    return {
      traces: [{
        type: "scatter",
        mode: "markers",
        name: comparisonLabel || "Exploratory comparison",
        x: rows.map((item) => Number(item.log2_fold_change || 0)),
        y: rows.map((item) => Number(item.neg_log10_p || 0)),
        text: rows.map((item) => String(item.gene_id || "")),
        customdata: rows.map((item) => [String(item.gene_id || ""), Number(item.mean_log2_cpm_a || 0), Number(item.mean_log2_cpm_b || 0), Number(item.p_value || 1)]),
        marker: {
          size: 8,
          color: colors,
          opacity: 0.8,
        },
        hovertemplate: "Gene: %{customdata[0]}<br>log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<br>Mean A: %{customdata[1]:.2f}<br>Mean B: %{customdata[2]:.2f}<br>p: %{customdata[3]:.3g}<extra></extra>",
      }],
      layout: basePlotLayout({
        xaxis: {
          ...basePlotLayout().xaxis,
          title: { text: "Exploratory log2 fold change", font: { color: "#61758c", size: 12 } },
          zeroline: true,
          zerolinecolor: "rgba(148,163,184,0.35)",
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: "Exploratory -log10(p)", font: { color: "#61758c", size: 12 } },
        },
      }),
    };
  }

  async function loadTabularArtifactRows(url) {
    const response = await fetch(String(url || ""));
    if (!response.ok) {
      throw new Error("Unable to load interactive plot data.");
    }
    const text = await response.text();
    const lines = String(text || "").split(/\r?\n/).filter((line) => line.trim());
    if (!lines.length) return [];
    const headers = lines[0].split("\t").map((item) => item.trim());
    return lines.slice(1).map((line) => {
      const values = line.split("\t");
      const row = {};
      headers.forEach((header, index) => {
        row[header] = values[index] !== undefined ? values[index] : "";
      });
      return row;
    });
  }

  async function loadJsonArtifact(url) {
    const response = await fetch(String(url || ""));
    if (!response.ok) {
      throw new Error("Unable to load interactive plot metadata.");
    }
    return response.json();
  }

  function buildDifferentialExpressionVolcanoPlot(points, datasetName) {
    const rows = (Array.isArray(points) ? points : []).filter((item) => item && item.gene_id !== undefined);
    const colors = rows.map((item) => {
      const adjP = Number(item.adj_p_value || 1);
      return adjP < 0.05 ? "#d9485f" : "#94a3b8";
    });
    const topHits = rows
      .slice()
      .sort((left, right) => {
        const leftAdj = Number(left.adj_p_value || 1);
        const rightAdj = Number(right.adj_p_value || 1);
        if (leftAdj !== rightAdj) return leftAdj - rightAdj;
        return Math.abs(Number(right.log2_fold_change || 0)) - Math.abs(Number(left.log2_fold_change || 0));
      })
      .slice(0, 5);
    return {
      traces: [{
        type: "scatter",
        mode: "markers",
        name: datasetName || "Differential expression",
        x: rows.map((item) => Number(item.log2_fold_change || 0)),
        y: rows.map((item) => Number(item.neg_log10_p || 0)),
        text: rows.map((item) => String(item.gene_id || "")),
        customdata: rows.map((item) => [
          String(item.gene_id || ""),
          Number(item.p_value || 1),
          Number(item.adj_p_value || 1),
        ]),
        marker: {
          size: 8,
          color: colors,
          opacity: 0.82,
        },
        hovertemplate: "Gene: %{customdata[0]}<br>log2FC: %{x:.3f}<br>-log10(p): %{y:.3f}<br>p: %{customdata[1]:.3g}<br>adj p: %{customdata[2]:.3g}<extra></extra>",
      }, {
        type: "scatter",
        mode: "text",
        name: "Top hits",
        x: topHits.map((item) => Number(item.log2_fold_change || 0)),
        y: topHits.map((item) => Number(item.neg_log10_p || 0)),
        text: topHits.map((item) => String(item.gene_id || "")),
        textposition: "top center",
        textfont: { color: "#111827", size: 11 },
        hoverinfo: "skip",
        showlegend: false,
      }],
      layout: basePlotLayout({
        xaxis: {
          ...basePlotLayout().xaxis,
          title: { text: "log2 fold change", font: { color: "#61758c", size: 12 } },
          zeroline: true,
          zerolinecolor: "#475569",
          zerolinewidth: 1,
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: "-log10(p-value)", font: { color: "#61758c", size: 12 } },
        },
        shapes: [{
          type: "line",
          x0: 0,
          x1: 0,
          y0: 0,
          y1: 1,
          xref: "x",
          yref: "paper",
          line: { color: "#475569", width: 1, dash: "dot" },
        }],
      }),
    };
  }

  function buildDifferentialExpressionHeatmap(rows, datasetName) {
    const matrixRows = Array.isArray(rows) ? rows.filter((item) => item && Object.keys(item).length) : [];
    const sampleNames = matrixRows.length
      ? Object.keys(matrixRows[0]).filter((key) => key !== "gene_id")
      : [];
    const topMargin = 32;
    const bottomMargin = 120;
    return {
      traces: [{
        type: "heatmap",
        x: sampleNames,
        y: matrixRows.map((item) => String(item.gene_id || "")),
        z: matrixRows.map((item) => sampleNames.map((sample) => {
          const value = Number(item[sample]);
          return Number.isFinite(value) ? value : null;
        })),
        colorscale: [
          [0, "#2563eb"],
          [0.5, "#f8fafc"],
          [1, "#dc2626"],
        ],
        zmid: 0,
        showscale: false,
        hovertemplate: "Gene: %{y}<br>Sample: %{x}<br>Scaled expression: %{z:.2f}<extra></extra>",
      }],
      layout: basePlotLayout({
        margin: { t: topMargin, r: 120, b: bottomMargin, l: 24 },
        title: datasetName ? { text: datasetName, font: { color: "#61758c", size: 12 } } : undefined,
        xaxis: {
          ...basePlotLayout().xaxis,
          tickangle: -35,
          side: "bottom",
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          automargin: true,
          side: "right",
        },
      }),
    };
  }

  function buildHallmarkPathwayPlot(rows, datasetName) {
    const rankedRows = (Array.isArray(rows) ? rows : [])
      .filter((item) => item && item.pathway !== undefined)
      .map((item) => ({
        pathway: String(item.display_label || item.pathway || ""),
        nes: Number(item.NES || 0),
        padj: Number(item.padj || 1),
      }))
      .filter((item) => item.pathway);
    const plotRows = rankedRows.slice(0, 20).reverse();
    const colors = plotRows.map((item) => (item.nes >= 0 ? "#2563eb" : "#d9485f"));
    return {
      traces: [{
        type: "bar",
        orientation: "h",
        y: plotRows.map((item) => item.pathway),
        x: plotRows.map((item) => item.nes),
        marker: { color: colors },
        customdata: plotRows.map((item) => [item.padj]),
        hovertemplate: "Pathway: %{y}<br>NES: %{x:.3f}<br>adj p: %{customdata[0]:.3g}<extra></extra>",
      }],
      layout: basePlotLayout({
        margin: { t: 28, r: 24, b: 56, l: 220 },
        title: datasetName ? { text: datasetName, font: { color: "#61758c", size: 12 } } : undefined,
        xaxis: {
          ...basePlotLayout().xaxis,
          title: { text: "Normalized enrichment score (NES)", font: { color: "#61758c", size: 12 } },
          zeroline: true,
          zerolinecolor: "#475569",
          zerolinewidth: 1,
        },
      }),
    };
  }

  function euclideanDistance(valuesA, valuesB) {
    let total = 0;
    for (let index = 0; index < valuesA.length; index += 1) {
      const delta = Number(valuesA[index] || 0) - Number(valuesB[index] || 0);
      total += delta * delta;
    }
    return Math.sqrt(total);
  }

  function clusterDistance(leftCluster, rightCluster, pairwiseDistances) {
    let maxDistance = 0;
    leftCluster.members.forEach((leftMember) => {
      rightCluster.members.forEach((rightMember) => {
        const key = leftMember < rightMember ? `${leftMember}:${rightMember}` : `${rightMember}:${leftMember}`;
        maxDistance = Math.max(maxDistance, Number(pairwiseDistances.get(key) || 0));
      });
    });
    return maxDistance;
  }

  function buildHeatmapRowCluster(matrixRows, sampleNames) {
    if (!Array.isArray(matrixRows) || matrixRows.length < 2 || !Array.isArray(sampleNames) || !sampleNames.length) {
      return null;
    }
    const pairwiseDistances = new Map();
    matrixRows.forEach((row, index) => {
      const leftValues = sampleNames.map((sample) => Number(row[sample] || 0));
      for (let rightIndex = index + 1; rightIndex < matrixRows.length; rightIndex += 1) {
        const rightValues = sampleNames.map((sample) => Number(matrixRows[rightIndex][sample] || 0));
        pairwiseDistances.set(`${index}:${rightIndex}`, euclideanDistance(leftValues, rightValues));
      }
    });
    let nextClusterId = matrixRows.length;
    let clusters = matrixRows.map((row, index) => ({
      id: index,
      members: [index],
      height: 0,
      left: null,
      right: null,
      label: String(row.gene_id || `Gene ${index + 1}`),
    }));
    while (clusters.length > 1) {
      let bestPair = null;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (let leftIndex = 0; leftIndex < clusters.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < clusters.length; rightIndex += 1) {
          const distance = clusterDistance(clusters[leftIndex], clusters[rightIndex], pairwiseDistances);
          if (distance < bestDistance) {
            bestDistance = distance;
            bestPair = [leftIndex, rightIndex];
          }
        }
      }
      if (!bestPair) break;
      const [leftIndex, rightIndex] = bestPair;
      const leftCluster = clusters[leftIndex];
      const rightCluster = clusters[rightIndex];
      const mergedCluster = {
        id: nextClusterId,
        members: leftCluster.members.concat(rightCluster.members),
        height: bestDistance,
        left: leftCluster,
        right: rightCluster,
        label: "",
      };
      nextClusterId += 1;
      clusters = clusters.filter((_, index) => index !== leftIndex && index !== rightIndex);
      clusters.push(mergedCluster);
    }
    return clusters[0] || null;
  }

  function flattenHeatmapClusterOrder(node) {
    if (!node) return [];
    if (!node.left && !node.right) return [node.members[0]];
    return flattenHeatmapClusterOrder(node.left).concat(flattenHeatmapClusterOrder(node.right));
  }

  function buildHeatmapClusterTreeFromR(payload) {
    const labels = Array.isArray(payload && payload.labels) ? payload.labels.map((item) => String(item || "")) : [];
    const merge = Array.isArray(payload && payload.merge) ? payload.merge : [];
    const heights = Array.isArray(payload && payload.height) ? payload.height : [];
    if (!labels.length || !merge.length || merge.length !== heights.length) return null;
    const leafNodes = new Map();
    labels.forEach((label, index) => {
      leafNodes.set(index + 1, {
        id: -(index + 1),
        members: [index],
        height: 0,
        left: null,
        right: null,
        label,
      });
    });
    const clusterNodes = new Map();
    for (let index = 0; index < merge.length; index += 1) {
      const pair = Array.isArray(merge[index]) ? merge[index] : [];
      if (pair.length !== 2) return null;
      const resolveNode = (value) => {
        if (value < 0) return leafNodes.get(Math.abs(value)) || null;
        return clusterNodes.get(value) || null;
      };
      const left = resolveNode(Number(pair[0]));
      const right = resolveNode(Number(pair[1]));
      if (!left || !right) return null;
      clusterNodes.set(index + 1, {
        id: index + 1,
        members: left.members.concat(right.members),
        height: Number(heights[index] || 0),
        left,
        right,
        label: "",
      });
    }
    return clusterNodes.get(merge.length) || null;
  }

  function buildHeatmapDendrogramSvg(clusterRoot, orderedRows) {
    if (!clusterRoot || !Array.isArray(orderedRows) || orderedRows.length < 2) return "";
    const width = 140;
    const height = 520;
    const paddingTop = 32;
    const paddingBottom = 120;
    const usableHeight = Math.max(height - paddingTop - paddingBottom, 80);
    const rowHeight = usableHeight / orderedRows.length;
    const leafY = new Map();
    orderedRows.forEach((row, index) => {
      leafY.set(String(row.gene_id || ""), paddingTop + index * rowHeight + rowHeight / 2);
    });
    const maxHeight = Math.max(Number(clusterRoot.height || 0), 1);
    const lines = [];

    function renderNode(node) {
      if (!node.left && !node.right) {
        return {
          x: width,
          y: leafY.get(String(node.label || "")) || paddingTop,
        };
      }
      const left = renderNode(node.left);
      const right = renderNode(node.right);
      const x = width - (Number(node.height || 0) / maxHeight) * (width - 12);
      lines.push(`<line x1="${x.toFixed(2)}" y1="${left.y.toFixed(2)}" x2="${left.x.toFixed(2)}" y2="${left.y.toFixed(2)}"></line>`);
      lines.push(`<line x1="${x.toFixed(2)}" y1="${right.y.toFixed(2)}" x2="${right.x.toFixed(2)}" y2="${right.y.toFixed(2)}"></line>`);
      lines.push(`<line x1="${x.toFixed(2)}" y1="${left.y.toFixed(2)}" x2="${x.toFixed(2)}" y2="${right.y.toFixed(2)}"></line>`);
      return { x, y: (left.y + right.y) / 2 };
    }

    renderNode(clusterRoot);
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Heatmap row dendrogram"><g class="analysis-heatmap-dendrogram-lines">${lines.join("")}</g></svg>`;
  }

  async function mountDifferentialExpressionInteractivePlot(turnIndex, payload) {
    const panelEl = document.querySelector(`[data-de-view-panel="interactive"][data-turn-index="${turnIndex}"]`);
    if (!panelEl || panelEl.dataset.loaded === "true" || panelEl.dataset.loading === "true") {
      return;
    }
    const plotEl = document.getElementById(`analysis-plot-${turnIndex}-de-volcano`);
    if (!plotEl) return;
    const artifactUrl = String(panelEl.dataset.volcanoUrl || "").trim();
    if (!artifactUrl) {
      plotEl.innerHTML = '<div class="empty">Interactive volcano plot unavailable.</div>';
      panelEl.dataset.loaded = "true";
      return;
    }
    panelEl.dataset.loading = "true";
    plotEl.innerHTML = '<div class="empty">Loading interactive plot...</div>';
    try {
      const rows = await loadTabularArtifactRows(artifactUrl);
      const context = payload && payload.data ? payload.data.context : null;
      const volcano = buildDifferentialExpressionVolcanoPlot(rows, context && context.dataset_name ? context.dataset_name : "");
      mountPlot(`analysis-plot-${turnIndex}-de-volcano`, volcano.traces, volcano.layout);
      panelEl.dataset.loaded = "true";
    } catch (_error) {
      plotEl.innerHTML = '<div class="empty">Unable to render the interactive volcano plot.</div>';
    } finally {
      panelEl.dataset.loading = "false";
    }
  }

  async function mountDifferentialExpressionInteractiveHeatmap(turnIndex, payload) {
    const panelEl = document.querySelector(`[data-de-heatmap-view-panel="interactive"][data-turn-index="${turnIndex}"]`);
    if (!panelEl || panelEl.dataset.loaded === "true" || panelEl.dataset.loading === "true") {
      return;
    }
    const plotEl = document.getElementById(`analysis-plot-${turnIndex}-de-heatmap`);
    if (!plotEl) return;
    const artifactUrl = String(panelEl.dataset.heatmapUrl || "").trim();
    if (!artifactUrl) {
      plotEl.innerHTML = '<div class="empty">Interactive heatmap unavailable.</div>';
      panelEl.dataset.loaded = "true";
      return;
    }
    panelEl.dataset.loading = "true";
    plotEl.innerHTML = '<div class="empty">Loading interactive heatmap...</div>';
    try {
      const clusteringUrl = String(panelEl.dataset.heatmapClusteringUrl || "").trim();
      const [rows, clusteringPayload] = await Promise.all([
        loadTabularArtifactRows(artifactUrl),
        clusteringUrl ? loadJsonArtifact(clusteringUrl).catch(() => null) : Promise.resolve(null),
      ]);
      const context = payload && payload.data ? payload.data.context : null;
      const sampleNames = rows.length ? Object.keys(rows[0]).filter((key) => key !== "gene_id") : [];
      const exactClusterRoot = buildHeatmapClusterTreeFromR(clusteringPayload);
      const exportedOrder = Array.isArray(clusteringPayload && clusteringPayload.order)
        ? clusteringPayload.order.map((value) => Number(value) - 1).filter((value) => Number.isInteger(value) && value >= 0)
        : [];
      const fallbackClusterRoot = !exactClusterRoot ? buildHeatmapRowCluster(rows, sampleNames) : null;
      const clusterRoot = exactClusterRoot || fallbackClusterRoot;
      const rowOrder = exportedOrder.length
        ? exportedOrder
        : clusterRoot
          ? flattenHeatmapClusterOrder(clusterRoot)
          : rows.map((_, index) => index);
      const orderedRows = rowOrder.map((index) => rows[index]).filter(Boolean);
      const dendrogramEl = document.getElementById(`analysis-plot-${turnIndex}-de-heatmap-dendrogram`);
      if (dendrogramEl) {
        dendrogramEl.innerHTML = clusterRoot ? buildHeatmapDendrogramSvg(clusterRoot, orderedRows) : '<div class="empty">Dendrogram unavailable.</div>';
      }
      const heatmap = buildDifferentialExpressionHeatmap(orderedRows, context && context.dataset_name ? context.dataset_name : "");
      mountPlot(`analysis-plot-${turnIndex}-de-heatmap`, heatmap.traces, heatmap.layout);
      panelEl.dataset.loaded = "true";
    } catch (_error) {
      plotEl.innerHTML = '<div class="empty">Unable to render the interactive heatmap.</div>';
    } finally {
      panelEl.dataset.loading = "false";
    }
  }

  async function mountHallmarkInteractivePlot(turnIndex, payload) {
    const panelEl = document.querySelector(`[data-pathway-view-panel="interactive"][data-turn-index="${turnIndex}"]`);
    if (!panelEl || panelEl.dataset.loaded === "true" || panelEl.dataset.loading === "true") {
      return;
    }
    const plotEl = document.getElementById(`analysis-plot-${turnIndex}-workflow-pathway`);
    if (!plotEl) return;
    const artifactUrl = String(panelEl.dataset.pathwayUrl || "").trim();
    if (!artifactUrl) {
      plotEl.innerHTML = '<div class="empty">Interactive pathway plot unavailable.</div>';
      panelEl.dataset.loaded = "true";
      return;
    }
    panelEl.dataset.loading = "true";
    plotEl.innerHTML = '<div class="empty">Loading interactive pathway plot...</div>';
    try {
      const rows = await loadTabularArtifactRows(artifactUrl);
      const context = payload && payload.data ? payload.data.context : null;
      const hallmarkContext = context && context.hallmark && typeof context.hallmark === "object" ? context.hallmark : null;
      const pathway = buildHallmarkPathwayPlot(rows, hallmarkContext && hallmarkContext.dataset_name ? hallmarkContext.dataset_name : "");
      mountPlot(`analysis-plot-${turnIndex}-workflow-pathway`, pathway.traces, pathway.layout);
      panelEl.dataset.loaded = "true";
    } catch (_error) {
      plotEl.innerHTML = '<div class="empty">Unable to render the interactive pathway plot.</div>';
    } finally {
      panelEl.dataset.loading = "false";
    }
  }

  function mountAnalysisPlots() {
    state.analysisTurns.forEach((turn, turnIndex) => {
      if (!turn || !turn.showPlots || !turn.payload || !turn.payload.data) return;
      const context = turn.payload.data.context;
      if (!context) return;
      if (context.mode === "transcriptomics_medication_compare") {
        (context.comparisons || []).forEach((item, comparisonIndex) => {
          const points = Array.isArray(item.exploratory_volcano_points) ? item.exploratory_volcano_points : [];
          if (!points.length) return;
          const volcano = buildExploratoryVolcanoPlot(points, `${item.medication_a || "A"} vs ${item.medication_b || "B"}`);
          mountPlot(`analysis-plot-${turnIndex}-assay-volcano-${comparisonIndex}`, volcano.traces, volcano.layout);
        });
        return;
      }
      if (isDifferentialExpressionContextMode(context.mode)) {
        const summary = buildHorizontalBar([
          { label: "Cohort A samples", value: Number(context.cohort_a_sample_count || 0) },
          { label: "Cohort B samples", value: Number(context.cohort_b_sample_count || 0) },
          { label: "Genes tested", value: Number(context.gene_count || 0) },
          { label: "Significant genes", value: Number(context.significant_gene_count || 0) },
        ], "label", "value", "#2563eb");
        mountPlot(`analysis-plot-${turnIndex}-de-summary`, summary.traces, summary.layout);
        return;
      }
      if (isPathwayEnrichmentContextMode(context.mode)) {
        const summary = buildHorizontalBar([
          { label: "Cohort A samples", value: Number(context.cohort_a_sample_count || 0) },
          { label: "Cohort B samples", value: Number(context.cohort_b_sample_count || 0) },
          { label: "Ranked genes", value: Number(context.ranked_gene_count || 0) },
          { label: "Pathways tested", value: Number(context.pathway_count || 0) },
          { label: "Significant pathways", value: Number(context.significant_pathway_count || 0) },
        ], "label", "value", "#2563eb");
        mountPlot(`analysis-plot-${turnIndex}-pathway-summary`, summary.traces, summary.layout);
        return;
      }
      if (context.mode === "workflow_transcriptomics_signature") {
        const deContext = context.deseq2 && typeof context.deseq2 === "object" ? context.deseq2 : {};
        const hallmarkContext = context.hallmark && typeof context.hallmark === "object" ? context.hallmark : {};
        const deSummary = buildHorizontalBar([
          { label: "Cohort A samples", value: Number(deContext.cohort_a_sample_count || 0) },
          { label: "Cohort B samples", value: Number(deContext.cohort_b_sample_count || 0) },
          { label: "Genes tested", value: Number(deContext.gene_count || 0) },
          { label: "Significant genes", value: Number(deContext.significant_gene_count || 0) },
        ], "label", "value", "#2563eb");
        mountPlot(`analysis-plot-${turnIndex}-workflow-de-summary`, deSummary.traces, deSummary.layout);
        const pathwaySummary = buildHorizontalBar([
          { label: "Ranked genes", value: Number(hallmarkContext.ranked_gene_count || 0) },
          { label: "Pathways tested", value: Number(hallmarkContext.pathway_count || 0) },
          { label: "Significant pathways", value: Number(hallmarkContext.significant_pathway_count || 0) },
        ], "label", "value", "#059669");
        mountPlot(`analysis-plot-${turnIndex}-workflow-pathway-summary`, pathwaySummary.traces, pathwaySummary.layout);
        return;
      }
      if (context.mode === "trajectory_compare" || context.mode === "trajectory_compare_response") {
        const comparison = buildTrajectoryComparisonPlot(buildTrajectoryComparisonSeries(context), context.time_axis_label);
        mountPlot(`analysis-plot-${turnIndex}-trajectory-compare`, comparison.traces, comparison.layout);
        return;
      }
      if (context.mode === "trajectory" || context.mode === "trajectory_response") {
        const trajectory = buildTrajectoryPlot(
          context.patient_series || [],
          { label: context.treatment ? "Median response" : "Cohort median", points: context.summary_points || [] },
          context.time_axis_label,
        );
        mountPlot(`analysis-plot-${turnIndex}-trajectory`, trajectory.traces, trajectory.layout);
        const coverage = buildHorizontalBar([
          { label: "Patients", value: Number(context.patient_count || 0) },
          { label: "Summary points", value: Number((context.summary_points || []).length) },
        ], "label", "value", "#2563eb");
        mountPlot(`analysis-plot-${turnIndex}-trajectory-coverage`, coverage.traces, coverage.layout);
        return;
      }
      if (context.mode === "survival_compare") {
        const cohortA = context.cohort_a || {};
        const cohortB = context.cohort_b || {};
        const survival = buildKaplanMeierPlot([
          { label: `Cohort A (${cohortA.patient_count || 0} patients)`, points: cohortA.curve_points || [] },
          { label: `Cohort B (${cohortB.patient_count || 0} patients)`, points: cohortB.curve_points || [] },
        ]);
        mountPlot(`analysis-plot-${turnIndex}-survival-compare`, survival.traces, survival.layout);
        const aSummary = buildHorizontalBar([
          { label: "Patients", value: Number(cohortA.patient_count || 0) },
          { label: "Events", value: Number(cohortA.event_count || 0) },
          { label: "Censored", value: Number(cohortA.censored_count || 0) },
        ], "label", "value", "#2563eb");
        const bSummary = buildHorizontalBar([
          { label: "Patients", value: Number(cohortB.patient_count || 0) },
          { label: "Events", value: Number(cohortB.event_count || 0) },
          { label: "Censored", value: Number(cohortB.censored_count || 0) },
        ], "label", "value", "#0ea5e9");
        mountPlot(`analysis-plot-${turnIndex}-survival-a`, aSummary.traces, aSummary.layout);
        mountPlot(`analysis-plot-${turnIndex}-survival-b`, bSummary.traces, bSummary.layout);
        return;
      }
      if (context.mode === "survival") {
        const survival = buildKaplanMeierPlot([
          { label: `${context.measure || "Measure"} ${context.operator || ""} ${context.threshold || ""}`.trim(), points: context.curve_points || [] },
        ]);
        mountPlot(`analysis-plot-${turnIndex}-survival`, survival.traces, survival.layout);
        const summary = buildHorizontalBar([
          { label: "Patients", value: Number(context.patient_count || 0) },
          { label: "Events", value: Number(context.event_count || 0) },
          { label: "Censored", value: Number(context.censored_count || 0) },
        ], "label", "value", "#2563eb");
        const median = buildHorizontalBar([
          { label: "Median days", value: Number(context.median_survival_days || 0) },
        ], "label", "value", "#0ea5e9");
        mountPlot(`analysis-plot-${turnIndex}-survival-summary`, summary.traces, summary.layout);
        mountPlot(`analysis-plot-${turnIndex}-survival-median`, median.traces, median.layout);
        return;
      }
      if (context.mode === "compare") {
        const cohortA = context.cohort_a || {};
        const cohortB = context.cohort_b || {};
        const overviewA = buildHorizontalBar([
          { label: "Patients", value: Number((cohortA.overview && cohortA.overview.patient_count) || 0) },
          { label: "Timepoints", value: Number((cohortA.overview && cohortA.overview.timepoint_count) || 0) },
        ], "label", "value", "#2563eb");
        const overviewB = buildHorizontalBar([
          { label: "Patients", value: Number((cohortB.overview && cohortB.overview.patient_count) || 0) },
          { label: "Timepoints", value: Number((cohortB.overview && cohortB.overview.timepoint_count) || 0) },
        ], "label", "value", "#0ea5e9");
        const disease = buildHorizontalBar((context.disease_deltas || []).slice(0, 8).map((item) => ({
          label: item.delta > 0 ? `${item.label} (A)` : item.delta < 0 ? `${item.label} (B)` : `${item.label} (=)`,
          value: Math.abs(Number(item.delta || 0)),
        })), "label", "value", "#0ea5e9");
        const medication = buildHorizontalBar((context.medication_deltas || []).slice(0, 8).map((item) => ({
          label: item.delta > 0 ? `${item.label} (A)` : item.delta < 0 ? `${item.label} (B)` : `${item.label} (=)`,
          value: Math.abs(Number(item.delta || 0)),
        })), "label", "value", "#7c3aed");
        mountPlot(`analysis-plot-${turnIndex}-compare-a`, overviewA.traces, overviewA.layout);
        mountPlot(`analysis-plot-${turnIndex}-compare-b`, overviewB.traces, overviewB.layout);
        mountPlot(`analysis-plot-${turnIndex}-compare-disease`, disease.traces, disease.layout);
        mountPlot(`analysis-plot-${turnIndex}-compare-medication`, medication.traces, medication.layout);
        return;
      }
      const disease = buildHorizontalBar((context.top_diseases || []).slice(0, 8).map((item) => ({ label: item.disease, value: item.patient_count })), "label", "value", "#0ea5e9");
      const medication = buildHorizontalBar((context.top_medications || []).slice(0, 8).map((item) => ({ label: item.medication, value: item.patient_count })), "label", "value", "#2563eb");
      const period = buildHorizontalBar((context.timepoints_by_period || []).slice(0, 12).map((item) => ({ label: item.period, value: item.timepoint_count })), "label", "value", "#7c3aed");
      const visits = buildHorizontalBar((context.visit_distribution || []).slice(0, 12).map((item) => ({ label: item.label, value: item.value })), "label", "value", "#059669");
      mountPlot(`analysis-plot-${turnIndex}-summary-disease`, disease.traces, disease.layout);
      mountPlot(`analysis-plot-${turnIndex}-summary-medication`, medication.traces, medication.layout);
      mountPlot(`analysis-plot-${turnIndex}-summary-period`, period.traces, period.layout);
      mountPlot(`analysis-plot-${turnIndex}-summary-visits`, visits.traces, visits.layout);
    });
  }

  function analysisIntentPresentation(intent) {
    const value = String(intent || "analysis");
    const labels = {
      analysis_deterministic: { label: "Workspace summary", title: "Deterministic workspace summary produced by the app." },
      analysis_compare: { label: "Cohort comparison", title: "Deterministic comparison between the selected cohorts." },
      analysis_transcriptomics_expression: { label: "Transcriptomics expression", title: "Deterministic transcriptomics expression summary across the loaded assays." },
      analysis_transcriptomics_medication_compare: { label: "Transcriptomics by medication", title: "Deterministic transcriptomics comparison aligned to medication-specific datasets." },
      analysis_survival: { label: "Time-to-event analysis", title: "Deterministic Kaplan-Meier time-to-event analysis." },
      analysis_survival_compare: { label: "Time-to-event comparison", title: "Deterministic Kaplan-Meier time-to-event comparison between two cohorts." },
      analysis_trajectory: { label: "Trajectory analysis", title: "Deterministic longitudinal trajectory analysis." },
      analysis_trajectory_compare: { label: "Trajectory comparison", title: "Deterministic trajectory comparison between two cohorts." },
      analysis_llm: { label: "LLM interpretation", title: "LM Studio narrative interpretation grounded in the provided analysis context." },
      analysis_compare_llm: { label: "LLM comparison", title: "LM Studio narrative comparison grounded in the provided cohort context." },
    };
    return labels[value] || {
      label: value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()),
      title: `Internal analysis intent: ${value}`,
    };
  }

  function analysisIconSvg(kind) {
    const icons = {
      summary: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h8"></path><path d="M8 12h8"></path><path d="M8 18h5"></path><rect x="4" y="3" width="16" height="18" rx="2"></rect></svg>',
      disclosure: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 7v5c0 5 3.5 7.8 8 9 4.5-1.2 8-4 8-9V7l-8-4Z"></path><path d="m9.5 12 1.8 1.8 3.2-3.6"></path></svg>',
      provider: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 10V7a4 4 0 1 1 8 0v3"></path><rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M12 14v2"></path></svg>',
      planner: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v6"></path><path d="M9 6h6"></path><path d="M5 13a7 7 0 1 0 14 0"></path><path d="m9 13 2 2 4-4"></path></svg>',
      deterministic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"></path></svg>',
      llm: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9h8"></path><path d="M8 13h5"></path><path d="M6 4h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-4 4v-4H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path></svg>',
      job: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6v6l4 2"></path><circle cx="12" cy="12" r="8"></circle></svg>',
      blocked: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="m8.5 8.5 7 7"></path><path d="m15.5 8.5-7 7"></path></svg>',
      unavailable: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>',
      context: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 10v6"></path><path d="M12 7h.01"></path></svg>',
      plot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"></path><path d="m7 16 4-5 3 3 5-7"></path></svg>',
      followup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="m5 12 7 7 7-7"></path></svg>',
      data: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="6" rx="7" ry="3"></ellipse><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"></path><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"></path></svg>',
    };
    return icons[kind] || icons.summary;
  }

  function renderAnalysisIcon(kind, cls = "analysis-inline-icon") {
    return `<span class="${cls}" aria-hidden="true">${analysisIconSvg(kind)}</span>`;
  }

  function renderAnalysisBadge(label, title, iconKind = "") {
    const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
    return `<span class="query-chip badge analysis-badge"${safeTitle}>${iconKind ? `${renderAnalysisIcon(iconKind, "analysis-badge-icon")}` : ""}<span>${escapeHtml(label)}</span></span>`;
  }

  function formatAnalysisAiProviderGranularity(value) {
    return String(value || "").replace(/_/g, " ");
  }

  function getAnalysisProvenanceChips(payload) {
    const data = payload && payload.data ? payload.data : {};
    const intentInfo = analysisIntentPresentation(payload && payload.intent ? payload.intent : "analysis");
    const plannedByLmStudio = data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio";
    const answeredByLmStudio = data.source === "llm";
    const aiProviderConsulted = plannedByLmStudio || answeredByLmStudio;
    const chips = [renderAnalysisBadge(intentInfo.label, intentInfo.title, "summary")];
    if (data.granularity_applied) {
      chips.push(renderAnalysisBadge(
        `Disclosure: ${data.granularity_applied}`,
        `Applied disclosure mode for this analysis: ${data.granularity_applied}.`,
        "disclosure",
      ));
    }
    if (aiProviderConsulted && data.ai_provider_context_granularity && data.ai_provider_access) {
      let title = "";
      if (data.ai_provider_access === "blocked") {
        title = "AI providers are blocked for this dataset or workspace.";
      } else if (data.ai_provider_access === "safe_summary") {
        title = "AI providers may be used, but they only receive provider-safe structural summary context.";
      } else {
        title = `AI providers may receive up to detailed context and currently receive ${formatAnalysisAiProviderGranularity(data.ai_provider_context_granularity)} context for this analysis.`;
      }
      chips.push(renderAnalysisBadge(
        `AI providers: ${formatAnalysisAiProviderGranularity(data.ai_provider_context_granularity)}`,
        title,
        "provider",
      ));
    }
    if (plannedByLmStudio) {
      chips.push(renderAnalysisBadge("LLM-planned", "LM Studio translated the prompt into a constrained internal analysis plan.", "planner"));
      chips.push(renderAnalysisBadge("Deterministic execution", "The app executed the planned analysis deterministically against local cohort data.", "deterministic"));
      if (data.planner.model) chips.push(renderAnalysisBadge(data.planner.model, "LM Studio model used for analysis planning.", "llm"));
      return chips;
    }
    let resultLabel = "Deterministic";
    let resultTitle = "The app executed this analysis deterministically.";
    if (data.execution === "queued") {
      resultLabel = "Queued job";
      resultTitle = "This curated analysis was submitted as a background job instead of running inline.";
    } else if (answeredByLmStudio) {
      resultLabel = "LLM answer";
      resultTitle = "LM Studio generated the narrative interpretation from the provided analysis context.";
    } else if (data.source === "policy") {
      resultLabel = "AI blocked";
      resultTitle = "This Analysis prompt requires an AI provider, but provider access is blocked by workspace policy.";
    } else if (data.source === "provider_unavailable") {
      resultLabel = "AI unavailable";
      resultTitle = "This Analysis prompt requires an AI provider, but no provider reply was available.";
    }
    const resultIcon = data.execution === "queued"
      ? "job"
      : answeredByLmStudio
      ? "llm"
      : data.source === "policy"
        ? "blocked"
        : data.source === "provider_unavailable"
          ? "unavailable"
          : "deterministic";
    chips.push(renderAnalysisBadge(resultLabel, resultTitle, resultIcon));
    if (answeredByLmStudio && data.model) chips.push(renderAnalysisBadge(data.model, "LM Studio model used for this analysis reply.", "llm"));
    return chips;
  }

  function renderAnalysisMeta(payload) {
    if (!analysisMetaEl) return;
    analysisMetaEl.innerHTML = getAnalysisProvenanceChips(payload).join("");
  }

  function formatAnalysisScopeLabel(scopeValue) {
    const ids = String(scopeValue || "").split(",").map((item) => item.trim()).filter(Boolean);
    if (!ids.length) return "Full workspace";
    const usesSampleIds = ids.some((item) => item.includes(":"));
    const preview = ids.slice(0, 6).join(", ");
    const suffix = ids.length > 6 ? ` ... (+${ids.length - 6} more)` : "";
    return `${ids.length} ${usesSampleIds ? "sample IDs" : "patient IDs"}: ${preview}${suffix}`;
  }

  function renderAnalysisCompareMode() {
    if (!analysisCompareModeEl || !refs.analysisCompareFieldEl) return;
    refs.analysisCompareFieldEl.style.display = analysisCompareModeEl.checked ? "" : "none";
    renderAnalysisScopeSummary();
    renderAnalysisCompareScopeSummary();
    callbacks.renderGlobalContext();
  }

  function resolveAnalysisScopeIds(side) {
    const savedCohortId = side === "b" ? state.analysisCompareSavedCohortId : state.analysisSelectedSavedCohortId;
    const inputEl = side === "b" ? analysisCompareSelectedPatientIdsEl : analysisSelectedPatientIdsEl;
    const selectedCohort = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === savedCohortId)
      : null;
    if (selectedCohort) {
      const sampleIds = Array.isArray(selectedCohort.sample_ids) ? selectedCohort.sample_ids.map((item) => String(item).trim()).filter(Boolean) : [];
      if (sampleIds.length) return sampleIds;
      if (Array.isArray(selectedCohort.patient_ids)) {
        return selectedCohort.patient_ids.map((item) => String(item).trim()).filter(Boolean);
      }
    }
    return String(inputEl && inputEl.value ? inputEl.value : "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function overlappingAnalysisScopeIds(scopeAIds, scopeBIds) {
    const left = Array.isArray(scopeAIds) ? scopeAIds.map((item) => String(item).trim()).filter(Boolean) : [];
    const rightSet = new Set((Array.isArray(scopeBIds) ? scopeBIds : []).map((item) => String(item).trim()).filter(Boolean));
    return Array.from(new Set(left.filter((item) => rightSet.has(item))));
  }

  function analysisPromptRequestsPlots(prompt) {
    const lowered = String(prompt || "").toLowerCase();
    return ["trajectory", "response to", "kaplan", "survival", "plot", "plots", "chart", "charts", "graph", "graphs", "visualize", "visualise", "distribution", "distributions", "histogram", "bar plot", "line plot", "trend", "trends", "over time"].some((token) => lowered.includes(token));
  }

  function setAnalysisComposerStatus(message, kind = "") {
    if (!analysisComposerStatusEl) return;
    const normalized = String(message || "").trim();
    analysisComposerStatusEl.textContent = normalized;
    analysisComposerStatusEl.className = `query-status${kind ? ` ${kind}` : ""}${normalized ? "" : " is-hidden"}`;
  }

  function setAnalysisBlockedStatus(message) {
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = message;
    setAnalysisComposerStatus(message, "error");
  }

  function renderAnalysisBlockedTurn(prompt, currentScope, compareScope, message) {
    state.analysisTurns.push({ role: "user", prompt, scope: currentScope || "", compareScope: compareScope || "" });
    state.analysisTurns.push({
      role: "assistant",
      payload: {
        intent: "analysis_error",
        reply: message,
        data: { source: "error", provider: "lm_status" },
      },
    });
    renderAnalysisThread();
    syncCurrentAnalysisSessionFromUi({ render: true });
    scrollAnalysisTurnIntoView(state.analysisTurns.length - 1);
  }

  function analysisPayloadHasPlots(payload) {
    const context = payload && payload.data ? payload.data.context : null;
    const mode = context && typeof context.mode === "string" ? context.mode : "";
    return [
      "external_rscript_transcriptomics_deseq2_differential_expression",
      "external_rscript_transcriptomics_hallmark_pathway_enrichment",
      "workflow_transcriptomics_signature",
      "transcriptomics_medication_compare",
      "trajectory",
      "trajectory_response",
      "trajectory_compare",
      "trajectory_compare_response",
      "survival",
      "survival_compare",
    ].includes(mode);
  }

  function uniquePrompts(items) {
    const seen = new Set();
    return (Array.isArray(items) ? items : []).filter((item) => {
      const value = String(item || "").trim();
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  function renderAnalysisFollowUps(prompts) {
    const followUps = uniquePrompts(prompts).slice(0, 4);
    if (!followUps.length) return "";
    return `<div class="query-followups" style="margin-top:12px;"><div class="query-followups-label analysis-section-label">${renderAnalysisIcon("followup")}<span>Suggested follow-up queries</span></div><div class="query-followups-list">${followUps.map((item) => `<button type="button" class="query-chip" data-analysis-followup-prompt="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("")}</div></div>`;
  }

  function getAnalysisFollowUpPrompts(payload, showPlots) {
    const context = payload && payload.data ? payload.data.context : null;
    const mode = context && typeof context.mode === "string" ? context.mode : "";
    const hasPlots = Boolean(showPlots || analysisPayloadHasPlots(payload));
    const measure = String(context && context.measure ? context.measure : "").trim();
    const treatment = String(context && context.treatment ? context.treatment : "").trim();
    const eventLabel = formatTimeToEventLabel(context);
    const trajectorySubject = treatment ? `response to ${treatment}` : measure ? `${measure} trajectory` : "trajectory";
    const comparisonLabel = measure ? `${measure} comparison` : "comparison";
    const transcriptomicsComparison = Array.isArray(context && context.comparisons) && context.comparisons.length
      ? context.comparisons[0]
      : null;
    const medicationComparisonLabel = transcriptomicsComparison
      ? `${String(transcriptomicsComparison.medication_a || "Group A").trim()} vs ${String(transcriptomicsComparison.medication_b || "Group B").trim()}`
      : "this transcriptomics comparison";
    if (!context && !hasPlots) return [];
    if (mode === "survival" || mode === "survival_compare") {
      return [
        `Can you explain this Kaplan-Meier plot for ${eventLabel}?`,
        mode === "survival_compare" ? `Which cohort appears to do better for ${eventLabel}, and why?` : `What does this Kaplan-Meier result suggest about ${eventLabel}?`,
        "How many events drove this separation?",
        `What are the main limitations of this Kaplan-Meier analysis for ${eventLabel}?`,
      ];
    }
    if (mode === "trajectory" || mode === "trajectory_response" || mode === "trajectory_compare" || mode === "trajectory_compare_response") {
      return [
        `Can you explain this ${trajectorySubject} plot?`,
        mode.includes("compare") ? `Which cohort changes faster in the ${trajectorySubject}?` : `What is the main pattern in this ${trajectorySubject}?`,
        mode.includes("compare") ? `Is the difference in ${trajectorySubject} clinically meaningful?` : `Is this ${trajectorySubject} clinically meaningful?`,
        "What should I look at next?",
      ];
    }
    if (mode === "transcriptomics_medication_compare") {
      return [
        `Can you explain the volcano plot for ${medicationComparisonLabel}?`,
        `Which genes drive the main separation in ${medicationComparisonLabel}?`,
        `Is ${medicationComparisonLabel} exploratory or confirmatory?`,
        `What should I validate next for ${medicationComparisonLabel}?`,
      ];
    }
    if (mode === "compare") {
      return [
        `Can you explain this ${comparisonLabel} in simpler terms?`,
        "What is the main difference between Cohort A and Cohort B?",
        `What are the main limitations of this ${comparisonLabel}?`,
        "What should I look at next?",
      ];
    }
    if (hasPlots) {
      return [
        "Can you explain this plot?",
        "What is the main takeaway?",
        "What are the main limitations of this analysis?",
        "What should I look at next?",
      ];
    }
    return [];
  }

  function renderAnalysisThread() {
    renderAnalysisStarterPrompts();
    if (!state.analysisTurns.length) {
      analysisThreadEl.innerHTML = '<div class="empty">Run an analysis prompt to start a threaded analysis workspace.</div>';
      return;
    }
    const latestAssistantIndex = (() => {
      for (let index = state.analysisTurns.length - 1; index >= 0; index -= 1) {
        const turn = state.analysisTurns[index];
        if (turn && turn.role === "assistant" && !turn.pending && turn.payload) {
          return index;
        }
      }
      return -1;
    })();
    analysisThreadEl.innerHTML = state.analysisTurns.map((turn, turnIndex) => {
      if (turn.role === "user") {
        const compareHtml = turn.compareScope ? `<div class="analysis-turn-scope"><strong>Cohort B:</strong> ${escapeHtml(formatAnalysisScopeLabel(turn.compareScope || ""))}</div>` : "";
        return `<article class="analysis-turn analysis-turn-user" data-analysis-turn-index="${turnIndex}"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${escapeHtml(turn.prompt)}</p><div class="analysis-turn-scope"><strong>${turn.compareScope ? "Cohort A" : "Scope"}:</strong> ${escapeHtml(formatAnalysisScopeLabel(turn.scope || ""))}</div>${compareHtml}</div></article>`;
      }
      if (turn.pending) {
        return `<article class="analysis-turn analysis-turn-pending" data-analysis-turn-index="${turnIndex}"><div class="analysis-turn-label">Analysis</div><div class="analysis-turn-meta"><span class="query-chip badge">pending</span><span class="query-chip badge">${escapeHtml(turn.pendingLabel || "Preparing response")}</span></div><div class="analysis-turn-body"><div class="analysis-pending-row"><div class="analysis-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></div><span>${escapeHtml(turn.pendingDetail || "Building cohort context and waiting for the model reply.")}</span></div></div></article>`;
      }
      const context = turn.payload && turn.payload.data ? turn.payload.data.context : null;
      const notable = context && Array.isArray(context.notable_findings) ? context.notable_findings : [];
      const source = context && typeof context.source === "string" && context.source.trim() ? context.source : "";
      const contextParts = [];
      if (source) contextParts.push(source);
      if (context && context.mode === "transcriptomics_expression") {
        const datasetCount = Array.isArray(context.datasets) ? context.datasets.length : 0;
        if (datasetCount) contextParts.push(`${datasetCount} assay${datasetCount === 1 ? "" : "s"}`);
        if (context.gene_id) contextParts.push(`gene ${context.gene_id}`);
      }
      if (context && (context.mode === "survival" || context.mode === "survival_compare")) {
        contextParts.push(`event: ${formatTimeToEventLabel(context)}`);
      }
      if (notable.length) contextParts.push(...notable);
      const isErrorTurn = String(turn.payload && turn.payload.intent ? turn.payload.intent : "").trim() === "analysis_error"
        || String(turn.payload && turn.payload.data && turn.payload.data.source ? turn.payload.data.source : "").trim() === "error";
      const followUpsHtml = renderAnalysisFollowUps(getAnalysisFollowUpPrompts(turn.payload, turn.showPlots));
      const turnClass = isErrorTurn ? "analysis-turn analysis-turn-error" : "analysis-turn analysis-turn-assistant";
      const turnLabel = isErrorTurn ? "Analysis Error" : "Analysis";
      const contextHtml = contextParts.length
        ? `<div class="analysis-turn-context"><p>${escapeHtml(contextParts.join(" | "))}</p></div>`
        : "";
      const visualHtml = turn.showPlots
        ? `<div class="analysis-result-visuals"><div class="analysis-plot-grid">${renderAnalysisPlotsMarkup(turn.payload, turnIndex)}</div></div>`
        : "";
      const followupHtml = followUpsHtml
        ? `<div class="analysis-result-followups">${followUpsHtml}</div>`
        : "";
      const dataHtml = `<details class="query-section analysis-result-data"><summary><span class="analysis-section-label">${renderAnalysisIcon("data")}<span>Show analysis data</span></span></summary><pre>${escapeHtml(JSON.stringify(turn.payload.data, null, 2))}</pre></details>`;
      const resultHtml = `<div class="analysis-result-content"><div class="analysis-turn-body">${renderQueryReply(turn.payload)}</div>${visualHtml}${contextHtml}${followupHtml}${dataHtml}</div>`;
      const intentInfo = analysisIntentPresentation(turn.payload && turn.payload.intent ? turn.payload.intent : "analysis");
      const summaryText = contextParts.length ? contextParts.slice(0, 2).join(" | ") : String(turn.payload && turn.payload.reply ? turn.payload.reply : "").replace(/\s+/g, " ").slice(0, 140);
      const compactResultHtml = turnIndex === latestAssistantIndex
        ? resultHtml
        : `<details class="analysis-result-collapsible"><summary><span class="analysis-result-collapsible-title">${escapeHtml(intentInfo.label)}</span><span class="analysis-result-collapsible-note">${escapeHtml(summaryText || "Open result")}</span></summary>${resultHtml}</details>`;
      return `<article class="${turnClass}${turnIndex === latestAssistantIndex ? " is-latest-result" : " is-previous-result"}" data-analysis-turn-index="${turnIndex}"><div class="analysis-turn-label">${turnLabel}</div><div class="analysis-turn-meta">${getAnalysisProvenanceChips(turn.payload).join("")}</div>${compactResultHtml}</article>`;
    }).join("");
    mountAnalysisPlots();
  }

  function scrollAnalysisTurnIntoView(turnIndex) {
    if (!analysisThreadEl) return;
    const index = Number(turnIndex);
    const target = Number.isInteger(index)
      ? analysisThreadEl.querySelector(`[data-analysis-turn-index="${index}"]`)
      : analysisThreadEl.lastElementChild;
    if (!target || typeof target.scrollIntoView !== "function") return;
    window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function runAnalysis() {
    if (state.analysisInFlight) return;
    const prompt = analysisPromptEl.value.trim();
    if (!prompt) {
      setAnalysisBlockedStatus("Enter an analysis prompt first.");
      return;
    }
    const currentScopeIds = resolveAnalysisScopeIds("a");
    const compareScopeIds = analysisCompareModeEl && analysisCompareModeEl.checked ? resolveAnalysisScopeIds("b") : [];
    const currentScope = currentScopeIds.join(",");
    const compareScope = compareScopeIds.join(",");
    const llmOnly = state.analysisExecutionMode === "llm_only";
    const plannerOnly = state.analysisExecutionMode === "planner_only";
    const deterministicOnly = state.analysisExecutionMode === "deterministic";
    const showPlots = analysisPromptRequestsPlots(prompt);
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    const selectedAssayDatasets = Array.isArray(state.selectedAssayDatasets) ? state.selectedAssayDatasets : [];
    if ((llmOnly || plannerOnly) && (!state.lmStatus || state.lmStatus.available !== true)) {
      const message = plannerOnly
        ? "LLM planner unavailable. Start an LLM model or choose a deterministic analysis."
        : "LLM unavailable. Start an LLM model or choose a deterministic analysis.";
      setAnalysisBlockedStatus(message);
      renderAnalysisBlockedTurn(prompt, currentScope, compareScope, message);
      return;
    }
    if (compareMode && (!state.analysisSelectedSavedCohortId || !state.analysisCompareSavedCohortId)) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis cohort comparison requires saved Cohort A and Cohort B.";
      state.analysisExecutionMode = "auto";
      return;
    }
    if (compareMode) {
      const overlappingIds = overlappingAnalysisScopeIds(currentScopeIds, compareScopeIds);
      if (overlappingIds.length) {
        const preview = overlappingIds.slice(0, 6).join(", ");
        const suffix = overlappingIds.length > 6 ? ` (+${overlappingIds.length - 6} more)` : "";
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = `Cohort A and Cohort B must be disjoint. Remove the overlapping IDs: ${preview}${suffix}.`;
        state.analysisExecutionMode = "auto";
        return;
      }
    }
    if (requiresSingleSelectedAssayDataset(state.analysisSelectedCatalogItemId) && selectedAssayDatasets.length !== 1) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = selectedAssayDatasets.length
        ? "This assay tool requires exactly one selected assay."
        : "Select one assay before running this assay tool.";
      state.analysisExecutionMode = "auto";
      return;
    }
    if (compareMode && requiresSingleSelectedAssayDataset(state.analysisSelectedCatalogItemId) && selectedAssayDatasets.length === 1 && typeof assayDatasetOverlap === "function") {
      const overlap = assayDatasetOverlap(selectedAssayDatasets[0]);
      if (overlap && (overlap.overlapA < 1 || overlap.overlapB < 1)) {
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = `Selected assay "${selectedAssayDatasets[0]}" overlaps Cohort A by ${overlap.overlapA} and Cohort B by ${overlap.overlapB}. Choose an assay with at least one sample in both cohorts.`;
        state.analysisExecutionMode = "auto";
        return;
      }
    }
    state.analysisInFlight = true;
    analysisRunBtnEl.disabled = true;
    if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = "Running analysis...";
    setAnalysisComposerStatus("Running analysis. Results will appear below.");
    if (analysisMetaEl) analysisMetaEl.innerHTML = "";
    state.analysisExamplesPinnedOpen = false;
    state.analysisTurns.push({ role: "user", prompt, scope: currentScope, compareScope });
    state.analysisTurns.push({ role: "assistant", pending: true, pendingLabel: "Preparing response", pendingDetail: "Building cohort context and waiting for the model reply." });
    renderAnalysisThread();
    scrollAnalysisTurnIntoView(state.analysisTurns.length - 1);
    syncCurrentAnalysisSessionFromUi({ render: true });
    startAnalysisProgressUpdates(compareMode, showPlots);
    try {
      const response = await fetch("/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          catalog_item_id: state.analysisSelectedCatalogItemId || "",
          analysis_session_id: state.currentAnalysisSessionId || "",
          assay_id: selectedAssayDatasets.length === 1 ? selectedAssayDatasets[0] : "",
          dataset_id: analysisWorkspaceKey(),
          selected_patient_ids: currentScope,
          scope_metadata: state.analysisScopeMetadata && typeof state.analysisScopeMetadata === "object" ? state.analysisScopeMetadata : {},
          compare_mode: compareMode,
          compare_selected_patient_ids: compareScope,
          compare_scope_metadata: state.analysisCompareScopeMetadata && typeof state.analysisCompareScopeMetadata === "object" ? state.analysisCompareScopeMetadata : {},
          llm_only: llmOnly,
          deterministic_only: deterministicOnly,
          history: state.analysisHistory.slice(-6),
        }),
      });
      if (!response.ok) {
        let message = "Analysis failed.";
        const raw = await response.text();
        try {
          const parsed = JSON.parse(raw);
          message = parsed.detail || parsed.message || message;
        } catch (_error) {
          message = raw || message;
        }
        throw new Error(message);
      }
      const payload = await response.json();
      const finalShowPlots = showPlots || analysisPayloadHasPlots(payload);
      stopAnalysisProgressUpdates();
      renderAnalysisMeta(payload);
      state.analysisTurns[state.analysisTurns.length - 1] = { role: "assistant", payload, showPlots: finalShowPlots };
      renderAnalysisThread();
      if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
      syncCurrentAnalysisSessionFromUi({ render: true });
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = payload && payload.data && payload.data.execution === "queued"
        ? "Analysis job submitted."
        : "Analysis complete.";
      setAnalysisComposerStatus(analysisStatusEl.textContent);
      scrollAnalysisTurnIntoView(state.analysisTurns.length - 1);
      state.analysisHistory.push({ role: "user", content: prompt });
      state.analysisHistory.push({ role: "assistant", content: payload.reply || "" });
      state.analysisHistory = state.analysisHistory.slice(-8);
      state.analysisExecutionMode = "auto";
      syncCurrentAnalysisSessionFromUi({ render: true });
      if (payload && payload.data && payload.data.execution === "queued" && typeof handleAnalysisJobSubmission === "function") {
        handleAnalysisJobSubmission(payload);
      }
    } catch (error) {
      state.analysisTurns[state.analysisTurns.length - 1] = {
        role: "assistant",
        payload: {
          intent: "analysis_error",
          reply: error && error.message ? error.message : "Analysis failed.",
          data: { source: "error", context: null },
        },
        showPlots: false,
      };
      stopAnalysisProgressUpdates();
      renderAnalysisThread();
      if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
      syncCurrentAnalysisSessionFromUi({ render: true });
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis failed.";
      setAnalysisComposerStatus(error && error.message ? error.message : "Analysis failed.", "error");
      state.analysisExecutionMode = "auto";
    } finally {
      stopAnalysisProgressUpdates();
      state.analysisInFlight = false;
      analysisRunBtnEl.disabled = false;
      if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
    }
  }

  return {
    renderAnalysisMeta,
    renderAnalysisCompareMode,
    analysisPromptRequestsPlots,
    analysisPayloadHasPlots,
    renderAnalysisThread,
    scrollAnalysisTurnIntoView,
    handleAnalysisPlotViewClick(event) {
      const button = event.target.closest("[data-de-view-btn]");
      const heatmapButton = !button ? event.target.closest("[data-de-heatmap-view-btn]") : null;
      const pathwayButton = !button && !heatmapButton ? event.target.closest("[data-pathway-view-btn]") : null;
      const targetButton = button || heatmapButton || pathwayButton;
      if (!targetButton || !analysisThreadEl.contains(targetButton) || targetButton.disabled) return;
      const turnIndex = String(targetButton.dataset.turnIndex || "").trim();
      if (!turnIndex) return;
      if (button) {
        const view = String(button.dataset.deViewBtn || "").trim();
        if (!view) return;
        const allButtons = analysisThreadEl.querySelectorAll(`[data-de-view-btn][data-turn-index="${turnIndex}"]`);
        const allPanels = analysisThreadEl.querySelectorAll(`[data-de-view-panel][data-turn-index="${turnIndex}"]`);
        allButtons.forEach((item) => {
          const active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-selected", active ? "true" : "false");
        });
        allPanels.forEach((panel) => {
          panel.classList.toggle("is-active", String(panel.dataset.deViewPanel || "") === view);
        });
        if (view !== "interactive") return;
        const index = Number(turnIndex);
        const turn = Number.isInteger(index) ? state.analysisTurns[index] : null;
        if (turn && turn.payload) {
          void mountDifferentialExpressionInteractivePlot(index, turn.payload);
        }
        return;
      }
      const view = String(heatmapButton.dataset.deHeatmapViewBtn || "").trim();
      if (!view) return;
      const allButtons = analysisThreadEl.querySelectorAll(`[data-de-heatmap-view-btn][data-turn-index="${turnIndex}"]`);
      const allPanels = analysisThreadEl.querySelectorAll(`[data-de-heatmap-view-panel][data-turn-index="${turnIndex}"]`);
      allButtons.forEach((item) => {
        const active = item === heatmapButton;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      allPanels.forEach((panel) => {
        panel.classList.toggle("is-active", String(panel.dataset.deHeatmapViewPanel || "") === view);
      });
      if (view === "interactive") {
        const index = Number(turnIndex);
        const turn = Number.isInteger(index) ? state.analysisTurns[index] : null;
        if (turn && turn.payload) {
          void mountDifferentialExpressionInteractiveHeatmap(index, turn.payload);
        }
      }
      if (!pathwayButton) {
        return;
      }
      const pathwayView = String(pathwayButton.dataset.pathwayViewBtn || "").trim();
      if (!pathwayView) return;
      const allPathwayButtons = analysisThreadEl.querySelectorAll(`[data-pathway-view-btn][data-turn-index="${turnIndex}"]`);
      const allPathwayPanels = analysisThreadEl.querySelectorAll(`[data-pathway-view-panel][data-turn-index="${turnIndex}"]`);
      allPathwayButtons.forEach((item) => {
        const active = item === pathwayButton;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      allPathwayPanels.forEach((panel) => {
        panel.classList.toggle("is-active", String(panel.dataset.pathwayViewPanel || "") === pathwayView);
      });
      if (pathwayView === "interactive") {
        const index = Number(turnIndex);
        const turn = Number.isInteger(index) ? state.analysisTurns[index] : null;
        if (turn && turn.payload) {
          void mountHallmarkInteractivePlot(index, turn.payload);
        }
      }
    },
    handleAnalysisFollowUpsClick(event) {
      const button = event.target.closest("[data-analysis-followup-prompt]");
      if (!button || !analysisThreadEl.contains(button)) return;
      analysisPromptEl.value = button.dataset.analysisFollowupPrompt || "";
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis follow-up prompt prepared. Press Enter or click Run analysis.";
      analysisPromptEl.focus();
    },
    handleAnalysisResultBoardClick(event) {
      const summary = event.target.closest(".analysis-result-collapsible > summary");
      if (!summary || !analysisThreadEl.contains(summary)) return;
      window.setTimeout(() => {
        mountAnalysisPlots();
      }, 0);
    },
    runAnalysis,
  };
}
