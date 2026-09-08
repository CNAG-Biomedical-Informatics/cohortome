"""Bridge between prepared synthetic inputs and the existing Analysis job model."""
import json
from pathlib import Path

from app.script_inputs import prepare_inputs
from app.script_sandbox import execute_script, sandbox_image


def run_script_analysis(runner_ref, *, prompt, data_dir, selected_patient_ids='',
                        compare_selected_patient_ids='', job_dir=None, **kwargs):
    if runner_ref != 'synthetic_custom_script' or job_dir is None:
        raise RuntimeError('Custom scripts require the isolated background runner.')
    parameters = json.loads(prompt)
    language = parameters.get('language', 'python')
    prepared = prepare_inputs(data_dir, selected_patient_ids, compare_selected_patient_ids,
                              bool(parameters['compare_mode']), parameters['assay_ids'], language)
    if prepared['contract_id'] != parameters['contract_id']:
        raise RuntimeError('The prepared inputs changed. Prepare the template again.')
    script = parameters['script']
    if not isinstance(script, str) or not script.strip() or len(script.encode()) > 128 * 1024:
        raise RuntimeError('Provide a script of at most 128 KiB.')
    root = Path(job_dir)
    (root / ('analysis.R' if language == 'r' else 'analysis.py')).write_text(script, encoding='utf-8')
    (root / 'input_contract.json').write_text(json.dumps(prepared['contract'], indent=2), encoding='utf-8')
    # Preserve the exact prepared inputs for reproducibility. Only approved synthetic data reaches here.
    inputs = root / 'inputs'
    inputs.mkdir(exist_ok=True)
    for name, text in prepared['files'].items():
        (inputs / name).write_text(text, encoding='utf-8')
    result = execute_script(prepared['files'], script, root, parameters['image_id'], language)
    audit = {key: result[key] for key in ('image_id', 'script_sha256', 'exit_code')}
    audit.update(contract_id=prepared['contract_id'], synthetic_only=True, language=language,
                 limits={'seconds': 90, 'memory_mib': 512, 'cpus': 1, 'pids': 64, 'output_mib': 4})
    (root / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    if result['exit_code']:
        raise RuntimeError(f"Custom script exited with code {result['exit_code']}. Open the run's stderr log and saved script for details.")
    return {'intent': 'analysis_custom_script',
            'reply': f"Custom {('R' if language == 'r' else 'Python')} analysis completed on synthetic data. Produced {len(result['files'])} output files. Code execution is not validation of the statistical method.",
            'data': {'source': 'deterministic', 'execution': 'external_runner', 'model': None,
                     'context': {'mode': 'custom_script', 'outputs': result['files'],
                                 'stdout': result['stdout'], 'stderr': result['stderr'], 'audit': audit}}}
