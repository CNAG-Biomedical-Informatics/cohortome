import csv
import io
import json
import os
from pathlib import Path

import pytest

from app.script_inputs import DEMO_ROOT, prepare_inputs, approved_inputs
from app.script_analysis import run_script_analysis
from app import script_sandbox


def test_prepared_objects_scope_and_template_contains_no_records():
    prepared = prepare_inputs(str(DEMO_ROOT), 'DEMOAI031', 'DEMOAI061', True)
    patients = list(csv.DictReader(io.StringIO(prepared['files']['patients.csv'])))
    assert [(r['patient_id'], r['cohort']) for r in patients] == [('DEMOAI031', 'A'), ('DEMOAI061', 'B')]
    assert 'DEMOAI031' not in prepared['template']
    assert 'DEMOAI061' not in prepared['template']
    assert 'patients = pd.read_csv' in prepared['template']
    assert 'assays[' in prepared['template']
    assert prepared['contract_id'] != prepare_inputs(str(DEMO_ROOT))['contract_id']
    assert prepared['contract']['assays']['transcriptomics']['samples'] == 2
    assert prepared['contract']['assays']['transcriptomics']['cohort_a_samples'] == 1
    assert prepared['contract']['assays']['transcriptomics']['cohort_b_samples'] == 1
    assert 'Do not substitute a different statistical method' in prepared['template']
    assert 'not stale metadata' in prepared['template']
    assert 'stop() (R)' in prepared['template']
    # Neither selected patient has methylation; it is omitted explicitly from the contract.
    assert 'methylation' not in prepared['contract']['assays']
    assert any(assay['modality'] == 'methylation' for assay in prepared['contract']['omitted_assays'])


def test_missing_comparison_group_has_actionable_message():
    with pytest.raises(RuntimeError, match='Choose Cohort A in Patients'):
        prepare_inputs(DEMO_ROOT, compare_mode=True)
    with pytest.raises(RuntimeError, match='Choose Cohort B in Patients'):
        prepare_inputs(DEMO_ROOT, 'DEMOAI031', compare_mode=True)
    prepared = prepare_inputs(DEMO_ROOT)
    assert prepared['contract']['compare_mode'] is False
    assert prepared['contract']['cohort_b'] == 0


def test_r_template_uses_same_data_and_different_contract():
    python = prepare_inputs(DEMO_ROOT)
    r = prepare_inputs(DEMO_ROOT, language='r')
    assert r['files'] == python['files']
    assert r['contract_id'] != python['contract_id']
    assert "patients <- read.csv" in r['template']
    assert 'check.names=FALSE' in r['template']
    assert 'DEMOAI001' not in r['template']
    assert r['contract']['packages']['limma'] == '3.54.1'


def test_only_exact_approved_demo_and_valid_scopes(tmp_path):
    with pytest.raises(RuntimeError, match='only the bundled'):
        approved_inputs(tmp_path)
    with pytest.raises(RuntimeError, match='do not belong'):
        prepare_inputs(DEMO_ROOT, 'unknown')
    with pytest.raises(RuntimeError, match='disjoint'):
        prepare_inputs(DEMO_ROOT, 'DEMOAI031', 'DEMOAI031:baseline', True)
    with pytest.raises(RuntimeError, match='selected assays'):
        prepare_inputs(DEMO_ROOT, assay_ids=['unknown'])


def test_worker_rejects_stale_contract_before_execution(tmp_path):
    with pytest.raises(RuntimeError, match='inputs changed'):
        run_script_analysis('synthetic_custom_script', prompt=json.dumps({
            'script': 'print(1)', 'contract_id': 'old', 'compare_mode': False,
            'assay_ids': []}), data_dir=DEMO_ROOT, job_dir=tmp_path)


def test_untrusted_artifact_cannot_escape_output_directory(tmp_path, monkeypatch):
    image = 'sha256:' + 'a' * 64
    monkeypatch.setattr(script_sandbox, 'sandbox_image', lambda: image)
    commands = []
    monkeypatch.setattr(script_sandbox, '_control', lambda args: commands.append(args) or '')
    monkeypatch.setattr(script_sandbox, '_docker', lambda: ['docker'])
    monkeypatch.setattr(script_sandbox, '_read_bounded', lambda _: {'exit_code': 0, 'stdout': '', 'stderr': '',
                                                                 'artifacts': [{'name': '../escape.txt', 'data': 'YQ=='}]})
    with pytest.raises(RuntimeError, match='simple, unique'):
        script_sandbox.execute_script({}, 'print(1)', tmp_path, image)
    command = commands[0]
    for flag in ['--read-only', '--cap-drop', '--network', '--memory', '--pids-limit', '--security-opt']:
        assert flag in command
    assert command[command.index('--network') + 1] == 'none'
    assert commands[-1][0:2] == ['rm', '--force']


