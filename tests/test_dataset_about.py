from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import dataset_about as about


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(about, 'require_authenticated', lambda request: {'username': 'reader'})
    monkeypatch.setattr(about, 'authorized_datasets_for_user', lambda user: [
        {'dataset_id': 'demo', 'root_path': str(tmp_path), 'name': 'Demo', 'description': 'Study notes'}])
    app = FastAPI()
    app.include_router(about.router)
    return TestClient(app)


def test_about_reads_only_package_documentation(client, tmp_path):
    (tmp_path / 'README.md').write_text('# Demo\n\nStudy limitations.', encoding='utf-8')
    (tmp_path / 'TERMS.md').write_text('Attribution', encoding='utf-8')
    (tmp_path / 'provenance.json').write_text('{"private_path":"not exposed"}')
    response = client.get('/datasets/demo/about')
    assert response.status_code == 200
    data = response.json()
    assert data['name'] == 'Demo'
    assert [d['title'] for d in data['documents']] == ['Overview', 'Terms and attribution']
    assert 'private_path' not in response.text
    assert str(tmp_path) not in response.text


def test_about_denies_inaccessible_dataset_before_reading(client, monkeypatch):
    def unexpected(*args):
        pytest.fail('Must authorize before accessing disk')
    monkeypatch.setattr(about, 'resolve_project_data_dir', unexpected)
    assert client.get('/datasets/other/about').status_code == 404


def test_about_without_documents(client):
    assert client.get('/datasets/demo/about').json()['documents'] == []


@pytest.mark.parametrize('registered, expected', [
    ('Imported resource 0.1.0', 'Clinical records and measured RNA expression.'),
    ('', 'Clinical records and measured RNA expression.'),
    ('An edited summary.', 'An edited summary.'),
])
def test_package_summary_for_old_imports(client, tmp_path, monkeypatch, registered, expected):
    monkeypatch.setattr(about, 'authorized_datasets_for_user', lambda user: [
        {'dataset_id': 'demo', 'root_path': str(tmp_path), 'description': registered}])
    (tmp_path / 'resource.json').write_text(
        '{"description":"Clinical records and measured RNA expression."}')
    assert client.get('/datasets/demo/about').json()['description'] == expected


def test_document_url_is_authorized_and_plain_text(client, tmp_path):
    (tmp_path / 'README.md').write_text('# Summary\n<script>not executable</script>')
    response = client.get('/datasets/demo/about/README.md')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    assert 'content-disposition' not in response.headers
    assert client.get('/datasets/other/about/README.md').status_code == 404
    assert client.get('/datasets/demo/about/provenance.json').status_code == 404


def test_about_rejects_symlinks_and_oversized_documents(client, tmp_path):
    (tmp_path / 'source.txt').write_text('Do not publish')
    (tmp_path / 'README.md').symlink_to(tmp_path / 'source.txt')
    (tmp_path / 'TERMS.md').write_bytes(b'x' * (about.MAX_DOCUMENT_BYTES + 1))
    data = client.get('/datasets/demo/about').json()
    assert data['documents'] == []
    assert len(data['unavailable']) == 2


def test_about_missing_package_keeps_description(client, monkeypatch):
    def missing(*args):
        raise FileNotFoundError('private/path')
    monkeypatch.setattr(about, 'resolve_project_data_dir', missing)
    response = client.get('/datasets/demo/about')
    assert response.json()['description'] == 'Study notes'
    assert 'private/path' not in response.text
