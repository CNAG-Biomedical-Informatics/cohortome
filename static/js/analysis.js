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
  } = callbacks;

  function renderBarChart(items, labelKey, valueKey, color) {
    if (!items.length) return '<div class="empty">No data.</div>';
    const max = Math.max(...items.map((item) => item[valueKey]), 1);
    const width = 520;
    const rowHeight = 26;
    const height = items.length * rowHeight + 8;
    const bars = items.map((item, index) => {
      const y = index * rowHeight + 4;
      const barWidth = Math.max(8, (item[valueKey] / max) * 300);
      return `
        <text x="0" y="${y + 14}" fill="#61758c" font-size="12">${item[labelKey]}</text>
        <rect x="190" y="${y}" width="${barWidth}" height="16" rx="8" fill="${color}"></rect>
        <text x="${200 + barWidth}" y="${y + 13}" fill="#132238" font-size="12">${item[valueKey]}</text>
      `;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMinYMin meet">${bars}</svg>`;
  }

  function renderKaplanMeierPlot(seriesList) {
    const series = (Array.isArray(seriesList) ? seriesList : []).filter((item) => Array.isArray(item.points) && item.points.length);
    if (!series.length) return '<div class="empty">No survival curve data available.</div>';
    const width = 560;
    const height = 260;
    const margin = { top: 16, right: 24, bottom: 36, left: 42 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const maxTime = Math.max(1, ...series.flatMap((item) => item.points.map((point) => Number(point.time_days || 0))));
    const colors = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed"];
    const xFor = (value) => margin.left + (Number(value || 0) / maxTime) * innerWidth;
    const yFor = (value) => margin.top + (1 - Number(value || 0)) * innerHeight;
    const axes = `
      <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerHeight}" stroke="#94a3b8" />
      <line x1="${margin.left}" y1="${margin.top + innerHeight}" x2="${margin.left + innerWidth}" y2="${margin.top + innerHeight}" stroke="#94a3b8" />
      <text x="${margin.left}" y="${height - 8}" fill="#61758c" font-size="12">Days since first dated observation of the selected measure</text>
      <text x="8" y="${margin.top - 2}" fill="#61758c" font-size="12">Survival</text>
    `;
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((value) => `
      <g>
        <line x1="${margin.left - 4}" y1="${yFor(value)}" x2="${margin.left + innerWidth}" y2="${yFor(value)}" stroke="rgba(148,163,184,0.18)" />
        <text x="8" y="${yFor(value) + 4}" fill="#61758c" font-size="11">${Math.round(value * 100)}%</text>
      </g>
    `).join("");
    const lines = series.map((item, index) => {
      const color = colors[index % colors.length];
      const points = item.points;
      let path = `M ${xFor(points[0].time_days)} ${yFor(points[0].survival_probability)}`;
      for (let i = 1; i < points.length; i += 1) {
        const prev = points[i - 1];
        const current = points[i];
        path += ` L ${xFor(current.time_days)} ${yFor(prev.survival_probability)}`;
        path += ` L ${xFor(current.time_days)} ${yFor(current.survival_probability)}`;
      }
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"></path>`;
    }).join("");
    const legend = series.map((item, index) => {
      const color = colors[index % colors.length];
      return `<div style="display:flex;align-items:center;gap:8px;"><span style="width:12px;height:12px;border-radius:999px;background:${color};display:inline-block;"></span><small>${escapeHtml(item.label || `Series ${index + 1}`)}</small></div>`;
    }).join("");
    return `<div><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMinYMin meet">${ticks}${axes}${lines}</svg><div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;">${legend}</div></div>`;
  }

  function renderTrajectoryPlot(seriesList, summarySeries) {
    const patientSeries = (Array.isArray(seriesList) ? seriesList : []).filter((item) => Array.isArray(item.points) && item.points.length);
    const summary = summarySeries && Array.isArray(summarySeries.points) ? summarySeries.points : [];
    const combined = patientSeries.flatMap((item) => item.points);
    const summaryIncluded = combined.concat(summary);
    if (!summaryIncluded.length) return '<div class="empty">No trajectory data available.</div>';
    const width = 560;
    const height = 280;
    const margin = { top: 16, right: 20, bottom: 36, left: 44 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const labels = Array.from(new Set(summaryIncluded.map((point) => String(point.x_label || point.x || ""))));
    const xIndex = new Map(labels.map((label, index) => [label, index]));
    const yValues = summaryIncluded.map((point) => Number(point.value || 0));
    const yMin = Math.min(...yValues);
    const yMax = Math.max(...yValues);
    const ySpan = Math.max(yMax - yMin, 1);
    const xFor = (label) => margin.left + ((xIndex.get(String(label)) || 0) / Math.max(labels.length - 1, 1)) * innerWidth;
    const yFor = (value) => margin.top + (1 - ((Number(value || 0) - yMin) / ySpan)) * innerHeight;
    const renderPath = (points, color, widthPx, opacity) => {
      if (!points.length) return "";
      const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(point.x_label || point.x)} ${yFor(point.value)}`).join(" ");
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="${widthPx}" stroke-linecap="round" stroke-linejoin="round" opacity="${opacity}"></path>`;
    };
    const faintPalette = ["#93c5fd", "#7dd3fc", "#a7f3d0", "#c4b5fd", "#f9a8d4", "#fcd34d"];
    const patientPaths = patientSeries.slice(0, 12).map((item, index) => renderPath(item.points, faintPalette[index % faintPalette.length], 1.5, 0.7)).join("");
    const summaryPath = renderPath(summary, "#1d4ed8", 3.2, 1);
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
      const value = yMin + ySpan * fraction;
      return `<g><line x1="${margin.left}" y1="${yFor(value)}" x2="${margin.left + innerWidth}" y2="${yFor(value)}" stroke="rgba(148,163,184,0.18)" /><text x="8" y="${yFor(value) + 4}" fill="#61758c" font-size="11">${value.toFixed(1)}</text></g>`;
    }).join("");
    const xTicks = labels.filter((_, index) => index === 0 || index === labels.length - 1 || index === Math.floor((labels.length - 1) / 2)).map((label) => `<text x="${xFor(label)}" y="${height - 10}" fill="#61758c" font-size="11" text-anchor="middle">${escapeHtml(label)}</text>`).join("");
    return `<div><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMinYMin meet">${yTicks}<line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerHeight}" stroke="#94a3b8" /><line x1="${margin.left}" y1="${margin.top + innerHeight}" x2="${margin.left + innerWidth}" y2="${margin.top + innerHeight}" stroke="#94a3b8" />${patientPaths}${summaryPath}${xTicks}</svg><div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;"><div style="display:flex;align-items:center;gap:8px;"><span style="width:12px;height:12px;border-radius:999px;background:#1d4ed8;display:inline-block;"></span><small>${escapeHtml(summarySeries.label || "Cohort median")}</small></div><div style="display:flex;align-items:center;gap:8px;"><span style="width:12px;height:12px;border-radius:999px;background:#93c5fd;display:inline-block;"></span><small>Individual patient trajectories</small></div></div></div>`;
  }

  function renderTrajectoryComparisonPlot(seriesList) {
    const series = (Array.isArray(seriesList) ? seriesList : []).filter((item) => Array.isArray(item.points) && item.points.length);
    if (!series.length) return '<div class="empty">No comparison trajectory data available.</div>';
    const width = 560;
    const height = 280;
    const margin = { top: 16, right: 20, bottom: 36, left: 44 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const allPoints = series.flatMap((item) => item.points || []);
    const labels = Array.from(new Set(allPoints.map((point) => String(point.x_label || point.x || ""))));
    const xIndex = new Map(labels.map((label, index) => [label, index]));
    const yValues = allPoints.map((point) => Number(point.value || 0));
    const yMin = Math.min(...yValues);
    const yMax = Math.max(...yValues);
    const ySpan = Math.max(yMax - yMin, 1);
    const palette = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed"];
    const xFor = (label) => margin.left + ((xIndex.get(String(label)) || 0) / Math.max(labels.length - 1, 1)) * innerWidth;
    const yFor = (value) => margin.top + (1 - ((Number(value || 0) - yMin) / ySpan)) * innerHeight;
    const paths = series.map((item, index) => {
      const path = item.points.map((point, pointIndex) => `${pointIndex === 0 ? "M" : "L"} ${xFor(point.x_label || point.x)} ${yFor(point.value)}`).join(" ");
      return `<path d="${path}" fill="none" stroke="${palette[index % palette.length]}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"></path>`;
    }).join("");
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
      const value = yMin + ySpan * fraction;
      return `<g><line x1="${margin.left}" y1="${yFor(value)}" x2="${margin.left + innerWidth}" y2="${yFor(value)}" stroke="rgba(148,163,184,0.18)" /><text x="8" y="${yFor(value) + 4}" fill="#61758c" font-size="11">${value.toFixed(1)}</text></g>`;
    }).join("");
    const xTicks = labels.filter((_, index) => index === 0 || index === labels.length - 1 || index === Math.floor((labels.length - 1) / 2)).map((label) => `<text x="${xFor(label)}" y="${height - 10}" fill="#61758c" font-size="11" text-anchor="middle">${escapeHtml(label)}</text>`).join("");
    const legend = series.map((item, index) => `<div style="display:flex;align-items:center;gap:8px;"><span style="width:12px;height:12px;border-radius:999px;background:${palette[index % palette.length]};display:inline-block;"></span><small>${escapeHtml(item.label || `Series ${index + 1}`)}</small></div>`).join("");
    return `<div><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMinYMin meet">${yTicks}<line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerHeight}" stroke="#94a3b8" /><line x1="${margin.left}" y1="${margin.top + innerHeight}" x2="${margin.left + innerWidth}" y2="${margin.top + innerHeight}" stroke="#94a3b8" />${paths}${xTicks}</svg><div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;">${legend}</div></div>`;
  }

  function renderAnalysisPlotsMarkup(context) {
    if (!context) return '<div class="empty">No analysis plots available.</div>';
    if (context.mode === "trajectory_compare" || context.mode === "trajectory_compare_response") {
      const cohortA = context.cohort_a || {};
      const cohortB = context.cohort_b || {};
      const unit = context.unit ? ` (${context.unit})` : "";
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Trajectory Comparison${unit}</h3>${renderTrajectoryComparisonPlot([{ label: `Cohort A median`, points: cohortA.summary_points || [] }, { label: `Cohort B median`, points: cohortB.summary_points || [] }])}</div>`;
    }
    if (context.mode === "trajectory" || context.mode === "trajectory_response") {
      const unit = context.unit ? ` (${context.unit})` : "";
      const heading = context.treatment ? `Response to ${context.treatment}${unit}` : `Trajectory of ${context.measure || "measure"}${unit}`;
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>${escapeHtml(heading)}</h3>${renderTrajectoryPlot(context.patient_series || [], { label: context.treatment ? "Median response" : "Cohort median", points: context.summary_points || [] })}</div><div class="viz-card"><h3>Trajectory Coverage</h3>${renderBarChart([{ label: "Patients", value: Number(context.patient_count || 0) }, { label: "Summary points", value: Number((context.summary_points || []).length) }], "label", "value", "#2563eb")}</div>`;
    }
    if (context.mode === "survival_compare") {
      const cohortA = context.cohort_a || {};
      const cohortB = context.cohort_b || {};
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Kaplan-Meier Comparison</h3>${renderKaplanMeierPlot([{ label: `Cohort A (${cohortA.patient_count || 0} patients)`, points: cohortA.curve_points || [] }, { label: `Cohort B (${cohortB.patient_count || 0} patients)`, points: cohortB.curve_points || [] }])}</div><div class="viz-card"><h3>Cohort A Survival Summary</h3>${renderBarChart([{ label: "Patients", value: Number(cohortA.patient_count || 0) }, { label: "Events", value: Number(cohortA.event_count || 0) }, { label: "Censored", value: Number(cohortA.censored_count || 0) }], "label", "value", "#2563eb")}</div><div class="viz-card"><h3>Cohort B Survival Summary</h3>${renderBarChart([{ label: "Patients", value: Number(cohortB.patient_count || 0) }, { label: "Events", value: Number(cohortB.event_count || 0) }, { label: "Censored", value: Number(cohortB.censored_count || 0) }], "label", "value", "#0ea5e9")}</div>`;
    }
    if (context.mode === "survival") {
      return `<div class="viz-card" style="grid-column: 1 / -1;"><h3>Kaplan-Meier Curve</h3>${renderKaplanMeierPlot([{ label: `${context.measure || "Measure"} ${context.operator || ""} ${context.threshold || ""}`, points: context.curve_points || [] }])}</div><div class="viz-card"><h3>Event Summary</h3>${renderBarChart([{ label: "Patients", value: Number(context.patient_count || 0) }, { label: "Events", value: Number(context.event_count || 0) }, { label: "Censored", value: Number(context.censored_count || 0) }], "label", "value", "#2563eb")}</div><div class="viz-card"><h3>Median Time</h3>${renderBarChart([{ label: "Median days", value: Number(context.median_survival_days || 0) }], "label", "value", "#0ea5e9")}</div>`;
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
      return `<div class="viz-card"><h3>Cohort A Profile</h3>${renderBarChart(overviewItems.slice(0, 2), "label", "value", "#2563eb")}</div><div class="viz-card"><h3>Cohort B Profile</h3>${renderBarChart(overviewItems.slice(2), "label", "value", "#0ea5e9")}</div><div class="viz-card"><h3>Disease Differences</h3>${renderBarChart(diseaseDeltaItems, "label", "value", "#0ea5e9")}</div><div class="viz-card"><h3>Medication Differences</h3>${renderBarChart(medicationDeltaItems, "label", "value", "#7c3aed")}</div>`;
    }
    const diseaseItems = (context.top_diseases || []).slice(0, 8).map((item) => ({ label: item.disease, value: item.patient_count }));
    const medicationItems = (context.top_medications || []).slice(0, 8).map((item) => ({ label: item.medication, value: item.patient_count }));
    const periodItems = (context.timepoints_by_period || []).slice(0, 12).map((item) => ({ label: item.period, value: item.timepoint_count }));
    const visitItems = (context.visit_distribution || []).slice(0, 12).map((item) => ({ label: item.label, value: item.value }));
    return `<div class="viz-card"><h3>Top Diseases</h3>${renderBarChart(diseaseItems, "label", "value", "#0ea5e9")}</div><div class="viz-card"><h3>Top Medications</h3>${renderBarChart(medicationItems, "label", "value", "#2563eb")}</div><div class="viz-card"><h3>Timepoints Over Time</h3>${renderBarChart(periodItems, "label", "value", "#7c3aed")}</div><div class="viz-card"><h3>Visits Per Patient</h3>${renderBarChart(visitItems, "label", "value", "#059669")}</div>`;
  }

  function analysisIntentPresentation(intent) {
    const value = String(intent || "analysis");
    const labels = {
      analysis_deterministic: { label: "Cohort summary", title: "Deterministic cohort summary produced by the app." },
      analysis_compare: { label: "Cohort comparison", title: "Deterministic comparison between the selected cohorts." },
      analysis_molecular_expression: { label: "Molecular expression", title: "Deterministic molecular expression summary across the loaded molecular datasets." },
      analysis_molecular_medication_compare: { label: "Molecular by medication", title: "Deterministic molecular comparison aligned to medication-specific datasets." },
      analysis_survival: { label: "Kaplan-Meier analysis", title: "Deterministic Kaplan-Meier survival analysis." },
      analysis_survival_compare: { label: "Kaplan-Meier comparison", title: "Deterministic Kaplan-Meier comparison between two cohorts." },
      analysis_trajectory: { label: "Trajectory analysis", title: "Deterministic longitudinal trajectory analysis." },
      analysis_trajectory_compare: { label: "Trajectory comparison", title: "Deterministic trajectory comparison between two cohorts." },
      analysis_llm: { label: "LM interpretation", title: "LM Studio narrative interpretation grounded in the provided analysis context." },
      analysis_compare_llm: { label: "LM comparison", title: "LM Studio narrative comparison grounded in the provided cohort context." },
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
      chips.push(renderAnalysisBadge("LLM planned", "LM Studio translated the prompt into a constrained internal analysis plan."));
      chips.push(renderAnalysisBadge("Deterministic execution", "The app executed the planned analysis deterministically against local cohort data."));
      if (data.planner.model) chips.push(renderAnalysisBadge(data.planner.model, "LM Studio model used for analysis planning."));
      return chips;
    }
    chips.push(renderAnalysisBadge(data.source === "llm" ? "LM-based" : "Deterministic", data.source === "llm"
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
    if (!ids.length) return "Full cohort";
    const preview = ids.slice(0, 6).join(", ");
    const suffix = ids.length > 6 ? ` ... (+${ids.length - 6} more)` : "";
    return `${ids.length} IDs: ${preview}${suffix}`;
  }

  function renderAnalysisCompareMode() {
    if (!analysisCompareModeEl || !refs.analysisCompareFieldEl) return;
    refs.analysisCompareFieldEl.style.display = analysisCompareModeEl.checked ? "" : "none";
    callbacks.renderGlobalContext();
  }

  function analysisPromptRequestsPlots(prompt) {
    const lowered = String(prompt || "").toLowerCase();
    return ["trajectory", "response to", "kaplan", "survival", "plot", "plots", "chart", "charts", "graph", "graphs", "visualize", "visualise", "distribution", "distributions", "histogram", "bar plot", "line plot", "trend", "trends", "over time"].some((token) => lowered.includes(token));
  }

  function analysisPayloadHasPlots(payload) {
    const context = payload && payload.data ? payload.data.context : null;
    const mode = context && typeof context.mode === "string" ? context.mode : "";
    return ["trajectory", "trajectory_response", "trajectory_compare", "trajectory_compare_response", "survival", "survival_compare"].includes(mode);
  }

  function renderAnalysisThread() {
    renderAnalysisStarterPrompts();
    if (!state.analysisTurns.length) {
      analysisThreadEl.innerHTML = '<div class="empty">Run an analysis prompt to start a threaded analysis workspace.</div>';
      return;
    }
    analysisThreadEl.innerHTML = state.analysisTurns.map((turn) => {
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
      if (notable.length) contextParts.push(...notable);
      return `<article class="analysis-turn analysis-turn-assistant"><div class="analysis-turn-label">Analysis</div><div class="analysis-turn-meta">${getAnalysisProvenanceChips(turn.payload).join("")}</div><div class="analysis-turn-body">${renderQueryReply(turn.payload)}</div>${contextParts.length ? `<div class="analysis-turn-context"><p><strong>Context:</strong> ${escapeHtml(contextParts.join(" | "))}</p></div>` : ""}${turn.showPlots ? `<div class="analysis-plot-grid">${renderAnalysisPlotsMarkup(context)}</div>` : ""}<details class="query-section"><summary>Show analysis data</summary><pre>${escapeHtml(JSON.stringify(turn.payload.data, null, 2))}</pre></details></article>`;
    }).join("");
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
    const currentScope = analysisSelectedPatientIdsEl.value.trim();
    const compareScope = analysisCompareModeEl && analysisCompareModeEl.checked ? analysisCompareSelectedPatientIdsEl.value.trim() : "";
    const llmOnly = state.analysisExecutionMode === "llm_only";
    const showPlots = analysisPromptRequestsPlots(prompt);
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
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
          data_dir: refs.dataDirEl.value.trim() || refs.dataDirEl.value,
          selected_patient_ids: analysisSelectedPatientIdsEl.value.trim(),
          compare_mode: compareMode,
          compare_selected_patient_ids: compareScope,
          llm_only: llmOnly,
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
    runAnalysis,
  };
}
