import {createAnalysisCharts} from './charts/analysis.js';
import {createAnalysisThreadView,createProvenanceView} from './react/ui.js';
import { parseAnalysisTsv } from "./analysis_tsv.js";
import { decodeIdentity, displayIdentity } from './identities.js';

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
    analysisContextWorkspaceBtnEl,
    analysisContextGeneralBtnEl,
    analysisComposerEl,
    analysisComposerTitleEl,
    analysisRunBtnLabelEl,
    analysisShellEl,
  } = refs;
  const { escapeHtml, queryReplyModel } = helpers;
  const metaView = createProvenanceView(analysisMetaEl,true);
  const threadView = createAnalysisThreadView(analysisThreadEl);
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
    renderAnalysisCatalogAssayPanel,
    prepareScriptForRun,
  } = callbacks;

  const ANALYSIS_PLOT_COLORS = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed", "#dc2626", "#d97706"];

  // Reuse the same editor and run button: no duplicated draft or event handlers.
  const {mountDifferentialExpressionInteractivePlot, mountDifferentialExpressionInteractiveHeatmap, mountHallmarkInteractivePlot, mountAnalysisPlots} = createAnalysisCharts({ANALYSIS_PLOT_COLORS, escapeHtml, parseAnalysisTsv, rankedQuantitativeAssayResults, finiteAnalysisNumber, state, isQuantitativeAssayWilcoxonContextMode, isDifferentialExpressionContextMode, isPathwayEnrichmentContextMode});
  function placeAnalysisRequest(afterThread) {
    const composer = document.getElementById("analysisRequestComposer");
    const host = document.getElementById(afterThread ? "analysisContinueHost" : "analysisRequestHome");
    if (composer && host && composer.parentElement !== host) host.append(composer);
    if (afterThread) document.getElementById("analysisRequestDetails").open = true;
    if (analysisPromptEl) analysisPromptEl.placeholder = afterThread
      ? "Ask a follow-up…"
      : isGeneralQuestionMode() ? "Ask a general question without workspace context"
      : "Describe the analysis to run against the current workspace";
  }

  function openAnalysisSetup() {
    placeAnalysisRequest(false);
    const setup = document.getElementById("analysisSetupDisclosure");
    if (setup) setup.open = true;
  }

  function editSetup() {
    openAnalysisSetup();
    document.getElementById("analysisSetupDisclosure").scrollIntoView({ behavior: "smooth", block: "start" });
    document.getElementById("analysisMethodSelect").focus({ preventScroll: true });
  }
  document.getElementById("analysisSetupDisclosure")?.addEventListener("toggle", (event) => {
    if (event.currentTarget.open) placeAnalysisRequest(false);
    else if (state.analysisTurns.length) placeAnalysisRequest(true);
  });


  function isGeneralQuestionMode() {
    return state.analysisContextMode === "general";
  }

  function historyForContext(mode) {
    return (Array.isArray(state.analysisHistory) ? state.analysisHistory : [])
      .filter((turn) => mode === "general" ? turn.context_mode === "general" : turn.context_mode !== "general")
      .slice(-6)
      .map((turn) => ({ role: turn.role, content: turn.content }));
  }

  function renderAnalysisContextMode() {
    const general = isGeneralQuestionMode();
    document.getElementById("analysisMeasurementComparison").hidden = general;
    [[analysisContextWorkspaceBtnEl, !general], [analysisContextGeneralBtnEl, general]].forEach(([button, active]) => {
      if (!button) return;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (analysisShellEl) analysisShellEl.classList.toggle("analysis-general-mode", general);
    if (analysisComposerEl) analysisComposerEl.classList.toggle("is-general-mode", general);
    if (analysisComposerTitleEl) analysisComposerTitleEl.textContent = general ? "Ask Model" : "Run Analysis";
    if (analysisRunBtnLabelEl) analysisRunBtnLabelEl.textContent = general ? "Ask" : "Run analysis";
    if (analysisPromptEl) {
      analysisPromptEl.placeholder = analysisPromptEl.closest("#analysisContinueHost") ? "Ask a follow-up…" : general
        ? "Ask a general question without workspace context"
        : "Describe the analysis to run against the current workspace";
    }
    if (general && analysisRunBtnEl && !state.analysisInFlight) {
      analysisRunBtnEl.disabled = false;
    }
    if (!general && typeof renderAnalysisCatalogAssayPanel === "function") {
      renderAnalysisCatalogAssayPanel();
    }
    if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
  }

  function setAnalysisContextMode(value) {
    state.analysisContextMode = value === "general" ? "general" : "workspace";
    if (isGeneralQuestionMode()) state.analysisExecutionMode = "auto";
    renderAnalysisContextMode();
    if (analysisStatusEl) {
      analysisStatusEl.className = "analysis-workspace-status";
      analysisStatusEl.textContent = isGeneralQuestionMode()
        ? "General question selected. No workspace context will be sent."
        : "Workspace analysis selected.";
    }
    syncCurrentAnalysisSessionFromUi({ render: true });
    analysisPromptEl && analysisPromptEl.focus();
  }

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
      || normalized === "transcriptomics-limma-voom-differential-expression"
      || normalized === "transcriptomics-hallmark-pathway-enrichment"
      || normalized === "transcriptomics-signature-workflow"
      || normalized === "methylation-qc-pca"
      || normalized === "methylation-limma-differential-methylation"
      || normalized === "flow-cytometry-wilcoxon-cohort-comparison"
      || normalized === "serology-wilcoxon-cohort-comparison";
  }

  function isDifferentialExpressionContextMode(mode) {
    const normalized = String(mode || "").trim();
    return normalized === "external_rscript_transcriptomics_deseq2_differential_expression"
      || normalized === "external_rscript_transcriptomics_limma_voom_differential_expression";
  }

  function isPathwayEnrichmentContextMode(mode) {
    return String(mode || "").trim() === "external_rscript_transcriptomics_hallmark_pathway_enrichment";
  }

  function isMethylationQcContextMode(mode) {
    return String(mode || "").trim() === "external_rscript_methylation_qc_pca";
  }

  function isDifferentialMethylationContextMode(mode) {
    return String(mode || "").trim() === "external_rscript_methylation_limma_differential_methylation";
  }

  function isQuantitativeAssayWilcoxonContextMode(mode) {
    return String(mode || "").trim() === "external_rscript_quantitative_assay_wilcoxon_comparison";
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

  function formatAnalysisCount(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.round(number).toLocaleString("en-US") : "n/a";
  }

  function formatAnalysisPercent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "n/a";
  }

  function formatAnalysisPValue(value) {
    if (value === null || value === undefined || value === "") return "n/a";
    const number = Number(value);
    if (!Number.isFinite(number)) return "n/a";
    if (number === 0) return "< 1e-300";
    return number < 0.001 ? number.toExponential(2) : number.toPrecision(3);
  }

  function formatAnalysisNumber(value, digits = 3) {
    if (value === null || value === undefined || value === "") return "n/a";
    const number = Number(value);
    if (!Number.isFinite(number)) return "n/a";
    return number.toLocaleString("en-US", {
      maximumFractionDigits: digits,
      minimumFractionDigits: 0,
    });
  }

  function finiteAnalysisNumber(value) {
    if (value === null || value === undefined || value === "") return Number.NaN;
    const number = Number(value);
    return Number.isFinite(number) ? number : Number.NaN;
  }

  function rankedQuantitativeAssayResults(results) {
    return (Array.isArray(results) ? results : [])
      .filter((item) => (
        item
        && String(item.feature_id || "").trim()
        && String(item.status || "").trim().toLowerCase() === "tested"
      ))
      .slice()
      .sort((left, right) => {
        const leftAdjusted = finiteAnalysisNumber(left.adj_p_value);
        const rightAdjusted = finiteAnalysisNumber(right.adj_p_value);
        const leftRank = Number.isFinite(leftAdjusted) ? leftAdjusted : Number.POSITIVE_INFINITY;
        const rightRank = Number.isFinite(rightAdjusted) ? rightAdjusted : Number.POSITIVE_INFINITY;
        if (leftRank !== rightRank) return leftRank - rightRank;
        const leftRaw = finiteAnalysisNumber(left.p_value);
        const rightRaw = finiteAnalysisNumber(right.p_value);
        const leftRawRank = Number.isFinite(leftRaw) ? leftRaw : Number.POSITIVE_INFINITY;
        const rightRawRank = Number.isFinite(rightRaw) ? rightRaw : Number.POSITIVE_INFINITY;
        if (leftRawRank !== rightRawRank) return leftRawRank - rightRawRank;
        const leftEffect = finiteAnalysisNumber(left.rank_biserial_effect);
        const rightEffect = finiteAnalysisNumber(right.rank_biserial_effect);
        return (Number.isFinite(rightEffect) ? Math.abs(rightEffect) : -1)
          - (Number.isFinite(leftEffect) ? Math.abs(leftEffect) : -1);
      });
  }

  function methylationPanelModel(context) {
    const panel = context && context.feature_panel && typeof context.feature_panel === "object"
      ? context.feature_panel
      : null;
    if (!panel || String(context.feature_view || "") !== "feature_panel") return "";
    const label = String(panel.label || panel.panel_id || "Methylation feature panel").trim();
    const version = String(panel.panel_version || "").trim();
    const independent = panel.independent_of_target_cohort
      ? " Feature selection was independent of this target cohort."
      : "";
    const source = String(panel.source_publication_doi || "").trim();
    const note = `${label}${version ? ` v${version}` : ""}.${source ? ` Source DOI: ${source}.` : ""}${independent}`;
    return {note, metrics:[
      {label:"Panel requested",value:formatAnalysisCount(panel.requested_feature_count)},
      {label:"Absent from source",value:formatAnalysisCount(panel.missing_feature_count)},
      {label:"Non-finite excluded",value:formatAnalysisCount(panel.excluded_nonfinite_feature_count)},
      {label:"Panel retained",value:formatAnalysisCount(panel.matched_feature_count)}]};
  }

  function resultFiles(_title, artifacts) {
    return artifacts.filter(item => item && String(item.name || "").trim() && String(item.url || "").trim());
  }

  function analysisVisuals(payload, turnIndex) {
    const context = payload?.data?.context;
    const modes = ["custom_script", "cross_modal_association", "trajectory_compare",
      "trajectory_compare_response", "trajectory", "trajectory_response", "survival",
      "survival_compare", "transcriptomics_medication_compare"];
    if (!context || modes.includes(context.mode)) return {
      context, turnIndex, artifacts: payload?.data?.artifacts || [],
      eventLabel: context ? formatTimeToEventLabel(context) : "",
    };
    return {context, turnIndex, scientific: analysisScientificModel(payload)};
  }

  function analysisScientificModel(payload) {
    const data = payload && payload.data ? payload.data : null;
    const context = data && data.context ? data.context : null;
    const artifacts = Array.isArray(data && data.artifacts) ? data.artifacts : [];
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
      const downloads = resultFiles("Result files", [
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
      return {kind:"workflow", context, downloads, deSummaryItems, pathwaySummaryItems,
        positiveText, negativeText, dePlotArtifact, deHeatmapArtifact, deHeatmapTableArtifact,
        deHeatmapClusteringArtifact, deVolcanoArtifact, pathwayPlotArtifact, pathwayResultsArtifact};
    }
    if (isMethylationQcContextMode(context.mode)) {
      const findArtifact = (name) => artifacts.find((item) => {
        const artifactName = String(item && item.name ? item.name : "");
        return artifactName === name || artifactName.endsWith(`/${name}`);
      });
      const plotArtifact = findArtifact("pca_plot.png");
      const sampleQcArtifact = findArtifact("sample_qc.tsv");
      const scoresArtifact = findArtifact("pca_scores.tsv");
      const varianceArtifact = findArtifact("pca_variance.tsv");
      const associationsArtifact = findArtifact("pca_covariate_associations.tsv");
      const summaryArtifact = findArtifact("summary.json");
      const manifestArtifact = findArtifact("manifest.yaml");
      const paramsArtifact = findArtifact("params.yaml");
      const downloads = resultFiles("Result files", [
        plotArtifact,
        sampleQcArtifact,
        scoresArtifact,
        varianceArtifact,
        associationsArtifact,
        summaryArtifact,
        manifestArtifact,
        paramsArtifact,
      ]);
      const covariates = Array.isArray(context.covariates_used)
        ? context.covariates_used.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const covariateText = covariates.length
        ? `Covariates assessed against the leading components: ${covariates.join(", ")}.`
        : "No varying declared covariates were available for PCA association checks in this scope.";
      const strongestCovariate = String(context.strongest_covariate || "").trim();
      const strongestAdjustedP = context.strongest_covariate_adj_p_value;
      const strongestAssociation = strongestCovariate
        ? ` Strongest exploratory association: ${strongestCovariate} with ${String(context.strongest_covariate_component || "a leading component")} (BH-adjusted p = ${formatAnalysisPValue(strongestAdjustedP)}; raw p = ${formatAnalysisPValue(context.strongest_covariate_p_value)}).`
        : "";
      const pcaDetails = `${formatAnalysisCount(context.variable_feature_count)} variable CpGs were observed; ${formatAnalysisCount(context.pca_component_count)} principal components were retained.`;
      const externalMatrixNote = context.source_matrix_materialized_in_duckdb === false
        ? "The complete M-value matrix remained external to DuckDB; this view contains compact analysis outputs only."
        : "";
      return {kind:"qc", context, downloads, panel:methylationPanelModel(context), metrics:[
          { label: "Samples", value: formatAnalysisCount(context.sample_count) },
          { label: "Patients", value: formatAnalysisCount(context.patient_count) },
          { label: "CpGs scanned", value: formatAnalysisCount(context.observed_feature_count) },
          { label: "CpGs in PCA", value: formatAnalysisCount(context.pca_feature_count) },
          { label: "PC1 variance", value: formatAnalysisPercent(context.pc1_variance_fraction) },
          { label: "PC2 variance", value: formatAnalysisPercent(context.pc2_variance_fraction) },
          { label: "Missingness", value: formatAnalysisPercent(context.missing_fraction) },
        ],
        notes:[`Processed-matrix QC for ${String(context.dataset_name || "the selected M-value assay")}. ${pcaDetails}`,
          covariateText + strongestAssociation, externalMatrixNote],
        plotArtifact};
    }
    if (isDifferentialMethylationContextMode(context.mode)) {
      const findArtifact = (name) => artifacts.find((item) => {
        const artifactName = String(item && item.name ? item.name : "");
        return artifactName === name || artifactName.endsWith(`/${name}`);
      });
      const plotArtifact = findArtifact("volcano_plot.png");
      const resultsArtifact = findArtifact("dm_results.tsv");
      const volcanoArtifact = findArtifact("volcano_points.tsv");
      const summaryArtifact = findArtifact("summary.json");
      const manifestArtifact = findArtifact("manifest.yaml");
      const paramsArtifact = findArtifact("params.yaml");
      const downloads = resultFiles("Result files", [
        plotArtifact,
        resultsArtifact,
        volcanoArtifact,
        summaryArtifact,
        manifestArtifact,
        paramsArtifact,
      ]);
      const covariates = Array.isArray(context.covariates_used)
        ? context.covariates_used.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const covariateText = covariates.length
        ? `Adjusted for: ${covariates.join(", ")}.`
        : "Unadjusted exploratory model: no varying declared covariates were included. Do not interpret disease effects as independent of demographic, cell-composition, or technical confounding.";
      const topCpg = String(context.top_cpg || "").trim();
      const topEffectValue = context.top_m_value_difference === null || context.top_m_value_difference === undefined
        ? NaN
        : Number(context.top_m_value_difference);
      const topHitText = topCpg
        ? `Top CpG: ${topCpg}; M-value difference ${Number.isFinite(topEffectValue) ? topEffectValue.toFixed(3) : "n/a"}; adjusted p = ${formatAnalysisPValue(context.top_adj_p_value)}.`
        : "No top CpG was reported.";
      const designText = `Contrast: ${String(context.contrast || "Cohort A - Cohort B")}. Design rank ${formatAnalysisCount(context.design_rank)} with ${formatAnalysisCount(context.residual_degrees_of_freedom)} residual degrees of freedom.`;
      const externalMatrixNote = context.source_matrix_materialized_in_duckdb === false
        ? "The complete M-value matrix remained external to DuckDB; this view contains compact analysis outputs only."
        : "";
      return {kind:"methylation", context, downloads, panel:methylationPanelModel(context), metrics:[
          { label: "Cohort A samples", value: formatAnalysisCount(context.cohort_a_sample_count) },
          { label: "Cohort B samples", value: formatAnalysisCount(context.cohort_b_sample_count) },
          { label: "CpGs analyzed", value: formatAnalysisCount(context.analyzed_feature_count) },
          { label: "BH < 0.05", value: formatAnalysisCount(context.significant_cpg_count) },
          { label: "Higher M in A", value: formatAnalysisCount(context.hypermethylated_cpg_count) },
          { label: "Lower M in A", value: formatAnalysisCount(context.hypomethylated_cpg_count) },
        ],
        notes:[`limma analysis of supplied processed M-values for ${String(context.dataset_name || "the selected assay")}. Positive M-value differences indicate higher methylation in Cohort A.`,
          covariateText + " " + designText, topHitText, externalMatrixNote], plotArtifact};
    }
    if (isQuantitativeAssayWilcoxonContextMode(context.mode)) {
      const assayLabel = String(context.assay_label || context.dataset_name || "Quantitative assay").trim();
      const topFeature = String(context.top_feature || "").trim();
      const topEffect = Number(context.top_rank_biserial_effect);
      const topHitText = topFeature
        ? `Top-ranked feature: ${topFeature}; rank-biserial effect ${Number.isFinite(topEffect) ? topEffect.toFixed(3) : "n/a"}; BH q = ${formatAnalysisPValue(context.top_adj_p_value)}.`
        : "No top-ranked tested feature was reported.";
      const externalMatrixNote = context.source_matrix_materialized_in_duckdb === false
        ? `The source measurement matrix remained external to DuckDB${context.source_matrix_copied_to_job === false ? " and was not copied into the job output" : ""}; only compact aggregate results are shown here.`
        : "";
      const modalityCaveat = String(context.modality || "") === "flow_cytometry"
        ? "Immune-cell abundance features may be compositional, so one population's apparent shift can reflect changes elsewhere in the measured cell mixture."
        : String(context.modality || "") === "serology"
          ? "Serology missingness can be feature-dependent; compare the cohort-specific missing counts before interpreting a marker."
          : "";
      const downloadableNames = new Set([
        "effect_plot.png",
        "compact_assay_results.tsv",
        "summary.json",
        "manifest.yaml",
        "params.yaml",
      ]);
      const downloads = resultFiles(
        "Result files",
        artifacts.filter((item) => downloadableNames.has(String(item && item.name ? item.name : ""))),
      );
      return {kind:"quantitative", context, downloads, assayLabel, topHitText, modalityCaveat, externalMatrixNote,
        metrics:[
          { label: "Cohort A samples", value: formatAnalysisCount(context.cohort_a_sample_count) },
          { label: "Cohort B samples", value: formatAnalysisCount(context.cohort_b_sample_count) },
          { label: "Features tested", value: formatAnalysisCount(context.tested_feature_count) },
          { label: "Features skipped", value: formatAnalysisCount(context.skipped_feature_count) },
          { label: "BH < 0.05", value: formatAnalysisCount(context.significant_feature_count) },
        ], rows:rankedQuantitativeAssayResults(context.results).slice(0,12).map(item=>[
          String(item.feature_id || ""), String(item.status || "n/a").replaceAll("_"," "),
          formatAnalysisCount(item.cohort_a_n),formatAnalysisCount(item.cohort_b_n),
          formatAnalysisCount(item.cohort_a_missing),formatAnalysisCount(item.cohort_b_missing),
          formatAnalysisNumber(item.cohort_a_median),formatAnalysisNumber(item.cohort_b_median),
          formatAnalysisNumber(item.median_difference),formatAnalysisNumber(item.rank_biserial_effect),
          formatAnalysisPValue(item.adj_p_value)])};
    }
    if (isDifferentialExpressionContextMode(context.mode)) {
      const isLimmaVoom = String(context.mode || "") === "external_rscript_transcriptomics_limma_voom_differential_expression";
      const plotArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "volcano_plot.png");
      const heatmapArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "top_genes_heatmap.png");
      const heatmapTableArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "top_genes_heatmap.tsv");
      const heatmapClusteringArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "top_genes_heatmap_clustering.json");
      const resultsArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "de_results.tsv");
      const volcanoArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "volcano_points.tsv");
      const summaryArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "summary.json");
      const modelArtifactNames = new Set(["model.json", "design_matrix.tsv", "contrast.tsv", "gene_filter.tsv", "normalization_factors.tsv", "analysis_covariates.tsv", "session_info.txt"]);
      const modelArtifacts = artifacts.filter((item) => modelArtifactNames.has(String(item && item.name ? item.name : "")));
      const downloads = resultFiles("Result files", [plotArtifact, heatmapArtifact, heatmapTableArtifact, heatmapClusteringArtifact, resultsArtifact, volcanoArtifact, summaryArtifact, ...modelArtifacts]);
      const summaryItems = [
        { label: "Cohort A samples", value: formatAnalysisCount(context.cohort_a_sample_count) },
        { label: "Cohort B samples", value: formatAnalysisCount(context.cohort_b_sample_count) },
        { label: "Input genes", value: formatAnalysisCount(context.input_gene_count ?? context.tested_gene_count ?? context.gene_count) },
        { label: "Retained after filtering", value: formatAnalysisCount(context.filtered_gene_count ?? context.gene_count) },
        { label: "BH < 0.05", value: formatAnalysisCount(context.significant_gene_count) },
      ];
      const topGene = String(context.top_gene || "").trim();
      const topLogFc = Number(context.top_log2_fold_change);
      const topHitText = topGene && topGene !== "n/a"
        ? `Top-ranked gene: ${topGene}; log2 fold change ${Number.isFinite(topLogFc) ? topLogFc.toFixed(3) : "n/a"}; adjusted p = ${formatAnalysisPValue(context.top_adj_p_value)}. ${Number.isFinite(topLogFc) && topLogFc >= 0 ? "Positive" : "Negative"} values mean higher expression in Cohort ${Number.isFinite(topLogFc) && topLogFc >= 0 ? "A" : "B"}.`
        : "No top-ranked gene was reported.";
      const covariates = Array.isArray(context.covariates_used) ? context.covariates_used.map(String).filter(Boolean) : [];
      const adjustmentText = covariates.length
        ? `The model adjusts for ${covariates.join(", ")}. Contrast: Cohort A minus Cohort B.`
        : "The model is cohort-only and unadjusted. Contrast: Cohort A minus Cohort B.";
      const methodText = isLimmaVoom
        ? `RSEM expected counts are filtered with edgeR filterByExpr, TMM-normalized, transformed to log2-CPM with voom precision weights, then tested with limma empirical Bayes and BH correction. ${adjustmentText}`
        : "Raw counts are analyzed with DESeq2. Positive log2 fold change means higher expression in Cohort A; negative means higher in Cohort B.";
      return {kind:"expression", context, downloads, metrics:summaryItems, isLimmaVoom, methodText, topHitText,
        plotArtifact, heatmapArtifact, heatmapTableArtifact, heatmapClusteringArtifact, volcanoArtifact};
    }
    if (isPathwayEnrichmentContextMode(context.mode)) {
      const plotArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "pathway_plot.png");
      const resultsArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "pathway_results.tsv");
      const rankingsArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "gene_rankings.tsv");
      const summaryArtifact = artifacts.find((item) => String(item && item.name ? item.name : "") === "summary.json");
      const downloads = resultFiles("Result files", [plotArtifact, resultsArtifact, rankingsArtifact, summaryArtifact]);
      const summaryItems = [
        { label: "Assay", value: String(context.dataset_name || "n/a") },
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
      return {kind:"pathway", context, downloads, positiveText, negativeText, plotArtifact, summaryItems};
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
      return {kind:"evidence", cards:[
        {suffix:"compare-a",title:"Cohort A Profile",items:overviewItems.slice(0,2)},
        {suffix:"compare-b",title:"Cohort B Profile",items:overviewItems.slice(2)},
        {suffix:"compare-disease",title:"Disease Differences",items:diseaseDeltaItems},
        {suffix:"compare-medication",title:"Medication Differences",items:medicationDeltaItems}]};
    }
    const diseaseItems = (context.top_diseases || []).slice(0, 8).map((item) => ({ label: item.disease, value: item.patient_count }));
    const medicationItems = (context.top_medications || []).slice(0, 8).map((item) => ({ label: item.medication, value: item.patient_count }));
    const periodItems = (context.timepoints_by_period || []).slice(0, 12).map((item) => ({ label: item.period, value: item.timepoint_count }));
    const visitItems = (context.visit_distribution || []).slice(0, 12).map((item) => ({ label: item.label, value: item.value }));
    return {kind:"evidence", cards:[
      {suffix:"summary-disease",title:"Top Diseases",items:diseaseItems},
      {suffix:"summary-medication",title:"Top Medications",items:medicationItems},
      {suffix:"summary-period",title:"Timepoints Over Time",items:periodItems},
      {suffix:"summary-visits",title:"Visits Per Patient",items:visitItems}]};
  }

























  function analysisIntentPresentation(intent) {
    const value = String(intent || "analysis");
    const labels = {
      analysis_external_rscript: { label: "R analysis", title: "An approved external R runner produced this result." },
      analysis_cross_modal_association: { label: "Cross-modal association", title: "Deterministic Spearman correlation of two explicitly matched measurements." },
      analysis_deterministic: { label: "Workspace summary", title: "Deterministic workspace summary produced by the app." },
      analysis_compare: { label: "Cohort comparison", title: "Deterministic comparison between the selected cohorts." },
      analysis_transcriptomics_expression: { label: "Transcriptomics expression", title: "Deterministic transcriptomics expression summary across the loaded assays." },
      analysis_transcriptomics_medication_compare: { label: "Transcriptomics by medication", title: "Deterministic transcriptomics comparison aligned to medication-specific datasets." },
      analysis_survival: { label: "Time-to-event analysis", title: "Deterministic Kaplan-Meier time-to-event analysis." },
      analysis_survival_compare: { label: "Time-to-event comparison", title: "Deterministic Kaplan-Meier time-to-event comparison between two cohorts." },
      analysis_trajectory: { label: "Trajectory analysis", title: "Deterministic longitudinal trajectory analysis." },
      analysis_trajectory_compare: { label: "Trajectory comparison", title: "Deterministic trajectory comparison between two cohorts." },
      general_llm: { label: "General LLM answer", title: "The selected model answered without receiving workspace, cohort, assay, or analysis context." },
      analysis_llm: { label: "LLM interpretation", title: "LM Studio narrative interpretation grounded in the provided analysis context." },
      analysis_compare_llm: { label: "LLM comparison", title: "LM Studio narrative comparison grounded in the provided cohort context." },
    };
    return labels[value] || {
      label: value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()),
      title: `Internal analysis intent: ${value}`,
    };
  }

  function renderAnalysisBadge(label,title,iconKind='') { return {label,title,iconKind}; }

  function formatAnalysisAiProviderGranularity(value) {
    const label = String(value || "").replace(/_/g, " ");
    return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : "";
  }

  function getAnalysisProvenanceChips(payload) {
    const data = payload && payload.data ? payload.data : {};
    const intentInfo = analysisIntentPresentation(payload && payload.intent ? payload.intent : "analysis");
    const plannedByLmStudio = data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio";
    const answeredByLmStudio = data.source === "llm";
    const aiProviderConsulted = plannedByLmStudio || answeredByLmStudio;
    const chips = [renderAnalysisBadge(intentInfo.label, intentInfo.title, "summary")];
    if (payload && payload.intent === "general_llm") {
      chips.push(renderAnalysisBadge(
        "No workspace context",
        "Only this prompt and recent General-question turns were sent to the selected model. No workspace, cohort, assay, or analysis context was supplied.",
        "no_context",
      ));
      if (data.model) chips.push(renderAnalysisBadge(data.model, "Model used for this general answer.", "llm"));
      return chips;
    }
    if (data.granularity_applied) {
      chips.push(renderAnalysisBadge(
        `Response detail: ${formatAnalysisAiProviderGranularity(data.granularity_applied)}`,
        `Detail available in the COHORTome response: ${data.granularity_applied}. This is separate from the context sent to a model.`,
        "response",
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
        `Model context: ${formatAnalysisAiProviderGranularity(data.ai_provider_context_granularity)}`,
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
    metaView.render(payload ? getAnalysisProvenanceChips(payload) : []);
  }

  function formatAnalysisScopeLabel(scopeValue) {
    const ids = String(scopeValue || "").split(",").map((item) => item.trim()).filter(Boolean);
    if (!ids.length) return "Full workspace";
    const usesSampleIds = ids.some(item => decodeIdentity(item)?.kind === 'sample' || (!decodeIdentity(item) && item.includes(':')));
    const showDataset = new Set(ids.map(id => decodeIdentity(id)?.datasetId).filter(Boolean)).size > 1
      || (state.analysisScopeMetadata?.dataset_ids || []).length > 1;
    const preview = ids.slice(0, 6).map(id => displayIdentity(id, showDataset)).join(", ");
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
    const contextMode = isGeneralQuestionMode() ? "general" : "workspace";
    state.analysisTurns.push({ role: "user", prompt, scope: currentScope || "", compareScope: compareScope || "", contextMode });
    state.analysisTurns.push({
      role: "assistant",
      contextMode,
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
    if (payload?.data?.source === 'deterministic' && (context?.overview || mode === 'compare')) return true;
    return [
      "custom_script",
      "external_rscript_transcriptomics_deseq2_differential_expression",
      "cross_modal_association",
      "external_rscript_transcriptomics_limma_voom_differential_expression",
      "external_rscript_transcriptomics_hallmark_pathway_enrichment",
      "external_rscript_methylation_qc_pca",
      "external_rscript_methylation_limma_differential_methylation",
      "external_rscript_quantitative_assay_wilcoxon_comparison",
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
    if (isQuantitativeAssayWilcoxonContextMode(mode)) {
      const assayLabel = String(context && (context.assay_label || context.dataset_name) ? (context.assay_label || context.dataset_name) : "this quantitative assay").trim();
      return [
        `Can you explain the rank-biserial effects in ${assayLabel}?`,
        `Which ${assayLabel} features have the strongest cohort separation?`,
        "How should I interpret features with large effects but BH q above 0.05?",
        "What covariates and assay preprocessing should be added before confirmatory analysis?",
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
      openAnalysisSetup();
      threadView.render([],state.currentAnalysisSessionId);
      return;
    }
    placeAnalysisRequest(true);
    document.getElementById("analysisSetupDisclosure").open = false;
    let latest=-1;
    for(let i=state.analysisTurns.length-1;i>=0;i--) {
      const turn=state.analysisTurns[i];
      if(turn?.role==="assistant" && !turn.pending && turn.payload) {latest=i;break;}
    }
    const turns=state.analysisTurns.map((turn,turnIndex)=>{
      const general=turn.contextMode==="general" || turn.payload?.intent==="general_llm";
      if(turn.role==="user") return {role:"user",prompt:turn.prompt,general,
        scope:formatAnalysisScopeLabel(turn.scope || ""),
        compareScope:turn.compareScope ? formatAnalysisScopeLabel(turn.compareScope) : ""};
      if(turn.pending) return {pending:true,general,pendingLabel:turn.pendingLabel,pendingDetail:turn.pendingDetail};
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

      const error=turn.payload?.intent==="analysis_error" || turn.payload?.data?.source==="error";
      const titles={summary:'Clinical cohort summary',compare:'Clinical cohort comparison',
        survival:'Time-to-event analysis',survival_compare:'Time-to-event comparison',
        trajectory:'Clinical trajectory',trajectory_compare:'Trajectory comparison',
        external_rscript_transcriptomics_limma_voom_differential_expression:'limma-voom differential expression',
        external_rscript_transcriptomics_deseq2_differential_expression:'DESeq2 differential expression'};
      const overview=context?.overview;
      const badges=[];
      const badge=(label,values,side='')=>{
        if(values && Number.isFinite(values.patient_count)) badges.push({side,
          text:`${label} · ${formatAnalysisCount(values.patient_count)} patients${Number.isFinite(values.timepoint_count) ? ` · ${formatAnalysisCount(values.timepoint_count)} records` : ''}`});
      };
      badge('Selected group',overview || context);
      badge('Cohort A',context?.cohort_a?.overview || context?.cohort_a,'cohort-a');
      badge('Cohort B',context?.cohort_b?.overview || context?.cohort_b,'cohort-b');
      for(const side of ['A','B']) {
        const count=context?.[`cohort_${side.toLowerCase()}_sample_count`];
        if(Number.isFinite(count)) badges.push({side:`cohort-${side.toLowerCase()}`,text:`Cohort ${side} · ${formatAnalysisCount(count)} samples`});
      }
      const audit=turn.payload?.data?.implementation_audit;
      return {general,error,latest:turnIndex===latest,contextParts,badges,framing:turn.framing,audit,
        heading:!general && !error && turn.showPlots ? titles[context?.mode] || context?.method || (overview ? 'Clinical cohort summary' : 'Analysis results') : '',
        visuals:turn.showPlots ? analysisVisuals(turn.payload,turnIndex) : '',
        reply:queryReplyModel(turn.payload), data:turn.payload.data,
        provenance:getAnalysisProvenanceChips(turn.payload),
        followups:turnIndex===latest && turn.payload?.data?.execution!=="queued" ? uniquePrompts(getAnalysisFollowUpPrompts(turn.payload,turn.showPlots)).slice(0,4) : []};
    });
    threadView.render(turns,state.currentAnalysisSessionId);
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
    if (!isGeneralQuestionMode() && analysisPromptEl.value.trim() === "Compare measurements:") {
      document.getElementById("associationOpenBtn").click();
      if (analysisPromptEl.value.trim() === "Compare measurements:") {
        setAnalysisBlockedStatus("Choose a matrix and feature for each measurement before running.");
        return;
      }
    }
    if (!isGeneralQuestionMode() && document.getElementById("analysisMethodSelect").value === "summary") state.analysisExecutionMode = "deterministic";
    const submittedDraft = analysisPromptEl.value;
    const prompt = submittedDraft.trim();
    const generalQuestion = isGeneralQuestionMode();
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
    const showPlots = generalQuestion ? false : analysisPromptRequestsPlots(prompt);
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    const selectedAssayDatasets = Array.isArray(state.selectedAssayDatasets) ? state.selectedAssayDatasets : [];
    if ((generalQuestion || llmOnly || plannerOnly) && (!state.lmStatus || state.lmStatus.available !== true)) {
      const message = plannerOnly
        ? "LLM planner unavailable. Start an LLM model or choose a deterministic analysis."
        : generalQuestion
          ? "General questions require an available model provider."
          : "LLM unavailable. Start an LLM model or choose a deterministic analysis.";
      setAnalysisBlockedStatus(message);
      renderAnalysisBlockedTurn(prompt, generalQuestion ? "" : currentScope, generalQuestion ? "" : compareScope, message);
      return;
    }
    if (!generalQuestion && compareMode && (!state.analysisSelectedSavedCohortId || !state.analysisCompareSavedCohortId)) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis cohort comparison requires saved Cohort A and Cohort B.";
      state.analysisExecutionMode = "auto";
      return;
    }
    if (!generalQuestion && compareMode) {
      const overlappingIds = overlappingAnalysisScopeIds(currentScopeIds, compareScopeIds);
      if (overlappingIds.length) {
        const preview = overlappingIds.slice(0, 6).map(id => displayIdentity(id)).join(", ");
        const suffix = overlappingIds.length > 6 ? ` (+${overlappingIds.length - 6} more)` : "";
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = `Cohort A and Cohort B must be disjoint. Remove the overlapping IDs: ${preview}${suffix}.`;
        state.analysisExecutionMode = "auto";
        return;
      }
    }
    if (!generalQuestion && requiresSingleSelectedAssayDataset(state.analysisSelectedCatalogItemId) && selectedAssayDatasets.length !== 1) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = selectedAssayDatasets.length
        ? "This assay tool requires exactly one selected assay."
        : "Select one assay before running this assay tool.";
      state.analysisExecutionMode = "auto";
      return;
    }
    if (!generalQuestion && compareMode && requiresSingleSelectedAssayDataset(state.analysisSelectedCatalogItemId) && selectedAssayDatasets.length === 1 && typeof assayDatasetOverlap === "function") {
      const overlap = assayDatasetOverlap(selectedAssayDatasets[0]);
      const selectedCatalogItem = typeof currentAnalysisCatalogItem === "function" ? currentAnalysisCatalogItem() : null;
      const minimumOverlap = Math.max(1, Number(selectedCatalogItem && selectedCatalogItem.minimum_samples_per_cohort ? selectedCatalogItem.minimum_samples_per_cohort : 1));
      if (overlap && (overlap.overlapA < minimumOverlap || overlap.overlapB < minimumOverlap)) {
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = `Selected assay "${selectedAssayDatasets[0]}" overlaps Cohort A by ${overlap.overlapA} and Cohort B by ${overlap.overlapB}. Choose an assay with at least ${minimumOverlap} samples in both cohorts.`;
        state.analysisExecutionMode = "auto";
        return;
      }
    }
    const workspaceRevision = state.workspaceRevision;
    const requestIsStale = () => !generalQuestion && workspaceRevision !== state.workspaceRevision;
    state.analysisInFlight = true;
    analysisRunBtnEl.disabled = true;
    if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = generalQuestion ? "Waiting for the model..." : "Running analysis...";
    setAnalysisComposerStatus(generalQuestion ? "Waiting for a general answer." : "Running analysis. Results will appear below.");
    metaView.render([]);
    state.analysisExamplesPinnedOpen = false;
    state.analysisTurns.push({ role: "user", prompt, scope: generalQuestion ? "" : currentScope, compareScope: generalQuestion ? "" : compareScope, contextMode: generalQuestion ? "general" : "workspace" });
    const setupDisclosure = document.getElementById("analysisSetupDisclosure");
    if (setupDisclosure) setupDisclosure.open = false;
    state.analysisTurns.push({
      role: "assistant",
      pending: true,
      contextMode: generalQuestion ? "general" : "workspace",
      pendingLabel: generalQuestion ? "Asking model" : "Preparing response",
      pendingDetail: generalQuestion
        ? "Waiting for a general answer without workspace context."
        : "Building cohort context and waiting for the model reply.",
    });
    renderAnalysisThread();
    scrollAnalysisTurnIntoView(state.analysisTurns.length - 1);
    syncCurrentAnalysisSessionFromUi({ render: true });
    startAnalysisProgressUpdates(generalQuestion ? false : compareMode, showPlots);
    try {
      if (!generalQuestion && state.analysisSelectedCatalogItemId === "synthetic-custom-script") {
        await prepareScriptForRun();
        if (requestIsStale()) return;
      }
      const response = await fetch(generalQuestion ? "/llm/general" : "/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(generalQuestion
          ? { prompt, history: historyForContext("general") }
          : {
            prompt,
            catalog_item_id: state.analysisSelectedCatalogItemId || "",
            measurement: state.analysisMeasurement || "",
            custom_script: state.analysisSelectedCatalogItemId === "synthetic-custom-script" ? state.analysisScriptDraft?.script || "" : "",
            input_contract_id: state.analysisScriptDraft?.contract_id || "",
            script_language: state.analysisScriptDraft?.language || "python",
            sandbox_image_id: state.analysisScriptDraft?.image_id || "",
            custom_assay_ids: state.analysisSelectedCatalogItemId === "synthetic-custom-script" ? state.selectedAssayDatasets || [] : [],
            analysis_session_id: state.currentAnalysisSessionId || "",
            assay_id: selectedAssayDatasets.length === 1 ? selectedAssayDatasets[0] : "",
            dataset_id: analysisWorkspaceKey(),
            selected_patient_ids: currentScope,
            query_result_handle: state.analysisScopeMetadata && typeof state.analysisScopeMetadata === "object"
              ? String(state.analysisScopeMetadata.query_result_handle || "")
              : "",
            scope_metadata: state.analysisScopeMetadata && typeof state.analysisScopeMetadata === "object" ? state.analysisScopeMetadata : {},
            compare_mode: compareMode,
            compare_selected_patient_ids: compareScope,
            compare_scope_metadata: state.analysisCompareScopeMetadata && typeof state.analysisCompareScopeMetadata === "object" ? state.analysisCompareScopeMetadata : {},
            llm_only: llmOnly,
            deterministic_only: deterministicOnly,
            history: historyForContext("workspace"),
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
        if (requestIsStale()) return;
        throw new Error(message);
      }
      const payload = await response.json();
      if (requestIsStale()) return;
      const completedSuccessfully = payload?.intent !== "analysis_error"
        && payload?.data?.source !== "error" && payload?.data?.execution !== "queued";
      if (completedSuccessfully && analysisPromptEl.value === submittedDraft) analysisPromptEl.value = "";
      const finalShowPlots = showPlots || analysisPayloadHasPlots(payload);
      stopAnalysisProgressUpdates();
      renderAnalysisMeta(payload);
      state.analysisTurns[state.analysisTurns.length - 1] = { role: "assistant", payload, showPlots: finalShowPlots, contextMode: generalQuestion ? "general" : "workspace" };
      renderAnalysisThread();
      if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
      syncCurrentAnalysisSessionFromUi({ render: true });
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = generalQuestion
        ? "Answer complete."
        : payload && payload.data && payload.data.execution === "queued"
        ? "Analysis job submitted."
        : "Analysis complete.";
      setAnalysisComposerStatus(analysisStatusEl.textContent);
      scrollAnalysisTurnIntoView(state.analysisTurns.length - 1);
      const contextMode = generalQuestion ? "general" : "workspace";
      state.analysisHistory.push({ role: "user", content: prompt, context_mode: contextMode });
      state.analysisHistory.push({ role: "assistant", content: payload.reply || "", context_mode: contextMode });
      state.analysisHistory = state.analysisHistory.slice(-16);
      state.analysisExecutionMode = "auto";
      syncCurrentAnalysisSessionFromUi({ render: true });
      if (payload && payload.data && payload.data.execution === "queued" && typeof handleAnalysisJobSubmission === "function") {
        handleAnalysisJobSubmission(payload);
      }
    } catch (error) {
      if (requestIsStale()) return;
      openAnalysisSetup();
      state.analysisTurns[state.analysisTurns.length - 1] = {
        role: "assistant",
        contextMode: generalQuestion ? "general" : "workspace",
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
    editSetup,
    openAnalysisSetup,
    renderAnalysisMeta,
    renderAnalysisCompareMode,
    analysisPromptRequestsPlots,
    analysisPayloadHasPlots,
    renderAnalysisThread,
    renderAnalysisContextMode,
    setContextMode: setAnalysisContextMode,
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
      placeAnalysisRequest(true);
      document.getElementById("analysisSetupDisclosure").open = false;
      document.getElementById("analysisRequestDetails").open = true;
      analysisPromptEl.value = button.dataset.analysisFollowupPrompt || "";
      state.analysisSelectedCatalogItemId = "";
      state.analysisExecutionMode = button.dataset.analysisFollowupMode === "llm_only" ? "llm_only" : "auto";
      if (typeof renderAnalysisFlowBar === "function") renderAnalysisFlowBar();
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "LLM interpretation follow-up prepared. Press Enter or click Run analysis.";
      setAnalysisComposerStatus("LLM interpretation follow-up. Review the request, then run it.");
      analysisPromptEl.focus({ preventScroll: true });
      document.getElementById("analysisRequestComposer").scrollIntoView({ behavior: "smooth", block: "end" });
    },
    handleAnalysisResultBoardClick(event) {
      const summary = event.target.closest(".analysis-result-collapsible > summary");
      if (!summary || !analysisThreadEl.contains(summary)) return;
      window.setTimeout(() => {
        mountAnalysisPlots();
      }, 0);
    },
    runAnalysis,
    setAnalysisComposerStatus,
  };
}
