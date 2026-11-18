import { createRoot } from 'react-dom/client';
import { ModalityIcon } from './assay-overview.jsx';

function ImagingHealth({ model }) {
  if (model.message) return <div className="empty">{model.message}</div>;
  const { source, studies } = model;
  const bundled = studies.filter((study) => study.local_viewer_url).length;
  const allBundled = bundled > 0 && bundled === studies.length;
  const orthanc = source.orthanc || {};
  return (
    <>
      <div className="imaging-viewer-status">
        <ModalityIcon modality="imaging" />
        <strong>
          {allBundled
            ? 'Built-in viewer'
            : bundled
              ? 'Built-in + external viewer'
              : 'External viewer'}
        </strong>
        <span>
          {allBundled
            ? 'OHIF · opens inside COHORTome'
            : `${source.enabled ? 'Configured · image access not verified' : 'External viewing not enabled'}${bundled ? ` · ${bundled} studies use built-in OHIF` : ''}`}
        </span>
      </div>
      <details className="imaging-service-details">
        <summary>Viewer details</summary>
        {allBundled ? (
          <p>
            Dataset permissions are checked on every request. Image source:{' '}
            {studies.some((study) => study.image_source === 'dicomweb')
              ? 'configured archive (DICOMweb)'
              : 'linked DICOM files'}
            . Images are not stored in DuckDB.
          </p>
        ) : (
          <>
            <p>
              Orthanc:{' '}
              {orthanc.checked ? (orthanc.reachable ? 'Reachable' : 'Unreachable') : 'Not checked'}.{' '}
              {String(orthanc.message || '').trim()}
            </p>
            <p>OHIF: {String(source.ohif_public_url || '').trim() || 'Not configured'}</p>
            <p>DICOMweb: {String(source.dicomweb_public_url || '').trim() || 'Not configured'}</p>
          </>
        )}
      </details>
    </>
  );
}
export function createImagingHealthView(host) {
  let root;
  return {
    render(model) {
      if (!host) return;
      root ||= createRoot(host);
      root.render(<ImagingHealth model={model} />);
    },
  };
}
