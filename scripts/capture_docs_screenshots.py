"""Capture real UI states from bundled synthetic data in a disposable runtime.

Run: PYTHONPATH=.deps:. python3 scripts/capture_docs_screenshots.py
Requires Playwright/Chromium and the repository frontend dependencies.
Does not use native.env, the Desktop runtime, or private datasets.
Optional: --llm-url http://HOST:1234/v1 --llm-model MODEL captures a real
General-question reply. Only the example prompt is sent, not dataset records.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs-site/static/img/screenshots'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--llm-url', help='Explicit OpenAI-compatible endpoint for the AI example')
    parser.add_argument('--llm-model', default='openai/gpt-oss-20b')
    args = parser.parse_args()
    plotly = ROOT / 'node_modules/plotly.js-dist-min/plotly.min.js'
    if not plotly.is_file():
        raise RuntimeError('Install the repository frontend dependencies first (npm ci).')
    with tempfile.TemporaryDirectory(prefix='cohortome-docs-') as runtime:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('COHORTOME_', 'LM_STUDIO_', 'UVICORN_'))}
        env.update(PYTHONPATH=os.pathsep.join([str(ROOT / '.deps'), str(ROOT)]),
                   COHORTOME_RUNTIME_ROOT=runtime, COHORTOME_AUTH_MODE='none',
                   COHORTOME_DESKTOP_MODE='true', COHORTOME_JOBS_BACKEND='local',
                   COHORTOME_JOBS_REDIS_URL='redis://127.0.0.1:1/0',
                   COHORTOME_SESSION_SECRET=secrets.token_urlsafe(32), LM_STUDIO_ENABLED='false')
        if args.llm_url:
            env.update(LM_STUDIO_ENABLED='true', LM_STUDIO_BASE_URL=args.llm_url,
                       LM_STUDIO_MODEL=args.llm_model, LM_STUDIO_TIMEOUT='120')
        # Only the two bundled fixtures are registered. No machine-local registry is read.
        subprocess.run([sys.executable, '-c', """
from app.datasets import DATASET_REGISTRY_PATH, _seed_dataset_records
from app.state_io import atomic_write_json
from app.query_store import prepare_dataset_query_store
from app.lm import initialize_desktop_default_provider, update_managed_lm_provider
import os
bundled = {'default', 'synthetic-cross-sectional-demo'}
atomic_write_json(DATASET_REGISTRY_PATH, [d for d in _seed_dataset_records() if d['dataset_id'] in bundled])
prepare_dataset_query_store('default')
prepare_dataset_query_store('synthetic-cross-sectional-demo')
initialize_desktop_default_provider()
if os.environ.get('LM_STUDIO_ENABLED') == 'true':
    update_managed_lm_provider('system-default', {
        'enabled': True, 'base_url': os.environ['LM_STUDIO_BASE_URL'],
        'model': os.environ['LM_STUDIO_MODEL'], 'timeout_seconds': 120,
        'data_boundary': 'external'})
