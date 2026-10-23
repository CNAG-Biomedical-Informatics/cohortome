import httpx
import pydicom
import pytest
from fastapi import HTTPException

from app import dicom_remote, dicom


def test_desktop_never_enables_remote_dicom(monkeypatch):
    monkeypatch.setenv('COHORTOME_DESKTOP_MODE', 'true')
    monkeypatch.setenv('COHORTOME_DICOM_ENABLED', 'true')
    assert not dicom.dicom_enabled()
    with pytest.raises(HTTPException) as error:
        dicom_remote.connection()
    assert error.value.status_code == 404


@pytest.mark.parametrize('patient,status', [('P1', 200), ('OTHER', 502)])
def test_remote_metadata_requires_exact_patient_and_study(monkeypatch, patient, status):
    monkeypatch.setenv('COHORTOME_DESKTOP_MODE', 'false')
    monkeypatch.setenv('COHORTOME_DICOM_ENABLED', 'true')
    monkeypatch.setenv('COHORTOME_ORTHANC_INTERNAL_URL', 'http://archive.test:8042')
    ds = pydicom.Dataset()
    ds.PatientID = patient
    ds.StudyInstanceUID = '1.2.3'
    ds.SeriesInstanceUID = '1.2.3.1'
    ds.SOPInstanceUID = '1.2.3.1.1'
    def get(url, **kwargs):
        assert url == 'http://archive.test:8042/dicom-web/studies/1.2.3/metadata'
        assert kwargs['follow_redirects'] is False
        return httpx.Response(200, json=[ds.to_json_dict()], request=httpx.Request('GET', url))
    monkeypatch.setattr(dicom_remote.httpx, 'get', get)
    study = {'patient_id': 'P1', 'study_instance_uid': '1.2.3'}
    if status == 200:
        assert str(dicom_remote.metadata(study)[0][1].PatientID) == 'P1'
    else:
        with pytest.raises(HTTPException) as error:
            dicom_remote.metadata(study)
        assert error.value.status_code == status
