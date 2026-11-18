import { createRoot } from 'react-dom/client';
import { useRef, useState } from 'react';
import { displayIdentity } from '../../static/js/identities.js';
import { ModalityIcon } from './assay-overview.jsx';

function StudyRow({ study, label, enabled, openViewer }) {
  const series = Array.isArray(study.series) ? study.series : [];
  const instances = series.reduce((total, item) => total + Number(item?.instance_count || 0), 0);
  const url = String(study.ohif_url || '').trim();
  // External viewer links may navigate, never execute a script URL.
  let safeUrl = '';
  try {
    const parsed = new URL(url, window.location.origin);
    if (url && ['http:', 'https:'].includes(parsed.protocol)) safeUrl = parsed.href;
  } catch (_) {}
  return (
    <tr>
      <td>
        {label}
        {study.sample_id && <small>{displayIdentity(study.sample_id)}</small>}
      </td>
      <td>{study.timepoint || 'Not recorded'}</td>
      <td>
        <span className="imaging-modality">
          <ModalityIcon modality="imaging" />
          {String(study.modality || 'DICOM')}
        </span>
      </td>
      <td>
        <strong>
          {String(
            study.label || study.study_description || study.study_instance_uid || 'DICOM study',
          ).trim()}
        </strong>
        {study.local_viewer_url && (
          <small>
            {study.image_source === 'dicomweb' ? 'DICOMweb archive' : 'Dataset-linked DICOM files'}
          </small>
        )}
        <details className="imaging-study-details">
          <summary>Study details</summary>
          <code className="dicom-uid">{String(study.study_instance_uid || '')}</code>
          {series.map((item, index) => (
            <small key={item.series_instance_uid || index}>
              {item.series_description || 'Series'} · {Number(item.instance_count || 0)} DICOM
              instances
            </small>
          ))}
        </details>
      </td>
      <td>{series.length || 'Not reported'}</td>
      <td>{instances || 'Not reported'}</td>
      <td className="imaging-viewer-action">
        {study.local_viewer_url ? (
          <button
            type="button"
            className="query-chip"
            data-local-viewer={study.local_viewer_url}
            onClick={(event) => openViewer(study.local_viewer_url, event.currentTarget)}
          >
            View images
          </button>
        ) : enabled && safeUrl ? (
          <a
            className="query-chip"
            href={safeUrl}
            target="_blank"
            rel="noopener"
            title="Opens the configured external viewer"
          >
            View images ↗
          </a>
        ) : (
          <button
            type="button"
            className="query-chip"
            disabled
            title="No viewer is configured for this study"
          >
            Unavailable
          </button>
        )}
      </td>
    </tr>
  );
}
function ImagingStudies({ model }) {
  const [query, setQuery] = useState(''),
    [page, setPage] = useState(0);
  const input = useRef(null);
  if (model.empty) return <div className="empty">{model.empty}</div>;
  const { studies, patientLabels, patientLabel, enabled, openViewer } = model;
  const search = query.trim(),
    exact = patientLabels.includes(search);
  const filtered = studies.filter(
    (study) =>
      !search ||
      (exact
        ? patientLabel(study) === search
        : patientLabel(study).toLowerCase().includes(search.toLowerCase())),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 25)),
    current = Math.min(page, pages - 1);
  return (
    <>
      <div className="imaging-patient-filter">
        <label htmlFor="imagingPatientFilter">Patient</label>
        <input
          ref={input}
          id="imagingPatientFilter"
          list="imagingPatientOptions"
          placeholder="All patients — type to search"
          autoComplete="off"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(0);
          }}
        />
        <datalist id="imagingPatientOptions">
          {patientLabels.map((label) => (
            <option key={label} value={label} />
          ))}
        </datalist>
        <button
          type="button"
          className="query-chip"
          data-imaging-clear=""
          onClick={() => {
            setQuery('');
            setPage(0);
            input.current.focus();
          }}
        >
          All patients
        </button>
      </div>
      <div className="imaging-study-results">
        <p className="section-note" role="status">
          {filtered.length
            ? `${current * 25 + 1}–${Math.min((current + 1) * 25, filtered.length)} of ${filtered.length} studies`
            : 'No studies match this patient.'}
          {search ? ' · filtered' : ''}
        </p>
        <div className="assay-table-wrap imaging-study-table">
          <table className="assay-table">
            <caption>
              Each row is one study for the patient shown. Series and instance counts apply to that
              study only.
            </caption>
            <thead>
              <tr>
                {[
                  'Patient / sample',
                  'Visit',
                  'Modality',
                  'Study',
                  'Series in study',
                  'Instances in study',
                  'Viewer',
                ].map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.slice(current * 25, (current + 1) * 25).map((study) => (
                <StudyRow
                  key={JSON.stringify([
                    study.source_dataset_id,
                    study.study_instance_uid || studies.indexOf(study),
                  ])}
                  study={study}
                  label={patientLabel(study)}
                  enabled={enabled}
                  openViewer={openViewer}
                />
              ))}
            </tbody>
          </table>
        </div>
        <details className="imaging-service-details">
          <summary>What do these counts mean?</summary>
          <p>
            A study is an imaging examination. It can contain several series (such as MRI
            sequences). A DICOM instance is an object that may hold one image or multiple frames;
            the instance count is not necessarily the slice count. Counts come from the study
            manifest, not a live image-server inventory.
          </p>
        </details>
        {pages > 1 && (
          <div className="imaging-study-pagination">
            <button
              type="button"
              className="query-chip"
              data-prev=""
              disabled={!current}
              onClick={() => setPage(current - 1)}
            >
              Previous
            </button>
            <span>
              Page {current + 1} of {pages}
            </span>
            <button
              type="button"
              className="query-chip"
              data-next=""
              disabled={current >= pages - 1}
              onClick={() => setPage(current + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </>
  );
}
export function createImagingStudiesView(host) {
  let root,
    revision = 0;
  return {
    render(model) {
      if (!host) return;
      root ||= createRoot(host);
      // A new scope/inventory starts a fresh search, as before the migration.
      root.render(<ImagingStudies key={++revision} model={model} />);
    },
  };
}
