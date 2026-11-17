"""Authentication form regressions with mocked identity/reset endpoints."""
from test_ui_smoke import live_server, page, playwright


def identity(**changes):
    return dict(enabled=True, authenticated=False, mode='local',
                local_login_enabled=True, password_reset_enabled=True, **changes)


def test_react_password_reset_request_retry_and_cancel(page):
    page.route('**/auth/me', lambda r: r.fulfill(json=identity()))
    calls = []

    def request(route):
        calls.append(route.request.post_data_json)
        route.fulfill(status=503 if len(calls) == 1 else 200, json={
            'detail': 'Try again later.', 'message': 'If an account exists, instructions were sent.'})

    page.route('**/auth/password-reset/request', request)
    page.reload(wait_until='networkidle')
    page.locator('#authForgotPasswordBtn').click()
    page.locator('#authPasswordResetIdentifier').fill('fictional-user')
    page.locator('#authPasswordResetRequestBtn').click()
    playwright.expect(page.locator('#authPasswordResetStatus')).to_have_text('Try again later.')
    playwright.expect(page.locator('#authPasswordResetIdentifier')).to_have_value('fictional-user')
    page.locator('#authPasswordResetRequestBtn').click()
    playwright.expect(page.locator('#authPasswordResetStatus')).to_contain_text('If an account exists')
    assert calls == [{'identifier': 'fictional-user'}] * 2
    page.locator('#authPasswordResetCancelBtn').click()
    playwright.expect(page.locator('#authPasswordResetPanel')).to_be_hidden()
    playwright.expect(page.locator('#authLoginBtn')).to_be_visible()


def test_react_password_reset_confirmation_and_oidc_form(page):
    page.route('**/auth/me', lambda r: r.fulfill(json=identity()))
    calls = []
    page.route('**/auth/password-reset/confirm', lambda r: (
        calls.append(r.request.post_data_json), r.fulfill(json={'message': 'Password reset.'})))
    page.goto(page.url.split('?')[0] + '?password_reset_token=fictional-token', wait_until='networkidle')
    page.locator('#authPasswordResetNewPassword').fill('fictional-password')
    page.locator('#authPasswordResetConfirmPassword').fill('different-password')
    page.locator('#authPasswordResetConfirmBtn').click()
    playwright.expect(page.locator('#authPasswordResetStatus')).to_contain_text('same new password twice')
    assert not calls
    page.locator('#authPasswordResetConfirmPassword').fill('fictional-password')
    page.locator('#authPasswordResetConfirmBtn').click()
    playwright.expect(page.locator('#authGateStatus')).to_have_text('Password reset.')
    playwright.expect(page.locator('#authPasswordResetNewPassword')).to_have_value('')
    assert 'password_reset_token' not in page.url
    assert calls == [{'token': 'fictional-token', 'password': 'fictional-password'}]
    page.unroute('**/auth/me')
    page.route('**/auth/me', lambda r: r.fulfill(json={
        'enabled': True, 'authenticated': False, 'mode': 'oidc',
        'local_login_enabled': False, 'password_reset_enabled': False}))
    page.reload(wait_until='networkidle')
    playwright.expect(page.locator('#authOidcLoginBtn')).to_be_visible()
    playwright.expect(page.locator('#authLoginBtn')).to_be_hidden()
    playwright.expect(page.locator('#authForgotPasswordBtn')).to_be_hidden()
