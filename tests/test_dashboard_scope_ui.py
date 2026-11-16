from playwright.sync_api import expect

from test_ui_smoke import live_server, page, _mock_dashboard_load, _mock_assay_datasets


def summary(count):
    return dict(selection_count=count, workspace_patient_count=2,
        totals=dict(patients=count, visits=count, clinical_records=count, source_files=1),
        sex_counts={'female':count} if count else {}, top_diseases=[], top_medications=[],
        visit_distribution={'1':count} if count else {}, patients=[], timelines=[], characteristics=[])


def test_clinical_dataset_view_is_shared_by_charts_and_tables(page):
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    payload = summary(3)
    payload['characteristics'] = [dict(dataset_id=key, label='Dataset ' + key,
        patients=count, chart_summary=summary(count), rows=[dict(label='Measurement ' + key, field_id='shared-field',
            kind='number', unit='mg/L', median=count, q1=count, q3=count,
            distribution=[dict(low=count, high=count, count=count)],
            recorded=count, missing=0)]) for key, count in [('a', 1), ('b', 2)]]
    page.route('**/dashboard?*', lambda r: r.fulfill(json=payload))
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardClinicalBtn').click()
    selector = page.locator('#clinicalTableDataset')
    expect(selector).to_have_value('')
    expect(selector.locator('option').first).to_have_text('All active datasets')
    expect(page.locator('.clinical-distribution-grid .dashboard-plot-card')).to_have_count(2)
    selector.select_option('b')
    expect(page.locator('.dashboard-hero .dashboard-count').first).to_have_text('2 patients')
    expect(page.locator('.clinical-distribution-grid .dashboard-plot-card')).to_have_count(1)
    expect(page.locator('.clinical-distribution-grid')).to_contain_text('2 measured · 0 missing')
    expect(page.locator('#contextScope')).to_contain_text('Full workspace')
    page.locator('[data-clinical-mode="table"]').click()
    expect(selector).to_have_value('b')
    expect(page.locator('.clinical-characteristics-dataset')).to_have_count(1)
    expect(page.locator('.clinical-characteristics-dataset')).to_contain_text('Measurement b')
    selector.select_option('')
    expect(page.locator('.clinical-characteristics-dataset')).to_have_count(2)
    expect(page.locator('.dashboard-hero .dashboard-count').first).to_have_text('3 patients')
    page.locator('[data-clinical-mode="charts"]').click()
    expect(selector).to_have_value('')
    expect(page.locator('.clinical-distribution-grid .dashboard-plot-card')).to_have_count(2)
    expect(page.locator('#contextScope')).to_contain_text('Full workspace')
    page.screenshot(path='/tmp/cohortome-clinical-dataset-selector.png')


def test_clinical_charts_normalize_sex_and_keep_secondary_plots_collapsed(page):
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    payload = summary(10)
    payload.update(sex_counts={'male':2, 'Male':1, ' female ':4, 'Female':2, 'Unknown':1},
        top_diseases=[{'disease':'Less common', 'patient_count':2},
                      {'disease':'More common', 'patient_count':7}])
    page.route('**/dashboard?*', lambda r: r.fulfill(json=payload))
    page.evaluate('''() => {
        const original = window.Plotly.newPlot.bind(window.Plotly);
        window.Plotly.newPlot = async (el, traces, layout, config) => {
            el.dataset.plotlyReady = 'true'; el._testTraces = traces; el._testLayout = layout;
            return original(el, traces, layout, config);
        };
    }''')
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardClinicalBtn').click()
    sex = page.locator('#dashboard-plot-sex')
    expect(sex).to_have_attribute('data-plotly-ready', 'true')
    trace = sex.evaluate('(el) => el._testTraces[0]')
    assert trace['type'] == 'pie' and trace['hole'] == .74
    assert dict(zip(trace['labels'], trace['values'])) == {'Female':6, 'Male':3, 'Unknown':1}
    assert trace['marker']['colors'][-1] == '#94a3b8'
    expect(page.locator('#clinicalSexLegend li')).to_have_count(3)
    expect(page.locator('#clinicalSexLegend li').first).to_contain_text('60.0%')
    assert '<b>10</b>' in sex.evaluate('(el) => el._testLayout.annotations[0].text')
    assert page.locator('#dashboard-plot-diseases').evaluate('(el) => el._testTraces[0].y') == ['More common', 'Less common']
    expect(page.locator('#clinicalSecondaryPlots')).to_be_hidden()
    page.screenshot(path='/tmp/cohortome-clinical-charts-primary.png')
    page.locator('#dashboardClinicalToggleBtn').click()
    expect(page.locator('#clinicalSecondaryPlots')).to_be_visible()
    expect(page.locator('#dashboard-plot-medications')).to_contain_text('No treatments recorded')
    expect(page.locator('#dashboard-plot-disease-medication')).to_contain_text('No linked diagnoses and treatments')


