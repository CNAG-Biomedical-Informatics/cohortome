"""MCP proposals are not execution authority; approval and disclosure are separate."""
import copy
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from app import local_agents as agents, local_agent_runs as runs, local_agent_tools as tools


@pytest.fixture
def context(tmp_path, monkeypatch):
    agents.configure_desktop('http://127.0.0.1:45678')
    runs._plans.clear()
    grant = agents.Grant('test-hash', 'default',
        [dict(dataset_id='default', patient_id=p) for p in ['P1','P2','P3','P4','P5','P6']],
        [('default', str(tmp_path), 'Demo')], 'fingerprint', 'local', time.time(), time.time()+3600,
        time.monotonic()+3600)
    agents._grant = grant
    request = Request({'type':'http', 'headers':[], 'session':{'username':'local', 'role':'admin'},
                       'state':{'desktop_ui':True}})
    monkeypatch.setattr(agents, 'require_admin', lambda _: {'username':'local'})
    monkeypatch.setattr(agents, '_approved_sources', lambda *_: grant.sources)
    monkeypatch.setattr(runs.cohort_filters, '_fingerprint', lambda *_: 'fingerprint')
    monkeypatch.setattr(runs.analysis_sessions, 'USER_STATE_ROOT', tmp_path / 'sessions')
    monkeypatch.setattr(runs.datasets, 'workspace_fingerprint_for_data_dir', lambda *_a, **_k: {'test':'fingerprint'})
    item = runs._item('flow-cytometry-wilcoxon-cohort-comparison')
    args = tools.PrepareRunArguments(analysis_id=item['id'], dataset_id='default', assay_id='cells',
                                   cohort_a=['P1','P2','P3'], cohort_b=['P4','P5','P6'])
    counts = dict(cohort_a_sample_count=3, cohort_b_sample_count=3, feature_count=10)
    monkeypatch.setattr(runs, '_validate_inputs', lambda *_: (item, args.cohort_a, args.cohort_b, counts))
    submitted = []
    def submit(**kwargs):
        submitted.append(kwargs)
        return {'job_id':'job1', 'status':'queued'}
    monkeypatch.setattr(runs.jobs, 'submit_analysis_job', submit)
    yield SimpleNamespace(grant=grant, request=request, args=args, submitted=submitted, item=item)
    agents.configure_desktop('')
    runs._plans.clear()


def proposal(c):
    return runs.prepare(c.args, c.grant, c.request)['plan_id']


def approve(c, plan, results=False):
    response = agents.decide_plan(plan, agents.RunDecision(approve=True, allow_results=results), c.request)
    return json.loads(response.body)


def test_prepare_never_runs_and_approval_is_one_shot(context):
    c = context
    plan = proposal(c)
    assert not c.submitted
    assert runs.pending(c.grant, owner=True)[0]['cohort_a'] == c.args.cohort_a
    result = approve(c, plan)
    assert result['status'] == 'submitted' and not result['results_shared']
    assert len(c.submitted) == 1
    assert c.submitted[0]['prompt'] == c.item['default_prompt']
    assert c.submitted[0]['selected_patient_ids'] == 'P1,P2,P3'
    session = runs.analysis_sessions.get_analysis_session(result['analysis_session_id'], 'local')
    assert session['title'].startswith('MCP · ')
    assert session['scope_metadata']['patient_count'] == 3
    assert session['compare_scope_metadata']['patient_count'] == 3
    assert session['turns'][1]['payload']['data']['job_id'] == 'job1'
    assert approve(c, plan)['job_id'] == 'job1' and len(c.submitted) == 1


@pytest.mark.parametrize('change', ['scope', 'revoke', 'expiry', 'reject', 'source'])
def test_changed_or_rejected_plan_cannot_run(context, change, monkeypatch):
    c = context
    plan = proposal(c)
    if change == 'scope':
        agents._grant = replace(c.grant, members=[])
    elif change == 'revoke':
        agents._revoke()
    elif change == 'expiry':
        runs._plans[plan]['deadline'] = 0
    elif change == 'reject':
        agents.decide_plan(plan, agents.RunDecision(approve=False), c.request)
    else:
        monkeypatch.setattr(runs.cohort_filters, '_fingerprint', lambda *_: 'changed')
    if change == 'reject':
        assert approve(c, plan)['status'] == 'rejected'
    else:
        with pytest.raises(HTTPException):
            approve(c, plan)
    assert not c.submitted


def test_connector_cannot_approve(context):
    c = context
    plan = proposal(c)
    connector_request = Request({'type':'http', 'headers':[], 'session':{'username':'local', 'role':'admin'}})
    with pytest.raises(HTTPException) as error:
        agents.decide_plan(plan, agents.RunDecision(approve=True), connector_request)
    assert error.value.status_code == 404 and not c.submitted
    with pytest.raises(HTTPException):
        tools.execute_tool('approve_analysis_run', {'plan_id':plan}, c.grant, connector_request)


