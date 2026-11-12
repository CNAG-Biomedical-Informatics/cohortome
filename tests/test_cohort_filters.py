"""Clinical filtering with entirely fictional, heterogeneous datasets."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import cohort_filters as filters, query_store


def measurement(value, *, code='TEST:M1', label='Marker', unit='mg/L'):
    return {'assayCode': {'id': code, 'label': label},
            'measurementValue': {'quantity': {'value': value, 'unit': {'label': unit} if unit else None}}}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(query_store, 'list_registered_datasets', lambda: [])
    available = []
    for dataset in ('a', 'b'):
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        records = [
            {'id': 'P1:V1', 'sex': {'label': 'Female'}, 'info': {'event_date': '2025-01-01', 'private_note': 'Never expose'},
             'measures': [measurement('1' if dataset == 'a' else 5, label='Marker' if dataset == 'a' else 'Other label')],
             'phenotypicFeatures': [{'featureType': {'id': 'TEST:F1', 'label': 'Fatigue'}, 'excluded': True}]},
            {'id': 'P1:V2', 'measures': [measurement(9)]},
            {'id': 'P2:V1', 'sex': {'label': 'Male'}, 'measures': [measurement(0)],
             'phenotypicFeatures': [{'featureType': {'id': 'TEST:F1', 'label': 'Fatigue'}, 'excluded': False}]},
            {'id': 'P3:V1', 'measures': [measurement(None)]},
            {'id': 'P4:V1', 'measures': [measurement(-1)]},
            {'id': 'P5:V1', 'measures': [measurement(False, code='TEST:BOOL', label='Boolean', unit=None)]},
            {'id': 'P6:V1', 'measures': [measurement(4, code='TEST:UNKNOWN_UNIT', unit=None)]},
            {'id': 'P8:V1', 'measures': [{'assayCode': {'id': 'TEST:CATEGORY', 'label': 'Categorical marker'},
                'measurementValue': {'ontologyTerm': {'id': 'TEST:NEG', 'label': 'Negative'}}}]},
        ]
        if dataset == 'b':
            records.append({'id': 'P7:V1', 'measures': [measurement(2, unit='mmol/L')]})
        (root / 'clinical/records.json').write_text(json.dumps(records))
        query_store.ensure_query_store(str(root))
        available.append((dataset, str(root), f'Dataset {dataset}'))
    monkeypatch.setattr(filters.patient_overview, 'sources', lambda *args: available)
    monkeypatch.setattr(filters.patient_overview, 'sample_inventory', lambda *args, **kwargs: ([{'patient_id': 'ASSAY_ONLY'}], []))
    monkeypatch.setattr(filters.patient_overview, 'biosample_records', lambda *args, **kwargs: [])
    from app import dicom
    monkeypatch.setattr(dicom, 'dicom_studies', lambda root: [])
    monkeypatch.setattr(filters, 'request_user_id', lambda _: 'test-user')
    return available


def catalogue(workspace):
    return filters.fields(SimpleNamespace(), 'scope')


def pick(payload, label='Marker', unit='mg/L', kind='number'):
    return next(f for f in payload['fields'] if label in f['label'] and f['unit'] == unit and f['kind'] == kind)


def evaluate(payload, field, operator, values=()):
    body = filters.FilterRequest(workspace='scope', fingerprint=payload['fingerprint'],
        filters=[dict(field_id=field['id'], operator=operator, values=list(values))])
    return filters.evaluate(body, SimpleNamespace())


def ids(result):
    return {(m['dataset_id'], m['patient_id']) for m in result['members']}


def test_catalogue_coded_measurements_units_and_metadata(workspace):
    payload = catalogue(workspace)
    marker = pick(payload)
    assert marker['dataset_ids'] == ['a', 'b']
    assert pick(payload, unit='mmol/L')['dataset_ids'] == ['b']
    unknown = [f for f in payload['fields'] if 'TEST:UNKNOWN_UNIT' in f['label']]
    assert len(unknown) == 2 and all(len(f['dataset_ids']) == 1 for f in unknown)
    assert 'private_note' not in str(payload)
    assert not any(k.startswith('_') for f in payload['fields'] for k in f)
    assert len(payload['fingerprint']) == 64


def test_any_visit_same_observation_range_and_negative(workspace):
    payload = catalogue(workspace)
    field = pick(payload)
    assert ids(evaluate(payload, field, 'between', [2, 8])) == {('b', 'P1')}
    assert ids(evaluate(payload, field, 'ne', [1])) == {
        ('a', 'P2'), ('a', 'P4'), ('b', 'P1'), ('b', 'P2'), ('b', 'P4')}
    assert ids(evaluate(payload, field, 'eq', [0])) == {('a', 'P2'), ('b', 'P2')}
    assert ids(evaluate(payload, field, 'lt', [0])) == {('a', 'P4'), ('b', 'P4')}


def test_missing_includes_assay_only_but_not_unsupported_dataset(workspace):
    payload = catalogue(workspace)
    missing = ids(evaluate(payload, pick(payload), 'is_missing'))
    assert {('a', 'P3'), ('b', 'P3'), ('a', 'ASSAY_ONLY'), ('b', 'ASSAY_ONLY')} <= missing
    assert ('a', 'P2') not in missing
    b_only = ids(evaluate(payload, pick(payload, unit='mmol/L'), 'is_missing'))
    assert b_only and all(dataset == 'b' for dataset, _ in b_only)


def test_boolean_and_excluded_phenotypes(workspace):
    payload = catalogue(workspace)
    boolean = pick(payload, label='Boolean', unit='', kind='boolean')
    assert ids(evaluate(payload, boolean, 'eq', [False])) == {('a', 'P5'), ('b', 'P5')}
    phenotype = next(f for f in payload['fields'] if f['label'] == 'Non-excluded phenotypes' and f['dataset_ids'] == ['a'])
    assert ids(evaluate(payload, phenotype, 'in', ['TEST:F1 · Fatigue'])) == {('a', 'P2')}
    for operator, values in [('is_missing', []), ('ne', ['TEST:F1 · Fatigue'])]:
        with pytest.raises(HTTPException) as exc:
            evaluate(payload, phenotype, operator, values)
        assert exc.value.status_code == 422


def test_categorical_measurements_keep_ontology_codes(workspace):
    payload = catalogue(workspace)
    field = pick(payload, label='Categorical marker', unit='', kind='string')
    assert field['dataset_ids'] == ['a', 'b']
    assert field['options'] == ['TEST:NEG · Negative']
    assert ids(evaluate(payload, field, 'eq', ['TEST:NEG · Negative'])) == {('a', 'P8'), ('b', 'P8')}
    assert ids(evaluate(payload, field, 'eq', ['Negative'])) == set()


@pytest.mark.parametrize('operator, values', [('eq', ['1']), ('eq', [True]), ('eq', [float('inf')]), ('eq', [10**1000]),
    ('between', [9, 1]), ('between', [2]), ('contains', ['x']), ('is_missing', [1]), ('drop table', [])])
def test_rejects_invalid_numeric_rules(workspace, operator, values):
    payload = catalogue(workspace)
    with pytest.raises(HTTPException) as exc:
        evaluate(payload, pick(payload), operator, values)
    assert exc.value.status_code == 422


def test_literal_strings_and_combined_clauses(workspace):
    payload = catalogue(workspace)
    sex = next(f for f in payload['fields'] if f['label'] == 'Sex')
    assert ids(evaluate(payload, sex, 'eq', ["Female' OR TRUE --"])) == set()
    body = filters.FilterRequest(workspace='scope', fingerprint=payload['fingerprint'], filters=[
        dict(field_id=pick(payload)['id'], operator='gt', values=[2]),
        dict(field_id=sex['id'], operator='eq', values=['Female'])])
    assert ids(filters.evaluate(body, SimpleNamespace())) == {('a', 'P1'), ('b', 'P1')}


def test_date_values_are_validated_before_sql(workspace):
    payload = catalogue(workspace)
    field = next(f for f in payload['fields'] if f['kind'] == 'date')
    assert ids(evaluate(payload, field, 'gte', ['2025-01-01'])) == {('a', 'P1'), ('b', 'P1')}
    with pytest.raises(HTTPException) as exc:
        evaluate(payload, field, 'eq', ['2025-02-30'])
    assert exc.value.status_code == 422


def test_stale_fingerprint_and_unknown_field_fail_closed(workspace):
    payload = catalogue(workspace)
    path = Path(workspace[0][1]) / 'clinical/records.json'
    path.write_text(path.read_text() + ' ')
    with pytest.raises(HTTPException) as exc:
        evaluate(payload, pick(payload), 'eq', [0])
    assert exc.value.status_code == 409
    current = catalogue(workspace)
    with pytest.raises(HTTPException) as exc:
        evaluate(current, {'id': 'no-such-field'}, 'eq', [0])
    assert exc.value.status_code == 422


@pytest.mark.parametrize('status', [401, 403])
def test_authorization_before_discovery_or_evaluation(workspace, monkeypatch, status):
    def deny(*args):
        raise HTTPException(status, 'Denied')
    monkeypatch.setattr(filters.patient_overview, 'sources', deny)
    with pytest.raises(HTTPException) as exc:
        catalogue(workspace)
    assert exc.value.status_code == status
    body = filters.FilterRequest(workspace='scope', fingerprint='a' * 64)
    with pytest.raises(HTTPException) as exc:
        filters.evaluate(body, SimpleNamespace())
    assert exc.value.status_code == status


def test_filter_request_limits_and_router_schema():
    from fastapi import FastAPI
    from pydantic import ValidationError
    app = FastAPI()
    app.include_router(filters.router)
    assert '/cohort-builder/fields' in app.openapi()['paths']
    assert '/cohort-builder/evaluate' in app.openapi()['paths']
    with pytest.raises(ValidationError):
        filters.FilterRequest(workspace='scope', fingerprint='a' * 64,
            filters=[dict(field_id='x', operator='eq', values=[1])] * 21)
    with pytest.raises(ValidationError):
        filters.FilterClause(field_id='x', operator='eq', values=[1], sql='SELECT *')


def test_missing_filter_refuses_incomplete_coverage(workspace, monkeypatch):
    payload = catalogue(workspace)
    monkeypatch.setattr(filters.patient_overview, 'sample_inventory', lambda *args, **kwargs: ([], ['Unlinked samples']))
    with pytest.raises(HTTPException) as exc:
        evaluate(payload, pick(payload), 'is_missing')
    assert exc.value.status_code == 409
