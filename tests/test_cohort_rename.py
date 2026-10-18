import pytest
from fastapi import HTTPException

from app import cohorts, routes
from app.schemas import SavedCohortRenameRequest


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts, 'USER_STATE_ROOT', tmp_path)
    return cohorts.save_cohort(name='Original', dataset_id='study', data_dir='/synthetic',
        members=[dict(dataset_id='study', patient_id='P1', sample_id='S1')],
        id_type='sample', source_kind='query', user_id='alice')


def test_rename_preserves_identity_and_membership(cohort):
    result = cohorts.rename_saved_cohort(cohort['id'], '  New label  ', 'alice')
    assert result['name'] == 'New label'
    assert set(result) == {'id', 'name', 'updated_at'}
    stored = cohorts.list_saved_cohorts(user_id='alice')[0]
    for key in cohort.keys() - {'name', 'updated_at'}:
        assert stored[key] == cohort[key]
    assert cohorts.rename_saved_cohort(cohort['id'], 'New label', 'alice')['name'] == 'New label'


@pytest.mark.parametrize('name', ['', '   ', 'x' * 201])
def test_invalid_name_leaves_cohort_unchanged(cohort, name):
    with pytest.raises(ValueError):
        cohorts.rename_saved_cohort(cohort['id'], name, 'alice')
    assert cohorts.list_saved_cohorts(user_id='alice')[0]['name'] == 'Original'


def test_route_is_owner_scoped(cohort, monkeypatch):
    monkeypatch.setattr(routes, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'bob')
    with pytest.raises(HTTPException) as exc:
        routes.update_saved_cohort_name(cohort['id'], SavedCohortRenameRequest(name='Changed'), None)
    assert exc.value.status_code == 404
    assert cohorts.list_saved_cohorts(user_id='alice')[0]['name'] == 'Original'
    monkeypatch.setattr(routes, 'request_user_id', lambda _: 'alice')
    assert routes.update_saved_cohort_name(cohort['id'], SavedCohortRenameRequest(name='Changed'), None)['name'] == 'Changed'


def test_duplicate_name_is_disambiguated(cohort):
    other = cohorts.save_cohort(name='Other', dataset_id='study', data_dir='/synthetic',
        members=cohort['members'], id_type='sample', source_kind='query', user_id='alice')
    assert cohorts.rename_saved_cohort(other['id'], 'Original', 'alice')['name'] == 'Original (2)'
