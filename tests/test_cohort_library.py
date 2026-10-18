from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app import cohorts, routes


def test_library_cross_workspace_access_and_owner_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts, 'USER_STATE_ROOT', tmp_path)
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: {'username': 'alice'})
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'alice')
    monkeypatch.setattr(routes, 'authorized_datasets_for_user', lambda _: [
        {'dataset_id': 'a'}, {'dataset_id': 'b'}, {'dataset_id': 'summary'}])
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling',
                        lambda ids: 'summary' if 'summary' in ids else 'detailed')
    for name, datasets, user in [('A', ['a'], 'alice'), ('B', ['b'], 'alice'),
                                 ('AB', ['a', 'b'], 'alice'), ('Restricted', ['a', 'revoked'], 'alice'),
                                 ('Summary', ['summary'], 'alice'), ('Other owner', ['a'], 'bob')]:
        cohorts.save_cohort(name=name, dataset_id='scope--' + '--'.join(datasets),
            dataset_ids=datasets, data_dir='/server/private/path',
            members=[{'dataset_id': d, 'patient_id': 'P1'} for d in datasets],
            id_type='patient', source_kind='test', user_id=user)
    result = routes.get_saved_cohort_library(SimpleNamespace())['cohorts']
    assert {c['name'] for c in result} == {'A', 'B', 'AB'}
    assert all('data_dir' not in c for c in result)
    cross = next(c for c in result if c['name'] == 'AB')
    assert cross['patient_count'] == 2
    assert len({m['patient_key'] for m in cross['members']}) == 2


def test_library_requires_authentication(monkeypatch):
    def deny(_):
        raise HTTPException(401, 'Authentication required')
    monkeypatch.setattr(routes, 'require_authenticated', deny)
    with pytest.raises(HTTPException) as error:
        routes.get_saved_cohort_library(SimpleNamespace())
    assert error.value.status_code == 401
