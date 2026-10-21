"""Reviewed psoriasis visit grouping, shared with the Store's longitudinal recipe."""
import re
from urllib.parse import quote
import numpy as np
from app.geo_gse85034 import MAPPING, metadata, expression, write_csv
from app.geo_gse85034 import codebook_path, convert_clinical
from app.preparation_tools import preparation_command
from app.source_builders.common import encode_subjects, write_json
from app.geo_source import SourcePreparationError
import pandas as pd

DRUGS = {'ADA': ('Adalimumab', 'NCIT:C65216'), 'MTX': ('Methotrexate', 'NCIT:C642'),
         'Etanercept': ('Etanercept', 'NCIT:C2381'),
         'Ustekinumab 45 mg': ('Ustekinumab', 'NCIT:C84237'),
         'Ustekinumab 90 mg': ('Ustekinumab', 'NCIT:C84237')}
MISSING = {'', 'NA', 'N/A', 'NaN', 'nan'}


def number(value):
    if str(value) in MISSING:
        return ''
    result = float(value)
    if not np.isfinite(result):
        raise ValueError('Nonfinite clinical value')
    return result


def record(patient, visit, sources, **info):
    return dict(id=patient + ':' + quote(visit, safe=''), patient_id=patient,
                info=dict(visit_id=visit, source_metadata=sources, **info))


def psoriasis(metadata, accession):
    """One clinical snapshot per visit; retain every biopsy and source field."""
    m = metadata.copy()
    if m.sample_id.duplicated().any():
        raise ValueError('Duplicate sample identifier')
    m['pid'] = (m.subjectid if accession == 'GSE117239' else
                m.title.str.extract(r'^Subject\s+(\d+)\s+')[0])
    if m.pid.isna().any() or m.pid.eq('').any():
        raise ValueError('Unresolved patient identity')
    if not set(m.treatment) <= set(DRUGS):
        raise ValueError('Unknown treatment')
    m['visit'] = m.timepoint.replace({'LS': 'Baseline', 'NL': 'Baseline', 'WK2': 'WK 2'})
    source_columns = list(metadata.columns)
    records, samples, inputs, subjects = [], [], [], []
    for pid, person in m.groupby('pid', sort=True):
        if person.treatment.nunique() != 1:
            raise ValueError('Conflicting treatment group')
        patient = accession + '-' + quote(str(pid), safe='')
        subjects.append(dict(unique_id=patient, study=accession, type='Case',
                             condition='L40.9', sex='Not Available', age_group='Not Available'))
        for visit, group in person.groupby('visit', sort=False):
            values = {number(v) for v in group.pasi if str(v) not in MISSING}
            if len(values) > 1:
                raise ValueError('Conflicting PASI within patient/visit')
            pasi = next(iter(values), '')
            if pasi != '' and not 0 <= pasi <= 72:
                raise ValueError('PASI outside instrument range')
            info = dict(source_patient_id=str(pid), treatment_group=group.iloc[0].treatment,
                        source_sample_ids=group.sample_id.tolist())
            # WK 1NL/WK 1LS are ambiguous; never silently recode them as baseline.
            if visit == 'Baseline':
                info['days_from_baseline'] = 0
            elif re.fullmatch(r'(?:WK|Week) \d+', visit):
                info['days_from_baseline'] = int(visit.split()[-1]) * 7
            else:
                info['timing_note'] = 'Source timing label ambiguous; no elapsed day assigned'
            if accession == 'GSE117239':
                outcomes = person['pasi75 response at week 12'].unique()
                if len(outcomes) != 1 or outcomes[0] not in {'R', 'NR'}:
                    raise ValueError('Conflicting or unknown response endpoint')
                info['pasi75_response_at_week_12'] = outcomes[0]
            clinical = record(patient, visit, group[source_columns].to_dict('records'), **info)
            records.append(clinical)
            inputs.append(dict(snapshot_id=clinical['id'], patient_id=patient, sex='Not Reported',
                               diagnosis='Psoriasis', treatment=DRUGS[group.iloc[0].treatment][0],
                               pasi=pasi, temperature_f='', enrollment_age=''))
            for row in group.to_dict('records'):
                site = row['tissue']
                if accession == 'GSE85034':
                    site = 'Non-lesional skin' if row['timepoint'] in {'NL', 'WK 1NL'} else 'Lesional skin'
                samples.append(dict(sample_id=patient + ':' + row['sample_id'], patient_id=patient,
                                    source_sample_id=row['sample_id'], visit_id=visit, timepoint=visit,
                                    days_from_baseline=info.get('days_from_baseline', ''),
                                    tissue=site, treatment=row['treatment']))
    return records, samples, inputs, subjects


