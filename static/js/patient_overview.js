import { patientInventoryMarkup } from '/static/js/patient_inventory.js';

export function createPatientOverview({state, navigation, escapeHtml: esc, scope, openTimeline}) {
  const input = document.getElementById('patientOverviewSearch');
  const list = document.getElementById('patientOverviewMatches');
  const status = document.getElementById('patientOverviewStatus');
  const detail = document.getElementById('patientOverviewDetail');
  let timer, controller, generation = 0, matches = [], active = -1;
  const timelineButton = document.getElementById('patientTimelineBtn');
  function clearSelection() {
    state.patientOverviewSelection = null;
    timelineButton.disabled = true;
    if (state.currentDashboardSubtab === 'timeline') navigation.setDashboardSubtab('patients');
  }
  const value = text => esc(String(text || 'Not recorded'));
  function close() {
    list.hidden = true; input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant'); active = -1;
  }
  function reset() {
    clearSelection();
    clearTimeout(timer); controller?.abort(); generation++;
    close(); matches = []; list.replaceChildren(); detail.replaceChildren(); input.value = '';
    status.textContent = 'Search by patient ID or ClarID. Up to 12 matches are shown.';
  }
  async function request(path, params, signal) {
    const response = await fetch(`/patient-overview/${path}?${new URLSearchParams(params)}`, {signal});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load patient information.');
    return data;
  }
  function render(data) {
    const p = data.patient, rows = data.samples;
    const samples = new Set(rows.map(r => r.sample_id)).size;
    const assays = new Set(rows.map(r => r.assay_id)).size;
    const modalities = new Set(rows.map(r => r.modality)).size;
    detail.innerHTML = `<section class="controls patient-overview-card">
      <div class="patient-overview-heading"><div><span class="patient-source">${value(data.dataset_label)}</span>
      <h2>${value(p.patient_id)}</h2>${p.clarid ? `<div class="patient-clarid">ClarID · ${value(p.clarid)}</div>` : ''}</div>
      <span class="patient-source">Sex: ${value(p.sex)}</span></div>
      <div class="patient-overview-stats">${[[samples,'Sample identifiers'],[assays,'Assays'],[modalities,'Assay types'],[p.clinical_record_count,'Clinical records']].map(([n,label]) => `<div><strong>${value(String(n))}</strong><span>${label}</span></div>`).join('')}</div>
      <h3>Samples & assays available in this dataset</h3>
      <p class="section-note">This inventory describes data available here, not every assay ever performed. Sample identifiers are those supplied by the dataset; they do not necessarily represent distinct biological specimens.</p>
      ${rows.length ? patientInventoryMarkup(rows, esc) : '<p>No linked assay samples are available in this dataset.</p>'}
      ${data.warnings.length ? `<details class="patient-inventory-warning"><summary>Inventory limitations (${data.warnings.length})</summary><ul>${data.warnings.map(w => `<li>${value(w)}</li>`).join('')}</ul></details>` : ''}
      </section>`;
  }
  async function choose(index) {
    const match = matches[index]; if (!match) return;
    clearSelection();
    clearTimeout(timer); controller?.abort(); controller = new AbortController();
    const ticket = ++generation, selectedScope = scope();
    close(); input.value = match.patient_id; detail.replaceChildren();
    status.textContent = 'Loading available samples and assays…';
    try {
      const data = await request('detail', {workspace:selectedScope, dataset_id:match.dataset_id, patient_id:match.patient_id}, controller.signal);
      if (ticket !== generation || selectedScope !== scope()) return;
      state.patientOverviewSelection = { patientId: match.patient_id, datasetId: match.dataset_id, samples: data.samples };
      timelineButton.disabled = false;
      render(data); status.textContent = `Showing ${match.patient_id} in ${match.dataset_label}.`;
    } catch (error) {
      if (ticket === generation && error.name !== 'AbortError') status.textContent = error.message;
    }
  }
  input.addEventListener('input', () => {
    clearSelection();
    clearTimeout(timer); controller?.abort(); generation++; close(); detail.replaceChildren();
    const q = input.value.trim(); matches = [];
    if (!q) { status.textContent = 'Start typing a patient ID or ClarID.'; return; }
    if (!scope()) { status.textContent = 'Select and apply a dataset first.'; return; }
    status.textContent = 'Searching…';
    const ticket = generation, selectedScope = scope();
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const data = await request('search', {workspace:selectedScope, q}, controller.signal);
        if (ticket !== generation || selectedScope !== scope()) return;
        matches = data.matches;
        list.innerHTML = matches.map((m,i) => `<button type="button" role="option" aria-selected="false" tabindex="-1" id="patient-match-${i}" data-match="${i}"><strong>${value(m.patient_id)}</strong><span>${value(m.dataset_label)}${m.clarid ? ` · ${value(m.clarid)}` : ''}</span></button>`).join('');
        list.hidden = !matches.length; input.setAttribute('aria-expanded', String(!!matches.length));
        status.textContent = matches.length ? `${matches.length} matches. Select a patient; type more to narrow the list.` : 'No matching patients in the active datasets.';
      } catch (error) {
        if (ticket === generation && error.name !== 'AbortError') status.textContent = error.message;
      }
    }, 200);
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') { close(); return; }
    if (list.hidden || !matches.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      active = active < 0 ? (event.key === 'ArrowDown' ? 0 : matches.length - 1)
        : (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
      [...list.children].forEach((el,i) => el.setAttribute('aria-selected', String(i === active)));
      input.setAttribute('aria-activedescendant', `patient-match-${active}`);
      list.children[active].scrollIntoView({block:'nearest'});
    } else if (event.key === 'Enter' && active >= 0) { event.preventDefault(); void choose(active); }
  });
  list.addEventListener('click', event => {
    const option = event.target.closest('[data-match]'); if (option) void choose(Number(option.dataset.match));
  });
  document.addEventListener('click', event => { if (!event.target.closest('.patient-lookup')) close(); });
  window.addEventListener('cohortome:workspace-changing', reset);
  document.getElementById('patientOverviewViewBtn').addEventListener('click', () => navigation.setDashboardSubtab('patients'));
  timelineButton.addEventListener('click', () => {
    if (state.patientOverviewSelection && !timelineButton.disabled) void openTimeline(state.patientOverviewSelection.patientId, state.patientOverviewSelection.datasetId);
  });
  document.getElementById('dashboardPatientsBtn').addEventListener('click', () => {
    navigation.setDashboardSubtab('patients'); input.focus();
  });
}
