import json

import pytest
from fastapi import HTTPException

from app import bff, routes, cohort_members
from app.identities import identity_key, qualified_member
from app.schemas import ClinicalSummaryRequest


def test_summary_filters_every_distribution_and_deduplicates_visits(tmp_path):
    clinical = tmp_path / 'clinical'
    clinical.mkdir()
    records = [dict(id=f'{pid}:{visit}', patient_id=pid, patient={'sex': sex},
                    diseases=[{'diseaseCode': {'label': disease}}],
                    treatments=[{'treatmentCode': {'label': 'Drug ' + disease}}])
               for pid, visit, sex, disease in [('P1', 'V1', 'female', 'A'),
                                               ('P1', 'V2', 'female', 'A'),
                                               ('P2', 'V1', 'male', 'B')]]
    (clinical / 'records.json').write_text(json.dumps(records))
    selected = bff.dashboard_summary(str(tmp_path), patient_ids=['P1'])
    assert selected['workspace_patient_count'] == 2
    assert selected['totals']['patients'] == 1
    assert selected['totals']['visits'] == 2
    assert selected['sex_counts'] == {'female': 1}
    assert selected['top_diseases'][0]['patient_count'] == 1
    assert selected['top_medications'] == [{'medication':'Drug A', 'patient_count':1, 'patients':['P1']}]
    assert [row['patient_id'] for row in selected['patients']] == ['P1']
    assert bff.dashboard_summary(str(tmp_path), patient_ids=[])['totals']['patients'] == 0
    assert bff.dashboard_summary(str(tmp_path))['totals']['patients'] == 2


@pytest.fixture
def selection_route(monkeypatch):
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda *_: ['alpha', 'beta'])
    monkeypatch.setattr(routes, 'resolve_dataset_dir', lambda _, key: key)
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'detailed')
    monkeypatch.setattr(routes, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(routes, 'clinical_representation', lambda _: 'snapshot')
    monkeypatch.setattr(routes, '_sanitize_response_paths', lambda payload, _: payload)
    monkeypatch.setattr(cohort_members, 'source_inventory', lambda _: ({'P1'}, {}))
    calls = []
    def summary(root, patient_ids):
        calls.append(patient_ids)
        return {'totals': {'visits': 1, 'patients': len(patient_ids)}}
    monkeypatch.setattr(routes, 'dashboard_summary', summary)
    return calls


def test_route_preserves_dataset_identity(selection_route):
    payload = ClinicalSummaryRequest(dataset_id='workspace', members=[{'dataset_id':'beta', 'patient_id':'P1'}])
    assert routes.selected_clinical_summary(payload, None)['selection_count'] == 1
    assert selection_route == [[identity_key('beta', 'patient', 'P1')]]


@pytest.mark.parametrize('fields', [{}, {'members':[]}, {'patient_ids':['P1']},
    {'members':[{'dataset_id':'outside', 'patient_id':'P1'}]}])
def test_route_rejects_empty_ambiguous_and_outside_selection(selection_route, fields):
    with pytest.raises(HTTPException) as error:
        routes.selected_clinical_summary(ClinicalSummaryRequest(dataset_id='workspace', **fields), None)
    assert error.value.status_code == 400
    assert not selection_route


def test_query_handle_uses_complete_membership(selection_route, monkeypatch):
    ids = [identity_key(d, 'patient', 'P1') for d in ['alpha', 'beta']]
    monkeypatch.setattr(routes, '_load_authorized_query_result', lambda *a, **k: ({}, {'patient_ids':ids}))
    result = routes.selected_clinical_summary(ClinicalSummaryRequest(dataset_id='workspace', result_handle='qr_test'), None)
    assert result['selection_count'] == 2
    assert selection_route == [ids]


def test_summary_only_access_is_rejected(selection_route, monkeypatch):
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'summary')
    with pytest.raises(HTTPException) as error:
        routes.selected_clinical_summary(ClinicalSummaryRequest(dataset_id='workspace', patient_ids=['P1']), None)
    assert error.value.status_code == 403
    assert not selection_route


def test_saved_sample_cohort_summarizes_unique_patients(selection_route, monkeypatch):
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'owner')
    monkeypatch.setattr(routes, 'list_saved_cohorts', lambda **_: [dict(id='saved', dataset_ids=['alpha'],
        members=[qualified_member(dict(dataset_id='alpha', patient_id='P1', sample_id=s)) for s in ['S1', 'S2']])])
    # Clinical selection uses patient identity, irrespective of the selected sample/visit.
    monkeypatch.setattr(cohort_members, 'source_inventory', lambda _: ({'P1'}, {'S1':{'P1'}, 'S2':{'P1'}}))
    result = routes.selected_clinical_summary(ClinicalSummaryRequest(dataset_id='workspace', cohort_id='saved'), None)
    assert result['selection_count'] == 1