@pytest.mark.skipif(os.environ.get('COHORTOME_TEST_SCRIPT_SANDBOX') != '1', reason='Explicit local sandbox integration test')
def test_real_synthetic_container_and_isolation(tmp_path):
    prepared = prepare_inputs(DEMO_ROOT)
    script = prepared['template'] + '''
import os, socket
assert len(assays) == 4
assert assays['transcriptomics'].shape == (1000, 90)
assert os.getuid() == 65534
assert not Path('/var/run/docker.sock').exists()
try:
    Path('/input/forbidden').write_text('no')
except OSError:
    pass
else:
    raise AssertionError('Inputs were writable')
with socket.socket() as connection:
    connection.settimeout(1)
    assert connection.connect_ex(('1.1.1.1', 443)) != 0
plt.plot([1, 2], [2, 3])
plt.savefig(output / 'plot.png')
print('Isolation checks passed')
'''
    payload = run_script_analysis('synthetic_custom_script', prompt=json.dumps({
        'script': script, 'contract_id': prepared['contract_id'], 'compare_mode': False,
        'assay_ids': [], 'image_id': script_sandbox.sandbox_image()}), data_dir=DEMO_ROOT, job_dir=tmp_path)
    assert payload['data']['context']['mode'] == 'custom_script'
    assert (tmp_path / 'outputs/cohort_summary.csv').is_file()
    assert (tmp_path / 'outputs/plot.png').is_file()
    assert (tmp_path / 'analysis.py').read_text() == script
    assert 'Isolation checks passed' in (tmp_path / 'stdout.txt').read_text()
    assert json.loads((tmp_path / 'audit.json').read_text())['synthetic_only']


@pytest.mark.skipif(os.environ.get('COHORTOME_TEST_SCRIPT_SANDBOX') != '1', reason='Explicit local sandbox integration test')
def test_real_r_container(tmp_path):
    prepared = prepare_inputs(DEMO_ROOT, language='r')
    script = prepared['template'] + '''
library(limma)
library(edgeR)
library(ggplot2)
stopifnot(nrow(patients) == 90, length(assays) == 4,
          identical(dim(assays[['transcriptomics']]), c(1000L, 90L)))
png(file.path(output, 'r_plot.png'))
plot(1:3, 3:1)
dev.off()
cat('R template checks passed\\n')
'''
    result = run_script_analysis('synthetic_custom_script', prompt=json.dumps({
        'script': script, 'contract_id': prepared['contract_id'], 'compare_mode': False,
        'assay_ids': [], 'language': 'r', 'image_id': script_sandbox.sandbox_image()}),
        data_dir=DEMO_ROOT, job_dir=tmp_path)
    assert result['data']['context']['audit']['language'] == 'r'
    assert (tmp_path / 'analysis.R').read_text() == script
    assert (tmp_path / 'outputs/r_plot.png').is_file()


def test_loaded_implementation_snapshot_is_content_addressed(tmp_path, monkeypatch):
    from app import analysis_code, user_state
    monkeypatch.setattr(user_state, 'STATE_ROOT_DIR', tmp_path)
    first = analysis_code.snapshot('print("first")\n')
    second = analysis_code.snapshot('print("second")\n')
    assert first['sha256'] != second['sha256']
    assert analysis_code.code_path(first['sha256']).read_text() == 'print("first")\n'
    assert len(list((tmp_path / 'analysis_code').iterdir())) == 2
    analysis_code.snapshot('print("first")\n')
    assert len(list((tmp_path / 'analysis_code').iterdir())) == 2


def test_template_route_rejects_non_demo_and_summary_access(tmp_path, monkeypatch):
    from app import routes
    from app.schemas import AnalysisRequest
    from fastapi import HTTPException
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda *a: ['fixture'])
    monkeypatch.setattr(routes, 'resolve_dataset_dir', lambda *a: str(tmp_path))
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'detailed')
    with pytest.raises(HTTPException) as exc:
        routes.prepare_analysis_script(AnalysisRequest(prompt='prepare', dataset_id='fixture'), None)
    assert exc.value.status_code == 400
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'summary')
    with pytest.raises(HTTPException) as exc:
        routes.prepare_analysis_script(AnalysisRequest(prompt='prepare', dataset_id='fixture'), None)
    assert exc.value.status_code == 403


def test_custom_background_job_uses_saved_script_and_rechecks_access(tmp_path, monkeypatch):
    from app import jobs, user_state
    import app.analysis_external as external
    monkeypatch.setattr(user_state, 'STATE_ROOT_DIR', tmp_path)
    monkeypatch.setattr(jobs, 'user_state_dir', lambda _: tmp_path)
    monkeypatch.setattr(jobs, '_authorize_analysis_scope', lambda *a: {'dataset_ids': ['synthetic-autoimmune-demo'],
        'datasets': [{'root_path': str(DEMO_ROOT), 'query_granularity_ceiling': 'detailed'}]})
    import app.datasets as datasets
    monkeypatch.setattr(datasets, 'effective_query_granularity_ceiling', lambda _: 'detailed')
    captured = []
    def runner(ref, **kwargs):
        captured.append(json.loads(kwargs['prompt']))
        return {'reply': 'done', 'data': {'context': {'mode': 'custom_script'}}}
    monkeypatch.setitem(external.EXTERNAL_ANALYSIS_RUNNERS, 'container', runner)
    record = jobs.create_job_record(job_type='analysis', user_id='tester', data={
        'catalog_item_id': 'synthetic-custom-script', 'dataset_id': 'synthetic-autoimmune-demo',
        'runner_type': 'container', 'script_parameters': {'script': 'print(123)'}, 'prompt': 'Custom analysis'})
    result = jobs.run_analysis_job(record['job_id'], 'tester')
    assert result['status'] == 'completed'
    assert captured[0]['script'] == 'print(123)'
    assert any(item['name'] == 'audit/runner_adapter.py' for item in result['artifacts'])
    monkeypatch.setattr(datasets, 'effective_query_granularity_ceiling', lambda _: 'summary')
    result = jobs.run_analysis_job(record['job_id'], 'tester')
    assert result['status'] == 'failed'
    assert len(captured) == 1
