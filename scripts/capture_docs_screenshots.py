"""Capture real UI states from demo data in a disposable runtime.

Run: PYTHONPATH=.deps:. python3 scripts/capture_docs_screenshots.py
Requires Playwright/Chromium and the repository frontend dependencies.
Does not use native.env, the Desktop runtime, or private datasets.
Optional: --llm-url http://HOST:1234/v1 --llm-model MODEL captures a real
General-question reply. Only the example prompt is sent, not dataset records.
Use --walkthrough-video to refresh the small silent multimodal clip and poster.
Use --updated-views for the dataset, patient, assay, variant and multimodal screenshots.
Use --biosamples-demo PATH with the public CINECA + GEUVADIS package for two biosample views.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs-site/static/img/screenshots'


def prepare_variant_example(runtime):
    """Fictional documentation-only panel; never changes the bundled dataset."""
    root = Path(runtime) / 'documentation-demo'
    shutil.copytree(ROOT / 'datasets/synthetic-longitudinal-demo', root)
    manifest = json.loads((root / 'manifest.json').read_text())
    manifest['biosamples'] = {'file': 'biosamples.json'}
    manifest['variants'] = dict(schema_version=1, annotations_file='variants.tsv',
        samples_file='variant-samples.tsv', genotypes_file='genotypes.tsv',
        provenance={'technology': 'synthetic', 'method': 'Fictional documentation example'})
    (root / 'manifest.json').write_text(json.dumps(manifest))
    (root / 'biosamples.json').write_text(json.dumps([
        {'id': f'DOC{i}', 'individualId': f'SYN{i:03}',
         'sampleOriginType': {'id': 'UBERON:0000178', 'label': 'blood'}} for i in range(1, 4)]))
    (root / 'variants.tsv').write_text(
        'variant_id\tassembly\tchromosome\tposition\tref\talt\tgene\tclassification_source\n'
        'DEMO-V1\tFictional\t22\t1000\tA\tG\tDEMO1\tFictional documentation example\n'
        'DEMO-V2\tFictional\t22\t2000\tC\tT\tDEMO2\tFictional documentation example\n')
    (root / 'variant-samples.tsv').write_text('sample_id\tpatient_id\tbiosample_id\n' +
        ''.join(f'DOC{i}\tSYN{i:03}\tDOC{i}\n' for i in range(1, 4)))
    (root / 'genotypes.tsv').write_text(
        'variant_id\tsample_id\tGT\tcall_status\talt_dosage\tploidy\tphased\n' +
        ''.join(f'DEMO-V{v}\tDOC{i}\t0/{int(i == v)}\tcalled\t{int(i == v)}\t2\tfalse\n'
                for v in (1, 2) for i in range(1, 4)))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--llm-url', help='Explicit OpenAI-compatible endpoint for the AI example')
    parser.add_argument('--llm-model', default='openai/gpt-oss-20b')
    parser.add_argument('--updated-views', action='store_true', help='Capture only dataset, patient, assay, variant and multimodal views')
    parser.add_argument('--walkthrough-video', action='store_true', help='Record only the silent multimodal docs walkthrough')
    parser.add_argument('--biosamples-demo', type=Path, help='Public CINECA + GEUVADIS package root; capture only biosample views')
    args = parser.parse_args()
    if args.biosamples_demo:
        args.biosamples_demo = args.biosamples_demo.resolve()
        resource = json.loads((args.biosamples_demo / 'resource.json').read_text())
        if resource.get('dataset_id') != 'cineca-uk1-demo':
            parser.error('--biosamples-demo requires the public CINECA demo package')
        if args.updated_views or args.walkthrough_video:
            parser.error('Choose only one capture mode')
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
        if args.updated_views:
            env['COHORTOME_DOCS_EXAMPLE_ROOT'] = str(prepare_variant_example(runtime))
        if args.biosamples_demo:
            env['COHORTOME_DOCS_EXAMPLE_ROOT'] = str(args.biosamples_demo)
            env['COHORTOME_DOCS_EXAMPLE_NAME'] = 'CINECA UK1 + GEUVADIS demo'
        # Seed bundled fixtures, optionally replacing one with the explicit demo.
        # No machine-local registry is read.
        subprocess.run([sys.executable, '-c', """
