"""Convert public IBDMDB products without normalizing or joining distinct visits."""
import gzip
import json
from urllib.parse import quote

import numpy as np
import pandas as pd

from app.source_builders.common import write_json

FILES = {'metadata': 'ibdmdb-metadata.csv', 'metabolomics': 'ibdmdb-metabolomics.biom.gz',
         'proteomics': 'ibdmdb-proteomics.tsv.gz', 'serology': 'ibdmdb-serology.tsv'}
SEROLOGY = ['IgA ASCA EU', 'IgG ASCA EU', 'OmpC. EU', 'Cbir1 EU', 'ANCA EU']
# Exact reviewed source column, not a general "drop unmatched" rule.
UNLINKED_SEROLOGY = {'220948'}
DIAGNOSES = {'CD': 'Crohn disease', 'UC': 'Ulcerative colitis', 'nonIBD': 'Non-IBD comparison group'}


def biom_matrix(payload):
    rows, cols = payload['rows'], payload['columns']
    shape = (len(rows), len(cols))
    if (list(shape) != payload['shape'] or payload['matrix_type'] != 'sparse'
            or len({r['id'] for r in rows}) != len(rows)
            or len({c['id'] for c in cols}) != len(cols)):
        raise ValueError('Invalid or unsupported BIOM dimensions/identifiers')
    matrix = np.zeros(shape, dtype=np.float64)
    seen = np.zeros(shape, dtype=bool)
    for r, c, value in payload['data']:
        if not isinstance(r, int) or not isinstance(c, int) or not (0 <= r < shape[0] and 0 <= c < shape[1]):
            raise ValueError('Invalid BIOM coordinate')
        if seen[r, c]:
            raise ValueError('Duplicate BIOM coordinate')
        seen[r, c] = True
        matrix[r, c] = np.nan if value is None else float(value)
    if np.isinf(matrix).any():
        raise ValueError('Infinite BIOM value')
    # BIOM 1.0 sparse entries omitted from data are zero, not missing.
    return pd.DataFrame(matrix, index=[r['id'] for r in rows], columns=[c['id'] for c in cols])


def link_samples(meta, modality, columns):
    rows = meta[meta.data_type == modality].copy()
    if rows['External ID'].duplicated().any() or len(set(columns)) != len(columns):
        raise ValueError('Duplicate sample identity')
    unknown = set(columns) - set(rows['External ID'])
    if unknown and (modality != 'serology' or unknown != UNLINKED_SEROLOGY):
        raise ValueError('Unexpected unlinked sample; review source metadata')
    rows = rows.set_index('External ID')
    samples = []
    for column in columns:
        if column in unknown:
            continue
        row = rows.loc[column]
        if not row['Participant ID'] or row['diagnosis'] not in DIAGNOSES:
            raise ValueError('Missing participant or unexpected diagnosis')
        week = float(row.week_num)
        if not np.isfinite(week):
            raise ValueError('Missing/nonfinite relative time')
        patient = 'IBDMDB-' + quote(row['Participant ID'], safe='')
        samples.append({'sample_id': patient + ':' + quote(column, safe=''),
            'patient_id': patient, 'source_sample_id': column,
            'source_participant_id': row['Participant ID'], 'diagnosis': row.diagnosis,
            'timepoint': 'week_' + format(week, 'g'), 'week_from_baseline': week,
            'days_from_baseline': week * 7, 'source_visit_num': row.visit_num,
            'specimen_type': 'serum' if modality == 'serology' else 'stool'})
    return samples, sorted(unknown)