def test_disclosure_requires_separate_consent_and_current_scope(context, monkeypatch, tmp_path):
    c = context
    plan = proposal(c)
    approve(c, plan)
    monkeypatch.setattr(runs.jobs, 'load_job_record', lambda *_: {'status':'completed'})
    monkeypatch.setattr(runs, 'validate_job', lambda *_: None)
    table = tmp_path / 'result.tsv'
    table.write_text('feature_id\tp_value\tprivate_path\nF1\t0.1\tNEVER\nF2\t0.2\tNEVER\n')
    monkeypatch.setattr(runs.jobs, 'resolve_job_artifact_path', lambda *_: table)
    args = tools.InspectRunArguments(plan_id=plan, include_results=True, limit=1)
    with pytest.raises(HTTPException):
        runs.inspect(args, c.grant)
    runs._plans[plan]['allow_results'] = True
    result = runs.inspect(args, c.grant)
    assert result['results'] == [{'feature_id':'F1','p_value':'0.1'}]
    assert result['next_offset'] == 1 and 'NEVER' not in json.dumps(result)
    for changed in (replace(c.grant, token_hash='other'), replace(c.grant, members=[])):
        with pytest.raises(HTTPException):
            runs.inspect(args, changed)


def test_submission_failure_leaves_a_visible_chat_not_a_retry_loop(context, monkeypatch):
    c = context
    plan = proposal(c)
    def fail(**_):
        raise RuntimeError('Secret path must not escape')
    monkeypatch.setattr(runs.jobs, 'submit_analysis_job', fail)
    result = approve(c, plan)
    assert result['status'] == 'failed'
    session = runs.analysis_sessions.get_analysis_session(result['analysis_session_id'], 'local')
    assert session['turns'][-1]['payload']['intent'] == 'analysis_error'
    assert 'Secret' not in json.dumps(session)


def test_worker_rechecks_approved_inputs(context, monkeypatch):
    c = context
    plan = proposal(c)
    approve(c, plan)
    submitted = c.submitted[0]
    record = dict(submitted, submitted_by='local')
    monkeypatch.setattr(runs.datasets, 'get_dataset', lambda _: {'root_path':c.grant.sources[0][1]})
    monkeypatch.setattr(agents, '_verify_fixture', lambda *_: None)
    runs.validate_job(record, c.item)
    for key in ['assay_id', 'selected_patient_ids', 'compare_selected_patient_ids', 'dataset_id']:
        with pytest.raises(RuntimeError):
            runs.validate_job({**record, key:'changed'}, c.item)
    monkeypatch.setattr(runs.cohort_filters, '_fingerprint', lambda *_: 'changed')
    with pytest.raises(RuntimeError):
        runs.validate_job(record, c.item)


@pytest.mark.parametrize('a,b', [([], ['P2']), (['P1'],['P1']), (['OUTSIDE'],['P2'])])
def test_input_membership_is_checked_before_any_reader(a, b):
    args = SimpleNamespace(dataset_id='default', cohort_a=a, cohort_b=b)
    grant = SimpleNamespace(sources=[('default','/must-not-read','Demo')],
                            members=[dict(patient_id='P1'),dict(patient_id='P2')])
    with pytest.raises(HTTPException):
        runs._validate_inputs(args, grant)


@pytest.mark.parametrize('execute', [False, True])
def test_actual_synthetic_wilcoxon_validation(tmp_path, monkeypatch, execute):
    from pathlib import Path
    from app import query_store
    root = Path(__file__).resolve().parents[1] / 'datasets/synthetic-cross-sectional-demo'
    if execute and runs.analysis_catalog.rscript_unavailable_reason('quantitative_assay_wilcoxon_comparison'):
        pytest.skip('R runtime for quantitative comparison not installed')
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'stores')
    monkeypatch.setattr(query_store, 'list_registered_datasets', lambda: [])
    monkeypatch.setattr(runs.analysis_catalog, 'rscript_unavailable_reason', lambda _: '')
    monkeypatch.setattr(runs.jobs, 'analysis_worker_available', lambda: True)
    item = next(i for i in query_store._assay_manifest_items_for_root(root) if i['modality'] == 'flow_cytometry')
    _, _, _, links = query_store._external_assay_header(str(root), item)
    patients = sorted(set(links.values()))[:6]
    args = tools.PrepareRunArguments(dataset_id='synthetic-cross-sectional-demo',
        analysis_id='flow-cytometry-wilcoxon-cohort-comparison', assay_id=item['assay_id'],
        cohort_a=patients[:3], cohort_b=patients[3:])
    grant = SimpleNamespace(sources=[(args.dataset_id,str(root),'Demo')],
                            members=[dict(patient_id=p) for p in patients])
    _, a, b, counts = runs._validate_inputs(args, grant)
    assert len(a) == len(b) == 3
    assert counts['cohort_a_sample_count'] == counts['cohort_b_sample_count'] == 3
    assert counts['feature_count'] > 0
    if execute:
        result = runs.analysis_external.run_rscript_analysis(
            'quantitative_assay_wilcoxon_comparison', prompt='Compare groups', data_dir=str(root),
            assay_id=args.assay_id, selected_patient_ids=','.join(a),
            compare_selected_patient_ids=','.join(b), job_dir=tmp_path / 'run', timeout_seconds=60)
        assert result['data']['execution'] == 'external_runner'
        assert (tmp_path / 'run' / 'compact_assay_results.tsv').is_file()