from app.datasets import DATASET_REGISTRY_PATH, _seed_dataset_records
from app.state_io import atomic_write_json
from app.query_store import prepare_dataset_query_store
from app.lm import initialize_desktop_default_provider, update_managed_lm_provider
import os
bundled = {'default', 'synthetic-cross-sectional-demo'}
records = [d for d in _seed_dataset_records() if d['dataset_id'] in bundled]
if os.environ.get('COHORTOME_DOCS_EXAMPLE_ROOT'):
    for record in records:
        if record['dataset_id'] == 'default':
            record['root_path'] = os.environ['COHORTOME_DOCS_EXAMPLE_ROOT']
            record['dataset_id'] = 'documentation-demo'
            record['name'] = os.environ.get('COHORTOME_DOCS_EXAMPLE_NAME', 'Fictional documentation demo')
atomic_write_json(DATASET_REGISTRY_PATH, records)
prepare_dataset_query_store('documentation-demo' if os.environ.get('COHORTOME_DOCS_EXAMPLE_ROOT') else 'default')
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
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce',
                    **({'record_video_dir': str(Path(runtime) / 'video'),
                        'record_video_size': {'width': 1440, 'height': 1000}} if args.walkthrough_video else {}))
                context.route('https://cdn.plot.ly/**', lambda route: route.fulfill(
                    path=str(plotly), content_type='application/javascript'))
                page = context.new_page()
                page.goto(bootstrap, wait_until='networkidle')
                initial_dataset = 'documentation-demo' if args.updated_views or args.biosamples_demo else 'default'
                response = page.request.post(url + '/datasets/select', data={'dataset_ids': [initial_dataset]})
                assert response.ok, response.status
                page.reload(wait_until='networkidle')

                captured = []

                if args.walkthrough_video:
                    page.locator('#dashboardTabBtn').click()
                    page.locator('#dashboardMultimodalBtn').click()
                    coverage = page.locator('.multimodal-coverage')
                    expect(coverage.locator('.coverage-result')).to_contain_text('matching patients')
                    page.evaluate('document.fonts.ready')
                    # A visible pointer and click pulse make the real interactions readable.
                    page.evaluate('''() => {
                      const pointer = document.createElement('div');
                      pointer.style.cssText = 'position:fixed;width:14px;height:14px;border:2px solid #2563eb;border-radius:50%;background:#ffffffaa;pointer-events:none;z-index:99999;transform:translate(-50%,-50%)';
                      document.body.append(pointer);
                      document.addEventListener('mousemove', e => {pointer.style.left=e.clientX+'px';pointer.style.top=e.clientY+'px';});
                      document.addEventListener('mousedown', () => pointer.animate([{boxShadow:'0 0 0 0 #2563eb88'}, {boxShadow:'0 0 0 18px #2563eb00'}], {duration:450}));
                    }''')
                    def click_visible(locator):
                        locator.scroll_into_view_if_needed()
                        box = locator.bounding_box()
                        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=18)
                        page.wait_for_timeout(350)
                        locator.click()
                    started = time.monotonic()
                    page.wait_for_timeout(2500)
                    click_visible(coverage.locator('input[value=clinical]'))
                    page.wait_for_timeout(1800)
                    click_visible(coverage.locator('input[value=proteomics]'))
                    expect(coverage.locator('.coverage-result')).to_contain_text('8 matching patients')
                    page.wait_for_timeout(3000)
                    media = ROOT / 'docs-site/static/media'
                    page.screenshot(path=str(media / 'multimodal-cohort-poster.jpg'), type='jpeg', quality=80)
                    click_visible(coverage.locator('.coverage-save'))
                    page.locator('#cohortNameInput').fill('Clinical + proteomics')
                    page.wait_for_timeout(2200)
                    click_visible(page.locator('#cohortNameDialog button[type=submit]'))
                    expect(coverage.locator('.coverage-save-status')).to_contain_text('Cohort saved')
                    page.wait_for_timeout(1800)
                    click_visible(page.locator('#cohortsTabBtn'))
                    expect(page.locator('.cohort-library-card')).to_contain_text('Clinical + proteomics')
                    page.wait_for_timeout(3500)
                    duration = time.monotonic() - started
                    recording = page.video
                    recording_path = recording.path()
                    context.close()
                    # Keep just the recorded interaction, excluding bootstrap/preparation.
                    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-sseof', f'-{duration:.3f}',
                        '-i', str(recording_path), '-an', '-vf', 'scale=1280:-2,fps=25',
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '25', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(media / 'multimodal-cohort.mp4')], check=True)
                    browser.close()
                    print(f'Recorded {duration:.1f}s of real synthetic-data interactions; no audio.')
                    return 0

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

                if args.biosamples_demo:
                    page.locator('#dashboardTabBtn').click()
                    page.locator('#dashboardPatientsBtn').click()
                    expect(page.locator('#patientSampleOriginFilter')).to_be_visible(timeout=30000)
                    page.locator('#patientSampleOrigin').select_option('UBERON:0000178')
                    page.locator('#patientOverviewSearch').fill('HG0009')
                    expect(page.locator('#patientOverviewMatches .patient-open')).to_have_count(3, timeout=30000)
                    capture('dashboard-patients.png', '#dashboardPatientsPanel')
                    page.locator('#patientOverviewSearch').fill('HG00096')
                    expect(page.locator('#patientOverviewMatches .patient-open')).to_have_count(1, timeout=30000)
                    patient = page.get_by_role('button', name='Open patient HG00096', exact=True)
                    expect(patient).to_be_visible(timeout=30000)
                    with page.expect_response(lambda r: '/patient-overview/clinical?' in r.url, timeout=60000) as clinical:
                        patient.click()
                    assert clinical.value.ok, f'Clinical inventory response: {clinical.value.status} {clinical.value.text()[:200]}'
                    inventory = page.locator('[data-patient-inventory]')
                    expect(inventory.locator('.clinical-record')).to_be_visible(timeout=30000)
                    expect(inventory.locator('[data-clarid-toggle]')).to_have_count(3)
                    capture('dashboard-biosamples.png', '[data-patient-inventory]')
                    browser.close()
                    print('Captured patient origins and biosample inventory from the public CINECA demo.')
                    return 0

                if args.updated_views:
                    panel_response = page.request.get(url + '/variants/panels?workspace=documentation-demo')
                    assert panel_response.ok, panel_response.text()
                    assert panel_response.json(), 'Documentation variant panel was not registered'
                    page.locator('#dashboardTabBtn').click()
                    page.locator('#dashboardPatientsBtn').click()
                    expect(page.locator('#patientSampleOriginFilter')).to_be_visible()
                    expect(page.locator('#patientOverviewMatches [data-match]').first).to_be_visible()
                    capture('dashboard-patients.png', '#dashboardPatientsPanel')
                    page.locator('#dashboardAssaysBtn').click()
                    page.locator('#assayModalityTabs button', has_text='Genotyping').click()
                    expect(page.locator('[data-variant-dataset]')).to_be_visible()
                    capture('dashboard-assays.png', '#assayOverviewView')
                    page.locator('[data-variant-dataset]').click()
                    expect(page.locator('.variant-open').first).to_be_visible()
                    page.locator('.variant-open').first.click()
                    expect(page.locator('.variant-fields').first).to_be_visible()
                    capture('variant-browser.png', '#variantBrowser')
                    response = page.request.post(url + '/datasets/select', data={
                        'dataset_ids': ['synthetic-cross-sectional-demo']})
                    assert response.ok
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
                    page.locator('#accountMenuButton').click()
                    page.locator('#adminTabBtn').click()
                    page.locator('#dataTabBtn').click()
                    page.locator('#resourceAdd').click()
                    expect(page.locator('#resourceList [data-resource]').first).to_be_visible()
                    page.locator('#resourceBrowse').click()
                    expect(page.locator('#resourceCatalogueStatus')).to_contain_text('Catalogue refreshed', timeout=20000)
                    page.locator('[data-category="archive"]').click()
                    expect(page.locator('.resource-card:visible')).to_contain_text('CINECA')
                    capture('install-dataset.png', '#resourcePanel')
                    browser.close()
                    print(f'Captured {len(captured)} updated views using fictional documentation data.')
                    return 0

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