def prepare(source, package, check_cancel, report):
    accession = 'GSE117239'
    path = source / (accession + '_series_matrix.txt.gz')
    records, samples, inputs, subjects = psoriasis(pd.DataFrame(metadata(path)), accession)
    for directory in ('clinical', 'assays', 'provenance'):
        (package / directory).mkdir(parents=True)
    report(message='Mapping psoriasis visits with Convert-Pheno…')
    convert_clinical(records, inputs, package / 'provenance', preparation_command('convert-pheno'),
                     drugs=dict(DRUGS.values()), mapping_text=MAPPING.replace('id: gse85034', 'id: gse117239'))
    write_json(package / 'clinical/records.json', records)
    write_csv(package / 'assays/samples.tsv', samples, '\t')
    check_cancel()
    report(message='Preparing microarray expression…')
    features = expression(path, package / 'assays/expression.csv', samples, check_cancel)
    counts = dict(patients=len(subjects), snapshots=len(records), samples=len(samples), features=features,
                  measures=sum(len(r['measures']) for r in records))
    if counts != dict(patients=89, snapshots=246, samples=324, features=33687, measures=158):
        raise SourcePreparationError('GSE117239 counts differ from the reviewed recipe.')
    for i, row in enumerate(sorted(subjects, key=lambda row: row['unique_id']), 1):
        row['subject_id'] = i
    report(message='Generating subject ClarIDs…')
    encode_subjects(subjects, package / 'identifiers', preparation_command('clarid-tools'), codebook_path(), accession, 'G117')
    write_json(package / 'manifest.json', dict(schema_version=1, name='Psoriasis ustekinumab/etanercept skin study',
        study_design='longitudinal', clinical={'representation': 'snapshot'},
        identifiers={'clarid_subjects': dict(entity='subject', file='identifiers/clarid_subjects.csv', delimiter=',',
            codebook_version='0.04', tools_version='0.04')}))
    write_json(package / 'assays/manifest.json', {'version': 1, 'assays': [dict(
        assay_id='gse117239_microarray', label='Skin microarray expression', modality='transcriptomics',
        data_type='microarray_expression', level='sample', feature_namespace='affymetrix_probeset_id',
        feature_id_column='feature_id', sample_id_column='matrix_columns', patient_id_column='patient_id',
        patient_linkage='sample_metadata_file', sample_metadata_file='assays/samples.tsv',
        file='assays/expression.csv', feature_count=features)]})
    (package / 'README.md').write_text(
        '# GSE117239\n\nSource: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE117239\n\n'
        'All 89 participants and 324 biopsies retained. One BFF snapshot per patient/visit, not per biopsy. '
        'PASI and treatment group mapped with Convert-Pheno; week-12 PASI75 response is an endpoint, '
        'not a measurement at every visit. Unknown demographics/dates are not inferred. '
        'Processed microarray values preserved without additional normalization or filtering; these are not counts. '
        'Repeated samples are not independent patients.\n\n'
        'Downloaded directly from GEO and prepared locally. Review the study and GEO usage conditions '
        '(https://www.ncbi.nlm.nih.gov/geo/info/disclaimer.html) and cite the original study. '
        'No unrestricted redistribution licence is inferred.\n', encoding='utf-8')
    return counts
