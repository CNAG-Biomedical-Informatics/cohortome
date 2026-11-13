"""Owner-approved curated MCP runs. No agent-controlled commands or prompts."""
import csv
import hashlib
import json
import secrets
import tempfile
import time
from pathlib import Path

from fastapi import HTTPException

from app import analysis_catalog, analysis_external, analysis_sessions, cohort_filters, datasets, jobs
from app.identities import identity_key

SUPPORTED = {
    'transcriptomics-deseq2-differential-expression',
    'transcriptomics-limma-voom-differential-expression',
    'flow-cytometry-wilcoxon-cohort-comparison',
    'serology-wilcoxon-cohort-comparison',
}
_plans = {}  # Transient permissions, never recovered on restart.


def _digest(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()


def _item(identifier):
    item = analysis_catalog.get_analysis_catalog_item(identifier)
    if identifier not in SUPPORTED or not item or item['runner_type'] != 'rscript' or item['execution_backend'] != 'job':
        raise HTTPException(422, 'This analysis is not enabled for MCP execution.')
    return item


def _validate_inputs(args, grant):
    from app.query_store import _assay_manifest_items_for_root, _external_assay_matrix_path
    if len(grant.sources) != 1 or grant.sources[0][0] != args.dataset_id:
        raise HTTPException(422, 'Share exactly one dataset for an MCP analysis run.')
    allowed = {m['patient_id'] for m in grant.members}
    a, b = sorted(set(args.cohort_a)), sorted(set(args.cohort_b))
    if not a or not b or set(a) & set(b) or not (set(a) | set(b)) <= allowed:
        raise HTTPException(422, 'Choose two non-empty, disjoint groups from the shared patients.')
    if any(',' in p or ':' in p or p != p.strip() for p in a + b):
        raise HTTPException(422, 'These patient identifiers are not supported by this runner interface.')
    item = _item(args.analysis_id)
    root = grant.sources[0][1]
    assay = next((i for i in _assay_manifest_items_for_root(Path(root)) if i.get('assay_id') == args.assay_id), None)
    if not assay or not analysis_catalog._assay_requirement_available(item, [assay]):
        raise HTTPException(422, 'Choose a compatible assay from the shared dataset.')
    if _external_assay_matrix_path(root, assay).stat().st_size > 64 * 1024 * 1024:
        raise HTTPException(422, 'MCP execution currently accepts matrix panels up to 64 MiB.')
    reason = analysis_catalog.rscript_unavailable_reason(item['runner_ref'])
    if reason or not jobs.analysis_worker_available():
        raise HTTPException(409, 'The required R runtime or analysis runner is unavailable. Check Jobs in COHORTome.')
    # Use the same bundle validation as the actual runner; no R process is run.
    with tempfile.TemporaryDirectory(prefix='cohortome-mcp-plan-') as folder:
        kwargs = dict(prompt=item['default_prompt'], assay_id=args.assay_id,
                      selected_patient_ids=','.join(a), compare_selected_patient_ids=','.join(b),
                      output_dir=Path(folder))
        if item['runner_ref'] == 'quantitative_assay_wilcoxon_comparison':
            bundle = analysis_external._prepare_quantitative_assay_comparison_bundle(root, **kwargs)
        else:
            limma = item['runner_ref'] == 'transcriptomics_limma_voom_differential_expression'
            bundle = analysis_external._prepare_transcriptomics_differential_expression_bundle(root, **kwargs,
                method='limma_voom' if limma else 'deseq2_apeglm', minimum_samples_per_group=2,
                required_data_type='rsem_expected_counts' if limma else 'raw_counts')
            (analysis_external._validate_limma_voom_bundle if limma else
             analysis_external._validate_deseq2_bundle)(bundle)
        counts = {k: bundle[k] for k in ('cohort_a_patient_count', 'cohort_b_patient_count',
                  'cohort_a_sample_count', 'cohort_b_sample_count', 'feature_count', 'gene_count',
                  'data_type', 'analysis_covariates') if k in bundle}
    return item, a, b, counts


def prepare(args, grant, request):
    from app import local_agents
    # Limit transient proposals and prevent unattended disk/compute churn.
    with local_agents._lock:
        for key, plan in list(_plans.items()):
            if plan['grant'].token_hash != grant.token_hash or time.monotonic() >= plan['grant'].deadline:
                del _plans[key]
        if len(_plans) >= 10:
            raise HTTPException(429, 'At most ten MCP plans are retained per connection. Turn access off to reset.')
    try:
        item, a, b, counts = _validate_inputs(args, grant)
    except (RuntimeError, ValueError, OSError):
        raise HTTPException(422, 'Analysis inputs failed validation. Check assay type, usable samples, replicates and covariates in COHORTome.') from None
    local_agents._validate_grant(grant, request)
    identifier = secrets.token_urlsafe(24)
    with local_agents._lock:
        local_agents._validate_grant(grant, request)
        _plans[identifier] = dict(id=identifier, grant=grant, arguments=args, item_hash=_digest(item),
            name=item['name'], counts=counts, a=a, b=b, status='awaiting_approval', job_id='',
            session_id='', allow_results=False, deadline=min(grant.deadline, time.monotonic() + 900))
    return _public(_plans[identifier])


def _public(plan):
    return dict(plan_id=plan['id'], status=plan['status'], analysis=plan['name'],
        dataset_id=plan['arguments'].dataset_id, assay_id=plan['arguments'].assay_id,
        cohort_a_patient_count=len(plan['a']), cohort_b_patient_count=len(plan['b']),
        validated_inputs=plan['counts'], job_id=plan['job_id'], analysis_session_id=plan['session_id'],
        results_shared=plan['allow_results'],
        approval='Approve this exact plan in COHORTome → Settings → Query & AI → Agent access (MCP).')


def pending(grant, *, owner=False):
    if grant is None:
        return []
    for plan in _plans.values():
        if plan['status'] == 'awaiting_approval' and (plan['grant'] is not grant or time.monotonic() >= plan['deadline']):
            plan['status'] = 'expired'
    return [dict(_public(p), **({'cohort_a':p['a'], 'cohort_b':p['b']} if owner else {}))
            for p in _plans.values() if p['grant'].token_hash == grant.token_hash
            and p['status'] == 'awaiting_approval']


def decide(plan_id, grant, request, *, approve, allow_results):
    from app import local_agents
    plan = _plans.get(plan_id)
    if not plan or plan['grant'] is not grant or time.monotonic() >= plan['deadline']:
        raise HTTPException(409, 'This plan expired or the shared selection changed. Ask the agent to prepare a new plan.')
    if plan['status'] != 'awaiting_approval':
        return _public(plan)  # Repeated approval cannot submit twice.
    if not approve:
        plan['status'] = 'rejected'
        return _public(plan)
    local_agents._validate_grant(grant, request)
    try:
        item, a, b, counts = _validate_inputs(plan['arguments'], grant)
    except (RuntimeError, ValueError, OSError):
        raise HTTPException(409, 'Inputs are no longer ready. Prepare a new plan.') from None
    if _digest(item) != plan['item_hash'] or counts != plan['counts']:
        raise HTTPException(409, 'The analysis plan changed. Prepare a new plan.')
    local_agents._validate_grant(grant, request)
    root = grant.sources[0][1]
    dataset_id = plan['arguments'].dataset_id
    session_id = 'mcp-' + secrets.token_hex(16)
    from app.datasets import workspace_fingerprint_for_data_dir
    metadata = lambda ids: dict(dataset_id=dataset_id, dataset_ids=[dataset_id],
        members=[dict(dataset_id=dataset_id, patient_id=p) for p in ids],
        id_type='patient', is_full_dataset=False, source={'kind':'mcp'})
    session = dict(id=session_id, title='MCP · ' + item['name'], dataset_id=dataset_id, data_dir=root,
        workspace_fingerprint=workspace_fingerprint_for_data_dir(root, dataset_id=dataset_id, dataset_ids=[dataset_id]),
        catalog_item_id=item['id'], assay_ids=[plan['arguments'].assay_id], execution_mode='deterministic',
        scope=','.join(identity_key(dataset_id, 'patient', p) for p in a), scope_metadata=metadata(a),
        compare_scope=','.join(identity_key(dataset_id, 'patient', p) for p in b), compare_scope_metadata=metadata(b),
        compare_mode=True, turns=[dict(role='user', prompt='Started via MCP; approved in COHORTome. ' + item['default_prompt'])])
    analysis_sessions.save_analysis_session(session, user_id=grant.user_id)
    plan.update(status='submitting', session_id=session_id, allow_results=allow_results)
    approval = dict(sources=grant.sources, fingerprint=grant.fingerprint, item_hash=plan['item_hash'],
                    cohort_a=a, cohort_b=b, assay_id=plan['arguments'].assay_id, results_shared=allow_results)
    try:
        job = jobs.submit_analysis_job(user_id=grant.user_id, analysis_session_id=session_id,
            prompt=item['default_prompt'], data_dir=root, dataset_id=dataset_id, assay_id=plan['arguments'].assay_id,
            catalog_item=item, selected_patient_ids=','.join(a), compare_selected_patient_ids=','.join(b),
            compare_mode=True, mcp_approval=approval)
        plan.update(status='submitted', job_id=job['job_id'])
        payload = dict(intent='analysis_job', reply='Started via MCP. Open Jobs to follow this approved run.',
            data=dict(source='job', execution='queued', job_id=job['job_id'], job_status=job['status'],
                      catalog_item_id=item['id'], catalog_item_name=item['name']))
    except Exception:
        plan['status'] = 'failed'
        payload = dict(intent='analysis_error', reply='The approved MCP run could not be submitted. Check Jobs in COHORTome.', data={})
    session['turns'].append(dict(role='assistant', payload=payload))
    analysis_sessions.save_analysis_session(session, user_id=grant.user_id)
    return _public(plan)


def validate_job(record, item):
    """Runs in the normal job process before execution and before publishing results."""
    approval = record.get('mcp_approval')
    if not approval:
        return
    from app.local_agents import _verify_fixture
    sources = [tuple(s) for s in approval['sources']]
    if (len(sources) != 1 or record['dataset_id'] != sources[0][0]
            or record['assay_id'] != approval['assay_id']
            or record['selected_patient_ids'] != ','.join(approval['cohort_a'])
            or record['compare_selected_patient_ids'] != ','.join(approval['cohort_b'])):
        raise RuntimeError('The run no longer matches the approved MCP plan.')
    for key, root, _ in sources:
        if str(datasets.get_dataset(key)['root_path']) != root:
            from app.bff import resolve_project_data_dir
            if str(resolve_project_data_dir(datasets.get_dataset(key)['root_path'])) != root:
                raise RuntimeError('The approved dataset location changed.')
        _verify_fixture(key, root)
    if (_digest(item) != approval['item_hash'] or item['id'] not in SUPPORTED
            or cohort_filters._fingerprint(sources, record['submitted_by']) != approval['fingerprint']):
        raise RuntimeError('The approved MCP analysis inputs changed. Prepare a new plan.')


def inspect(args, grant):
    plan = _plans.get(args.plan_id)
    if not plan or plan['grant'].token_hash != grant.token_hash:
        raise HTTPException(403, 'This plan is not authorized by the current connection.')
    pending(grant)
    public = _public(plan)
    if not plan['job_id']:
        return public
    record = jobs.load_job_record(plan['job_id'], grant.user_id)
    public['job_status'] = record['status']
    if not args.include_results or record['status'] != 'completed':
        return public
    allowed = {(m['dataset_id'], m['patient_id']) for m in grant.members}
    required = {(plan['arguments'].dataset_id, p) for p in plan['a'] + plan['b']}
    if not plan['allow_results'] or not required <= allowed:
        raise HTTPException(403, 'Result sharing was not approved or these patients are no longer shared.')
    validate_job(record, _item(plan['arguments'].analysis_id))
    filename = 'compact_assay_results.tsv' if 'wilcoxon' in plan['arguments'].analysis_id else 'de_results.tsv'
    path = jobs.resolve_job_artifact_path(plan['job_id'], grant.user_id, filename)
    columns = {'feature_id', 'gene_id', 'log2_fold_change', 'p_value', 'adj_p_value', 't', 'stat',
               'lfc_se', 'rank_biserial_effect', 'cohort_a_median', 'cohort_b_median',
               'cohort_a_n', 'cohort_b_n', 'mean_difference', 'median_difference', 'status'}
    rows = []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        for i, row in enumerate(csv.DictReader(handle, delimiter='\t')):
            if i < args.offset:
                continue
            if len(rows) > args.limit:
                break
            rows.append({k:v for k,v in row.items() if k in columns})
    public.update(results=rows[:args.limit], next_offset=args.offset + args.limit if len(rows) > args.limit else None,
                  notice='Feature-level results only. Plots, full tables and logs remain available in COHORTome.')
    return public
