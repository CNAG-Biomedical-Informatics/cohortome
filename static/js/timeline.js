import { patientInventoryMarkup } from '/static/js/patient_inventory.js';
import { modalityIcon, modalityLabel, modalityColor } from './modalities.js';

// Availability is dataset-scoped. Clinical properties are inspector details.
export function createTimelineUi({state, refs, helpers, callbacks}) {
  const {escapeHtml: esc, mountPlot, dashboardPlotLayout} = helpers;
  const {detailEl} = refs;
  let data = null, scopeKey = '', pending = null, generation = 0;
  let required = [], active = '';
  let timeMode = '';
  let inspection = 0;
  const modality = value => String(value || 'assay').toLowerCase() === 'olink' ? 'proteomics' : String(value || 'assay').toLowerCase();
  const label = value => value === 'imaging' ? 'Imaging-derived' : modalityLabel(value);
  const colour = value => modalityColor(value, true);
  const scope = () => state.currentDatasetIds.length === 1 ? state.currentDatasetIds[0]
    : 'scope--' + state.currentDatasetIds.slice().sort().join('--');
  const patientLabel = p => p.source_patient_id + ' · ' + p.dataset_label;
  const time = value => value && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
  const relativeTime = e => typeof e.days_from_baseline === 'number' && Number.isFinite(e.days_from_baseline) ? e.days_from_baseline : null;
  const coordinate = e => timeMode === 'relative' ? relativeTime(e) : time(e.date);
  const timeLabel = e => e.date || (relativeTime(e) !== null ? 'Day ' + relativeTime(e) + ' from study baseline' : 'Time not recorded');
  const events = p => [
    ...(p.events || []).map(e => ({...e, modality: 'clinical', date: e.event_date || '', title: e.event_type || 'Clinical record'})),
    ...(p.samples || []).map(s => ({...s, modality: modality(s.modality), date: s.collection_date || '', title: s.assay || s.assay_id}))
  ];
  function reset() {
    inspection++;
    detailEl.replaceChildren();
    generation++; pending?.abort(); pending = null; data = null; scopeKey = '';
    required = []; active = ''; timeMode = '';
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
    const ticket = ++inspection, selectedScope = scope();
    active = p.patient_id;
    detailEl.classList.remove('empty');
    detailEl.innerHTML = '<div class="workspace-card"><h3>' + esc(patientLabel(p)) + '</h3>'
      + '<p>' + (p.events || []).length + ' clinical records · ' + (p.samples || []).length + ' linked assay entries</p>'
      + (event ? '<h4>' + esc(event.title) + '</h4><p>' + esc(timeLabel(event)) + '</p>' : '')
      + (event?.diagnosis ? '<p>' + esc(event.diagnosis) + '</p>' : '')
      + (event?.domains || []).map(d => '<p><strong>' + esc(d.label || d.key) + ':</strong> ' + (d.examples || []).map(esc).join(', ') + '</p>').join('')
      + '<h4>Clinical data, samples & assays</h4>'
      + '<div data-patient-inventory>' + patientInventoryMarkup(p.samples || [], esc, []) + '</div>'
      + '<p data-clinical-status class="section-note" role="status">Loading clinical records…</p>'
      + (event?.modality === 'clinical' ? '<button type="button" class="query-chip" data-clinical-all>All clinical timepoints</button>' : '')
      + '<button type="button" class="query-chip" data-clinical-more hidden>Load more records</button>'
      + '</div>';
    const inventoryEl = detailEl.querySelector('[data-patient-inventory]');
    const statusEl = detailEl.querySelector('[data-clinical-status]');
    let clinicalRecords = [];
    const more = detailEl.querySelector('[data-clinical-more]');
    const all = detailEl.querySelector('[data-clinical-all]');
    if (all) all.onclick = () => inspect(p, null, summary);
    let offset = 0;
    async function loadRecords() {
      more.disabled = true;
      try {
        const response = await fetch('/patient-overview/clinical?' + new URLSearchParams({
          workspace:selectedScope, dataset_id:p.dataset_id, patient_id:p.source_patient_id, offset,
          visit_id:event?.modality === 'clinical' ? (event.visit_id || '') : ''}));
        const payload = await response.json();
        if (ticket !== inspection || selectedScope !== scope()) return;
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to load clinical records.');
        const expanded = [...inventoryEl.querySelectorAll('[data-clinical-index][open]')].map(el => el.dataset.clinicalIndex);
        const scrollTop = inventoryEl.querySelector('.patient-inventory-scroll')?.scrollTop || 0;
        clinicalRecords = offset ? clinicalRecords.concat(payload.records) : payload.records;
        inventoryEl.innerHTML = patientInventoryMarkup(p.samples || [], esc, clinicalRecords);
        expanded.forEach(index => inventoryEl.querySelector(`[data-clinical-index="${index}"]`)?.setAttribute('open', ''));
        if (!offset && event?.modality === 'clinical') inventoryEl.querySelector('.clinical-record')?.setAttribute('open', '');
        inventoryEl.querySelector('.patient-inventory-scroll').scrollTop = scrollTop;
        statusEl.textContent = payload.total ? `${clinicalRecords.length} of ${payload.total} clinical records shown.` : 'No clinical records available.';
        more.textContent = 'Load more records';
        more.hidden = payload.next_offset === null;
        offset = payload.next_offset;
      } catch (error) {
        if (ticket !== inspection || selectedScope !== scope()) return;
        statusEl.textContent = error.message;
        more.hidden = false; more.textContent = 'Retry clinical records';
      } finally { more.disabled = false; }
    }
    more.onclick = loadRecords;
    void loadRecords();
    renderDashboardTimeline(summary);
    detailEl.scrollIntoView({block:'nearest'});
  }
  function renderDashboardTimeline(summary) {
    const plot = document.getElementById('dashboard-plot-timeline');
    if (!plot) return;
    if (scopeKey !== scope()) reset();
    if (!data) { plot.textContent = 'Loading data availability…'; void load(summary); return; }
    const all = data.timelines || [];
    if (state.timelinePatientFilter && active !== state.timelinePatientFilter) required = [];
    if (!timeMode) timeMode = all.some(p => events(p).some(e => time(e.date) !== null)) ? 'calendar' : 'relative';
    const axis = document.getElementById('timelineTimeMode');
    axis.value = timeMode;
    axis.onchange = () => {timeMode = axis.value; renderDashboardTimeline(summary);};
    document.getElementById('timelineTimeNote').textContent = timeMode === 'relative'
      ? 'Days from each participant’s recorded study baseline. Baseline definitions may differ between datasets; this is not calendar time.'
      : 'Recorded calendar dates. Observations with only relative study time are available in the Study days view.';
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
    if (state.timelinePatientFilter && filtered.length === 1 && active !== filtered[0].patient_id) {
      inspect(filtered[0], null, summary);
      return;
    }
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
    table.innerHTML = '<table class="dashboard-timeline-table"><thead><tr><th>Patient / dataset</th><th>Available data</th><th>' + (timeMode === 'relative' ? 'Study day not recorded' : 'Calendar date not recorded') + '</th></tr></thead><tbody>'
      + visible.map((p,i) => {
        const es = events(p);
        const badges = list => [...new Set(list.map(e => e.modality))].map(m => '<span class="pill" style="border-color:' + colour(m) + '">' + modalityIcon(m) + esc(label(m)) + '</span>').join(' ') || '—';
        return '<tr' + (active === p.patient_id ? ' class="is-inspected"' : '') + '><td><button type="button" class="query-chip" data-timeline-inspect="' + i + '">' + esc(patientLabel(p)) + '</button></td><td>' + badges(es) + '</td><td>' + badges(es.filter(e => coordinate(e) === null)) + '</td></tr>';
      }).join('') + '</tbody></table>';
    table.querySelectorAll('[data-timeline-inspect]').forEach(b => {b.onclick = () => inspect(visible[Number(b.dataset.timelineInspect)], null, summary);});
    const points = visible.flatMap(p => events(p).filter(e => coordinate(e) !== null).map(e => ({p,e})));
    if (!points.length) {
      window.Plotly?.purge(plot);
      plot.style.height = 'auto';
      plot.innerHTML = '<p class="empty">No observations with ' + (timeMode === 'relative' ? 'recorded study days' : 'calendar dates') + ' in this selection. Availability is listed below.</p>';
      return;
    }
    const traces = modalities.map(m => {
      const rows = points.filter(v => v.e.modality === m);
      return {type:'scatter', mode:'markers', name:label(m), x:rows.map(v => timeMode === 'relative' ? relativeTime(v.e) : v.e.date), y:rows.map(v => v.p.patient_id),
        customdata:rows.map(v => points.indexOf(v)), text:rows.map(v => esc(patientLabel(v.p) + ' · ' + v.e.title)),
        marker:{color:colour(m), size:rows.map(v => v.p.patient_id === active ? 14 : 10), symbol:m === 'clinical' ? 'circle' : 'diamond'},
        hovertemplate:'%{text}<br>' + (timeMode === 'relative' ? 'Study day ' : '') + '%{x}<extra></extra>'};
    }).filter(t => t.x.length);
    const spans = visible.map(p => ({p, dates: events(p).map(coordinate).filter(t => t !== null)})).filter(v => v.dates.length);
    const spanTrace = {type:'bar', orientation:'h', name:'Recorded span', showlegend:false, textposition:'none',
      y:spans.map(v => v.p.patient_id), base:spans.map(v => timeMode === 'relative' ? Math.min(...v.dates) : new Date(Math.min(...v.dates)).toISOString()),
      x:spans.map(v => Math.max(...v.dates) - Math.min(...v.dates)),
      customdata:spans.map(v => v.p.patient_id), text:spans.map(v => esc(patientLabel(v.p))),
      marker:{color:'#cbd5e1', line:{color:'#64748b', width:spans.map(v => active === v.p.patient_id ? 2 : 0)}},
      hovertemplate:'%{text}<br>Span of recorded observations<extra></extra>'};
    const plotHeight = Math.max(280, visible.length * 24 + 100);
    plot.style.height = plotHeight + 'px';
    if (!plot.data) plot.textContent = '';
    mountPlot('dashboard-plot-timeline', [spanTrace, ...traces], dashboardPlotLayout({
      height:plotHeight, margin:{t:35,r:15,b:45,l:160},
      xaxis:{type:timeMode === 'relative' ? 'linear' : 'date', title:{text:timeMode === 'relative' ? 'Days from study baseline' : 'Recorded date'}},
      yaxis:{type:'category', categoryorder:'array', categoryarray:visible.map(p => p.patient_id), tickmode:'array',
        tickvals:visible.map(p => p.patient_id), ticktext:visible.map(p => esc(datasets.size === 1 ? p.source_patient_id : patientLabel(p))), autorange:'reversed', automargin:true},
      showlegend:true, legend:{orientation:'h', y:1.02, yanchor:'bottom'}, dragmode:'zoom'
    }), el => {el.on?.('plotly_click', event => {
      const id = event.points?.[0]?.customdata;
      const point = typeof id === 'number' ? points[id] : null;
      if (point) inspect(point.p, point.e, summary);
      else { const patient = visible.find(p => p.patient_id === id); if (patient) inspect(patient, null, summary); }
    });}, {displayModeBar:true, modeBarButtonsToRemove:['select2d','lasso2d']});
  }
  function timelinePanelMarkup() {
    return '<section class="section-card dashboard-timeline-card"><h3>Data availability over time</h3>'
      + '<p class="section-note">Find patients with particular data, then inspect when it was collected.</p>'
      + '<div class="timeline-scope-controls"><strong id="timelineScopeLabel"></strong><label>Dataset <select id="timelineDatasetFilter"></select></label><button id="timelineShowAll" class="query-chip" type="button">Show all patients</button></div>'
      + '<label>Time axis <select id="timelineTimeMode"><option value="calendar">Calendar dates</option><option value="relative">Study days</option></select></label><p id="timelineTimeNote" class="section-note"></p>'
      + '<h4>Has data</h4><p class="section-note">Patients must have every checked data type. Leave unchecked to include everyone.</p><div id="timelineHasData" class="dashboard-timeline-controls"></div>'
      + '<p class="section-note">Click a plot legend item to hide or show its markers. Grey bars span the earliest to latest recorded observations; they do not imply continuous monitoring.</p>'
      + '<div class="timeline-pagination"><button id="timelinePrevious" class="query-chip">Previous</button><span id="timelinePageLabel"></span><button id="timelineNext" class="query-chip">Next</button></div>'
      + '<div id="timelineWarnings"></div><div id="dashboard-plot-timeline" class="dashboard-plot-frame"></div>'
      + '<div id="timelineAvailability" class="dashboard-timeline-table-wrap"></div>'
      + '<p class="section-note">Click a marker or patient to inspect. Availability is based on declared links; missing entries do not prove an assay was never performed. No dates are inferred.</p></section>';
  }
  return {renderDashboardTimeline, timelinePanelMarkup};
}
