"""The agent tool surface cannot widen its owner's frozen selection."""
import copy
import json
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from app import local_agent_tools as tools, query_store


@pytest.fixture
def grant():
    return SimpleNamespace(workspace='scope--a--b', fingerprint='f' * 64,
        sources=[('a', '/not-exposed/a', 'A'), ('b', '/not-exposed/b', 'B')],
        members=[dict(dataset_id='a', patient_id='P1'), dict(dataset_id='b', patient_id='P1')])


@pytest.fixture
def evaluated(monkeypatch):
    calls = []
    def apply(body, request):
        calls.append(body)
        members = [m.model_dump() for m in body.base_members]
        return dict(selection=dict(members=members),
            summary=dict(totals=dict(patients=len(members), clinical_records=3),
                         sex_counts={'female':len(members)}, visit_distribution={'1':1},
                         workspace_patient_count=999,
                         patients=[{'source_files':['/private/path']}], timelines=[{'patient_id':'UNSHARED'}],
                         top_diseases=[dict(disease='Example', patient_count=len(members), patients=['UNSHARED'])],
                         top_medications=[dict(medication='Example treatment', patient_count=1, patients=['UNSHARED'])]),
            assays=[dict(assay_id='a::rna', modality='transcriptomics', patient_count=1,
                         sample_count=2, patient_ids=['UNSHARED'], sample_ids=['NOT-RETURNED'],
                         source_file='/private/path')])
    monkeypatch.setattr(tools.cohort_scope, 'apply_draft', apply)
    return calls


def test_describe_scope_has_explicit_membership_and_no_paths(grant):
    result = tools.execute_tool('describe_scope', {}, grant, None)
    assert result['patient_count'] == 2
    assert result['datasets'] == [dict(dataset_id='a', name='A', patient_count=1),
                                   dict(dataset_id='b', name='B', patient_count=1)]
    assert result['frozen'] and result['synthetic']
    assert '/not-exposed' not in json.dumps(result)


@pytest.mark.parametrize('name,args', [
    ('delete_dataset', {}),
    ('describe_scope', {'workspace':'another'}),
    ('find_patients', {'base_members':[]}),
    ('find_patients', {'cohort_id':'someone-elses-cohort'}),
    ('find_patients', {'limit':101}),
    ('find_patients', {'offset':-1}),
    ('find_patients', {'exact':'false'}),
    ('find_patients', {'diseases':['x' * 257]}),
    ('find_patients', {'clinical_filters':[dict(field_id='field', operator='eq', values=[1], sql='SELECT 1')]}),
    ('list_filter_fields', {'limit':51}),
    ('summarize_selection', {'sql':'SELECT * FROM patients'}),
    ('get_clinical_records', {'dataset_id':'a', 'patient_id':'P1', 'limit':21}),
    ('list_biosamples', {'dataset_id':'a', 'patient_id':'P1', 'path':'/secret'}),
    ('get_assay_measurements', {'dataset_id':'a', 'assay_id':'rna', 'feature_id':'x', 'limit':101}),
    ('list_analyses', {'run':True}),
])
def test_tool_schema_rejects_widening_and_unbounded_requests(name, args, grant):
    with pytest.raises(HTTPException) as error:
        tools.execute_tool(name, args, grant, None)
    assert error.value.status_code == 422
    assert 'SELECT' not in error.value.detail


def test_find_forces_grant_and_pages_dataset_qualified_patients(grant, evaluated):
    original = copy.deepcopy(grant.members)
    result = tools.execute_tool('find_patients', dict(limit=1, modalities=['proteomics']), grant, None)
    body = evaluated[0]
    assert body.workspace == grant.workspace and body.fingerprint == grant.fingerprint
    assert [m.model_dump() for m in body.base_members] == original
    assert body.modalities == ['proteomics']
    assert result['patients'] == [dict(dataset_id='a', patient_id='P1')]
    assert result['patient_count'] == 2 and result['next_offset'] == 1
    second = tools.execute_tool('find_patients', dict(offset=1, limit=1), grant, None)
    assert second['patients'] == [dict(dataset_id='b', patient_id='P1')]
    assert second['next_offset'] is None and grant.members == original


def test_empty_grant_never_becomes_full_workspace(grant, evaluated):
    grant.members = []
    result = tools.execute_tool('find_patients', {}, grant, None)
    assert evaluated[0].base_members == []
    assert result['patient_count'] == 0 and result['patients'] == []
    summary = tools.execute_tool('summarize_selection', {}, grant, None)
    assert summary['patient_count'] == summary['clinical_patient_count'] == 0


