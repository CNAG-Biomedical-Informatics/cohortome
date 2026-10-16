"""Browser download/upload uses the real project endpoints and synthetic workspace."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from playwright.sync_api import sync_playwright, expect


def test_project_download_and_reopen_restores_query_draft(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {k:v for k,v in os.environ.items() if not k.startswith(('COHORTOME_', 'LM_STUDIO_'))}
    env.update(COHORTOME_RUNTIME_ROOT=str(tmp_path / 'runtime'), COHORTOME_AUTH_MODE='none',
               LM_STUDIO_ENABLED='false', COHORTOME_JOBS_REDIS_URL='redis://127.0.0.1:1/0')
    subprocess.run([sys.executable, '-c', 'from app.query_store import prepare_dataset_query_store; prepare_dataset_query_store("default")'],
                   cwd=root, env=env, check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    child = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host','127.0.0.1','--port',str(port)],
                             cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                if httpx.get(url, timeout=1, trust_env=False).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(accept_downloads=True)
            response = page.request.post(url + '/datasets/select', data={'dataset_ids': ['default']})
            assert response.ok, response.text()
            page.route('https://cdn.plot.ly/**', lambda route: route.fulfill(content_type='application/javascript',
                body='window.Plotly={newPlot:async()=>{},react:async()=>{},purge:()=>{},Plots:{resize:()=>{}}};'))
            page.goto(url)
            expect(page.locator('.app-project-section > summary')).to_be_visible(timeout=30000)
            expect(page.locator('#saveProjectBtn')).to_be_hidden()
            page.locator('.app-project-section > summary').click()
            expect(page.locator('#saveProjectBtn')).to_be_visible()
            expect(page.locator('.app-sidebar-account #heroAuthIdentity')).to_have_text('Local user')
            expect(page.locator('#accountAvatar')).to_have_text('LU')
            expect(page.locator('#heroLogoutBtn')).to_be_hidden()
            page.locator('#dashboardTabBtn').click()
            expect(page.locator('#dashboardTabBtn')).to_have_attribute('aria-current', 'page')
            expect(page.locator('#dashboardClinicalBtn')).to_be_visible()
            expect(page.locator('#dashboardTab')).to_be_visible()
            page.locator('#dashboardTabBtn').click()
            expect(page.locator('#dashboardClinicalBtn')).to_be_visible()
            page.set_viewport_size({'width': 1440, 'height': 960})
            expect(page.locator('.app-header .brand-wordmark')).to_have_text('COHORTome')
            assert page.locator('.app-header .hero-powered-by, .app-header .hero-copy p').count() == 0
            assert page.locator('.app-header').bounding_box()['height'] <= 70
            expect(page.locator('.app-icon-rail')).to_be_visible()
            title = page.get_by_role('heading', name='Clinical dashboard', exact=True)
            expect(title).to_be_visible()
            assert title.evaluate('(el) => getComputedStyle(el).fontSize') == '18px'
            page.screenshot(path=str(tmp_path / 'navigation-light.png'))
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.screenshot(path=str(tmp_path / 'navigation-dark.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            expect(page.locator('.app-sidebar')).to_be_hidden()
            assert page.locator('.app-sidebar').evaluate('(el) => el.getBoundingClientRect().right <= innerWidth')
            page.evaluate("document.documentElement.dataset.theme = 'light'")
            page.set_viewport_size({'width': 1440, 'height': 960})
            page.locator('#dashboardPatientsBtn').click()
            patient_search = page.locator('#patientOverviewSearch')
            patient_search.fill('SYN015')
            expect(page.locator('#patientOverviewMatches [role=option]').first).to_be_visible()
            patient_search.press('ArrowDown')
            patient_search.press('Enter')
            expect(page.locator('#patientOverviewDetail h2')).to_have_text('SYN015')
            expect(page.locator('.patient-inventory')).to_contain_text('SYN015:week_0')
            expect(page.locator('.patient-inventory')).to_contain_text('Metadata table')
            expect(page.locator('.patient-inventory th[scope=rowgroup]').first).to_be_visible()
            assert page.locator('.inventory-modality-icon svg').count() > 0
            assert page.locator('.patient-inventory thead th').count() == 5
            page.screenshot(path=str(tmp_path / 'patient-overview.png'))
            patient_search.fill('no-such-synthetic-patient')
            expect(page.locator('#patientOverviewStatus')).to_contain_text('No matching patients')
            expect(page.locator('#patientOverviewDetail')).to_be_empty()
            page.locator('#queryTabBtn').click()
            page.locator('#question').fill('Review the synthetic lupus cohort')
            page.once('dialog', lambda dialog: dialog.accept('Synthetic project'))
            try:
                with page.expect_download(timeout=10000) as download:
                    page.locator('#saveProjectBtn').click()
            except Exception:
                print('Project save status:', page.locator('.app-sidebar-utility [role=status]').inner_text())
                raise
            target = tmp_path / 'review.cohortome'
            download.value.save_as(target)
            project = json.loads(target.read_text())
            assert project['format'] == 'cohortome-project'
            assert project['query_prompt'] == 'Review the synthetic lupus cohort'
            assert project['datasets'][0]['id'] == 'default'
            assert project['analysis_session_id'], page.request.get(url + '/analysis-sessions').text()
            page.locator('#question').fill('Replace this draft')
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('.app-sidebar-utility input[type=file]').set_input_files(target)
            expect(page.locator('#question')).to_have_value('Review the synthetic lupus cohort', timeout=20000)
            expect(page.locator('.app-sidebar-utility [role=status]')).to_contain_text('Opened Synthetic project')
            browser.close()
    finally:
        child.terminate()
        child.wait(timeout=10)
