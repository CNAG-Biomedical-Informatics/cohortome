from playwright.sync_api import expect

from test_ui_smoke import live_server, page


def test_branding_waits_for_its_final_navigation_position(page):
    page.evaluate('''() => {
        const brand = document.getElementById('deploymentBrand');
        brand.textContent = 'Example programme';
        brand.hidden = false;
        document.querySelector('.app-sidebar-utility').append(brand);
    }''')
    expect(page.locator('#deploymentBrand')).to_be_hidden()
    page.evaluate('''() => {
        document.querySelector('.app-icon-rail').insertBefore(
            document.getElementById('deploymentBrand'), document.getElementById('projectsMenuBtn'));
    }''')
    expect(page.locator('#deploymentBrand')).to_be_visible()
    page.evaluate("document.getElementById('deploymentBrand').hidden = true")
    expect(page.locator('#deploymentBrand')).to_be_hidden()
