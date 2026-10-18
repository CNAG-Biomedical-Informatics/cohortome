import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app import cohorts, exports, routes


@pytest.fixture
def clinical_export(tmp_path, monkeypatch):
    roots = {}
    for dataset in ['a', 'b']:
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical' / 'records.json').write_text(json.dumps([
            dict(id='P1:V1', patient_id='P1', sex=dataset, _cohortome_source={'secret': 'ignored'}),
            dict(id='P1:V2', patient_id='P1', visit='follow-up'),
            dict(id='P2:V1', patient_id='P2', sex='excluded'),
        ]))
        roots[dataset] = str(root)
    monkeypatch.setattr(cohorts, 'USER_STATE_ROOT', tmp_path / 'state')
    cohort = cohorts.save_cohort(name='Selected', dataset_id='a,b', dataset_ids=['a', 'b'],
        data_dir='', members=[dict(dataset_id=d, patient_id='P1', sample_id='P1:V1') for d in roots],
        id_type='sample', source_kind='test')
    return cohort, roots


def test_clinical_export_keeps_datasets_separate_and_all_visits(clinical_export):
    cohort, roots = clinical_export
    with zipfile.ZipFile(io.BytesIO(exports.clinical_cohort_bundle(cohort, roots))) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['row_count'] == 4
        for dataset in manifest['datasets']:
            records = json.loads(archive.read(dataset['clinical_file']))
            assert len(records) == 2
            assert records[0] == dict(id='P1:V1', patient_id='P1', sex=dataset['dataset_id'])
            assert records[1]['visit'] == 'follow-up'
        assert 'Assay matrices' in manifest['omitted']
        assert all(root not in archive.read('manifest.json').decode() for root in roots.values())


def test_clinical_export_rejects_changed_membership(clinical_export):
    cohort, roots = clinical_export
    cohort['members'][0]['patient_id'] = 'absent'
    with pytest.raises(HTTPException) as exc:
        exports.clinical_cohort_bundle(cohort, roots)
    assert exc.value.status_code == 409


def test_clinical_export_bounds(clinical_export, monkeypatch):
    cohort, roots = clinical_export
    monkeypatch.setattr(exports, 'MAX_EXPORT_BYTES', 20)
    with pytest.raises(HTTPException) as exc:
        exports.clinical_cohort_bundle(cohort, roots)
    assert exc.value.status_code == 413


def test_assay_only_patient_is_explicitly_reported(clinical_export, monkeypatch):
    from app import patient_overview
    cohort, roots = clinical_export
    monkeypatch.setattr(patient_overview, 'sample_inventory', lambda *a, **kw:
        ([dict(patient_id='assay-only', sample_id='sample-only')], []))
    cohort['members'].append(dict(dataset_id='a', patient_id='assay-only', sample_id='sample-only'))
    with zipfile.ZipFile(io.BytesIO(exports.clinical_cohort_bundle(cohort, roots))) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['datasets'][0]['patients_without_clinical_records'] == ['assay-only']


def test_clinical_export_route_download(clinical_export, monkeypatch):
    cohort, roots = clinical_export
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'local')
    monkeypatch.setattr(routes, 'parse_scope_dataset_ids', lambda _: list(roots))
    monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda *a: list(roots))
    monkeypatch.setattr(routes, 'resolve_dataset_dir', lambda req, identifier: roots[identifier])
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'detailed')
    response = routes.export_saved_cohort(cohort['id'], SimpleNamespace(), include='clinical')
    assert response.headers['cache-control'] == 'no-store'
    assert 'cohort-clinical-data.zip' in response.headers['content-disposition']
    assert zipfile.is_zipfile(io.BytesIO(response.body))


@pytest.mark.parametrize('failure,status', [('owner', 404), ('summary', 403), ('revoked', 403)])
def test_clinical_export_rechecks_access(clinical_export, monkeypatch, failure, status):
    cohort, roots = clinical_export
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'other' if failure == 'owner' else 'local')
    monkeypatch.setattr(routes, 'parse_scope_dataset_ids', lambda _: list(roots))
    def resolve(*args):
        if failure == 'revoked':
            raise HTTPException(403, 'Denied')
        return list(roots)
    monkeypatch.setattr(routes, 'resolve_dataset_ids', resolve)
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda _: 'summary' if failure == 'summary' else 'detailed')
    with pytest.raises(HTTPException) as exc:
        routes.export_saved_cohort(cohort['id'], SimpleNamespace(), include='clinical')
    assert exc.value.status_code == status
