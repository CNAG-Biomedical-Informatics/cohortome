import pytest
import json
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app import local_viewer as viewer

UID = '1.2.826.0.1.3680043.10.54321.1.1'


@pytest.mark.parametrize('platform,desktop,expected', [
    ('linux', 'true', True), ('linux', '', False),
    ('darwin', 'true', False), ('win32', 'true', False),
])
def test_software_rendering_is_limited_to_linux_desktop(monkeypatch, platform, desktop, expected):
    monkeypatch.setattr(viewer, 'require_authenticated', lambda _: {})
    monkeypatch.setattr(viewer.sys, 'platform', platform)
    monkeypatch.setenv('COHORTOME_DESKTOP_MODE', desktop)
    response = viewer.assets(None, 'app-config.js')
    config = json.loads(response.body.decode().removeprefix('window.config='))
    assert config['useCPURendering'] is expected
    assert config['defaultDataSourceName'] == 'dicomjson'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(viewer, 'require_authenticated', lambda _: {})
    monkeypatch.setattr(viewer, '_require_detailed_assay_access', lambda *a: ['default'])
    monkeypatch.setattr(viewer, '_resolve_route_dataset_dir', lambda *a: viewer.SYNTHETIC_ROOT)
    app = FastAPI()
    app.include_router(viewer.router)
    with TestClient(app) as client:
        yield client


def test_metadata_and_pixels_are_local_and_not_cached(client):
    response = client.get(f'/local-viewer/data/default/{UID}/metadata')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    study = response.json()['studies'][0]
    instance = study['series'][0]['instances'][0]
    assert isinstance(instance['metadata']['ImagePositionPatient'], list)
    url = instance['url'].removeprefix('dicomweb:')
    response = client.get(url)
    assert response.status_code == 200
    assert response.content[128:132] == b'DICM'
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('status', [401, 403])
def test_each_data_read_rechecks_permissions(client, monkeypatch, status):
    def denied(*args):
        raise HTTPException(status, 'Denied')
    target = 'require_authenticated' if status == 401 else '_require_detailed_assay_access'
    monkeypatch.setattr(viewer, target, denied)
    for suffix in ['metadata', UID + '.1.1']:
        assert client.get(f'/local-viewer/data/default/{UID}/{suffix}').status_code == status
    assert client.get(f'/local-viewer/open/default/{UID}').status_code == status


def test_other_roots_and_cross_dataset_ids_rejected(client, monkeypatch, tmp_path):
    assert client.get(f'/local-viewer/data/other/{UID}/metadata').status_code == 403
    monkeypatch.setattr(viewer, '_resolve_route_dataset_dir', lambda *a: tmp_path)
    assert client.get(f'/local-viewer/data/default/{UID}/metadata').status_code == 404


def test_unknown_images_and_asset_escape_rejected(client):
    assert client.get('/local-viewer/data/default/9.9/metadata').status_code == 404
    assert client.get(f'/local-viewer/data/default/{UID}/9.9').status_code == 404
    assert client.get('/local-viewer/..%2f..%2fPROJECT.md').status_code == 404
    assert 'disabled' in client.get('/local-viewer/sw.js').text
