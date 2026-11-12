"""Dataset-driven clinical filters over prepared stores; no model involvement."""
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app import patient_overview
from app.dataset_sources import dataset_input_signature
from app.query_store import _connect, ensure_query_store, QueryStoreNotReadyError, duckdb, QUERY_STORE_SCHEMA_VERSION
from app.user_state import request_user_id


router = APIRouter(prefix='/cohort-builder', tags=['cohorts'])
MAX_FIELDS = 1000
MAX_MEMBERS = 100_000
OPERATORS = {
    'number': ['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'between', 'is_present', 'is_missing'],
    'date': ['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'between', 'is_present', 'is_missing'],
    'boolean': ['eq', 'ne', 'is_present', 'is_missing'],
    'string': ['eq', 'ne', 'in', 'contains', 'is_present', 'is_missing'],
}
# These are semantic source paths, not a fixed list of study measurements.
# Arbitrary info/free text stays inspectable but is not silently made a filter.
SCALAR_PATHS = {
    ('sex',), ('sex', 'label'), ('gender',), ('ethnicity', 'label'),
    ('geographicOrigin', 'label'), ('karyotypicSex',), ('vitalStatus', 'status'),
    ('age',), ('age_at_visit',), ('ageAtCollection', 'age'),
    ('event_date',), ('date_of_birth',), ('birthDate',),
    ('info', 'event_date'), ('info', 'age'), ('info', 'age_at_visit'),
    ('info', 'days_from_baseline'), ('info', 'week_from_baseline'),
}
COLLECTION_LABELS = {'diseases': 'Recorded diagnoses', 'phenotypicFeatures': 'Non-excluded phenotypes',
                     'treatments': 'Recorded treatments', 'interventionsOrProcedures': 'Recorded procedures'}


class FilterClause(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field_id: str = Field(min_length=1, max_length=80)
    operator: str = Field(min_length=1, max_length=24)
    values: list = Field(default_factory=list, max_length=50)


class FilterRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace: str = Field(min_length=1, max_length=2000)
    fingerprint: str = Field(min_length=64, max_length=64)
    filters: list[FilterClause] = Field(default_factory=list, max_length=20)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def _fingerprint(available, user_id):
    return _digest({'version': 1, 'store_schema': QUERY_STORE_SCHEMA_VERSION, 'user': user_id,
                    'datasets': [(identifier, str(Path(root).resolve()), dataset_input_signature(root))
                                 for identifier, root, _ in sorted(available)]})


def _add(fields, identity, label, kind, unit, dataset, dataset_label, binding):
    identifier = _digest(identity)
    field = fields.setdefault(identifier, dict(id=identifier, label=label, kind=kind,
        unit=unit or '', dataset_ids=[], dataset_labels=[], operators=OPERATORS[kind],
        options=[], _bindings={}))
    if identity[0] == 'measurement':
        field['group'] = 'Measurements' if identity[1] == 'measures' else 'Exposures'
    elif identity[0] == 'collection':
        field['group'] = {'diseases': 'Diagnoses', 'phenotypicFeatures': 'Phenotypes',
                          'treatments': 'Treatments', 'interventionsOrProcedures': 'Procedures'}[identity[2]]
    else:
        field['group'] = 'Demographics and time'
    if dataset not in field['_bindings']:
        field['dataset_ids'].append(dataset)
        field['dataset_labels'].append(dataset_label)
    field['_bindings'][dataset] = binding
    if len(fields) > MAX_FIELDS:
        raise HTTPException(422, 'Too many clinical fields. Select fewer datasets before adding filters.')


def _catalogue(available):
    fields = {}
    for dataset, root, dataset_label in available:
        ensure_query_store(root)
        con = _connect(root)
        try:
            rows = con.execute('''SELECT collection, code_id, code_label, unit_id, unit_label,
                CASE WHEN number_value IS NOT NULL THEN 'number'
                     WHEN boolean_value IS NOT NULL THEN 'boolean'
                     WHEN coalesce(value_code_id, value_code_label, text_value) IS NOT NULL
                     THEN 'string' ELSE NULL END AS kind
                FROM clinical_observations
                WHERE patient_id IS NOT NULL AND collection IN ('measures', 'exposures')
                GROUP BY ALL ORDER BY collection, code_id, code_label, unit_id, unit_label''').fetchall()
            for collection, code, label, unit_code, unit, kind in rows:
                if not kind or not (code or label):
                    continue
                identity = ['measurement', collection, code or [dataset, label], unit_code, unit, kind,
                            dataset if kind == 'number' and not (unit_code or unit) else None]
                value = {'number': 'number_value', 'boolean': 'boolean_value',
                    'string': "CASE WHEN coalesce(value_code_id, '') <> '' THEN value_code_id || CASE WHEN coalesce(value_code_label, '') <> '' THEN ' · ' || value_code_label ELSE '' END ELSE coalesce(value_code_label, text_value) END"}[kind]
                predicate = '''collection = ? AND code_id IS NOT DISTINCT FROM ?
                    AND unit_id IS NOT DISTINCT FROM ? AND unit_label IS NOT DISTINCT FROM ?'''
                params = [collection, code, unit_code, unit]
                if not code:
                    predicate += ' AND code_label IS NOT DISTINCT FROM ?'
                    params.append(label)
                # Keep textual categories separate from numeric strings.
                if kind == 'string':
                    predicate += ' AND number_value IS NULL'
                _add(fields, identity, f'{label or code}' + (f' [{code}]' if code and label else ''),
                     kind, unit or unit_code or '', dataset, dataset_label,
                     ('clinical_observations', predicate, params, value))
            scalar = con.execute('''SELECT field_path, value_type,
                bool_and(date_value IS NOT NULL) FILTER (WHERE text_value IS NOT NULL AND text_value <> '')
                FROM clinical_values WHERE patient_id IS NOT NULL
                GROUP BY field_path, value_type ORDER BY field_path, value_type''').fetchall()
            for path, value_type, dates in scalar:
                keys = tuple(json.loads(match) for match in re.findall(r'"(?:[^"\\]|\\.)*"', path))
                if keys not in SCALAR_PATHS or value_type not in ('string', 'number', 'boolean'):
                    continue
                kind = 'date' if value_type == 'string' and dates else value_type
                value = {'number': 'number_value', 'boolean': 'boolean_value', 'string': 'text_value', 'date': 'date_value'}[kind]
                label = ' · '.join(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key).replace('_', ' ')
                                   for key in keys if key not in {'info', 'label'})
                _add(fields, ['scalar', keys, kind, dataset if kind == 'number' else None], label[:1].upper() + label[1:], kind, '', dataset, dataset_label,
                     ('clinical_values', 'field_path = ? AND value_type = ?', [path, value_type], value))
            for collection, label in COLLECTION_LABELS.items():
                # Codes stay attached to labels. Uncoded text is not silently
                # harmonized with the same label in another source dataset.
                predicate = 'collection = ? AND excluded IS DISTINCT FROM true'
                value = "CASE WHEN coalesce(code_id, '') <> '' THEN code_id || CASE WHEN coalesce(code_label, '') <> '' THEN ' · ' || code_label ELSE '' END ELSE code_label END"
                if con.execute(f'''SELECT 1 FROM clinical_observations WHERE {predicate}
                    AND patient_id IS NOT NULL AND {value} IS NOT NULL LIMIT 1''', [collection]).fetchone():
                    _add(fields, ['collection', dataset, collection], label, 'string', '', dataset, dataset_label,
                         ('clinical_observations', predicate, [collection], value))
                    if collection == 'phenotypicFeatures':
                        # An explicitly excluded phenotype is known negative,
                        # not missing metadata. Defer negative/missing phenotype
                        # filtering until rules select individual coded terms.
                        fields[_digest(['collection', dataset, collection])]['operators'] = ['eq', 'in', 'contains', 'is_present']
            for field in fields.values():
                if dataset in field['_bindings'] and field['kind'] == 'number':
                    table, predicate, params, value = field['_bindings'][dataset]
                    low, high = con.execute(f'''SELECT min({value}), max({value}) FROM {table}
                        WHERE patient_id IS NOT NULL AND {predicate} AND isfinite({value})''', params).fetchone()
                    if low is not None:
                        previous = field.get('observed_range', [low, high])
                        field['observed_range'] = [min(previous[0], low), max(previous[1], high)]
                if dataset not in field['_bindings'] or field['kind'] not in ('string', 'boolean'):
                    continue
                table, predicate, params, value = field['_bindings'][dataset]
                rows = con.execute(f'''SELECT DISTINCT {value} AS value FROM {table}
                    WHERE patient_id IS NOT NULL AND {predicate} AND {value} IS NOT NULL
                    ORDER BY value LIMIT 50''', params).fetchall()
                field['options'] = sorted(set(field['options']) | {r[0] for r in rows
                    if not isinstance(r[0], str) or (r[0].strip() and len(r[0]) <= 500)}, key=str)[:50]
        finally:
            con.close()
    return fields


def _validate(field, clause):
    operator, values = clause.operator, clause.values
    if operator not in field['operators']:
        raise HTTPException(422, 'This operator is not supported for the selected field.')
    count = 0 if operator in {'is_missing', 'is_present'} else 2 if operator == 'between' else None if operator == 'in' else 1
    if (count is not None and len(values) != count) or (operator == 'in' and not values):
        raise HTTPException(422, 'Supply the required number of filter values.')
    kind = field['kind']
    for value in values:
        valid = False
        if kind == 'number':
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
        elif kind == 'boolean':
            valid = type(value) is bool
        elif kind in ('string', 'date'):
            valid = isinstance(value, str) and bool(value.strip()) and len(value) <= 500
            if valid and kind == 'date':
                try:
                    valid = date.fromisoformat(value).isoformat() == value
                except ValueError:
                    valid = False
        if not valid:
            raise HTTPException(422, 'A filter value has the wrong type or is invalid.')
    if operator == 'between' and values[0] > values[1]:
        raise HTTPException(422, 'The lower bound must not exceed the upper bound.')


def _matching(con, binding, field, clause):
    table, predicate, params, value = binding
    usable = f'{value} IS NOT NULL'
    if field['kind'] == 'string':
        usable += f" AND trim({value}) <> ''"
    base = f'FROM {table} WHERE patient_id IS NOT NULL AND {predicate} AND {usable}'
    present = ({r[0] for r in con.execute(f'SELECT DISTINCT patient_id {base}', params).fetchall()}
               if clause.operator in ('is_missing', 'is_present', 'ne') else set())
    if clause.operator in ('is_missing', 'is_present'):
        return present
    op = clause.operator
    operator_sql = {'eq': '=', 'ne': '=', 'lt': '<', 'lte': '<=', 'gt': '>', 'gte': '>='}
    if op in operator_sql:
        comparison = f'{value} {operator_sql[op]} ?'
    elif op == 'between':
        comparison = f'{value} BETWEEN ? AND ?'
    elif op == 'in':
        comparison = f'{value} IN ({",".join("?" for _ in clause.values)})'
    else:
        comparison = f'contains(lower({value}), lower(?))'
    matched = {r[0] for r in con.execute(f'SELECT DISTINCT patient_id {base} AND ({comparison})', params + clause.values).fetchall()}
    return present - matched if op == 'ne' else matched


def _universe(con, root):
    patients = {r[0] for r in con.execute('SELECT patient_id FROM patients').fetchall()}
    rows, warnings = patient_overview.sample_inventory(root, include_imaging=True, include_clarids=False)
    if warnings:
        raise HTTPException(409, 'Patient coverage is incomplete. Resolve dataset linkage issues before using a missing-data filter.')
    patients.update(r['patient_id'] for r in rows)
    patients.update(r['individualId'] for r in patient_overview.biosample_records(root, include_clarids=False))
    from app.dicom import dicom_studies
    patients.update(r['patient_id'] for r in dicom_studies(root) if r.get('patient_id'))
    return patients


def _available(request, workspace):
    available = patient_overview.sources(request, workspace)
    if not available:
        raise HTTPException(409, 'Select at least one dataset.')
    return available


@router.get('/fields')
def fields(request: Request, workspace: str = Query(min_length=1, max_length=2000)):
    available = _available(request, workspace)
    try:
        fingerprint = _fingerprint(available, request_user_id(request))
        catalogue = _catalogue(available)
        if fingerprint != _fingerprint(available, request_user_id(request)):
            raise HTTPException(409, 'Dataset contents changed. Reload clinical filters.')
        return dict(fields=sorted(({k: v for k, v in field.items() if not k.startswith('_')}
            for field in catalogue.values()), key=lambda f: (f['label'].casefold(), f['unit'], f['id'])), fingerprint=fingerprint)
    except (OSError, ValueError, QueryStoreNotReadyError, duckdb.Error):
        raise HTTPException(409, 'Clinical filters require ready, valid dataset stores. Rebuild DuckDB if needed.') from None


@router.post('/evaluate')
def evaluate(body: FilterRequest, request: Request):
    available = _available(request, body.workspace)
    try:
        fingerprint = _fingerprint(available, request_user_id(request))
        if body.fingerprint != fingerprint:
            raise HTTPException(409, 'Dataset contents changed. Reload clinical filters.')
        catalogue = _catalogue(available)
        selected = []
        for clause in body.filters:
            field = catalogue.get(clause.field_id)
            if field is None:
                raise HTTPException(422, 'A selected field is no longer available in this workspace.')
            _validate(field, clause)
            selected.append((field, clause))
        members = []
        for dataset, root, _ in available:
            if any(dataset not in field['_bindings'] for field, _ in selected):
                continue  # A dataset without this field is not patient missingness.
            con = _connect(root)
            try:
                matches = None
                for field, clause in selected:
                    current = _matching(con, field['_bindings'][dataset], field, clause)
                    if clause.operator == 'is_missing':
                        current = _universe(con, root) - current
                    matches = current if matches is None else matches & current
                if matches is None:
                    matches = _universe(con, root)
                members.extend(dict(dataset_id=dataset, patient_id=pid) for pid in sorted(matches))
                if len(members) > MAX_MEMBERS:
                    raise HTTPException(422, 'Select at most 100,000 patients. Narrow the filters.')
            finally:
                con.close()
        if fingerprint != _fingerprint(available, request_user_id(request)):
            raise HTTPException(409, 'Dataset contents changed. Reload clinical filters.')
        description = '; '.join(f"{field['label']} {clause.operator} " + ', '.join(map(str, clause.values))
                                + (f" {field['unit']}" if field['unit'] else '')
                                + ' [' + ', '.join(field['dataset_labels']) + ']'
                                for field, clause in selected)
        return dict(members=members, patient_count=len(members), fingerprint=fingerprint,
                    description=(description or 'All patients') + '; recorded at any visit')
    except (OSError, ValueError, QueryStoreNotReadyError, duckdb.Error):
        raise HTTPException(409, 'Clinical filters require ready, valid dataset stores. Rebuild DuckDB if needed.') from None
