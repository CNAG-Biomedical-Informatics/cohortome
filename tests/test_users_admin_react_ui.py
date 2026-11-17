from playwright.sync_api import expect

from test_ui_smoke import live_server, page


def test_users_admin_edit_refresh_and_escaped_labels(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.evaluate('''async () => {
      const {createUsersAdminView} = await import('/static/js/react/ui.js');
      const host = document.createElement('div'); host.id = 'usersTest'; document.body.append(host);
      window.usersView = createUsersAdminView(host);
      window.exampleUser = {username:'example',display_name:'<img src=x onerror=alert(1)>',role:'user',groups:['Research']};
      usersView.render([exampleUser]);
    }''')
    card = page.locator('#usersTest [data-auth-user-card]')
    expect(card.locator('img')).to_have_count(0)
    expect(card).to_contain_text('<img src=x onerror=alert(1)>')
    card.locator('summary').click()
    display = card.locator('[data-auth-user-field="display_name"]')
    display.fill('Changed name')
    card.locator('[data-auth-user-field="role"]').select_option('admin')
    card.locator('[data-auth-user-field="enabled"]').uncheck()
    expect(display).to_have_value('Changed name')
    expect(card.locator('[data-auth-user-field="role"]')).to_have_value('admin')
    expect(card.locator('[data-auth-user-field="enabled"]')).not_to_be_checked()
    card.locator('[data-auth-user-field="password"]').fill('temporary-test-password')
    display.evaluate('(el)=>window.originalUserInput=el')
    page.evaluate('usersView.render([{...exampleUser,display_name:"Saved name",role:"admin",enabled:false}])')
    expect(card).to_have_attribute('open','')
    expect(display).to_have_value('Saved name')
    assert display.evaluate('(el)=>el===window.originalUserInput')
    expect(card.locator('[data-auth-user-field="password"]')).to_have_value('')
    page.evaluate('usersView.render([],"User list unavailable.")')
    expect(page.locator('#usersTest')).to_have_text('User list unavailable.')
    assert not errors
