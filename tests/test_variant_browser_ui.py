from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright, expect


def test_variant_browser_layout_filter_detail_and_cohort():
    root = Path(__file__).resolve().parents[1]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1200, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('http://variants.test/', lambda r: r.fulfill(content_type='text/html', body='''
            <link rel="stylesheet" href="/static/app.css"><main style="padding:24px;max-width:1100px;margin:auto">
            <div id="assayOverviewView"><h2>Assays overview</h2><div id="variantPanelCards"></div></div>
            <section id="variantBrowser" class="variant-browser" hidden></section></main>'''))
        page.route('http://variants.test/static/**', lambda r: r.fulfill(
            content_type='text/javascript' if r.request.url.endswith('.js') else 'text/css',
            body=(root / urlparse(r.request.url).path.lstrip('/')).read_text()))
        requests = []
        def api(route):
            url = urlparse(route.request.url)
            params = parse_qs(url.query)
            requests.append(params)
            if url.path.endswith('/panels'):
                payload = [dict(dataset_id='demo', label='Example variant panel', variants=44, samples=100)]
            elif url.path.endswith('/detail'):
                payload = dict(annotation=dict(variant_id='GRCh37:22:100:A:G', assembly='GRCh37', gene='EXAMPLE1',
                    classification='Likely_pathogenic', classification_source='Example annotation', classification_version='1'),
                    provenance=dict(technology='dna_sequencing', method='WGS', input_format='VCF'),
                    counts=dict(reference=95, alternate=3, missing=2, partial=0),
                    members=[dict(dataset_id='demo', patient_id='P1')])
            else:
                payload = dict(total=1, chromosomes=['1','2','22'], classifications=['Likely_pathogenic'], rows=[
                    dict(variant_id='GRCh37:22:100:A:G', chromosome='22', position=100, ref='A', alt='G',
                         gene='EXAMPLE1', classification='Likely_pathogenic', carriers=1)])
            route.fulfill(json=payload)
        page.route('http://variants.test/variants/**', api)
        page.goto('http://variants.test/')
        page.evaluate("async () => {window.variantModule = await import('/static/js/variant_browser.js');}")
        page.evaluate('''async () => {
            const {createVariantBrowser} = window.variantModule;
            window.state = {currentDatasetScopeId:'scope'};
            window.ui = createVariantBrowser({state, escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
                saveIdsAsCohort:async options=>{window.saved = options.members; return true;}});
            await ui.load('scope');
        }''')
        expect(page.locator('#variantBrowser')).to_be_hidden()
        expect(page.get_by_role('heading', name='Assays overview')).to_be_visible()
        assert not any('sort_by' in r for r in requests)
        page.get_by_role('button', name='Browse variants', exact=False).click()
        expect(page.locator('#assayOverviewView')).to_be_hidden()
        expect(page.get_by_role('button', name='GRCh37:22:100:A:G', exact=True)).to_be_visible()
        page.evaluate("window.originalVariantTable = document.querySelector('.variant-results table')")
        page.get_by_role('button', name='Carriers', exact=True).click()
        expect(page.locator('.variant-results')).to_have_attribute('aria-busy', 'false')
        assert page.evaluate("originalVariantTable === document.querySelector('.variant-results table')")
        expect(page.locator('[data-sort="carriers"]')).to_be_focused()
        expect(page.locator('[data-sort="carriers"]')).to_have_text('Carriers ↑')
        assert any(r.get('sort_by') == ['carriers'] for r in requests)
        page.get_by_label('Chromosome', exact=True).select_option('22')
        expect(page.get_by_role('button', name='GRCh37:22:100:A:G', exact=True)).to_be_visible()
        assert any(r.get('chromosome') == ['22'] for r in requests)
        page.get_by_role('button', name='GRCh37:22:100:A:G', exact=True).click()
        expect(page.get_by_role('button', name='Save 1 carrier as a cohort')).to_be_visible()
        page.get_by_text('Provenance and supplied annotations', exact=True).click()
        expect(page.get_by_text('DNA sequencing', exact=True)).to_be_visible()
        page.get_by_role('button', name='Save 1 carrier as a cohort').click()
        expect(page.get_by_text('Saved. Find the cohort in Cohorts.', exact=True)).to_be_visible()
        assert page.evaluate('saved') == [{'dataset_id':'demo', 'patient_id':'P1'}]
        page.screenshot(path='/tmp/cohortome-variant-browser.png', full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.get_by_role('button', name='Close variant details', exact=True).click()
        expect(page.locator('.variant-detail')).to_be_hidden()
        page.get_by_role('button', name='Back to assays', exact=False).click()
        expect(page.locator('#variantBrowser')).to_be_hidden()
        expect(page.get_by_role('heading', name='Assays overview')).to_be_visible()
        expect(page.get_by_role('button', name='Browse variants', exact=False)).to_be_focused()
        page.get_by_role('button', name='Browse variants', exact=False).click()
        expect(page.locator('#variantBrowser')).to_be_visible()
        page.evaluate("state.currentDatasetScopeId='new-scope'")
        page.evaluate("ui.load('new-scope')")
        expect(page.locator('#variantBrowser')).to_be_hidden()
        expect(page.locator('#assayOverviewView')).to_be_visible()
        assert not errors
        browser.close()
