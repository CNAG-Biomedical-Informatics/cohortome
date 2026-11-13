"""Real tiny synthetic clinical/assay inputs through the shared scope endpoint."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import cohort_filters, cohort_scope, datasets, patient_overview, query_store, routes
from app.identities import decode_identity


@pytest.mark.parametrize('count', [1, 2])
def test_apply_scope_real_summary_assays_and_empty_selection(tmp_path, monkeypatch, count):
    monkeypatch.setattr(datasets, 'DATASET_REGISTRY_PATH', tmp_path / 'registry.json')
    monkeypatch.setattr(datasets, 'STATE_ROOT_DIR', tmp_path / 'state')
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    available, registry = [], []
    for key in ['one', 'two'][:count]:
        root = tmp_path / key
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical/records.json').write_text(json.dumps([
            {'id':f'{patient}:V1', 'patient_id':patient, 'sex':'female',
             'diseases':[{'diseaseCode':{'id':'TEST:1','label':'Example'}}]}
            for patient in ['P1', 'P2']]))
        (root / 'assays').mkdir()
        (root / 'assays/manifest.json').write_text(json.dumps({'assays':[{
            'assay_id':'protein', 'file':'assays/matrix.csv', 'modality':'proteomics',
            'data_type':'normalized_abundance', 'sample_metadata_file':'assays/samples.tsv', 'feature_count':1}]}))
        (root / 'assays/matrix.csv').write_text('feature_id,S1,S2\nF1,1,2\n')
        (root / 'assays/samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\nS2\tP2\n')
        available.append((key, str(root), key.title()))
        registry.append(dict(dataset_id=key, name=key.title(), root_path=str(root), enabled=True,
                             visibility='all_authenticated', data_classification='public'))
    datasets.DATASET_REGISTRY_PATH.write_text(json.dumps(registry))
    for key, _, _ in available:
        query_store.prepare_dataset_query_store(key)
    monkeypatch.setattr(patient_overview, 'sources', lambda *_: available)
    monkeypatch.setattr(cohort_scope, 'request_user_id', lambda _: 'scope-test')
    monkeypatch.setattr(cohort_filters, 'request_user_id', lambda _: 'scope-test')
    monkeypatch.setattr(cohort_scope, 'resolve_dataset_dir', lambda _, key: datasets.materialize_dataset_scope(datasets.parse_scope_dataset_ids(key)))
    monkeypatch.setattr(routes, '_sanitize_response_paths', lambda payload, _: payload)
    scope = datasets.dataset_scope_id([key for key, _, _ in available])
    app = FastAPI()
    app.include_router(cohort_scope.router)
    with TestClient(app) as client:
        selected_dataset = available[-1][0]
        response = client.post('/cohort-builder/apply', json=dict(workspace=scope,
            base_members=[dict(dataset_id=selected_dataset, patient_id='P1')], modalities=['proteomics']))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['selection']['patient_count'] == payload['summary']['totals']['patients'] == 1
        assert payload['summary']['totals']['clinical_records'] == 1
        assert [decode_identity(value) for value in payload['selection']['patient_ids']] == [(selected_dataset, 'patient', 'P1')]
        assert len(payload['summary']['characteristics']) == count
        assert sum(item['patients'] for item in payload['summary']['characteristics']) == 1
        assert len(payload['assays']) == 1
        assert payload['assays'][0]['dataset_name'] == ('two::protein' if count == 2 else 'protein')
        assert payload['assays'][0]['patient_count'] == payload['assays'][0]['sample_count'] == 1
        empty = client.post('/cohort-builder/apply', json=dict(workspace=scope, base_members=[]))
        assert empty.status_code == 200, empty.text
        assert empty.json()['summary']['totals']['patients'] == 0
        assert empty.json()['selection']['selection_active'] is True
        assert empty.json()['assays'] == []
        full = client.post('/cohort-builder/apply', json=dict(workspace=scope))
        assert full.status_code == 200, full.text
        assert full.json()['selection'] is None
        assert full.json()['summary']['totals']['patients'] == 2 * count
