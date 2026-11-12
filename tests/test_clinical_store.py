"""Clinical ingestion tests: entirely fictional data, isolated stores."""
import gzip
import json
from datetime import date

import pytest

from app import bff, clinical_store, query_store
from app.identities import identity_key


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(query_store, 'list_registered_datasets', lambda: [])


def write_records(root, records):
    clinical = root / 'clinical'
    clinical.mkdir(parents=True, exist_ok=True)
    path = clinical / 'records.json'
    path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    return path


def rich_record():
    return {
        'id': 'P1:V2',
        'sex': {'id': 'NCIT:C16576', 'label': 'Female'},
        'diseases': [{'diseaseCode': {'id': 'TEST:D1', 'label': 'Condition'}, 'stage': {'id': 'TEST:S1', 'label': 'Mild'}}],
        'phenotypicFeatures': [
            {'featureType': {'id': 'TEST:F1', 'label': 'Feature'}, 'excluded': True},
            {'featureType': {'id': 'TEST:F2', 'label': 'Feature'}, 'excluded': False},
            {'featureType': {'id': 'TEST:F3', 'label': 'Other'}},
        ],
        'measures': [
            {'assayCode': {'id': 'TEST:M1', 'label': 'Marker'},
             'measurementValue': {'quantity': {'value': -1, 'unit': {'id': 'TEST:U1', 'label': 'mg/L'}}}},
            {'assayCode': {'id': 'TEST:M2', 'label': 'Marker'},
             'measurementValue': {'quantity': {'value': '0.25', 'unit': {'label': 'mmol/L'}}}},
            {'assayCode': {'id': 'TEST:M3', 'label': 'Categorical'},
             'measurementValue': {'ontologyTerm': {'id': 'TEST:NEG', 'label': 'Negative'}}},
        ],
        'treatments': [{'treatmentCode': {'id': 'TEST:T1', 'label': 'Drug'},
                        'doseIntervals': [{'quantity': {'value': 10, 'unit': {'label': 'mg'}}}]}],
        'interventionsOrProcedures': [{'procedureCode': {'id': 'TEST:P1', 'label': 'Procedure'}}],
        'exposures': [{'exposureCode': {'id': 'TEST:E1', 'label': 'Exposure'}, 'value': 0, 'unit': {'label': 'mg'}}],
        'info': {'visit_id': 'V2', 'event_date': '2025-02-01', 'days_from_baseline': 0,
                 'zero': 0, 'false': False, 'missing': None, 'blank': '', 'literal': 'NA',
                 'numeric_id': '001', 'negative': -1, 'date': '2025-01-01',
                 'invalid_date': '2025-02-30', 'duration': 'P40Y',
                 'empty_array': [], 'empty_object': {}, 'unicode': 'é雪',
                 'source_metadata': [{'field': 'x', 'value': 2}, {'field': 'y', 'value': 9}]},
    }


def test_complete_record_and_typed_values_preserve_source(tmp_path):
    root = tmp_path / 'study'
    raw = rich_record()
    source = write_records(root, [raw, {'info': {'unlinked': True}}])
    before = source.read_bytes()
    query_store.ensure_query_store(str(root))
    con = query_store._connect(str(root))
    try:
        rows = con.execute('SELECT record_json, source_file, record_index, patient_id FROM clinical_records ORDER BY record_id').fetchall()
        assert [json.loads(r[0]) for r in rows] == [raw, {'info': {'unlinked': True}}]
        assert rows[0][1:] == ('records.json', 0, 'P1')
        assert rows[1][3] is None  # Retained, not invented as a patient.
        assert con.execute('SELECT count(*) FROM patients').fetchone()[0] == 1
        values = {r[0]: r[1:] for r in con.execute('''SELECT value_path, value_type,
            text_value, number_value, boolean_value, date_value, value_json
            FROM clinical_values WHERE record_id=1''').fetchall()}
        assert values['/info/negative'][2] == -1
        assert values['/info/zero'][:4] == ('number', None, 0, None)
        assert values['/info/false'][:4] == ('boolean', None, None, False)
        assert values['/info/missing'][0] == 'null'
        assert '/info/not_present' not in values
        assert values['/info/literal'][:2] == ('string', 'NA')
        assert values['/info/numeric_id'][:3] == ('string', '001', None)
        assert values['/info/date'][4] == date(2025, 1, 1)
        assert values['/info/invalid_date'][4] is None
        assert values['/info/duration'][1] == 'P40Y'
        assert values['/info/blank'][1] == ''
        assert values['/info/empty_array'][0] == 'array'
        assert values['/info/empty_object'][0] == 'object'
        assert values['/info/unicode'][1] == 'é雪'
        assert values['/measures/0/measurementValue/quantity/value'][2] == -1
        observations = con.execute('''SELECT collection, code_id, excluded, number_value,
            value_code_id, unit_label FROM clinical_observations ORDER BY item_path''').fetchall()
        assert {r[0] for r in observations} == set(clinical_store.COLLECTION_CODES)
        by_code = {r[1]: r for r in observations}
        assert by_code['TEST:F1'][2] is True
        assert by_code['TEST:F2'][2] is False
        assert by_code['TEST:F3'][2] is None
        assert by_code['TEST:M1'][3:] == (-1, None, 'mg/L')
        assert by_code['TEST:M2'][3:] == (0.25, None, 'mmol/L')
        assert by_code['TEST:M3'][4] == 'TEST:NEG'
    finally:
        con.close()
    assert source.read_bytes() == before
    fields = clinical_store.field_inventory(str(root))
    entry = next(r for r in fields if r['field_path'] == '$."info"."source_metadata"[*]."value"')
    assert entry['patient_count'] == 1 and entry['value_count'] == 2
    assert not any('unlinked' in r['field_path'] for r in fields)


