from playwright.sync_api import expect

from test_ui_smoke import live_server, page, _clinical_filter_panel


def test_react_patient_rows_keep_dataset_identity_and_escape_labels(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.evaluate('''async () => {
        const {createPatientsView} = await import('/static/js/react/ui.js');
        const tableHost = document.createElement('div'); tableHost.id = 'reactPatientTest';
        document.body.append(tableHost);
        window.patientTestCalls = [];
        const view = createPatientsView({host:tableHost, scopeUi:{mount:() => {}}, mountClinical:() => {}, actions:{
            sort: key => window.patientTestCalls.push(key),
            choose: match => window.patientTestCalls.push([match.dataset_id, match.patient_id])}});
        window.patientTestView = {renderTable:table => view.render({
            draft:{q:'', diseases:[], sample_origin:''}, diseases:[], origins:[],
            clinicalWorkspace:'', showAllDiseases:false, ...table})};
        window.patientTestRows = [
            {dataset_id:'a', patient_id:'P1', dataset_label:'Alpha', diagnosis:'<img src=x onerror=alert(1)>', clarid:'<Example>'},
            {dataset_id:'b', patient_id:'P1', dataset_label:'Beta'}];
        window.patientTestView.renderTable({matches:window.patientTestRows, sortBy:'patient_id', sortDirection:'asc'});
    }''')
    table = page.locator('#reactPatientTest')
    expect(table.locator('tbody tr')).to_have_count(2)
    expect(table.locator('img')).to_have_count(0)
    expect(table.locator('tbody tr').first).to_contain_text('<img src=x onerror=alert(1)>')
    expect(table.locator('.patient-browser-clarid')).to_have_attribute('title', '<Example>')
    expect(table.locator('tbody tr').last).to_contain_text('Not recorded')
    page.evaluate('''() => {
        window.patientFirstRow = document.querySelector('#reactPatientTest tbody tr');
        window.patientTestView.renderTable({matches:[...window.patientTestRows].reverse(), sortBy:'dataset_label', sortDirection:'desc'});
    }''')
    expect(table.locator('tbody tr').first).to_contain_text('Beta')
    assert page.evaluate('window.patientFirstRow === document.querySelector("#reactPatientTest tbody tr:last-child")')
    table.locator('.patient-open').first.focus()
    page.keyboard.press('Enter')
    assert page.evaluate('window.patientTestCalls') == [['b', 'P1']]
    page.evaluate('''() => window.patientTestView.renderTable({matches:[], sortBy:'patient_id', sortDirection:'asc'})''')
    expect(table).to_contain_text('No patients to display.')
    assert not errors


def test_react_patient_inputs_keep_focus_and_clinical_editor_until_discard(page):
    panel = _clinical_filter_panel(page)
    page.route('**/patient-overview/sample-origins?*', lambda route: route.fulfill(json=[
        {'id':'example-origin', 'label':'Example origin', 'patient_count':2}]))
    page.reload(wait_until='networkidle')
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardPatientsBtn').click()
    expect(panel.locator('#patientOverviewStatus')).to_contain_text('Page 1')
    expect(panel.locator('#patientSampleOriginFilter')).to_be_visible()
    requests = len(page._clinical_patient_requests)
    panel.get_by_role('button', name='Add clinical filter', exact=True).click()
    panel.locator('[data-field-id="marker"]').click()
    field = panel.get_by_label('Value', exact=True)
    expect(field).to_be_visible()
    page.evaluate('window.patientEditorBefore = document.querySelector("#patientClinicalFilters .clinical-filter-form")')
    search = panel.locator('#patientOverviewSearch')
    search.press_sequentially('HG00096', delay=20)
    expect(search).to_have_value('HG00096')
    search.evaluate('(el) => el.setSelectionRange(2, 2)')
    search.press_sequentially('X')
    expect(search).to_have_value('HGX00096')
    expect(search).to_be_focused()
    assert search.evaluate('(el) => el.selectionStart') == 3
    panel.locator('#patientSampleOrigin').select_option('example-origin')
    expect(panel.locator('#patientSampleOrigin')).to_have_value('example-origin')
    expect(field).to_be_visible()
    assert page.evaluate('window.patientEditorBefore === document.querySelector("#patientClinicalFilters .clinical-filter-form")')
    expect(panel.locator('.cohort-scope-pending')).to_be_visible()
    expect(panel.locator('#patientSaveCohort')).to_be_disabled()
    assert len(page._clinical_patient_requests) == requests
    panel.locator('[data-scope-discard]').click()
    expect(search).to_have_value('')
    expect(panel.locator('#patientSampleOrigin')).to_have_value('')
    expect(panel.locator('.clinical-filter-editor')).to_be_hidden()
    expect(panel.locator('#patientSaveCohort')).to_be_enabled()
