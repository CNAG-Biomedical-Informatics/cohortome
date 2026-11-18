import React from 'react';
import { ArtifactDownloads, Plot } from '../analysis-result-parts.jsx';
import { Metrics, Card, Notes } from './presentation.jsx';
export function QuantitativeResults({ model: m, turnIndex }) {
  const id = (suffix) => `analysis-plot-${turnIndex}-${suffix}`;
  const downloads = <ArtifactDownloads artifacts={m.downloads} />;
  return (
    <>
      <Metrics kind="quantitative-assay-wilcoxon" items={m.metrics} />
      <Card
        title={`${m.assayLabel}: Wilcoxon Cohort Comparison`}
        data-analysis-result="quantitative-assay-wilcoxon"
      >
        <p className="section-note">
          <strong>Exploratory and unadjusted.</strong> Wilcoxon rank-sum tests and BH correction
          were applied to each feature on its supplied measurement scale. No covariate adjustment,
          assay normalization, or causal interpretation is included.
        </p>
        <Notes
          items={[
            `Positive rank-biserial effects indicate higher ranks in Cohort A; negative effects indicate higher ranks in Cohort B. ${m.topHitText}`,
            m.modalityCaveat,
            m.externalMatrixNote,
          ]}
        />
        <Plot id={id('quantitative-assay-wilcoxon')} height={460} />
        <h4
          style={{
            margin: '18px 0 10px',
          }}
        >
          Top tested features
        </h4>
        <p className="section-note">
          Up to 12 features are shown, ordered by BH-adjusted p-value. Sample sizes are non-missing
          observations for each feature.
        </p>
        {m.rows.length ? (
          <div className="query-result-table-scroll" data-quantitative-assay-results="true">
            <table className="query-result-table">
              <thead>
                <tr>
                  {[
                    'Feature',
                    'Status',
                    'N A',
                    'N B',
                    'Missing A',
                    'Missing B',
                    'Median A',
                    'Median B',
                    'Median A - B',
                    'Rank-biserial effect',
                    'BH q',
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {m.rows.map((row, index) => (
                  <tr key={index}>
                    {row.map((value, column) => (
                      <td
                        key={column}
                        className={column === 0 ? 'query-result-id-cell' : undefined}
                      >
                        {value}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">No tested quantitative features were returned.</div>
        )}
        {downloads}
      </Card>
    </>
  );
}
