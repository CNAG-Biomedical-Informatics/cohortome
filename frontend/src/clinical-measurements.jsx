import { useLayoutEffect, useRef } from 'react';

export function ClinicalMeasurements({model}) {
  const host = useRef(null);
  const {measurementFields:fields, measurement:selected, viewedDatasets:datasets, formatNumber} = model;
  useLayoutEffect(() => {
    const element = host.current;
    if (selected) model.drawMeasurements();
    const plots = [...element.querySelectorAll('.js-plotly-plot')];
    return () => plots.forEach(plot => window.Plotly?.purge?.(plot));
  }, [model]);
  return <section ref={host} id="clinicalMeasurements" className="clinical-measurements">
    {!selected ? <p className="section-note">No numeric clinical measurements recorded in this view.</p> : <>
      <div className="clinical-measurement-heading"><h4>Measurement distribution</h4>
        <details className="inline-view-help"><summary aria-label="About measurement distributions">?</summary><p>One median value per patient across recorded visits, not baseline values. Bars count patients, not observations. Each dataset uses up to 20 equal-width bins; the last bin includes its upper edge. Datasets remain separate. Only matching catalogue identities and units share a measurement choice. Missing means no usable numeric value. All records of selected patients contribute, not only visits matching a filter.</p></details>
      </div>
      <label className="clinical-measurement-picker" htmlFor="clinicalMeasurementSelect">Measurement
        <select id="clinicalMeasurementSelect" value={selected.id} onChange={event => model.actions.measurement(event.target.value)}>
          {fields.map(field => <option key={field.id} value={field.id}>{field.label} · {field.unit || 'unit not reported'}{datasets.length > 1 && field.sources.length < datasets.length ? ` — ${field.sources.map(source => source.dataset.label).join(', ')}` : ''}</option>)}
        </select>
      </label>
      <p className="clinical-chart-caption">One median per patient · {selected.unit || 'Unit not reported'}</p>
      <div className="dashboard-plot-grid clinical-distribution-grid">{datasets.map((dataset, index) => {
        const row = selected.sources.find(source => source.dataset === dataset)?.row;
        return <section key={dataset.dataset_id} className="dashboard-plot-card"><h4>{dataset.label}</h4>
          {row ? <><p className="clinical-chart-caption">{formatNumber(row.recorded)} measured · {formatNumber(row.missing)} missing</p>
            <div key={`${selected.id}:${!!row.distribution?.length}`} className="dashboard-plot-frame" id={`clinical-distribution-${index}`}>
              {!row.distribution?.length && <div className="clinical-chart-empty">{row.recorded ? 'Distribution unavailable for this numeric range.' : 'No measured patients in this scope.'}</div>}
            </div></> : <p className="section-note">This measurement is not recorded in this dataset.</p>}
        </section>;
      })}</div>
    </>}
  </section>;
}
