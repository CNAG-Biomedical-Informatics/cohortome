"""Clean desktop first use and same-installation resume with real synthetic data."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture
def desktop_page(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith(('COHORTOME_', 'LM_STUDIO_'))}
    env['PYTHONPATH'] = os.pathsep.join([str(root / '.deps'), str(root)])
    with (tmp_path / 'server.log').open('w') as log:
        child = subprocess.Popen([sys.executable, str(root / 'desktop/server.py'),
                                  '--runtime-dir', str(tmp_path / 'runtime')], cwd=root, env=env,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True)
        try:
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(child.stdout.readline()), daemon=True).start()
            url = json.loads(ready.get(timeout=40))['url']
            with sync_playwright() as p:
                browser = p.chromium.launch()
                origin = urlsplit(url)
                page = browser.new_page(base_url=f'{origin.scheme}://{origin.netloc}',
                                        viewport={'width': 1440, 'height': 960}, accept_downloads=True)
                page.set_default_timeout(15000)
                page.goto(url)
                expect(page.locator('[data-open-demo]')).to_be_visible(timeout=30000)
                yield page
                browser.close()
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)


def test_demo_coverage_and_analysis_resume(desktop_page, tmp_path):
    page = desktop_page
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.screenshot(path=str(tmp_path / 'welcome.png'))
    page.locator('[data-open-demo]').click()
    expect(page.locator('#contextCohort')).to_contain_text('90 patients', timeout=30000)
    dataset = 'synthetic-cross-sectional-demo'
    coverage = page.request.get('/patient-overview/coverage', params={'workspace': dataset}).json()['patients']
    groups = {}
    for disease, name in [('Systemic Lupus Erythematosus', 'SLE'), ('Healthy Control', 'Controls')]:
        members = [dict(dataset_id=p['dataset_id'], patient_id=p['patient_id'])
                   for p in coverage if disease in p['diseases']]
        assert len(members) == 30
        response = page.request.post('/saved-cohorts', data={
            'name': name, 'dataset_id': dataset, 'members': members, 'id_type': 'patient',
            'source_kind': 'manual', 'source_prompt': 'Synthetic release test'})
        assert response.ok, response.text()
        groups[name] = response.json()
    page.reload(wait_until='networkidle')
    page.locator('#dashboardMultimodalBtn').click()
    host = page.locator('.multimodal-coverage')
    expect(page.locator('#multimodalReadinessStatus')).to_be_hidden()
    title_box = page.locator('.multimodal-heading > h3').bounding_box()
    help_box = page.locator('.multimodal-heading .inline-view-help > summary').bounding_box()
    assert abs(title_box['y'] + title_box['height'] / 2 - help_box['y'] - help_box['height'] / 2) < 2
    expect(page.locator('#multimodalCompareShortcut')).to_be_hidden()
    page.locator('#multimodalMoreOptions > summary').click()
    expect(page.locator('#multimodalCompareShortcut')).to_be_visible()
    page.locator('#multimodalMoreOptions > summary').click()
    page.get_by_label('About multimodal coverage', exact=True).click()
    expect(page.locator('#multimodalReadinessSummary')).to_contain_text('data types checked')
    page.get_by_label('About multimodal coverage', exact=True).click()
    expect(host.locator('.coverage-result')).to_contain_text('90 matching patients')
    host.locator('[data-disease="Systemic Lupus Erythematosus"]').click()
    host.locator('input[value=transcriptomics]').check()
    host.locator('input[value=methylation]').check()
    expect(host.locator('.coverage-result')).to_contain_text('28 matching patients')
    page.screenshot(path=str(tmp_path / 'coverage.png'), full_page=True)
    host.locator('[data-disease=""]').click()
    host.locator('.coverage-cohort').select_option(groups['SLE']['id'])
    expect(host.locator('.coverage-result')).to_contain_text('28 matching patients')
    host.locator('.coverage-save').click()
    page.locator('#cohortNameInput').fill('SLE RNA methylation')
    page.locator('#cohortNameDialog button[type=submit]').click()
    expect(host.locator('.coverage-save-status')).to_contain_text('Cohort saved')
    saved = page.request.get('/saved-cohorts', params={'dataset_id': dataset}).json()['cohorts']
    narrowed = next(c for c in saved if c['name'] == 'SLE RNA methylation')
    assert narrowed['patient_count'] == 28
    assert {(m['dataset_id'], m['patient_id']) for m in narrowed['members']} <= {
        (m['dataset_id'], m['patient_id']) for m in groups['SLE']['members']}

    page.locator('#cohortsTabBtn').click()
    card = page.locator('.cohort-library-card').filter(has=page.get_by_text('SLE', exact=True))
    card.locator('[data-saved-cohort-action=load-analysis]').click()
    page.locator('#analysisMethodSelect').select_option('catalog:transcriptomics-limma-voom-differential-expression')
    # Choose B using the existing saved-cohort setup panel.
    page.locator('[data-analysis-setup-action=choose-cohort-b]').first.click()
    page.locator(f'#savedCohorts [data-saved-cohort-action=load-analysis-b][data-saved-cohort-id="{groups["Controls"]["id"]}"]').click()
    expect(page.locator('#analysisCurrentChatMeta')).to_contain_text('A: 30 patients vs B: 30 patients')
    expect(page.locator('#analysisDatasetScope')).to_contain_text('Synthetic cross-sectional demo')
    expect(page.locator('#analysisFlowBar')).to_contain_text('limma-voom')
    page.locator('#projectsMenuBtn').click()
    page.once('dialog', lambda dialog: dialog.accept('Resume test'))
    with page.expect_download() as result:
        page.locator('#saveProjectBtn').click()
    project_path = tmp_path / 'resume.cohortome'
    result.value.save_as(project_path)
    project = json.loads(project_path.read_text())
    session = next(s for s in page.request.get('/analysis-sessions').json()['sessions']
                   if s['id'] == project['analysis_session_id'])
    assert session['catalog_item_id'] == 'transcriptomics-limma-voom-differential-expression'
    assert len(session['assay_ids']) == 1
    page.reload(wait_until='networkidle')
    expect(page.locator('#analysisFlowBar')).to_contain_text('limma-voom')
    page.locator('#projectsMenuBtn').click()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#projectsMenu input[type=file]').set_input_files(project_path)
    expect(page.locator('.app-project-status')).to_contain_text('Opened Resume test')
    expect(page.locator('#analysisMethodSelect')).to_have_value('catalog:transcriptomics-limma-voom-differential-expression')
    expect(page.locator('#analysisFlowBar [data-analysis-flow-target=requirements]')).to_contain_text('Ready')
    expect(page.locator('#analysisCurrentChatMeta')).to_contain_text('A: 30 patients vs B: 30 patients')
    # Exercise automatic job hydration, not only the manual Open result action.
    job = {'job_id': 'journey-job', 'status': 'queued', 'result_available': False,
           'feature': 'analysis', 'job_type': 'analysis', 'name': 'Synthetic status check'}
    def submit(route):
        job['analysis_session_id'] = route.request.post_data_json['analysis_session_id']
        route.fulfill(json={'intent': 'analysis_job', 'reply': 'Submitted test job.',
                           'data': {'execution': 'queued', 'job_status': 'queued', 'job_id': job['job_id']}})
    page.route('**/analysis', submit)
    page.route('**/jobs', lambda route: route.fulfill(json={'jobs': [job]}))
    page.route('**/jobs/journey-job', lambda route: route.fulfill(json={**job, 'artifacts': [],
        'result_payload': {'intent': 'analysis_external_rscript', 'reply': 'Synthetic job completed.',
                           'data': {'execution': 'external_runner', 'source': 'deterministic'}}}))
    page.locator('#analysisRunBtn').click()
    expect(page.locator('#analysisFlowBar')).to_contain_text('Job queued')
    job.update(status='completed', result_available=True)
    expect(page.locator('#analysisThread')).to_contain_text('Synthetic job completed.', timeout=15000)
    expect(page.locator('#analysisFlowBar')).to_contain_text('Completed')
    expect(page.locator('#analysisComposerStatus')).to_contain_text('completed')
    page.locator('#jobsDrawerCloseBtn').click()
    assert errors == []


def test_demo_preparation_failure_can_retry(desktop_page):
    page = desktop_page
    path = '**/datasets/synthetic-cross-sectional-demo/prepare-store'
    page.route(path, lambda route: route.fulfill(status=503, json={'detail': 'Preparation temporarily unavailable.'}))
    page.locator('[data-open-demo]').click()
    expect(page.locator('.workspace-welcome [role=status]')).to_have_text('Preparation temporarily unavailable.')
    expect(page.locator('[data-open-demo]')).to_be_enabled()
    page.unroute(path)
    page.locator('[data-open-demo]').click()
    expect(page.locator('#contextCohort')).to_contain_text('90 patients', timeout=30000)


def test_bundled_dataset_is_prepared_when_workspace_is_applied(desktop_page):
    page = desktop_page
    requested = []
    page.on('request', lambda request: requested.append(request.url)
            if request.url.endswith('/datasets/default/prepare-store') else None)
    page.locator('#datasetsTabBtn').click()
    page.locator("#datasetPicker [data-dataset-checkbox='default']").check()
    expect(page.locator('#loadBtn')).to_be_enabled()
    page.locator('#loadBtn').evaluate('(button) => button.click()')
    expect(page.locator('#loadStatus')).to_contain_text('Loaded', timeout=30000)
    expect(page.locator('#contextDatasets')).to_contain_text('Synthetic longitudinal demo')
    assert len(requested) == 1
    dataset = next(item for item in page.request.get('/datasets').json()['datasets']
                   if item['dataset_id'] == 'default')
    assert dataset['query_store_status']['ready'] is True


def test_patient_filters_handoff_to_multimodal(desktop_page):
    page = desktop_page
    page.locator('[data-open-demo]').click()
    expect(page.locator('#loadStatus')).to_contain_text('Loaded 90 patients', timeout=30000)
    page.locator('#dashboardPatientsBtn').click()
    page.locator('#patientDiseaseFilters [data-disease="Systemic Lupus Erythematosus"]').click()
    expect(page.locator('#patientSaveCohort')).to_contain_text('Save 30 patients')
    expect(page.locator('#patientOverviewMatches tbody tr')).to_have_count(20)
    page.locator('#patientRefineMultimodal').click()
    host = page.locator('.multimodal-coverage')
    expect(host.locator('.coverage-cohort')).to_have_value('patient-filter')
    expect(host.locator('[data-disease="Systemic Lupus Erythematosus"]')).to_have_attribute('aria-pressed', 'true')
    expect(host.locator('[data-disease="Systemic Lupus Erythematosus"] .badge')).to_have_text('30')
    expect(host.locator('.coverage-diseases .badge')).to_have_count(3)
    expect(host.locator('[data-disease=""]')).to_have_attribute('aria-pressed', 'false')
    expect(host.locator('.coverage-result')).to_contain_text('30 matching patients')
    expect(host.locator('.coverage-start-description')).to_contain_text('Systemic Lupus Erythematosus')
    host.locator('input[value=transcriptomics]').check()
    host.locator('input[value=methylation]').check()
    expect(host.locator('.coverage-result')).to_contain_text('28 matching patients')
    # Returning to Patients and narrowing by ID must replace, not merge, the handoff.
    page.locator('#dashboardPatientsBtn').click()
    page.locator('#patientOverviewSearch').fill('DEMOAI30031')
    expect(page.locator('#patientSaveCohort')).to_contain_text('Save 1 patient')
    page.locator('#patientRefineMultimodal').click()
    expect(host.locator('.coverage-result')).to_contain_text('1 matching patients')
    expect(host.locator('.coverage-start-description')).to_contain_text('ID/ClarID search: DEMOAI30031')
    expect(host.locator('.coverage-selectors input:checked')).to_have_count(0)
    host.locator('.coverage-cohort').select_option('')
    expect(host.locator('.coverage-result')).to_contain_text('90 matching patients')
    expect(host.locator('.coverage-start-description')).to_be_hidden()
    expect(host.locator('[data-disease=""]')).to_have_attribute('aria-pressed', 'true')
