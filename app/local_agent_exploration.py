"""Bounded MCP exploration; only the dispatcher can authorize a shared grant.

No arbitrary paths, SQL, cohort IDs, exports or run submission. Reuse source
readers, then positively select response fields rather than returning UI payloads.
"""
import csv
from pathlib import Path

from fastapi import HTTPException

from app import analysis_catalog, biosamples, clinical_store, datasets, patient_overview, query_store


def _pick(row, keys):
    return {key: row[key] for key in keys if key in row}


def _source(grant, dataset_id, patient_id=None):
    source = next((s for s in grant.sources if s[0] == dataset_id), None)
    ids = {m['patient_id'] for m in grant.members if m['dataset_id'] == dataset_id}
    if source is None or (patient_id is not None and patient_id not in ids):
        # Do not distinguish an unknown patient from a known but unshared one.
        raise HTTPException(403, 'The requested dataset or patient is outside the shared selection.')
    return source[1], source[2], ids


def _page(rows, args):
    return dict(items=rows[args.offset:args.offset + args.limit], total=len(rows),
                next_offset=args.offset + args.limit if args.offset + args.limit < len(rows) else None)


def _inventory(root, ids):
    if not ids:
        return [], []
    rows, warnings = patient_overview.sample_inventory(root, include_imaging=True, include_clarids=False)
    return [r for r in rows if r['patient_id'] in ids], warnings


def _describe(args, grant):
    root, label, ids = _source(grant, args.dataset_id)
    rows, warnings = _inventory(root, ids)
    assays = []
    for item in query_store._assay_manifest_items_for_root(Path(root)):
        linked = [r for r in rows if r['assay_id'] == item['assay_id']]
        if not linked:
            continue
        assays.append(dict(_pick(item, ('assay_id', 'label', 'modality', 'data_type',
            'feature_namespace', 'value_kind', 'unit')),
            patient_count=len({r['patient_id'] for r in linked}),
            sample_count=len({r['sample_id'] for r in linked})))
    registered = datasets.get_dataset(args.dataset_id) or {}
    return dict(dataset_id=args.dataset_id, name=label,
        description=str(registered.get('description') or '')[:4000],
        patient_count=len(ids), clinical_representation=datasets.clinical_representation(root),
        assays=assays[:100], assays_truncated=len(assays) > 100,
        coverage_incomplete=bool(warnings), coverage_scope='shared patients only',
        notice='No linked assay rows does not establish that no assay was performed.')


def _records(args, grant):
    root, _, _ = _source(grant, args.dataset_id, args.patient_id)
    page = clinical_store.patient_records_page(root, args.patient_id, offset=args.offset, limit=args.limit)
    if page is None:
        page = dict(records=[], total=0, next_offset=None)
    records = []
    for entry in page['records']:
        record = _pick(entry['record'], ('id', 'sex', 'ethnicity', 'geographicOrigin',
            'diseases', 'phenotypicFeatures', 'measurements', 'treatments', 'interventions',
            'exposures', 'karyotypicSex', 'vitalStatus'))
        records.append(dict(_pick(entry, ('visit_id', 'event_date', 'days_from_baseline')), record=record))
    return dict(dataset_id=args.dataset_id, patient_id=args.patient_id, records=records,
                total=page['total'], next_offset=page['next_offset'],
                omitted_fields='Arbitrary info and provenance fields are not exposed.')


def _biosamples(args, grant):
    root, _, _ = _source(grant, args.dataset_id, args.patient_id)
    records = [r for r in biosamples.read_biosamples(root) if r['individualId'] == args.patient_id]
    rows = [_pick(r, ('id', 'individualId', 'sampleOriginType', 'sampleOriginDetail',
        'biosampleStatus', 'collectionMoment', 'collectionDate', 'histologicalDiagnosis',
        'pathologicalStage', 'pathologicalTnmFinding', 'tumorProgression', 'clarid'))
        for r in sorted(records, key=lambda r: r['id'])]
    return dict(dataset_id=args.dataset_id, patient_id=args.patient_id, **_page(rows, args))


def _assay(args, grant):
    root, _, ids = _source(grant, args.dataset_id)
    item = next((i for i in query_store._assay_manifest_items_for_root(Path(root))
                 if i.get('assay_id') == args.assay_id), None)
    if item is None:
        raise HTTPException(404, 'Assay not found in the shared dataset.')
    path = query_store._external_assay_matrix_path(root, item)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise HTTPException(422, 'MCP feature browsing requires a matrix panel of at most 64 MiB.')
    return root, ids, item