@pytest.mark.parametrize('selection', [None, {'members':[dict(dataset_id='a', patient_id='UNSHARED')]}])
def test_defensive_check_rejects_full_or_widened_backend_result(monkeypatch, grant, selection):
    monkeypatch.setattr(tools.cohort_scope, 'apply_draft', lambda *_: {'selection':selection})
    with pytest.raises(HTTPException) as error:
        tools.execute_tool('find_patients', {}, grant, None)
    assert error.value.status_code == 409


def test_summary_omits_unshared_denominators_ids_paths_and_timeline(grant, evaluated):
    result = tools.execute_tool('summarize_selection', {}, grant, None)
    assert result['patient_count'] == 2 and result['clinical_record_count'] == 3
    assert result['top_diseases'] == [dict(disease='Example', patient_count=2)]
    assert result['top_medications'] == [dict(medication='Example treatment', patient_count=1)]
    assert result['assays'] == [dict(assay_id='a::rna', modality='transcriptomics', patient_count=1, sample_count=2)]
    rendered = json.dumps(result)
    assert not any(text in rendered for text in ('UNSHARED', 'NOT-RETURNED', '/private', '999', 'source_file', 'timelines'))


def test_field_options_and_ranges_are_limited_to_shared_patients(tmp_path, monkeypatch):
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(query_store, 'list_registered_datasets', lambda: [])
    sources = []
    for dataset in ['a', 'b']:
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical/data.json').write_text(json.dumps([
            {'id':'P1:V1', 'info':{'age':20}, 'ethnicity':{'label':f'{dataset}-selected'}},
            {'id':'P1:V2', 'info':{'age':30}, 'ethnicity':{'label':f'{dataset}-selected'}},
            {'id':'P2:V1', 'info':{'age':99}, 'ethnicity':{'label':f'{dataset}-unshared'}},
        ]))
        query_store.ensure_query_store(str(root))
        sources.append((dataset, str(root), dataset))
    grant = SimpleNamespace(sources=sources, members=[dict(dataset_id='a', patient_id='P1')])
    result = tools.execute_tool('list_filter_fields', {}, grant, None)
    age = next(field for field in result['fields'] if field['kind'] == 'number' and field['dataset_ids'] == ['a'])
    assert age['observed_range'] == [20, 30]
    other_age = next(field for field in result['fields'] if field['kind'] == 'number' and field['dataset_ids'] == ['b'])
    assert 'observed_range' not in other_age
    ethnicity = next(field for field in result['fields'] if field['label'] == 'Ethnicity')
    assert ethnicity['options'] == ['a-selected']
    rendered = json.dumps(result)
    assert not any(text in rendered for text in ('unshared', 'b-selected', '_bindings', str(tmp_path)))
    page = tools.execute_tool('list_filter_fields', {'limit':1, 'search':'age'}, grant, None)
    assert page['total_fields'] == 2 and len(page['fields']) == 1 and page['next_offset'] == 1
    grant.members = []
    empty = tools.execute_tool('list_filter_fields', {}, grant, None)
    assert all(not field.get('options') and 'observed_range' not in field for field in empty['fields'])


def test_catalogue_marks_proposals_as_state_changing_not_run_authority():
    assert {tool['name'] for tool in tools.TOOL_DEFINITIONS} == {
        'describe_scope', 'list_filter_fields', 'find_patients', 'summarize_selection',
        'describe_dataset', 'get_clinical_records', 'list_biosamples', 'list_assay_features',
        'get_assay_measurements', 'list_analyses', 'check_analysis_requirements',
        'prepare_analysis_run', 'inspect_analysis_run'}
    assert all(tool['annotations']['readOnlyHint'] == (tool['name'] != 'prepare_analysis_run')
               and not tool['annotations']['destructiveHint']
               and tool['inputSchema']['additionalProperties'] is False for tool in tools.TOOL_DEFINITIONS)


