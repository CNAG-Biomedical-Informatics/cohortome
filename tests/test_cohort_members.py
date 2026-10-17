import csv
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import cohorts, routes
from app.analysis_sessions import _normalize_scope_metadata
from app.cohort_members import resolve_members
from app.exports import cohort_bundle
from app.identities import identity_key
from app.schemas import SavedCohortRequest, SavedCohortResponse, AnalysisRequest


@pytest.fixture
def sources(tmp_path, monkeypatch):
    roots = {}
    for dataset in ['study-a', 'study-b']:
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical' / 'records.json').write_text(json.dumps([
            {'id': 'P001:V1', 'patient_id': 'P001'},
            {'id': f'{dataset}-P2:V2', 'patient_id': f'{dataset}-P2'},
        ]))
        roots[dataset] = str(root)
    monkeypatch.setattr(cohorts, 'USER_STATE_ROOT', tmp_path / 'user-state')
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: {'username':'local'})
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'local')
    monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda *a: list(roots))
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'detailed')
    monkeypatch.setattr(routes, 'resolve_dataset_dir', lambda req, identifier: roots.get(identifier, str(tmp_path / 'merged')))
    return roots


def test_identity_keys_are_stable_typed_and_collision_safe():
    assert identity_key('a', 'patient', 'b_c') != identity_key('a_b', 'patient', 'c')
    assert identity_key('a', 'patient', 'P001') != identity_key('b', 'patient', 'P001')
    assert identity_key('a', 'patient', 'P001') != identity_key('a', 'sample', 'P001')
    assert identity_key('étude', 'patient', 'P,01:雪') == identity_key('étude', 'patient', 'P,01:雪')


@pytest.mark.parametrize('id_type', ['patient', 'sample'])
def test_save_reopen_export_duplicate_source_ids(sources, id_type):
    members = [dict(dataset_id=d, patient_id='P001', **({'sample_id':'P001:V1'} if id_type == 'sample' else {})) for d in sources]
    request = SavedCohortRequest(dataset_id='scope--study-a--study-b', name='Cross-disease', members=members, id_type=id_type)
    saved = routes.create_saved_cohort(request, SimpleNamespace())
    assert saved['patient_count'] == 2
    assert saved['sample_count'] == (2 if id_type == 'sample' else 0)
    assert len({m['patient_key'] for m in saved['members']}) == 2
    loaded = routes.get_saved_cohorts(SimpleNamespace(), dataset_id='scope--study-a--study-b')['cohorts'][0]
    assert loaded['members'] == saved['members']
    assert SavedCohortResponse(**loaded).model_dump()['members'][0]['patient_key']
    with zipfile.ZipFile(io.BytesIO(cohort_bundle(loaded, []))) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read('membership.tsv').decode()), delimiter='\t'))
        assert [r['dataset_id'] for r in rows] == ['study-a', 'study-b']
        assert [r['patient_id'] for r in rows] == ['P001', 'P001']
        assert json.loads(archive.read('metadata.json'))['members'] == saved['members']
    restored = _normalize_scope_metadata(loaded)
    assert restored['members'] == loaded['members']
    assert restored['patient_count'] == 2
    assert restored['sample_count'] == saved['sample_count']


def test_bare_ids_are_resolved_only_when_unambiguous(sources):
    member = resolve_members(sources, patient_ids=['study-a-P2'])[0]
    assert member['dataset_id'] == 'study-a'
    with pytest.raises(ValueError, match='ambiguous'):
        resolve_members(sources, patient_ids=['P001'])
    with pytest.raises(ValueError, match='outside'):
        resolve_members(sources, members=[dict(dataset_id='other', patient_id='P001')])
    with pytest.raises(ValueError, match='sample link'):
        resolve_members(sources, id_type='sample', members=[dict(dataset_id='study-a', patient_id='P001', sample_id='study-a-P2:V2')])


def test_runner_reloads_authoritative_members_and_preserves_source(sources):
    saved = routes.create_saved_cohort(SavedCohortRequest(
        members=[dict(dataset_id='study-a', patient_id='study-a-P2')], id_type='patient'), SimpleNamespace())
    request = AnalysisRequest(prompt='Summary', scope_metadata={'id':saved['id']}, selected_patient_ids='P001')
    routes._resolve_saved_analysis_members(request, SimpleNamespace(), list(sources))
    assert request.selected_patient_ids == identity_key('study-a', 'patient', 'study-a-P2')
    assert request.scope_metadata['members'] == saved['members']
    for dataset in sources:
        member = resolve_members(sources, patient_ids=[identity_key(dataset, 'patient', 'P001')])[0]
        assert member['dataset_id'] == dataset
        assert member['patient_id'] == 'P001'
    with pytest.raises(HTTPException) as error:
        routes._resolve_saved_analysis_members(request, SimpleNamespace(), ['study-a'])
    assert error.value.status_code == 409


def test_saving_rechecks_detailed_access(sources, monkeypatch):
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'summary')
    with pytest.raises(HTTPException) as error:
        routes.create_saved_cohort(SavedCohortRequest(members=[dict(dataset_id='study-a', patient_id='P001')]), SimpleNamespace())
    assert error.value.status_code == 403


def test_analysis_chat_cannot_be_rebound_to_new_workspace(sources, monkeypatch):
    from app.schemas import AnalysisSessionRequest
    monkeypatch.setattr(routes, 'get_analysis_session', lambda *args, **kwargs: {'id': 'chat-1', 'dataset_id': 'study-a'})
    with pytest.raises(HTTPException) as error:
        routes.create_or_update_analysis_session(AnalysisSessionRequest(id='chat-1', dataset_id='scope--study-a--study-b'), SimpleNamespace())
    assert error.value.status_code == 409
    assert 'original workspace' in error.value.detail


def test_cohorts_from_separate_datasets_can_be_compared_in_combined_workspace(sources, monkeypatch):
    saved = []
    for dataset in sources:
        monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda *args, dataset=dataset: [dataset])
        saved.append(routes.create_saved_cohort(SavedCohortRequest(dataset_id=dataset,
            members=[dict(dataset_id=dataset, patient_id='P001')], id_type='patient'), SimpleNamespace()))
    scope = 'scope--study-a--study-b'
    listed = cohorts.list_saved_cohorts(scope)
    assert {item['id'] for item in listed} == {item['id'] for item in saved}
    assert len(cohorts.list_saved_cohorts('study-a')) == 1
    request = AnalysisRequest(prompt='Compare', compare_mode=True,
        scope_metadata={'id': saved[0]['id']}, compare_scope_metadata={'id': saved[1]['id']})
    routes._resolve_saved_analysis_members(request, SimpleNamespace(), list(sources))
    assert request.selected_patient_ids == identity_key('study-a', 'patient', 'P001')
    assert request.compare_selected_patient_ids == identity_key('study-b', 'patient', 'P001')
    pheno_cohorts = cohorts.get_saved_cohorts_by_ids([item['id'] for item in saved], scope)
    assert {item['patient_ids'][0] for item in pheno_cohorts} == {
        request.selected_patient_ids, request.compare_selected_patient_ids}
