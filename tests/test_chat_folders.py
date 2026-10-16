import pytest
from fastapi import HTTPException
from app import chat_folders, query_sessions, analysis_sessions


@pytest.fixture
def storage(tmp_path, monkeypatch):
    for module in (chat_folders, query_sessions, analysis_sessions):
        monkeypatch.setattr(module, 'USER_STATE_ROOT', tmp_path)
    query_sessions.save_session('alice', {'id': 'same', 'revision': 0, 'dataset_id': 'default'})
    analysis_sessions.save_analysis_session({'id': 'same', 'dataset_id': 'other'}, user_id='alice')
    return tmp_path


def test_mixed_folders_pin_and_delete_preserve_chats(storage):
    before_q = query_sessions.get_session('alice', 'same')
    before_a = analysis_sessions.get_analysis_session('same', user_id='alice')
    data = chat_folders.change_folders('alice', 'create', name='Research')
    folder = data['folders'][0]['id']
    for kind in ('query', 'analysis'):
        chat_folders.change_folders('alice', 'move', folder_id=folder, kind=kind, chat_id='same')
    chat_folders.change_folders('alice', 'pin', kind='query', chat_id='same', pinned=True)
    chat_folders.change_folders('alice', 'pin', kind='folder', chat_id=folder, pinned=True)
    data = chat_folders.change_folders('alice', 'rename', folder_id=folder, name='Renamed')
    assert data['assignments'] == {'query:same': folder, 'analysis:same': folder}
    assert data['folders'][0]['name'] == 'Renamed'
    assert len(data['pinned']) == 2
    chat_folders.change_folders('alice', 'move', kind='query', chat_id='same')
    assert 'query:same' in chat_folders.read_folders('alice')['pinned']
    data = chat_folders.change_folders('alice', 'delete', folder_id=folder)
    assert data['folders'] == [] and data['assignments'] == {}
    assert data['pinned'] == ['query:same']
    assert before_q == query_sessions.get_session('alice', 'same')
    assert before_a == analysis_sessions.get_analysis_session('same', user_id='alice')


def test_folder_ownership_and_validation(storage):
    folder = chat_folders.change_folders('alice', 'create', name='Research')['folders'][0]['id']
    assert chat_folders.read_folders('bob')['folders'] == []
    for operation in ('rename', 'delete', 'move'):
        with pytest.raises(HTTPException) as error:
            chat_folders.change_folders('bob', operation, folder_id=folder, name='Denied', kind='query', chat_id='same')
        assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        chat_folders.change_folders('bob', 'pin', kind='query', chat_id='same', pinned=True)
    for name in ('  ', 'Unfiled', 'research'):
        with pytest.raises(HTTPException):
            chat_folders.change_folders('alice', 'create', name=name)
