from playwright.sync_api import expect

from test_ui_smoke import live_server, page, _mock_dashboard_load, _mock_assay_datasets


def summary(count):
    return dict(selection_count=count, workspace_patient_count=2,
        totals=dict(patients=count, visits=count, clinical_records=count, source_files=1),
        sex_counts={'female':count} if count else {}, top_diseases=[], top_medications=[],
        visit_distribution={'1':count} if count else {}, patients=[], timelines=[], characteristics=[])


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
    expect(page.locator('.clinical-scope-bar')).to_contain_text('1 selected')
    # A failed replacement must leave the applied group and charts intact.
    def reject_expired(route):
        route.fulfill(status=410, json={'detail':'Query selection expired. Run it again.'})
    page.route('**/cohort-builder/apply-selection', reject_expired)
    with page.expect_response('**/cohort-builder/apply-selection'):
        page.evaluate("window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:{result_handle:'qr_expired'}}))")
    expect(page.locator('.clinical-scope-bar')).to_contain_text('1 selected')
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
    expect(page.locator('.clinical-scope-bar')).to_contain_text('0 selected')
    page.locator('#dashboardTimelineBtn').click()
    expect(page.locator('#timelineScopeLabel')).to_contain_text('0 in applied scope')
    expect(page.locator('#timelineAvailability tbody tr')).to_have_count(0)
    page.locator('#dashboardAssaysBtn').click()
    expect(page.locator('#assayDashboardOverview')).to_contain_text('No linked assays')
    page.locator('#dashboardImagingBtn').click()
    expect(page.locator('#dicomDashboardStatus')).to_contain_text('No imaging studies in the applied scope')
    page.locator('#dashboardClinicalBtn').click()
    page.locator('[data-clinical-reset]').click()
    page.get_by_role('dialog', name='Show full workspace?').get_by_role('button', name='Show full workspace', exact=True).click()
    expect(page.locator('.clinical-scope-bar')).to_contain_text('Full workspace')
    page.locator('#dashboardImagingBtn').click()
    expect(page.locator('#dicomDashboardStatus')).to_contain_text('2 patients')
    page.locator('#dashboardAssaysBtn').click()
    expect(page.locator('#assayDashboardCards')).to_contain_text('1024.0')
    assert not errors
