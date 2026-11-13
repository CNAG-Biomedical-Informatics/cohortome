"""Explicit local-agent sharing, without real credentials or dataset reads."""
from test_ui_smoke import live_server, page, playwright


def setup_agents(page, *, dirty=False):
    page.evaluate('''async dirty => {
      document.documentElement.dataset.deployment = 'desktop';
      document.querySelector('#userSettingsPanel').classList.remove('is-hidden');
      document.querySelectorAll('[data-settings-page]').forEach(p => p.hidden = p.dataset.settingsPage !== 'query');
      window.agentState = {currentDatasetScopeId:'default', currentDatasetIds:['default'],
        activePatientScope:{workspace:'default', selection:{members:[{dataset_id:'default', patient_id:'P1', patient_key:'internal-key'}]}},
        dirty, cohortScope:{isDirty:() => window.agentState.dirty, isBusy:() => false, subscribe:fn => window.renderAgents = fn}};
      const {createLocalAgentsUi} = await import('/static/js/local_agents.js');
      window.agents = createLocalAgentsUi({state:window.agentState});
      await window.agents.load();
      document.querySelector('#localAgentsSettings').open = true;
    }''', dirty)


def shared():
    import hashlib
    return dict(enabled=True, patient_count=1, datasets=[dict(dataset_id='default', name='Demo')],
                selection_signature=hashlib.sha256(b'["default",[["default","P1"]]]').hexdigest(),
                created_at='2026-11-12T09:00:00Z', expires_at='2099-11-12T17:00:00Z')


def test_run_approval_is_explicit_and_results_are_opt_in(page):
    calls = []
    plan = dict(plan_id='plan-test', analysis='Flow comparison', dataset_id='default', assay_id='cells',
                cohort_a_patient_count=3, cohort_b_patient_count=3,
                validated_inputs=dict(cohort_a_sample_count=3, cohort_b_sample_count=3, feature_count=12),
                cohort_a=['P1', 'P2', 'P3'], cohort_b=['P4', 'P5', 'P6'])
    page.route('**/local-agent/status', lambda r: r.fulfill(json=shared()))
    page.route('**/local-agent/plans', lambda r: r.fulfill(json={'plans':[] if calls else [plan]}))
    def decide(route):
        calls.append(route.request.post_data_json)
        route.fulfill(json={'status':'submitted', 'job_id':'fictional-job'})
    page.route('**/local-agent/plans/plan-test', decide)
    setup_agents(page)
    page.evaluate("window.addEventListener('cohortome:mcp-run', e => window.approvedRun = e.detail)")
    card = page.locator('#localAgentsPlans')
    playwright.expect(card).to_contain_text('3 usable samples')
    playwright.expect(card.locator('input[type=checkbox]')).not_to_be_checked()
    assert calls == []
    card.get_by_role('button', name='Approve and run').click()
    playwright.expect(page.locator('#localAgentsMessage')).to_contain_text('Your current workspace is unchanged')
    assert calls == [{'approve':True, 'allow_results':False}]
    assert page.evaluate('window.approvedRun.job_id') == 'fictional-job'
    assert page.evaluate('window.agentState.activePatientScope.selection.members[0].patient_id') == 'P1'
    playwright.expect(card).not_to_contain_text('Approve and run')


def test_bundled_configuration_formats_and_turn_off(page):
    import json
    import tomllib
    page.route('**/local-agent/status', lambda route: route.fulfill(json={'enabled': False}))
    command = '/Applications/COHORTome Desktop Preview.app/Contents/Resources/engine/mcp/cohortome-mcp'
    page.route('**/local-agent/share', lambda route: route.fulfill(json=(
        {'enabled': False} if route.request.method == 'DELETE' else
        {**shared(), 'connector': {'command': command, 'args': []},
         'url': 'http://127.0.0.1:12345/local-agent/call', 'token': 'fictional-test-token'})))
    setup_agents(page)
    page.locator('#localAgentsConsent').check()
    page.locator('#localAgentsShare').click()
    playwright.expect(page.locator('#localAgentsSecret')).to_be_visible()
    config = tomllib.loads(page.locator('#localAgentsConfiguration').input_value())
    assert config['mcp_servers']['cohortome']['command'] == command
    assert config['mcp_servers']['cohortome']['env']['COHORTOME_MCP_TOKEN'] == 'fictional-test-token'
    page.locator('#localAgentsFormat').select_option('json')
    assert json.loads(page.locator('#localAgentsConfiguration').input_value())['mcpServers']['cohortome']['command'] == command
    page.locator('#localAgentsRevoke').click()
    playwright.expect(page.locator('#localAgentsStatus')).to_have_text('MCP off · No agent access.')
    playwright.expect(page.locator('#localAgentsConfiguration')).to_have_value('')


