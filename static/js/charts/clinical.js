// Chart-only module. Controllers retain requests, chat state and run execution.
export function createClinicalCharts({
  clinicalSexCounts,
  clinicalSexColor,
  formatNumber,
  clinicalRepresentation,
}) {
  function plotlyAvailable() {
    return (
      typeof window !== 'undefined' && window.Plotly && typeof window.Plotly.newPlot === 'function'
    );
  }

  function dashboardPlotConfig() {
    return {
      displayModeBar: false,
      displaylogo: false,
      responsive: true,
    };
  }

  function dashboardPlotLayout(overrides) {
    return {
      margin: { t: 24, r: 18, b: 56, l: 56 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#f8fbff',
      font: { family: 'inherit', color: '#132238', size: 12 },
      xaxis: {
        automargin: true,
        gridcolor: 'rgba(148,163,184,0.2)',
        zeroline: false,
        linecolor: '#cbd5e1',
        tickfont: { color: '#61758c' },
      },
      yaxis: {
        automargin: true,
        gridcolor: 'rgba(148,163,184,0.2)',
        zeroline: false,
        linecolor: '#cbd5e1',
        tickfont: { color: '#61758c' },
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

  function mountPlot(targetId, traces, layout, afterPlot, configOverrides = {}) {
    const el = document.getElementById(targetId);
    if (!el) return;
    if (!plotlyAvailable()) {
      el.innerHTML = '<div class="empty">Plot rendering unavailable.</div>';
      return;
    }
    const plotResult = window.CohortomeTheme.newPlot(el, traces, layout, {
      ...dashboardPlotConfig(),
      ...configOverrides,
    });
    if (typeof afterPlot === 'function') {
      Promise.resolve(plotResult)
        .then(() => afterPlot(el))
        .catch(() => {});
    }
    window.requestAnimationFrame(() => {
      if (
        window.Plotly &&
        window.Plotly.Plots &&
        typeof window.Plotly.Plots.resize === 'function'
      ) {
        window.Plotly.Plots.resize(el);
      }
    });
  }

  function normalizeRankedItems(items, labelKey) {
    return (Array.isArray(items) ? items : [])
      .map((item) => {
        if (Array.isArray(item)) {
          return { label: String(item[0] || 'Unknown'), value: Number(item[1] || 0) };
        }
        return {
          label: String(item[labelKey] || item.label || 'Unknown'),
          value: Number(item.patient_count || item.value || 0),
        };
      })
      .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  }

  function renderMeasurementDistributions(datasets, selected) {
    const bounds = selected.sources.flatMap(({ row }) =>
      (row.distribution || []).flatMap((bin) => [bin.low, bin.high]),
    );
    const low = bounds.length ? Math.min(...bounds) : 0;
    const high = bounds.length ? Math.max(...bounds) : 0;
    datasets.forEach((dataset, index) => {
      const row = selected.sources.find((source) => source.dataset === dataset)?.row;
      if (!row) return;
      const bins = row.distribution || [];
      const target = `clinical-distribution-${index}`;
      if (!bins.length) return;
      const constant = bins.length === 1 && bins[0].low === bins[0].high;
      const numeric = (value) =>
        Number(value).toLocaleString(undefined, { maximumSignificantDigits: 6 });
      mountPlot(
        target,
        [
          {
            type: 'bar',
            x: bins.map((bin) => bin.low / 2 + bin.high / 2),
            y: bins.map((bin) => bin.count),
            ...(constant ? {} : { width: bins.map((bin) => bin.high - bin.low) }),
            customdata: bins.map((bin, i) =>
              constant
                ? numeric(bin.low)
                : `[${numeric(bin.low)}, ${numeric(bin.high)}${i === bins.length - 1 ? ']' : ')'}`,
            ),
            marker: { color: '#3b82f6', line: { color: 'rgba(255,255,255,.5)', width: 1 } },
            meta: { cohortome_group: 0 },
            hovertemplate: '%{customdata}<br>%{y} patients<extra></extra>',
          },
        ],
        dashboardPlotLayout({
          margin: { t: 12, r: 16, b: 48, l: 48 },
          bargap: 0.02,
          xaxis: {
            ...dashboardPlotLayout().xaxis,
            title: { text: selected.unit || 'Recorded value' },
            ...(low < high
              ? { range: [low, high] }
              : { tickvals: [low], ticktext: [numeric(low)] }),
          },
          yaxis: {
            ...dashboardPlotLayout().yaxis,
            title: { text: 'Patients' },
            rangemode: 'tozero',
            tickformat: ',d',
          },
          ...(constant
            ? {
                annotations: [
                  {
                    text: 'All measured patients have the same value',
                    x: 0.5,
                    y: 1.08,
                    xref: 'paper',
                    yref: 'paper',
                    showarrow: false,
                    font: { size: 10 },
                  },
                ],
              }
            : {}),
        }),
      );
    });
  }

  function renderDashboardCharts(summary) {
    const sexCounts = summary && summary.sex_counts ? summary.sex_counts : {};
    const visitDistribution =
      summary && summary.visit_distribution ? summary.visit_distribution : {};
    const topDiseases = normalizeRankedItems(summary && summary.top_diseases, 'disease').slice(
      0,
      8,
    );
    const topMedications = normalizeRankedItems(
      summary && summary.top_medications
        ? summary.top_medications
        : summary && summary.top_treatments,
      'medication',
    ).slice(0, 8);
    const diseaseMedicationMatrix =
      summary && summary.disease_medication_matrix ? summary.disease_medication_matrix : {};

    const sexEntries = clinicalSexCounts(sexCounts);
    const sexTotal = sexEntries.reduce((total, [, count]) => total + count, 0);
    const sexColors = sexEntries.map(([label], index) => clinicalSexColor(label, index));
    // Empty plots should explain absence, rather than resemble a rendering failure.
    for (const [id, present, label] of [
      ['sex', sexEntries.length, 'sex values'],
      ['visits', Object.keys(visitDistribution).length, 'clinical records'],
      ['diseases', topDiseases.length, 'diagnoses'],
      ['medications', topMedications.length, 'treatments'],
      [
        'disease-medication',
        diseaseMedicationMatrix.values?.length,
        'linked diagnoses and treatments',
      ],
    ]) {
      const frame = document.getElementById(`dashboard-plot-${id}`);
      if (frame && !present)
        frame.innerHTML = `<div class="clinical-chart-empty">No ${label} recorded in this view.</div>`;
    }
    if (sexEntries.length) {
      mountPlot(
        'dashboard-plot-sex',
        [
          {
            type: 'pie',
            hole: 0.74,
            sort: false,
            direction: 'clockwise',
            rotation: 90,
            labels: sexEntries.map(([label]) => label),
            values: sexEntries.map(([, count]) => count),
            marker: { colors: sexColors },
            textinfo: 'none',
            hovertemplate: '%{label}<br>%{value} patients · %{percent}<extra></extra>',
          },
        ],
        dashboardPlotLayout({
          margin: { t: 8, r: 8, b: 8, l: 8 },
          annotations: [
            {
              x: 0.5,
              y: 0.5,
              xref: 'paper',
              yref: 'paper',
              showarrow: false,
              text: `<b>${formatNumber(sexTotal)}</b><br><span style="font-size:11px">patients</span>`,
              font: { size: 26 },
            },
          ],
          showlegend: false,
        }),
      );
    }

    const visitEntries = Object.entries(visitDistribution);
    const snapshotRepresentation = clinicalRepresentation(summary) === 'snapshot';
    if (visitEntries.length) {
      mountPlot(
        'dashboard-plot-visits',
        [
          {
            type: 'bar',
            x: visitEntries.map(([label]) => label),
            y: visitEntries.map(([, value]) => Number(value || 0)),
            marker: { color: '#3b82f6' },
            text: visitEntries.map(([, count]) => formatNumber(count)),
            textposition: 'outside',
            cliponaxis: false,
            hovertemplate: snapshotRepresentation
              ? '%{x} visits: %{y}<extra></extra>'
              : '%{x} records: %{y}<extra></extra>',
          },
        ],
        dashboardPlotLayout({
          xaxis: {
            ...dashboardPlotLayout().xaxis,
            title: {
              text: snapshotRepresentation
                ? 'Visits per patient bucket'
                : 'Clinical records per patient',
              font: { color: '#61758c', size: 12 },
            },
          },
          yaxis: {
            ...dashboardPlotLayout().yaxis,
            title: { text: 'Patients', font: { color: '#61758c', size: 12 } },
          },
        }),
      );
    }

    if (topDiseases.length) {
      mountPlot(
        'dashboard-plot-diseases',
        [
          {
            type: 'bar',
            orientation: 'h',
            y: topDiseases.map((item) => item.label),
            x: topDiseases.map((item) => item.value),
            meta: { cohortome_group: 0 },
            marker: { color: '#2563eb' },
            text: topDiseases.map((item) => formatNumber(item.value)),
            textposition: 'outside',
            cliponaxis: false,
            hovertemplate: '%{y}<br>%{x} patients<extra></extra>',
          },
        ],
        dashboardPlotLayout({
          margin: { t: 12, r: 45, b: 40, l: 155 },
          xaxis: {
            ...dashboardPlotLayout().xaxis,
            title: { text: 'Patients' },
            rangemode: 'tozero',
          },
          yaxis: { ...dashboardPlotLayout().yaxis, autorange: 'reversed', showgrid: false },
          bargap: 0.35,
        }),
      );
    }

    if (topMedications.length) {
      mountPlot(
        'dashboard-plot-medications',
        [
          {
            type: 'bar',
            orientation: 'h',
            y: topMedications.map((item) => item.label),
            x: topMedications.map((item) => item.value),
            meta: { cohortome_group: 1 },
            marker: { color: '#0d9488' },
            text: topMedications.map((item) => formatNumber(item.value)),
            textposition: 'outside',
            cliponaxis: false,
            hovertemplate: '%{y}<br>%{x} patients<extra></extra>',
          },
        ],
        dashboardPlotLayout({
          margin: { t: 12, r: 45, b: 40, l: 155 },
          xaxis: {
            ...dashboardPlotLayout().xaxis,
            title: { text: 'Patients' },
            rangemode: 'tozero',
          },
          yaxis: { ...dashboardPlotLayout().yaxis, autorange: 'reversed', showgrid: false },
          bargap: 0.35,
        }),
      );
    }

    const matrixDiseases = Array.isArray(diseaseMedicationMatrix.diseases)
      ? diseaseMedicationMatrix.diseases
      : [];
    const matrixMedications = Array.isArray(diseaseMedicationMatrix.medications)
      ? diseaseMedicationMatrix.medications
      : [];
    const matrixValues = Array.isArray(diseaseMedicationMatrix.values)
      ? diseaseMedicationMatrix.values
      : [];
    if (matrixDiseases.length && matrixMedications.length && matrixValues.length) {
      mountPlot(
        'dashboard-plot-disease-medication',
        [
          {
            type: 'heatmap',
            x: matrixMedications,
            y: matrixDiseases,
            z: matrixValues,
            colorscale: [
              [0, '#eff6ff'],
              [0.35, '#bfdbfe'],
              [0.65, '#60a5fa'],
              [1, '#1d4ed8'],
            ],
            hovertemplate: 'Disease: %{y}<br>Medication: %{x}<br>Patients: %{z}<extra></extra>',
            colorbar: { title: 'Patients' },
          },
        ],
        dashboardPlotLayout({
          margin: { t: 16, r: 20, b: 90, l: 160 },
          xaxis: {
            ...dashboardPlotLayout().xaxis,
            tickangle: -25,
            title: { text: 'Medication', font: { color: '#61758c', size: 12 } },
          },
          yaxis: {
            ...dashboardPlotLayout().yaxis,
            title: { text: 'Disease', font: { color: '#61758c', size: 12 } },
            autorange: 'reversed',
          },
        }),
      );
    }
  }
  return { dashboardPlotLayout, mountPlot, renderMeasurementDistributions, renderDashboardCharts };
}
