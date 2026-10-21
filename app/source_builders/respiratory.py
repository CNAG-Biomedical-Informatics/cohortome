"""GSE68310 harmonized expression and original clinical metadata recipe."""
import csv
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import quote
import numpy as np
import pandas as pd
from app.source_builders.psoriasis import number, record, DRUGS
from app.source_builders.common import sha256, write_json, encode_subjects
from app.preparation_tools import preparation_command
from app.geo_gse85034 import codebook_path
MEASURES = {'pasi': 'NCIT:C135734', 'temperature_f': 'NCIT:C164325', 'enrollment_age': 'NCIT:C25150'}

def respiratory(metadata, phenotypes):
    if metadata.index.duplicated().any() or phenotypes.SUBJECT_ID.duplicated().any():
        raise ValueError('Duplicate respiratory source identifiers')
    if set(metadata.ID) != set(phenotypes.SUBJECT_ID):
        raise ValueError('Phenotype subject coverage differs')
    if metadata.duplicated(['ID', 'timepoint']).any():
        raise ValueError('Duplicate respiratory patient/visit')
    phenotype = phenotypes.set_index('SUBJECT_ID').to_dict('index')
    records, samples, inputs, subjects = [], [], [], []
    for pid, group in metadata.groupby('ID', sort=True):
        patient = 'GSE68310-' + quote(pid, safe='')
        source = phenotype[pid]
        sex = {'F': 'Female', 'M': 'Male'}[source['Gender']]
        # No single precise disease code is supplied for this mixed-ARI cohort.
        subjects.append(dict(unique_id=patient, study='GSE68310', type='Case', condition='R69',
                             sex=sex, age_group='Not Available'))
        for sample, row in group.iterrows():
            visit = row['timepoint']
            if visit not in {'Baseline', '0', '2', '4', '6', '21', 'Spring'}:
                raise ValueError('Unknown respiratory visit')
            info = dict(source_patient_id=pid, source_sample_ids=[sample],
                        study_condition='Acute respiratory illness cohort',
                        source_phenotypes=source, time_reference='First illness assessment, not enrollment baseline')
            if visit.isdigit():
                info['days_from_first_illness_assessment'] = int(visit)
            clinical = record(patient, visit, [row.to_dict()], **info)
            records.append(clinical)
            # Enrollment age belongs only to baseline, not all later visits.
            age = number(source['Age']) if visit == 'Baseline' else ''
            # First-day illness temperature is not necessarily the day-0 visit.
            # Retain it in source_phenotypes until observation timing is resolved.
            inputs.append(dict(snapshot_id=clinical['id'], patient_id=patient, sex=sex,
                               diagnosis='', treatment='', pasi='', temperature_f='', enrollment_age=age))
            samples.append(dict(sample_id=patient + ':' + sample, patient_id=patient,
                                source_sample_id=sample, visit_id=visit, timepoint=visit,
                                tissue=row['tissue'], pathogen_group=row['pathogen']))
    return records, samples, inputs, subjects


