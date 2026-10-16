"""Synthetic DOM check: desktop wording and shared compact action styles."""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright, expect


def test_desktop_access_controls_and_shared_button_sizes():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'static/js/datasets_ui.js').read_text()
    imports = re.findall(r'@import "\./([^"]+)";', (root / 'static/app.css').read_text())
    styles = '\n'.join((root / 'static' / name).read_text() for name in imports)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content('<main class="app-content">'
                         '<div id="picker"></div><div id="admin"></div>'
                         '<button id="blue" class="query-chip action">Apply workspace</button>'
                         '<button id="red" style="background:red">Delete run</button></main>'
                         '<div class="job-completion-notice"><button id="viewRuns">View runs</button><button id="dismiss">Dismiss</button></div>')
        page.add_style_tag(content=styles)
        setup = '''async ({source, desktop}) => {
          delete window.__COHORTOME_DESKTOP__;
          document.documentElement.dataset.deployment = desktop ? 'desktop' : 'web';
          const {createDatasetsUi} = await import(URL.createObjectURL(new Blob([source], {type:'text/javascript'})));
          const ui = createDatasetsUi({refs: {datasetPickerEl:document.querySelector('#picker'),
            datasetAdminListEl:document.querySelector('#admin')},
            state: {currentDatasetIds:[], pendingDatasetIds:[], datasetAdminFeedback:{}, availableDatasets:[{
              dataset_id:'demo', visibility:'all_authenticated', allowed_users:['tester'], allowed_groups:['team'],
              data_classification:'private', query_granularity_ceiling:'summary', ai_provider_access:'blocked'}]},
            helpers:{escapeHtml: s => String(s)}, callbacks:{canManageDataset:()=>true}});
          ui.renderDatasetPicker(); ui.renderDatasetAdminList();
          document.querySelector('#admin details').open = true;
        }'''
        page.evaluate(setup, {'source': source, 'desktop': True})
        expect(page.locator('#picker')).to_contain_text('Available in this desktop workspace')
        for field in ('visibility', 'users', 'groups'):
            expect(page.locator(f'[data-dataset-{field}]')).to_be_hidden()
        for field in ('classification', 'query-granularity', 'ai-provider-access'):
            expect(page.locator(f'[data-dataset-{field}]')).to_be_visible()
        for button in ('blue', 'red', 'viewRuns', 'dismiss'):
            assert page.locator(f'#{button}').evaluate('(el)=>getComputedStyle(el).fontSize') == '13px'
            assert page.locator(f'#{button}').evaluate('(el)=>getComputedStyle(el).borderRadius') == '8px'
        page.evaluate(setup, {'source': source, 'desktop': False})
        expect(page.locator('#picker')).to_contain_text('All authenticated users')
        for field in ('visibility', 'users', 'groups'):
            expect(page.locator(f'[data-dataset-{field}]')).to_be_visible()
        browser.close()
