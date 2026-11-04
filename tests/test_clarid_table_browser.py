from pathlib import Path
import pytest

from playwright.sync_api import sync_playwright, expect


@pytest.mark.parametrize('table_class', ['query-result-table', 'patient-inventory'])
def test_query_clarid_opens_once_without_resizing_table(table_class):
    root = Path(__file__).resolve().parents[1]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        page.route("http://clarid.test/", lambda r: r.fulfill(
            content_type="text/html", body=f'<div class="query-result-table-scroll"><table class="{table_class}"><tbody><tr><td>Patient 1</td><td id="identity"></td><td>Female</td></tr></tbody></table></div>'))
        page.route("http://clarid.test/static/js/**", lambda r: r.fulfill(
            content_type="text/javascript", body=(root / "static/js" / r.request.url.rsplit("/", 1)[-1]).read_text()))
        page.goto("http://clarid.test/")
        for css in ("dashboard.css", "query-core.css"):
            page.add_style_tag(content=(root / "static/css" / css).read_text())
        page.evaluate('''async (biosample) => {
          const {createDashboardUi} = await import('/static/js/dashboard.js');
          window.ui = createDashboardUi({refs:{}, helpers:{escapeHtml:s=>String(s)},
            callbacks:{}, state:{}, constants:{}});
          const {claridMarkup} = await import('/static/js/clarid.js');
          const clarid = {
            human_id:'COH-SYN-example', stub_id:'example', subject_id:1,
            condition:'R69', condition_name:'Unspecified illness'};
          document.querySelector('#identity').innerHTML = biosample
            ? claridMarkup({...clarid, entity:'biosample', tissue:'Blood'}, String, true)
            : ui.claridIdentityMarkup({clarid}, true);
          document.addEventListener('click', e=>ui.handleClaridAction(e));
        }''', table_class == 'patient-inventory')
        cell = page.locator('#identity')
        before = cell.bounding_box()
        badge = page.locator('[data-clarid-toggle]')
        badge.click()
        expect(badge).to_have_attribute('aria-expanded', 'true')
        expect(page.get_by_role('dialog')).to_be_visible()
        assert page.locator('.clarid-popover').evaluate('(e)=>e.matches(":popover-open")')
        assert cell.bounding_box() == before
        badge.click()
        expect(badge).to_have_attribute('aria-expanded', 'false')
        expect(page.get_by_role('dialog')).to_be_hidden()
        badge.focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('dialog')).to_be_visible()
        page.evaluate('ui.closeClaridPopovers()')
        expect(page.get_by_role('dialog')).to_be_hidden()
        browser.close()
