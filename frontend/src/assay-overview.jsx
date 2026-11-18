import { createRoot } from 'react-dom/client';
import { ModalityIcon } from './shared/modality-icon.jsx';
import { modalityColor } from '../../static/js/modalities.js';

function Overview({ model }) {
  const {
    empty,
    assays,
    samples,
    patients,
    scoped,
    featureCountsKnown,
    featureTotal,
    totalKnown,
    totalPatients,
    denominator,
    coverage = [],
    formatNumber,
    formatModality,
  } = model;
  if (empty)
    return (
      <>
        <div className="dashboard-view-heading">
          <h2>Assays</h2>
        </div>
        <div className="empty">{empty}</div>
      </>
    );
  return (
    <section className="assay-overview-summary">
      <div className="dashboard-view-heading">
        <h2>Assays</h2>
        <div className="dashboard-heading-counts">
          <span className="dashboard-count">{assays} assays</span>
          <span className="dashboard-count">{samples} samples</span>
          <span className="dashboard-count">{patients} patients</span>
        </div>
        <details className="inline-view-help">
          <summary aria-label="About assays">?</summary>
          <p>
            Patient coverage in {scoped ? 'the applied scope' : 'the whole workspace'}. Modalities
            may overlap.{' '}
            {featureCountsKnown
              ? `${featureTotal} features across the listed assays.`
              : 'Feature counts are not reported for every assay.'}
          </p>
        </details>
      </div>
      <div className="assay-coverage-chart">
        <p className="section-note">
          {totalKnown
            ? `Share of ${formatNumber(totalPatients)} patients with any assay`
            : 'Unique patients by modality'}{' '}
          · modalities may overlap.
        </p>
        {coverage.map(({ modality, count }) => (
          <div key={modality} className="assay-coverage-row">
            <span>
              <ModalityIcon modality={modality} />
              {formatModality(modality)}
            </span>
            <div className="assay-coverage-track" aria-hidden="true">
              <i
                style={{
                  width: `${count === null || !denominator ? 0 : (count / denominator) * 100}%`,
                  background: modalityColor(modality),
                }}
              />
            </div>
            <strong>
              {count === null
                ? 'Not reported'
                : formatNumber(count) + (count === 1 ? ' patient' : ' patients')}
              {count !== null && totalKnown && !!totalPatients && (
                <small className="assay-coverage-percent">
                  {((count / totalPatients) * 100).toFixed(0)}%
                </small>
              )}
            </strong>
          </div>
        ))}
      </div>
    </section>
  );
}
export function createAssayOverviewView(host) {
  let root;
  return {
    render(model) {
      if (!host) return;
      root ||= createRoot(host);
      root.render(<Overview model={model} />);
    },
  };
}
export function createAssayTabsView(host) {
  let root;
  return {
    render(tabs, selected) {
      if (!host) return;
      root ||= createRoot(host);
      // Existing parent event delegation handles selection.
      root.render(
        <>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`assay-modality-tab${tab.key === selected ? ' active' : ''}`}
              data-assay-modality-filter={tab.key}
              aria-pressed={tab.key === selected}
            >
              {tab.key !== 'all' && <ModalityIcon modality={tab.key} />}
              <span>{tab.label}</span>
              <strong>
                {tab.count} {tab.count === 1 ? 'assay' : 'assays'}
              </strong>
            </button>
          ))}
        </>,
      );
    },
  };
}
