export function createAnalysisUi(ctx) {
  const { refs, helpers, callbacks, state } = ctx;
  const {
    analysisMetaEl,
    analysisThreadEl,
    analysisStatusEl,
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
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
  } = callbacks;

  const ANALYSIS_PLOT_COLORS = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed", "#dc2626", "#d97706"];

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

  function renderAnalysisPlotsMarkup(context, turnIndex) {
    if (!context) return '<div class="empty">No analysis plots available.</div>';
    if (context.mode === "molecular_medication_compare") {
      const comparisons = Array.isArray(context.comparisons) ? context.comparisons : [];
      const cards = comparisons.map((item, index) => {
        const title = `${item.medication_a || "Group A"} vs ${item.medication_b || "Group B"}`;
        const note = context.exploratory_note || "Exploratory transcriptomics comparison.";
        const thresholdNote = `Coloring is exploratory: red = log2FC >= 1 and p <= 0.05, blue = log2FC <= -1 and p <= 0.05, gray = everything else. Positive log2FC means higher in ${item.medication_a || "Group A"}; negative log2FC means higher in ${item.medication_b || "Group B"}.`;
        return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Exploratory Volcano Plot: ${escapeHtml(title)}</h3><p class="section-note">${escapeHtml(note)}</p><p class="section-note">${escapeHtml(thresholdNote)}</p>${plotPlaceholder(`analysis-plot-${turnIndex}-molecular-volcano-${index}`, 420)}</div>`;
      });
      return cards.join("") || '<div class="empty">No exploratory molecular comparison plot available.</div>';
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

  function mountAnalysisPlots() {
    state.analysisTurns.forEach((turn, turnIndex) => {
      if (!turn || !turn.showPlots || !turn.payload || !turn.payload.data) return;
      const context = turn.payload.data.context;
      if (!context) return;
      if (context.mode === "molecular_medication_compare") {
        (context.comparisons || []).forEach((item, comparisonIndex) => {
          const points = Array.isArray(item.exploratory_volcano_points) ? item.exploratory_volcano_points : [];
          if (!points.length) return;
          const volcano = buildExploratoryVolcanoPlot(points, `${item.medication_a || "A"} vs ${item.medication_b || "B"}`);
          mountPlot(`analysis-plot-${turnIndex}-molecular-volcano-${comparisonIndex}`, volcano.traces, volcano.layout);
        });
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
      analysis_molecular_expression: { label: "Molecular expression", title: "Deterministic molecular expression summary across the loaded molecular datasets." },
      analysis_molecular_medication_compare: { label: "Molecular by medication", title: "Deterministic molecular comparison aligned to medication-specific datasets." },
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

  function renderAnalysisBadge(label, title) {
    const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
    return `<span class="query-chip badge"${safeTitle}>${escapeHtml(label)}</span>`;
  }

  function getAnalysisProvenanceChips(payload) {
    const data = payload && payload.data ? payload.data : {};
    const intentInfo = analysisIntentPresentation(payload && payload.intent ? payload.intent : "analysis");
    const chips = [renderAnalysisBadge(intentInfo.label, intentInfo.title)];
    if (data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio") {
      chips.push(renderAnalysisBadge("LLM-planned", "LM Studio translated the prompt into a constrained internal analysis plan."));
      chips.push(renderAnalysisBadge("Deterministic execution", "The app executed the planned analysis deterministically against local cohort data."));
      if (data.planner.model) chips.push(renderAnalysisBadge(data.planner.model, "LM Studio model used for analysis planning."));
      return chips;
    }
    chips.push(renderAnalysisBadge(data.source === "llm" ? "LLM answer" : "Deterministic", data.source === "llm"
      ? "LM Studio generated the narrative interpretation from the provided analysis context."
      : "The app executed this analysis deterministically."));
    if (data.model) chips.push(renderAnalysisBadge(data.model, "LM Studio model used for this analysis reply."));
    return chips;
  }

  function renderAnalysisMeta(payload) {
    if (!analysisMetaEl) return;
    analysisMetaEl.innerHTML = getAnalysisProvenanceChips(payload).join("");
  }

  function formatAnalysisScopeLabel(scopeValue) {
    const ids = String(scopeValue || "").split(",").map((item) => item.trim()).filter(Boolean);
    if (!ids.length) return "Full workspace";
    const preview = ids.slice(0, 6).join(", ");
    const suffix = ids.length > 6 ? ` ... (+${ids.length - 6} more)` : "";
    return `${ids.length} IDs: ${preview}${suffix}`;
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

  function analysisPromptRequestsPlots(prompt) {
    const lowered = String(prompt || "").toLowerCase();
    return ["trajectory", "response to", "kaplan", "survival", "plot", "plots", "chart", "charts", "graph", "graphs", "visualize", "visualise", "distribution", "distributions", "histogram", "bar plot", "line plot", "trend", "trends", "over time"].some((token) => lowered.includes(token));
  }

  function analysisPayloadHasPlots(payload) {
    const context = payload && payload.data ? payload.data.context : null;
    const mode = context && typeof context.mode === "string" ? context.mode : "";
    return [
      "molecular_medication_compare",
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
    return `<div class="query-followups" style="margin-top:12px;"><div class="query-followups-label">Suggested follow-up queries</div><div class="query-followups-list">${followUps.map((item) => `<button type="button" class="query-chip" data-analysis-followup-prompt="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("")}</div></div>`;
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
    const molecularComparison = Array.isArray(context && context.comparisons) && context.comparisons.length
      ? context.comparisons[0]
      : null;
    const medicationComparisonLabel = molecularComparison
      ? `${String(molecularComparison.medication_a || "Group A").trim()} vs ${String(molecularComparison.medication_b || "Group B").trim()}`
      : "this molecular comparison";
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
    if (mode === "molecular_medication_compare") {
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
    analysisThreadEl.innerHTML = state.analysisTurns.map((turn, turnIndex) => {
      if (turn.role === "user") {
        const compareHtml = turn.compareScope ? `<div class="analysis-turn-scope"><strong>Cohort B:</strong> ${escapeHtml(formatAnalysisScopeLabel(turn.compareScope || ""))}</div>` : "";
        return `<article class="analysis-turn analysis-turn-user"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${escapeHtml(turn.prompt)}</p><div class="analysis-turn-scope"><strong>${turn.compareScope ? "Cohort A" : "Scope"}:</strong> ${escapeHtml(formatAnalysisScopeLabel(turn.scope || ""))}</div>${compareHtml}</div></article>`;
      }
      if (turn.pending) {
        return `<article class="analysis-turn analysis-turn-pending"><div class="analysis-turn-label">Analysis</div><div class="analysis-turn-meta"><span class="query-chip badge">pending</span><span class="query-chip badge">${escapeHtml(turn.pendingLabel || "Preparing response")}</span></div><div class="analysis-turn-body"><div class="analysis-pending-row"><div class="analysis-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></div><span>${escapeHtml(turn.pendingDetail || "Building cohort context and waiting for the model reply.")}</span></div></div></article>`;
      }
      const context = turn.payload && turn.payload.data ? turn.payload.data.context : null;
      const notable = context && Array.isArray(context.notable_findings) ? context.notable_findings : [];
      const source = context && typeof context.source === "string" && context.source.trim() ? context.source : "";
      const contextParts = [];
      if (source) contextParts.push(source);
      if (context && context.mode === "molecular_expression") {
        const datasetCount = Array.isArray(context.datasets) ? context.datasets.length : 0;
        if (datasetCount) contextParts.push(`${datasetCount} molecular dataset${datasetCount === 1 ? "" : "s"}`);
        if (context.gene_id) contextParts.push(`gene ${context.gene_id}`);
      }
      if (context && (context.mode === "survival" || context.mode === "survival_compare")) {
        contextParts.push(`event: ${formatTimeToEventLabel(context)}`);
      }
      if (notable.length) contextParts.push(...notable);
      const followUpsHtml = renderAnalysisFollowUps(getAnalysisFollowUpPrompts(turn.payload, turn.showPlots));
      return `<article class="analysis-turn analysis-turn-assistant"><div class="analysis-turn-label">Analysis</div><div class="analysis-turn-meta">${getAnalysisProvenanceChips(turn.payload).join("")}</div><div class="analysis-turn-body">${renderQueryReply(turn.payload)}</div>${contextParts.length ? `<div class="analysis-turn-context"><p><strong>Context:</strong> ${escapeHtml(contextParts.join(" | "))}</p></div>` : ""}${turn.showPlots ? `<div class="analysis-plot-grid">${renderAnalysisPlotsMarkup(context, turnIndex)}</div>` : ""}${followUpsHtml}<details class="query-section"><summary>Show analysis data</summary><pre>${escapeHtml(JSON.stringify(turn.payload.data, null, 2))}</pre></details></article>`;
    }).join("");
    mountAnalysisPlots();
  }

  async function runAnalysis() {
    if (state.analysisInFlight) return;
    const prompt = analysisPromptEl.value.trim();
    if (!prompt) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Enter an analysis prompt first.";
      return;
    }
    state.analysisInFlight = true;
    analysisRunBtnEl.disabled = true;
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = "Running analysis...";
    if (analysisMetaEl) analysisMetaEl.innerHTML = "";
    const currentScopeIds = resolveAnalysisScopeIds("a");
    const compareScopeIds = analysisCompareModeEl && analysisCompareModeEl.checked ? resolveAnalysisScopeIds("b") : [];
    const currentScope = currentScopeIds.join(",");
    const compareScope = compareScopeIds.join(",");
    const llmOnly = state.analysisExecutionMode === "llm_only";
    const deterministicOnly = state.analysisExecutionMode === "deterministic";
    const showPlots = analysisPromptRequestsPlots(prompt);
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    if (compareMode && (!state.analysisSelectedSavedCohortId || !state.analysisCompareSavedCohortId)) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis cohort comparison requires saved Cohort A and Cohort B.";
      state.analysisExecutionMode = "auto";
      return;
    }
    state.analysisExamplesPinnedOpen = false;
    state.analysisTurns.push({ role: "user", prompt, scope: currentScope, compareScope });
    state.analysisTurns.push({ role: "assistant", pending: true, pendingLabel: "Preparing response", pendingDetail: "Building cohort context and waiting for the model reply." });
    renderAnalysisThread();
    syncCurrentAnalysisSessionFromUi({ render: true });
    startAnalysisProgressUpdates(compareMode, showPlots);
    try {
      const response = await fetch("/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          data_dir: (refs.dataDirEl.dataset && refs.dataDirEl.dataset.scopeId) ? refs.dataDirEl.dataset.scopeId : (refs.dataDirEl.value.trim() || refs.dataDirEl.value),
          selected_patient_ids: currentScope,
          compare_mode: compareMode,
          compare_selected_patient_ids: compareScope,
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
      syncCurrentAnalysisSessionFromUi({ render: true });
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis complete.";
      state.analysisHistory.push({ role: "user", content: prompt });
      state.analysisHistory.push({ role: "assistant", content: payload.reply || "" });
      state.analysisHistory = state.analysisHistory.slice(-8);
      state.analysisExecutionMode = "auto";
      syncCurrentAnalysisSessionFromUi({ render: true });
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
      syncCurrentAnalysisSessionFromUi({ render: true });
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis failed.";
      state.analysisExecutionMode = "auto";
    } finally {
      stopAnalysisProgressUpdates();
      state.analysisInFlight = false;
      analysisRunBtnEl.disabled = false;
    }
  }

  return {
    renderAnalysisMeta,
    renderAnalysisCompareMode,
    analysisPromptRequestsPlots,
    analysisPayloadHasPlots,
    renderAnalysisThread,
    handleAnalysisFollowUpsClick(event) {
      const button = event.target.closest("[data-analysis-followup-prompt]");
      if (!button || !analysisThreadEl.contains(button)) return;
      analysisPromptEl.value = button.dataset.analysisFollowupPrompt || "";
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = "Analysis follow-up prompt prepared. Press Enter or click Run analysis.";
      analysisPromptEl.focus();
    },
    runAnalysis,
  };
}
