import json
import shutil
from pathlib import Path

import pydicom
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import dicom_files, local_viewer as viewer


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(dicom_files, 'STATE_ROOT_DIR', tmp_path / 'state')
    root = viewer.SYNTHETIC_ROOT
    folder = tmp_path / 'images'
    folder.mkdir()
    source = next((root / 'assays/imaging/dicom').glob('*.dcm'))
    image = folder / 'image'  # DICOM files do not require a .dcm extension.
    shutil.copyfile(source, image)
    ds = pydicom.dcmread(image)
    monkeypatch.setattr(viewer, 'require_authenticated', lambda _: {})
    monkeypatch.setattr(viewer, 'require_admin', lambda _: {})
    monkeypatch.setattr(viewer, '_require_detailed_assay_access', lambda *a: ['study'])
    monkeypatch.setattr(viewer, '_resolve_route_dataset_dir', lambda *a: root)
    from app import config
    monkeypatch.setattr(config, 'private_artifact_runtime_is_safe', lambda: True)
    app = FastAPI()
    app.include_router(viewer.router)
    with TestClient(app) as client:
        yield root, folder, image, ds, client


def test_link_and_view_without_copying_images(setup):
    root, folder, image, ds, client = setup
    original = image.read_bytes()
    response = client.post('/local-viewer/datasets/study/folder', json={'directory': str(folder)})
    assert response.status_code == 200
    assert response.json() == {'studies': 1, 'instances': 1, 'patients': 1}
    assert image.read_bytes() == original
    metadata = client.get(f'/local-viewer/data/study/{ds.StudyInstanceUID}/metadata')
    assert metadata.status_code == 200
    url = metadata.json()['studies'][0]['series'][0]['instances'][0]['url'].removeprefix('dicomweb:')
    assert client.get(url).content == original
    assert client.get(url).headers['cache-control'] == 'no-store'
    image.write_bytes(original + b'changed')
    assert client.get(url).status_code == 409


def test_invalid_link_preserves_previous_index(setup):
    root, folder, image, ds, client = setup
    dicom_files.link_folder(root, folder)
    previous = dicom_files.index_path(root).read_bytes()
    ds.PatientID = 'NO-MATCH'
    ds.save_as(image)
    response = client.post('/local-viewer/datasets/study/folder', json={'directory': str(folder)})
    assert response.status_code == 400
    assert 'nothing was linked' in response.json()['detail']
    assert dicom_files.index_path(root).read_bytes() == previous


def test_duplicates_and_symlinks_rejected(setup):
    root, folder, image, ds, client = setup
    duplicate = folder / 'duplicate.dcm'
    shutil.copyfile(image, duplicate)
    with pytest.raises(ValueError, match='Duplicate'):
        dicom_files.link_folder(root, folder)
    duplicate.unlink()
    duplicate.symlink_to(image)
    with pytest.raises(ValueError, match='Symbolic'):
        dicom_files.link_folder(root, folder)


def test_admin_and_dataset_permissions_rechecked(setup, monkeypatch):
    root, folder, image, ds, client = setup
    dicom_files.link_folder(root, folder)
    def denied(*a):
        raise HTTPException(403, 'Denied')
    monkeypatch.setattr(viewer, 'require_admin', denied)
    assert client.post('/local-viewer/datasets/study/folder', json={'directory': str(folder)}).status_code == 403
    monkeypatch.setattr(viewer, '_require_detailed_assay_access', denied)
    assert client.get(f'/local-viewer/data/study/{ds.StudyInstanceUID}/metadata').status_code == 403
    assert client.get(f'/local-viewer/data/study/{ds.StudyInstanceUID}/{ds.SOPInstanceUID}').status_code == 403


def test_naturalized_metadata_preserves_sequences():
    ds = pydicom.Dataset()
    child = pydicom.Dataset()
    child.SliceThickness = '2.5'
    ds.SharedFunctionalGroupsSequence = [child]
    assert viewer.natural_metadata(ds)['SharedFunctionalGroupsSequence'][0]['SliceThickness'] == 2.5
