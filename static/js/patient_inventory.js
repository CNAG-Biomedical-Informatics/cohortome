// Icons accompany text labels: colour is never the only modality cue.
import { modalityKey, modalityIcon, modalityLabel } from './modalities.js';
import { clinicalRecordsMarkup } from './clinical_records.js';
const links = {sample_metadata_file:'Metadata table', exact_sample_id:'Exact identifier', sample_id_prefix:'Dataset ID convention'};
const natural = new Intl.Collator(undefined, {numeric:true, sensitivity:'base'});
const byVisit = (a, b) => Number(!a) - Number(!b) || natural.compare(String(a || ''), String(b || ''));

export function patientInventoryMarkup(rows, escapeHtml, clinicalRecords = null) {
  const combined = clinicalRecords !== null;
  const esc = value => escapeHtml(String(value || ''));
  const missing = '<span class="inventory-missing" title="Not recorded" aria-label="Not recorded">—</span>';
  const field = value => value ? esc(value) : missing;
  const groups = new Map();
  for (const row of rows) {
    const key = combined ? JSON.stringify([row.visit || '', row.sample_id]) : row.sample_id;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  const bodies = [...groups.values()].sort((a, b) =>
    byVisit(a[0].visit, b[0].visit) || natural.compare(a[0].sample_id, b[0].sample_id)
  ).map(assays => {
    const sample = assays[0].sample_id;
    return {visit: assays[0].visit || '', html: `<tbody>${assays.map((r, i) => {
    const key = modalityKey(r.modality);
    const relative = typeof r.days_from_baseline === 'number' && Number.isFinite(r.days_from_baseline)
      ? `Day ${r.days_from_baseline} from study baseline` : '';
    return `<tr>${i === 0 ? `<th scope="rowgroup" rowspan="${assays.length}" class="inventory-sample"><span class="inventory-sample-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3h6M10 3v6L6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2L14 9V3M8 15h8"/></svg><code>${esc(sample)}</code></span><small>${assays.length} assay${assays.length === 1 ? '' : 's'}</small></th>` : ''}
      <td><div class="inventory-assay"><span class="inventory-modality-icon" data-modality="${key}" aria-hidden="true">${modalityIcon(key, '')}</span><div><span class="inventory-modality">${esc(modalityLabel(r.modality))}</span><small>${esc(r.assay)}</small></div></div>${r.sample_clarid ? `<small>ClarID: ${esc(r.sample_clarid)}</small>` : ''}</td>
      <td class="inventory-collection">${r.visit || r.collection_date || r.material || relative ? `<span>${field(r.visit)}</span><small>${field(r.collection_date || relative)}</small>${r.collection_date && relative ? `<small>${esc(relative)}</small>` : ''}<small>${field(r.material)}</small>` : missing}</td>
      <td>${esc(String(r.data_type || 'Not recorded').replaceAll('_', ' '))}</td>
      <td><span class="inventory-link">${esc(links[r.linkage] || 'Not recorded')}</span></td></tr>`;
  }).join('')}</tbody>`};
  });
  const clinicalBodies = (clinicalRecords || []).map((item, index) => ({item, index}))
    .sort((a, b) => byVisit(a.item.visit_id, b.item.visit_id))
    .map(({item, index}) => {
    const raw = item.record;
    const counts = [['diseases', 'diagnosis', 'diagnoses'], ['phenotypicFeatures', 'phenotype', 'phenotypes'],
      ['measures', 'measurement', 'measurements'], ['treatments', 'treatment', 'treatments']]
      .filter(([key]) => Array.isArray(raw[key]) && raw[key].length)
      .map(([key, one, many]) => `${raw[key].length} ${raw[key].length === 1 ? one : many}`).join(' · ');
    const diagnoses = (raw.diseases || []).map(d => d.diseaseCode?.label || d.diseaseCode?.id).filter(Boolean).join(', ');
    const when = item.event_date || (Number.isFinite(item.days_from_baseline) ? `Day ${item.days_from_baseline} from study baseline` : '');
    return {visit: item.visit_id || '', html: `<tbody class="inventory-clinical"><tr>
      <th scope="row" class="inventory-sample"><span class="inventory-sample-label">${modalityIcon('clinical', '')}<code>${field(item.visit_id)}</code></span><small>Clinical record</small></th>
      <td><div class="inventory-assay"><span class="inventory-modality-icon" data-modality="clinical">${modalityIcon('clinical', '')}</span><div><span class="inventory-modality">Clinical</span><small>${esc(diagnoses || 'No diagnosis recorded')}</small></div></div></td>
      <td class="inventory-collection"><span>${field(item.visit_id)}</span><small>${field(when)}</small></td>
      <td>${esc(counts || 'Source record')}${raw.sex ? `<small>${esc(raw.sex.label || raw.sex.id || raw.sex)}</small>` : ''}</td>
      <td><span class="inventory-link">Clinical record</span></td>
      </tr><tr><td colspan="5" class="inventory-clinical-detail"><details data-clinical-index="${index}" class="clinical-record"><summary>View clinical values</summary>${clinicalRecordsMarkup([item], escapeHtml)}</details></td></tr></tbody>`};
  });
  let content = bodies.map(body => body.html).join('');
  if (combined) {
    const visits = new Map();
    for (const body of [...clinicalBodies, ...bodies]) {
      if (!visits.has(body.visit)) visits.set(body.visit, []);
      visits.get(body.visit).push(body.html);
    }
    content = [...visits].sort(([a], [b]) => byVisit(a, b)).map(([visit, entries]) =>
      `<tbody class="inventory-visit-heading" data-visit="${esc(visit)}"><tr><th colspan="5"><span class="inventory-visit-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/></svg>${esc(visit || 'Visit not recorded')}</span></th></tr></tbody>${entries.join('')}`
    ).join('');
  }
  return `<div class="patient-inventory-scroll" tabindex="0" role="region" aria-label="${combined ? 'Available clinical data, samples and assays' : 'Available samples and assays'}"><table class="patient-inventory"><caption>${combined ? 'Clinical records and samples grouped by recorded visit' : 'Available assay data grouped by sample identifier'}</caption><thead><tr><th scope="col">${combined ? 'Record / sample' : 'Sample'}</th><th scope="col">${combined ? 'Data type' : 'Assay'}</th><th scope="col">Collection<small>Visit · date · material</small></th><th scope="col">Available data</th><th scope="col">Patient link</th></tr></thead>${content}</table></div><div class="inventory-legend">— Not recorded. Patient link shows how the dataset connects the entry to this patient. ${combined ? 'Visits are grouped by exact identifiers, not by matching dates.' : ''}</div>`;
}
