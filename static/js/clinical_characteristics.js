export function characteristicsMarkup(datasets, esc, selectedId = '') {
  if (!datasets?.length) return '<section class="section-card"><p class="section-note">Clinical characteristics are unavailable for this workspace.</p></section>';
  const selected = datasets.find(dataset => dataset.dataset_id === selectedId);
  const number = value => value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits:2});
  const coverage = (row, dataset) => {
    const percent = dataset.patients ? Math.max(0, Math.min(100, 100 * row.recorded / dataset.patients)) : 0;
    return `<div class="clinical-coverage"><span>${number(row.recorded)} / ${number(dataset.patients)}</span><span class="clinical-coverage-track" aria-hidden="true"><span style="width:${percent}%"></span></span></div>`;
  };
  return `<section class="section-card"><div class="patient-finder-heading"><h3>Clinical characteristics</h3>
    <details class="inline-view-help"><summary aria-label="How clinical characteristics are summarized">?</summary><p>Each dataset is summarized separately. Percentages use patients with clinical records in the displayed group. Categories count patients with a recorded value at any visit; a patient can appear in several categories. Numeric values use each patient's median across recorded visits, then show the group median [25th–75th percentile]. These are not baseline values. Missing means no usable value was recorded. The 20 most frequent values are shown for large categories.</p></details></div>
    ${(selected ? [selected] : datasets).map(dataset => {
      const measurements = dataset.rows.filter(row => row.kind === 'number');
      const categories = dataset.rows.filter(row => row.kind !== 'number');
      return `<section class="clinical-characteristics-dataset"><div class="clinical-table-heading"><h4>${esc(dataset.label)}</h4><span class="clinical-population">${number(dataset.patients)} ${dataset.patients === 1 ? 'patient' : 'patients'}</span></div>
      ${measurements.length ? `<section class="clinical-summary-group" aria-label="Numeric measurements"><div class="clinical-summary-heading"><h5>Numeric measurements</h5><span>Patient medians across visits</span></div>
      <div class="table-scroll"><table class="assay-table clinical-stats-table clinical-measurements-table"><thead><tr><th scope="col">Measurement</th><th scope="col">Unit</th><th scope="col">Median [Q1–Q3]</th><th scope="col">Patients measured</th><th scope="col" class="clinical-count">Missing</th></tr></thead><tbody>
      ${measurements.map(row => `<tr><th scope="row">${esc(row.label)}</th><td class="clinical-measurement-unit">${row.unit ? esc(row.unit) : 'Not reported'}</td><td><span class="clinical-numeric-summary"><strong>${number(row.median)}</strong> <span>[${number(row.q1)}–${number(row.q3)}]</span></span></td><td>${coverage(row, dataset)}</td><td class="clinical-count"><span class="clinical-count-value ${row.missing ? 'has-missing' : 'none-missing'}">${number(row.missing)}</span></td></tr>`).join('')}
      </tbody></table></div></section>` : ''}
      ${categories.length ? `<section class="clinical-summary-group" aria-label="Patient characteristics"><div class="clinical-summary-heading"><h5>Patient characteristics</h5><span>Recorded at any visit</span></div>
      <div class="table-scroll"><table class="assay-table clinical-stats-table"><thead><tr><th scope="col">Characteristic</th><th scope="col">Summary</th><th scope="col" class="clinical-count">Recorded</th><th scope="col" class="clinical-count">Missing</th></tr></thead><tbody>
      ${categories.map(row => `<tr><th scope="row">${esc(row.label)}<small class="clinical-stat-caption">Patients, n (%)</small></th><td><div class="clinical-categories">${row.categories.map(value => `<div class="clinical-category"><span>${esc(value.label)}</span><span class="clinical-category-value"><strong>${number(value.count)}</strong> <span>(${dataset.patients ? number(100 * value.count / dataset.patients) : '0'}%)</span></span></div>`).join('')}</div>${row.truncated ? '<small>Top 20 values shown</small>' : ''}</td><td class="clinical-count"><span class="clinical-count-value">${number(row.recorded)}</span></td><td class="clinical-count"><span class="clinical-count-value ${row.missing ? 'has-missing' : 'none-missing'}">${number(row.missing)}</span></td></tr>`).join('')}
      </tbody></table></div></section>` : ''}
      ${!dataset.rows.length ? '<p class="section-note">No supported clinical characteristics recorded.</p>' : ''}
      </section>`; }).join('')}</section>`;
}
