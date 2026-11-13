"""The two builder views share drafts; only Apply changes the patient scope."""
from test_ui_smoke import live_server, page, playwright, _clinical_filter_panel


def scope_response(members=None):
    count = 3 if members is None else len(members)
    return {'workspace':'default', 'selection':None if members is None else {
        'selection_active':True, 'members':members, 'patient_count':count,
        'patient_ids':[], 'sample_ids':[], 'sample_count':0, 'id_type':'patient',
        'dataset_ids':['default'], 'source':{'kind':'cohort-builder', 'prompt':'Applied test filters'}},
        'summary':{'totals':{'patients':count, 'visits':count, 'clinical_records':count, 'source_files':1},
            'selection_count':count, 'workspace_patient_count':3, 'characteristics':[],
            'sex_counts':{'Unknown':count}, 'visit_distribution':{}, 'top_diseases':[],
            'top_medications':[], 'patients':[], 'timelines':[]}, 'assays':[]}


def setup_scoped_search(page):
    calls = []
    def respond(route):
        members = route.request.post_data_json['members']
        calls.append(members)
        route.fulfill(json={'matches':[{**m, 'dataset_label':'Demo', 'diagnosis':'Example'} for m in members],
                           'total':len(members), 'next':None})
    page.route('**/patient-overview/scoped-search?*', respond)
    return calls


def test_shared_draft_applies_once_across_patients_and_multimodal(page):
    expect = playwright.expect
    page.set_viewport_size({'width':1200, 'height':900})
    errors, evaluations, applications = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/cohort-builder/evaluate', lambda route: (evaluations.append(route.request.post_data_json), route.fulfill(json={})))
    def apply(route):
        body = route.request.post_data_json
        applications.append(body)
        route.fulfill(json=scope_response([{'dataset_id':'default', 'patient_id':'P1'}]
            if body['clinical_filters'] or body['modalities'] else None))
    page.route('**/cohort-builder/apply', apply)
    scoped_searches = setup_scoped_search(page)
    panel = _clinical_filter_panel(page)
    initial_searches = len(page._clinical_patient_requests)
    panel.get_by_role('button', name='Add clinical filter', exact=True).click()
    panel.locator('[data-field-id="marker"]').click()
    panel.get_by_label('Operator', exact=True).select_option('gt')
    panel.get_by_label('Value', exact=True).fill('5')
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('Marker greater than 5')
    expect(panel.locator('.cohort-scope-pending')).to_be_visible()
    expect(panel.locator('#patientMatchCount')).to_contain_text('3 of 3')
    assert not evaluations and not applications
    assert len(page._clinical_patient_requests) == initial_searches
    panel.screenshot(path='/tmp/cohortome-scope-patients.png')
    panel.locator('#patientRefineMultimodal').click()
    coverage = page.locator('.multimodal-coverage')
    expect(coverage.locator('.coverage-result')).to_contain_text('3 patients in scope')
    expect(coverage.locator('.cohort-scope-filters')).to_contain_text('Marker greater than 5')
    coverage.locator('.coverage-selectors input[value="transcriptomics"]').check()
    expect(coverage.locator('.cohort-scope-pending')).to_be_visible()
    expect(coverage.locator('.coverage-result')).to_contain_text('3 patients in scope')
    assert not applications
    coverage.screenshot(path='/tmp/cohortome-scope-multimodal.png')
    coverage.locator('[data-scope-apply]').click()
    expect(coverage.locator('.coverage-result')).to_contain_text('1 patients in scope')
    expect(coverage.locator('.cohort-scope-pending')).to_be_hidden()
    assert len(applications) == 1
    assert applications[0]['clinical_filters'] == [{'field_id':'marker', 'operator':'gt', 'values':[5]}]
    assert applications[0]['modalities'] == ['transcriptomics']
    page.locator('#dashboardPatientsBtn').click()
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    expect(panel.locator('.cohort-scope-filters')).to_contain_text('Transcriptomics')
    assert scoped_searches[-1] == [{'dataset_id':'default', 'patient_id':'P1'}]
    panel.locator('[data-scope-clear]').click()
    expect(panel.locator('.cohort-scope-pending')).to_be_visible()
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    assert len(applications) == 1
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('#patientMatchCount')).to_contain_text('3 of 3')
    assert len(applications) == 2
    assert not errors


def test_failed_scope_application_keeps_previous_membership(page):
    expect = playwright.expect
    setup_scoped_search(page)
    panel = _clinical_filter_panel(page)
    applied = []
    def respond(route):
        applied.append(route.request.post_data_json)
        if len(applied) == 1:
            route.fulfill(json=scope_response([{'dataset_id':'default', 'patient_id':'P1'}]))
        else:
            route.fulfill(status=503, json={'detail':'Data source temporarily unavailable.'})
    page.route('**/cohort-builder/apply', respond)
    panel.locator('#patientOverviewSearch').fill('P1')
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    panel.locator('#patientOverviewSearch').fill('P2')
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('.cohort-scope-message')).to_contain_text('temporarily unavailable')
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    expect(panel.locator('#patientOverviewMatches tbody')).to_contain_text('P1')
    expect(panel.locator('#patientOverviewSearch')).to_have_value('P2')
    expect(panel.locator('#patientSaveCohort')).to_be_disabled()
    panel.locator('[data-scope-discard]').click()
    expect(panel.locator('#patientOverviewSearch')).to_have_value('P1')
    expect(panel.locator('.cohort-scope-pending')).to_be_hidden()
    expect(panel.locator('#patientSaveCohort')).to_be_enabled()
    assert len(applied) == 2


