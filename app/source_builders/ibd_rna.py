"""Prepare a local GSE191328 package from the original public GEO inputs."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

import numpy as np
import pandas as pd

from app.source_builders.common import write_json
from app.source_builders.common import encode_subjects
from app.geo_gse85034 import metadata, codebook_path
from app.preparation_tools import preparation_command

# Exact preferred labels checked in Convert-Pheno's bundled NCIT vocabulary.
DIAGNOSES = {'CD': ('NCIT:C2965', 'Crohn Disease'),
             'UC': ('NCIT:C2952', 'Ulcerative Colitis')}
TREATMENTS = {'Adalimumab': 'NCIT:C65216', 'Infliximab': 'NCIT:C1789',
              'Vedolizumab': 'NCIT:C95798'}


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def clinical_and_samples(metadata):
    """Keep source identity, relative timing and future outcome explicitly separate."""
    clinical, samples = [], []
    if metadata.sample_id.duplicated().any():
        raise ValueError('Duplicate GEO sample identifier')
    if metadata.duplicated(['patient_id', 'time point']).any():
        raise ValueError('Duplicate patient/timepoint')
    for field in ['treatment', 'remission at week 14', 'diagnosis']:
        if metadata.groupby('patient_id')[field].nunique().gt(1).any():
            raise ValueError('Inconsistent patient-level source metadata: ' + field)
    for row in metadata.to_dict('records'):
        if row['diagnosis'] not in DIAGNOSES:
            raise ValueError('Unknown source diagnosis')
        if row['treatment'] not in TREATMENTS:
            raise ValueError('Unknown source treatment')
        # Escape each component: no collisions and no colon inside patient IDs.
        patient = 'GSE191328-' + quote(row['cohort'], safe='') + ':' + quote(row['patient'], safe='')
        patient = patient.replace(':', '~')
        sample = patient + ':' + row['sample_id']
        clinical.append({
            'id': sample, 'patient_id': patient,
            'info': {'visit_id': row['time point'],
                     'source_accession': row['sample_id'], 'source_patient_id': row['patient'],
                     'study_cohort': row['cohort'], 'timepoint': row['time point'],
                     'days_from_baseline': row['time'],
                     'remission_at_week_14': row['remission at week 14'],
                     'source_metadata': {k: str(v) for k, v in row.items() if k not in {'patient_id', 'disease', 'time'}}}})
        samples.append({'sample_id': sample, 'patient_id': patient,
                        'source_sample_id': row['sample_id'], 'source_patient_id': row['patient'],
                        'study_cohort': row['cohort'], 'diagnosis': row['diagnosis'],
                        'treatment': row['treatment'], 'timepoint': row['time point'],
                        'visit_id': row['time point'],
                        'days_from_baseline': row['time'],
                        'remission_at_week_14': row['remission at week 14']})
    if len({r['sample_id'] for r in samples}) != len(samples):
        raise ValueError('Mapped sample identity collision')
    if len({r['patient_id'] for r in samples}) != metadata.patient_id.nunique():
        raise ValueError('Mapped patient identity collision')
    return clinical, samples


def merge_converted(clinical, converted):
    """Copy only mapped terms; discard converter placeholders, not source facts."""
    mapped = {r['id']: r for r in converted}
    if len(mapped) != len(converted) or set(mapped) != {r['id'] for r in clinical}:
        raise ValueError('Conversion dropped or duplicated snapshot identities')
    for record in clinical:
        source = record['info']['source_metadata']
        result = mapped[record['id']]
        diseases = result.get('diseases', [])
        treatments = result.get('treatments', [])
        if (len(diseases) != 1 or len(treatments) != 1
                or diseases[0]['diseaseCode']['id'] != DIAGNOSES[source['diagnosis']][0]
                or treatments[0]['treatmentCode']['id'] != TREATMENTS[source['treatment']]):
            raise ValueError('Converted ontology terms do not match reviewed source mapping')
        record['diseases'] = [{'diseaseCode': diseases[0]['diseaseCode']}]
        record['treatments'] = [{
            'treatmentCode': treatments[0]['treatmentCode'],
            '_info': {'interpretation': 'Study treatment group, not a dated administration'}}]


def convert_clinical(clinical, converter, mapping, directory):
    source = directory / 'clinical.csv'
    with source.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['snapshot_id', 'patient_id', 'diagnosis', 'treatment', 'sex'])
        writer.writeheader()
        for record in clinical:
            original = record['info']['source_metadata']
            writer.writerow(dict(snapshot_id=record['id'], patient_id=record['patient_id'],
                                 diagnosis=original['diagnosis'], treatment=original['treatment'],
                                 sex='Not Reported'))
    with (directory / 'converter.log').open('w') as log:
        subprocess.run([*converter, '-icsv', str(source), '--separator', ',',
                        '--mapping-file', str(mapping), '--search', 'exact',
                        '--no-source-info', '--term-audit', str(directory / 'terminology.tsv'),
                        '-obff', str(directory / 'converted.json')],
                       check=True, stdout=log, stderr=log, timeout=300)
    merge_converted(clinical, json.loads((directory / 'converted.json').read_text()))
    return {'converter_version': subprocess.check_output([*converter, '--version'], text=True, timeout=30).strip(),
            'mapping_sha256': sha256(mapping), 'snapshots': len(clinical),
            'diagnoses': len(clinical), 'treatment_groups': len(clinical),
            'missing': 'No age, sex, dates, doses or remission measurements inferred',
            'placeholders': 'Only mapped diseaseCode and treatmentCode retained from converter'}


def subject_rows(samples, previous=()):
    numbers = {r['unique_id']: int(r['subject_id']) for r in previous}
    if len(set(numbers.values())) != len(numbers) or any(n < 1 for n in numbers.values()):
        raise ValueError('Invalid previous subject-number mapping')
    patients = {s['patient_id']: s for s in samples}
    next_id = max(numbers.values(), default=0) + 1
    for pid in sorted(patients):
        if pid not in numbers:
            numbers[pid] = next_id
            next_id += 1
    return [dict(unique_id=pid, subject_id=numbers[pid], study='GSE191328',
                 type='Case', condition={'CD': 'K50.9', 'UC': 'K51.9'}[s['diagnosis']],
                 sex='Not Available', age_group='Not Available')
            for pid, s in sorted(patients.items())]


def prepare(source, package, check_cancel, report):
    meta = pd.DataFrame(metadata(source / 'ed-GSE191328_series_matrix.txt.gz',
        required={'sample_id', 'cohort', 'patient', 'diagnosis', 'treatment', 'time point', 'remission at week 14'}))
    times = {'baseline': 0., '4h': 4/24, '24h': 1., '72h': 3., '2w': 14., '6w': 42., '14w': 98.}
    meta['patient_id'] = meta['cohort'] + ':' + meta['patient']
    meta['time'] = meta['time point'].map(times)
    if meta.time.isna().any():
        raise ValueError('Unrecognized RNA-seq visit timing')
    records, samples = clinical_and_samples(meta)
    for folder in ('clinical', 'assays', 'provenance'):
        (package / folder).mkdir(parents=True)
    report(message='Mapping IBD clinical records with Convert-Pheno…')
    mapping = Path(__file__).with_suffix('.yaml')
    audit = convert_clinical(records, preparation_command('convert-pheno'), mapping, package / 'provenance')
    (package / 'provenance/converted.json').unlink()
    (package / 'provenance/converter.log').unlink()
    shutil.copyfile(mapping, package / 'provenance/clinical.yaml')
    write_json(package / 'provenance/mapping-audit.json', audit)
    write_json(package / 'clinical/records.json', records)
    report(message='Assembling published featureCounts by sample identifier…')
    columns, genes = {}, None
    wanted = set(meta.sample_id)
    for path in sorted(source.glob('*.featureCounts.txt.gz')):
        check_cancel()
        sample = path.name.split('_')[0]
        if sample not in wanted or sample in columns:
            raise ValueError('Unexpected or duplicate count sample')
        with gzip.open(path, 'rt') as handle:
            frame = pd.read_csv(handle, sep='\t', comment='#', usecols=[0, 6], index_col=0)
        if frame.index.duplicated().any() or (genes is not None and not genes.equals(frame.index)):
            raise ValueError('Count gene coordinates differ')
        genes = frame.index
        values = frame.iloc[:, 0].to_numpy(dtype=float)
        if (not np.isfinite(values).all() or (values < 0).any() or (values >= 2**63).any()
                or (values != np.floor(values)).any() or values.sum() <= 0):
            raise ValueError('Invalid integer counts')
        columns[sample] = values.astype(np.int64)
    if set(columns) != wanted or genes is None or not all(re.fullmatch(r'ENSG[0-9]+(?:\.[0-9]+)?', g) for g in genes):
        raise ValueError('Count sample/feature coverage differs')
    matrix = np.vstack([columns[s['source_sample_id']] for s in samples])
    from app.geo_gse85034 import write_csv
    write_csv(package / 'assays/samples.tsv', samples, '\t')
    with (package / 'assays/counts.csv').open('w', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['gene_id'] + [s['sample_id'] for s in samples])
        for gene, values in zip(genes, matrix.T):
            check_cancel()
            writer.writerow([gene] + values.tolist())
    subjects = subject_rows(samples)
    if (len(subjects), len(records), len(genes)) != (53, 201, 58051):
        raise ValueError('GSE191328 counts differ from reviewed recipe')
    report(message='Generating subject ClarIDs…')
    encode_subjects(subjects, package / 'identifiers', preparation_command('clarid-tools'), codebook_path(), 'GSE191328', 'G191')
    write_json(package / 'manifest.json', dict(schema_version=1, name='GSE191328 longitudinal IBD blood RNA-seq',
        study_design='longitudinal', clinical={'representation': 'snapshot'},
        identifiers={'clarid_subjects': dict(entity='subject', file='identifiers/clarid_subjects.csv', delimiter=',',
            codebook_version='0.04', tools_version='0.04')}))
    write_json(package / 'assays/manifest.json', {'version': 1, 'assays': [dict(
        assay_id='gse191328_transcriptomics', label='Whole-blood RNA-seq gene counts', modality='transcriptomics',
        data_type='raw_counts', level='sample', feature_namespace='ensembl_gene_id', feature_id_column='gene_id',
        sample_id_column='matrix_columns', patient_id_column='patient_id', patient_linkage='sample_metadata_file',
        sample_metadata_file='assays/samples.tsv', file='assays/counts.csv', feature_count=len(genes))]})
    (package / 'README.md').write_text(
        '# GSE191328\n\nSource: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE191328\n\n'
        'All 53 patients and 201 samples retained. Original featureCounts assembled by sample and gene ID '
        'without normalization or filtering. Clinical diagnoses/treatment groups mapped with Convert-Pheno. '
        'Relative time is retained; no demographics, calendar dates or doses inferred. '
        'Week-14 remission is a future endpoint, not a repeated visit measurement. '
        'Repeated samples must not be treated as independent patients.\n\n'
        'Downloaded directly from GEO. Review study conditions and https://www.ncbi.nlm.nih.gov/geo/info/disclaimer.html '
        'before use or redistribution; cite the original study.\n', encoding='utf-8')
    return dict(patients=53, snapshots=201, samples=201, features=58051)
