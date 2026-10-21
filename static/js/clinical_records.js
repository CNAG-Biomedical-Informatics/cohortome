// Stored clinical fields only: no imputation or cross-visit propagation.
export function clinicalRecordsMarkup(records, escapeHtml) {
  const esc = value => escapeHtml(String(value));
  const labels = {phenotypicFeatures:'Phenotypes', measures:'Measurements',
    treatments:'Treatments', diseases:'Diagnoses', info:'Additional source information',
    interventionsOrProcedures:'Procedures', exposures:'Exposures', sex:'Sex'};
  const label = key => labels[key] || key.replace(/([a-z])([A-Z])/g, '$1 $2').replaceAll('_', ' ');
  const term = value => value && typeof value === 'object' ? value.label || value.id || 'Not recorded' : value ?? 'Not recorded';
  const termMarkup = value => `${esc(term(value))}${value?.id && value?.label ? ` <small class="muted">(${esc(value.id)})</small>` : ''}`;
  const paths = {
    diseases: '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>',
    measures: '<path d="M9 3h6m-5 0v6L6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2L14 9V3M8 15h8"/>',
    phenotypicFeatures: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    treatments: '<path d="M8 16 16 8m-9-1a6 6 0 0 1 10 0 6 6 0 0 1 0 8l-2 2a6 6 0 0 1-8-8z"/>',
    sex: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    other: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6m-6 4h6m-6 4h4"/>',
  };
  const icon = key => `<svg class="clinical-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[key] || paths.other}</svg>`;
  const present = value => value !== null && value !== undefined && value !== ''
    && (typeof value !== 'object' || Object.keys(value).length > 0);
  function measurements(rows) {
    return `<div class="patient-inventory-scroll"><table class="patient-inventory clinical-measures">
      <thead><tr><th>Measurement</th><th>Value</th><th>Unit</th></tr></thead><tbody>
      ${rows.map(row => {
        const quantity = row.measurementValue?.quantity;
        return `<tr><th scope="row">${termMarkup(row.assayCode)}</th>
          <td>${quantity ? esc(quantity.value ?? 'Not recorded') : fields(row.measurementValue)}</td>
          <td>${termMarkup(quantity?.unit)}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  }
  function section(key, value) {
    if (key === 'measures' && Array.isArray(value)) return measurements(value);
    if (key === 'sex') return `<p>${termMarkup(value)}</p>`;
    if (['diseases', 'phenotypicFeatures', 'treatments'].includes(key) && Array.isArray(value)) {
      const code = {diseases:'diseaseCode', phenotypicFeatures:'featureType', treatments:'treatmentCode'}[key];
      return value.map(row => `<div class="clinical-finding"><strong>${termMarkup(row[code])}</strong>
        ${typeof row.excluded === 'boolean' ? `<span class="pill">${row.excluded ? 'Recorded absent' : 'Recorded present'}</span>` : ''}
        ${Object.keys(row).some(k => ![code, 'excluded'].includes(k)) ? `<div class="clinical-finding-context">${fields(Object.fromEntries(Object.entries(row).filter(([k]) => ![code, 'excluded'].includes(k))))}</div>` : ''}
        </div>`).join('') || '<p>No entries recorded.</p>';
    }
    return fields(value);
  }
  function fields(value, depth = 0) {
    if (value === null || value === undefined) return '<span class="muted">Not recorded</span>';
    if (typeof value !== 'object') return esc(value);
    if (depth > 5) return `<pre>${esc(JSON.stringify(value, null, 2))}</pre>`;
    if (Array.isArray(value)) return value.length
      ? `<ul>${value.map(item => `<li>${fields(item, depth + 1)}</li>`).join('')}</ul>`
      : '<span class="muted">No entries recorded</span>';
    return `<dl>${Object.entries(value).map(([key, item]) =>
      `<div><dt>${esc(label(key))}</dt><dd>${fields(item, depth + 1)}</dd></div>`).join('')}</dl>`;
  }
  return records.map(item => {
    const raw = item.record;
    const entries = Object.entries(raw).filter(([key, value]) =>
      !['id','patient_id','visit_id','info'].includes(key) && present(value));
    return `
      <div class="clinical-record-sections">${entries.map(([key, value]) => {
        const title = `${esc(label(key))}${Array.isArray(value) ? ` <span class="clinical-count">${value.length}</span>` : ''}`;
        return `<section class="clinical-record-section"><h4>${icon(key)}${title}</h4>${section(key, value)}</section>`;
      }).join('')}</div>
      <details class="clinical-record-json clinical-technical"><summary>${icon('other')}Technical details</summary>
        ${present(raw.info) ? `<h4>Source metadata</h4>${fields(raw.info)}` : ''}
        <h4>Full BFF JSON</h4><pre>${esc(JSON.stringify(raw, null, 2))}</pre></details>
    `;
  }).join('');
}