def test_edits_while_applying_do_not_install_an_outdated_scope(page):
    expect = playwright.expect
    setup_scoped_search(page)
    panel = _clinical_filter_panel(page)
    pending = []
    page.route('**/cohort-builder/apply', lambda route: pending.append(route))
    panel.locator('#patientOverviewSearch').fill('P1')
    with page.expect_request('**/cohort-builder/apply'):
        panel.locator('[data-scope-apply]').click()
    expect(panel.locator('[data-scope-apply]')).to_be_disabled()
    panel.locator('#patientOverviewSearch').fill('P2')
    pending[0].fulfill(json=scope_response([{'dataset_id':'default', 'patient_id':'P1'}]))
    expect(panel.locator('.cohort-scope-message')).to_contain_text('Filters changed while calculating')
    expect(panel.locator('#patientMatchCount')).to_contain_text('3 of 3')
    expect(panel.locator('[data-scope-apply]')).to_be_enabled()
    with page.expect_request('**/cohort-builder/apply'):
        panel.locator('[data-scope-apply]').click()
    assert len(pending) == 2
    assert pending[1].request.post_data_json['q'] == 'P2'
    pending[1].fulfill(json=scope_response([{'dataset_id':'default', 'patient_id':'P2'}]))
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    expect(panel.locator('#patientOverviewMatches tbody')).to_contain_text('P2')


def test_draft_ranges_are_local_and_discardable(page):
    expect = playwright.expect
    requests = []
    page.route('**/cohort-builder/evaluate', lambda route: (requests.append(route.request.url), route.fulfill(json={})))
    page.route('**/cohort-builder/apply', lambda route: (requests.append(route.request.url), route.fulfill(json={})))
    panel = _clinical_filter_panel(page)
    initial_searches = len(page._clinical_patient_requests)
    panel.get_by_role('button', name='Add clinical filter', exact=True).click()
    panel.locator('[data-field-id="marker"]').click()
    panel.get_by_label('Operator', exact=True).select_option('between')
    panel.get_by_label('Minimum range', exact=True).fill('3')
    panel.get_by_label('Upper value', exact=True).fill('8')
    expect(panel.get_by_label('Maximum range', exact=True)).to_have_value('8')
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('3 and 8')
    panel.get_by_label('Value', exact=True).fill('10')
    expect(panel.locator('.clinical-filter-validation')).to_contain_text('lower limit')
    expect(panel.locator('[data-scope-apply]')).to_be_disabled()
    expect(panel.locator('#patientMatchCount')).to_contain_text('3 of 3')
    panel.get_by_label('Upper value', exact=True).fill('11')
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('10 and 11')
    expect(panel.locator('[data-scope-apply]')).to_be_enabled()
    panel.locator('[data-scope-discard]').click()
    expect(panel.locator('.clinical-filter-chip')).to_have_count(0)
    expect(panel.locator('.cohort-scope-pending')).to_be_hidden()
    # Clearing/reopening uses the loaded catalogue fingerprint, not a blank one.
    panel.get_by_role('button', name='Add clinical filter', exact=True).click()
    panel.locator('[data-field-id="marker"]').click()
    panel.get_by_label('Operator', exact=True).select_option('is_present')
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('Marker is recorded')
    panel.locator('[data-scope-clear]').click()
    expect(panel.locator('.clinical-filter-chip')).to_have_count(0)
    assert not requests
    assert len(page._clinical_patient_requests) == initial_searches
    page.set_viewport_size({'width':390, 'height':844})
    assert panel.evaluate('el => el.scrollWidth <= el.clientWidth + 1')


def test_stale_apply_retains_scope_and_offers_clinical_reload(page):
    expect = playwright.expect
    panel = _clinical_filter_panel(page)
    page.route('**/cohort-builder/apply', lambda route: route.fulfill(
        status=409, json={'detail':'Dataset contents changed. Reload clinical filters.'}))
    panel.get_by_role('button', name='Add clinical filter', exact=True).click()
    panel.locator('[data-field-id="marker"]').click()
    panel.get_by_label('Operator', exact=True).select_option('is_present')
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('is recorded')
    panel.locator('[data-scope-apply]').click()
    expect(panel.get_by_role('button', name='Reload clinical filters')).to_be_visible()
    expect(panel.locator('[data-scope-apply]')).to_be_disabled()
    expect(panel.locator('#patientMatchCount')).to_contain_text('3 of 3')
    panel.get_by_role('button', name='Reload clinical filters').click()
    expect(panel.locator('.clinical-filter-chip')).to_have_count(0)
    expect(panel.get_by_role('button', name='Add clinical filter')).to_be_enabled()