@pytest.mark.parametrize('dataset_ids', [['default'], ['default', 'synthetic-cross-sectional-demo']])
def test_bundled_prepared_stores_find_and_summarize_are_scoped(tmp_path, monkeypatch, dataset_ids):
    """Read shipped fictional inputs; every store and mutable index stays in tmp."""
    from app import cohort_filters, datasets, dicom_files, patient_overview
    from app.cohort_members import source_inventory
    from app.user_state import request_user_id

    monkeypatch.setenv('COHORTOME_AUTH_MODE', 'none')
    monkeypatch.setenv('COHORTOME_DESKTOP_MODE', 'true')
    monkeypatch.setattr(datasets, 'DATASET_REGISTRY_PATH', tmp_path / 'registry.json')
    monkeypatch.setattr(datasets, 'STATE_ROOT_DIR', tmp_path / 'state')
    monkeypatch.setattr(dicom_files, 'STATE_ROOT_DIR', tmp_path / 'state')
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    root = Path(__file__).resolve().parents[1]
    registry = [item for item in json.loads((root / 'config/datasets/registry.json').read_text())
                if item['dataset_id'] in dataset_ids]
    for item in registry:
        item['root_path'] = str(root / item['root_path'])
    datasets.DATASET_REGISTRY_PATH.write_text(json.dumps(registry))
    for identifier in dataset_ids:
        assert query_store.prepare_dataset_query_store(identifier)['status'] == 'ready'

    workspace = datasets.dataset_scope_id(dataset_ids)
    request = Request({'type':'http', 'method':'POST', 'path':'/local-agent/call',
                       'headers':[], 'query_string':b'', 'session':{'username':'local', 'role':'admin'}})
    sources = patient_overview.sources(request, workspace)
    members = [dict(dataset_id=identifier, patient_id=patient)
               for identifier, source, _ in sources for patient in sorted(source_inventory(source)[0])[:2]]
    grant = SimpleNamespace(workspace=workspace, sources=sources, members=members,
        fingerprint=cohort_filters._fingerprint(sources, request_user_id(request)))
    expected = sorted(members, key=lambda m: (m['dataset_id'], m['patient_id']))
    result = tools.execute_tool('find_patients', {}, grant, request)
    assert result['patient_count'] == len(expected)
    assert result['patients'] == expected
    result = tools.execute_tool('find_patients', {'q':expected[0]['patient_id']}, grant, request)
    assert result['patients'] == [member for member in expected
                                  if expected[0]['patient_id'].casefold() in member['patient_id'].casefold()]

    summary = tools.execute_tool('summarize_selection', {}, grant, request)
    assert summary['patient_count'] == summary['clinical_patient_count'] == len(expected)
    assert summary['clinical_record_count'] >= len(expected)
    assert sum(summary['sex_counts'].values()) == len(expected)
    assert all(set(item) == {'disease', 'patient_count'} for item in summary['top_diseases'])
    assert all(set(item) == {'medication', 'patient_count'} for item in summary['top_medications'])
    assert summary['assays']
    assert all(item['patient_count'] <= len(expected) for item in summary['assays'])
    assert str(root) not in json.dumps(summary)

    coverage = patient_overview.coverage(request, workspace)['patients']
    allowed = {(m['dataset_id'], m['patient_id']) for m in expected}
    with_rna = [dict(dataset_id=p['dataset_id'], patient_id=p['patient_id']) for p in coverage
                if (p['dataset_id'], p['patient_id']) in allowed
                and 'transcriptomics' in {tools.cohort_scope._modality(m) for m in p['modalities']}]
    found = tools.execute_tool('find_patients', {'modalities':['transcriptomics']}, grant, request)
    assert found['patients'] == sorted(with_rna, key=lambda m: (m['dataset_id'], m['patient_id']))

    for dataset_id, source, _ in sources:
        description = tools.execute_tool('describe_dataset', {'dataset_id':dataset_id}, grant, request)
        assert description['patient_count'] == 2 and description['assays']
        assert all(a['patient_count'] <= 2 for a in description['assays'])
        first = next(m for m in members if m['dataset_id'] == dataset_id)
        clinical = tools.execute_tool('get_clinical_records', {**first, 'limit':1}, grant, request)
        assert len(clinical['records']) == 1
        assert 'info' not in clinical['records'][0]['record']
        specimens = tools.execute_tool('list_biosamples', first, grant, request)
        assert all(r['individualId'] == first['patient_id'] for r in specimens['items'])
        for assay in description['assays']:
            parameters = dict(dataset_id=dataset_id, assay_id=assay['assay_id'])
            features = tools.execute_tool('list_assay_features', {**parameters, 'limit':1}, grant, request)
            assert len(features['features']) == 1
            measurements = tools.execute_tool('get_assay_measurements',
                {**parameters, 'feature_id':features['features'][0], 'limit':1}, grant, request)
            assert len(measurements['items']) <= 1
            assert all((dataset_id, r['patient_id']) in allowed for r in measurements['items'])
            assert str(root) not in json.dumps(measurements)
        assert str(root) not in json.dumps(description)
    analyses = tools.execute_tool('list_analyses', {'limit':1}, grant, request)
    assert len(analyses['items']) == 1 and analyses['next_offset'] == 1
    check = tools.execute_tool('check_analysis_requirements',
        {'analysis_id':analyses['items'][0]['id']}, grant, request)
    assert check['validation'] == 'partial' and check['execution_via_mcp'] is False
    assert check['checks_remaining']

    grant.members = []
    empty = tools.execute_tool('find_patients', {}, grant, request)
    assert empty['patient_count'] == 0 and empty['patients'] == []
    summary = tools.execute_tool('summarize_selection', {}, grant, request)
    assert summary['patient_count'] == summary['clinical_patient_count'] == summary['clinical_record_count'] == 0
    assert summary['sex_counts'] == {} and summary['assays'] == []
    empty = tools.execute_tool('get_assay_measurements',
        {**parameters, 'feature_id':features['features'][0]}, grant, request)
    assert empty['items'] == [] and empty['total'] == 0


