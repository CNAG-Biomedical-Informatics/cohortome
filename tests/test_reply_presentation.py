import pytest

from app.lm import sanitize_lm_text
from app.query_policy import finalize_query_response


@pytest.mark.parametrize('reply', [
    '**Disease distribution**\n- Five patients have condition A.\n\nLimitations follow.',
    '1. Five patients have condition A.\n2. Three take medication B.\n\nSummary complete.',
    '- Five patients match.\n- Two have follow-up.\n\nInterpret cautiously.',
])
def test_valid_formatted_answers_are_not_removed(reply):
    assert sanitize_lm_text(reply) == reply


@pytest.mark.parametrize('mode', ['summary', 'detailed'])
@pytest.mark.parametrize('intent', ['llm_fallback', 'llm_error', 'llm_unavailable', 'unsupported'])
def test_uncomputed_count_never_claims_a_summary_exists(mode, intent):
    payload = {'query': 'How many patients take biologics?', 'intent': intent,
               'reply': 'Potentially identifying free text', 'data': {}}
    result = finalize_query_response(payload, mode, mode, 'detailed_allowed')
    assert 'summary is available' not in result['reply']
    assert 'Potentially identifying' not in result['reply']
    assert not any(result['data']['available_actions'].values())


@pytest.mark.parametrize('count', [0, 1, 25])
def test_verified_count_still_returns_the_number(count):
    payload = {'query': 'How many patients take biologics?', 'intent': 'semantic_cohort_query',
               'reply': 'Computed', 'data': {'patient_count': count}}
    result = finalize_query_response(payload, 'detailed', 'detailed', 'detailed_allowed')
    assert result['reply'].startswith(str(count) + ' ')
