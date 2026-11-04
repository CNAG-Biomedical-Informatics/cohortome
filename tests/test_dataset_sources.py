import json

import pytest

from app import datasets, query_store
from app.dataset_sources import dataset_input_signature


@pytest.fixture
def package(tmp_path):
    (tmp_path / 'clinical').mkdir()
    (tmp_path / 'clinical/records.json').write_text('[{"id":"P1"}]')
    (tmp_path / 'assays').mkdir()
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'biosamples': {'file': 'specimens.json'},
        'identifiers': {'clarid_biosamples': {'file': 'labels.csv'}},
        'variants': {'genotypes_file': 'calls.tsv', 'annotations_file': 'annotations.tsv'}}))
    (tmp_path / 'assays/manifest.json').write_text(json.dumps({'assays': [
        {'file': 'assays/matrix.tsv', 'sample_metadata_file': 'assays/samples.tsv'}]}))
    for name in ['specimens.json', 'labels.csv', 'calls.tsv', 'annotations.tsv',
                 'assays/matrix.tsv', 'assays/samples.tsv']:
        (tmp_path / name).write_text('initial')
    return tmp_path


@pytest.mark.parametrize('name', ['specimens.json', 'labels.csv', 'calls.tsv',
    'annotations.tsv', 'assays/matrix.tsv', 'assays/samples.tsv', 'clinical/records.json'])
def test_workspace_detects_all_input_changes(package, monkeypatch, name):
    monkeypatch.setattr(query_store, '_workspace_dataset_ids', lambda _: [])
    before = datasets.workspace_fingerprint_for_data_dir(str(package))
    (package / name).write_text('changed contents')
    after = datasets.workspace_fingerprint_for_data_dir(str(package))
    assert before['token'] != after['token']
    assert str(package) not in json.dumps(after)
    assert before['token'] != datasets.workspace_fingerprint_for_data_dir(str(package))['token']


def test_missing_files_and_manifest_changes(package):
    initial = dataset_input_signature(package)
    (package / 'labels.csv').unlink()
    missing = dataset_input_signature(package)
    assert initial != missing
    assert {'name': 'labels.csv', 'missing': True} in missing
    (package / 'labels.csv').write_text('replacement')
    assert dataset_input_signature(package) != missing
    (package / 'README.md').write_text('Documentation is not an analytical input.')
    unchanged = dataset_input_signature(package)
    (package / 'README.md').write_text('Revised documentation')
    assert dataset_input_signature(package) == unchanged


def test_multi_dataset_fingerprint_uses_each_source(package, tmp_path, monkeypatch):
    other = tmp_path / 'other'
    (other / 'clinical').mkdir(parents=True)
    (other / 'clinical/records.json').write_text('[{"id":"P1"}]')
    monkeypatch.setattr(datasets, 'get_dataset', lambda key: {'root_path': str(package if key == 'a' else other)})
    def fingerprint():
        return datasets.workspace_fingerprint_for_data_dir(str(package), dataset_ids=['a', 'b'])
    before = fingerprint()
    (other / 'manifest.json').write_text('{"biosamples":{"file":"biosamples.json"}}')
    assert fingerprint()['token'] != before['token']
    assert [s['dataset_id'] for s in fingerprint()['source_files']] == ['a', 'b']


def test_query_store_tracks_same_declared_inputs(package, monkeypatch):
    monkeypatch.setattr(query_store, '_dataset_root_path', lambda _: package)
    before = query_store._dataset_source_signature('example')
    (package / 'labels.csv').write_text('new labels')
    assert query_store._dataset_source_signature('example') != before


def test_reject_external_declared_file(package):
    (package / 'manifest.json').write_text('{"biosamples":{"file":"../outside.json"}}')
    with pytest.raises(ValueError, match='inside its package'):
        dataset_input_signature(package)
