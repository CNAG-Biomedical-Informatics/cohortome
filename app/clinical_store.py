"""Complete clinical records and typed search data in the prepared DuckDB store.

This is a storage index, not a policy for exposing fields to users or models.
Source values are never normalized away or harmonized by their display labels.
"""
import json
import math
import re
from datetime import date

from app.bff import relative_study_days


CLINICAL_TABLES = ('clinical_records', 'clinical_values', 'clinical_observations')
COLLECTION_CODES = {
    'diseases': 'diseaseCode',
    'phenotypicFeatures': 'featureType',
    'measures': 'assayCode',
    'treatments': 'treatmentCode',
    'interventionsOrProcedures': 'procedureCode',
    'exposures': 'exposureCode',
}


def create_tables(con):
    con.execute('''CREATE TABLE clinical_records (
        dataset_id VARCHAR NOT NULL, record_id BIGINT NOT NULL,
        patient_id VARCHAR, source_patient_id VARCHAR, original_id VARCHAR,
        visit_id VARCHAR, event_date VARCHAR, days_from_baseline DOUBLE,
        source_file VARCHAR NOT NULL, record_index INTEGER NOT NULL,
        record_json JSON NOT NULL,
        PRIMARY KEY (dataset_id, record_id),
        UNIQUE (dataset_id, source_file, record_index)
    )''')
    con.execute('''CREATE TABLE clinical_values (
        dataset_id VARCHAR NOT NULL, record_id BIGINT NOT NULL, patient_id VARCHAR,
        field_path VARCHAR NOT NULL, value_path VARCHAR NOT NULL,
        parent_path VARCHAR NOT NULL, value_type VARCHAR NOT NULL,
        text_value VARCHAR, number_value DOUBLE, boolean_value BOOLEAN,
        date_value DATE, value_json JSON NOT NULL
    )''')
    con.execute('''CREATE TABLE clinical_observations (
        dataset_id VARCHAR NOT NULL, record_id BIGINT NOT NULL, patient_id VARCHAR,
        collection VARCHAR NOT NULL, item_path VARCHAR NOT NULL,
        code_id VARCHAR, code_label VARCHAR, excluded BOOLEAN,
        visit_id VARCHAR, event_date VARCHAR, days_from_baseline DOUBLE,
        value_type VARCHAR, number_value DOUBLE, text_value VARCHAR,
        boolean_value BOOLEAN, value_code_id VARCHAR, value_code_label VARCHAR,
        unit_id VARCHAR, unit_label VARCHAR
    )''')


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _pointer_part(key):
    return key.replace('~', '~0').replace('/', '~1')


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _typed_value(value):
    # Do not use bff.normalize_value here: -1 and "NA" may be real values,
    # while false, zero, null, empty strings and absent fields are distinct.
    if value is None:
        return 'null', None, None, None, None
    if isinstance(value, bool):
        return 'boolean', None, None, value, None
    if isinstance(value, (int, float)):
        return 'number', None, _number(value), None, None
    if isinstance(value, str):
        parsed_date = None
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError:
                pass
        return 'string', value, None, None, parsed_date
    return ('array' if isinstance(value, list) else 'object'), None, None, None, None


def scalar_rows(value, field_path='$', value_path='', parent_path=''):
    """Index leaves and explicit empty containers, keeping array boundaries.

    field_path is a JSONPath with wildcard array indices; value_path and
    parent_path are exact JSON Pointers. Quoted keys avoid confusing a key
    containing a dot, slash or bracket with a nested/array path.
    """
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from scalar_rows(child, f'{field_path}.{_json(key)}',
                                   f'{value_path}/{_pointer_part(key)}', value_path)
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from scalar_rows(child, f'{field_path}[*]', f'{value_path}/{index}', value_path)
    else:
        yield (field_path, value_path, parent_path, *_typed_value(value), _json(value))


def _term(value):
    if not isinstance(value, dict):
        return None, None
    return tuple(value.get(key) if isinstance(value.get(key), str) else None for key in ('id', 'label'))


def _measurement(item):
    """Read a BFF quantity, categorical value or supported simple value.

    Numeric strings in a declared measurement can be queried numerically;
    clinical_values still retains their source string type. Complex/range
    values stay in the record and scalar index, never reduced to a point.
    """
    measured = item.get('measurementValue')
    if isinstance(measured, dict) and isinstance(measured.get('quantity'), dict):
        quantity = measured['quantity']
        value, unit = quantity.get('value'), quantity.get('unit')
    elif isinstance(measured, dict) and 'value' in measured:
        value, unit = measured['value'], measured.get('unit')
    elif isinstance(measured, dict) and isinstance(measured.get('ontologyTerm'), dict):
        value, unit = measured['ontologyTerm'], None
    elif 'value' in item:
        value, unit = item['value'], item.get('unit')
    else:
        value, unit = measured, None
    kind, text, number, boolean, _ = _typed_value(value)
    code_id, code_label = _term(value)
    if code_id or code_label:
        kind = 'ontology'
    if kind == 'string':
        number = _number(value)
    return kind, number, text, boolean, code_id, code_label, *_term(unit)


