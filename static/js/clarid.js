// Prepared metadata only: labels are never used as specimen identity keys.
export function claridMarkup(clarid, escapeHtml, compact = false) {
  if (!clarid || !clarid.human_id || !clarid.stub_id) return '';
  const esc = value => escapeHtml(String(value ?? ''));
  const biosample = clarid.entity === 'biosample';
  const condition = clarid.condition_name
    ? `${clarid.condition_name} (${clarid.condition})` : clarid.condition;
  const decoded = biosample
    ? [['Project', clarid.project], ['Subject', clarid.subject_id], ['Species', clarid.species],
       ['Tissue', clarid.tissue], ['Sample type', clarid.sample_type], ['Assay', clarid.assay],
       ['Condition', condition], ['Timepoint', clarid.timepoint], ['Duration', clarid.duration],
       ['Batch', clarid.batch], ['Replicate', clarid.replicate]]
      .filter(([, value]) => value !== '' && value != null)
      .map(([label, value]) => `<span><b>${label}:</b> ${esc(value)}</span>`).join('')
    : esc([clarid.study, clarid.type, condition, clarid.sex, clarid.age_group].filter(Boolean).join(' · '));
  const version = [clarid.codebook_version ? `Codebook ${clarid.codebook_version}` : '',
    clarid.tools_version ? `Tools ${clarid.tools_version}` : ''].filter(Boolean).join(' · ');
  return `<span class="clarid-identity${compact ? ' is-compact' : ''}">
    <button type="button" class="clarid-badge" data-clarid-toggle aria-expanded="false" title="Show decoded ${biosample ? 'biosample' : 'subject'} ClarID metadata">ClarID</button>
    <span class="clarid-popover" role="dialog" aria-label="Decoded ClarID metadata">
      <strong>ClarID ${biosample ? 'biosample' : `subject ${esc(clarid.subject_id)}`}</strong>
      <span class="clarid-decoded-summary">${decoded}</span>
      <span class="clarid-code-row"><b>Human</b><code>${esc(clarid.human_id)}</code><button type="button" data-clarid-copy="${esc(clarid.human_id)}" aria-label="Copy human-readable ClarID">Copy</button></span>
      <span class="clarid-code-row"><b>Stub</b><code>${esc(clarid.stub_id)}</code><button type="button" data-clarid-copy="${esc(clarid.stub_id)}" aria-label="Copy ClarID stub">Copy</button></span>
      ${biosample ? '<small>Descriptive label; different specimens may share it.</small>' : ''}
      ${version ? `<small>${esc(version)}</small>` : ''}
    </span></span>`;
}
