import { createRoot } from 'react-dom/client';
import { useLayoutEffect, useRef } from 'react';
import { ClinicalCharacteristics } from './clinical-characteristics.jsx';
import { ClinicalMeasurements } from './clinical-measurements.jsx';

// Plotly owns plot interiors; React owns the cards and controls around them.
function ClinicalCharts({model}) {
  const host = useRef(null);
  useLayoutEffect(() => {
    const element = host.current;
    model.draw();
    const plots = [...element.querySelectorAll('.js-plotly-plot')].filter(plot => !plot.closest('.clinical-measurements'));
    return () => {
      plots.forEach(plot => window.Plotly?.purge?.(plot));
    };
  }, [model]);
  return <section ref={host} className="section-card clinical-charts">
    <div className="dashboard-plot-grid clinical-primary-plots">
      <div className="dashboard-plot-card"><h4>Recorded diagnoses</h4>
        <p className="clinical-chart-caption">Most frequent · patients may have more than one diagnosis.</p>
        <div className="dashboard-plot-frame" id="dashboard-plot-diseases"/>
      </div>
      <div className="dashboard-plot-card clinical-sex-card"><h4>Recorded sex</h4>
        <p className="clinical-chart-caption">Patients, n (%) · includes unknown values.</p>
        <div className="dashboard-plot-frame" id="dashboard-plot-sex"/>
        <ul id="clinicalSexLegend" className="clinical-sex-legend" aria-label="Recorded sex counts and percentages"/>
      </div>
    </div>
    <div className="clinical-chart-toggle"><button id="dashboardClinicalToggleBtn" type="button" className="query-chip query-chip-toggle"
      aria-expanded={model.expanded} aria-controls="clinicalSecondaryPlots" onClick={model.actions.expand}>
      {model.expanded ? 'Hide visits and treatments' : 'Visits and treatments'}
    </button></div>
    <div id="clinicalSecondaryPlots" hidden={!model.expanded}>{model.expanded && <div className="dashboard-plot-grid clinical-secondary-plots">
      <div className="dashboard-plot-card"><h4>{model.representation === 'snapshot' ? 'Visits per patient' : 'Clinical records per patient'}</h4><div className="dashboard-plot-frame" id="dashboard-plot-visits"/></div>
      <div className="dashboard-plot-card"><h4>Recorded treatments</h4><div className="dashboard-plot-frame" id="dashboard-plot-medications"/></div>
      <div className="dashboard-plot-card clinical-association-chart"><h4>Disease by medication</h4><p className="clinical-chart-caption">Patient-level overlap, not necessarily the same visit.</p><div className="dashboard-plot-frame" id="dashboard-plot-disease-medication"/></div>
    </div>}</div>
    <ClinicalMeasurements model={model}/>
  </section>;
}

function ClinicalDashboard({model}) {
  const {totals, patients, records, representation, scoped, workspacePatients,
    datasets, datasetId, tableMode, formatNumber, actions} = model;
  return <>
    <section className="section-card dashboard-hero">
      <div className="dashboard-view-heading">
        <h2>Clinical dashboard</h2>
        <div className="dashboard-heading-counts">
          <span className="dashboard-count">{formatNumber(patients)} {Number(patients) === 1 ? 'patient' : 'patients'}</span>
          <span className="dashboard-count">{formatNumber(records)} {records === 1 ? 'record' : 'records'}</span>
        </div>
        <details className="inline-view-help"><summary aria-label="About the clinical dashboard">?</summary>
          <p>Counts describe the group shown below. Disease and medication counts use unique patients; a patient may appear in several categories. All their clinical records are included, not only the visit or sample that matched a filter. Distributions use patients with clinical records. Missing sex is shown as Unknown.{scoped ? ` The full workspace contains ${formatNumber(workspacePatients)} patients with clinical records.` : ''}
          <br/><br/>{formatNumber(totals.source_files || 0)} source files · {representation === 'snapshot'
            ? `Average visits per patient: ${totals.avg_visits_per_patient || 0}`
            : representation === 'person' ? 'One record per person' : 'Mixed or unspecified representation'}.</p>
        </details>
      </div>
    </section>
    <div className="clinical-view-toolbar">
      <div className="clinical-view-switch" role="group" aria-label="Clinical presentation">
        <button type="button" className="query-chip" data-clinical-mode="charts" aria-pressed={!tableMode} onClick={() => actions.mode('charts')}>Charts</button>
        <button type="button" className="query-chip" data-clinical-mode="table" aria-pressed={tableMode} onClick={() => actions.mode('table')}>Table</button>
      </div>
      {!!datasets.length && <label className="clinical-table-dataset-label" htmlFor="clinicalTableDataset">View
        <select id="clinicalTableDataset" title="Display a dataset within the current scope; this does not change scope."
          value={datasetId} onChange={event => actions.dataset(event.target.value)}>
          <option value="">All active datasets</option>
          {datasets.map(item => <option key={item.dataset_id} value={item.dataset_id}>{item.label}</option>)}
        </select>
      </label>}
    </div>
    <div className="clinical-view-content">{tableMode
      ? <ClinicalCharacteristics datasets={datasets} selectedId={datasetId}/>
      : <ClinicalCharts model={model}/>}</div>
  </>;
}

export function createClinicalDashboardView(host) {
  let root;
  return {
    render(model) {
      root ||= createRoot(host);
      root.render(<ClinicalDashboard model={model}/>);
    },
    reset() {root?.unmount(); root = null;},
  };
}
