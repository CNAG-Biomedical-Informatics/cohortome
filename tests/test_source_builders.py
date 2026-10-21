import json
from pathlib import Path

import pandas as pd
import pytest

from app.source_builders import source_files
from app.source_builders.ibdmdb_assays import biom_matrix, link_samples
from app.source_builders.psoriasis import psoriasis


def test_ibdmdb_sparse_zero_and_duplicate_coordinates():
    payload = dict(rows=[{'id': 'f1'}, {'id': 'f2'}], columns=[{'id': 's1'}],
                   shape=[2, 1], matrix_type='sparse', data=[[0, 0, 3.25]])
    assert biom_matrix(payload).iloc[:, 0].tolist() == [3.25, 0]
    payload['data'].append([0, 0, 4])
    with pytest.raises(ValueError, match='Duplicate'):
        biom_matrix(payload)


def test_ibdmdb_only_reviewed_unlinked_serology_is_excluded():
    meta = pd.DataFrame([{'External ID': 's1', 'Participant ID': 'p1', 'data_type': 'serology',
                          'week_num': '2', 'visit_num': '1', 'diagnosis': 'CD'}])
    samples, excluded = link_samples(meta, 'serology', ['s1', '220948'])
    assert excluded == ['220948']
    assert samples[0]['days_from_baseline'] == 14
    with pytest.raises(ValueError, match='Unexpected unlinked'):
        link_samples(meta, 'serology', ['s1', 'unreviewed'])


def test_psoriasis_endpoint_is_not_a_visit_measurement():
    meta = pd.DataFrame([dict(sample_id='s1', subjectid='p1', title='example', timepoint='Week 2',
        treatment='Etanercept', tissue='skin', pasi='0', **{'pasi75 response at week 12': 'R'})])
    records, samples, inputs, subjects = psoriasis(meta, 'GSE117239')
    assert records[0]['info']['pasi75_response_at_week_12'] == 'R'
    assert records[0]['info']['days_from_baseline'] == 14
    assert inputs[0]['pasi'] == 0
    assert subjects[0]['condition'] == 'L40.9'
    assert samples[0]['visit_id'] == 'Week 2'


def test_source_catalogue_sizes_match_shipped_inputs():
    entries = json.loads(Path('config/resources.json').read_text())
    for entry in entries:
        if entry.get('install_mode') == 'source' and entry['dataset_id'] != 'gse85034':
            specs = source_files(entry['dataset_id'])
            assert entry['source_bytes'] == sum(s['bytes'] for s in specs)
            assert all(s['url'].startswith('https://') and len(s['sha256']) == 64 for s in specs)
            assert len({s['filename'] for s in specs}) == len(specs)
            assert entry['review_statement'] and entry['source_policy_url']


def test_multi_source_progress_and_downloads_are_pinned(tmp_path, monkeypatch):
    from app import source_builders as recipes
    calls, progress = [], []
    def fetch(target, spec, check_cancel, report):
        calls.append((target.name, spec['url']))
        report(bytes=spec['bytes'], total=spec['bytes'])
    monkeypatch.setattr(recipes, 'fetch_source', fetch)
    recipes.fetch('ibdmdb', tmp_path / 'sources', lambda: None, lambda **kw: progress.append(kw))
    assert len(calls) == 4
    assert progress[-1]['bytes'] == progress[-1]['total']
    assert [p['bytes'] for p in progress] == sorted(p['bytes'] for p in progress)


def test_harmonized_redirects_stay_on_provider_hosts():
    import httpx
    from app.geo_source import source_url, SourcePreparationError
    original = 'https://huggingface.co/datasets/example/resolve/revision/file'
    for location, accepted in [('https://cas-bridge.xethub.hf.co/file', True),
                               ('https://evil.example/file', False),
                               ('http://huggingface.co/file', False),
                               ('https://name:password@cdn.hf.co/file', False)]:
        def response(request):
            assert 'authorization' not in request.headers
            return httpx.Response(302, headers={'location': location}) if str(request.url) == original else httpx.Response(200)
        with httpx.Client(transport=httpx.MockTransport(response), follow_redirects=False) as client:
            if accepted:
                assert source_url(client, original) == location
            else:
                with pytest.raises(SourcePreparationError, match='redirect'):
                    source_url(client, original)


def test_rna_patient_ids_are_scoped_to_source_cohort():
    from app.source_builders.ibd_rna import clinical_and_samples, subject_rows
    rows = pd.DataFrame([{'sample_id': 's' + str(i), 'cohort': cohort, 'patient': '1',
        'patient_id': cohort + ':1', 'diagnosis': 'CD', 'treatment': 'Infliximab',
        'time point': 'baseline', 'time': 0, 'remission at week 14': 'Remission'}
        for i, cohort in enumerate(['Discovery', 'Replication'])])
    clinical, samples = clinical_and_samples(rows)
    assert len({s['patient_id'] for s in samples}) == 2
    assert len(subject_rows(samples)) == 2
    assert all('measures' not in r and 'sex' not in r for r in clinical)
    with pytest.raises(ValueError, match='Duplicate'):
        clinical_and_samples(pd.concat([rows, rows.iloc[:1]]))


def test_respiratory_elapsed_time_is_not_baseline_time():
    from app.source_builders.respiratory import respiratory
    metadata = pd.DataFrame([dict(ID='p1', timepoint=v, pathogen='virus', tissue='blood')
                            for v in ['Baseline', '0', 'Spring']], index=['s1', 's2', 's3'])
    phenotype = pd.DataFrame([dict(SUBJECT_ID='p1', Gender='F', Age='25.5', Duration_of_symptoms='7')])
    records, samples, inputs, subjects = respiratory(metadata, phenotype)
    assert inputs[0]['enrollment_age'] == 25.5
    assert all(i['enrollment_age'] == '' for i in inputs[1:])
    assert records[1]['info']['days_from_first_illness_assessment'] == 0
    assert all('days_from_baseline' not in r['info'] for r in records)
    assert all(i['diagnosis'] == '' for i in inputs)
    assert subjects[0]['condition'] == 'R69'


def test_cd_ra_baseline_has_no_inferred_treatment():
    from app.source_builders.cd_ra import merge_converted, subject_rows
    records = [dict(id='s1', patient_id='p1', info={'source_metadata': {'time': 'week 0', 'disease state': "Crohn's disease"}})]
    converted = [dict(id='s1', diseases=[{'diseaseCode': {'id': 'NCIT:C2965'}, 'ageOfOnset': 'placeholder'}], treatments=[])]
    merge_converted(records, converted)
    assert records[0]['treatments'] == []
    assert 'ageOfOnset' not in records[0]['diseases'][0]
    assert subject_rows(records)[0]['condition'] == 'K50.9'
    converted[0]['treatments'] = [{'treatmentCode': {'id': 'NCIT:C1789'}}]
    with pytest.raises(ValueError, match='reviewed source'):
        merge_converted(records, converted)
