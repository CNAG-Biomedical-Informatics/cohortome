import json

import pytest

from app import query
from bff_test_helpers import isolate_query_store, write_json


DRUGS = ['Vedolizumab', 'Adalimumab', 'Belimumab', 'Dupilumab',
         'Mepolizumab', 'Ocrelizumab', 'Infliximab', 'Ustekinumab']


def plan():
    return {'intent': 'cohort_query', 'output': 'count', 'logic': 'or',
            'filters': [{'domain': 'treatment', 'operator': 'eq', 'value': drug} for drug in DRUGS]}


def test_all_eight_biologics_count_unique_patients(tmp_path, monkeypatch):
    isolate_query_store(monkeypatch, tmp_path)
    root = tmp_path / 'data'
    root.mkdir()
    write_json(root, 'records.json', [
        {'id': f'P{i}:v{visit}', 'patient_id': f'P{i}',
         'treatments': [{'treatmentCode': {'label': drug}}]}
        for i, drug in enumerate(DRUGS) for visit in [1, 2]
    ])
    monkeypatch.setattr(query, '_lm_studio_enabled', lambda: True)
    monkeypatch.setattr(query, '_resolve_lm_studio_model', lambda: 'test')
    monkeypatch.setattr(query, '_http_json', lambda *a, **kw:
        {'choices': [{'message': {'content': json.dumps(plan())}}]})
    result = query.answer_query(str(root), 'How many patients take biologics?')
    assert result['data']['patient_count'] == 8
    assert len(result['data']['semantic_plan']['filters']) == 8
    assert result['reply'] == '8 patients match this query.'


@pytest.mark.parametrize('mode', ['auto', 'planner_only', 'deterministic_only'])
@pytest.mark.parametrize('granularity', ['detailed', 'summary'])
def test_missing_treatments_are_explained_without_model_or_zero_count(tmp_path, monkeypatch, mode, granularity):
    isolate_query_store(monkeypatch, tmp_path)
    root = tmp_path / 'data'
    root.mkdir()
    write_json(root, 'records.json', [{'id': 'P1:v1', 'patient_id': 'P1', 'treatments': []}])
    def forbidden(*args, **kwargs):
        pytest.fail('Missing treatment data should not need an LLM request')
    monkeypatch.setattr(query, '_http_json', forbidden)
    result = query.answer_query(str(root), 'How many patients take biologics?',
                                query_mode=mode, granularity_mode=granularity)
    assert result['intent'] == 'treatment_data_unavailable'
    assert 'No treatment records' in result['reply']
    assert 'does not establish' in result['reply']
    assert 'patient_count' not in result['data']
    assert not any(result['data']['available_actions'].values())


def test_oversized_and_invalid_tail_plans_are_rejected_whole():
    value = plan()
    value['filters'] *= 7
    assert query._validate_semantic_query_plan(value) is None
    value = plan()
    value['filters'][-1] = {'domain': 'invalid'}
    assert query._validate_semantic_query_plan(value) is None
