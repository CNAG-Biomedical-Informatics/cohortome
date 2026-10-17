// Icons accompany text labels: colour is never the only modality cue.
import { modalityKey, modalityIcon, modalityLabel } from './modalities.js';
const links = {sample_metadata_file:'Metadata table', exact_sample_id:'Exact identifier', sample_id_prefix:'Dataset ID convention'};

export function patientInventoryMarkup(rows, escapeHtml) {
  const esc = value => escapeHtml(String(value || ''));
  const missing = '<span class="inventory-missing" title="Not recorded" aria-label="Not recorded">—</span>';
  const field = value => value ? esc(value) : missing;
  const groups = new Map();
  for (const row of rows) {
    if (!groups.has(row.sample_id)) groups.set(row.sample_id, []);
    groups.get(row.sample_id).push(row);
  }
  const bodies = [...groups].map(([sample, assays]) => `<tbody>${assays.map((r, i) => {
    const key = modalityKey(r.modality);
    return `<tr>${i === 0 ? `<th scope="rowgroup" rowspan="${assays.length}" class="inventory-sample"><span class="inventory-sample-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3h6M10 3v6L6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2L14 9V3M8 15h8"/></svg><code>${esc(sample)}</code></span><small>${assays.length} assay${assays.length === 1 ? '' : 's'}</small></th>` : ''}
      <td><div class="inventory-assay"><span class="inventory-modality-icon" data-modality="${key}" aria-hidden="true">${modalityIcon(key, '')}</span><div><span class="inventory-modality">${esc(modalityLabel(r.modality))}</span><small>${esc(r.assay)}</small></div></div>${r.sample_clarid ? `<small>ClarID: ${esc(r.sample_clarid)}</small>` : ''}</td>
      <td class="inventory-collection">${r.visit || r.collection_date || r.material ? `<span>${field(r.visit)}</span><small>${field(r.collection_date)}</small><small>${field(r.material)}</small>` : missing}</td>
      <td>${esc(String(r.data_type || 'Not recorded').replaceAll('_', ' '))}</td>
      <td><span class="inventory-link">${esc(links[r.linkage] || 'Not recorded')}</span></td></tr>`;
  }).join('')}</tbody>`).join('');
  return `<div class="patient-inventory-scroll" tabindex="0" role="region" aria-label="Available samples and assays"><table class="patient-inventory"><caption>Available assay data grouped by sample identifier</caption><thead><tr><th scope="col">Sample</th><th scope="col">Assay</th><th scope="col">Collection<small>Visit · date · material</small></th><th scope="col">Available data</th><th scope="col">Patient link</th></tr></thead>${bodies}</table></div><div class="inventory-legend">— Not recorded. Patient link shows how the dataset connects the sample to this patient.</div>`;
}
