import { Fragment } from 'react';
import { ClinicalRecord } from './clinical-records.jsx';
import { ClarID } from './clarid.jsx';
import { ModalityIcon } from './shared/modality-icon.jsx';
import { modalityKey, modalityLabel } from '../../static/js/modalities.js';
const natural = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const byVisit = (a, b) =>
  Number(!a) - Number(!b) || natural.compare(String(a || ''), String(b || ''));
const missing = (
  <span className="inventory-missing" title="Not recorded" aria-label="Not recorded">
    —
  </span>
);
const field = (value) => (value ? String(value) : missing);
const clarid = (value) => (value?.human_id && value.stub_id ? <ClarID clarid={value} /> : missing);
function Samples({ rows }) {
  return (
    <tbody>
      {rows.map((r, i) => {
        const relative =
          typeof r.days_from_baseline === 'number' && Number.isFinite(r.days_from_baseline)
            ? `Day ${r.days_from_baseline} from study baseline`
            : '';
        return (
          <tr key={i}>
            {!i && (
              <th scope="rowgroup" rowSpan={rows.length} className="inventory-sample">
                <span className="inventory-sample-label">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    aria-hidden="true"
                  >
                    <path d="M9 3h6M10 3v6L6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2L14 9V3M8 15h8" />
                  </svg>
                  <code>{r.sample_id}</code>
                </span>
                <small>
                  {rows.length} assay{rows.length === 1 ? '' : 's'}
                </small>
              </th>
            )}
            <td>
              <div className="inventory-assay">
                <span
                  className="inventory-modality-icon"
                  data-modality={modalityKey(r.modality)}
                  aria-hidden="true"
                >
                  <ModalityIcon modality={r.modality} />
                </span>
                <div>
                  <span className="inventory-modality">{modalityLabel(r.modality)}</span>
                  <small>{r.assay}</small>
                </div>
              </div>
              {r.biosample_id && (
                <small>
                  Specimen <code>{r.biosample_id}</code>
                </small>
              )}
            </td>
            <td className="inventory-collection">
              {r.visit || r.collection_date || r.material || relative ? (
                <>
                  <span>{field(r.visit)}</span>
                  <small>{field(r.collection_date || relative)}</small>
                  {r.collection_date && relative && <small>{relative}</small>}
                  <small>{field(r.material)}</small>
                </>
              ) : (
                missing
              )}
            </td>
            <td>{String(r.data_type || 'Not recorded').replaceAll('_', ' ')}</td>
            <td>{clarid(r.biosample_clarid)}</td>
          </tr>
        );
      })}
    </tbody>
  );
}
function Clinical({ item, index, subjectClarid, expandFirst }) {
  const raw = item.record;
  const counts = [
    ['diseases', 'diagnosis', 'diagnoses'],
    ['phenotypicFeatures', 'phenotype', 'phenotypes'],
    ['measures', 'measurement', 'measurements'],
    ['treatments', 'treatment', 'treatments'],
  ]
    .filter(([key]) => Array.isArray(raw[key]) && raw[key].length)
    .map(([key, one, many]) => `${raw[key].length} ${raw[key].length === 1 ? one : many}`)
    .join(' · ');
  const diagnoses = (raw.diseases || [])
    .map((d) => d.diseaseCode?.label || d.diseaseCode?.id)
    .filter(Boolean)
    .join(', ');
  const when =
    item.event_date ||
    (Number.isFinite(item.days_from_baseline)
      ? `Day ${item.days_from_baseline} from study baseline`
      : '');
  return (
    <tbody className="inventory-clinical">
      <tr>
        <th scope="row" className="inventory-sample">
          <span className="inventory-sample-label">
            <ModalityIcon modality="clinical" />
            <code>{field(item.visit_id)}</code>
          </span>
          <small>Clinical record</small>
        </th>
        <td>
          <div className="inventory-assay">
            <span className="inventory-modality-icon" data-modality="clinical">
              <ModalityIcon modality="clinical" />
            </span>
            <div>
              <span className="inventory-modality">Clinical</span>
              <small>{diagnoses || 'No diagnosis recorded'}</small>
            </div>
          </div>
        </td>
        <td className="inventory-collection">
          <span>{field(item.visit_id)}</span>
          <small>{field(when)}</small>
        </td>
        <td>
          {counts || 'Source record'}
          {raw.sex && <small>{String(raw.sex.label || raw.sex.id || raw.sex)}</small>}
        </td>
        <td>{clarid(subjectClarid)}</td>
      </tr>
      <tr>
        <td colSpan="5" className="inventory-clinical-detail">
          <details
            data-clinical-index={index}
            className="clinical-record"
            open={expandFirst && index === 0 ? true : undefined}
          >
            <summary>View clinical values</summary>
            <ClinicalRecord record={raw} />
          </details>
        </td>
      </tr>
    </tbody>
  );
}
export function PatientInventory({
  rows,
  records = null,
  subjectClarid = null,
  expandFirst = false,
}) {
  const combined = records !== null,
    groups = new Map();
  for (const row of rows) {
    const key = combined ? JSON.stringify([row.visit || '', row.sample_id]) : row.sample_id;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  const bodies = [...groups]
    .sort(
      ([, a], [, b]) =>
        byVisit(a[0].visit, b[0].visit) || natural.compare(a[0].sample_id, b[0].sample_id),
    )
    .map(([key, items]) => ({
      key: `sample:${key}`,
      visit: items[0].visit || '',
      node: <Samples rows={items} />,
    }));
  const clinical = (records || []).map((item, index) => ({
    key: `clinical:${index}`,
    visit: item.visit_id || '',
    node: (
      <Clinical item={item} index={index} subjectClarid={subjectClarid} expandFirst={expandFirst} />
    ),
  }));
  let content = bodies.map((body) => <Fragment key={body.key}>{body.node}</Fragment>);
  if (combined) {
    const visits = new Map();
    for (const body of [...clinical, ...bodies]) {
      if (!visits.has(body.visit)) visits.set(body.visit, []);
      visits.get(body.visit).push(body);
    }
    content = [...visits]
      .sort(([a], [b]) => byVisit(a, b))
      .map(([visit, entries]) => (
        <Fragment key={visit}>
          <tbody className="inventory-visit-heading" data-visit={visit}>
            <tr>
              <th colSpan="5">
                <span className="inventory-visit-label">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <rect x="3" y="5" width="18" height="16" rx="2" />
                    <path d="M7 3v4m10-4v4M3 11h18" />
                  </svg>
                  {visit || 'Visit not recorded'}
                </span>
              </th>
            </tr>
          </tbody>
          {entries.map((body) => (
            <Fragment key={body.key}>{body.node}</Fragment>
          ))}
        </Fragment>
      ));
  }
  return (
    <>
      <div
        className="patient-inventory-scroll"
        tabIndex="0"
        role="region"
        aria-label={
          combined ? 'Available clinical data, samples and assays' : 'Available samples and assays'
        }
      >
        <table className="patient-inventory">
          <caption>
            {combined
              ? 'Clinical records and samples grouped by recorded visit'
              : 'Available assay data grouped by sample identifier'}
          </caption>
          <thead>
            <tr>
              <th scope="col">{combined ? 'Record / sample' : 'Sample'}</th>
              <th scope="col">{combined ? 'Data type' : 'Assay'}</th>
              <th scope="col">
                Collection<small>Visit · date · material</small>
              </th>
              <th scope="col">Available data</th>
              <th scope="col">ClarID</th>
            </tr>
          </thead>
          {content}
        </table>
      </div>
      <div className="inventory-legend">
        — Not recorded.{' '}
        {combined ? 'Visits are grouped by exact identifiers, not by matching dates.' : ''}
      </div>
    </>
  );
}
