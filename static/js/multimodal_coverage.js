import { modalityIcon, modalityLabel, modalityKey, modalityColor } from './modalities.js';
import { patientInventoryMarkup } from './patient_inventory.js';

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

export function createMultimodalCoverage({state, escapeHtml: esc, saveIdsAsCohort}) {
  let generation = 0, controller;
  function reset() { generation++; controller?.abort(); }
  window.addEventListener('cohortome:workspace-changing', reset);
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
    const groups = coverageGroups(data.patients || []);
    const modalities = [...new Set(groups.flatMap(g => g.modalities))].sort();
    if (!groups.length) {
      host.innerHTML = '<h3>Find shared coverage</h3><p>No linked patient coverage is available in this workspace.</p>'
        + (data.warnings || []).map(w => `<p>${esc(w)}</p>`).join('');
      return;
    }
    let selected = [], exact = false, page = 0;
    host.innerHTML = `<h3>Find shared coverage</h3>
      <p class="section-note">Choose the data your patients need.</p>
      <div class="coverage-selectors" role="group" aria-label="Required data types">${modalities.map(m => `<label><input type="checkbox" value="${esc(m)}">${modalityIcon(m)}<span>${esc(label(m))}</span></label>`).join('')}</div>
      <label class="coverage-match-mode"><span>Match</span><select class="coverage-mode"><option value="includes">At least these types</option><option value="exact">Only these types</option></select></label>
      <p class="section-note">Patient-level matches—not necessarily the same specimen or visit.</p>
      <div class="coverage-result" aria-live="polite"></div>
      <h4>Available combinations</h4><p class="section-note">Filled dots show available data. Click a count to select a combination.</p>
      <div class="assay-table-wrap coverage-intersections"></div>
      <details class="coverage-patients"><summary>Matching patients</summary><div class="coverage-patient-list"></div></details>
      <div class="coverage-inspector"></div>
      <details><summary>How matching works</summary>
      <p>At least these types allows additional data. Only these types excludes additional non-clinical types. Clinical records are optional unless Clinical is selected.</p>
      <p>Each chart row is a recorded combination. Combinations with more non-clinical types appear first. Patient IDs remain separate across datasets. Imaging studies means a listed study, not confirmed image access.</p></details>
      ${(data.warnings || []).length ? `<details><summary>Coverage limitations (${data.warnings.length})</summary>${data.warnings.map(w => `<p>${esc(w)}</p>`).join('')}</details>` : ''}`;
    const result = host.querySelector('.coverage-result');
    const list = host.querySelector('.coverage-patient-list');
    const intersection = host.querySelector('.coverage-intersections');
    function update() {
      const matches = groups.filter(g => selected.every(m => g.modalities.includes(m))
        && (!exact || g.modalities.every(m => m === 'clinical' || selected.includes(m))));
      const patients = matches.flatMap(g => g.patients);
      result.innerHTML = `<strong>${patients.length} matching patients</strong><button type="button" class="query-chip coverage-save" ${!patients.length ? 'disabled' : ''}>Save cohort</button><span class="coverage-save-status"></span>`;
      result.querySelector('button').onclick = async event => {
        event.target.disabled = true;
        const saved = await saveIdsAsCohort({members:patients.map(p => ({dataset_id:p.dataset_id, patient_id:p.patient_id})), sourceKind:'manual', sourcePrompt:`Multimodal coverage: ${exact ? 'only' : 'at least'} ${selected.map(label).join(', ') || 'no required types'}; Clinical ${selected.includes('clinical') ? 'required' : 'optional'}`});
        if (ticket !== generation || !host.isConnected) return;
        result.querySelector('.coverage-save-status').textContent = saved ? 'Cohort saved.' : 'Cohort was not saved.';
        event.target.disabled = false;
      };
      const max = Math.max(1, ...matches.map(g => g.patients.length));
      intersection.innerHTML = `<table class="assay-table"><thead><tr><th>Patients</th>${modalities.map(m => `<th>${modalityIcon(m)} ${esc(label(m))}</th>`).join('')}</tr></thead><tbody>${matches.map(g => `<tr class="coverage-match"><td><button class="query-chip" type="button" data-combination="${groups.indexOf(g)}" aria-label="${esc(g.modalities.map(label).join(' + '))}: ${g.patients.length} patients">${g.patients.length}</button><span class="coverage-bar" style="width:${g.patients.length / max * 85}px" aria-hidden="true"></span></td>${modalities.map(m => `<td class="coverage-dot" style="color:${modalityColor(m)}"><span aria-label="${g.modalities.includes(m) ? 'Available' : 'Not recorded'}">${g.modalities.includes(m) ? '●' : '·'}</span></td>`).join('')}</tr>`).join('')}</tbody></table>`;
      if (!matches.length) intersection.innerHTML = '<p class="empty">No matches. Remove a type or choose At least these types.</p>';
      intersection.querySelectorAll('[data-combination]').forEach(button => button.onclick = () => {
        selected = groups[Number(button.dataset.combination)].modalities.slice(); exact = true; page = 0;
        host.querySelector('.coverage-mode').value = 'exact';
        host.querySelectorAll('.coverage-selectors input').forEach(input => input.checked = selected.includes(input.value));
        update();
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
      selected = [...host.querySelectorAll('.coverage-selectors input:checked')].map(i => i.value); page = 0; update();
    });
    host.querySelector('.coverage-mode').onchange = event => {exact = event.target.value === 'exact'; page = 0; update();};
    update();
  }
  return {load};
}
