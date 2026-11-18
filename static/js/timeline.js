import { modalityLabel, modalityColor } from './modalities.js';
import { createTimelineView, createPatientInspectorView } from './react/ui.js';

// Availability is dataset-scoped. Clinical properties are inspector details.
export function createTimelineUi({state, refs, helpers}) {
  const {escapeHtml: esc, mountPlot, dashboardPlotLayout} = helpers;
  const {detailEl} = refs;
  const view = createTimelineView(refs.dashboardTimelineEl);
  const inspectorView = createPatientInspectorView(detailEl);
  let data = null, scopeKey = '', pending = null, generation = 0;
  let active = '';
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
    inspectorView.reset();
    detailEl.replaceChildren();
    generation++; pending?.abort(); pending = null; data = null; scopeKey = '';
    active = ''; timeMode = '';
    view.reset();
  }
  window.addEventListener('cohortome:workspace-changing', reset);
  window.addEventListener('cohortome:scope-applied', () => {
    inspection++; active = ''; inspectorView.reset(); detailEl.replaceChildren();
    state.timelinePatientFilter = ''; state.timelinePage = 0;
  });
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
        view.render({error:error.message, actions:{retry:() => renderDashboardTimeline(summary)}});
      }
    } finally { if (pending === controller) pending = null; }
  }
  function inspect(p, event, summary) {
    const ticket = ++inspection, selectedScope = scope();
    active = p.patient_id;
    detailEl.classList.remove('empty');
    let clinicalRecords = [], offset = 0, loading = false, failed = false, clarid;
    let status = 'Loading clinical records…';
    const current = () => ticket === inspection && selectedScope === scope();
    const render = () => inspectorView.render({ticket, patient:p, event, label:patientLabel(p),
      timeLabel:event ? timeLabel(event) : '', records:clinicalRecords, clarid, status, loading,
      failed, hasMore:failed || offset !== null, more:loadRecords, all:() => inspect(p,null,summary)});
    async function loadRecords() {
      if (!current() || loading || offset === null) return;
      loading = true; failed = false; render();
      try {
        const response = await fetch('/patient-overview/clinical?' + new URLSearchParams({
          workspace:selectedScope, dataset_id:p.dataset_id, patient_id:p.source_patient_id, offset,
          visit_id:event?.modality === 'clinical' ? (event.visit_id || '') : ''}));
        const payload = await response.json();
        if (!current()) return;
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to load clinical records.');
        clinicalRecords = offset ? clinicalRecords.concat(payload.records) : payload.records;
        clarid = payload.clarid; offset = payload.next_offset;
        status = payload.total ? clinicalRecords.length + ' of ' + payload.total + ' clinical records shown.' : 'No clinical records available.';
      } catch (error) {if (current()) {status = error.message; failed = true;}}
      finally {if (current()) {loading = false; render();}}
    }
    render(); void loadRecords();
    renderDashboardTimeline(summary);
  }
  function renderDashboardTimeline(summary) {
    if (scopeKey !== scope()) {reset(); scopeKey = scope();}
    if (!data) { view.render({loading:true, actions:{}}); void load(summary); return; }
    const applied = state.activePatientScope?.workspace === state.currentDatasetScopeId ? state.activePatientScope : null;
    const memberKeys = applied ? new Set((applied.selection.members || []).map(m => JSON.stringify([m.dataset_id, m.patient_id]))) : null;
    const all = (data.timelines || []).filter(patient => !memberKeys || memberKeys.has(JSON.stringify([patient.dataset_id, patient.source_patient_id])));
    if (!timeMode) timeMode = all.some(p => events(p).some(e => time(e.date) !== null)) ? 'calendar' : 'relative';
    const datasets = new Map(all.map(p => [p.dataset_id, p.dataset_label]));
    const modalities = [...new Set(all.flatMap(p => events(p).map(e => e.modality)))].sort();
    const filtered = all.filter(p => (!state.timelineDatasetFilter || p.dataset_id === state.timelineDatasetFilter)
      && (!state.timelinePatientFilter || p.patient_id === state.timelinePatientFilter));
    if (state.timelinePatientFilter && filtered.length === 1 && active !== filtered[0].patient_id) {
      inspect(filtered[0], null, summary);
      return;
    }
    const pages = Math.max(1, Math.ceil(filtered.length / 40));
    state.timelinePage = Math.min(state.timelinePage || 0, pages - 1);
    const visible = filtered.slice(state.timelinePage * 40, (state.timelinePage + 1) * 40);
    view.render({
      datasets:[...datasets], dataset:state.timelineDatasetFilter || '', timeMode,
      page:state.timelinePage, pages, active, warnings:data.warnings || [],
      scopeLabel:filtered.length + ' patients match · ' + all.length + (applied ? ' in applied scope' : ' in workspace'),
      rows:visible.map(patient => ({patient, label:patientLabel(patient),
        modalities:[...new Set(events(patient).map(e => e.modality))],
        undated:[...new Set(events(patient).filter(e => coordinate(e) === null).map(e => e.modality))]})),
      actions:{
        dataset:value => {state.timelineDatasetFilter = value; state.timelinePatientFilter = ''; state.timelinePage = 0; renderDashboardTimeline(summary);},
        time:value => {timeMode = value; renderDashboardTimeline(summary);},
        page:delta => {state.timelinePage += delta; renderDashboardTimeline(summary);},
        clear:() => {state.timelineDatasetFilter = ''; state.timelinePatientFilter = ''; state.timelinePage = 0; renderDashboardTimeline(summary);},
        inspect:patient => inspect(patient, null, summary),
      },
      draw:() => drawTimeline(visible, modalities, datasets, summary),
    });
  }
  function drawTimeline(visible, modalities, datasets, summary) {
    const plot = document.getElementById('dashboard-plot-timeline');
    if (!plot) return;
    const points = visible.flatMap(p => events(p).filter(e => coordinate(e) !== null).map(e => ({p,e})));
    if (!points.length) {
      window.Plotly?.purge?.(plot);
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
  return {renderDashboardTimeline, resetTimelineView:() => view.reset(),
    resetInspectorView:() => {inspection++; inspectorView.reset();}};
}
