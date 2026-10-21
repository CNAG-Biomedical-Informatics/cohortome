"""Package both GSE42296 disease groups from the ED-Omics public-data export."""
import argparse
import csv
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
from app.source_builders.common import sha256
from app.source_builders.common import encode_subjects
from app.geo_gse85034 import metadata, codebook_path
from app.preparation_tools import preparation_command
import gzip

DIAGNOSES = {"Crohn's disease": 'NCIT:C2965', 'Rheumatoid arthritis': 'NCIT:C2884'}


def merge_converted(records, converted):
    mapped = {r['id']: r for r in converted}
    if len(mapped) != len(converted) or set(mapped) != {r['id'] for r in records}:
        raise ValueError('Conversion dropped or duplicated snapshot identities')
    for record in records:
        source = record['info']['source_metadata']
        result = mapped[record['id']]
        diseases, treatments = result.get('diseases', []), result.get('treatments', [])
        expected_treatments = 0 if source['time'] == 'week 0' else 1
        if (len(diseases) != 1 or
                diseases[0]['diseaseCode']['id'] != DIAGNOSES[source['disease state']] or
                len(treatments) != expected_treatments or
                any(t['treatmentCode']['id'] != 'NCIT:C1789' for t in treatments)):
            raise ValueError('Converted terms do not match reviewed source mapping')
        record['diseases'] = [{'diseaseCode': diseases[0]['diseaseCode']}]
        record['treatments'] = [
            {'treatmentCode': t['treatmentCode'],
             '_info': {'interpretation': 'Source treatment status; no dose or administration date supplied'}}
            for t in treatments]


def convert_clinical(records, converter, mapping, directory):
    source = directory / 'clinical.csv'
    with source.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['snapshot_id', 'patient_id', 'diagnosis', 'treatment', 'sex'])
        writer.writeheader()
        for record in records:
            row = record['info']['source_metadata']
            writer.writerow(dict(snapshot_id=record['id'], patient_id=record['patient_id'],
                                 diagnosis=row['disease state'], treatment=row['treatment'],
                                 sex='Not Reported'))
    with (directory / 'converter.log').open('w') as log:
        subprocess.run([*converter, '-icsv', str(source), '--separator', ',',
                        '--mapping-file', str(mapping), '--search', 'exact', '--no-source-info',
                        '--term-audit', str(directory / 'terminology.tsv'),
                        '-obff', str(directory / 'converted.json')],
                       check=True, stdout=log, stderr=log, timeout=300)
    merge_converted(records, json.loads((directory / 'converted.json').read_text()))
    return {'converter_version': subprocess.check_output([*converter, '--version'], text=True, timeout=30).strip(),
            'mapping_sha256': sha256(mapping), 'snapshots': len(records),
            'diagnoses': len(records), 'treatment_records': sum(len(r['treatments']) for r in records),
            'placeholders': 'Only mapped diseaseCode/treatmentCode retained; temporary Not Reported sex omitted',
            'limits': 'No demographics, dates, doses or response scores inferred'}


def subject_rows(records, previous=()):
    numbers = {r['unique_id']: int(r['subject_id']) for r in previous}
    if len(numbers) != len(previous) or len(set(numbers.values())) != len(numbers) or any(n < 1 for n in numbers.values()):
        raise ValueError('Invalid previous subject-number mapping')
    patients = {}
    for record in records:
        pid, disease = record['patient_id'], record['info']['source_metadata']['disease state']
        if pid in patients and patients[pid] != disease:
            raise ValueError('Conflicting subject diagnoses')
        patients[pid] = disease
    next_id = max(numbers.values(), default=0) + 1
    for pid in sorted(patients):
        if pid not in numbers:
            numbers[pid] = next_id
            next_id += 1
    return [dict(unique_id=pid, subject_id=numbers[pid], study='GSE42296', type='Case',
                 condition={"Crohn's disease": 'K50.9', 'Rheumatoid arthritis': 'M06.9'}[disease],
                 sex='Not Available', age_group='Not Available')
            for pid, disease in sorted(patients.items())]


