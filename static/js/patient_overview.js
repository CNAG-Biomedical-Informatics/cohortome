import { sortDiseaseOptions } from './shared.js';
import { patientScopeLabel } from './scope-label.js';
import { createPatientsView } from './react/ui.js';

export function createPatientOverview({state, navigation, escapeHtml: esc, scope, openTimeline, saveIdsAsCohort}) {
  const scopeUi = state.cohortScope;
  let timer, controller, generation = 0, matches = [], nextPage = null, loading = false;
  let loadedScope = null, pages = [{}], pageIndex = 0;
  let sortBy = 'patient_id', sortDirection = 'asc';
  let diseases = [], origins = [], showAllDiseases = false, diseaseGeneration = 0, originGeneration = 0;
  let workspaceTotal = null, clinicalWorkspace = '', previewLabel = '';
  let saving = false, matchCount = '', saveStatus = '', saveLabel = 'Save filtered patients as cohort';
  let status = 'Select a workspace to browse patients.';

  const view = createPatientsView({host:document.getElementById('patientOverviewRoot'), scopeUi,
    isClinicalCurrent:selectedScope => selectedScope === scope() && !state.loadInFlight, actions:{
      search:q => scopeUi.patch({q}),
      origin:sample_origin => scopeUi.patch({sample_origin}),
      disease:label => {
        const selected = new Set(scopeUi.getDraft().diseases);
        if (!label) selected.clear();
        else if (selected.has(label)) selected.delete(label);
        else selected.add(label);
        scopeUi.patch({diseases:[...selected]});
      },
      toggleDiseases:() => { showAllDiseases = !showAllDiseases; render(); },
      sort:key => {
        sortDirection = sortBy === key && sortDirection === 'asc' ? 'desc' : 'asc';
        sortBy = key; searchPatients();
      },
      choose:match => {
        if (!loading) void choose(matches.find(item => item.dataset_id === match.dataset_id && item.patient_id === match.patient_id));
      },
      save:useFilteredPatients,
      multimodal:() => navigation.setDashboardSubtab('multimodal'),
      next:() => { if (!loading && nextPage) { pages[++pageIndex] = nextPage; searchPatients(true); } },
      previous:() => { if (!loading && pageIndex > 0) { pageIndex--; searchPatients(true); } },
      timeline:() => {
        const patient = state.patientOverviewSelection;
        if (patient) void openTimeline(patient.patientId, patient.datasetId);
      },
    }});

  function render() {
    view.render({matches, sortBy, sortDirection, draft:scopeUi.getDraft(), diseases, origins, showAllDiseases,
      clinicalWorkspace, matchCount, status, saveStatus, saveLabel, loading, previewLabel,
      canSave:!saving && !loading && !state.loadInFlight && !scopeUi.isDirty() && !scopeUi.isBusy() && matches.length > 0,
      canNavigate:Boolean(scope()) && !state.loadInFlight && !loading && !saving,
      canNext:!loading && Boolean(nextPage), canPrevious:!loading && pageIndex > 0,
      selectedPatient:state.patientOverviewSelection});
  }
  async function loadOrigins() {
    const ticket = ++originGeneration, selectedScope = scope();
    if (!selectedScope) return;
    try {
      const rows = await request('sample-origins', {workspace:selectedScope});
      if (ticket !== originGeneration || selectedScope !== scope()) return;
      origins = rows; render();
    } catch (_) {
      if (ticket === originGeneration && selectedScope === scope()) {
        origins = []; status = 'Sample-origin filters could not be loaded.'; render();
      }
    }
  }
  async function loadDiseases() {
    const ticket = ++diseaseGeneration, selectedScope = scope();
    if (!selectedScope) return;
    try {
      const response = await fetch(`/cohorts/diseases?${new URLSearchParams({data_dir:selectedScope})}`);
      if (!response.ok) throw new Error('Disease filters unavailable');
      const payload = await response.json();
      if (ticket !== diseaseGeneration || selectedScope !== scope()) return;
      diseases = sortDiseaseOptions(Array.isArray(payload) ? payload : []); render();
    } catch (_) {
      if (ticket === diseaseGeneration) { diseases = []; render(); }
    }
  }
  scopeUi.subscribe((snapshot, reason) => {
    if (['draft','clear','discard','validation'].includes(reason)) {
      if (state.currentDashboardSubtab === 'patients' && navigation.currentTabName() === 'dashboard') searchPatients();
      else loadedScope = null;
    }
    if (reason === 'applied') { clearSelection(false); searchPatients(); }
    if (reason === 'workspace-settled') refresh();
    render();
  });
  function clearSelection(navigate = true) {
    state.patientOverviewSelection = null;
    if (navigate && state.currentDashboardSubtab === 'timeline') navigation.setDashboardSubtab('patients');
  }
  function reset() {
    workspaceTotal = null; matchCount = ''; loadedScope = null; clinicalWorkspace = ''; previewLabel = '';
    origins = []; originGeneration++; saveStatus = ''; saveLabel = 'Save filtered patients as cohort';
    diseases = []; showAllDiseases = false; diseaseGeneration++;
    clearSelection(); clearTimeout(timer); controller?.abort(); generation++;
    matches = []; pages = [{}]; pageIndex = 0; nextPage = null; loading = false;
    status = 'Select a workspace to browse patients.'; render();
  }
  function refresh() {
    if (state.loadInFlight || navigation.currentTabName() !== 'dashboard'
        || state.currentDashboardSubtab !== 'patients' || !state.currentDatasetIds.length) return;
    const selectedScope = scope();
    if (!selectedScope || selectedScope === loadedScope) return;
    loadedScope = selectedScope; clinicalWorkspace = selectedScope;
    searchPatients(); void loadDiseases(); void loadOrigins();
  }
  async function request(path, params, signal) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => (Array.isArray(val) ? val : [val]).forEach(item => query.append(key, item)));
    const options = {signal};
    const active = state.activePatientScope?.workspace === scope() ? state.activePatientScope : null;
    if (active && path === 'search') {
      path = 'scoped-search';
      Object.assign(options, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({members:active.selection.members})});
    }
    const response = await fetch(`/patient-overview/${path}?${query}`, options);
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load patient information.');
      error.status = response.status; throw error;
    }
    return data;
  }
  async function choose(match) {
    if (!match) return;
    clearSelection(); clearTimeout(timer); controller?.abort(); controller = new AbortController();
    const ticket = ++generation, selectedScope = scope();
    status = 'Opening patient timeline…';
    state.patientOverviewSelection = {patientId:match.patient_id, datasetId:match.dataset_id}; render();
    try {
      await openTimeline(match.patient_id, match.dataset_id);
      if (ticket !== generation || selectedScope !== scope()) return;
      status = `Selected ${match.patient_id} in ${match.dataset_label}. Details are in Timeline.`; render();
    } catch (error) {
      if (ticket === generation && error.name !== 'AbortError') { status = error.message; render(); }
    }
  }
  function searchPatients(changePage = false) {
    previewLabel = '';
    if (!scopeUi.isDirty()) matchCount = '';
    saveStatus = '';
    clearTimeout(timer); controller?.abort(); generation++; loading = false;
    if (!changePage) { pages = [{}]; pageIndex = 0; }
    nextPage = null;
    if (state.loadInFlight) { status = 'Applying workspace selection…'; render(); return; }
    if (!scope()) { matches = []; status = 'Select and apply a dataset first.'; render(); return; }
    const preview = scopeUi.isDirty();
    if (preview && scopeUi.getSnapshot().hasValidation) { matches = []; status = 'Complete the filter to preview patients.'; render(); return; }
    status = preview ? 'Finding matching patients…' : 'Loading patients in scope…'; loading = true; render();
    const ticket = generation, selectedScope = scope();
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        let data;
        if (preview) {
          const {clinical_labels, ...filters} = scopeUi.getDraft();
          const query = new URLSearchParams({sort_by:sortBy, direction:sortDirection, ...pages[pageIndex]});
          const response = await fetch('/cohort-builder/preview?' + query, {method:'POST', signal:controller.signal,
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({workspace:selectedScope, ...filters})});
          data = await response.json();
          if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Patient preview unavailable.');
        } else data = await request('search', {workspace:selectedScope, sort_by:sortBy, direction:sortDirection, ...pages[pageIndex]}, controller.signal);
        if (ticket !== generation || selectedScope !== scope()) return;
        matches = data.matches;
        const activeScope = state.activePatientScope?.workspace === selectedScope ? state.activePatientScope : null;
        if (Number.isInteger(activeScope?.summary?.workspace_patient_count)) workspaceTotal = activeScope.summary.workspace_patient_count;
        if (!preview && !state.activePatientScope && Number.isInteger(data.total)) workspaceTotal = data.total;
        if (!preview && Number.isInteger(data.total)) matchCount = patientScopeLabel(data.total, workspaceTotal);
        saveLabel = Number.isInteger(data.total) ? `Save ${data.total.toLocaleString()} ${data.total === 1 ? 'patient' : 'patients'} as cohort` : 'Save filtered patients as cohort';
        nextPage = data.next || null;
        status = matches.length ? `Page ${pageIndex + 1} · ${matches.length} ${matches.length === 1 ? 'patient' : 'patients'}` : 'No matching patients in the active datasets.';
        if (preview) previewLabel = `Preview: ${data.total} matching ${data.total === 1 ? 'patient' : 'patients'}`;
      } catch (error) {
        if (ticket === generation && error.name !== 'AbortError') { loadedScope = null; matches = []; status = error.message; }
      } finally { if (ticket === generation) { loading = false; render(); } }
    }, 200);
  }
  async function useFilteredPatients() {
    if (saving || loading || scopeUi.isDirty() || scopeUi.isBusy() || !matches.length) return;
    saving = true;
    const ticket = generation, selectedScope = scope();
    const isCurrent = () => ticket === generation && selectedScope === scope();
    saveStatus = 'Collecting all matching patients…'; render();
    try {
      const active = state.activePatientScope?.workspace === scope() ? state.activePatientScope : null;
      const data = active ? active.selection : await request('selection', {workspace:selectedScope});
      if (!isCurrent()) throw new Error('Filters or workspace changed. Please try again.');
      const members = data.members || [];
      if (!members.length) throw new Error('No matching patients.');
      const saved = await saveIdsAsCohort({members, sourceKind:'manual', statusTarget:'none', isCurrent,
        sourcePrompt:active?.selection.source?.prompt || 'All workspace patients'});
      saveStatus = !isCurrent() ? 'Filters or workspace changed. Please save again.'
        : saved ? `Saved ${members.length} patients. Find the cohort in Cohorts.` : 'Cohort was not saved.';
    } catch (error) {
      if (isCurrent()) saveStatus = error.message || 'Unable to save cohort.';
    } finally { saving = false; render(); }
  }
  window.addEventListener('cohortome:workspace-changing', reset);
  render();
  return {refresh};
}
