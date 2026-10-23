"""Read-only DICOMweb access for the configured Web deployment archive."""
import httpx
import pydicom
from fastapi import HTTPException

from app.dicom import dicom_enabled, _clean_uid
from app.env import app_env


def connection():
    if not dicom_enabled():
        raise HTTPException(404, 'No DICOMweb service enabled for this deployment.')
    base = app_env('COHORTOME_DICOMWEB_INTERNAL_URL', '').strip().rstrip('/')
    if not base:
        orthanc = app_env('COHORTOME_ORTHANC_INTERNAL_URL', '').strip().rstrip('/')
        base = orthanc + '/dicom-web' if orthanc else app_env('COHORTOME_DICOMWEB_PUBLIC_URL', '').strip().rstrip('/')
    if not base.startswith(('http://', 'https://')):
        raise HTTPException(503, 'Configure a server-accessible DICOMweb endpoint.')
    username = app_env('COHORTOME_ORTHANC_USERNAME', '').strip()
    password = app_env('COHORTOME_ORTHANC_PASSWORD', '')
    return base, (username, password) if username or password else None


def metadata(study):
    base, auth = connection()
    try:
        response = httpx.get(base + '/studies/' + study['study_instance_uid'] + '/metadata',
                             auth=auth, timeout=30, follow_redirects=False, trust_env=False)
        response.raise_for_status()
        records = response.json()
        rows = []
        for record in records:
            ds = pydicom.Dataset.from_json({key: value for key, value in record.items()
                                           if not key.upper().startswith('7FE0')})
            if str(ds.PatientID) != study['patient_id'] or str(ds.StudyInstanceUID) != study['study_instance_uid']:
                raise ValueError('Patient/study linkage mismatch')
            for value in (str(ds.SeriesInstanceUID), str(ds.SOPInstanceUID)):
                if not value or _clean_uid(value) != value:
                    raise ValueError('Invalid UID')
            rows.append((None, ds))
        if not rows:
            raise ValueError('Empty study')
        return rows
    except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError):
        raise HTTPException(502, 'Cannot read this study from DICOMweb or its patient link does not match.') from None


def pixel_stream(ds):
    base, auth = connection()
    # WADO-URI delivers one DICOM file, rather than a multipart WADO-RS body.
    # OHIF's dicomjson source expects a single file at each instance URL.
    wado = app_env('COHORTOME_WADO_INTERNAL_URL', '').strip()
    if not wado:
        orthanc = app_env('COHORTOME_ORTHANC_INTERNAL_URL', '').strip().rstrip('/')
        wado = orthanc + '/wado' if orthanc else ''
    if not wado.startswith(('http://', 'https://')):
        raise HTTPException(503, 'Configure the archive WADO-URI endpoint for embedded viewing.')
    client = httpx.Client(auth=auth, timeout=60, follow_redirects=False, trust_env=False)
    request = client.build_request('GET', wado, params={
        'requestType': 'WADO', 'studyUID': str(ds.StudyInstanceUID),
        'seriesUID': str(ds.SeriesInstanceUID), 'objectUID': str(ds.SOPInstanceUID),
        'contentType': 'application/dicom',
    })
    try:
        response = client.send(request, stream=True)
        response.raise_for_status()
        if response.headers.get('content-type', '').split(';')[0].lower() != 'application/dicom':
            raise ValueError('Unexpected image type')
    except (httpx.HTTPError, ValueError):
        client.close()
        raise HTTPException(502, 'Cannot retrieve this image from the configured archive.') from None
    def chunks():
        try:
            yield from response.iter_bytes()
        finally:
            response.close()
            client.close()
    return chunks()
