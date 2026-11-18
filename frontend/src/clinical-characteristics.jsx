const number = (value) =>
  value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });

function Missing({ value }) {
  return (
    <td className="clinical-count">
      <span className={`clinical-count-value ${value ? 'has-missing' : 'none-missing'}`}>
        {number(value)}
      </span>
    </td>
  );
}

function DatasetCharacteristics({ dataset }) {
  const measurements = dataset.rows.filter((row) => row.kind === 'number');
  const categories = dataset.rows.filter((row) => row.kind !== 'number');
  return (
    <section className="clinical-characteristics-dataset">
      <div className="clinical-table-heading">
        <h4>{dataset.label}</h4>
        <span className="clinical-population">
          {number(dataset.patients)} {dataset.patients === 1 ? 'patient' : 'patients'}
        </span>
      </div>
      {!!measurements.length && (
        <section className="clinical-summary-group" aria-label="Numeric measurements">
          <div className="clinical-summary-heading">
            <h5>Numeric measurements</h5>
            <span>Patient medians across visits</span>
          </div>
          <div className="table-scroll">
            <table className="assay-table clinical-stats-table clinical-measurements-table">
              <thead>
                <tr>
                  <th scope="col">Measurement</th>
                  <th scope="col">Unit</th>
                  <th scope="col">Median [Q1–Q3]</th>
                  <th scope="col">Patients measured</th>
                  <th scope="col" className="clinical-count">
                    Missing
                  </th>
                </tr>
              </thead>
              <tbody>
                {measurements.map((row) => (
                  <tr key={row.field_id}>
                    <th scope="row">{row.label}</th>
                    <td className="clinical-measurement-unit">{row.unit || 'Not reported'}</td>
                    <td>
                      <span className="clinical-numeric-summary">
                        <strong>{number(row.median)}</strong>{' '}
                        <span>
                          [{number(row.q1)}–{number(row.q3)}]
                        </span>
                      </span>
                    </td>
                    <td>
                      <div className="clinical-coverage">
                        <span>
                          {number(row.recorded)} / {number(dataset.patients)}
                        </span>
                        <span className="clinical-coverage-track" aria-hidden="true">
                          <span
                            style={{
                              width: `${dataset.patients ? Math.max(0, Math.min(100, (100 * row.recorded) / dataset.patients)) : 0}%`,
                            }}
                          />
                        </span>
                      </div>
                    </td>
                    <Missing value={row.missing} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {!!categories.length && (
        <section className="clinical-summary-group" aria-label="Patient characteristics">
          <div className="clinical-summary-heading">
            <h5>Patient characteristics</h5>
            <span>Recorded at any visit</span>
          </div>
          <div className="table-scroll">
            <table className="assay-table clinical-stats-table">
              <thead>
                <tr>
                  <th scope="col">Characteristic</th>
                  <th scope="col">Summary</th>
                  <th scope="col" className="clinical-count">
                    Recorded
                  </th>
                  <th scope="col" className="clinical-count">
                    Missing
                  </th>
                </tr>
              </thead>
              <tbody>
                {categories.map((row, index) => (
                  <tr key={row.field_id || `${row.label}:${index}`}>
                    <th scope="row">
                      {row.label}
                      <small className="clinical-stat-caption">Patients, n (%)</small>
                    </th>
                    <td>
                      <div className="clinical-categories">
                        {row.categories.map((value) => (
                          <div className="clinical-category" key={value.label}>
                            <span>{value.label}</span>
                            <span className="clinical-category-value">
                              <strong>{number(value.count)}</strong>{' '}
                              <span>
                                (
                                {dataset.patients
                                  ? number((100 * value.count) / dataset.patients)
                                  : '0'}
                                %)
                              </span>
                            </span>
                          </div>
                        ))}
                      </div>
                      {row.truncated && <small>Top 20 values shown</small>}
                    </td>
                    <td className="clinical-count">
                      <span className="clinical-count-value">{number(row.recorded)}</span>
                    </td>
                    <Missing value={row.missing} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {!dataset.rows.length && (
        <p className="section-note">No supported clinical characteristics recorded.</p>
      )}
    </section>
  );
}

export function ClinicalCharacteristics({ datasets, selectedId }) {
  if (!datasets.length)
    return (
      <section className="section-card">
        <p className="section-note">Clinical characteristics are unavailable for this workspace.</p>
      </section>
    );
  const selected = datasets.find((dataset) => dataset.dataset_id === selectedId);
  return (
    <section className="section-card">
      <div className="patient-finder-heading">
        <h3>Clinical characteristics</h3>
        <details className="inline-view-help">
          <summary aria-label="How clinical characteristics are summarized">?</summary>
          <p>
            Each dataset is summarized separately. Percentages use patients with clinical records in
            the displayed group. Categories count patients with a recorded value at any visit; a
            patient can appear in several categories. Numeric values use each patient's median
            across recorded visits, then show the group median [25th–75th percentile]. These are not
            baseline values. Missing means no usable value was recorded. The 20 most frequent values
            are shown for large categories.
          </p>
        </details>
      </div>
      {(selected ? [selected] : datasets).map((dataset) => (
        <DatasetCharacteristics key={dataset.dataset_id} dataset={dataset} />
      ))}
    </section>
  );
}
