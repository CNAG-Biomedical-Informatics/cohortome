export function ClarID({ clarid: c, compact = true }) {
  if (!c?.human_id || !c.stub_id) return null;
  const biosample = c.entity === 'biosample';
  const condition = c.condition_name ? `${c.condition_name} (${c.condition})` : c.condition;
  const decoded = biosample
    ? [
        ['Project', c.project],
        ['Subject', c.subject_id],
        ['Species', c.species],
        ['Tissue', c.tissue],
        ['Sample type', c.sample_type],
        ['Assay', c.assay],
        ['Condition', condition],
        ['Timepoint', c.timepoint],
        ['Duration', c.duration],
        ['Batch', c.batch],
        ['Replicate', c.replicate],
      ].filter(([, value]) => value !== '' && value != null)
    : [c.study, c.type, condition, c.sex, c.age_group].filter(Boolean).join(' · ');
  const version = [
    c.codebook_version ? `Codebook ${c.codebook_version}` : '',
    c.tools_version ? `Tools ${c.tools_version}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
  // App-level delegation retains the shared copy and accessible popover behaviour.
  return (
    <span className={`clarid-identity${compact ? ' is-compact' : ''}`}>
      <button
        type="button"
        className="clarid-badge"
        data-clarid-toggle=""
        aria-expanded="false"
        title={`Show decoded ${biosample ? 'biosample' : 'subject'} ClarID metadata`}
      >
        ClarID
      </button>
      <span className="clarid-popover" role="dialog" aria-label="Decoded ClarID metadata">
        <strong>ClarID {biosample ? 'biosample' : `subject ${c.subject_id}`}</strong>
        <span className="clarid-decoded-summary">
          {biosample
            ? decoded.map(([key, value]) => (
                <span key={key}>
                  <b>{key}:</b> {String(value)}
                </span>
              ))
            : decoded}
        </span>
        {[
          ['Human', c.human_id, 'Copy human-readable ClarID'],
          ['Stub', c.stub_id, 'Copy ClarID stub'],
        ].map(([key, value, label]) => (
          <span key={key} className="clarid-code-row">
            <b>{key}</b>
            <code>{value}</code>
            <button type="button" data-clarid-copy={value} aria-label={label}>
              Copy
            </button>
          </span>
        ))}
        {biosample && <small>Descriptive label; different specimens may share it.</small>}
        {version && <small>{version}</small>}
      </span>
    </span>
  );
}
