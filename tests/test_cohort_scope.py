"""Explicit combined filter application, using fictional patients only."""
import pytest
from fastapi import HTTPException
from app import cohort_scope as scope


@pytest.fixture
def setup(monkeypatch):
    sources = [('a', '/a', 'A'), ('b', '/b', 'B')]
    monkeypatch.setattr(scope.patient_overview, 'sources', lambda *_: sources)
    monkeypatch.setattr(scope, 'request_user_id', lambda _: 'user')
    monkeypatch.setattr(scope.cohort_filters, '_fingerprint', lambda *_: 'f' * 64)
    rows = [dict(dataset_id=d, patient_id=p, diseases=[disease], modalities=modalities)
            for d, p, disease, modalities in [
                ('a', 'P1', 'A', ['clinical', 'transcriptomics', 'olink']),
                ('b', 'P1', 'A', ['clinical', 'proteomics']),
                ('b', 'P2', 'B', ['clinical', 'transcriptomics', 'proteomics']),
                ('a', 'ASSAY_ONLY', '', ['transcriptomics'])]]
    monkeypatch.setattr(scope.patient_overview, 'coverage', lambda *_: {'patients':rows, 'warnings':[]})
    monkeypatch.setattr(scope, '_response', lambda request, workspace, available, members, label, fingerprint:
                        {'members':members, 'label':label})
    return rows


def test_disease_and_modality_filters_are_intersected(setup):
    result = scope.apply_draft(scope.Draft(workspace='ws', diseases=['a'], modalities=['proteomics', 'transcriptomics']), None)
    assert [(m['dataset_id'], m['patient_id']) for m in result['members']] == [('a', 'P1')]


def test_empty_is_not_full_and_no_filters_restore_full(setup):
    assert scope.apply_draft(scope.Draft(workspace='ws', diseases=['Absent']), None)['members'] == []
    assert scope.apply_draft(scope.Draft(workspace='ws'), None)['members'] is None
    assert scope.apply_draft(scope.Draft(workspace='ws', base_members=[]), None)['members'] == []


def test_exact_keeps_clinical_optional_and_assay_only_patients(setup):
    result = scope.apply_draft(scope.Draft(workspace='ws', modalities=['transcriptomics'], exact=True), None)
    assert [(m['dataset_id'], m['patient_id']) for m in result['members']] == [('a', 'ASSAY_ONLY')]


def test_clinical_evaluated_once_and_intersected(setup, monkeypatch):
    calls = []
    def evaluate(body, _):
        calls.append(body)
        return {'members':[dict(dataset_id='b', patient_id='P2')], 'description':'Example rule'}
    monkeypatch.setattr(scope.cohort_filters, 'evaluate', evaluate)
    body = scope.Draft(workspace='ws', clinical_filters=[dict(field_id='test', operator='eq', values=[1])],
                       fingerprint='f'*64, modalities=['transcriptomics'])
    result = scope.apply_draft(body, None)
    assert len(calls) == 1
    assert result['members'][0]['dataset_id'] == 'b'
    body.fingerprint = 'old'
    with pytest.raises(HTTPException) as exc:
        scope.apply_draft(body, None)
    assert exc.value.status_code == 409
    assert len(calls) == 1


def test_incomplete_modality_coverage_fails_closed(setup, monkeypatch):
    monkeypatch.setattr(scope.patient_overview, 'coverage', lambda *_: {'patients':setup, 'warnings':['Unlinked samples']})
    with pytest.raises(HTTPException) as exc:
        scope.apply_draft(scope.Draft(workspace='ws', modalities=['proteomics']), None)
    assert exc.value.status_code == 409


def test_scoped_search_checks_dataset_authorization_and_keeps_empty(setup, monkeypatch):
    result = scope.scoped_search(scope.ScopedSearch(members=[]), None, 'ws', offset=0)
    assert result == {'matches':[], 'total':0, 'next':None}
    with pytest.raises(HTTPException) as exc:
        scope.scoped_search(scope.ScopedSearch(members=[dict(dataset_id='outside', patient_id='P1')]), None, 'ws', offset=0)
    assert exc.value.status_code == 403