def test_array_paths_preserve_correlations_and_escape_keys(tmp_path):
    record = {'id': 'P1', 'info': {'a.b': 1, 'a': {'b': 2},
        'slash/~': [{'x': 3}, {'x': 4}], '*': 'literal'}}
    write_records(tmp_path, [record])
    query_store.ensure_query_store(str(tmp_path))
    con = query_store._connect(str(tmp_path))
    try:
        rows = con.execute('SELECT field_path, value_path, parent_path, number_value FROM clinical_values').fetchall()
        by_path = {r[1]: r for r in rows}
        assert by_path['/info/a.b'][0] != by_path['/info/a/b'][0]
        assert by_path['/info/slash~1~0/0/x'][0] == by_path['/info/slash~1~0/1/x'][0]
        assert by_path['/info/slash~1~0/0/x'][2] != by_path['/info/slash~1~0/1/x'][2]
        assert len({r[1] for r in rows}) == len(rows)
    finally:
        con.close()


def test_item_visits_do_not_inherit_unrelated_record_dates(tmp_path):
    record = {'id': 'P1:V1', 'info': {'event_date': '2025-01-01', 'days_from_baseline': 0},
              'measures': [{'value': 1}, {'value': 2, '_visitId': 'V2'},
                           {'value': 3, '_visit': {'id': 'V3', 'date': '2025-03-01', 'days_from_baseline': 59}},
                           {'value': 4, '_visit': {'date': '2025-04-01'}},
                           {'value': 5, '_visit': {'days_from_baseline': 10}}]}
    write_records(tmp_path, [record])
    query_store.ensure_query_store(str(tmp_path))
    con = query_store._connect(str(tmp_path))
    try:
        assert con.execute('''SELECT visit_id, event_date, days_from_baseline
            FROM clinical_observations ORDER BY item_path''').fetchall() == [
                ('V1', '2025-01-01', 0), ('V2', None, None), ('V3', '2025-03-01', 59),
                ('V1', '2025-04-01', None), ('V1', None, 10)]
    finally:
        con.close()


def test_multiple_datasets_keep_record_and_patient_identity(tmp_path, monkeypatch):
    paths = {}
    for dataset, unit in [('a', 'mg/L'), ('b', 'mmol/L')]:
        root = tmp_path / dataset
        record = rich_record()
        record['measures'][0]['measurementValue']['quantity']['unit'] = {'label': unit}
        write_records(root, [record, {'info': {'unlinked': True}}])
        db, meta, status = root / 'store.duckdb', root / 'meta.json', root / 'status.json'
        query_store._build_query_store(str(root), db, meta, {'dataset_id': dataset})
        paths[dataset] = db, meta, status
    monkeypatch.setattr(query_store, '_dataset_store_paths', paths.__getitem__)
    monkeypatch.setattr(query_store, '_store_ready_or_raise', lambda _: None)
    con = query_store._connect_workspace(['a', 'b'])
    try:
        rows = con.execute('SELECT dataset_id, record_id, patient_id, source_patient_id, record_json FROM clinical_records').fetchall()
        assert len(rows) == 4
        assert {r[2] for r in rows} == {None, *(identity_key(d, 'patient', 'P1') for d in paths)}
        assert {r[3] for r in rows} == {'P1', None}
        assert all(json.loads(r[4])['id'] == 'P1:V2' for r in rows if r[2])
        assert con.execute('''SELECT count(*) FROM clinical_observations o
            JOIN clinical_records r USING (dataset_id, record_id, patient_id)
            WHERE o.code_id='TEST:M1' ''').fetchone()[0] == 2
        assert {r[0] for r in con.execute("SELECT unit_label FROM clinical_observations WHERE code_id='TEST:M1'").fetchall()} == {'mg/L', 'mmol/L'}
    finally:
        con.close()


