const labels = {
  phenotypicFeatures: 'Phenotypes',
  measures: 'Measurements',
  treatments: 'Treatments',
  diseases: 'Diagnoses',
  info: 'Additional source information',
  interventionsOrProcedures: 'Procedures',
  exposures: 'Exposures',
  sex: 'Sex',
};
const label = (key) => labels[key] || key.replace(/([a-z])([A-Z])/g, '$1 $2').replaceAll('_', ' ');
const present = (value) =>
  value != null && value !== '' && (typeof value !== 'object' || Object.keys(value).length > 0);
const paths = {
  diseases: <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />,
  measures: <path d="M9 3h6m-5 0v6L6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2L14 9V3M8 15h8" />,
  phenotypicFeatures: <path d="M3 12h4l3-7 4 14 3-7h4" />,
  treatments: <path d="M8 16 16 8m-9-1a6 6 0 0 1 10 0 6 6 0 0 1 0 8l-2 2a6 6 0 0 1-8-8z" />,
  sex: (
    <>
      <circle cx="12" cy="7" r="4" />
      <path d="M4 21v-2a8 8 0 0 1 16 0v2" />
    </>
  ),
  other: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M9 8h6m-6 4h6m-6 4h4" />
    </>
  ),
};
function Icon({ kind }) {
  return (
    <svg
      className="clinical-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[kind] || paths.other}
    </svg>
  );
}
function Term({ value }) {
  const text =
    value && typeof value === 'object'
      ? value.label || value.id || 'Not recorded'
      : (value ?? 'Not recorded');
  return (
    <>
      {String(text)}
      {value?.id && value?.label && (
        <>
          {' '}
          <small className="muted">({value.id})</small>
        </>
      )}
    </>
  );
}
function Fields({ value, depth = 0 }) {
  if (value == null) return <span className="muted">Not recorded</span>;
  if (typeof value !== 'object') return String(value);
  if (depth > 5) return <pre>{JSON.stringify(value, null, 2)}</pre>;
  if (Array.isArray(value))
    return value.length ? (
      <ul>
        {value.map((item, i) => (
          <li key={i}>
            <Fields value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    ) : (
      <span className="muted">No entries recorded</span>
    );
  return (
    <dl>
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{label(key)}</dt>
          <dd>
            <Fields value={item} depth={depth + 1} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
function Values({ kind, value }) {
  if (kind === 'measures' && Array.isArray(value))
    return (
      <div className="patient-inventory-scroll">
        <table className="patient-inventory clinical-measures">
          <thead>
            <tr>
              <th>Measurement</th>
              <th>Value</th>
              <th>Unit</th>
            </tr>
          </thead>
          <tbody>
            {value.map((row, i) => {
              const quantity = row.measurementValue?.quantity;
              return (
                <tr key={i}>
                  <th scope="row">
                    <Term value={row.assayCode} />
                  </th>
                  <td>
                    {quantity ? (
                      String(quantity.value ?? 'Not recorded')
                    ) : (
                      <Fields value={row.measurementValue} />
                    )}
                  </td>
                  <td>
                    <Term value={quantity?.unit} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  if (kind === 'sex')
    return (
      <p>
        <Term value={value} />
      </p>
    );
  if (['diseases', 'phenotypicFeatures', 'treatments'].includes(kind) && Array.isArray(value)) {
    const code = {
      diseases: 'diseaseCode',
      phenotypicFeatures: 'featureType',
      treatments: 'treatmentCode',
    }[kind];
    return value.length ? (
      value.map((row, i) => (
        <div className="clinical-finding" key={i}>
          <strong>
            <Term value={row[code]} />
          </strong>
          {typeof row.excluded === 'boolean' && (
            <span className="pill">{row.excluded ? 'Recorded absent' : 'Recorded present'}</span>
          )}
          {Object.keys(row).some((k) => ![code, 'excluded'].includes(k)) && (
            <div className="clinical-finding-context">
              <Fields
                value={Object.fromEntries(
                  Object.entries(row).filter(([key]) => ![code, 'excluded'].includes(key)),
                )}
              />
            </div>
          )}
        </div>
      ))
    ) : (
      <p>No entries recorded.</p>
    );
  }
  return <Fields value={value} />;
}
export function ClinicalRecord({ record }) {
  const entries = Object.entries(record).filter(
    ([key, value]) => !['id', 'patient_id', 'visit_id', 'info'].includes(key) && present(value),
  );
  return (
    <>
      <div className="clinical-record-sections">
        {entries.map(([key, value]) => (
          <section className="clinical-record-section" key={key}>
            <h4>
              <Icon kind={key} />
              {label(key)}
              {Array.isArray(value) && (
                <>
                  {' '}
                  <span className="clinical-count">{value.length}</span>
                </>
              )}
            </h4>
            <Values kind={key} value={value} />
          </section>
        ))}
      </div>
      <details className="clinical-record-json clinical-technical">
        <summary>
          <Icon kind="other" />
          Technical details
        </summary>
        {present(record.info) && (
          <>
            <h4>Source metadata</h4>
            <Fields value={record.info} />
          </>
        )}
        <h4>Full BFF JSON</h4>
        <pre>{JSON.stringify(record, null, 2)}</pre>
      </details>
    </>
  );
}
