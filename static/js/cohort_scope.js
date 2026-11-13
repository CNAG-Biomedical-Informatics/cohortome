import { modalityLabel } from './modalities.js';

const copy = value => JSON.parse(JSON.stringify(value));
export const emptyCohortDraft = () => ({q:'', diseases:[], sample_origin:'', clinical_filters:[],
  fingerprint:'', modalities:[], exact:false, cohort_id:'', clinical_labels:[], base_members:null, source_label:''});
// UI labels and the catalogue fingerprint are not filter conditions themselves.
export function cohortDraftKey(draft) {
  const {clinical_labels, fingerprint, source_label, ...conditions} = draft;
  return JSON.stringify(conditions);
}

export function createCohortScopeUi({state, escapeHtml: esc, renderGlobalContext = () => {}}) {
  let draft = emptyCohortDraft(), applied = emptyCohortDraft(), busy = false;
  let revision = 0, generation = 0, controller, error = '', errorStatus = 0;
  const validation = new Map(), hosts = new Set(), listeners = new Set();
  const workspace = () => String(state.currentDatasetScopeId || '');
  const isDirty = () => cohortDraftKey(draft) !== cohortDraftKey(applied);
  const view = () => ({draft:copy(draft), applied:copy(applied), dirty:isDirty(), busy,
    error, errorStatus, validation:[...validation.values()].find(Boolean) || ''});
  function notify(reason) {
    render();
    for (const listener of listeners) listener(view(), reason);
  }
  function patch(changes) {
    draft = {...draft, ...copy(changes)}; revision++; error = ''; errorStatus = 0; notify('draft');
  }
  function setValidation(owner, message = '') {
    if (validation.get(owner) === message) return;
    if (message) validation.set(owner, message); else validation.delete(owner);
    notify('validation');
  }
  function chips() {
    const entries = [];
    if (draft.base_members !== null) entries.push({label:draft.source_label || `${draft.base_members.length} selected patients`, field:'base_members'});
    if (draft.q) entries.push({label:`ID: ${draft.q}`, field:'q'});
    draft.diseases.forEach((value, index) => entries.push({label:value, field:'diseases', index}));
    if (draft.sample_origin) entries.push({label:`Sample origin: ${draft.sample_origin}`, field:'sample_origin'});
    draft.clinical_filters.forEach((rule, index) => entries.push({label:draft.clinical_labels[index] || `Clinical filter ${index + 1}`, field:'clinical_filters', index}));
    draft.modalities.forEach((value, index) => entries.push({label:value === 'dicom' ? 'Imaging studies'
      : value === 'imaging' ? 'Imaging-derived' : modalityLabel(value), field:'modalities', index}));
    if (draft.exact) entries.push({label:'Only selected data types', field:'exact'});
    if (draft.cohort_id) entries.push({label:(state.savedCohorts || []).find(c => c.id === draft.cohort_id)?.name || 'Saved cohort', field:'cohort_id'});
    return entries;
  }
  function render() {
    const current = state.activePatientScope?.workspace === workspace() ? state.activePatientScope : null;
    const count = current?.selection?.patient_count ?? current?.selection?.members?.length;
    const scopeLabel = current ? `${Number(count || 0).toLocaleString()} patients in scope` : 'Full workspace';
    const issue = error || [...validation.values()].find(Boolean) || '';
    for (const host of hosts) {
      if (!host.isConnected) { hosts.delete(host); continue; }
      host.innerHTML = `<div class="cohort-scope-filters" aria-label="Shared draft filters">${chips().map(chip =>
        `<button type="button" class="query-chip" data-scope-field="${esc(chip.field)}" ${chip.index === undefined ? '' : `data-scope-index="${chip.index}"`} aria-label="Remove filter: ${esc(chip.label)}">${esc(chip.label)} <span aria-hidden="true">×</span></button>`).join('') || '<span class="section-note">No filters</span>'}</div>
        <div class="cohort-scope-actions"><span class="cohort-scope-state">${esc(scopeLabel)}</span>
        <span class="cohort-scope-pending" ${isDirty() ? '' : 'hidden'}>Unapplied changes</span>
        <button type="button" class="primary-btn" data-scope-apply ${busy || state.loadInFlight || !isDirty() || validation.size || !workspace() ? 'disabled' : ''}>${busy ? 'Applying…' : 'Apply to scope'}</button>
        <button type="button" class="query-chip" data-scope-discard ${!isDirty() && !validation.size ? 'hidden' : ''} ${busy ? 'disabled' : ''}>Discard changes</button>
        <button type="button" class="query-chip" data-scope-clear ${!chips().length ? 'hidden' : ''}>Clear filters</button></div>
        <p class="cohort-scope-message" role="status" ${issue ? '' : 'hidden'}>${esc(issue)}</p>`;
      host.querySelector('[data-scope-apply]').onclick = () => void apply();
      host.querySelector('[data-scope-discard]').onclick = discard;
      host.querySelector('[data-scope-clear]').onclick = () => {
        validation.clear(); draft = emptyCohortDraft(); revision++; error = ''; notify('clear');
      };
      host.querySelectorAll('[data-scope-field]').forEach(button => button.onclick = () => {
        const field = button.dataset.scopeField;
        if (button.dataset.scopeIndex !== undefined) {
          const index = Number(button.dataset.scopeIndex), next = draft[field].filter((_, i) => i !== index);
          if (field === 'clinical_filters') {
            validation.delete('clinical');
            patch({clinical_filters:next, clinical_labels:draft.clinical_labels.filter((_, i) => i !== index)});
          } else patch({[field]:next});
        } else patch({[field]:field === 'exact' ? false : field === 'base_members' ? null : ''});
      });
    }
  }
  async function apply() {
    if (busy || state.loadInFlight || !isDirty() || validation.size || !workspace()) return false;
    const submitted = copy(draft);
    const {clinical_labels, ...filters} = submitted;
    return applyRequest('/cohort-builder/apply', filters, submitted);
  }
  async function applySelection(detail) {
    if (busy || state.loadInFlight || !workspace()) return false;
    const {members, patient_ids, result_handle, cohort_id, label} = detail;
    return applyRequest('/cohort-builder/apply-selection', {members, patient_ids, result_handle, cohort_id, label},
      {...emptyCohortDraft(), source_label:detail.label || 'Selected patients'}, true);
  }
  async function applyRequest(url, filters, submitted, handoff = false) {
    const ticket = ++generation, edited = revision, selectedWorkspace = workspace();
    busy = true; error = ''; errorStatus = 0; controller = new AbortController(); notify('applying');
    const timeout = setTimeout(() => controller?.abort(), 120000);
    try {
      const response = await fetch(url, {method:'POST', signal:controller.signal,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({workspace:selectedWorkspace, ...filters})});
      const payload = await response.json();
      if (!response.ok) {
        const failure = new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to apply filters. The previous scope is unchanged.');
        failure.status = response.status; throw failure;
      }
      if (ticket !== generation || selectedWorkspace !== workspace()) return false;
      if (edited !== revision) { error = 'Filters changed while calculating. Apply the latest changes when ready.'; return false; }
      if (payload.workspace !== selectedWorkspace || !Object.hasOwn(payload, 'selection')
          || (payload.selection !== null && !Array.isArray(payload.selection?.members))) {
        throw new Error('Invalid scope response. The previous scope is unchanged.');
      }
      if (handoff) {
        submitted.base_members = payload.selection?.members ?? null;
        draft = copy(submitted); validation.clear();
      }
      applied = submitted;
      state.activePatientScope = payload.selection === null ? null : {
        workspace:selectedWorkspace, selection:payload.selection, summary:payload.summary, assays:payload.assays};
      state.clinicalSelection = payload.selection === null ? null : {workspace:selectedWorkspace,
        status:'ready', label:payload.selection.source?.prompt || 'Applied filters', data:payload.summary};
      window.dispatchEvent(new CustomEvent('cohortome:scope-applied', {detail:state.activePatientScope}));
      renderGlobalContext(); notify('applied');
      return true;
    } catch (failure) {
      if (ticket === generation && selectedWorkspace === workspace()) {
        error = failure.name === 'AbortError' ? 'Applying filters timed out. The previous scope is unchanged.' : failure.message;
        errorStatus = failure.status || 0;
      }
      return false;
    } finally {
      clearTimeout(timeout);
      if (ticket === generation) { busy = false; notify('settled'); }
    }
  }
  function discard() {
    if (busy) return;
    draft = copy(applied); validation.clear(); revision++; error = ''; notify('discard');
  }
  function reset() {
    generation++; controller?.abort(); busy = false; revision++;
    draft = emptyCohortDraft(); applied = emptyCohortDraft(); validation.clear(); error = '';
    state.activePatientScope = null; state.clinicalSelection = null; notify('reset');
  }
  window.addEventListener('cohortome:workspace-changing', () => {
    // A workspace switch can fail. Cancel in-flight work, but do not discard
    // the previous workspace's active scope or the user's unsubmitted filters.
    generation++; revision++; controller?.abort(); busy = false; error = ''; errorStatus = 0;
    notify('workspace-changing');
  });
  window.addEventListener('cohortome:workspace-committed', reset);
  window.addEventListener('cohortome:workspace-settled', () => notify('workspace-settled'));
  const api = {getDraft:() => copy(draft), getAppliedDraft:() => copy(applied), getError:() => error, patch, setValidation,
    mount(host) {host.classList.add('cohort-scope-bar'); hosts.add(host); render();},
    subscribe(listener) {listeners.add(listener); return () => listeners.delete(listener);},
    apply, applySelection, clearScope() {
      if (busy) return Promise.resolve(false);
      draft = emptyCohortDraft(); validation.clear(); revision++; error = ''; notify('clear');
      return isDirty() ? apply() : Promise.resolve(true);
    }, discard, reset, isDirty, isBusy:() => busy};
  state.cohortScope = api;
  return api;
}
