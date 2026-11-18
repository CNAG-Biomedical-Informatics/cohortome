// Chart-only module. Controllers retain requests, chat state and run execution.
export function createPhenoOrdinationChart({
  parseTsvLines,
  getPhenoMdsCohortInfo,
  renderPhenoCohortLegend,
  state,
  normalizePhenoSelectedRecordId,
  displayIdentity,
  normalizePhenoSelectedRecordIds,
  escapeHtml,
}) {
  async function renderInteractivePhenoMdsPlot(file, method = 'MDS') {
    const prefix = method === 'UMAP' ? 'phenoUmap' : 'phenoMds';
    const selectionKey = method === 'UMAP' ? 'selectedUmapRecordIds' : 'selectedMdsRecordIds';
    const plotEl = document.getElementById(prefix + 'Plot');
    const noteEl = document.getElementById(prefix + 'SelectionNote');
    if (!plotEl) {
      return;
    }
    if (typeof window.Plotly === 'undefined') {
      plotEl.innerHTML =
        '<div class="empty">Interactive Plotly view is unavailable in this browser.</div>';
      return;
    }
    try {
      const response = await fetch(file.url);
      if (!response.ok) {
        plotEl.innerHTML = '<div class="empty">Unable to load MDS coordinates.</div>';
        return;
      }
      const text = await response.text();
      const rows = parseTsvLines(text);
      if (!rows || rows.length < 2) {
        plotEl.innerHTML =
          '<div class="empty">No MDS coordinates were available for this run.</div>';
        return;
      }
      const header = rows[0];
      const recordIndex = header.indexOf('record_id');
      const patientIndex = header.indexOf('patient_id');
      const xIndex = header.indexOf('x');
      const yIndex = header.indexOf('y');
      if ([recordIndex, patientIndex, xIndex, yIndex].some((index) => index < 0)) {
        plotEl.innerHTML =
          '<div class="empty">MDS coordinate file is missing required columns.</div>';
        return;
      }
      const points = rows
        .slice(1)
        .map((row) => ({
          record_id: String(row[recordIndex] || '').trim(),
          patient_id: String(row[patientIndex] || '').trim(),
          x: Number(row[xIndex]),
          y: Number(row[yIndex]),
        }))
        .filter((item) => item.record_id && Number.isFinite(item.x) && Number.isFinite(item.y))
        .map((item) => ({
          ...item,
          cohort: getPhenoMdsCohortInfo(item.record_id),
        }));
      if (!points.length) {
        plotEl.innerHTML =
          '<div class="empty">No valid MDS coordinates were available for this run.</div>';
        return;
      }
      renderPhenoCohortLegend(
        prefix + 'CohortLegend',
        points.map((item) => item.record_id),
      );
      points.forEach((item) => {
        if (item.patient_id)
          state.projectionPatientIds.set(
            normalizePhenoSelectedRecordId(item.record_id),
            item.patient_id,
          );
      });
      const cohortGroups = new Map();
      points.forEach((item) => {
        if (!cohortGroups.has(item.cohort.key)) {
          cohortGroups.set(item.cohort.key, {
            label: item.cohort.label,
            color: item.cohort.color,
            points: [],
          });
        }
        cohortGroups.get(item.cohort.key).points.push(item);
      });
      const traces = Array.from(cohortGroups.values()).map((group) => ({
        type: 'scattergl',
        mode: 'markers+text',
        name: group.label,
        x: group.points.map((item) => item.x),
        y: group.points.map((item) => item.y),
        text: group.points.map((item) => displayIdentity(item.record_id)),
        customdata: group.points.map((item) => [
          item.record_id,
          item.patient_id,
          group.label,
          displayIdentity(item.record_id),
          displayIdentity(item.patient_id),
        ]),
        textposition: 'top center',
        textfont: {
          size: 12,
          color: window.CohortomeTheme.colors().ink,
        },
        hovertemplate:
          '<b>%{customdata[3]}</b><br>Patient %{customdata[4]}<br>%{customdata[2]}<br>x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>',
        marker: {
          size: 10,
          color: group.color,
          opacity: 0.88,
        },
        selected: {
          textfont: {
            color: '#991b1b',
            size: 13,
          },
          marker: {
            opacity: 1,
          },
        },
        unselected: {
          textfont: {
            color: 'rgba(15, 23, 42, 0.28)',
          },
          marker: {
            opacity: 0.22,
          },
        },
      }));
      await window.CohortomeTheme.newPlot(
        plotEl,
        traces,
        {
          margin: { l: 40, r: 20, t: 10, b: 40 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(255,255,255,0.86)',
          dragmode: 'lasso',
          showlegend: false,
          xaxis: { title: `${method} Coordinate 1`, zeroline: false },
          yaxis: { title: `${method} Coordinate 2`, zeroline: false },
        },
        {
          responsive: true,
          displaylogo: false,
          modeBarButtonsToRemove: ['autoScale2d'],
        },
      );
      const applySelectedPlotPoints = (selected) => {
        state[selectionKey] = normalizePhenoSelectedRecordIds(
          (Array.isArray(selected) ? selected : []).map((point) => {
            if (Array.isArray(point.customdata) && point.customdata[0]) {
              return String(point.customdata[0]).trim();
            }
            if (typeof point.text === 'string' && point.text.trim()) {
              return point.text.trim();
            }
            return '';
          }),
        );
        if (noteEl) {
          noteEl.textContent = state[selectionKey].length
            ? `Selected ${state[selectionKey].length} ${method} points.`
            : 'Select points with box or lasso to reuse them in Analysis.';
        }
      };
      plotEl.on('plotly_selected', (event) => {
        applySelectedPlotPoints(Array.isArray(event && event.points) ? event.points : []);
      });
      plotEl.on('plotly_click', (event) => {
        applySelectedPlotPoints(Array.isArray(event && event.points) ? event.points : []);
      });
      plotEl.on('plotly_deselect', () => {
        state[selectionKey] = [];
        if (noteEl) {
          noteEl.textContent = 'Select points with box or lasso to reuse them in Analysis.';
        }
      });
    } catch (error) {
      plotEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : 'Unable to render the MDS plot.')}</div>`;
    }
  }
  return { renderInteractivePhenoMdsPlot };
}