def test_clinical_choices_remain_visible_and_edit_one_draft_rule(page):
    expect = playwright.expect
    panel = _clinical_filter_panel(page)
    page.route('**/cohort-builder/fields?*', lambda route: route.fulfill(json={
        'fingerprint':'synthetic-fingerprint', 'fields':[dict(id='category', label='Ethnicity',
            group='Demographics', kind='string', unit='', dataset_ids=['default'], dataset_labels=['Demo'],
            operators=['eq', 'in'], options=['Category A', 'Category B'])]}))
    applications = []
    def apply(route):
        applications.append(route.request.post_data_json)
        route.fulfill(json=scope_response([{'dataset_id':'default', 'patient_id':'P1'}]))
    page.route('**/cohort-builder/apply', apply)
    setup_scoped_search(page)
    panel.get_by_role('button', name='Add clinical filter').click()
    panel.locator('[data-field-id="category"]').click()
    panel.get_by_label('Operator', exact=True).select_option('in')
    panel.locator('[data-value-index="0"]').click()
    panel.locator('[data-value-index="1"]').click()
    expect(panel.locator('[data-value-index="0"]')).to_have_attribute('aria-pressed', 'true')
    expect(panel.locator('[data-value-index="1"]')).to_have_attribute('aria-pressed', 'true')
    expect(panel.locator('.clinical-filter-chip')).to_have_count(1)
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('Category A or Category B')
    expect(panel.locator('#patientMatchCount')).to_contain_text('3 of 3')
    assert not applications
    panel.locator('[data-value-index="0"]').click()
    expect(panel.locator('.clinical-filter-chip')).to_contain_text('is any of Category B')
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    assert applications[0]['clinical_filters'] == [{'field_id':'category', 'operator':'in', 'values':['Category B']}]
    panel.locator('[data-edit-clinical="0"]').click()
    expect(panel.locator('[data-value-index="1"]')).to_have_attribute('aria-pressed', 'true')
    panel.locator('[data-value-index="0"]').click()
    expect(panel.locator('.clinical-filter-chip')).to_have_count(1)
    expect(panel.locator('.cohort-scope-pending')).to_be_visible()
    panel.locator('[data-scope-discard]').click()
    panel.locator('[data-edit-clinical="0"]').click()
    expect(panel.locator('[data-value-index="0"]')).to_have_attribute('aria-pressed', 'false')
    expect(panel.locator('[data-value-index="1"]')).to_have_attribute('aria-pressed', 'true')
    assert len(applications) == 1


def test_failed_workspace_switch_preserves_applied_scope_and_draft(page):
    expect = playwright.expect
    panel = _clinical_filter_panel(page)
    setup_scoped_search(page)
    applications = []
    def apply(route):
        applications.append(route.request.post_data_json)
        route.fulfill(json=scope_response([{'dataset_id':'default', 'patient_id':'P1'}]))
    page.route('**/cohort-builder/apply', apply)
    panel.locator('#patientOverviewSearch').fill('P1')
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 of 3')
    panel.locator('#patientOverviewSearch').fill('P2')
    page.route('**/patients?dataset_id=secondary', lambda route: route.fulfill(
        status=409, json={'detail':'Dataset store needs preparation.'}))
    page.evaluate("() => window.__cohortomeLoadPatients({respectAdminGate:false, targetDatasetIds:['secondary']})")
    expect(panel.locator('#patientOverviewSearch')).to_have_value('P2')
    expect(panel.locator('.cohort-scope-pending')).to_be_visible()
    expect(panel.locator('#patientMatchCount')).to_contain_text('1 patients in scope')
    expect(panel.locator('#patientOverviewMatches tbody')).to_contain_text('P1')
    assert len(applications) == 1
    panel.locator('[data-scope-discard]').click()
    expect(panel.locator('#patientOverviewSearch')).to_have_value('P1')


def test_empty_applied_scope_is_not_the_full_workspace(page):
    expect = playwright.expect
    panel = _clinical_filter_panel(page)
    searches = setup_scoped_search(page)
    page.route('**/cohort-builder/apply', lambda route: route.fulfill(json=scope_response([])))
    panel.locator('#patientOverviewSearch').fill('NO-MATCH')
    panel.locator('[data-scope-apply]').click()
    expect(panel.locator('#patientMatchCount')).to_contain_text('0 of 3 patients in scope')
    expect(panel.locator('#patientOverviewMatches tbody tr[data-match]')).to_have_count(0)
    expect(panel.locator('#patientSaveCohort')).to_be_disabled()
    expect(panel.locator('.cohort-scope-state')).to_have_text('0 patients in scope')
    assert searches[-1] == []
    panel.locator('#patientRefineMultimodal').click()
    expect(page.locator('.multimodal-coverage .coverage-result')).to_contain_text('0 patients in scope')
    expect(page.locator('.multimodal-coverage .coverage-save')).to_be_disabled()
