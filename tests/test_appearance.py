import pytest
from pydantic import ValidationError

from app import user_settings
from app.schemas import UserSettingsUpdateRequest, UserSettingsResponse


def test_appearance_saved_per_user(tmp_path, monkeypatch):
    def path(filename, user_id):
        directory = tmp_path / user_id
        directory.mkdir(exist_ok=True)
        return directory / filename
    monkeypatch.setattr(user_settings, 'user_state_file', path)
    assert user_settings.load_user_settings('one')['appearance'] == 'light'
    user_settings.update_user_settings({'appearance': 'dark'}, 'one')
    assert user_settings.load_user_settings('one')['appearance'] == 'dark'
    assert user_settings.load_user_settings('two')['appearance'] == 'light'
    user_settings.update_user_settings({'appearance': 'system'}, 'one')
    assert user_settings.load_user_settings('one')['appearance'] == 'system'


def test_appearance_validation():
    for value in ['light', 'dark', 'system']:
        assert UserSettingsUpdateRequest(appearance=value).appearance == value
        assert UserSettingsResponse(appearance=value).appearance == value
    with pytest.raises(ValidationError):
        UserSettingsUpdateRequest(appearance='invalid')
    assert user_settings.normalize_user_settings({'appearance': 'invalid'})['appearance'] == 'light'
