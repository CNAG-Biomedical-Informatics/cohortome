// Chart-only module. Controllers retain requests, chat state and run execution.
export function createPhenoHeatmapChart({
  phenoHeatmapRecordCount,
  PHENO_HEATMAP_MAX_RECORDS,
  parseTsvLines,
  getEffectivePhenoCohortMetric,
  escapeHtml,
  displayIdentity,
}) {
  async function renderInteractivePhenoHeatmap(file) {
    const plotEl = document.getElementById('phenoHeatmapPlot');
    if (!plotEl) {
      return;
    }
    if (typeof window.Plotly === 'undefined') {
      plotEl.innerHTML =
        '<div class="empty">Interactive Plotly heatmap is unavailable in this browser.</div>';
      return;
    }
    try {
      const response = await fetch(file.url);
      if (!response.ok) {
        plotEl.innerHTML =
          '<div class="empty">Unable to load the cohort matrix for the heatmap.</div>';
        return;
      }
      const text = await response.text();
      const recordCount = phenoHeatmapRecordCount(text);
      if (recordCount > PHENO_HEATMAP_MAX_RECORDS) {
        plotEl.classList.remove('pheno-mds-plot');
        plotEl.innerHTML = `<div class="empty" role="status">Heatmap disabled: this matrix contains ${recordCount.toLocaleString('en-US')} records. The limit is 1,000 records because larger heatmaps are difficult to interpret. Select a smaller cohort to view a heatmap; the full matrix remains available to download.</div>`;
        const noteEl = document.getElementById('phenoHeatmapSelectionNote');
        if (noteEl) noteEl.textContent = '';
        return;
      }
      const rows = parseTsvLines(text);
      if (!rows || rows.length < 2) {
        plotEl.innerHTML =
          '<div class="empty">No matrix data were available for this heatmap.</div>';
        return;
      }
      const metric = getEffectivePhenoCohortMetric();
      const metricLabel = metric === 'jaccard' ? 'Jaccard similarity' : 'Hamming dissimilarity';
      const header = rows[0];
      const xLabels = header.slice(1);
      const body = rows.slice(1);
      const yLabels = body.map((row) => row[0]);
      const noteEl = document.getElementById('phenoHeatmapSelectionNote');
      if (noteEl) {
        noteEl.textContent = `Rendering ${yLabels.length} x ${xLabels.length} sample matrix. Plotly thins axis labels at this density; zoom or hover to inspect individual timepoints.`;
      }
      const zValues = body.map((row) =>
        row.slice(1).map((value) => {
          const numeric = Number(value);
          return Number.isFinite(numeric) ? numeric : null;
        }),
      );
      await window.CohortomeTheme.newPlot(
        plotEl,
        [
          {
            type: 'heatmap',
            x: xLabels,
            y: yLabels,
            z: zValues,
            text: yLabels.map((y) =>
              xLabels.map(
                (x) => `${escapeHtml(displayIdentity(y))} vs ${escapeHtml(displayIdentity(x))}`,
              ),
            ),
            colorscale: [
              [0.0, '#4575b4'],
              [0.5, '#ffffbf'],
              [1.0, '#d73027'],
            ],
            hoverongaps: false,
            hovertemplate: `<b>%{text}</b><br>${metricLabel} %{z:.4f}<extra></extra>`,
            colorbar: {
              title: metricLabel,
            },
          },
        ],
        {
          margin: { l: 100, r: 20, t: 10, b: 90 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(255,255,255,0.86)',
          dragmode: 'zoom',
          xaxis: {
            title: 'Reference / comparison IDs',
            tickangle: -40,
            tickvals: xLabels,
            ticktext: xLabels.map((id) => displayIdentity(id)),
            automargin: true,
          },
          yaxis: {
            title: 'Reference / comparison IDs',
            autorange: 'reversed',
            tickvals: yLabels,
            ticktext: yLabels.map((id) => displayIdentity(id)),
            automargin: true,
          },
        },
        {
          responsive: true,
          displaylogo: false,
        },
      );
    } catch (error) {
      plotEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : 'Unable to render the heatmap.')}</div>`;
    }
  }
  return { renderInteractivePhenoHeatmap };
}