def _prepare(source, package, converter, mapping, clarid_tools, codebook):
    previous = None
    expression_path = source / 'GSE42296_series_matrix.txt.gz'
    m = pd.DataFrame(metadata(expression_path, required={'sample_id'}))
    required = {'sample_id', 'subject', 'response', 'treatment', 'time', 'disease state', 'cell type'}
    if not required <= set(m.columns) or m.empty or m.sample_id.duplicated().any():
        raise ValueError('Incomplete metadata or duplicate sample IDs')
    diseases = {"Crohn's disease": 'CD', 'Rheumatoid arthritis': 'RA'}
    if set(m['disease state']) != set(diseases):
        raise ValueError('Expected both Crohn and rheumatoid arthritis source groups')
    if not set(m.response) <= {'R - responder', 'NR - non-responder'}:
        raise ValueError('Unexpected response label')
    if m.duplicated(['disease state', 'subject', 'time']).any():
        raise ValueError('Duplicate disease/patient/visit; review rather than discard')
    for _, group in m.groupby(['disease state', 'subject']):
        if set(group.time) != {'week 0', 'week 2'} or group.response.nunique() != 1:
            raise ValueError('Expected complete paired visits with consistent response labels')
    with gzip.open(expression_path, 'rt') as handle:
        for line in handle:
            if line.startswith('!series_matrix_table_begin'):
                break
        frame = pd.read_csv(handle, sep='\t', comment='!', dtype={'ID_REF': str}, float_precision='round_trip')
    probes = frame.pop('ID_REF').to_numpy(dtype=str)
    source_samples = frame.columns.to_numpy(dtype=str)
    values = frame.to_numpy(dtype=float).T
    if (values.shape != (len(source_samples), len(probes)) or
            len(set(source_samples)) != len(source_samples) or len(set(probes)) != len(probes) or
            not len(probes) or not np.isfinite(values).all() or
            set(m.sample_id) != set(source_samples)):
        raise ValueError('Expression shape, identifiers, coverage or values are invalid')
    # Align explicitly by original sample ID, never by source row position.
    index = {sample: i for i, sample in enumerate(source_samples)}
    values = values[[index[s] for s in m.sample_id]]
    samples, records = [], []
    for row in m.to_dict('records'):
        patient = 'GSE42296-' + diseases[row['disease state']] + '-' + quote(row['subject'], safe='')
        sample = patient + ':' + row['sample_id']
        day = {'week 0': 0, 'week 2': 14}[row['time']]
        expected_treatment = 'Before treatment' if day == 0 else 'infliximab'
        if row['treatment'] != expected_treatment or row['cell type'] != 'PBMC':
            raise ValueError('Unexpected treatment timing or tissue')
        records.append({'id': sample, 'patient_id': patient,
            'info': {'visit_id': row['time'],
                     'source_accession': row['sample_id'], 'source_subject': row['subject'],
                     'days_from_baseline': day, 'treatment_response': row['response'],
                     'source_metadata': row}})
        samples.append({'sample_id': sample, 'patient_id': patient,
            'source_sample_id': row['sample_id'], 'source_patient_id': row['subject'],
            'diagnosis': row['disease state'], 'timepoint': row['time'], 'visit_id': row['time'],
            'days_from_baseline': day, 'treatment': row['treatment'], 'response': row['response'],
            'tissue': row['cell type']})
    (package / 'clinical').mkdir(parents=True)
    (package / 'assays').mkdir()
    if converter:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            audit = convert_clinical(records, converter, mapping, work)
            provenance = package / 'provenance'
            provenance.mkdir()
            shutil.copyfile(mapping, provenance / 'clinical.yaml')
            shutil.copyfile(work / 'terminology.tsv', provenance / 'terminology.tsv')
            write_json(provenance / 'mapping-audit.json', audit)
    write_json(package / 'manifest.json', {'schema_version': 1,
        'name': 'GSE42296 Crohn disease and rheumatoid arthritis infliximab study',
        'study_design': 'longitudinal', 'clinical': {'representation': 'snapshot'}})
    write_json(package / 'clinical/records.json', records)
    if clarid_tools:
        prior = []
        if previous:
            with previous.open() as handle:
                prior = list(csv.DictReader(handle))
        encode_subjects(subject_rows(records, prior), package / 'identifiers',
                        clarid_tools, codebook, 'GSE42296', 'G422')
        manifest = json.loads((package / 'manifest.json').read_text())
        manifest['identifiers'] = {'clarid_subjects': {
            'entity': 'subject', 'file': 'identifiers/clarid_subjects.csv',
            'delimiter': ',', 'codebook_version': '0.04', 'tools_version': '0.04'}}
        write_json(package / 'manifest.json', manifest)
    with (package / 'assays/samples.tsv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(samples[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(samples)
    with (package / 'assays/expression.csv').open('w', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['feature_id'] + [s['sample_id'] for s in samples])
        for probe, expression in zip(probes, values.T):
            writer.writerow([probe] + expression.astype(float).tolist())
    write_json(package / 'assays/manifest.json', {'version': 1, 'assays': [{
        'assay_id': 'gse42296_microarray', 'label': 'Published PBMC microarray expression',
        'modality': 'transcriptomics', 'data_type': 'microarray_expression', 'level': 'sample',
        'feature_namespace': 'affymetrix_transcript_cluster_id', 'feature_id_column': 'feature_id',
        'sample_id_column': 'matrix_columns', 'patient_id_column': 'patient_id',
        'patient_linkage': 'sample_metadata_file', 'sample_metadata_file': 'assays/samples.tsv',
        'file': 'assays/expression.csv', 'feature_count': len(probes)}]})
    counts = dict(patients=len({r['patient_id'] for r in records}), snapshots=len(records), samples=len(samples), features=len(probes))
    if counts != dict(patients=39, snapshots=78, samples=78, features=33297):
        raise ValueError('GSE42296 counts differ from reviewed recipe')
    return counts



def prepare(source, package, check_cancel, report):
    check_cancel()
    report(message='Preparing paired Crohn/RA clinical records and microarrays…')
    counts = _prepare(source, package, preparation_command('convert-pheno'), Path(__file__).with_suffix('.yaml'),
                      preparation_command('clarid-tools'), codebook_path())
    check_cancel()
    (package / 'README.md').write_text(
        '# GSE42296\n\nSource: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE42296\n\n'
        'All 39 Crohn/RA patients and 78 paired visits retained. Diagnoses and post-treatment infliximab '
        'status mapped with Convert-Pheno. No demographics, dates, doses or response scores inferred. '
        'Original processed microarray values read directly from GEO, not the older float32 ED-Omics export. '
        'No additional normalization, probe collapsing or filtering. These are not RNA-seq counts. '
        'Paired visits must be modelled by patient; response labels are endpoints, not visit measurements.\n\n'
        'Review the original study and https://www.ncbi.nlm.nih.gov/geo/info/disclaimer.html before use or '
        'redistribution; cite the original study.\n', encoding='utf-8')
    return counts