@pytest.mark.parametrize('name', ['get_clinical_records', 'list_biosamples'])
@pytest.mark.parametrize('dataset,patient', [('a','UNSHARED'), ('unknown','P1')])
def test_record_tools_reject_unshared_before_reading(grant, monkeypatch, name, dataset, patient):
    from app import local_agent_exploration as exploration
    monkeypatch.setattr(exploration.clinical_store, 'patient_records_page',
                        lambda *_a, **_k: pytest.fail('Must not read unshared patient'))
    monkeypatch.setattr(exploration.biosamples, 'read_biosamples',
                        lambda *_a, **_k: pytest.fail('Must not read unshared patient'))
    with pytest.raises(HTTPException) as error:
        tools.execute_tool(name, dict(dataset_id=dataset, patient_id=patient), grant, None)
    assert error.value.status_code == 403


def test_biosamples_paged_and_sanitized(grant, monkeypatch):
    from app import local_agent_exploration as exploration
    monkeypatch.setattr(exploration.biosamples, 'read_biosamples', lambda *_: [
        dict(id='B2', individualId='P1', sampleOriginType={'id':'TEST:1', 'label':'Blood'}, info={'path':'SECRET'}),
        dict(id='B1', individualId='P1'), dict(id='SECRET', individualId='UNSHARED')])
    result = tools.execute_tool('list_biosamples', dict(dataset_id='a', patient_id='P1', limit=1), grant, None)
    assert result['total'] == 2 and result['next_offset'] == 1
    assert result['items'] == [dict(id='B1', individualId='P1')]
    second = tools.execute_tool('list_biosamples', dict(dataset_id='a', patient_id='P1', offset=1), grant, None)
    assert 'SECRET' not in json.dumps(second) and second['next_offset'] is None


def test_measurements_keep_only_shared_samples_and_missing_values(grant, tmp_path, monkeypatch):
    from app import local_agent_exploration as exploration
    path = tmp_path / 'matrix.csv'
    path.write_text('feature,S1,S2,S3\nF1,2,NA,999\nF2,3,4,888\n')
    item = dict(assay_id='rna', modality='transcriptomics', data_type='counts')
    monkeypatch.setattr(exploration, '_assay', lambda *_: ('/fixture', {'P1'}, item))
    monkeypatch.setattr(exploration.query_store, '_external_assay_header', lambda *_:
                        (path, ',', ['S1','S2','S3'], {'S1':'P1','S2':'P1','S3':'UNSHARED'}))
    args = dict(dataset_id='a', assay_id='rna', feature_id='F1', limit=1)
    result = tools.execute_tool('get_assay_measurements', args, grant, None)
    assert result['total'] == 2 and result['next_offset'] == 1
    assert result['items'] == [dict(patient_id='P1', sample_id='S1', value=2)]
    result = tools.execute_tool('get_assay_measurements', {**args, 'offset':1}, grant, None)
    assert result['items'] == [dict(patient_id='P1', sample_id='S2', value=None)]
    assert not any(s in json.dumps(result) for s in ('UNSHARED','999','888',str(tmp_path)))
    path.write_text('feature,S1,S2,S3\nF1,2,NA,999\nF1,3,4,888\n')
    with pytest.raises(HTTPException) as error:
        tools.execute_tool('get_assay_measurements', args, grant, None)
    assert error.value.status_code == 409


def test_analysis_check_does_not_claim_readiness_or_inspect_other_cohorts(grant, monkeypatch):
    from app import local_agent_exploration as exploration
    monkeypatch.setattr(exploration, '_inventory', lambda *_: ([], []))
    monkeypatch.setattr(exploration.datasets, 'clinical_representation', lambda *_: 'person')
    monkeypatch.setattr(exploration, '_analysis_items', lambda: [dict(
        id='test', name='Test', requires_assays=True, required_modalities=['transcriptomics'],
        requires_single_dataset_workspace=True, required_clinical_representation='snapshot',
        requires_measurement=True, default_compare_mode=True, minimum_samples_per_cohort=3)])
    result = tools.execute_tool('check_analysis_requirements', {'analysis_id':'test'}, grant, None)
    assert len(result['blockers']) == 3
    assert len(result['checks_remaining']) == 4
    assert result['validation'] == 'partial' and result['execution_via_mcp'] is False
    assert 'ready' not in result
    grant.members = []
    result = tools.execute_tool('check_analysis_requirements', {'analysis_id':'test'}, grant, None)
    assert 'The shared selection is empty.' in result['blockers']
