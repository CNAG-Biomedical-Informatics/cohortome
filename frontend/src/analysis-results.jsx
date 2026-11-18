import React from 'react';
import { ArtifactDownloads, Plot, EvidenceCard } from './analysis-result-parts.jsx';
import { ScientificResults } from './analysis-scientific-results.jsx';
export { ArtifactDownloads } from './analysis-result-parts.jsx';

export function AnalysisResults({ model }) {
  const { context: c, artifacts = [], turnIndex, eventLabel } = model;
  const id = (suffix) => `analysis-plot-${turnIndex}-${suffix}`;
  const card = (title, suffix, height, note) => (
    <div className="viz-card" style={{ gridColumn: '1 / -1' }}>
      <h3>{title}</h3>
      {note && <p className="section-note">{note}</p>}
      <Plot id={id(suffix)} height={height} />
    </div>
  );
  if (!c) return <div className="empty">No analysis plots available.</div>;
  if (c.mode === 'custom_script')
    return (
      <div className="viz-card" style={{ gridColumn: '1 / -1' }}>
        <ArtifactDownloads title="Script, audit and result files" artifacts={artifacts} />
        {artifacts
          .filter((item) => /^outputs\/[A-Za-z0-9_.-]+\.png$/.test(item.name || ''))
          .map((item, index) => (
            <img
              key={index}
              className="analysis-artifact-image"
              src={item.url}
              alt="Custom script output"
            />
          ))}
        <details className="query-section">
          <summary>Execution logs and audit</summary>
          <pre>
            {JSON.stringify({ stdout: c.stdout, stderr: c.stderr, audit: c.audit }, null, 2)}
          </pre>
        </details>
      </div>
    );
  if (c.mode === 'cross_modal_association')
    return (
      <div className="viz-card" style={{ gridColumn: '1 / -1' }}>
        <div className="section-note">{c.matching}</div>
        <div className="assay-kpi-grid">
          {Object.entries(c.counts || {}).map(([key, value]) => (
            <div key={key} className="assay-kpi">
              <span className="assay-kpi-label">{key.replace(/_/g, ' ')}</span>
              <strong className="assay-kpi-value">{String(value)}</strong>
            </div>
          ))}
        </div>
        <Plot id={id('association')} height={420} />
        <div className="query-result-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Clinical group</th>
                <th>Patients</th>
                <th>Spearman rho</th>
              </tr>
            </thead>
            <tbody>
              {(c.groups || []).map((group, index) => (
                <tr key={index}>
                  <td>{group.label}</td>
                  <td>{group.n}</td>
                  <td>
                    {group.spearman_rho === null
                      ? 'Undefined'
                      : Number(group.spearman_rho).toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="section-note">{c.limitations}</p>
        <details>
          <summary>Parameters and provenance</summary>
          <pre>
            {JSON.stringify({ parameters: c.parameters, provenance: c.provenance }, null, 2)}
          </pre>
        </details>
      </div>
    );
  const unit = c.unit ? ` (${c.unit})` : '';
  if (c.mode === 'trajectory_compare' || c.mode === 'trajectory_compare_response')
    return card(`Trajectory Comparison${unit}`, 'trajectory-compare', 400);
  if (c.mode === 'trajectory' || c.mode === 'trajectory_response')
    return (
      <>
        {card(
          c.treatment
            ? `Response to ${c.treatment}${unit}`
            : `Trajectory of ${c.measure || 'measure'}${unit}`,
          'trajectory',
          400,
        )}
        <EvidenceCard
          id={id('trajectory-coverage')}
          title="Trajectory Coverage"
          items={[
            { label: 'Patients', value: Number(c.patient_count || 0) },
            { label: 'Summary points', value: (c.summary_points || []).length },
          ]}
        />
      </>
    );
  if (c.mode === 'survival' || c.mode === 'survival_compare')
    return card(
      `Kaplan-Meier Time-to-Event ${c.mode === 'survival' ? 'Analysis' : 'Comparison'}`,
      c.mode === 'survival' ? 'survival' : 'survival-compare',
      360,
      `Event: ${eventLabel}`,
    );
  if (c.mode === 'transcriptomics_medication_compare')
    return (c.comparisons || []).length ? (
      c.comparisons.map((item, index) => (
        <div key={index} className="viz-card" style={{ gridColumn: '1 / -1' }}>
          <h3>
            Exploratory Volcano Plot: {item.medication_a || 'Group A'} vs{' '}
            {item.medication_b || 'Group B'}
          </h3>
          <p className="section-note">
            {c.exploratory_note || 'Exploratory transcriptomics comparison.'}
          </p>
          <p className="section-note">{`Coloring is exploratory: red = log2FC >= 1 and p <= 0.05, blue = log2FC <= -1 and p <= 0.05, gray = everything else. Positive log2FC means higher in ${item.medication_a || 'Group A'}; negative log2FC means higher in ${item.medication_b || 'Group B'}.`}</p>
          <Plot id={id(`assay-volcano-${index}`)} height={420} />
        </div>
      ))
    ) : (
      <div className="empty">No exploratory transcriptomics comparison plot available.</div>
    );
  return <ScientificResults model={model.scientific} turnIndex={turnIndex} />;
}
