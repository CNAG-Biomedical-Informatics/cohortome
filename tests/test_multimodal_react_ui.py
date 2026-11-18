from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect

from test_ui_smoke import live_server, page, _mock_dashboard_load, _mock_assay_datasets, _mock_multimodal_readiness
from test_scope_builder_ui import scope_response


def open_coverage(page, patients, responder=None):
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_multimodal_readiness(page)
    page.route('**/patient-overview/coverage?*', responder or (lambda route: route.fulfill(json={'patients':patients, 'warnings':[]})))
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardMultimodalBtn').click()
    return page.locator('.multimodal-coverage')


def test_multimodal_react_keeps_drafts_stable_and_saves_applied_combination(page):
    patients = [dict(patient_id=f'P{index}', dataset_id='default', dataset_label='Example', has_clinical=True,
                     diseases=['Example disease'], modalities=modalities) for index, modalities in enumerate([
        ['clinical', 'transcriptomics', 'proteomics'],
        ['clinical', 'transcriptomics', 'proteomics', 'serology'],
        ['transcriptomics', 'proteomics'], ['clinical', 'transcriptomics']])]
    applications, saved = [], []
    def apply(route):
        body = route.request.post_data_json
        applications.append(body)
        required = set(body['modalities'])
        matches = [patient for patient in patients if required <= set(patient['modalities']) and
                   (not body['exact'] or set(patient['modalities']) - {'clinical'} == required - {'clinical'})]
        members = [dict(dataset_id=patient['dataset_id'], patient_id=patient['patient_id']) for patient in matches]
        route.fulfill(json=scope_response(members))
    page.route('**/cohort-builder/apply', apply)
    page.route('**/saved-cohorts', lambda route: (saved.append(route.request.post_data_json), route.fulfill(json={'id':'example-cohort'})))
    panel = open_coverage(page, patients)
    # Parent-page selectors must not restyle the shared filter basket.
    styles = page.evaluate("""() => {
      const properties = ['fontSize','fontWeight','color','backgroundColor','padding','borderRadius','marginTop'];
      return ['#dashboardPatientsPanel', '#dashboardMultimodalPanel'].map(panel =>
        ['.cohort-scope-bar','.cohort-filter-basket','.cohort-filter-basket > summary','[data-scope-apply]'].map(selector => {
          const style = getComputedStyle(document.querySelector(panel + ' ' + selector));
          return Object.fromEntries(properties.map(key => [key,style[key]]));
        }));
    }""")
    assert styles[0] == styles[1]
    expect(panel.locator('.cohort-scope-state')).to_contain_text('4 patients match selected data types')
    page.evaluate('''() => {
        window.coverageTableBefore = document.querySelector('.coverage-intersections table');
        window.coverageInputBefore = document.querySelector('.coverage-selectors input[value="proteomics"]');
    }''')
    panel.locator('input[value="transcriptomics"]').check()
    panel.locator('input[value="proteomics"]').check()
    expect(panel.locator('.cohort-filter-basket summary')).to_have_text('2 filters')
    expect(panel.locator('.cohort-scope-filters')).to_be_hidden()
    assert panel.locator('.cohort-scope-bar').bounding_box()['y'] < panel.locator('.coverage-selectors').bounding_box()['y']
    panel.locator('.cohort-filter-basket summary').click()
    expect(panel.locator('.cohort-scope-filters')).to_contain_text('Proteomics')
    panel.locator('.cohort-filter-basket summary').click()
    assert page.evaluate('window.coverageInputBefore === document.querySelector(\'.coverage-selectors input[value="proteomics"]\')')
    expect(panel.locator('.coverage-save')).to_be_disabled()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('3 patients match selected data types')
    expect(page.locator('#multimodalHeadingCount')).to_have_text('3 matching patients (preview)')
    expect(panel.locator('.coverage-save')).to_be_hidden()
    assert not applications
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('3 patients match selected data types')
    expect(panel.locator('[data-combination]')).to_have_count(3)
    assert page.evaluate('window.coverageTableBefore === document.querySelector(".coverage-intersections table")')
    panel.locator('.coverage-mode').select_option('exact')
    expect(panel.locator('.cohort-scope-state')).to_contain_text('2 patients match selected data types')
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('2 patients match selected data types')
    panel.locator('input[value="clinical"]').check()
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('1 patients match selected data types')
    panel.locator('.coverage-save').click()
    dialog = page.get_by_role('dialog', name='Save cohort', exact=True)
    dialog.get_by_label('Cohort name').fill('React test cohort')
    dialog.get_by_role('button', name='Save cohort', exact=True).click()
    expect(panel.locator('.coverage-save-status')).to_contain_text('Cohort saved')
    assert saved[0]['members'] == [{'dataset_id':'default', 'patient_id':'P0'}]
    assert applications[-1]['exact'] is True
    assert len(applications) == 3
    panel.locator('[data-scope-clear]').click()
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('.cohort-scope-pending')).to_be_hidden()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('4 patients match selected data types')
    panel.locator('[data-combination="0"]').click()
    expect(panel.locator('input[value="serology"]')).to_be_checked()
    expect(panel.locator('.coverage-mode')).to_have_value('exact')
    expect(panel.locator('.cohort-scope-state')).to_contain_text('1 patients match selected data types')
    assert len(applications) == 4
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('1 patients match selected data types')
    panel.screenshot(path='/tmp/cohortome-react-multimodal.png')


