import csv
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app import cohorts, molecular_exports as molecular, routes
from app.schemas import CohortAssaySelection, CohortMolecularExportRequest


@pytest.fixture
def matrices(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts, 'USER_STATE_ROOT', tmp_path / 'state')
    roots = {}
    for dataset in ['a', 'b']:
        root = tmp_path / dataset
        roots[dataset] = str(root)
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical' / 'records.json').write_text(json.dumps([{'id': 'P1'}, {'id': 'P2'}]))
        (root / 'assays').mkdir()
        (root / 'assays' / 'values.csv').write_text('gene_id,S-other,S2,S1\ngene1,999,2.500,1.25\ngene2,999,NA,0\n')
        (root / 'assays' / 'samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\nS2\tP1\nS-other\tP2\n')
        (root / 'assays' / 'manifest.json').write_text(json.dumps({'assays': [dict(
            assay_id='rna', label='RNA', modality='transcriptomics', data_type='rsem_expected_counts',
            sample_id_column='matrix_columns', feature_id_column='gene_id',
            file='assays/values.csv', sample_metadata_file='assays/samples.tsv')]}))
    cohort = cohorts.save_cohort(name='Selected', dataset_id='a,b', dataset_ids=['a', 'b'],
        data_dir='', members=[dict(dataset_id=d, patient_id='P1') for d in roots],
        id_type='patient', source_kind='test')
    return cohort, roots


def selections(cohort, roots):
    rows, _ = molecular.inventory(cohort, roots)
    return [CohortAssaySelection(key=r['key'], fingerprint=r['fingerprint']) for r in rows if r['available']]


def test_dataset_separation_column_order_and_exact_values(matrices):
    cohort, roots = matrices
    with zipfile.ZipFile(io.BytesIO(molecular.bundle(cohort, roots, selections(cohort, roots)))) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert len(manifest['assays']) == 2
        for assay in manifest['assays']:
            assert assay['data_type'] == 'rsem_expected_counts'
            assert assay['units'] is None
            assert archive.read(assay['file']).decode() == 'gene_id\tS2\tS1\ngene1\t2.500\t1.25\ngene2\tNA\t0\n'
        links = list(csv.DictReader(io.StringIO(archive.read('samples.tsv').decode()), delimiter='\t'))
        assert {(r['dataset_id'], r['sample_id'], r['patient_id']) for r in links} == {
            (d, s, 'P1') for d in roots for s in ['S1', 'S2']}
        assert all(root not in archive.read('manifest.json').decode() for root in roots.values())


def test_sample_scope_does_not_expand_to_other_samples(matrices):
    cohort, roots = matrices
    cohort['id_type'] = 'sample'
    for member in cohort['members']:
        member['sample_id'] = 'S1'
    with zipfile.ZipFile(io.BytesIO(molecular.bundle(cohort, roots, selections(cohort, roots)))) as archive:
        assert archive.read('assays/1/matrix.tsv').decode().splitlines()[0] == 'gene_id\tS1'


@pytest.mark.parametrize('problem', ['duplicate', 'undeclared', 'traversal', 'unlinked', 'oversize'])
def test_unavailable_assays_are_reported(matrices, problem, monkeypatch):
    from pathlib import Path
    cohort, roots = matrices
    root = Path(roots['a'])
    path = root / 'assays' / 'manifest.json'
    payload = json.loads(path.read_text())
    item = payload['assays'][0]
    if problem == 'duplicate':
        (root / 'assays' / 'values.csv').write_text('gene_id,S1,S1\ng,1,2\n')
    elif problem == 'undeclared':
        item.pop('sample_metadata_file')
    elif problem == 'traversal':
        item['file'] = '../b/assays/values.csv'
    elif problem == 'unlinked':
        (root / 'assays' / 'samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\n')
    else:
        monkeypatch.setattr(molecular, 'MAX_SOURCE_BYTES', 1)
    path.write_text(json.dumps(payload))
    if problem == 'oversize':
        with pytest.raises(HTTPException):
            molecular.inventory(cohort, roots)
    else:
        rows, _ = molecular.inventory(cohort, roots)
        assert not rows[0]['available']
        assert rows[0]['reason']


@pytest.mark.parametrize('problem', ['stale', 'malformed', 'duplicate_feature', 'output_limit', 'row_limit'])
def test_export_fails_without_partial_download(matrices, problem, monkeypatch):
    from pathlib import Path
    cohort, roots = matrices
    chosen = selections(cohort, roots)
    matrix = Path(roots['a']) / 'assays' / 'values.csv'
    if problem == 'stale':
        matrix.write_text(matrix.read_text() + 'g3,1,2,3\n')
    elif problem in ['malformed', 'duplicate_feature']:
        matrix.write_text(matrix.read_text() + ('bad,1\n' if problem == 'malformed' else 'gene1,1,2,3\n'))
        chosen = selections(cohort, roots)
    elif problem == 'output_limit':
        monkeypatch.setattr(molecular.exports, 'MAX_EXPORT_BYTES', 10)
    else:
        monkeypatch.setattr(molecular.exports, 'MAX_EXPORT_ROWS', 1)
    with pytest.raises(HTTPException) as exc:
        molecular.bundle(cohort, roots, chosen)
    assert exc.value.status_code == (413 if problem.endswith('limit') else 409)


@pytest.mark.parametrize('failure,status', [('owner',404), ('summary',403), ('revoked',403)])
def test_preview_and_download_reauthorize(matrices, monkeypatch, failure, status):
    cohort, roots = matrices
    chosen = selections(cohort, roots)
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'other' if failure == 'owner' else 'local')
    monkeypatch.setattr(routes, 'parse_scope_dataset_ids', lambda _: list(roots))
    def resolve(*args):
        if failure == 'revoked':
            raise HTTPException(403, 'Denied')
        return list(roots)
    monkeypatch.setattr(routes, 'resolve_dataset_ids', resolve)
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'summary' if failure == 'summary' else 'detailed')
    for call in [lambda: routes.get_cohort_export_assays(cohort['id'], SimpleNamespace()),
                 lambda: routes.export_cohort_molecular(cohort['id'], CohortMolecularExportRequest(assays=chosen), SimpleNamespace())]:
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == status
