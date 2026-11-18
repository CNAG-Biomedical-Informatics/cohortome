import { renderSupplemental, resetSupplementalView } from './shared/view-root.js';
import { useLayoutEffect, useRef } from 'react';
import { ModalityIcon } from './shared/modality-icon.jsx';
import { modalityLabel, modalityColor } from '../../static/js/modalities.js';

const label = (value) => (value === 'imaging' ? 'Imaging-derived' : modalityLabel(value));
function Badges({ modalities }) {
  return modalities.length
    ? modalities.map((modality) => (
        <span
          key={modality}
          className="pill"
          style={{ borderColor: modalityColor(modality, true) }}
        >
          <ModalityIcon modality={modality} />
          {label(modality)}
        </span>
      ))
    : '—';
}
function TimelinePlot({ model }) {
  const host = useRef(null);
  useLayoutEffect(() => {
    const element = host.current;
    if (!model.loading && !model.error) model.draw();
    return () => {
      window.Plotly?.purge?.(element);
      element.replaceChildren();
    };
  }, [model]);
  // Plotly (or its empty-state renderer) exclusively owns this element.
  return <div ref={host} id="dashboard-plot-timeline" className="dashboard-plot-frame" />;
}
function Timeline({ model }) {
  const {
    actions,
    loading,
    error,
    datasets = [],
    modalities = [],
    required = [],
    rows = [],
    page = 0,
    pages = 1,
    warnings = [],
  } = model;
  return (
    <section className="section-card dashboard-timeline-card">
      <div className="dashboard-view-heading">
        <h2>Timeline</h2>
        <span id="timelineScopeLabel" className="dashboard-count">
          {model.scopeLabel || ''}
        </span>
        <details className="inline-view-help">
          <summary aria-label="About timeline">?</summary>
          <p>
            Data availability over time. Find patients with particular data, then inspect when it
            was collected.
          </p>
        </details>
      </div>
      <div className="timeline-scope-controls">
        <label>
          Dataset{' '}
          <select
            id="timelineDatasetFilter"
            disabled={loading || !!error}
            value={model.dataset || ''}
            onChange={(event) => actions.dataset(event.target.value)}
          >
            <option value="">All workspace datasets</option>
            {datasets.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button
          id="timelineShowAll"
          className="query-chip"
          type="button"
          disabled={loading || !!error}
          onClick={actions.clear}
        >
          Show all patients
        </button>
      </div>
      <label>
        Time axis{' '}
        <select
          id="timelineTimeMode"
          disabled={loading || !!error}
          value={model.timeMode || 'calendar'}
          onChange={(event) => actions.time(event.target.value)}
        >
          <option value="calendar">Calendar dates</option>
          <option value="relative">Study days</option>
        </select>
      </label>
      <p id="timelineTimeNote" className="section-note">
        {model.timeMode === 'relative'
          ? 'Days from each participant’s recorded study baseline. Baseline definitions may differ between datasets; this is not calendar time.'
          : 'Recorded calendar dates. Observations with only relative study time are available in the Study days view.'}
      </p>
      <h4>Has data</h4>
      <p className="section-note">
        Patients must have every checked data type. Leave unchecked to include everyone.
      </p>
      <div id="timelineHasData" className="dashboard-timeline-controls">
        {modalities.map((modality) => (
          <label
            key={modality}
            className="dashboard-timeline-domain"
            style={{ '--timeline-domain-color': modalityColor(modality, true) }}
          >
            <input
              type="checkbox"
              value={modality}
              checked={required.includes(modality)}
              onChange={(event) =>
                actions.required(
                  event.target.checked
                    ? [...required, modality]
                    : required.filter((value) => value !== modality),
                )
              }
            />
            <ModalityIcon modality={modality} />
            <span>{label(modality)}</span>
          </label>
        ))}
      </div>
      <p className="section-note">
        Click a plot legend item to hide or show its markers. Grey bars span the earliest to latest
        recorded observations; they do not imply continuous monitoring.
      </p>
      <div className="timeline-pagination">
        <button
          id="timelinePrevious"
          className="query-chip"
          disabled={loading || !!error || !page}
          onClick={() => actions.page(-1)}
        >
          Previous
        </button>
        <span id="timelinePageLabel">{loading || error ? '' : `Page ${page + 1} of ${pages}`}</span>
        <button
          id="timelineNext"
          className="query-chip"
          disabled={loading || !!error || page >= pages - 1}
          onClick={() => actions.page(1)}
        >
          Next
        </button>
      </div>
      <div id="timelineWarnings">
        {!!warnings.length && (
          <details>
            <summary>Linkage limitations ({warnings.length})</summary>
            {warnings.map((warning, index) => (
              <p key={index}>{warning}</p>
            ))}
          </details>
        )}
      </div>
      {loading && <p role="status">Loading data availability…</p>}
      {error && (
        <div role="status">
          <p>{error}</p>
          <button type="button" id="timelineRetry" onClick={actions.retry}>
            Retry
          </button>
        </div>
      )}
      <TimelinePlot model={model} />
      <div id="timelineAvailability" className="dashboard-timeline-table-wrap">
        <table className="dashboard-timeline-table">
          <thead>
            <tr>
              <th>Patient / dataset</th>
              <th>Available data</th>
              <th>
                {model.timeMode === 'relative'
                  ? 'Study day not recorded'
                  : 'Calendar date not recorded'}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={JSON.stringify([row.patient.dataset_id, row.patient.source_patient_id])}
                className={row.patient.patient_id === model.active ? 'is-inspected' : undefined}
              >
                <td>
                  <button
                    type="button"
                    className="query-chip"
                    data-timeline-inspect={index}
                    onClick={() => actions.inspect(row.patient)}
                  >
                    {row.label}
                  </button>
                </td>
                <td>
                  <Badges modalities={row.modalities} />
                </td>
                <td>
                  <Badges modalities={row.undated} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="section-note">
        Click a marker or patient to inspect. Availability is based on declared links; missing
        entries do not prove an assay was never performed. No dates are inferred.
      </p>
    </section>
  );
}
export function createTimelineView(host) {
  return {
    render(model) {
      renderSupplemental(host, <Timeline model={model} />);
    },
    reset() {
      resetSupplementalView(host);
    },
  };
}