def merge_converted(records, inputs, converted):
    mapped = {r['id']: r for r in converted}
    if len(mapped) != len(converted) or set(mapped) != {r['id'] for r in records}:
        raise ValueError('Converted snapshot coverage differs')
    expected = {r['snapshot_id']: r for r in inputs}
    for record in records:
        source, result = expected[record['id']], mapped[record['id']]
        diseases, treatments = result.get('diseases', []), result.get('treatments', [])
        if len(diseases) != bool(source['diagnosis']) or len(treatments) != bool(source['treatment']):
            raise ValueError('Converted term count differs')
        if diseases and diseases[0]['diseaseCode']['id'] != 'NCIT:C3346':
            raise ValueError('Unexpected psoriasis ontology term')
        drugs = {label: code for label, code in DRUGS.values()}
        if treatments and treatments[0]['treatmentCode']['id'] != drugs[source['treatment']]:
            raise ValueError('Unexpected treatment ontology term')
        record['diseases'] = [{'diseaseCode': d['diseaseCode']} for d in diseases]
        record['treatments'] = [{'treatmentCode': t['treatmentCode'],
                                  '_info': {'interpretation': 'Study treatment group, not a dated administration'}}
                                 for t in treatments]
        if source['sex'] != 'Not Reported':
            expected_sex = {'Female': 'NCIT:C16576', 'Male': 'NCIT:C20197'}[source['sex']]
            if result['sex']['id'] != expected_sex:
                raise ValueError('Converted sex differs')
            record['sex'] = result['sex']
        measures = []
        expected_measures = {code: float(source[field]) for field, code in MEASURES.items()
                             if source[field] != ''}
        for measure in result.get('measures', []):
            code = measure['assayCode']['id']
            quantity = measure['measurementValue']['quantity']
            if code not in expected_measures or float(quantity['value']) != expected_measures.pop(code):
                raise ValueError('Converted measurement differs from source')
            measures.append(dict(assayCode=measure['assayCode'],
                                 measurementValue={'quantity': {k: quantity[k] for k in ['value', 'unit']}}))
        if expected_measures:
            raise ValueError('Missing converted measurements')
        record['measures'] = measures


def convert(records, inputs, converter, mapping, package):
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        with (work / 'clinical.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(inputs[0]))
            writer.writeheader()
            writer.writerows(inputs)
        with (work / 'converter.log').open('w') as log:
            subprocess.run([*converter, '-icsv', str(work / 'clinical.csv'), '--separator', ',',
                            '--mapping-file', str(mapping), '--search', 'exact', '--no-source-info',
                            '--term-audit', str(work / 'terminology.tsv'), '-obff', str(work / 'converted.json')],
                           check=True, stdout=log, stderr=log, timeout=300)
        merge_converted(records, inputs, json.loads((work / 'converted.json').read_text()))
        provenance = package / 'provenance'
        provenance.mkdir()
        shutil.copyfile(mapping, provenance / 'clinical.yaml')
        shutil.copyfile(work / 'terminology.tsv', provenance / 'terminology.tsv')
        write_json(provenance / 'mapping-audit.json', dict(
            converter_version=subprocess.check_output([*converter, '--version'], text=True, timeout=30).strip(),
            mapping_sha256=sha256(mapping), snapshots=len(records),
            measures=sum(len(r['measures']) for r in records),
            placeholder_policy='Retain reviewed terms and source values only; no onset, dates or reference ranges inferred'))


def write_matrix(path, features, values, samples):
    if len(set(features)) != len(features) or len(set(s['sample_id'] for s in samples)) != len(samples):
        raise ValueError('Duplicate feature/sample coordinates')
    if values.shape != (len(samples), len(features)) or np.isinf(values).any():
        raise ValueError('Invalid expression shape or infinite values')
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['feature_id'] + [s['sample_id'] for s in samples])
        for feature, row in zip(features, values.T):
            writer.writerow([feature] + ['' if np.isnan(v) else float(v) for v in row])


