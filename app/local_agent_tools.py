"""Read-only tools restricted to an explicitly shared patient snapshot.

Authentication, expiry, source checksums and disclosure checks belong to the
local-agent boundary. This module never chooses a workspace on the agent's
behalf or accepts replacement membership from tool arguments.
"""
from collections import Counter
from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import cohort_filters, cohort_scope
from app.query_store import _connect


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class FieldArguments(Arguments):
    search: str = Field(default='', max_length=150)
    offset: int = Field(default=0, ge=0, le=1000)
    limit: int = Field(default=25, ge=1, le=50)


ShortLabel = Annotated[str, Field(min_length=1, max_length=256)]


class SelectionArguments(Arguments):
    clinical_filters: list[cohort_filters.FilterClause] = Field(default_factory=list, max_length=20)
    diseases: list[ShortLabel] = Field(default_factory=list, max_length=100)
    modalities: list[ShortLabel] = Field(default_factory=list, max_length=40)
    sample_origin: str = Field(default='', max_length=256)
    q: str = Field(default='', max_length=150)
    exact: bool = False


class PatientArguments(SelectionArguments):
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=25, ge=1, le=100)


_TOOLS = {
    'describe_scope': (Arguments, 'Describe the shared, frozen patient selection and its datasets. '
        'This is not a live view of the Desktop selection. Results concern synthetic test data.'),
    'list_filter_fields': (FieldArguments, 'Discover clinical filter fields, their operators, and '
        'values recorded only in the shared patients. Search by field label; use field IDs in '
        'clinical_filters. Categories are OR within one clause, clauses are AND; recorded at any visit.'),
    'find_patients': (PatientArguments, 'Find patients within the shared selection using the same '
        'clinical, disease, sample-origin and modality filters as COHORTome. Returns a bounded '
        'page of dataset-qualified IDs and the complete matching count. Does not change app scope. '
        'q searches patient IDs/ClarIDs, not free-text research questions.'),
    'summarize_selection': (SelectionArguments, 'Summarize shared patients, optionally narrowed by '
        'the same filters as find_patients. Reports clinical counts and linked assay availability, '
        'not molecular analysis or statistical inference. Does not change app scope.'),
}