def observation_rows(record, visit):
    for collection, code_key in COLLECTION_CODES.items():
        items = record.get(collection)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            code_id, code_label = _term(item.get(code_key))
            item_visit = item.get('_visit') if isinstance(item.get('_visit'), dict) else {}
            explicit_visit = item.get('_visitId', item_visit.get('id'))
            if not isinstance(explicit_visit, str):
                explicit_visit = None
            visit_id = explicit_visit or (visit.visit_id if visit else None)
            same_visit = visit is not None and (not explicit_visit or explicit_visit == visit.visit_id)
            event_date = item_visit.get('event_date', item_visit.get('date'))
            if not isinstance(event_date, str):
                event_date = None
            days = relative_study_days(item_visit)
            # An item-local date/offset must not acquire the other half from a
            # different time point on its enclosing record.
            if event_date is None and days is None and same_visit:
                event_date = visit.event_date
                info = record.get('info')
                days = relative_study_days(info) if isinstance(info, dict) else None
            excluded = item.get('excluded')
            if not isinstance(excluded, bool):
                excluded = None  # Missing is not an asserted negative/positive.
            measurement = _measurement(item) if collection in {'measures', 'exposures'} else (None,) * 8
            yield (collection, f'/{collection}/{index}', code_id, code_label, excluded,
                   visit_id, event_date, days, *measurement)


def _insert_rows(con, table, rows):
    if rows:
        # Vectorized insertion without a new pandas/Arrow dependency or a
        # transaction/SQL call per leaf. Table names are internal constants.
        columns = [list(column) for column in zip(*rows)]
        con.execute(f'INSERT INTO {table} SELECT ' + ', '.join('unnest(?)' for _ in columns), columns)
        rows.clear()


class ClinicalStoreWriter:
    """Bounded batches; built in the same temporary database as existing tables."""
    def __init__(self, con, dataset_id=''):
        self.con = con
        self.dataset_id = dataset_id
        self.record_id = 0
        self.records, self.values, self.observations = [], [], []
        create_tables(con)

    def add(self, source_file, record_index, record, patient_id, visit):
        self.record_id += 1
        prefix = (self.dataset_id, self.record_id, patient_id)
        info = record.get('info')
        original_id = record.get('id')
        self.records.append((*prefix, patient_id,
            str(original_id) if original_id is not None else None,
            visit.visit_id if visit else None, visit.event_date if visit else None,
            relative_study_days(info) if isinstance(info, dict) else None,
            source_file, record_index, _json(record)))
        for row in scalar_rows(record):
            self.values.append((*prefix, *row))
            if len(self.values) >= 4096:
                _insert_rows(self.con, 'clinical_values', self.values)
        for row in observation_rows(record, visit):
            self.observations.append((*prefix, *row))
            if len(self.observations) >= 4096:
                _insert_rows(self.con, 'clinical_observations', self.observations)
        if len(self.records) >= 256:
            self.flush()

    def flush(self):
        for table, rows in zip(CLINICAL_TABLES, (self.records, self.values, self.observations)):
            _insert_rows(self.con, table, rows)

    def finish(self):
        self.flush()
        self.con.execute('CREATE INDEX idx_clinical_records_patient ON clinical_records(patient_id)')
        self.con.execute('CREATE INDEX idx_clinical_values_record ON clinical_values(record_id)')
        self.con.execute('CREATE INDEX idx_clinical_values_field ON clinical_values(field_path)')
        self.con.execute('CREATE INDEX idx_clinical_observations_code ON clinical_observations(collection, code_id)')


def field_inventory(data_dir):
    """Internal field discovery, per dataset/type; not an unrestricted API.

    Counts include only linked patients. No sampled values, paths on disk or
    source records are returned, and no cross-dataset harmonization is implied.
    Callers must enforce authorization before using this inventory.
    """
    from app.query_store import _connect, ensure_query_store
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute('''SELECT dataset_id, field_path, value_type,
            count(DISTINCT patient_id), count(*)
            FROM clinical_values WHERE patient_id IS NOT NULL
            GROUP BY dataset_id, field_path, value_type
            ORDER BY dataset_id, field_path, value_type''').fetchall()
    finally:
        con.close()
    return [dict(dataset_id=r[0], field_path=r[1], value_type=r[2],
                 patient_count=r[3], value_count=r[4]) for r in rows]


def patient_records_page(data_dir, patient_id, *, visit_id='', offset=0, limit=20):
    """Inspect a source patient's complete records without parsing the cohort.

    Use after dataset authorization. Visit ordering matches the Timeline UI;
    only record keys for this patient are sorted, and only the requested page
    of JSON is loaded. Dataset-qualified execution IDs work in merged stores.
    """
    from app.query_store import _connect, ensure_query_store
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        keys = con.execute('''SELECT dataset_id, record_id, visit_id, original_id
            FROM clinical_records WHERE patient_id = ?''', [patient_id]).fetchall()
        if not keys:
            return None
        keys = [r for r in keys if not visit_id or r[2] == visit_id]
        keys.sort(key=lambda r: (not bool(r[2]),
            [(1, int(p)) if p.isdigit() else (0, p.casefold()) for p in re.split(r'(\d+)', r[2] or '')],
            r[3] or '', r[0], r[1]))
        page = keys[offset:offset + limit]
        records = []
        if page:
            rows = con.execute('''SELECT r.dataset_id, r.record_id, r.visit_id, r.event_date,
                r.days_from_baseline, r.record_json
                FROM clinical_records r JOIN (
                    SELECT unnest(?) AS dataset_id, unnest(?) AS record_id
                ) selected USING (dataset_id, record_id)''',
                [[r[0] for r in page], [r[1] for r in page]]).fetchall()
            by_key = {(r[0], r[1]): dict(visit_id=r[2], event_date=r[3], days_from_baseline=r[4],
                                        record=json.loads(r[5])) for r in rows}
            records = [by_key[(r[0], r[1])] for r in page]
        return dict(records=records, total=len(keys),
                    next_offset=offset + limit if offset + limit < len(keys) else None)
    finally:
        con.close()