def prepare(source, package, check_cancel, report):
    report(message='Mapping respiratory clinical visits with Convert-Pheno…')
    metadata = pd.read_csv(source / 'GSE68310_meta.csv', index_col=0, dtype=str, keep_default_na=False)
    phenotypes = pd.read_csv(source / 'GSE68310_SubjectPhenotypes1.txt.gz', sep='\t', dtype=str, keep_default_na=False)
    records, samples, inputs, subjects = respiratory(metadata, phenotypes)
    (package / 'clinical').mkdir(parents=True)
    (package / 'assays').mkdir()
    convert(records, inputs, preparation_command('convert-pheno'), Path(__file__).with_suffix('.yaml'), package)
    check_cancel()
    report(message='Preparing harmonized expression; retaining measured genes…')
    matrix = pd.read_csv(source / 'GSE68310_gene_expr.csv', index_col=0, float_precision='round_trip')
    if matrix.index.duplicated().any() or set(matrix.index) != set(metadata.index):
        raise ValueError('Expression/sample coverage differs')
    unmeasured = matrix.columns[matrix.isna().all()].tolist()
    matrix = matrix.drop(columns=unmeasured).loc[[s['source_sample_id'] for s in samples]]
    write_matrix(package / 'assays/expression.csv', matrix.columns.to_numpy(dtype=str), matrix.to_numpy(dtype=float), samples)
    with (package / 'provenance/unmeasured_features.tsv').open('w') as handle:
        handle.write('feature_id\treason\n')
        for feature in unmeasured:
            handle.write(feature + '\tUnmeasured harmonized-union padding\n')
    counts = dict(patients=len(subjects), snapshots=len(records), samples=len(samples), features=len(matrix.columns),
                  measures=sum(len(r['measures']) for r in records), omitted_unmeasured_features=len(unmeasured))
    if counts != dict(patients=133, snapshots=880, samples=880, features=18755, measures=128, omitted_unmeasured_features=22912):
        raise ValueError('GSE68310 counts differ from the reviewed recipe')
    write_json(package / 'clinical/records.json', records)
    from app.geo_gse85034 import write_csv
    write_csv(package / 'assays/samples.tsv', samples, '\t')
    check_cancel()
    report(message='Generating subject ClarIDs…')
    for i, row in enumerate(sorted(subjects, key=lambda row: row['unique_id']), 1):
        row['subject_id'] = i
    encode_subjects(subjects, package / 'identifiers', preparation_command('clarid-tools'), codebook_path(), 'GSE68310', 'G683')
    write_json(package / 'manifest.json', dict(schema_version=1, name='Respiratory infection and recovery',
        study_design='longitudinal', clinical={'representation': 'snapshot'},
        identifiers={'clarid_subjects': dict(entity='subject', file='identifiers/clarid_subjects.csv', delimiter=',',
            codebook_version='0.04', tools_version='0.04')}))
    write_json(package / 'assays/manifest.json', {'version': 1, 'assays': [dict(
        assay_id='gse68310_microarray', label='Harmonized respiratory expression', modality='transcriptomics',
        data_type='microarray_expression', level='sample', feature_namespace='gene_symbol', feature_id_column='feature_id',
        sample_id_column='matrix_columns', patient_id_column='patient_id', patient_linkage='sample_metadata_file',
        sample_metadata_file='assays/samples.tsv', file='assays/expression.csv', feature_count=len(matrix.columns))]})
    (package / 'README.md').write_text(
        '# GSE68310\n\nOriginal study: Zhai et al., https://doi.org/10.1371/journal.ppat.1004869\n'
        'Harmonization: HR-VILAGE-3K3M (earlier RIGEL), xuejun72 and contributors: '
        'https://huggingface.co/datasets/xuejun72/HR-VILAGE-3K3M\n\n'
        'All 133 participants and 880 observations retained. Expression is processed, not RNA-seq counts. '
        'Only 22,912 wholly unmeasured union-padding columns omitted; every omitted identifier is listed. '
        'No measured value changed, imputed or zero-filled.\n\n'
        'Sex and baseline enrollment age mapped with Convert-Pheno. Other source fields remain in metadata. '
        'Illness temperature, HAI scale and episode-level symptom timing are not reinterpreted as visit measurements. '
        'Numeric visit labels are days from first illness assessment, not enrollment baseline. '
        'Baseline/Spring have no inferred elapsed days. ClarID R69 is an unspecified-illness convention, '
        'not a BFF diagnosis or evidence of illness at every visit.\n\n'
        'Source terms: harmonized expression dataset card declares CC BY 4.0 at revision '
        'c68349578b97af04d1102eac5ad9f30f85362c53; older metadata card declares MIT at revision '
        '9d84762f55e61062156f77b3b5bca97900a45951. Review both original cards and notices; do not relabel '
        'all inputs under one licence. Original GEO phenotype supplement is governed by its own source terms '
        'and https://www.ncbi.nlm.nih.gov/geo/info/disclaimer.html. Source URLs/checksums are in provenance/preparation.json.\n', encoding='utf-8')
    return counts