def _features(args, grant):
    root, _, _ = _assay(args, grant)
    rows = query_store.assay_feature_inventory(root, args.assay_id,
        search=args.search, limit=args.offset + args.limit + 1)
    return dict(dataset_id=args.dataset_id, assay_id=args.assay_id,
        features=rows[args.offset:args.offset + args.limit],
        next_offset=args.offset + args.limit if len(rows) > args.offset + args.limit else None,
        semantics='Feature catalogue only; no patient measurements or whole-dataset statistics.')


def _measurements(args, grant):
    root, ids, item = _assay(args, grant)
    if not ids:
        return dict(dataset_id=args.dataset_id, assay_id=args.assay_id, feature_id=args.feature_id,
                    items=[], total=0, next_offset=None)
    path, delimiter, samples, links = query_store._external_assay_header(root, item)
    selected = [(i, sid) for i, sid in enumerate(samples, 1) if links[sid] in ids]
    values = None
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        next(reader, None)
        for row in reader:
            if not row or row[0].strip() != args.feature_id:
                continue
            if values is not None or len(row) != len(samples) + 1:
                raise HTTPException(409, 'The selected feature has ambiguous or invalid matrix rows.')
            values = [dict(patient_id=links[sid], sample_id=sid,
                           value=query_store._external_numeric_value(row[i])) for i, sid in selected]
    if values is None:
        raise HTTPException(404, 'Feature not found. Use an exact identifier from list_assay_features.')
    values.sort(key=lambda r: (r['patient_id'], r['sample_id']))
    return dict(dataset_id=args.dataset_id, assay_id=args.assay_id, feature_id=args.feature_id,
        **_pick(item, ('modality', 'data_type', 'value_kind', 'unit')),
        **_page(values, args), semantics='Source-scale sample values; null is missing. No aggregation or imputation.')


def _analysis_items():
    return [i for i in analysis_catalog.load_analysis_catalog() if not i.get('debug_only')]


def _analysis_description(item):
    from app.local_agent_runs import SUPPORTED
    return dict(_pick(item, ('id', 'name', 'category', 'description', 'guidance',
        'requires_measurement', 'minimum_samples_per_cohort', 'required_modalities',
        'required_data_types', 'supports_compare_mode', 'default_compare_mode')),
        requirements=analysis_catalog._workspace_requirements(item), execution_via_mcp=False,
        mcp_proposal_supported=item['id'] in SUPPORTED,
        mcp_approval='Owner approval in COHORTome is required; discovery alone cannot start a job.')


def _analyses(args):
    rows = [_analysis_description(i) for i in _analysis_items()
            if args.search.casefold() in (i['name'] + ' ' + i['description']).casefold()]
    return _page(rows, args)


def _requirements(args, grant):
    item = next((i for i in _analysis_items() if i['id'] == args.analysis_id), None)
    if item is None:
        raise HTTPException(404, 'Analysis not found.')
    assays, incomplete = [], False
    representations = set()
    for dataset_id, root, _ in grant.sources:
        ids = {m['patient_id'] for m in grant.members if m['dataset_id'] == dataset_id}
        rows, warnings = _inventory(root, ids)
        incomplete |= bool(warnings)
        assays.extend(rows)
        representations.add(datasets.clinical_representation(root))
    blockers = []
    if not grant.members:
        blockers.append('The shared selection is empty.')
    if item.get('requires_single_dataset_workspace') and len(grant.sources) != 1:
        blockers.append('Select exactly one dataset.')
    representation = item.get('required_clinical_representation')
    if representation and representations != {representation}:
        blockers.append('The shared datasets do not all have the required clinical representation.')
    if not analysis_catalog._assay_requirement_available(item, assays):
        blockers.append('No compatible linked assay was found in the shared selection.')
    pending = ['Validate analysis parameters and runtime availability in COHORTome.']
    if item.get('requires_measurement'):
        pending.append('Select a clinical measurement and validate its observations and timepoints.')
    if item.get('default_compare_mode'):
        pending.append('Define Cohorts A and B; validate overlap and usable samples in each.')
    if item.get('minimum_samples_per_cohort'):
        pending.append('Check minimum usable samples per cohort after missing-value and replicate handling.')
    if incomplete:
        pending.append('Some assay linkage could not be inspected; coverage is incomplete.')
    return dict(analysis=_analysis_description(item), blockers=blockers, checks_remaining=pending,
                validation='partial', execution_via_mcp=False,
                notice='This is not permission or confirmation to run. Complete setup in COHORTome.')


def explore(name, args, grant, request):
    handlers = {'describe_dataset': _describe, 'get_clinical_records': _records,
        'list_biosamples': _biosamples, 'list_assay_features': _features,
        'get_assay_measurements': _measurements, 'check_analysis_requirements': _requirements}
    try:
        return _analyses(args) if name == 'list_analyses' else handlers[name](args, grant)
    except (OSError, ValueError, KeyError):
        raise HTTPException(409, 'The requested data could not be inspected. Check the shared dataset in COHORTome.') from None