def prepare(source, package, clinical_records):
    meta = pd.read_csv(source / FILES['metadata'], dtype=str, keep_default_na=False)
    records, assays, counts, exclusions = {}, [], {}, []
    enriched = json.loads(clinical_records.read_text())
    snapshot_links = {}
    if enriched is not None:
        for record in enriched:
            for source_sample in record['info']['source_sample_ids']:
                key = (record['patient_id'], source_sample)
                if key in snapshot_links:
                    raise ValueError('Source sample links to multiple clinical snapshots')
                snapshot_links[key] = record['info']['visit_id']
    (package / 'clinical').mkdir(parents=True)
    (package / 'assays').mkdir()
    for modality in ('metabolomics', 'proteomics', 'serology'):
        annotation = None
        if modality == 'metabolomics':
            with gzip.open(source / FILES[modality], 'rt') as handle:
                payload = json.load(handle)
            frame = biom_matrix(payload)
            annotation = [{'feature_id': r['id'], **(r.get('metadata') or {})} for r in payload['rows']]
            del payload
        else:
            frame = pd.read_csv(source / FILES[modality], sep='\t', index_col=0)
            if modality == 'serology':
                # Preserve administrative/categorical annotations separately.
                frame.to_csv(package / 'assays/serology_source.tsv', sep='\t', index_label='source_row')
                frame = frame.loc[SEROLOGY].apply(pd.to_numeric, errors='raise')
        if frame.index.has_duplicates or frame.empty:
            raise ValueError('Duplicate/empty feature table')
        numeric = frame.to_numpy(dtype=float)
        if np.isinf(numeric).any():
            raise ValueError('Infinite matrix value')
        samples, unknown = link_samples(meta, modality, list(frame.columns))
        if enriched is not None:
            for sample in samples:
                sample['visit_id'] = snapshot_links[(sample['patient_id'], sample['source_sample_id'])]
        exclusions.extend({'modality': modality, 'source_sample_id': sample,
                           'reason': 'No exact match in published modality metadata'} for sample in unknown)
        frame = frame.loc[:, [s['source_sample_id'] for s in samples]]
        frame.columns = [s['sample_id'] for s in samples]
        frame.index = frame.index.map(str)
        frame.to_csv(package / f'assays/{modality}.csv', index_label='feature_id', na_rep='NA')
        pd.DataFrame(samples).to_csv(package / f'assays/{modality}_samples.tsv', sep='\t', index=False)
        if annotation:
            pd.DataFrame(annotation).to_csv(package / 'assays/metabolomics_features.tsv', sep='\t', index=False)
        for sample in samples:
            key = sample['sample_id']
            info = {k: sample[k] for k in ['source_sample_id', 'source_participant_id',
                'week_from_baseline', 'days_from_baseline', 'source_visit_num', 'specimen_type']}
            record = {'id': key, 'patient_id': sample['patient_id'],
                'info': {**info, 'visit_id': sample['source_sample_id'],
                         'study_group': DIAGNOSES[sample['diagnosis']]}}
            if key in records and records[key] != record:
                raise ValueError('Conflicting metadata for shared specimen')
            records[key] = record
        assays.append({'assay_id': 'ibdmdb_' + modality, 'label': {
            'metabolomics': 'Stool metabolite features (published values)',
            'proteomics': 'Stool metaproteomics (published values)',
            'serology': 'Serum antibody assays (ELISA units)'}[modality],
            'modality': modality, 'data_type': 'elisa_units' if modality == 'serology' else 'published_abundance',
            'level': 'sample', 'feature_namespace': 'ibdmdb_' + modality + '_feature',
            'feature_id_column': 'feature_id', 'sample_id_column': 'matrix_columns',
            'patient_id_column': 'patient_id', 'patient_linkage': 'sample_metadata_file',
            'sample_metadata_file': f'assays/{modality}_samples.tsv',
            'file': f'assays/{modality}.csv', 'feature_count': len(frame)})
        counts[modality] = {'samples': len(samples), 'features': len(frame),
                           'missing_values': int(frame.isna().sum().sum())}
        del frame, numeric
    patients = {}
    for record in records.values():
        group = record['info']['study_group']
        if record['patient_id'] in patients and patients[record['patient_id']] != group:
            raise ValueError('Conflicting patient diagnosis across specimens')
        patients[record['patient_id']] = group
    if enriched is not None:
        linked = {(record['patient_id'], record['info']['source_sample_id']) for record in records.values()}
        if set(snapshot_links) != linked:
            raise ValueError('Enriched clinical sample links differ from packaged assay samples')
        records = {record['id']: record for record in enriched}
        if len(records) != len(enriched):
            raise ValueError('Duplicate enriched clinical record IDs')
    write_json(package / 'clinical/records.json', list(records.values()))
    write_json(package / 'manifest.json', {'schema_version': 1,
        'name': 'IBDMDB processed stool and serum multi-omics', 'study_design': 'longitudinal',
        'clinical': {'representation': 'snapshot'}})
    write_json(package / 'assays/manifest.json', {'version': 1, 'assays': assays})
    write_json(package / 'exclusions.json', exclusions)
    return counts
