import { patientInventoryMarkup } from '/static/js/patient_inventory.js';
import { modalityIcon, modalityLabel, modalityColor } from './modalities.js';

// Availability is dataset-scoped. Clinical properties are inspector details.
export function createTimelineUi({state, refs, helpers, callbacks}) {
  const {escapeHtml: esc, mountPlot, dashboardPlotLayout} = helpers;
  const {detailEl} = refs;
  let data = null, scopeKey = '', pending = null, generation = 0;
  let required = [], active = '';
  const modality = value => String(value || 'assay').toLowerCase() === 'olink' ? 'proteomics' : String(value || 'assay').toLowerCase();
  const label = value => value === 'imaging' ? 'Imaging-derived' : modalityLabel(value);
  const colour = value => modalityColor(value, true);
  const scope = () => state.currentDatasetIds.length === 1 ? state.currentDatasetIds[0]
    : 'scope--' + state.currentDatasetIds.slice().sort().join('--');
  const patientLabel = p => p.source_patient_id + ' · ' + p.dataset_label;
  const time = value => value && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
  const events = p => [
    ...(p.events || []).map(e => ({...e, modality: 'clinical', date: e.event_date || '', title: e.event_type || 'Clinical record'})),
    ...(p.samples || []).map(s => ({...s, modality: modality(s.modality), date: s.collection_date || '', title: s.assay || s.assay_id}))
  ];
  function reset() {
    generation++; pending?.abort(); pending = null; data = null; scopeKey = '';
    required = []; active = '';
  }
  window.addEventListener('cohortome:workspace-changing', reset);
  async function load(summary) {
    const key = scope();
    if (pending || !state.currentDatasetIds.length) return;
    if (scopeKey !== key) reset();
    scopeKey = key;
    const ticket = generation, controller = new AbortController();
    pending = controller;
    try {
      const response = await fetch('/patient-overview/timeline?' + new URLSearchParams({workspace:key}), {signal:controller.signal});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Timeline unavailable.');
      if (ticket !== generation || scope() !== key) return;
      data = payload;
      renderDashboardTimeline(summary);
    } catch (error) {
      if (ticket === generation && error.name !== 'AbortError') {
        const plot = document.getElementById('dashboard-plot-timeline');
        if (plot) plot.innerHTML = '<p>' + esc(error.message) + '</p><button type="button" id="timelineRetry">Retry</button>';
        document.getElementById('timelineRetry')?.addEventListener('click', () => load(summary));
      }
    } finally { if (pending === controller) pending = null; }
  }
  function inspect(p, event, summary) {
    active = p.patient_id;
    const rows = events(p);
    detailEl.classList.remove('empty');
    detailEl.innerHTML = '<div class="workspace-card"><h3>' + esc(patientLabel(p)) + '</h3>'
      + '<p>' + (p.events || []).length + ' clinical records · ' + (p.samples || []).length + ' linked assay entries</p>'
      + (event ? '<h4>' + esc(event.title) + '</h4><p>' + esc(event.date || 'Date not recorded') + '</p>' : '')
      + (event?.diagnosis ? '<p>' + esc(event.diagnosis) + '</p>' : '')
      + (event?.domains || []).map(d => '<p><strong>' + esc(d.label || d.key) + ':</strong> ' + (d.examples || []).map(esc).join(', ') + '</p>').join('')
      + '<h4>Available samples and assays</h4>'
      + ((p.samples || []).length ? patientInventoryMarkup(p.samples, esc) : '<p>No linked assay entries recorded.</p>')
      + '<details><summary>Clinical records (' + (p.events || []).length + ')</summary>'
      + rows.filter(e => e.modality === 'clinical').map(e => '<p>' + esc(e.date || 'Undated') + ' · ' + esc(e.title) + (e.diagnosis ? ' · ' + esc(e.diagnosis) : '') + '</p>').join('')
      + '</details></div>';
    renderDashboardTimeline(summary);
    detailEl.scrollIntoView({block:'nearest'});
  }
  function renderDashboardTimeline(summary) {
    const plot = document.getElementById('dashboard-plot-timeline');
    if (!plot) return;
    if (scopeKey !== scope()) reset();
    if (!data) { plot.textContent = 'Loading data availability…'; void load(summary); return; }
    const all = data.timelines || [];
    const datasets = new Map(all.map(p => [p.dataset_id, p.dataset_label]));
    const ds = document.getElementById('timelineDatasetFilter');
    ds.innerHTML = '<option value="">All workspace datasets</option>' + [...datasets].map(([id,name]) => '<option value="' + esc(id) + '">' + esc(name) + '</option>').join('');
    ds.value = state.timelineDatasetFilter || '';
    ds.onchange = () => {state.timelineDatasetFilter = ds.value; state.timelinePatientFilter = ''; state.timelinePage = 0; renderDashboardTimeline(summary);};
    const modalities = [...new Set(all.flatMap(p => events(p).map(e => e.modality)))].sort();
    function controls(id, values, change) {
      const el = document.getElementById(id);
      el.innerHTML = modalities.map(m => '<label class="dashboard-timeline-domain" style="--timeline-domain-color:' + colour(m) + '"><input type="checkbox" value="' + esc(m) + '"' + (values.includes(m) ? ' checked' : '') + '>' + modalityIcon(m) + '<span>' + esc(label(m)) + '</span></label>').join('');
      el.onchange = () => change([...el.querySelectorAll('input:checked')].map(i => i.value));
    }
    controls('timelineHasData', required, values => {required = values; state.timelinePage = 0; renderDashboardTimeline(summary);});
    const filtered = all.filter(p => (!state.timelineDatasetFilter || p.dataset_id === state.timelineDatasetFilter)
      && (!state.timelinePatientFilter || p.patient_id === state.timelinePatientFilter)
      && required.every(m => events(p).some(e => e.modality === m)));
    const pages = Math.max(1, Math.ceil(filtered.length / 40));
    state.timelinePage = Math.min(state.timelinePage || 0, pages - 1);
    const visible = filtered.slice(state.timelinePage * 40, (state.timelinePage + 1) * 40);
    document.getElementById('timelineScopeLabel').textContent = filtered.length + ' patients match · ' + all.length + ' in workspace';
    document.getElementById('timelinePageLabel').textContent = 'Page ' + (state.timelinePage + 1) + ' of ' + pages;
    for (const [id, delta] of [['timelinePrevious', -1], ['timelineNext', 1]]) {
      const button = document.getElementById(id);
      button.disabled = delta < 0 ? !state.timelinePage : state.timelinePage >= pages - 1;
      button.onclick = () => {state.timelinePage += delta; renderDashboardTimeline(summary);};
    }
    document.getElementById('timelineShowAll').onclick = () => {
      required = []; state.timelineDatasetFilter = ''; state.timelinePatientFilter = ''; state.timelinePage = 0; renderDashboardTimeline(summary);
    };
    document.getElementById('timelineWarnings').innerHTML = (data.warnings || []).length
      ? '<details><summary>Linkage limitations (' + data.warnings.length + ')</summary>' + data.warnings.map(w => '<p>' + esc(w) + '</p>').join('') + '</details>' : '';
    // This column remains visible for patients who have no dated observations.
    const table = document.getElementById('timelineAvailability');
    table.innerHTML = '<table class="dashboard-timeline-table"><thead><tr><th>Patient / dataset</th><th>Available data</th><th>Date not recorded</th></tr></thead><tbody>'
      + visible.map((p,i) => {
        const es = events(p);
        const badges = list => [...new Set(list.map(e => e.modality))].map(m => '<span class="pill" style="border-color:' + colour(m) + '">' + modalityIcon(m) + esc(label(m)) + '</span>').join(' ') || '—';
        return '<tr' + (active === p.patient_id ? ' class="is-inspected"' : '') + '><td><button type="button" class="query-chip" data-timeline-inspect="' + i + '">' + esc(patientLabel(p)) + '</button></td><td>' + badges(es) + '</td><td>' + badges(es.filter(e => time(e.date) === null)) + '</td></tr>';
      }).join('') + '</tbody></table>';
    table.querySelectorAll('[data-timeline-inspect]').forEach(b => {b.onclick = () => inspect(visible[Number(b.dataset.timelineInspect)], null, summary);});
    const points = visible.flatMap(p => events(p).filter(e => time(e.date) !== null).map(e => ({p,e})));
    if (!points.length) {plot.innerHTML = '<p class="empty">No dated observations for the displayed data types. Availability without dates is listed below.</p>'; return;}
    const traces = modalities.map(m => {
      const rows = points.filter(v => v.e.modality === m);
      return {type:'scatter', mode:'markers', name:label(m), x:rows.map(v => v.e.date), y:rows.map(v => v.p.patient_id),
        customdata:rows.map(v => points.indexOf(v)), text:rows.map(v => esc(patientLabel(v.p) + ' · ' + v.e.title)),
        marker:{color:colour(m), size:rows.map(v => v.p.patient_id === active ? 14 : 10), symbol:m === 'clinical' ? 'circle' : 'diamond'},
        hovertemplate:'%{text}<br>%{x}<extra></extra>'};
    }).filter(t => t.x.length);
    const spans = visible.map(p => ({p, dates: events(p).map(e => time(e.date)).filter(t => t !== null)})).filter(v => v.dates.length);
    const spanTrace = {type:'bar', orientation:'h', name:'Recorded span', showlegend:false,
      y:spans.map(v => v.p.patient_id), base:spans.map(v => new Date(Math.min(...v.dates)).toISOString()),
      x:spans.map(v => Math.max(...v.dates) - Math.min(...v.dates)),
      customdata:spans.map(v => v.p.patient_id), text:spans.map(v => esc(patientLabel(v.p))),
      marker:{color:'#cbd5e1', line:{color:'#64748b', width:spans.map(v => active === v.p.patient_id ? 2 : 0)}},
      hovertemplate:'%{text}<br>Span of recorded observations<extra></extra>'};
    mountPlot('dashboard-plot-timeline', [spanTrace, ...traces], dashboardPlotLayout({
      height:Math.max(280, visible.length * 24 + 100), margin:{t:35,r:15,b:45,l:160},
      xaxis:{type:'date', title:{text:'Recorded date'}},
      yaxis:{type:'category', categoryorder:'array', categoryarray:visible.map(p => p.patient_id), tickmode:'array',
        tickvals:visible.map(p => p.patient_id), ticktext:visible.map(p => esc(patientLabel(p))), autorange:'reversed', automargin:true},
      showlegend:true, legend:{orientation:'h'}, dragmode:'zoom'
    }), el => {el.on?.('plotly_click', event => {
      const id = event.points?.[0]?.customdata;
      const point = typeof id === 'number' ? points[id] : null;
      if (point) inspect(point.p, point.e, summary);
      else { const patient = visible.find(p => p.patient_id === id); if (patient) inspect(patient, null, summary); }
    });}, {displayModeBar:true, modeBarButtonsToRemove:['select2d','lasso2d']});
  }
  function timelinePanelMarkup() {
    return '<section class="section-card dashboard-timeline-card"><h3>Data availability over time</h3>'
      + '<p class="section-note">Find patients with particular data, then inspect when it was collected. Dates are recorded calendar dates, not aligned study visits. Imaging-derived means linked measurements, not DICOM studies.</p>'
      + '<div class="timeline-scope-controls"><strong id="timelineScopeLabel"></strong><label>Dataset <select id="timelineDatasetFilter"></select></label><button id="timelineShowAll" class="query-chip" type="button">Show all patients</button></div>'
      + '<h4>Has data</h4><p class="section-note">Patients must have every checked data type. Leave unchecked to include everyone.</p><div id="timelineHasData" class="dashboard-timeline-controls"></div>'
      + '<p class="section-note">Click a plot legend item to hide or show its markers. Grey bars span the earliest to latest recorded observations; they do not imply continuous monitoring.</p>'
      + '<div class="timeline-pagination"><button id="timelinePrevious" class="query-chip">Previous</button><span id="timelinePageLabel"></span><button id="timelineNext" class="query-chip">Next</button></div>'
      + '<div id="timelineWarnings"></div><div id="dashboard-plot-timeline" class="dashboard-plot-frame"></div>'
      + '<div id="timelineAvailability" class="dashboard-timeline-table-wrap"></div>'
      + '<p class="section-note">Click a marker or patient to inspect. Availability is based on declared links; missing entries do not prove an assay was never performed. No dates are inferred.</p></section>';
  }
  return {renderDashboardTimeline, timelinePanelMarkup};
}
