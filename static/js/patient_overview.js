import { sortDiseaseOptions } from './shared.js';

export function createPatientOverview({state, navigation, escapeHtml: esc, scope, openTimeline, saveIdsAsCohort, refineInMultimodal}) {
  const input = document.getElementById('patientOverviewSearch');
  const list = document.getElementById('patientOverviewMatches');
  const status = document.getElementById('patientOverviewStatus');
  const detail = document.getElementById('patientOverviewDetail');
  let timer, controller, generation = 0, matches = [], nextPage = null, loading = false;
  let pages = [{}], pageIndex = 0;
  let sortBy = 'patient_id', sortDirection = 'asc';
  let selectedDiseases = new Set(), diseases = [], showAllDiseases = false, diseaseGeneration = 0;
  const filters = document.getElementById('patientDiseaseFilters');
  function renderDiseases() {
    const items = showAllDiseases ? diseases : diseases.slice(0, 8);
    filters.innerHTML = `<button type="button" class="query-chip query-chip-deterministic" data-disease="" aria-pressed="${!selectedDiseases.size}">All patients</button>` + items.map(item => `<button type="button" class="query-chip query-chip-deterministic" data-disease="${esc(item.disease)}" aria-pressed="${selectedDiseases.has(item.disease)}">${esc(item.disease)} <span class="query-chip badge">${Number(item.patient_count) || 0}</span></button>`).join('') + (diseases.length > 8 ? `<button type="button" class="query-chip" data-more-diseases aria-expanded="${showAllDiseases}">${showAllDiseases ? 'Show fewer' : 'More diseases…'}</button>` : '') + (selectedDiseases.size > 1 ? '<span class="section-note">Matching any selected disease</span>' : '');
  }
  async function loadDiseases() {
    const ticket = ++diseaseGeneration, selectedScope = scope();
    if (!selectedScope) return;
    try {
      const response = await fetch(`/cohorts/diseases?${new URLSearchParams({data_dir:selectedScope})}`);
      if (!response.ok) throw new Error('Disease filters unavailable');
      const payload = await response.json();
      if (ticket !== diseaseGeneration || selectedScope !== scope()) return;
      diseases = sortDiseaseOptions(Array.isArray(payload) ? payload : []); renderDiseases();
    } catch (_) {
      if (ticket === diseaseGeneration) { diseases = []; renderDiseases(); }
    }
  }
  const sortKeys = ['patient_id', 'dataset_label', 'diagnosis', 'clarid'];
  const more = document.getElementById('patientOverviewMore');
  const previous = document.getElementById('patientOverviewPrevious');
  const timelineButton = document.getElementById('patientTimelineBtn');
  const saveButton = document.getElementById('patientSaveCohort');
  const refineButton = document.getElementById('patientRefineMultimodal');
  const saveStatus = document.getElementById('patientSaveStatus');
  let saving = false;
  function clearSelection() {
    state.patientOverviewSelection = null;
    timelineButton.disabled = true;
    timelineButton.hidden = true;
    if (state.currentDashboardSubtab === 'timeline') navigation.setDashboardSubtab('patients');
  }
  const value = text => esc(String(text || 'Not recorded'));
  const icon = path => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">${path}</svg>`;
  const headers = [
    ['Patient ID', '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/>'],
    ['Dataset', '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>'],
    ['Diagnosis', '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M12 8v8M8 12h8"/>'],
    ['ClarID', '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10h3M7 14h3M13 10h4M13 14h4"/>'],
  ];
  function render() {
    list.innerHTML = `<table><thead><tr><th>Patient ID</th><th>Dataset</th><th>Diagnosis</th><th>ClarID</th></tr></thead><tbody>${matches.map((m,i) => `<tr data-match="${i}"><td><button type="button" class="patient-open" aria-label="Open patient ${value(m.patient_id)}">${value(m.patient_id)}<span aria-hidden="true"> →</span></button></td><td>${value(m.dataset_label)}</td><td>${value(m.diagnosis)}</td><td>${m.clarid ? `<span class="patient-browser-clarid" title="${value(m.clarid)}">${value(m.clarid)}</span>` : '<span class="patient-browser-missing">Not recorded</span>'}</td></tr>`).join('') || '<tr><td colspan="4" class="patient-browser-empty">No patients to display.</td></tr>'}</tbody></table>`;
    list.querySelector('thead tr').innerHTML = headers.map(([label, path], i) => `<th scope="col" aria-sort="${sortBy === sortKeys[i] ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}"><button type="button" class="patient-sort" data-sort="${sortKeys[i]}" aria-label="Sort by ${label}">${icon(path)}${label}<span aria-hidden="true">${sortBy === sortKeys[i] ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ' ↕'}</span></button></th>`).join('');
  }
  function reset() {
    saveButton.disabled = refineButton.disabled = true; saveStatus.textContent = '';
    selectedDiseases.clear(); diseases = []; showAllDiseases = false; diseaseGeneration++; renderDiseases();
    clearSelection();
    clearTimeout(timer); controller?.abort(); generation++;
    matches = []; pages = [{}]; pageIndex = 0; nextPage = null; loading = false;
    more.disabled = true; previous.disabled = true;
    render(); detail.replaceChildren(); input.value = '';
    status.textContent = 'Select a workspace to browse patients.';
  }
  async function request(path, params, signal) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => (Array.isArray(val) ? val : [val]).forEach(item => query.append(key, item)));
    const response = await fetch(`/patient-overview/${path}?${query}`, {signal});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load patient information.');
    return data;
  }
  async function choose(index) {
    const match = matches[index]; if (!match) return;
    clearSelection();
    clearTimeout(timer); controller?.abort(); controller = new AbortController();
    const ticket = ++generation, selectedScope = scope();
    detail.replaceChildren();
    status.textContent = 'Opening patient timeline…';
    try {
      state.patientOverviewSelection = { patientId: match.patient_id, datasetId: match.dataset_id };
      timelineButton.disabled = false;
      timelineButton.hidden = false;
      await openTimeline(match.patient_id, match.dataset_id);
      if (ticket !== generation || selectedScope !== scope()) return;
      status.textContent = `Selected ${match.patient_id} in ${match.dataset_label}. Details are in Timeline.`;
    } catch (error) {
      if (ticket === generation && error.name !== 'AbortError') status.textContent = error.message;
    }
  }
  function searchPatients(changePage = false) {
    saveButton.disabled = refineButton.disabled = true; saveStatus.textContent = '';
    clearTimeout(timer); controller?.abort(); generation++;
    if (!changePage) { pages = [{}]; pageIndex = 0; nextPage = null; }
    nextPage = null;
    const q = input.value.trim();
    if (!scope()) { matches = []; render(); status.textContent = 'Select and apply a dataset first.'; return; }
    status.textContent = q ? 'Searching…' : 'Loading patients…';
    loading = true; more.disabled = true; previous.disabled = true;
    list.setAttribute('aria-busy', 'true');
    const ticket = generation, selectedScope = scope();
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const data = await request('search', {workspace:selectedScope, q, disease:[...selectedDiseases], sort_by:sortBy, direction:sortDirection, ...pages[pageIndex]}, controller.signal);
        if (ticket !== generation || selectedScope !== scope()) return;
        matches = data.matches;
        saveButton.querySelector('span').textContent = Number.isInteger(data.total)
          ? `Save ${data.total.toLocaleString()} ${data.total === 1 ? 'patient' : 'patients'} as cohort`
          : 'Save filtered patients as cohort';
        nextPage = data.next || null;
        render();
        status.textContent = matches.length ? `Page ${pageIndex + 1} · ${matches.length} ${matches.length === 1 ? 'patient' : 'patients'}` : 'No matching patients in the active datasets.';
      } catch (error) {
        if (ticket === generation && error.name !== 'AbortError') {
          matches = []; render(); status.textContent = error.message;
        }
      } finally { if (ticket === generation) { loading = false; more.disabled = !nextPage; previous.disabled = pageIndex === 0; saveButton.disabled = refineButton.disabled = saving || !matches.length; list.removeAttribute('aria-busy'); } }
    }, 200);
  }
  input.addEventListener('input', () => {
    clearSelection(); detail.replaceChildren(); searchPatients();
  });
  filters.addEventListener('click', event => {
    if (event.target.closest('[data-more-diseases]')) { showAllDiseases = !showAllDiseases; renderDiseases(); return; }
    const chip = event.target.closest('[data-disease]');
    if (!chip) return;
    const label = chip.dataset.disease;
    if (!label) selectedDiseases.clear();
    else if (selectedDiseases.has(label)) selectedDiseases.delete(label);
    else selectedDiseases.add(label);
    clearSelection(); renderDiseases(); searchPatients();
  });
  async function useFilteredPatients(refine = false) {
    if (saving || loading || !matches.length) return;
    saving = true; saveButton.disabled = refineButton.disabled = true;
    const ticket = generation, selectedScope = scope();
    const isCurrent = () => ticket === generation && selectedScope === scope();
    const params = {workspace:selectedScope, q:input.value.trim(), disease:[...selectedDiseases],
      sort_by:'patient_id', direction:'asc'};
    const members = [], seen = new Set();
    let cursor = {};
    saveStatus.textContent = 'Collecting all matching patients…';
    try {
      do {
        const data = await request('search', {...params, ...cursor});
        if (!isCurrent()) throw new Error('Filters or workspace changed. Please try again.');
        for (const row of data.matches) {
          const key = JSON.stringify([row.dataset_id, row.patient_id]);
          if (!seen.has(key)) { seen.add(key); members.push({dataset_id:row.dataset_id, patient_id:row.patient_id}); }
        }
        cursor = data.next;
        saveStatus.textContent = `Collected ${members.length} matching patients…`;
      } while (cursor);
      if (!members.length) throw new Error('No matching patients.');
      const description = `Patients: ${params.disease.length ? 'Any of ' + params.disease.join(', ') : 'All diseases'}${params.q ? `; ID/ClarID search: ${params.q}` : ''}`;
      if (refine) {
        refineInMultimodal({scope:selectedScope, members, description, diseases:params.disease});
        saveStatus.textContent = `Sent ${members.length} patients to Multimodal.`;
        return;
      }
      const saved = await saveIdsAsCohort({members, sourceKind:'manual', statusTarget:'none', isCurrent,
        sourcePrompt:description});
      saveStatus.textContent = !isCurrent() ? 'Filters or workspace changed. Please save again.'
        : saved ? `Saved ${members.length} patients. Find the cohort in Cohorts.` : 'Cohort was not saved.';
    } catch (error) { saveStatus.textContent = error.message || 'Unable to save cohort.'; }
    finally { saving = false; saveButton.disabled = refineButton.disabled = loading || !matches.length; }
  }
  saveButton.addEventListener('click', () => useFilteredPatients());
  refineButton.addEventListener('click', () => useFilteredPatients(true));
  more.addEventListener('click', () => {
    if (loading || !nextPage) return;
    pages[++pageIndex] = nextPage; searchPatients(true);
  });
  previous.addEventListener('click', () => {
    if (loading || pageIndex === 0) return;
    pageIndex--; searchPatients(true);
  });
  list.addEventListener('click', event => {
    const sort = event.target.closest('[data-sort]');
    if (sort) {
      sortDirection = sortBy === sort.dataset.sort && sortDirection === 'asc' ? 'desc' : 'asc';
      sortBy = sort.dataset.sort; searchPatients(); return;
    }
    if (loading) return;
    const option = event.target.closest('[data-match]'); if (option) void choose(Number(option.dataset.match));
  });
  window.addEventListener('cohortome:workspace-changing', reset);
  timelineButton.addEventListener('click', () => {
    if (state.patientOverviewSelection && !timelineButton.disabled) void openTimeline(state.patientOverviewSelection.patientId, state.patientOverviewSelection.datasetId);
  });
  document.getElementById('dashboardPatientsBtn').addEventListener('click', () => {
    navigation.setDashboardSubtab('patients'); searchPatients(); void loadDiseases();
  });
  render(); renderDiseases();
}
