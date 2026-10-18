"""Capture real UI states from bundled synthetic data in a disposable runtime.

Run: PYTHONPATH=.deps:. python3 scripts/capture_docs_screenshots.py
Requires Playwright/Chromium and the repository frontend dependencies.
Does not use native.env, the Desktop runtime, private datasets, or a live LLM.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs-site/static/img/screenshots'


def main() -> int:
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
        # Only the bundled fixture is registered. No machine-local registry is read.
        subprocess.run([sys.executable, '-c', """
from app.datasets import DATASET_REGISTRY_PATH, _seed_dataset_records
from app.state_io import atomic_write_json
from app.query_store import prepare_dataset_query_store
atomic_write_json(DATASET_REGISTRY_PATH, [d for d in _seed_dataset_records() if d['dataset_id'] == 'default'])
prepare_dataset_query_store('default')
"""], cwd=ROOT, env=env, check=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                   '--host', '127.0.0.1', '--port', str(port)],
                                  cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url, timeout=1):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Screenshot server stopped before startup.')
                    time.sleep(.2)
            else:
                raise RuntimeError('Screenshot server did not start.')
            OUTPUT.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                context.route('https://cdn.plot.ly/**', lambda route: route.fulfill(
                    path=str(plotly), content_type='application/javascript'))
                page = context.new_page()
                page.goto(url, wait_until='networkidle')
                response = page.request.post(url + '/datasets/select', data={'dataset_ids': ['default']})
                assert response.ok, response.status
                page.reload(wait_until='networkidle')

                def capture(name):
                    page.evaluate('window.scrollTo(0, 0)')
                    page.screenshot(path=str(OUTPUT / name), animations='disabled')

                page.locator('#dashboardTabBtn').click()
                expect(page.locator('#contextCohort')).not_to_contain_text('Loading')
                page.wait_for_timeout(750)
                capture('workspace-shell.png')
                page.locator('#datasetsTabBtn').click()
                expect(page.locator('#datasetPicker [data-dataset-checkbox]')).to_have_count(1)
                capture('datasets-tab.png')
                page.locator('#queryTabBtn').click()
                page.locator('#question').fill('Which patients have Crohn Disease?')
                page.locator('#askBtn').click()
                expect(page.locator('#queryThread .query-thread-turn-assistant').last).to_contain_text('5 patients', timeout=30000)
                capture('query-tab.png')
                page.locator('#queryContextGeneralBtn').click()
                expect(page.locator('#queryContextGeneralBtn')).to_have_attribute('aria-pressed', 'true')
                page.locator('#question').fill('What is infliximab?')
                page.locator('#queryTab .context-mode-switch').screenshot(
                    path=str(OUTPUT / 'query-general-mode.png'), animations='disabled')
                page.locator('#queryContextWorkspaceBtn').click()
                page.locator('#analysisTabBtn').click()
                capture('analysis-tab.png')
                page.locator('#phenoTabBtn').click()
                expect(page.locator('[data-pheno-mode="cohort"]')).to_be_visible()
                expect(page.locator('#phenoStatus')).not_to_have_text('No workspace loaded.')
                capture('pheno-tab.png')
                page.locator('[data-pheno-mode="patient"]').click()
                expect(page.locator('#phenoPatientId')).to_be_visible()
                capture('pheno-patient-setup.png')
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    print('Captured seven synthetic-only screenshots; temporary runtime removed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
