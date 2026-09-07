from app import analysis_sessions
from app.schemas import AnalysisSessionRequest


def test_framing_draft_and_submission_snapshot_survive_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_sessions, 'USER_STATE_ROOT', tmp_path)
    framing = {'mode': 'hypothesis_driven', 'question': 'Do simulated measurements covary?',
               'hypothesis': 'A positive association.', 'captured_at': '2026-09-07T12:00:00Z'}
    request = AnalysisSessionRequest(id='framing-test', framing=framing,
                                    turns=[{'role': 'assistant', 'framing': framing}])
    analysis_sessions.save_analysis_session(request.model_dump(), user_id='alice')
    stored = analysis_sessions.get_analysis_session('framing-test', user_id='alice')
    stored['framing'] = {'mode': 'exploratory', 'question': 'Another question'}
    analysis_sessions.save_analysis_session(stored, user_id='alice')
    restored = analysis_sessions.get_analysis_session('framing-test', user_id='alice')
    assert restored['framing']['mode'] == 'exploratory'
    assert restored['turns'][0]['framing'] == framing
    assert analysis_sessions.get_analysis_session('framing-test', user_id='bob') is None
