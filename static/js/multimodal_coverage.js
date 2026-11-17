import { modalityLabel, modalityKey } from './modalities.js';
import { patientInventoryMarkup } from './patient_inventory.js';
import { sortDiseaseOptions } from './shared.js';
import { createMultimodalView } from './react/ui.js';

// DICOM study records and quantitative imaging measurements are different inputs.
const key = value => ['dicom', 'imaging'].includes(value) ? value
  : modalityKey(value) === 'assay' ? value : modalityKey(value);
const label = value => value === 'dicom' ? 'Imaging studies' : value === 'imaging' ? 'Imaging-derived' : modalityLabel(value);
export function coverageGroups(patients) {
  const groups = new Map();
  for (const patient of patients) {
    const modalities = [...new Set(patient.modalities.map(key))].sort();
    const identity = JSON.stringify(modalities);
    if (!groups.has(identity)) groups.set(identity, {modalities, patients: []});
    groups.get(identity).patients.push(patient);
  }
  return [...groups.values()].sort((a, b) => b.modalities.filter(m => m !== 'clinical').length - a.modalities.filter(m => m !== 'clinical').length
    || b.patients.length - a.patients.length || a.modalities.join().localeCompare(b.modalities.join()));
}

export function createMultimodalCoverage({state, escapeHtml: esc, saveIdsAsCohort, renderGlobalContext = () => {}}) {
  let generation = 0, controller, unsubscribe, view, cancelDetails;
  function reset() {
    generation++; controller?.abort(); unsubscribe?.(); unsubscribe = null;
    cancelDetails?.(); cancelDetails = null; view?.destroy(); view = null;
    const badge = document.getElementById('multimodalHeadingCount');
    if (badge) badge.textContent = '';
  }
  window.addEventListener('cohortome:workspace-changing', () => {reset(); renderGlobalContext();});
  async function load(host, scope) {
    reset();
    const ticket = generation;
    controller = new AbortController();
    view = createMultimodalView({host, scopeUi:state.cohortScope});
    view.render({phase:'loading'});
    try {
      const response = await fetch('/patient-overview/coverage?' + new URLSearchParams({workspace:scope}), {signal:controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Patient coverage is unavailable.');
      if (ticket !== generation || !host.isConnected) return;
      initialize(host, data, scope, ticket);
    } catch (error) {
      if (ticket !== generation || !host.isConnected || error.name === 'AbortError') return;
      view.render({phase:'error', error:error.message}, {retry:() => load(host, scope)});
    }
  }
  function initialize(host, data, scope, ticket) {
    const scopeUi = state.cohortScope;
    const live = () => ticket === generation && host.isConnected;
    const patch = changes => { if (live()) scopeUi.patch(changes); };
    const allPatients = data.patients || [];
    const modalities = [...new Set(coverageGroups(allPatients).flatMap(group => group.modalities))].sort();
    const labels = Object.fromEntries(modalities.map(value => [value, label(value)]));
    // Coverage is patient-level: sample cohorts are intentionally not offered.
    const cohorts = (state.savedCohorts || []).filter(cohort => !cohort.sample_count && cohort.members?.length);
    const patientKey = patient => JSON.stringify([patient.dataset_id, patient.patient_id]);
    const diseasePatients = new Map();
    for (const patient of allPatients) {
      for (const disease of patient.diseases || []) {
        if (!diseasePatients.has(disease)) diseasePatients.set(disease, new Set());
        diseasePatients.get(disease).add(patientKey(patient));
      }
    }
    const diseases = sortDiseaseOptions([...diseasePatients].map(([disease, patients]) => ({disease, patient_count:patients.size})));
    let page = 0, showAllDiseases = false, saving = false, saveStatus = '', groups = [], patients = [];
    let inspector = null, detailController, detailGeneration = 0, appliedRevision = 0;
    const clearInspector = () => {detailGeneration++; detailController?.abort(); inspector = null;};
    cancelDetails = clearInspector;
    const actions = {
      editPatients:() => document.getElementById('dashboardPatientsBtn')?.click(),
      clinical:() => document.getElementById('dashboardClinicalBtn')?.click(),
      mode:value => patch({exact:value === 'exact'}),
      cohort:value => {if (value !== '__selection__') patch({cohort_id:value, base_members:null, source_label:''});},
      modality:(value, checked) => {
        const selected = new Set(scopeUi.getDraft().modalities);
        if (checked) selected.add(value); else selected.delete(value);
        patch({modalities:modalities.filter(modality => selected.has(modality))});
      },
      combination:values => patch({modalities:values.slice(), exact:true}),
      disease:value => {
        const selected = new Set(scopeUi.getDraft().diseases);
        if (!value) selected.clear();
        else if (selected.has(value)) selected.delete(value); else selected.add(value);
        patch({diseases:[...selected]});
      },
      toggleDiseases:() => {showAllDiseases = !showAllDiseases; render();},
      page:value => {
        page = Math.max(0, Math.min(value, Math.max(0, Math.ceil(patients.length / 25) - 1)));
        clearInspector(); render();
      },
      inspect:inspectPatient,
      save:savePatients,
    };
    function render() {
      if (!live()) return;
      const badge = document.getElementById('multimodalHeadingCount');
      if (badge) badge.textContent = `${patients.length} patients in scope`;
      view.render({phase:'ready', draft:scopeUi.getDraft(), cohorts, modalities, labels, diseases, showAllDiseases,
        groups, patients, page, saveStatus, inspector, warnings:data.warnings || [],
        canSave:patients.length > 0 && !saving && !scopeUi.isDirty() && !scopeUi.isBusy() && !state.loadInFlight}, actions);
    }
    function updateSelection() {
      const active = state.activePatientScope?.workspace === scope ? state.activePatientScope : null;
      const allowed = active ? new Set(active.selection.members.map(patientKey)) : null;
      groups = coverageGroups(allowed ? allPatients.filter(patient => allowed.has(patientKey(patient))) : allPatients);
      patients = groups.flatMap(group => group.patients);
      page = 0; saveStatus = ''; appliedRevision++; clearInspector(); render();
    }
    async function savePatients() {
      if (!live() || saving || !patients.length || scopeUi.isDirty() || scopeUi.isBusy() || state.loadInFlight) return;
      const revision = appliedRevision;
      const isCurrent = () => live() && revision === appliedRevision && !scopeUi.isDirty() && !scopeUi.isBusy();
      const active = state.activePatientScope?.workspace === scope ? state.activePatientScope : null;
      const members = patients.map(patient => ({dataset_id:patient.dataset_id, patient_id:patient.patient_id}));
      saving = true; saveStatus = 'Saving…'; render();
      try {
        const saved = await saveIdsAsCohort({members, sourceKind:'manual', statusTarget:'none', isCurrent,
          sourcePrompt:active?.selection.source?.prompt || 'All workspace patients'});
        if (isCurrent()) saveStatus = saved ? 'Cohort saved. Find it in Cohorts.' : 'Cohort was not saved.';
        else if (live() && revision === appliedRevision) saveStatus = 'Filters changed. Please save again.';
      } catch (error) {
        if (isCurrent()) saveStatus = error.message || 'Unable to save cohort.';
      } finally {saving = false; render();}
    }
    async function inspectPatient(patient) {
      if (!live() || !patient.has_clinical || !patients.some(item => patientKey(item) === patientKey(patient))) return;
      clearInspector(); detailController = new AbortController();
      const detailTicket = detailGeneration;
      const current = () => live() && detailTicket === detailGeneration;
      inspector = {message:'Loading sample inventory…'}; render();
      try {
        const response = await fetch('/patient-overview/detail?' + new URLSearchParams({workspace:scope,
          dataset_id:patient.dataset_id, patient_id:patient.patient_id}), {signal:detailController.signal});
        const payload = await response.json();
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Inventory unavailable.');
        if (!current()) return;
        inspector = {html:`<h4>${esc(patient.patient_id)} · ${esc(patient.dataset_label)}</h4>${patientInventoryMarkup(payload.samples || [], esc)}${(payload.warnings || []).map(warning => `<p>${esc(warning)}</p>`).join('')}`};
        render();
      } catch (error) {
        if (current() && error.name !== 'AbortError') {inspector = {message:error.message}; render();}
      }
    }
    unsubscribe = scopeUi.subscribe((_snapshot, reason) => {
      if (!live()) return;
      if (reason === 'applied') updateSelection(); else render();
    });
    updateSelection();
  }
  return {load, reset};
}