def test_compressed_bff_and_stale_schema_rebuild(tmp_path):
    root = tmp_path / 'study'
    root.mkdir()
    raw = rich_record()
    with gzip.open(root / 'records.json.gz', 'wt', encoding='utf-8') as handle:
        json.dump([raw], handle)
    query_store.ensure_query_store(str(root))
    db, meta = query_store._store_paths(str(root))
    assert query_store._store_has_required_tables(db)
    con = query_store._connect(str(root))
    con.execute('DROP TABLE clinical_values')
    con.close()
    assert not query_store._store_has_required_tables(db)
    query_store.ensure_query_store(str(root))
    assert query_store._store_has_required_tables(db)
    # A store from the prior version must rebuild even if all table names exist.
    old_signature = json.loads(meta.read_text())
    old_signature['schema_version'] -= 1
    meta.write_text(json.dumps(old_signature))
    query_store.ensure_query_store(str(root))
    assert json.loads(meta.read_text())['schema_version'] == query_store.QUERY_STORE_SCHEMA_VERSION
    assert clinical_store.patient_records_page(str(root), 'P1')['records'][0]['record'] == raw


def test_inspection_reads_prepared_records_not_source_bodies(tmp_path, monkeypatch):
    records = [{'id': f'P1:V{i}', 'info': {'days_from_baseline': i}, 'value': 0} for i in range(25)]
    # Same original id can occur in a different source file; do not overwrite it.
    write_records(tmp_path, records)
    (tmp_path / 'clinical/second.json').write_text(json.dumps([records[0]]))
    query_store.ensure_query_store(str(tmp_path))
    def no_read(*args):
        raise AssertionError('Patient inspection must not parse BFF files')
    monkeypatch.setattr(bff, 'read_bff_records', no_read)
    monkeypatch.setattr(query_store, 'read_bff_records', no_read)
    page = clinical_store.patient_records_page(str(tmp_path), 'P1')
    assert page['total'] == 26 and page['next_offset'] == 20
    assert [r['visit_id'] for r in page['records']][:4] == ['V0', 'V0', 'V1', 'V2']
    assert page['records'][0]['record'] == records[0]
    page = clinical_store.patient_records_page(str(tmp_path), 'P1', offset=20)
    assert len(page['records']) == 6 and page['next_offset'] is None
    assert clinical_store.patient_records_page(str(tmp_path), 'P1', visit_id='V10')['records'][0]['record'] == records[10]
    assert clinical_store.patient_records_page(str(tmp_path), 'P1', visit_id='absent')['records'] == []
    assert clinical_store.patient_records_page(str(tmp_path), "P1' OR TRUE --") is None


def test_registered_failed_rebuild_keeps_previous_store(tmp_path, monkeypatch):
    root = tmp_path / 'study'
    path = write_records(root, [rich_record()])
    monkeypatch.setattr(query_store, 'get_dataset', lambda _: {'root_path': str(root), 'name': 'Synthetic'})
    assert query_store.prepare_dataset_query_store('test')['ready']
    db, _, _ = query_store._dataset_store_paths('test')
    path.write_text('{invalid')
    with pytest.raises(json.JSONDecodeError):
        query_store.prepare_dataset_query_store('test')
    con = query_store.duckdb.connect(str(db), read_only=True)
    try:
        assert con.execute('SELECT count(*) FROM clinical_records').fetchone()[0] == 1
    finally:
        con.close()
    assert not query_store.dataset_query_store_status('test')['ready']
    assert not list(db.parent.glob('*.tmp.*'))


@pytest.mark.parametrize('value, expected', [(False, None), (0, 0), (-1, -1),
    ('-1', -1), ('NA', None), ('NaN', None), ('Infinity', None),
    ({'low': 1, 'high': 3}, None), (None, None)])
def test_measurements_do_not_invent_numeric_values(value, expected):
    measurement = clinical_store._measurement({'measurementValue': {'quantity': {'value': value}}})
    assert measurement[1] == expected
    if value is False:
        assert measurement[0] == 'boolean' and measurement[3] is False


def test_batched_ingestion_keeps_all_records_values_and_observations(tmp_path):
    raw = rich_record()
    count = 600
    records = [dict(raw, id=f'P{i}:V2') for i in range(count)]
    write_records(tmp_path, records)
    query_store.ensure_query_store(str(tmp_path))
    con = query_store._connect(str(tmp_path))
    try:
        assert con.execute('SELECT count(*) FROM clinical_records').fetchone()[0] == count
        assert con.execute('SELECT count(*) FROM clinical_values').fetchone()[0] == count * len(list(clinical_store.scalar_rows(raw)))
        assert con.execute('SELECT count(*) FROM clinical_observations').fetchone()[0] == count * 10
        assert con.execute('SELECT count(DISTINCT patient_id) FROM clinical_values').fetchone()[0] == count
    finally:
        con.close()
