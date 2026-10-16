// Icons accompany text labels: colour is never the only modality cue.
const icons = {
  transcriptomics: '<path d="M7 3c0 4 10 5 10 9s-10 5-10 9M17 3c0 4-10 5-10 9s10 5 10 9M8 6h8M8 18h8M9 10h6M9 14h6"/>',
  methylation: '<path d="M7 3v7l-4 8a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-4-8V3M5 3h10M6 15h8"/><circle cx="19" cy="6" r="3"/>',
  flow_cytometry: '<circle cx="6" cy="7" r="3"/><circle cx="17" cy="6" r="2"/><circle cx="13" cy="16" r="4"/><circle cx="4" cy="18" r="1"/>',
  serology: '<path d="M12 3S5 11 5 15a7 7 0 0 0 14 0c0-4-7-12-7-12Z"/><path d="M9 16a3 3 0 0 0 3 3"/>',
  proteomics: '<circle cx="5" cy="6" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="10" cy="19" r="3"/><path d="m8 6 7 1M6 9l3 7m7-6-4 6"/>',
  genotyping: '<path d="M7 3c0 4 10 5 10 9s-10 5-10 9M17 3c0 4-10 5-10 9s10 5 10 9M8 6h8M8 18h8"/>',
};
const labels = {transcriptomics:'Transcriptomics', methylation:'Methylation', flow_cytometry:'Flow cytometry', serology:'Serology', proteomics:'Proteomics', genotyping:'Genotyping', olink:'OLINK'};
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
    const key = Object.hasOwn(labels, r.modality) ? r.modality : 'other';
    const path = icons[key === 'olink' ? 'proteomics' : key] || '<path d="M9 3v8l-5 8a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2l-5-8V3M7 3h10M7 16h10"/>';
    return `<tr>${i === 0 ? `<th scope="rowgroup" rowspan="${assays.length}" class="inventory-sample"><span class="inventory-sample-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3h6M10 3v6L6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2L14 9V3M8 15h8"/></svg><code>${esc(sample)}</code></span><small>${assays.length} assay${assays.length === 1 ? '' : 's'}</small></th>` : ''}
      <td><div class="inventory-assay"><span class="inventory-modality-icon" data-modality="${key}" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${path}</svg></span><div><span class="inventory-modality">${esc(labels[key] || r.modality)}</span><small>${esc(r.assay)}</small></div></div>${r.sample_clarid ? `<small>ClarID: ${esc(r.sample_clarid)}</small>` : ''}</td>
      <td class="inventory-collection">${r.visit || r.collection_date || r.material ? `<span>${field(r.visit)}</span><small>${field(r.collection_date)}</small><small>${field(r.material)}</small>` : missing}</td>
      <td>${esc(String(r.data_type || 'Not recorded').replaceAll('_', ' '))}</td>
      <td><span class="inventory-link">${esc(links[r.linkage] || 'Not recorded')}</span></td></tr>`;
  }).join('')}</tbody>`).join('');
  return `<div class="patient-inventory-scroll" tabindex="0" role="region" aria-label="Available samples and assays"><table class="patient-inventory"><caption>Available assay data grouped by sample identifier</caption><thead><tr><th scope="col">Sample</th><th scope="col">Assay</th><th scope="col">Collection<small>Visit · date · material</small></th><th scope="col">Available data</th><th scope="col">Patient link</th></tr></thead>${bodies}</table></div><div class="inventory-legend">— Not recorded. Patient link shows how the dataset connects the sample to this patient.</div>`;
}
