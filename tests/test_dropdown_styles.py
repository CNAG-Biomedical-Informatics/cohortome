from pathlib import Path

from playwright.sync_api import sync_playwright


def test_dropdown_text_and_spacing_match_across_views():
    root = Path(__file__).resolve().parents[1]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 390, 'height': 800})
        page.route('http://controls.test/', lambda route: route.fulfill(
            content_type='text/html', body='''<link rel="stylesheet" href="/static/app.css">
            <main class="app-content">
            <div class="patient-finder"><div class="patient-lookup">
              <label for="patientSampleOrigin">Sample origin</label>
              <select id="patientSampleOrigin"><option>All sample origins</option><option>Blood</option></select>
            </div></div>
            <label class="coverage-match-mode">Patient group<select><option>All patients</option></select></label>
            <div class="patient-search-field"><input id="patientOverviewSearch" type="search" placeholder="Patient ID or ClarID"></div>
            <input id="analysisCatalogDrawerSearch" type="search">
            </main><input id="analysisChatSearch" type="search">
            <div class="user-settings-content"><select><option>System default</option></select></div>'''))
        page.route('http://controls.test/static/**', lambda route: route.fulfill(
            content_type='text/css', body=(root / route.request.url.split('controls.test/')[1]).read_text()))
        page.goto('http://controls.test/', wait_until='networkidle')
        for theme in ['light', 'dark']:
            page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
            styles = page.locator('select').evaluate_all('''elements => elements.map(e => {
              const s = getComputedStyle(e);
              return [s.fontFamily,s.fontSize,s.fontWeight,s.padding,s.borderRadius,s.color,s.backgroundColor];
            })''')
            assert styles[0] == styles[1] == styles[2]
            assert styles[0][1] == '13px'
            searches = page.locator('input[type=search]').evaluate_all('''elements => elements.map(e => {
              const s = getComputedStyle(e);
              return [s.fontFamily,s.fontSize,s.fontWeight,s.paddingTop,s.paddingBottom,s.borderRadius,s.color,s.backgroundColor,s.height];
            })''')
            assert searches[0] == searches[1] == searches[2]
            assert searches[0][1] == '13px'
            assert 36 <= float(searches[0][-1].removesuffix('px')) < 37
            assert page.locator('#patientOverviewSearch').evaluate('e => getComputedStyle(e).paddingLeft') == '38px'
        page.locator('#patientSampleOrigin').select_option(label='Blood')
        assert page.locator('#patientSampleOrigin').input_value() == 'Blood'
        browser.close()