def test_explicit_sharing_freezes_selection_and_revokes(page):
    expect = playwright.expect
    calls, status = [], {'enabled': False}
    page.route('**/local-agent/status', lambda route: route.fulfill(json=status))
    def share(route):
        calls.append((route.request.method, route.request.post_data_json))
        status.clear()
        if route.request.method == 'DELETE':
            status.update(enabled=False)
            route.fulfill(json=status)
        else:
            status.update(shared())
            if route.request.method == 'PUT':
                import hashlib
                import json
                body = route.request.post_data_json
                pairs = sorted({(m['dataset_id'], m['patient_id']) for m in body['members']})
                status['selection_signature'] = hashlib.sha256(json.dumps(
                    [body['workspace'], pairs], separators=(',', ':')).encode()).hexdigest()
                route.fulfill(json=status)
                return
            route.fulfill(json={**status, 'url':'http://127.0.0.1:12345/local-agent/call', 'token':'fictional-test-token'})
    page.route('**/local-agent/share', share)
    setup_agents(page)
    expect(page.locator('#localAgentsShare')).to_be_disabled()
    page.locator('#localAgentsConsent').check()
    page.locator('#localAgentsShare').click()
    expect(page.locator('#localAgentsMessage')).to_contain_text('Scope shared')
    assert calls == [('POST', dict(workspace='default', acknowledge=True,
                                 members=[dict(dataset_id='default', patient_id='P1')]))]
    assert 'fictional-test-token' in page.locator('#localAgentsConfiguration').input_value()
    page.locator('[data-settings-section="query"]').click()
    page.screenshot(path='/tmp/cohortome-local-agents.png')
    assert page.evaluate('JSON.stringify(localStorage) + JSON.stringify(sessionStorage)').find('fictional-test-token') == -1
    page.evaluate('''() => {
      window.agentState.activePatientScope.selection.members = [{dataset_id:'default', patient_id:'P2'}];
      window.dispatchEvent(new CustomEvent('cohortome:scope-applied'));
    }''')
    assert len(calls) == 1
    expect(page.locator('#localAgentsShare')).to_have_text('Update shared selection')
    expect(page.locator('#localAgentsScope')).to_contain_text('Selection changed—not shared yet')
    page.locator('#localAgentsConsent').check()
    page.locator('#localAgentsShare').click()
    expect(page.locator('#localAgentsMessage')).to_contain_text('token is unchanged')
    assert calls[-1][0] == 'PUT'
    assert calls[-1][1]['members'] == [dict(dataset_id='default', patient_id='P2')]
    expect(page.locator('#localAgentsBadge')).to_contain_text('On · 1 shared')
    expect(page.locator('#localAgentsScope')).not_to_contain_text('Selection changed')
    page.evaluate('window.agents.hide()')
    expect(page.locator('#localAgentsConfiguration')).to_have_value('')
    page.evaluate('window.agents.load()')
    expect(page.locator('#localAgentsStatus')).to_contain_text('1 patient shared')
    expect(page.locator('#localAgentsSecret')).to_be_hidden()
    page.locator('#localAgentsRevoke').click()
    expect(page.locator('#localAgentsMessage')).to_have_text('Agent access revoked.')
    expect(page.locator('#localAgentsRevoke')).to_be_hidden()


