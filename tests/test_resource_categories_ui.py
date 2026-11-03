from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def test_catalogue_type_badges_filters_and_refresh():
    root = Path(__file__).resolve().parents[1]
    resources = [dict(dataset_id=mode, install_mode=mode, name=name, version='1',
                      description='Example', terms='Example terms', modality_keys=['clinical'], modalities='Clinical',
                      included=mode == 'included', compatible=True, archive_bytes=100, source_bytes=100)
                 for mode, name in [('included','Demo'), ('archive','Prepared study'), ('source','Source study')]]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route('http://resources.test/', lambda r: r.fulfill(content_type='text/html', body=
            '<link rel="stylesheet" href="/static/app.css">' + (root / 'templates/partials/data_management.html').read_text()))
        page.route('http://resources.test/static/**', lambda r: r.fulfill(
            content_type='text/javascript' if r.request.url.endswith('.js') else 'text/css',
            body=(root / urlparse(r.request.url).path.lstrip('/')).read_text()))
        def api(route):
            route.fulfill(json={'jobs': []} if route.request.url.endswith('/jobs') else
                dict(resources=resources, repository='example/store', catalogue_source='cached'))
        page.route('http://resources.test/resources**', api)
        page.goto('http://resources.test/')
        page.evaluate('''async () => {
          const {createResourceInstaller} = await import('/static/js/resource_install.js');
          window.ui = createResourceInstaller({escapeHtml:s=>String(s), refresh:async()=>{}, select:()=>{}});
          ui.setAllowed(true);
        }''')
        page.locator('#resourceAdd').click()
        expect(page.locator('.resource-card:visible')).to_have_count(3)
        expect(page.locator('.resource-install-kind svg')).to_have_count(3)
        page.locator('[data-category="included"]').click()
        expect(page.locator('.resource-card:visible')).to_have_count(1)
        expect(page.locator('.resource-card:visible')).to_contain_text('No download needed')
        expect(page.locator('.resource-card:visible button')).to_be_disabled()
        page.locator('[data-category="archive"]').click()
        expect(page.locator('.resource-card:visible')).to_contain_text('Ready to install')
        expect(page.locator('.resource-card:visible button')).to_have_text('↓ Download and install')
        page.locator('#resourceBrowse').click()
        expect(page.locator('[data-category="archive"]')).to_have_attribute('aria-pressed', 'true')
        page.locator('[data-category="source"]').click()
        expect(page.locator('.resource-card:visible button')).to_have_text('↓ Fetch and prepare')
        resources.pop()
        page.locator('#resourceBrowse').click()
        expect(page.locator('#resourceFilterEmpty')).to_be_visible()
        page.locator('[data-category="all"]').click()
        expect(page.locator('.resource-card:visible')).to_have_count(2)
        browser.close()
