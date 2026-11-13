"""Descriptive patient summaries, kept separate by source dataset."""
from app.cohort_filters import _catalogue
from app.query_store import _connect


def characteristics(available, members=None):
    result = []
    for identifier, root, label in available:
        fields = _catalogue([(identifier, root, label)])
        con = _connect(root)
        try:
            ids = [row[0] for row in con.execute('SELECT patient_id FROM patients').fetchall()]
            if members is not None:
                allowed = {m['patient_id'] for m in members if m['dataset_id'] == identifier}
                ids = [pid for pid in ids if pid in allowed]
            rows = []
            for field in fields.values():
                table, predicate, params, value = field['_bindings'][identifier]
                base = f'FROM {table} WHERE ({predicate}) AND patient_id IN (SELECT unnest(?))'
                args = params + [ids]
                if field['kind'] == 'number':
                    stats = con.execute(f'''WITH per_patient AS (
                        SELECT patient_id, median({value}) AS value {base}
                        AND isfinite({value}) GROUP BY patient_id)
                        SELECT count(*), quantile_cont(value, .5), quantile_cont(value, .25),
                        quantile_cont(value, .75) FROM per_patient''', args).fetchone()
                    rows.append(dict(label=field['label'], unit=field['unit'], kind='number',
                                     recorded=stats[0], missing=len(ids)-stats[0],
                                     median=stats[1], q1=stats[2], q3=stats[3]))
                elif field['kind'] in ('string', 'boolean'):
                    usable = f'{value} IS NOT NULL AND trim(CAST({value} AS VARCHAR)) <> \'\''
                    recorded = con.execute(f'SELECT count(DISTINCT patient_id) {base} AND {usable}', args).fetchone()[0]
                    categories = con.execute(f'''SELECT CAST({value} AS VARCHAR), count(DISTINCT patient_id) AS n
                        {base} AND {usable} GROUP BY 1 ORDER BY n DESC, 1 LIMIT 21''', args).fetchall()
                    rows.append(dict(label=field['label'], kind='category', recorded=recorded,
                        missing=len(ids)-recorded, truncated=len(categories)>20,
                        categories=[dict(label=v, count=n) for v,n in categories[:20]]))
            result.append(dict(dataset_id=identifier, label=label, patients=len(ids), rows=rows))
        finally:
            con.close()
    return result
