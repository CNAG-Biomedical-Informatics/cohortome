// Chart-only module. Controllers retain requests, chat state and run execution.
export function createAnalysisSeries({
  ANALYSIS_PLOT_COLORS,
  escapeHtml,
  rankedQuantitativeAssayResults,
  finiteAnalysisNumber,
}) {
  function basePlotLayout(overrides) {
    return {
      margin: { t: 28, r: 24, b: 84, l: 56 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#f8fbff',
      font: { family: 'inherit', color: '#132238', size: 12 },
      xaxis: {
        automargin: true,
        gridcolor: 'rgba(148,163,184,0.2)',
        zeroline: false,
        linecolor: '#cbd5e1',
        tickfont: { color: '#61758c' },
        title: { font: { color: '#61758c', size: 12 } },
      },
      yaxis: {
        automargin: true,
        gridcolor: 'rgba(148,163,184,0.2)',
        zeroline: false,
        linecolor: '#cbd5e1',
        tickfont: { color: '#61758c' },
        title: { font: { color: '#61758c', size: 12 } },
      },
      legend: {
        orientation: 'h',
        yanchor: 'bottom',
        y: 1.02,
        xanchor: 'left',
        x: 0,
      },
      hoverlabel: { bgcolor: '#132238', font: { color: '#f8fafc' } },
      ...overrides,
    };
  }

  function buildHorizontalBar(items, labelKey, valueKey, color) {
    return {
      traces: [
        {
          type: 'bar',
          orientation: 'h',
          y: items.map((item) => item[labelKey]),
          x: items.map((item) => Number(item[valueKey] || 0)),
          marker: { color, line: { color, width: 1 } },
          hovertemplate: '%{y}: %{x}<extra></extra>',
        },
      ],
      layout: basePlotLayout({
        margin: { t: 18, r: 24, b: 36, l: 140 },
      }),
    };
  }

  function buildKaplanMeierPlot(seriesList) {
    const series = (Array.isArray(seriesList) ? seriesList : []).filter(
      (item) => Array.isArray(item.points) && item.points.length,
    );
    const traces = series.map((item, index) => ({
      type: 'scatter',
      mode: 'lines',
      name: item.label || `Series ${index + 1}`,
      meta: { cohortome_group: index },
      line: {
        color: ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
        width: 3,
        shape: 'hv',
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
          title: {
            text: 'Days since first dated observation of the selected measure',
            font: { color: '#61758c', size: 12 },
          },
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: 'Event-free probability', font: { color: '#61758c', size: 12 } },
          tickformat: '.0%',
          range: [0, 1],
        },
      }),
    };
  }

  function buildTrajectoryPlot(seriesList, summarySeries, xAxisTitle) {
    const patientSeries = (Array.isArray(seriesList) ? seriesList : []).filter(
      (item) => Array.isArray(item.points) && item.points.length,
    );
    const summary =
      summarySeries && Array.isArray(summarySeries.points) ? summarySeries.points : [];
    const labels = Array.from(
      new Set(
        patientSeries
          .flatMap((item) => item.points.map((point) => String(point.x_label || point.x || '')))
          .concat(summary.map((point) => String(point.x_label || point.x || ''))),
      ),
    );
    const traces = patientSeries.slice(0, 12).map((item, index) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name: item.label || `Patient ${index + 1}`,
      meta: { cohortome_group: index },
      showlegend: false,
      opacity: 0.35,
      line: {
        color: ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
        width: 1.5,
      },
      marker: { size: 5 },
      x: item.points.map((point) => String(point.x_label || point.x || '')),
      y: item.points.map((point) => Number(point.value || 0)),
      hovertemplate: '%{x}<br>%{y}<extra></extra>',
    }));
    traces.push({
      type: 'scatter',
      mode: 'lines+markers',
      name: summarySeries.label || 'Cohort median',
      line: { color: '#1d4ed8', width: 3 },
      marker: { size: 7, color: '#1d4ed8' },
      x: summary.map((point) => String(point.x_label || point.x || '')),
      y: summary.map((point) => Number(point.value || 0)),
      hovertemplate: `${escapeHtml(summarySeries.label || 'Cohort median')}<br>%{x}<br>%{y}<extra></extra>`,
    });
    return {
      traces,
      layout: basePlotLayout({
        margin: { t: 28, r: 24, b: 112, l: 56 },
        xaxis: {
          ...basePlotLayout().xaxis,
          type: 'category',
          categoryorder: 'array',
          categoryarray: labels,
          tickangle: -35,
          title: {
            text: xAxisTitle || 'Days since first dated observation',
            font: { color: '#61758c', size: 12 },
          },
        },
      }),
    };
  }

  function buildTrajectoryComparisonPlot(seriesList, xAxisTitle) {
    const series = (Array.isArray(seriesList) ? seriesList : []).filter(
      (item) => Array.isArray(item.points) && item.points.length,
    );
    const labels = Array.from(
      new Set(
        series.flatMap((item) =>
          item.points.map((point) => String(point.x_label || point.x || '')),
        ),
      ),
    );
    const traces = series.map((item, index) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name: item.label || `Series ${index + 1}`,
      showlegend: item.showLegend !== false,
      meta: { cohortome_group: index },
      opacity: item.opacity !== undefined ? item.opacity : 1,
      line: {
        color: item.lineColor || ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
        width: item.lineWidth || 3,
      },
      marker: {
        size: item.markerSize || 7,
        color: item.lineColor || ANALYSIS_PLOT_COLORS[index % ANALYSIS_PLOT_COLORS.length],
      },
      x: item.points.map((point) => String(point.x_label || point.x || '')),
      y: item.points.map((point) => Number(point.value || 0)),
      hovertemplate: `${escapeHtml(item.label || `Series ${index + 1}`)}<br>%{x}<br>%{y}<extra></extra>`,
    }));
    return {
      traces,
      layout: basePlotLayout({
        margin: { t: 28, r: 24, b: 112, l: 56 },
        xaxis: {
          ...basePlotLayout().xaxis,
          type: 'category',
          categoryorder: 'array',
          categoryarray: labels,
          tickangle: -35,
          title: {
            text: xAxisTitle || 'Days since first dated observation',
            font: { color: '#61758c', size: 12 },
          },
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
          lineColor: '#2563eb',
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
          lineColor: '#dc2626',
          opacity: 0.28,
          lineWidth: 1.4,
          markerSize: 4,
          showLegend: false,
        });
      });
    }

    output.push({
      label: 'Cohort A median',
      points: cohortA.summary_points || [],
      lineColor: '#1d4ed8',
      opacity: 1,
      lineWidth: 3,
      markerSize: 7,
      showLegend: true,
    });
    output.push({
      label: 'Cohort B median',
      points: cohortB.summary_points || [],
      lineColor: '#b91c1c',
      opacity: 1,
      lineWidth: 3,
      markerSize: 7,
      showLegend: true,
    });
    return output;
  }

  function buildExploratoryVolcanoPlot(points, comparisonLabel) {
    const rows = (Array.isArray(points) ? points : []).filter(
      (item) => item && item.gene_id !== undefined,
    );
    const colors = rows.map((item) => {
      const log2fc = Number(item.log2_fold_change || 0);
      const negLog10P = Number(item.neg_log10_p || 0);
      const significant = negLog10P >= 1.3;
      const largeEffect = Math.abs(log2fc) >= 1;
      if (!(significant && largeEffect)) return '#94a3b8';
      return log2fc > 0 ? '#dc2626' : '#2563eb';
    });
    return {
      traces: [
        {
          type: 'scatter',
          mode: 'markers',
          name: comparisonLabel || 'Exploratory comparison',
          x: rows.map((item) => Number(item.log2_fold_change || 0)),
          y: rows.map((item) => Number(item.neg_log10_p || 0)),
          text: rows.map((item) => String(item.gene_id || '')),
          customdata: rows.map((item) => [
            String(item.gene_id || ''),
            Number(item.mean_log2_cpm_a || 0),
            Number(item.mean_log2_cpm_b || 0),
            Number(item.p_value || 1),
          ]),
          marker: {
            size: 8,
            color: colors,
            opacity: 0.8,
          },
          hovertemplate:
            'Gene: %{customdata[0]}<br>log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<br>Mean A: %{customdata[1]:.2f}<br>Mean B: %{customdata[2]:.2f}<br>p: %{customdata[3]:.3g}<extra></extra>',
        },
      ],
      layout: basePlotLayout({
        xaxis: {
          ...basePlotLayout().xaxis,
          title: { text: 'Exploratory log2 fold change', font: { color: '#61758c', size: 12 } },
          zeroline: true,
          zerolinecolor: 'rgba(148,163,184,0.35)',
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: 'Exploratory -log10(p)', font: { color: '#61758c', size: 12 } },
        },
      }),
    };
  }

  function buildDifferentialExpressionVolcanoPlot(points, datasetName) {
    const rows = (Array.isArray(points) ? points : []).filter(
      (item) => item && item.gene_id !== undefined,
    );
    const colors = rows.map((item) => {
      const adjP = Number(item.adj_p_value || 1);
      return adjP < 0.05 ? '#d9485f' : '#94a3b8';
    });
    const topHits = rows
      .slice()
      .sort((left, right) => {
        const leftAdj = Number(left.adj_p_value || 1);
        const rightAdj = Number(right.adj_p_value || 1);
        if (leftAdj !== rightAdj) return leftAdj - rightAdj;
        return (
          Math.abs(Number(right.log2_fold_change || 0)) -
          Math.abs(Number(left.log2_fold_change || 0))
        );
      })
      .slice(0, 5);
    return {
      traces: [
        {
          type: 'scatter',
          mode: 'markers',
          name: datasetName || 'Differential expression',
          x: rows.map((item) => Number(item.log2_fold_change || 0)),
          y: rows.map((item) => Number(item.neg_log10_p || 0)),
          text: rows.map((item) => String(item.gene_id || '')),
          customdata: rows.map((item) => [
            String(item.gene_id || ''),
            Number(item.p_value || 1),
            Number(item.adj_p_value || 1),
          ]),
          marker: {
            size: 8,
            color: colors,
            opacity: 0.82,
          },
          hovertemplate:
            'Gene: %{customdata[0]}<br>log2FC: %{x:.3f}<br>-log10(p): %{y:.3f}<br>p: %{customdata[1]:.3g}<br>adj p: %{customdata[2]:.3g}<extra></extra>',
        },
        {
          type: 'scatter',
          mode: 'text',
          name: 'Top hits',
          x: topHits.map((item) => Number(item.log2_fold_change || 0)),
          y: topHits.map((item) => Number(item.neg_log10_p || 0)),
          text: topHits.map((item) => String(item.gene_id || '')),
          textposition: 'top center',
          textfont: { color: '#111827', size: 11 },
          hoverinfo: 'skip',
          showlegend: false,
        },
      ],
      layout: basePlotLayout({
        xaxis: {
          ...basePlotLayout().xaxis,
          title: { text: 'log2 fold change', font: { color: '#61758c', size: 12 } },
          zeroline: true,
          zerolinecolor: '#475569',
          zerolinewidth: 1,
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: '-log10(p-value)', font: { color: '#61758c', size: 12 } },
        },
        shapes: [
          {
            type: 'line',
            x0: 0,
            x1: 0,
            y0: 0,
            y1: 1,
            xref: 'x',
            yref: 'paper',
            line: { color: '#475569', width: 1, dash: 'dot' },
          },
        ],
      }),
    };
  }

  function buildDifferentialExpressionHeatmap(rows, datasetName) {
    const matrixRows = Array.isArray(rows)
      ? rows.filter((item) => item && Object.keys(item).length)
      : [];
    const sampleNames = matrixRows.length
      ? Object.keys(matrixRows[0]).filter((key) => key !== 'gene_id')
      : [];
    const topMargin = 32;
    const bottomMargin = 120;
    return {
      traces: [
        {
          type: 'heatmap',
          x: sampleNames,
          y: matrixRows.map((item) => String(item.gene_id || '')),
          z: matrixRows.map((item) =>
            sampleNames.map((sample) => {
              const value = Number(item[sample]);
              return Number.isFinite(value) ? value : null;
            }),
          ),
          colorscale: [
            [0, '#2563eb'],
            [0.5, '#f8fafc'],
            [1, '#dc2626'],
          ],
          zmid: 0,
          showscale: false,
          hovertemplate: 'Gene: %{y}<br>Sample: %{x}<br>Scaled expression: %{z:.2f}<extra></extra>',
        },
      ],
      layout: basePlotLayout({
        margin: { t: topMargin, r: 120, b: bottomMargin, l: 24 },
        title: datasetName
          ? { text: datasetName, font: { color: '#61758c', size: 12 } }
          : undefined,
        xaxis: {
          ...basePlotLayout().xaxis,
          tickangle: -35,
          side: 'bottom',
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          automargin: true,
          side: 'right',
        },
      }),
    };
  }

  function buildHallmarkPathwayPlot(rows, datasetName) {
    const rankedRows = (Array.isArray(rows) ? rows : [])
      .filter((item) => item && item.pathway !== undefined)
      .map((item) => ({
        pathway: String(item.display_label || item.pathway || ''),
        nes: Number(item.NES || 0),
        padj: Number(item.padj || 1),
      }))
      .filter((item) => item.pathway);
    const plotRows = rankedRows.slice(0, 20).reverse();
    const colors = plotRows.map((item) => (item.nes >= 0 ? '#2563eb' : '#d9485f'));
    return {
      traces: [
        {
          type: 'bar',
          orientation: 'h',
          y: plotRows.map((item) => item.pathway),
          x: plotRows.map((item) => item.nes),
          marker: { color: colors },
          customdata: plotRows.map((item) => [item.padj]),
          hovertemplate:
            'Pathway: %{y}<br>NES: %{x:.3f}<br>adj p: %{customdata[0]:.3g}<extra></extra>',
        },
      ],
      layout: basePlotLayout({
        margin: { t: 28, r: 24, b: 56, l: 220 },
        title: datasetName
          ? { text: datasetName, font: { color: '#61758c', size: 12 } }
          : undefined,
        xaxis: {
          ...basePlotLayout().xaxis,
          title: {
            text: 'Normalized enrichment score (NES)',
            font: { color: '#61758c', size: 12 },
          },
          zeroline: true,
          zerolinecolor: '#475569',
          zerolinewidth: 1,
        },
      }),
    };
  }

  function buildQuantitativeAssayWilcoxonPlot(results, assayLabel) {
    const plotRows = rankedQuantitativeAssayResults(results)
      .map((item) => ({
        feature: String(item.feature_id || '').trim(),
        effect: finiteAnalysisNumber(item.rank_biserial_effect),
        adjustedP: finiteAnalysisNumber(item.adj_p_value),
        cohortAN: finiteAnalysisNumber(item.cohort_a_n),
        cohortBN: finiteAnalysisNumber(item.cohort_b_n),
      }))
      .filter(
        (item) => item.feature && Number.isFinite(item.effect) && Number.isFinite(item.adjustedP),
      );
    const plottedRows = plotRows.map((item) => ({
      ...item,
      negativeLogAdjustedP: -Math.log10(Math.max(item.adjustedP, 1e-300)),
    }));
    const labeledFeatures = new Set(plottedRows.slice(0, 12).map((item) => item.feature));
    return {
      traces: [
        {
          type: 'scatter',
          mode: 'markers+text',
          x: plottedRows.map((item) => item.effect),
          y: plottedRows.map((item) => item.negativeLogAdjustedP),
          text: plottedRows.map((item) => (labeledFeatures.has(item.feature) ? item.feature : '')),
          textposition: 'top center',
          textfont: { color: '#334155', size: 10 },
          cliponaxis: false,
          marker: {
            color: plottedRows.map((item) => (item.adjustedP < 0.05 ? '#dc2626' : '#2563eb')),
            size: plottedRows.map((item) => (item.adjustedP < 0.05 ? 11 : 9)),
            opacity: 0.82,
            line: { color: '#ffffff', width: 1 },
          },
          customdata: plottedRows.map((item) => [
            item.feature,
            item.adjustedP,
            item.cohortAN,
            item.cohortBN,
          ]),
          hovertemplate:
            'Feature: %{customdata[0]}<br>Rank-biserial effect: %{x:.3f}<br>BH q: %{customdata[1]:.3g}<br>N A: %{customdata[2]}<br>N B: %{customdata[3]}<extra></extra>',
          showlegend: false,
        },
      ],
      layout: basePlotLayout({
        margin: { t: 54, r: 36, b: 70, l: 72 },
        title: assayLabel ? { text: assayLabel, font: { color: '#61758c', size: 12 } } : undefined,
        xaxis: {
          ...basePlotLayout().xaxis,
          title: {
            text: 'Rank-biserial effect (Cohort A - Cohort B)',
            font: { color: '#61758c', size: 12 },
          },
          range: [-1.1, 1.1],
          zeroline: true,
          zerolinecolor: '#475569',
          zerolinewidth: 1,
        },
        yaxis: {
          ...basePlotLayout().yaxis,
          title: { text: '-log10(BH q)', font: { color: '#61758c', size: 12 } },
          rangemode: 'tozero',
        },
        shapes: [
          {
            type: 'line',
            x0: -1.1,
            x1: 1.1,
            y0: -Math.log10(0.05),
            y1: -Math.log10(0.05),
            line: { color: '#d97706', width: 1, dash: 'dot' },
          },
        ],
        annotations: [
          {
            x: 1.08,
            y: -Math.log10(0.05),
            text: 'BH q = 0.05',
            showarrow: false,
            xanchor: 'right',
            yanchor: 'bottom',
            font: { color: '#92400e', size: 10 },
          },
        ],
      }),
    };
  }
  return {
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
  };
}
