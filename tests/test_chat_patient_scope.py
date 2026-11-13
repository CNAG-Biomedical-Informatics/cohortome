from contextlib import nullcontext

import pytest
from fastapi import HTTPException

import app.query as query
import app.routes as routes
from app.identities import identity_key
from app.schemas import QueryRequest
from bff_test_helpers import make_request, write_json


@pytest.fixture
def dataset(tmp_path):
    clinical = tmp_path / 'clinical'
    clinical.mkdir()
    write_json(clinical, 'patients.json', [
        {'id': pid, 'patient': {'sex': sex}, 'diseases': [{'diseaseCode': {'label': 'Example disease'}}]}
        for pid, sex in [('P1', 'female'), ('P2', 'male')]
    ])
    return str(tmp_path)


def test_captured_scope_applies_without_followup_wording(dataset):
    result = query.answer_query(dataset, 'List all patients in the workspace',
                                scoped_patient_ids=['P1'], force_scope=True)
    assert result['data']['patient_ids'] == ['P1']
    assert result['data']['patient_count'] == 1


def test_empty_scope_does_not_load_workspace_or_call_model(monkeypatch):
    monkeypatch.setattr(query, '_build_query_scope_context', lambda *a, **kw: pytest.fail('Empty scope accessed workspace'))
    result = query.answer_query('/not-used', 'List all patients', scoped_patient_ids=[], force_scope=True, query_mode='llm_only')
    assert result['intent'] == 'empty_scope'
    assert result['data']['patient_count'] == 0


def test_explicit_patient_lookup_cannot_escape_chat_scope(dataset, monkeypatch):
    original = query.build_patient_workspace
    def checked(path, pid):
        assert pid != 'P2'
        return original(path, pid)
    monkeypatch.setattr(query, 'build_patient_workspace', checked)
    result = query.answer_query(dataset, 'Show patient P2', scoped_patient_ids=['P1'], force_scope=True)
    assert 'not in this chat' in result['reply']


def test_model_context_never_includes_outside_patient_detail(dataset, monkeypatch):
    monkeypatch.setattr(query, '_lm_studio_include_patient_workspace', lambda: True)
    context = query._lm_studio_context(dataset, 'Show patient P2', scoped_patient_ids=['P1'])
    assert 'patient_workspace' not in context
    assert [row['patient_id'] for row in context['patient_summaries']] == ['P1']


@pytest.fixture
def query_route(monkeypatch, dataset):
    monkeypatch.setattr(routes, 'require_authenticated', lambda request: None)
    monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda request, value: ['a'])
    monkeypatch.setattr(routes, 'resolve_dataset_dir', lambda request, value: dataset)
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda ids: 'detailed')
    monkeypatch.setattr(routes, 'selected_lm_provider_id', lambda request: '')
    monkeypatch.setattr(routes, 'selected_ai_provider_access', lambda *args: 'blocked')
    monkeypatch.setattr(routes, 'lm_provider_context', lambda *args: nullcontext())
    monkeypatch.setattr(routes, '_authorized_datasets_for_request', lambda request: [])
    monkeypatch.setattr(routes, '_materialize_query_response', lambda payload, *args, **kw: payload)
    monkeypatch.setattr(routes, '_sanitize_response_paths', lambda payload, *args: payload)
    captured = {}
    def answer(*args, **kwargs):
        captured.update(kwargs)
        return {'reply': 'test', 'data': {}}
    monkeypatch.setattr(routes, 'answer_query', answer)
    return captured, make_request({'username': 'tester'})


def test_scope_route_intersects_full_followup_membership(query_route, monkeypatch):
    captured, request = query_route
    monkeypatch.setattr(routes, '_load_authorized_query_result', lambda *a, **kw: ({}, {'patient_ids': ['P1', 'P2']}))
    routes.query_app_post(QueryRequest(q='List patients', dataset_id='a', scoped_result_handle='qr_example',
        scope_metadata={'selection_active': True, 'members': [{'dataset_id':'a', 'patient_id':'P1'}]}), request)
    assert captured['scoped_patient_ids'] == ['P1']
    assert captured['force_scope'] is True


def test_scope_route_rejects_outside_workspace_members(query_route):
    _, request = query_route
    with pytest.raises(HTTPException) as error:
        routes.query_app_post(QueryRequest(q='List patients', dataset_id='a',
            scope_metadata={'selection_active':True, 'members':[{'dataset_id':'other', 'patient_id':'P1'}]}), request)
    assert error.value.status_code == 409


def test_scope_route_accepts_empty_as_explicit_selection(query_route):
    captured, request = query_route
    routes.query_app_post(QueryRequest(q='List patients', dataset_id='a',
        scope_metadata={'selection_active':True, 'members':[]}), request)
    assert captured['scoped_patient_ids'] == []
    assert captured['force_scope'] is True


def test_large_chat_scope_is_not_truncated_to_query_page_size(query_route, monkeypatch):
    captured, request = query_route
    ids = [f'P{i}' for i in range(20000)]
    monkeypatch.setattr('app.cohort_members.source_inventory', lambda root: (set(ids), {}))
    routes.query_app_post(QueryRequest(q='List patients', dataset_id='a',
        scope_metadata={'selection_active':True, 'members':[{'dataset_id':'a', 'patient_id':pid} for pid in ids]}), request)
    assert len(captured['scoped_patient_ids']) == 20000


def test_empty_scope_is_rejected_by_analysis_and_pheno(query_route):
    _, request = query_route
    scope = {'selection_active':True, 'members':[]}
    with pytest.raises(HTTPException) as analysis_error:
        routes._resolve_saved_analysis_members(routes.AnalysisRequest(prompt='Summary', scope_metadata=scope), request, ['a'])
    assert analysis_error.value.status_code == 400
    with pytest.raises(HTTPException) as pheno_error:
        routes.run_pheno_ranker_route(routes.PhenoRankerRequest(scope_metadata=scope), request)
    assert pheno_error.value.status_code == 400