def test_applied_scope_updates_all_dashboard_views_without_replacing_chat_inventory(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    page.route('**/variants/panels?*', lambda r: r.fulfill(json=[]))
    page.route('**/patient-overview/timeline?*', lambda r: r.fulfill(json={'timelines':[
        dict(patient_id=f'["default","{pid}"]', source_patient_id=pid, dataset_id='default',
             dataset_label='Demo', events=[dict(event_date='2025-01-01', event_type='Visit')], samples=[])
        for pid in ['SYN001', 'SYN002']], 'warnings':[]}))
    page.route('**/dicom/studies?*', lambda r: r.fulfill(json={'enabled':False, 'studies':[
        dict(patient_id=pid, source_dataset_id='default', study_instance_uid=f'1.2.{i}', label='MRI ' + pid,
             modality='MR', series=[]) for i, pid in enumerate(['SYN001', 'SYN002'])]}))
    page.route('**/cohort-builder/apply', lambda r: r.fulfill(json={
        'workspace':'default', 'selection':None, 'summary':summary(2), 'assays':None}))
    def apply(route):
        members = route.request.post_data_json['members']
        count = len(members)
        route.fulfill(json={'workspace':'default', 'selection':{
            'selection_active':True, 'members':members, 'patient_count':count, 'patient_ids':[],
            'source':{'prompt':'Selected patients'}}, 'summary':summary(count), 'assays':[] if not count else [
            dict(dataset_name='synthetic_transcriptome_raw_counts_infliximab', modality='transcriptomics',
                 data_type='raw_counts', sample_count=1, patient_count=1, feature_count=12,
                 patient_ids=['SYN001'], sample_ids=['SYN001:V1'], clinical_overlap_patient_count=1,
                 count_summary_status='not_calculated_for_scope')]})
    page.route('**/cohort-builder/apply-selection', apply)
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardImagingBtn').click()
    expect(page.locator('#dicomDashboardStatus')).to_contain_text('2 patients')
    page.evaluate("window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:{members:[{dataset_id:'default', patient_id:'SYN001'}]}}))")
    expect(page.locator('#contextScope')).to_contain_text('1 patient')
    expect(page.locator('.clinical-scope-bar')).to_have_count(0)
    # A failed replacement must leave the applied group and charts intact.
    def reject_expired(route):
        route.fulfill(status=410, json={'detail':'Query selection expired. Run it again.'})
    page.route('**/cohort-builder/apply-selection', reject_expired)
    with page.expect_response('**/cohort-builder/apply-selection'):
        page.evaluate("window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:{result_handle:'qr_expired'}}))")
    expect(page.locator('#contextScope')).to_contain_text('1 patient')
    page.unroute('**/cohort-builder/apply-selection', reject_expired)
    expect(page.locator('#scopeHandoffStatus')).to_contain_text('Query selection expired')
    page.locator('#dashboardTimelineBtn').click()
    expect(page.locator('#timelineScopeLabel')).to_contain_text('1 in applied scope')
    expect(page.locator('#timelineAvailability')).to_contain_text('SYN001')
    expect(page.locator('#timelineAvailability')).not_to_contain_text('SYN002')
    page.locator('#dashboardAssaysBtn').click()
    expect(page.locator('#assayDashboardOverview')).to_contain_text('1 samples')
    expect(page.locator('#assayDashboardCards')).to_contain_text('available in Analysis')
    page.locator('#dashboardImagingBtn').click()
    expect(page.locator('#dicomDashboardStatus')).to_contain_text('1 patient · 1 imaging study')
    expect(page.locator('#dicomDashboardStudies')).not_to_contain_text('SYN002')
    page.evaluate("window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:{members:[]}}))")
    expect(page.locator('#contextScope')).to_contain_text('0 patients')
    page.locator('#dashboardTimelineBtn').click()
    expect(page.locator('#timelineScopeLabel')).to_contain_text('0 in applied scope')
    expect(page.locator('#timelineAvailability tbody tr')).to_have_count(0)
    page.locator('#dashboardAssaysBtn').click()
    expect(page.locator('#assayDashboardOverview')).to_contain_text('No linked assays')
    page.locator('#dashboardImagingBtn').click()
    expect(page.locator('#dicomDashboardStatus')).to_contain_text('No imaging studies in the applied scope')
    page.locator('#dashboardPatientsBtn').click()
    panel = page.locator('#dashboardPatientsPanel')
    panel.locator('[data-scope-clear]').click()
    expect(page.locator('#contextScope')).to_contain_text('0 patients')
    panel.locator('[data-scope-apply]').click()
    expect(page.locator('#contextScope')).to_contain_text('Full workspace')
    page.locator('#dashboardImagingBtn').click()
    expect(page.locator('#dicomDashboardStatus')).to_contain_text('2 patients')
    page.locator('#dashboardAssaysBtn').click()
    expect(page.locator('#assayDashboardCards')).to_contain_text('1024.0')
    assert not errors