TOOL_DEFINITIONS = [dict(name=name, description=description, inputSchema=model.model_json_schema(),
    annotations=dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    for name, (model, description) in _TOOLS.items()]


def _scope(grant):
    counts = Counter(member['dataset_id'] for member in grant.members)
    return dict(patient_count=len(grant.members),
        datasets=[dict(dataset_id=identifier, name=label, patient_count=counts[identifier])
                  for identifier, _, label in grant.sources],
        entity='patient', frozen=True, synthetic=True,
        notice='Synthetic data test software; these results are not biological evidence.')


def _field_page(args, grant):
    # Catalogue bindings contain only server-generated SQL, never agent input.
    # In particular, do not return the catalogue's workspace-wide options/range.
    catalogue = cohort_filters._catalogue(grant.sources)
    candidates = sorted((field for field in catalogue.values()
                         if args.search.casefold() in field['label'].casefold()),
                        key=lambda field: (field['label'].casefold(), field['unit'], field['id']))
    page = candidates[args.offset:args.offset + args.limit]
    fields = []
    by_source = {identifier: [m['patient_id'] for m in grant.members if m['dataset_id'] == identifier]
                 for identifier, _, _ in grant.sources}
    for field in page:
        public = {key: field[key] for key in ('id', 'label', 'kind', 'unit', 'dataset_ids', 'operators', 'group')
                  if key in field}
        options, bounds, truncated = set(), [], False
        for identifier, root, _ in grant.sources:
            ids = by_source[identifier]
            if not ids or identifier not in field['_bindings']:
                continue
            table, predicate, params, value = field['_bindings'][identifier]
            base = f'FROM {table} WHERE ({predicate}) AND patient_id IN (SELECT unnest(?))'
            with _connect(root) as connection:
                if field['kind'] == 'number':
                    low, high = connection.execute(f'SELECT min({value}), max({value}) {base} '
                        f'AND isfinite({value})', params + [ids]).fetchone()
                    if low is not None:
                        bounds.extend((low, high))
                elif field['kind'] in ('string', 'boolean'):
                    rows = connection.execute(f'SELECT DISTINCT {value} AS value {base} '
                        f'AND {value} IS NOT NULL ORDER BY value LIMIT 51', params + [ids]).fetchall()
                    values = [row[0] for row in rows if not isinstance(row[0], str)
                              or (row[0].strip() and len(row[0]) <= 500)]
                    options.update(values)
                    truncated = truncated or len(rows) > 50 or len(options) > 50
        if bounds:
            public['observed_range'] = [min(bounds), max(bounds)]
        if field['kind'] in ('string', 'boolean'):
            public.update(options=sorted(options, key=str)[:50], options_truncated=truncated)
        fields.append(public)
    next_offset = args.offset + args.limit if args.offset + args.limit < len(candidates) else None
    return dict(scope=_scope(grant), fields=fields, total_fields=len(candidates), next_offset=next_offset,
                values_scope='shared patients only', temporal_rule='recorded at any visit')


def _selection(args, grant, request):
    conditions = args.model_dump(exclude={'offset', 'limit'})
    result = cohort_scope.apply_draft(cohort_scope.Draft(workspace=grant.workspace,
        fingerprint=grant.fingerprint, base_members=grant.members, **conditions), request)
    selection = result.get('selection')
    if not isinstance(selection, dict) or not isinstance(selection.get('members'), list):
        raise HTTPException(409, 'The shared selection could not be evaluated.')
    members = selection['members']
    allowed = {(m['dataset_id'], m['patient_id']) for m in grant.members}
    if any((m['dataset_id'], m['patient_id']) not in allowed for m in members):
        raise HTTPException(409, 'The shared selection could not be evaluated.')
    members = [dict(dataset_id=dataset, patient_id=patient)
               for dataset, patient in sorted({(m['dataset_id'], m['patient_id']) for m in members})]
    return result, members, conditions


def _patient_page(args, grant, request):
    _, members, conditions = _selection(args, grant, request)
    next_offset = args.offset + args.limit if args.offset + args.limit < len(members) else None
    return dict(scope=_scope(grant), patient_count=len(members), patients=members[args.offset:args.offset + args.limit],
                next_offset=next_offset, filters=conditions, temporal_rule='recorded at any visit')


def _summary(args, grant, request):
    result, members, conditions = _selection(args, grant, request)
    summary = result['summary']
    totals = summary['totals']
    counts = Counter(m['dataset_id'] for m in members)
    # Positive lists deliberately exclude individual timelines, patient IDs,
    # provenance paths and whole-workspace denominators from the UI response.
    assays = [{key: item[key] for key in ('assay_id', 'label', 'modality', 'data_type',
                'sample_count', 'patient_count', 'feature_count') if key in item}
              for item in result.get('assays') or []]
    return dict(scope=_scope(grant), patient_count=len(members), filters=conditions,
        clinical_patient_count=totals['patients'], clinical_record_count=totals['clinical_records'],
        datasets=[dict(dataset_id=identifier, name=label, patient_count=counts[identifier])
                  for identifier, _, label in grant.sources],
        sex_counts=summary.get('sex_counts', {}), visit_distribution=summary.get('visit_distribution', {}),
        top_diseases=[{key: item[key] for key in ('disease', 'patient_count') if key in item}
                      for item in summary.get('top_diseases', [])[:8]],
        top_medications=[{key: item[key] for key in ('medication', 'patient_count') if key in item}
                         for item in summary.get('top_medications', [])[:8]],
        assays=assays[:100], assays_truncated=len(assays) > 100,
        semantics='Patient-level availability at any visit. It does not establish same-visit or same-specimen linkage.')


def execute_tool(name: str, arguments: dict, grant, request: Request) -> dict:
    definition = _TOOLS.get(name)
    if definition is None:
        raise HTTPException(422, 'Unknown read-only tool.')
    try:
        args = definition[0].model_validate(arguments)
    except ValidationError:
        # Do not echo arbitrary arguments or Pydantic's input snippets.
        raise HTTPException(422, 'Invalid tool arguments. Use the declared input schema.') from None
    if name == 'describe_scope':
        return _scope(grant)
    if name == 'list_filter_fields':
        return _field_page(args, grant)
    if name == 'find_patients':
        return _patient_page(args, grant, request)
    return _summary(args, grant, request)
