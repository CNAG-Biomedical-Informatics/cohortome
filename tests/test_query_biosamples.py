import json

import pytest

from app import query, query_biosamples as origins, query_store
from app.identities import identity_key


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'stores')
    monkeypatch.setattr(origins, '_workspace_dataset_ids', lambda _: [])
    monkeypatch.setattr(query, '_lm_studio_enabled', lambda: False)
    (tmp_path / 'clinical').mkdir()
    (tmp_path / 'clinical/individuals.json').write_text(json.dumps([
        {'id': 'P1', 'diseases': [{'diseaseCode': {'id': 'X:1', 'label': 'Example disease'}}]},
        {'id': 'P2'}, {'id': 'P3'}]))
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'schema_version':1, 'clinical':{'representation':'person'}, 'biosamples':{'file':'biosamples.json'}}))
    (tmp_path / 'biosamples.json').write_text(json.dumps([
        {'id':'S1', 'individualId':'P1', 'sampleOriginType':{'id':'UBERON:1', 'label':'skin'}},
        {'id':'S2', 'individualId':'P1', 'sampleOriginType':{'id':'UBERON:1', 'label':'skin'}},
        {'id':'S3', 'individualId':'P2', 'sampleOriginType':{'id':'UBERON:2', 'label':'liver'}},
        {'id':'S4', 'individualId':'P3'},
    ]))
    return tmp_path


@pytest.mark.parametrize('question', ['Which patients have skin samples?',
    'List patients with skin specimens', 'Show patients with samples from UBERON:1',
    'How many patients have SKIN biosamples?'])
def test_deterministic_origins_select_patients_not_samples(package, question):
    result = query.answer_query(str(package), question, query_mode='deterministic_only')
    assert result['intent'] == 'sample_origin_cohort'
    assert result['data']['patient_count'] == 1
    if not question.startswith('How many'):
        assert result['data']['patient_ids'] == ['P1']
        assert result['data']['id_type'] == 'patient'
        assert result['action_context']['id_type'] == 'patient'
        assert result['action_context']['record_ids'] == []
    else:
        assert 'patient_ids' not in result['data']
    assert 'S1' not in json.dumps(result)


def test_inventory_and_previous_selection(package):
    result = query.answer_query(str(package), 'Which sample origins are available?', query_mode='deterministic_only')
    assert result['intent'] == 'sample_origin_inventory'
    assert [(r['label'], r['patient_count']) for r in result['data']['sample_origins']] == [('liver', 1), ('skin', 1)]
    scoped = query.answer_query(str(package), 'Which tissues are available?', query_mode='deterministic_only',
        history=[{'role':'user', 'content':'Select P2'}], scoped_patient_ids=['P2'])
    assert [r['label'] for r in scoped['data']['sample_origins']] == ['liver']


def test_unknown_ambiguous_and_missing_metadata_are_not_guessed(package):
    assert query.answer_query(str(package), 'Which patients have brain samples?', query_mode='deterministic_only')['intent'] == 'sample_origin_clarification'
    path = package / 'biosamples.json'
    rows = json.loads(path.read_text())
    rows[2]['sampleOriginType'] = {'id':'OTHER:skin', 'label':'skin'}
    path.write_text(json.dumps(rows))
    result = query.answer_query(str(package), 'Which patients have skin samples?', query_mode='deterministic_only')
    assert result['intent'] == 'sample_origin_clarification'
    assert 'more than one' in result['reply']
    path.write_text('[]')
    result = query.answer_query(str(package), 'Which patients have skin samples?', query_mode='deterministic_only')
    assert 'does not mean' in result['reply']


def test_summary_does_not_disclose_patient_ids(package):
    result = query.answer_query(str(package), 'Which patients have skin samples?', query_mode='deterministic_only', granularity_ceiling='summary')
    assert 'patients' not in result['data']
    assert 'P1' not in json.dumps(result)
    assert result['data']['patient_count'] == 1


def test_dataset_qualified_origins_do_not_merge_same_source_ids(package, monkeypatch):
    monkeypatch.setattr(origins, '_workspace_dataset_ids', lambda _: ['a','b'])
    monkeypatch.setattr(origins, '_dataset_root_path', lambda _: package)
    keys = [identity_key(d, 'patient', 'P1') for d in ['a', 'b']]
    result = origins.origin_catalog('scope', keys)
    assert result[0]['patients'] == set(keys)
    assert origins.origin_catalog('scope', keys[:1])[0]['patients'] == {keys[0]}


def test_planner_origin_filter_uses_same_matches(package):
    plan = {'intent':'cohort_query', 'output':'patient_list', 'logic':'and', 'filters':[
        {'domain':'sample_origin', 'operator':'eq', 'value':'UBERON:1'},
        {'domain':'disease', 'operator':'eq', 'value':'Example disease'}]}
    valid = query._validate_semantic_query_plan(plan)
    result = query._execute_semantic_query_plan(str(package), 'Find matching patients', valid, 'test-model')
    assert result['data']['patient_ids'] == ['P1']
    assert '_sample_origins' not in json.dumps(result)
    plan['filters'][0]['negate'] = True
    assert query._validate_semantic_query_plan(plan) is None
    plan['filters'][0]['negate'] = False
    plan['filters'][0]['operator'] = 'contains'
    assert query._validate_semantic_query_plan(plan) is None


def test_safe_summary_catalog_does_not_include_origin_values(package):
    catalog = query._semantic_query_catalog(str(package), ai_provider_access='safe_summary')
    assert 'known_sample_origins' not in catalog
    assert 'skin' not in json.dumps(catalog)


def test_planner_mode_receives_origin_catalog_and_executes_validated_filter(package, monkeypatch):
    monkeypatch.setattr(query, '_lm_studio_enabled', lambda: True)
    monkeypatch.setattr(query, '_resolve_lm_studio_model', lambda: 'test-model')
    calls = []
    def planner(url, payload, **kwargs):
        calls.append(payload)
        return {'choices':[{'message':{'content':json.dumps({
            'intent':'cohort_query', 'output':'patient_list', 'logic':'and',
            'filters':[{'domain':'sample_origin','operator':'eq','value':'UBERON:1'}]})}}]}
    monkeypatch.setattr(query, '_http_json', planner)
    result = query.answer_query(str(package), 'Find people with skin specimens', query_mode='planner_only')
    assert len(calls) == 1
    assert 'known_sample_origins' in calls[0]['messages'][1]['content']
    assert result['data']['patient_ids'] == ['P1']
    assert result['action_context']['id_type'] == 'patient'


def test_deterministic_mode_never_calls_model(package, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Deterministic sample-origin query must not call a model')
    monkeypatch.setattr(query, '_http_json', unexpected)
    assert query.answer_query(str(package), 'Which patients have liver samples?', query_mode='deterministic_only')['intent'] == 'sample_origin_cohort'
