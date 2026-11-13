import { modalityIcon, modalityLabel, modalityKey, modalityColor } from './modalities.js';
import { patientInventoryMarkup } from './patient_inventory.js';
import { sortDiseaseOptions } from './shared.js';

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
  let generation = 0, controller, unsubscribe;
  function reset() { generation++; controller?.abort(); unsubscribe?.(); const badge = document.getElementById('multimodalHeadingCount'); if (badge) badge.textContent = ''; }
  window.addEventListener('cohortome:workspace-changing', () => {
    reset(); renderGlobalContext();
  });
  async function load(host, scope) {
    reset();
    const ticket = generation;
    controller = new AbortController();
    host.innerHTML = '<p class="section-note">Loading patient coverage…</p>';
    try {
      const response = await fetch('/patient-overview/coverage?' + new URLSearchParams({workspace:scope}), {signal:controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Patient coverage is unavailable.');
      if (ticket !== generation || !host.isConnected) return;
      render(host, data, scope, ticket);
    } catch (error) {
      if (ticket !== generation || error.name === 'AbortError') return;
      host.innerHTML = `<p>${esc(error.message)}</p><button class="query-chip" type="button">Retry coverage</button>`;
      host.querySelector('button').onclick = () => load(host, scope);
    }
  }
  function render(host, data, scope, ticket) {
    const scopeUi = state.cohortScope;
    const allPatients = data.patients || [];
    let groups = coverageGroups(allPatients);
    const modalities = [...new Set(groups.flatMap(g => g.modalities))].sort();
    let page = 0;
    // Coverage is patient-level: sample cohorts are intentionally not offered.
    const cohorts = (state.savedCohorts || []).filter(c => !c.sample_count && c.members?.length);
    const patientKey = p => JSON.stringify([p.dataset_id, p.patient_id]);
    let selectedDiseases = new Set(scopeUi.getDraft().diseases), showAllDiseases = false;
    host.innerHTML = `<div class="coverage-scope-bar"></div><section class="coverage-filter-section"><h3>Filter patients</h3>
      <div class="coverage-filter-row">
      <label class="coverage-match-mode"><span>Patient group</span><select class="coverage-cohort" aria-label="Patient group" ${!cohorts.length ? 'disabled' : ''}><option value="">All patients in this workspace</option>${cohorts.map(c => `<option value="${esc(c.id)}">${esc(c.name)} · ${c.patient_count} patients</option>`).join('')}</select></label>
      <label class="coverage-match-mode"><span>Match</span><select class="coverage-mode"><option value="includes">At least these types</option><option value="exact">Only these types</option></select></label>
      </div>
      <div class="coverage-start-description"><button type="button" class="query-chip" data-edit-patient-filters>Edit clinical filters in Patients</button></div>
      <div class="coverage-clinical-section"><h4>Diseases</h4><div class="coverage-diseases" role="group" aria-label="Disease filters"></div>
      </div><div class="coverage-modality-section"><h4>Required data</h4>
      <div class="coverage-selectors" role="group" aria-label="Required data types">${modalities.map(m => `<label><input type="checkbox" value="${esc(m)}">${modalityIcon(m)}<span>${esc(label(m))}</span></label>`).join('')}</div>
      </div></section>
      <div class="coverage-result" aria-live="polite"></div>
      <section class="coverage-data-section">
      <h4>Available combinations</h4><p class="section-note">Filled dots show available data. Click a count to select a combination.</p>
      <div class="assay-table-wrap coverage-intersections"></div>
      <details class="coverage-patients"><summary>Matching patients</summary><div class="coverage-patient-list"></div></details>
      <div class="coverage-inspector"></div>
      </section>
      <details><summary>How matching works</summary>
      <p>Patient-level matches—not necessarily the same specimen or visit.</p>
      <p>At least these types allows additional data. Only these types excludes additional non-clinical types. Clinical records are optional unless Clinical is selected.</p>
      <p>Each chart row is a recorded combination. Combinations with more non-clinical types appear first. Patient IDs remain separate across datasets. Imaging studies means a listed study, not confirmed image access.</p></details>
      ${(data.warnings || []).length ? `<details><summary>Coverage limitations (${data.warnings.length})</summary>${data.warnings.map(w => `<p>${esc(w)}</p>`).join('')}</details>` : ''}`;
    const result = host.querySelector('.coverage-result');
    const list = host.querySelector('.coverage-patient-list');
    const intersection = host.querySelector('.coverage-intersections');
    const cohortSelect = host.querySelector('.coverage-cohort');
    const diseaseFilters = host.querySelector('.coverage-diseases');
    scopeUi.mount(host.querySelector('.coverage-scope-bar'));
    host.querySelector('[data-edit-patient-filters]').onclick = () => document.getElementById('dashboardPatientsBtn')?.click();
    function renderDiseases() {
      // Choices stay workspace-wide while the combined filter set is drafted.
      const diseasePatients = new Map();
      for (const patient of allPatients) {
        for (const disease of patient.diseases || []) {
          if (!diseasePatients.has(disease)) diseasePatients.set(disease, new Set());
          diseasePatients.get(disease).add(patientKey(patient));
        }
      }
      const diseases = sortDiseaseOptions([...diseasePatients].map(([disease, patients]) =>
        ({disease, patient_count:patients.size}))).map(item => item.disease);
      diseaseFilters.innerHTML = `<button type="button" class="query-chip query-chip-deterministic" data-disease="" aria-pressed="${!selectedDiseases.size}">All diseases</button>`
        + (showAllDiseases ? diseases : diseases.filter((d, index) => index < 8 || selectedDiseases.has(d))).map(d => `<button type="button" class="query-chip query-chip-deterministic" data-disease="${esc(d)}" aria-pressed="${selectedDiseases.has(d)}" title="Workspace patients with this disease">${esc(d)} <span class="query-chip badge">${diseasePatients.get(d).size}</span></button>`).join('')
        + (diseases.length > 8 ? `<button type="button" class="query-chip" data-more-diseases>${showAllDiseases ? 'Show fewer' : 'More diseases…'}</button>` : '')
        + (selectedDiseases.size > 1 ? '<span class="section-note">Any selected disease</span>' : '');
      diseaseFilters.hidden = !diseases.length;
      diseaseFilters.closest('.coverage-clinical-section').hidden = !diseases.length;
    }
    function update() {
      const active = state.activePatientScope?.workspace === scope ? state.activePatientScope : null;
      const allowed = active ? new Set(active.selection.members.map(patientKey)) : null;
      groups = coverageGroups(allowed ? allPatients.filter(p => allowed.has(patientKey(p))) : allPatients);
      const matches = groups;
      const patients = matches.flatMap(g => g.patients);
      const badge = document.getElementById('multimodalHeadingCount');
      if (badge) badge.textContent = `${patients.length} patients in scope`;
      result.innerHTML = `<strong>${patients.length} patients in scope</strong><button type="button" class="coverage-save" title="Save the applied patient scope for later use" ${!patients.length || scopeUi.isDirty() || scopeUi.isBusy() ? 'disabled' : ''}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 3h12l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8"/></svg>Save ${patients.length} ${patients.length === 1 ? 'patient' : 'patients'} as a cohort</button><span class="coverage-save-status" role="status"></span>`;
      result.querySelector('button').onclick = async event => {
        const button = event.currentTarget;
        const status = result.querySelector('.coverage-save-status');
        button.disabled = true;
        status.textContent = 'Saving…';
        const saved = await saveIdsAsCohort({members:patients.map(p => ({dataset_id:p.dataset_id, patient_id:p.patient_id})), sourceKind:'manual', statusTarget:'none', isCurrent:() => ticket === generation && button.isConnected && !scopeUi.isDirty(), sourcePrompt:active?.selection.source?.prompt || 'All workspace patients'});
        if (ticket !== generation || !button.isConnected) return;
        status.textContent = saved ? 'Cohort saved. Find it in Cohorts.' : 'Cohort was not saved.';
        button.disabled = scopeUi.isDirty() || scopeUi.isBusy();
      };
      const clinicalButton = document.createElement('button');
      clinicalButton.type = 'button'; clinicalButton.className = 'query-chip';
      clinicalButton.textContent = 'View Clinical';
      clinicalButton.onclick = () => document.getElementById('dashboardClinicalBtn')?.click();
      result.append(clinicalButton);
      const max = Math.max(1, ...matches.map(g => g.patients.length));
      intersection.innerHTML = `<table class="assay-table"><thead><tr><th>Patients</th>${modalities.map(m => `<th>${modalityIcon(m)} ${esc(label(m))}</th>`).join('')}</tr></thead><tbody>${matches.map(g => `<tr class="coverage-match"><td><button class="query-chip" type="button" data-combination="${groups.indexOf(g)}" aria-label="${esc(g.modalities.map(label).join(' + '))}: ${g.patients.length} patients">${g.patients.length}</button><span class="coverage-bar" style="width:${g.patients.length / max * 85}px" aria-hidden="true"></span></td>${modalities.map(m => `<td class="coverage-dot" style="color:${modalityColor(m)}"><span aria-label="${g.modalities.includes(m) ? 'Available' : 'Not recorded'}">${g.modalities.includes(m) ? '●' : '·'}</span></td>`).join('')}</tr>`).join('')}</tbody></table>`;
      if (!matches.length) intersection.innerHTML = '<p class="empty">No matches. Broaden the cohort, disease or data-type filters.</p>';
      intersection.querySelectorAll('[data-combination]').forEach(button => button.onclick = () => {
        scopeUi.patch({modalities:groups[Number(button.dataset.combination)].modalities.slice(), exact:true});
      });
      const pages = Math.max(1, Math.ceil(patients.length / 25)); page = Math.min(page, pages - 1);
      list.innerHTML = `<div class="assay-table-wrap"><table class="assay-table"><thead><tr><th>Patient</th><th>Dataset</th><th></th></tr></thead><tbody>${patients.slice(page * 25, (page + 1) * 25).map((p, i) => `<tr><td>${esc(p.patient_id)}</td><td>${esc(p.dataset_label)}</td><td><button class="query-chip" type="button" data-patient="${page * 25 + i}" ${p.has_clinical ? '' : 'disabled'}>Inspect</button>${p.has_clinical ? '' : ' No clinical record'}</td></tr>`).join('')}</tbody></table></div><button class="query-chip coverage-prev" ${page === 0 ? 'disabled' : ''}>Previous</button> Page ${page + 1} of ${pages} <button class="query-chip coverage-next" ${page + 1 === pages ? 'disabled' : ''}>Next</button>`;
      list.querySelector('.coverage-prev').onclick = () => {page--; update();};
      list.querySelector('.coverage-next').onclick = () => {page++; update();};
      host.querySelector('.coverage-inspector').replaceChildren();
      list.querySelectorAll('[data-patient]').forEach(button => button.onclick = async () => {
        const p = patients[Number(button.dataset.patient)];
        const target = document.createElement('section');
        host.querySelector('.coverage-inspector').replaceChildren(target);
        target.textContent = 'Loading sample inventory…';
        try {
          const response = await fetch('/patient-overview/detail?' + new URLSearchParams({workspace:scope, dataset_id:p.dataset_id, patient_id:p.patient_id}));
          const payload = await response.json();
          if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Inventory unavailable.');
          if (ticket !== generation || !target.isConnected) return;
          target.innerHTML = `<h4>${esc(p.patient_id)} · ${esc(p.dataset_label)}</h4>${patientInventoryMarkup(payload.samples || [], esc)}${(payload.warnings || []).map(w => `<p>${esc(w)}</p>`).join('')}`;
        } catch (error) {if (ticket === generation && target.isConnected) target.textContent = error.message;}
      });
    }
    host.querySelectorAll('.coverage-selectors input').forEach(input => input.onchange = () => {
      scopeUi.patch({modalities:[...host.querySelectorAll('.coverage-selectors input:checked')].map(i => i.value)});
    });
    host.querySelector('.coverage-mode').onchange = event => scopeUi.patch({exact:event.target.value === 'exact'});
    cohortSelect.onchange = () => {
      if (cohortSelect.value !== '__selection__') scopeUi.patch({cohort_id:cohortSelect.value, base_members:null, source_label:''});
    };
    diseaseFilters.onclick = event => {
      if (event.target.closest('[data-more-diseases]')) { showAllDiseases = !showAllDiseases; renderDiseases(); return; }
      const button = event.target.closest('[data-disease]');
      if (!button || button.disabled) return;
      const disease = button.dataset.disease;
      if (!disease) selectedDiseases.clear();
      else if (selectedDiseases.has(disease)) selectedDiseases.delete(disease);
      else selectedDiseases.add(disease);
      scopeUi.patch({diseases:[...selectedDiseases]});
    };
    function syncDraft(snapshot, reason) {
      const draft = snapshot.draft;
      selectedDiseases = new Set(draft.diseases); renderDiseases();
      let selectionOption = cohortSelect.querySelector('option[value="__selection__"]');
      if (draft.base_members !== null) {
        if (!selectionOption) {
          selectionOption = document.createElement('option'); selectionOption.value = '__selection__';
          cohortSelect.append(selectionOption);
        }
        selectionOption.textContent = `${draft.base_members.length} selected patients`;
      } else selectionOption?.remove();
      cohortSelect.disabled = !cohorts.length && draft.base_members === null;
      cohortSelect.value = draft.base_members !== null ? '__selection__' : draft.cohort_id;
      host.querySelector('.coverage-mode').value = draft.exact ? 'exact' : 'includes';
      host.querySelectorAll('.coverage-selectors input').forEach(input => {input.checked = draft.modalities.includes(input.value);});
      const save = result.querySelector('.coverage-save');
      if (save) save.disabled = snapshot.dirty || snapshot.busy || !groups.some(group => group.patients.length);
      if (reason === 'applied') {page = 0; update();}
    }
    unsubscribe = scopeUi.subscribe((snapshot, reason) => {
      if (ticket === generation && host.isConnected) syncDraft(snapshot, reason);
    });
    syncDraft({draft:scopeUi.getDraft(), dirty:scopeUi.isDirty(), busy:scopeUi.isBusy()}, 'initial');
    update();
  }
  return {load};
}