def test_multimodal_react_pagination_inventory_identity_and_stale_reply(page):
    patients = [dict(patient_id='P1' if i < 2 else f'P{i}', dataset_id='b' if i == 1 else 'a',
                     dataset_label='Beta' if i == 1 else 'Alpha', modalities=['clinical'], has_clinical=True)
                for i in range(26)]
    pending = []
    page.route('**/patient-overview/detail?*', lambda route: pending.append(route))
    panel = open_coverage(page, patients)
    expect(panel.locator('.cohort-scope-state')).to_contain_text('26 patients match selected data types')
    panel.locator('.coverage-patients summary').click()
    rows = panel.locator('.coverage-patient-list tbody tr')
    expect(rows).to_have_count(25)
    with page.expect_request('**/patient-overview/detail?*'):
        rows.nth(0).get_by_role('button', name='Inspect').click()
    expect(panel.locator('.coverage-inspector')).to_contain_text('Loading sample inventory')
    with page.expect_request('**/patient-overview/detail?*'):
        rows.nth(1).get_by_role('button', name='Inspect').click()
    page.wait_for_function('document.querySelector(".coverage-inspector").textContent.includes("Loading")')
    assert len(pending) == 2
    assert parse_qs(urlsplit(pending[0].request.url).query)['dataset_id'] == ['a']
    assert parse_qs(urlsplit(pending[1].request.url).query)['dataset_id'] == ['b']
    pending[1].fulfill(json={'samples':[], 'warnings':['Example warning']})
    expect(panel.locator('.coverage-inspector')).to_contain_text('P1 · Beta')
    pending[0].fulfill(json={'samples':[], 'warnings':['Outdated response']})
    expect(panel.locator('.coverage-inspector')).not_to_contain_text('Outdated response')
    panel.locator('.coverage-next').click()
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text('P25')
    expect(panel.locator('.coverage-inspector')).to_be_empty()
    expect(panel.locator('.coverage-next')).to_be_disabled()
    panel.locator('.coverage-prev').click()
    expect(rows).to_have_count(25)
    page.set_viewport_size({'width':390, 'height':844})
    assert panel.evaluate('el => el.scrollWidth <= el.clientWidth + 1')


def test_multimodal_react_retry_and_escape_untrusted_labels(page):
    patients = [dict(patient_id='P1', dataset_id='default', dataset_label='Example', has_clinical=False,
                     diseases=['<img src=x onerror=alert(1)>'], modalities=['clinical', 'unknown_<script>'])]
    calls = []
    def coverage(route):
        calls.append(route.request.url)
        if len(calls) == 1:
            route.fulfill(status=503, json={'detail':'Coverage temporarily unavailable.'})
        else:
            route.fulfill(json={'patients':patients, 'warnings':['<script>Not executable</script>']})
    panel = open_coverage(page, patients, coverage)
    expect(panel).to_contain_text('Coverage temporarily unavailable.')
    panel.get_by_role('button', name='Retry coverage').click()
    expect(panel.locator('.cohort-scope-state')).to_contain_text('1 patients match selected data types')
    expect(panel.locator('.coverage-diseases')).to_contain_text('<img src=x onerror=alert(1)>')
    expect(panel.locator('img, script')).to_have_count(0)
    panel.locator('.coverage-patients summary').click()
    expect(panel.get_by_role('button', name='Inspect')).to_be_disabled()
    assert len(calls) == 2
