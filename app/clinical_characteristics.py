"""Descriptive patient summaries, kept separate by source dataset."""
import math

from app.cohort_filters import _catalogue
from app.query_store import _connect


def _distribution(values):
    """Bounded aggregate output; patient-level values never leave this helper."""
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [dict(low=low, high=high, count=len(values))]
    if not math.isfinite(high - low):
        return []
    size = min(20, math.ceil(math.sqrt(len(values))))
    width = (high - low) / size
    if not width:
        return []
    bins = [dict(low=low + i * width, high=low + (i + 1) * width, count=0)
            for i in range(size)]
    bins[-1]['high'] = high
    for value in values:
        index = min(size - 1, max(0, int((value - low) / width)))
        bins[index]['count'] += 1
    return bins


def characteristics(available, members=None):
    from app.bff import dashboard_summary
    from app.datasets import clinical_representation

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
                        quantile_cont(value, .75), list(value) FROM per_patient''', args).fetchone()
                    rows.append(dict(field_id=field['id'], label=field['label'], unit=field['unit'], kind='number',
                                     recorded=stats[0], missing=len(ids)-stats[0],
                                     median=stats[1], q1=stats[2], q3=stats[3],
                                     distribution=_distribution(stats[4])))
                elif field['kind'] in ('string', 'boolean'):
                    usable = f'{value} IS NOT NULL AND trim(CAST({value} AS VARCHAR)) <> \'\''
                    recorded = con.execute(f'SELECT count(DISTINCT patient_id) {base} AND {usable}', args).fetchone()[0]
                    categories = con.execute(f'''SELECT CAST({value} AS VARCHAR), count(DISTINCT patient_id) AS n
                        {base} AND {usable} GROUP BY 1 ORDER BY n DESC, 1 LIMIT 21''', args).fetchall()
                    rows.append(dict(label=field['label'], kind='category', recorded=recorded,
                        missing=len(ids)-recorded, truncated=len(categories)>20,
                        categories=[dict(label=v, count=n) for v,n in categories[:20]]))
            # Reuse the same chart definitions as the combined workspace, but
            # filter with source-local IDs so equal IDs in other datasets cannot leak in.
            source = dashboard_summary(root, patient_ids=ids)
            charts = {key: source[key] for key in (
                'totals', 'sex_counts', 'visit_distribution', 'disease_medication_matrix')}
            for key in ('top_diseases', 'top_medications'):
                charts[key] = [{k: v for k, v in item.items() if k != 'patients'}
                               for item in source[key]]
            charts['clinical_representation'] = clinical_representation(root)
            result.append(dict(dataset_id=identifier, label=label, patients=len(ids),
                               rows=rows, chart_summary=charts))
        finally:
            con.close()
    return result