def test_dirty_or_mismatched_scope_cannot_share_and_empty_stays_empty(page):
    expect = playwright.expect
    calls = []
    page.route('**/local-agent/status', lambda route: route.fulfill(json={'enabled':False}))
    page.route('**/local-agent/share', lambda route: (
        calls.append(route.request.post_data_json),
        route.fulfill(json={**shared(), 'patient_count':0, 'url':'http://127.0.0.1:12345/local-agent/call', 'token':'fictional-test-token'})))
    setup_agents(page, dirty=True)
    page.locator('#localAgentsConsent').check()
    expect(page.locator('#localAgentsShare')).to_be_disabled()
    expect(page.locator('#localAgentsScope')).to_contain_text('Apply or discard')
    page.evaluate("agentState.dirty = false; agentState.activePatientScope.workspace = 'other'; renderAgents()")
    expect(page.locator('#localAgentsShare')).to_be_disabled()
    page.evaluate("agentState.activePatientScope = {workspace:'default', selection:{members:[]}}; renderAgents()")
    expect(page.locator('#localAgentsShare')).to_be_enabled()
    page.locator('#localAgentsShare').click()
    expect(page.locator('#localAgentsMessage')).to_contain_text('Scope shared')
    assert calls[0]['members'] == []
    page.evaluate("agentState.currentDatasetIds = ['other']; renderAgents()")
    expect(page.locator('#localAgentsScope')).to_contain_text('only the two included')
    assert len(calls) == 1


def test_web_is_hidden_and_failed_replacement_clears_secret(page):
    expect = playwright.expect
    status_calls, share_calls = [], []
    page.route('**/local-agent/status', lambda route: (status_calls.append(True), route.fulfill(json={'enabled':False})))
    page.evaluate('''async () => {
      const {createLocalAgentsUi} = await import('/static/js/local_agents.js');
      await createLocalAgentsUi({state:{}}).load();
    }''')
    assert not status_calls
    expect(page.locator('#localAgentsSettings')).to_be_hidden()
    def share(route):
        share_calls.append(True)
        if len(share_calls) == 1:
            route.fulfill(json={**shared(), 'url':'http://127.0.0.1:12345/local-agent/call', 'token':'fictional-test-token'})
        else:
            route.fulfill(status=409, json={'detail':'Scope unavailable.'})
    page.route('**/local-agent/share', share)
    setup_agents(page)
    page.locator('#localAgentsConsent').check()
    page.locator('#localAgentsShare').click()
    expect(page.locator('#localAgentsSecret')).to_be_visible()
    page.locator('#localAgentsConsent').check()
    page.locator('#localAgentsShare').click()
    expect(page.locator('#localAgentsMessage')).to_have_text('Scope unavailable.')
    expect(page.locator('#localAgentsSecret')).to_be_hidden()
    expect(page.locator('#localAgentsConfiguration')).to_have_value('')
    expect(page.locator('#localAgentsStatus')).to_have_text('MCP off · No agent access.')
    expect(page.locator('#localAgentsRevoke')).to_be_hidden()
    assert len(status_calls) == 2


def test_changed_scope_during_sharing_does_not_reveal_old_snapshot_token(page):
    expect = playwright.expect
    pending = []
    page.route('**/local-agent/status', lambda route: route.fulfill(json={'enabled':False}))
    page.route('**/local-agent/share', lambda route: pending.append(route))
    setup_agents(page)
    page.locator('#localAgentsConsent').check()
    with page.expect_request('**/local-agent/share'):
        page.locator('#localAgentsShare').click()
    page.evaluate('''() => {
      agentState.activePatientScope.selection.members = [];
      window.dispatchEvent(new CustomEvent('cohortome:scope-applied'));
    }''')
    pending[0].fulfill(json={**shared(), 'url':'http://127.0.0.1:12345/local-agent/call', 'token':'fictional-old-token'})
    expect(page.locator('#localAgentsMessage')).to_contain_text('earlier snapshot is shared')
    expect(page.locator('#localAgentsScope')).to_contain_text('0 selected patients')
    expect(page.locator('#localAgentsStatus')).to_contain_text('1 patient shared')
    expect(page.locator('#localAgentsSecret')).to_be_hidden()
    expect(page.locator('#localAgentsConfiguration')).to_have_value('')
