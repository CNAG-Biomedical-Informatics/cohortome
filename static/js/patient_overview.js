import { sortDiseaseOptions } from './shared.js';
import { createClinicalFilters } from './clinical_filters.js';

export function createPatientOverview({state, navigation, escapeHtml: esc, scope, openTimeline, saveIdsAsCohort}) {
  const scopeUi = state.cohortScope;
  const input = document.getElementById('patientOverviewSearch');
  const list = document.getElementById('patientOverviewMatches');
  const status = document.getElementById('patientOverviewStatus');
  const detail = document.getElementById('patientOverviewDetail');
  let timer, controller, generation = 0, matches = [], nextPage = null, loading = false;
  let loadedScope = null;
  let pages = [{}], pageIndex = 0;
  let sortBy = 'patient_id', sortDirection = 'asc';
  let selectedDiseases = new Set(), diseases = [], showAllDiseases = false, diseaseGeneration = 0;
  const filters = document.getElementById('patientDiseaseFilters');
  const originFilter = document.getElementById('patientSampleOriginFilter');
  const originSelect = document.getElementById('patientSampleOrigin');
  const clinicalHost = document.getElementById('patientClinicalFilters');
  const matchCount = document.getElementById('patientMatchCount');
  let workspaceTotal = null;
  let clinicalFilters = null;
  let clinicalSignature = '';
  const scopeBar = document.createElement('div');
  document.querySelector('#dashboardPatientsPanel .dashboard-view-heading').after(scopeBar);
  scopeUi.mount(scopeBar);
  let originGeneration = 0;
  function mountClinicalFilters() {
    clinicalFilters?.destroy();
    const draft = scopeUi.getDraft();
    clinicalSignature = JSON.stringify(draft.clinical_filters);
    const selectedScope = scope();
    clinicalHost.hidden = false;
    clinicalFilters = createClinicalFilters({host:clinicalHost, workspace:selectedScope, escapeHtml:esc,
      isCurrent:() => selectedScope === scope() && !state.loadInFlight,
      initialFilters:draft.clinical_filters, initialFingerprint:draft.fingerprint, initialLabels:draft.clinical_labels,
      onChange:result => {
        clinicalSignature = JSON.stringify(result.filters);
        scopeUi.patch({clinical_filters:result.filters, fingerprint:result.fingerprint, clinical_labels:result.rule_labels});
        scopeUi.setValidation('clinical', result.status === 'ready' ? '' : result.message || 'Finish editing the clinical filter.');
      },
      onReload:() => {
        scopeUi.setValidation('clinical', '');
        scopeUi.patch({clinical_filters:[], fingerprint:'', clinical_labels:[]}); mountClinicalFilters();
      },
    });
  }
  async function loadOrigins() {
    const ticket = ++originGeneration, selectedScope = scope();
    if (!selectedScope) return;
    try {
      const rows = await request('sample-origins', {workspace:selectedScope});
      if (ticket !== originGeneration || selectedScope !== scope()) return;
      const selected = scopeUi.getDraft().sample_origin;
      originSelect.innerHTML = '<option value="">All sample origins</option>' + rows.map(row =>
        `<option value="${esc(row.id)}">${esc(row.label)} · ${esc(row.id)} (${Number(row.patient_count)})</option>`).join('');
      originSelect.value = selected;
      originFilter.hidden = !rows.length;
    } catch (_) {
      if (ticket === originGeneration && selectedScope === scope()) {
        originFilter.hidden = true;
        status.textContent = 'Sample-origin filters could not be loaded.';
      }
    }
  }
  originSelect.addEventListener('change', () => scopeUi.patch({sample_origin:originSelect.value}));
  function renderDiseases() {
    const items = showAllDiseases ? diseases : diseases.filter((item, index) => index < 8 || selectedDiseases.has(item.disease));
    filters.innerHTML = `<button type="button" class="query-chip query-chip-deterministic" data-disease="" aria-pressed="${!selectedDiseases.size}">All diseases</button>` + items.map(item => `<button type="button" class="query-chip query-chip-deterministic" data-disease="${esc(item.disease)}" aria-pressed="${selectedDiseases.has(item.disease)}">${esc(item.disease)} <span class="query-chip badge">${Number(item.patient_count) || 0}</span></button>`).join('') + (diseases.length > 8 ? `<button type="button" class="query-chip" data-more-diseases aria-expanded="${showAllDiseases}">${showAllDiseases ? 'Show fewer' : 'More diseases…'}</button>` : '') + (selectedDiseases.size > 1 ? '<span class="section-note">Matching any selected disease</span>' : '');
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
  const clinicalButton = document.getElementById('patientClinicalSummary');
  const saveStatus = document.getElementById('patientSaveStatus');
  let saving = false;
  refineButton.textContent = 'Multimodal filters';
  clinicalButton.textContent = 'View Clinical';
  function updateActions() {
    saveButton.disabled = saving || loading || scopeUi.isDirty() || scopeUi.isBusy() || !matches.length;
    refineButton.disabled = clinicalButton.disabled = !scope();
  }
  scopeUi.subscribe((snapshot, reason) => {
    input.value = snapshot.draft.q;
    originSelect.value = snapshot.draft.sample_origin;
    selectedDiseases = new Set(snapshot.draft.diseases); renderDiseases();
    const next = JSON.stringify(snapshot.draft.clinical_filters);
    if (next !== clinicalSignature || ['discard', 'clear'].includes(reason)) {
      clinicalSignature = next;
      clinicalFilters?.setFilters(snapshot.draft.clinical_filters, snapshot.draft.fingerprint, snapshot.draft.clinical_labels);
    }
    updateActions();
    if (reason === 'applied') { clearSelection(false); searchPatients(); }
    if (reason === 'settled' && snapshot.errorStatus === 409 && snapshot.draft.clinical_filters.length) {
      clinicalFilters?.invalidate(snapshot.error);
    }
    if (reason === 'workspace-settled') refresh();
  });
  function clearSelection(navigate = true) {
    state.patientOverviewSelection = null;
    timelineButton.disabled = true;
    timelineButton.hidden = true;
    if (navigate && state.currentDashboardSubtab === 'timeline') navigation.setDashboardSubtab('patients');
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
    workspaceTotal = null; matchCount.textContent = '';
    loadedScope = null;
    clinicalFilters?.destroy(); clinicalFilters = null;
    clinicalHost.replaceChildren(); clinicalHost.hidden = true;
    originGeneration++; originSelect.value = ''; originFilter.hidden = true;
    saveButton.disabled = refineButton.disabled = clinicalButton.disabled = true; saveStatus.textContent = '';
    selectedDiseases.clear(); diseases = []; showAllDiseases = false; diseaseGeneration++; renderDiseases();
    clearSelection();
    clearTimeout(timer); controller?.abort(); generation++;
    matches = []; pages = [{}]; pageIndex = 0; nextPage = null; loading = false;
    list.removeAttribute('aria-busy');
    more.disabled = true; previous.disabled = true;
    render(); detail.replaceChildren(); input.value = '';
    status.textContent = 'Select a workspace to browse patients.';
  }
  function refresh() {
    if (state.loadInFlight || navigation.currentTabName() !== 'dashboard'
        || state.currentDashboardSubtab !== 'patients' || !state.currentDatasetIds.length) return;
    const selectedScope = scope();
    if (!selectedScope || selectedScope === loadedScope) return;
    loadedScope = selectedScope;
    if (!clinicalFilters) mountClinicalFilters();
    searchPatients();
    void loadDiseases();
    void loadOrigins();
  }
  async function request(path, params, signal) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => (Array.isArray(val) ? val : [val]).forEach(item => query.append(key, item)));
    const options = {signal};
    const active = state.activePatientScope?.workspace === scope() ? state.activePatientScope : null;
    if (active && path === 'search') {
      path = 'scoped-search';
      Object.assign(options, {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({members:active.selection.members})});
    }
    const response = await fetch(`/patient-overview/${path}?${query}`, options);
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load patient information.');
      error.status = response.status; throw error;
    }
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
    matchCount.textContent = '';
    saveButton.disabled = refineButton.disabled = clinicalButton.disabled = true; saveStatus.textContent = '';
    clearTimeout(timer); controller?.abort(); generation++;
    loading = false;
    if (!changePage) { pages = [{}]; pageIndex = 0; nextPage = null; }
    nextPage = null;
    if (state.loadInFlight) { status.textContent = 'Applying workspace selection…'; return; }
    if (!scope()) { matches = []; render(); status.textContent = 'Select and apply a dataset first.'; return; }
    status.textContent = 'Loading patients in scope…';
    loading = true; more.disabled = true; previous.disabled = true;
    list.setAttribute('aria-busy', 'true');
    const ticket = generation, selectedScope = scope();
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const data = await request('search', {workspace:selectedScope, sort_by:sortBy, direction:sortDirection, ...pages[pageIndex]}, controller.signal);
        if (ticket !== generation || selectedScope !== scope()) return;
        matches = data.matches;
        if (!state.activePatientScope && Number.isInteger(data.total)) workspaceTotal = data.total;
        if (Number.isInteger(data.total)) matchCount.textContent = `${data.total.toLocaleString()}${workspaceTotal !== null ? ` of ${workspaceTotal.toLocaleString()}` : ''} patients in scope`;
        saveButton.querySelector('span').textContent = Number.isInteger(data.total)
          ? `Save ${data.total.toLocaleString()} ${data.total === 1 ? 'patient' : 'patients'} as cohort`
          : 'Save filtered patients as cohort';
        nextPage = data.next || null;
        render();
        status.textContent = matches.length ? `Page ${pageIndex + 1} · ${matches.length} ${matches.length === 1 ? 'patient' : 'patients'}` : 'No matching patients in the active datasets.';
      } catch (error) {
        if (ticket === generation && error.name !== 'AbortError') {
          loadedScope = null;
          matches = []; render(); status.textContent = error.message;
        }
      } finally { if (ticket === generation) { loading = false; more.disabled = !nextPage; previous.disabled = pageIndex === 0; updateActions(); list.removeAttribute('aria-busy'); } }
    }, 200);
  }
  input.addEventListener('input', () => {
    scopeUi.patch({q:input.value});
  });
  filters.addEventListener('click', event => {
    if (event.target.closest('[data-more-diseases]')) { showAllDiseases = !showAllDiseases; renderDiseases(); return; }
    const chip = event.target.closest('[data-disease]');
    if (!chip) return;
    const label = chip.dataset.disease;
    if (!label) selectedDiseases.clear();
    else if (selectedDiseases.has(label)) selectedDiseases.delete(label);
    else selectedDiseases.add(label);
    scopeUi.patch({diseases:[...selectedDiseases]});
  });
  async function useFilteredPatients() {
    if (saving || loading || scopeUi.isDirty() || scopeUi.isBusy() || !matches.length) return;
    saving = true; saveButton.disabled = refineButton.disabled = clinicalButton.disabled = true;
    const ticket = generation, selectedScope = scope();
    const isCurrent = () => ticket === generation && selectedScope === scope();
    const params = {workspace:selectedScope};
    saveStatus.textContent = 'Collecting all matching patients…';
    try {
      const active = state.activePatientScope?.workspace === scope() ? state.activePatientScope : null;
      const data = active ? active.selection : await request('selection', params);
      if (!isCurrent()) throw new Error('Filters or workspace changed. Please try again.');
      const members = data.members || [];
      if (!members.length) throw new Error('No matching patients.');
      const description = active?.selection.source?.prompt || 'All workspace patients';
      const saved = await saveIdsAsCohort({members, sourceKind:'manual', statusTarget:'none', isCurrent,
        sourcePrompt:description});
      saveStatus.textContent = !isCurrent() ? 'Filters or workspace changed. Please save again.'
        : saved ? `Saved ${members.length} patients. Find the cohort in Cohorts.` : 'Cohort was not saved.';
    } catch (error) {
      if (isCurrent()) {
        saveStatus.textContent = error.message || 'Unable to save cohort.';
      }
    }
    finally { saving = false; updateActions(); }
  }
  saveButton.addEventListener('click', () => useFilteredPatients());
  clinicalButton.addEventListener('click', () => navigation.setDashboardSubtab('clinical'));
  refineButton.addEventListener('click', () => navigation.setDashboardSubtab('multimodal'));
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
    navigation.setDashboardSubtab('patients');
  });
  render(); renderDiseases();
  return { refresh };
}
