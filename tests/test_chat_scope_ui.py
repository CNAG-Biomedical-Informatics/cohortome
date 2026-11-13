"""Browser regression for captured chat scope, with synthetic mocked responses."""
from test_ui_smoke import page, live_server, playwright, _open_query_tab


def test_query_chat_keeps_scope_and_new_chat_captures_new_scope(page):
    expect = playwright.expect
    chats, queries = {}, []
    def instrument(route):
        response = route.fetch()
        script = response.text().replace('const state = createAppState();',
            'const state = createAppState(); window.__scopeTestState = state;')
        route.fulfill(response=response, body=script)
    page.route('**/static/app.js', instrument)
    page.route('**/analysis-sessions', lambda route: route.fulfill(json={'sessions':[]}))
    def sessions(route):
        if route.request.method == 'POST':
            data = route.request.post_data_json
            data['revision'] = data.get('revision', 0) + 1
            chats[data['id']] = data
            route.fulfill(json=data)
        else:
            route.fulfill(json={'sessions':list(chats.values())})
    page.route('**/query-sessions', sessions)
    page.route('**/query-sessions/*', lambda route: route.fulfill(json=chats[route.request.url.rsplit('/', 1)[-1]]))
    def query(route):
        queries.append(route.request.post_data_json)
        route.fulfill(json={'intent':'patient_inventory', 'reply':'One selected patient.',
                            'data':{'source':'deterministic', 'patient_count':1}})
    page.route('**/query', query)
    page.evaluate('localStorage.clear()')
    page.reload(wait_until='networkidle')
    page.wait_for_function('Boolean(window.__scopeTestState?.currentDatasetScopeId)')
    def apply(patient):
        page.evaluate('''patient => {
          const state = window.__scopeTestState;
          state.activePatientScope = {workspace:state.currentDatasetScopeId,
            selection:{selection_active:true, members:[{dataset_id:state.currentDatasetIds[0], patient_id:patient}]}};
          window.dispatchEvent(new CustomEvent('cohortome:scope-applied'));
        }''', patient)
    def ask():
        page.locator('#question').fill('List patients')
        with page.expect_response('**/query'):
            page.locator('#askBtn').click()
        expect(page.locator('#askBtn')).to_be_enabled()
    apply('P1')
    page.wait_for_function("window.__scopeTestState.analysisScopeMetadata?.members?.[0]?.patient_id === 'P1'")
    _open_query_tab(page)
    ask()
    first_id = next(iter(chats))
    assert queries[-1]['scope_metadata']['members'][0]['patient_id'] == 'P1'
    expect(page.locator('#queryChatContextNotice')).to_contain_text('Chat scope: 1 patient')
    apply('P2')
    ask()
    assert queries[-1]['scope_metadata']['members'][0]['patient_id'] == 'P1'
    page.locator('#analysisNewSessionBtn').click()
    page.locator('#newQueryChatBtn').click()
    page.wait_for_function("window.__scopeTestState.queryScopeMetadata?.members?.[0]?.patient_id === 'P2'")
    ask()
    assert queries[-1]['scope_metadata']['members'][0]['patient_id'] == 'P2'
    page.locator(f'[data-query-session-id="{first_id}"]').click()
    page.wait_for_function("window.__scopeTestState.queryScopeMetadata?.members?.[0]?.patient_id === 'P1'")
    ask()
    assert queries[-1]['scope_metadata']['members'][0]['patient_id'] == 'P1'
    page.locator('#analysisNewSessionBtn').click()
    page.locator('#newAnalysisChatBtn').click()
    page.wait_for_function("window.__scopeTestState.analysisScopeMetadata?.members?.[0]?.patient_id === 'P2'")
    apply('P3')
    assert page.evaluate("window.__scopeTestState.analysisScopeMetadata.members[0].patient_id") == 'P2'