"""], cwd=ROOT, env=env, check=True)
        # Use the real desktop bootstrap, including its local-owner session.
        server = subprocess.Popen([sys.executable, str(ROOT / 'desktop/server.py'),
                                   '--runtime-dir', runtime], cwd=ROOT, env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True)
        try:
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(server.stdout.readline()), daemon=True).start()
            bootstrap = json.loads(ready.get(timeout=40))['url']
            origin = urlsplit(bootstrap)
            url = f'{origin.scheme}://{origin.netloc}'
            OUTPUT.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                context.route('https://cdn.plot.ly/**', lambda route: route.fulfill(
                    path=str(plotly), content_type='application/javascript'))
                page = context.new_page()
                page.goto(bootstrap, wait_until='networkidle')
                response = page.request.post(url + '/datasets/select', data={'dataset_ids': ['default']})
                assert response.ok, response.status
                page.reload(wait_until='networkidle')

                captured = []

                def capture(name, selector=None):
                    page.evaluate("""() => {
                      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
                      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
                      document.documentElement.scrollTop = 0;
                      document.body.scrollTop = 0;
                      for (const selector of ['.app-sidebar', '.app-sidebar-nav', '.app-content']) {
                        const element = document.querySelector(selector);
                        if (element) element.scrollTop = 0;
                      }
                    }""")
                    page.wait_for_timeout(100)
                    page.evaluate('document.fonts.ready')
                    target = page.locator(selector) if selector else page
                    target.screenshot(path=str(OUTPUT / name), animations='disabled')
                    captured.append(name)
                    print(f'Captured {name}', flush=True)

                page.locator('#dashboardTabBtn').click()
                expect(page.locator('#contextCohort')).not_to_contain_text('Loading')
                page.wait_for_timeout(750)
                capture('workspace-shell.png')
                page.locator('#dashboardPatientsBtn').click()
                expect(page.locator('#patientOverviewMatches [data-match]').first).to_be_visible()
                capture('dashboard-patients.png', '#dashboardPatientsPanel')
                page.locator('#patientDiseaseFilters [data-disease="Crohn Disease"]').click()
                expect(page.locator('#patientSaveCohort')).to_contain_text('Save 5 patients')
                page.locator('#patientOverviewMatches [data-match]').first.click()
                expect(page.locator('[data-patient-inventory]')).to_be_visible()
                capture('dashboard-patient-visits.png', '[data-patient-inventory]')
                page.locator('#dashboardAssaysBtn').click()
                expect(page.locator('#dashboardAssaysPanel')).to_be_visible()
                page.wait_for_timeout(750)
                capture('dashboard-assays.png', '#assayDashboardOverview')
                page.locator('#datasetsTabBtn').click()
                expect(page.locator('#datasetPicker [data-dataset-checkbox]')).to_have_count(2)
                capture('datasets-tab.png')
                page.locator('#queryTabBtn').click()
                page.locator('#question').fill('Which patients have Crohn Disease?')
                page.locator('#askBtn').click()
                expect(page.locator('#queryThread .query-thread-turn-assistant').last).to_contain_text('5 patients', timeout=30000)
                capture('query-tab.png')
                page.locator('#queryContextGeneralBtn').click()
                expect(page.locator('#queryContextGeneralBtn')).to_have_attribute('aria-pressed', 'true')
                page.locator('#question').fill('What is infliximab?')
                capture('query-general-mode.png', '#queryTab .context-mode-switch')
                page.locator('#queryContextWorkspaceBtn').click()
                page.locator('#analysisTabBtn').click()
                capture('analysis-tab.png')
                page.locator('#analysisMethodSelect').select_option('summary')
                expect(page.locator('#analysisRunBtn')).to_be_enabled()
                page.locator('#analysisRunBtn').click()
                expect(page.locator('#analysisThread .analysis-turn-assistant').last).to_be_visible(timeout=60000)
                capture('analysis-result.png', '#analysisThread .analysis-turn-assistant:last-child')
                page.locator('#phenoTabBtn').click()
                expect(page.locator('[data-pheno-mode="cohort"]')).to_be_visible()
                expect(page.locator('#phenoStatus')).not_to_have_text('No workspace loaded.')
                capture('pheno-tab.png')
                page.locator('[data-pheno-mode="patient"]').click()
                expect(page.locator('#phenoPatientId')).to_be_visible()
                capture('pheno-patient-setup.png')

                response = page.request.post(url + '/datasets/select', data={
                    'dataset_ids': ['synthetic-cross-sectional-demo']})
                assert response.ok, response.status
                page.reload(wait_until='networkidle')
                page.locator('#dashboardTabBtn').click()
                page.locator('#dashboardMultimodalBtn').click()
                coverage = page.locator('.multimodal-coverage')
                expect(coverage.locator('.coverage-result')).to_contain_text('90 matching patients')
                coverage.locator('[data-disease="Systemic Lupus Erythematosus"]').click()
                coverage.locator('input[value=transcriptomics]').check()
                coverage.locator('input[value=methylation]').check()
                expect(coverage.locator('.coverage-result')).to_contain_text('28 matching patients')
                capture('multimodal-selection.png', '.multimodal-coverage')
                coverage.locator('.coverage-save').click()
                page.locator('#cohortNameInput').fill('SLE with RNA and methylation')
                capture('save-cohort.png', '#cohortNameDialog')
                page.locator('#cohortNameDialog button[type=submit]').click()
                expect(coverage.locator('.coverage-save-status')).to_contain_text('Cohort saved')
                page.locator('#cohortsTabBtn').click()
                expect(page.locator('.cohort-library-card')).to_be_visible()
                capture('cohort-library.png', '.cohort-library-card')
                page.locator('.cohort-library-more > summary').click()
                page.locator('#cohortsTab [data-saved-cohort-action="export-molecular"]').click()
                expect(page.locator('#cohortExportDialog .cohort-export-option').first).to_be_visible()
                capture('cohort-export.png', '#cohortExportDialog')
                page.locator('#cohortExportDialog [data-close]').click()
                page.locator('#accountMenuButton').click()
                page.locator('#adminTabBtn').click()
                page.locator('#dataTabBtn').click()
                page.locator('#resourceAdd').click()
                expect(page.locator('#resourceList [data-resource]').first).to_be_visible()
                capture('install-dataset.png', '#resourcePanel')
                page.locator('#resourceClose').click()

                if args.llm_url:
                    page.locator('#queryTabBtn').click()
                    page.locator('#queryContextGeneralBtn').click()
                    page.locator('#question').fill(
                        'In two short sentences, explain what infliximab is and its mechanism of action. '
                        'This is general research background, not treatment advice.')
                    with page.expect_response(lambda r: r.request.method == 'POST' and '/llm/general' in r.url,
                                              timeout=180000):
                        page.locator('#askBtn').click()
                    reply = page.locator('#queryThread .query-thread-turn-assistant').last
                    expect(reply).to_contain_text('infliximab', ignore_case=True, timeout=180000)
                    capture('query-llm-answer.png')
                browser.close()
        finally:
            server.stdin.close()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    print(f'Captured {len(captured)} screenshots from synthetic-only state; temporary runtime removed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
