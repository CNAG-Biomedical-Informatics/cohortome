from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")


def test_deployment_branding_admin_preview_persistence_and_researcher_access(page_auth):
    from test_deployment_branding import png
    import base64
    page = page_auth
    expect = playwright.expect
    base = page.url.rstrip('/')
    assert page.request.post(base + '/auth/login', data={'username': 'admin', 'password': 'secret'}).ok
    page.reload(wait_until='networkidle')
    original_logo = page.locator('#appShell .hero-logo').get_attribute('src')
    if not page.locator("#adminTabBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#adminTabBtn').click()
    page.locator('#deploymentAppearanceBtn').click()
    page.locator('#deploymentBrandName').fill('Test programme')
    page.locator('#deploymentBrandWebsite').fill('https://example.org/')
    page.locator('#deploymentBrandFile').set_input_files({'name': 'logo.png', 'mimeType': 'image/png',
        'buffer': base64.b64decode(png().split(',')[1])})
    expect(page.locator('#deploymentBrandPreview img')).to_be_visible()
    expect(page.locator('#deploymentBrand')).to_be_hidden()
    page.locator('#deploymentBrandSave').click()
    expect(page.locator('#deploymentBrandStatus')).to_contain_text('Branding saved')
    page.locator('#deploymentAppearanceClose').click()
    page.reload(wait_until='networkidle')
    expect(page.locator('#deploymentBrand')).to_contain_text('Test programme')
    expect(page.locator('#deploymentBrand a')).to_have_attribute('href', 'https://example.org/')
    expect(page.locator('#appShell .hero-logo')).to_have_attribute('src', original_logo)
    assert page.request.post(base + '/auth/login', data={'username': 'researcher', 'password': 'secret'}).ok
    page.reload(wait_until='networkidle')
    expect(page.locator('#deploymentAppearanceBtn')).to_be_hidden()
    expect(page.locator('#deploymentBrand')).to_contain_text('Test programme')
    assert page.request.delete(base + '/deployment-branding').status == 403
    assert page.request.put(base + '/deployment-branding', data={'name': 'Denied', 'logo': png()}).status == 403
    # Logo and long names remain within the narrow sidebar on mobile/dark mode.
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    expect(page.locator('#deploymentBrand')).to_be_visible()
    assert page.locator('#deploymentBrand').evaluate('el => el.scrollWidth <= el.clientWidth')
    assert page.request.post(base + '/auth/login', data={'username': 'admin', 'password': 'secret'}).ok
    page.reload(wait_until='networkidle')
    if not page.locator("#adminTabBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#adminTabBtn').click(); page.locator('#deploymentAppearanceBtn').click()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#deploymentBrandRemove').click()
    expect(page.locator('#deploymentBrandStatus')).to_contain_text('removed')
    expect(page.locator('#deploymentBrand')).to_be_hidden()
    page.reload(wait_until='networkidle')
    expect(page.locator('#deploymentBrand')).to_be_hidden()


def test_appearance_saves_reloads_and_follows_system(page):
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#userSettingsBtn').click()
    page.locator('[data-settings-section="appearance"]').click()
    page.locator('#settingsAppearance').select_option('dark')
    page.locator('#userSettingsSaveBtn').click()
    page.wait_for_function('document.documentElement.dataset.theme === "dark"')
    page.reload(wait_until='networkidle')
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#userSettingsBtn').click()
    page.locator('[data-settings-section="appearance"]').click()
    page.locator('#settingsAppearance').select_option('system')
    page.locator('#userSettingsSaveBtn').click()
    page.wait_for_function('document.documentElement.dataset.appearance === "system"')
    page.emulate_media(color_scheme='dark')
    page.wait_for_function('document.documentElement.dataset.theme === "dark"')
    page.emulate_media(color_scheme='light')
    page.wait_for_function('document.documentElement.dataset.theme === "light"')
    page.request.patch(page.url.rstrip('/') + '/user-settings', data={'appearance': 'light'})


def test_plot_palette_settings_save_reload_and_reset(page):
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#userSettingsBtn').click()
    page.locator('[data-settings-section="appearance"]').click()
    choices = {'plot_palette': 'okabe-ito', 'heatmap_palette': 'cividis', 'diverging_palette': 'blue-orange'}
    for key, value in choices.items():
        page.locator(f'#settings_{key}').select_option(value)
        assert 'linear-gradient' in page.locator(f'#preview_{key}').evaluate('el => el.style.background')
    playwright.expect(page.locator('#userSettingsDirty')).to_have_text('Unsaved changes')
    page.locator('[data-settings-section="general"]').click()
    playwright.expect(page.locator('#settings_plot_palette')).to_be_hidden()
    page.locator('[data-settings-section="appearance"]').click()
    playwright.expect(page.locator('#settings_plot_palette')).to_have_value('okabe-ito')
    with page.expect_response('**/user-settings'):
        page.locator('#userSettingsSaveBtn').click()
    page.reload(wait_until='networkidle')
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#userSettingsBtn').click()
    page.locator('[data-settings-section="appearance"]').click()
    playwright.expect(page.locator('#userSettingsDirty')).to_have_text('')
    for width in (1280, 390):
        page.set_viewport_size({'width': width, 'height': 800})
        playwright.expect(page.locator('#userSettingsSaveBtn')).to_be_in_viewport()
        assert page.locator('#userSettingsPanel').evaluate('el => el.scrollWidth <= el.clientWidth')
    for key, value in choices.items():
        playwright.expect(page.locator(f'#settings_{key}')).to_have_value(value)
        page.locator(f'#settings_{key}').select_option('default')
    with page.expect_response('**/user-settings'):
        page.locator('#userSettingsSaveBtn').click()


def test_settings_about_and_background_notifications(page):
    settings = {"job_notifications": True}
    jobs = [{"job_id": "notice-test", "status": "running", "execution_backend": "job"}]

    def settings_handler(route):
        if route.request.method == "PATCH":
            settings.update(route.request.post_data_json)
        route.fulfill(json=settings)

    page.route("**/user-settings", settings_handler)
    page.route("**/jobs", lambda route: route.fulfill(json={"jobs": jobs}))
    page.route("**/about", lambda route: route.fulfill(json={
        "components": {"COHORTome": "0.1.0", "duckdb": "1.5.0", "R": "Not installed"},
        "note": "No private configuration included.",
    }))
    page.reload(wait_until="networkidle")
    expect = playwright.expect
    expect(page.locator(".job-completion-notice")).to_have_count(0)
    # Navigation must not discard the observed running status.
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator("#userSettingsBtn").click()
    page.locator('[data-settings-section="about"]').click()
    page.locator("#settingsAbout summary").click()
    expect(page.locator("#aboutVersionReport")).to_contain_text("duckdb: 1.5.0")
    expect(page.locator("#aboutVersionReport")).to_contain_text("R: Not installed")
    expect(page.locator("#aboutCopyReport")).to_be_enabled()
    jobs[0]["status"] = "completed"
    expect(page.locator(".job-completion-notice")).to_contain_text("1 completed, 0 failed", timeout=10000)
    page.locator('#userSettingsCloseBtn').click()
    page.locator(".job-completion-notice").get_by_text("Dismiss", exact=True).click()
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#userSettingsBtn').click()
    page.locator('[data-settings-section="jobs"]').click()
    page.locator("#settingsJobNotifications").uncheck()
    page.locator("#userSettingsSaveBtn").click()
    expect(page.locator("#userSettingsStatus")).to_contain_text("saved")
    assert settings["job_notifications"] is False
    page.reload(wait_until="networkidle")
    expect(page.locator(".job-completion-notice")).to_have_count(0)


def test_shared_clipboard_fallback_preserves_focus_and_cleans_up(page):
    result = page.evaluate("""async () => {
      const { fallbackCopyText } = await import('/static/js/shared.js');
      const button = document.getElementById('userSettingsBtn');
      button.focus();
      const before = document.querySelectorAll('textarea').length;
      const original = document.execCommand;
      let copied = '';
      try {
        document.execCommand = () => { copied = document.activeElement.value; return true; };
        const success = fallbackCopyText('Synthetic version report');
        const focusRestored = document.activeElement === button;
        document.execCommand = () => { throw new Error('Copy denied'); };
        const failure = fallbackCopyText('Not copied');
        return { success, failure, focusRestored, copied,
          clean: document.querySelectorAll('textarea').length === before };
      } finally { document.execCommand = original; }
    }""")
    assert result == {"success": True, "failure": False, "focusRestored": True,
                      "copied": "Synthetic version report", "clean": True}


def test_query_downloads_all_rows_and_reports_expired_export(page):
    handle = "qr_export_fixture"
    page.route("**/query", lambda route: route.fulfill(json={
        "intent": "patient_inventory", "reply": "Found 607 patients.",
        "data": {"source": "deterministic", "patient_count": 607,
                 "result_handle": handle, "result_page": {
                     "result_handle": handle, "total_count": 607, "returned_count": 1,
                     "rows": [{"patient_id": "P0000"}], "patient_ids": ["P0000"],
                     "has_more": True, "next_cursor": "next"}},
    }))
    body = "patient_id\n" + "\n".join(f"P{i:04d}" for i in range(607)) + "\n"
    page.route(f"**/query-results/{handle}/export?format=tsv", lambda route: route.fulfill(
        content_type="text/tab-separated-values", body=body))
    _open_query_tab(page)
    page.locator("#question").fill("List all patients")
    page.locator("#askBtn").click()
    button = page.locator('#queryThread [data-query-export="tsv"]').last
    playwright.expect(button).to_have_text("Export all · TSV")
    with page.expect_download() as download_info:
        button.click()
    download = download_info.value
    assert download.suggested_filename == "query-result.tsv"
    assert Path(download.path()).read_text() == body
    page.route(f"**/query-results/{handle}/export?format=csv", lambda route: route.fulfill(
        status=410, json={"detail": "Query result expired. Run the query again."}))
    page.locator('#queryThread [data-query-export="csv"]').last.click()
    playwright.expect(page.locator("#queryStatus")).to_contain_text("Query result expired")
    playwright.expect(page.locator('#queryThread [data-query-export="csv"]').last).to_be_enabled()


def test_saved_cohort_download_button(page):
    _mock_saved_cohorts(page)
    page.route("**/saved-cohorts/cohort-a/export", lambda route: route.fulfill(
        content_type="application/zip", body=b"synthetic-download-placeholder"))
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    with page.expect_download() as download_info:
        page.locator('#savedCohorts [data-saved-cohort-action="export"]').first.click()
    assert download_info.value.suggested_filename == "saved-cohort.zip"


@pytest.mark.parametrize('generate_template', [False, True])
def test_custom_script_editor_prepares_and_submits_bound_inputs(page, generate_template):
    _install_online_worker_route(page)
    item = {"id": "synthetic-custom-script", "name": "Custom Python script", "kind": "custom_script",
            "runner_type": "container", "runner_ref": "synthetic_custom_script", "execution_mode": "deterministic",
            "execution_backend": "job", "available": True, "default_prompt": "Run custom analysis."}
    page.route("**/analysis/catalog?*", lambda route: route.fulfill(json={"items": [item], "workspace": {}}))
    page.route("**/analysis/script-template", lambda route: route.fulfill(json={
        "template": "print('prepared')", "contract_id": "a" * 64,
        "contract": {"patients": 90, "cohort_a": 90, "cohort_b": 0,
                     "language": "Python 3.11", "packages": {"pandas": "2.2.3"},
                     "assays": {"transcriptomics": {"features": 1000, "cohort_a_samples": 90, "cohort_b_samples": 0}}},
        "sandbox": {"available": True, "image_id": "sha256:" + "b" * 64}}))
    submitted = []
    def run(route):
        submitted.append(route.request.post_data_json)
        route.fulfill(json={"intent": "analysis_custom_script", "reply": "Script completed.",
                            "data": {"source": "deterministic", "context": {"mode": "custom_script", "audit": {}}}})
    page.route("**/analysis", run)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    page.locator("#analysisMethodSelect").select_option("catalog:synthetic-custom-script")
    playwright.expect(page.locator("#analysisRunBtn")).to_be_disabled()
    if generate_template:
        page.locator("[data-script-prepare]").click()
        playwright.expect(page.locator("#analysisScriptCode")).to_have_value("print('prepared')")
        playwright.expect(page.locator('[data-script-summary]')).to_contain_text('Python 3.11')
        playwright.expect(page.locator('[data-script-summary]')).to_contain_text('pandas 2.2.3')
        playwright.expect(page.locator('[data-script-summary]')).to_contain_text('90 patients')
        playwright.expect(page.locator('[data-script-summary]')).to_contain_text('Not used — single-cohort analysis')
        playwright.expect(page.locator('[data-script-summary] table')).to_contain_text('1000')
    else:
        page.locator('[data-script-basic]').click()
        assert "output = Path('/work/output')" in page.locator('#analysisScriptCode').input_value()
        assert 'time.sleep(60)' in page.locator('#analysisScriptCode').input_value()
    page.locator("#analysisScriptCode").fill("print('completed by external AI')")
    playwright.expect(page.locator("#analysisRunBtn")).to_be_enabled()
    page.locator("#analysisRunBtn").click()
    playwright.expect(page.locator("#analysisThread")).to_contain_text("Script completed.")
    assert submitted[0]["custom_script"] == "print('completed by external AI')"
    assert submitted[0]["input_contract_id"] == "a" * 64
    page.locator('[data-analysis-flow-target="scope"]').click()
    page.locator("#analysisCompareMode").check()
    playwright.expect(page.locator("#analysisRunBtn")).to_be_disabled()
    playwright.expect(page.locator('[data-script-prepare]')).to_be_disabled()
    playwright.expect(page.locator('[data-script-copy]')).to_be_disabled()
    playwright.expect(page.locator('[data-script-status]')).to_contain_text('Choose Cohort A in Patients')
    playwright.expect(page.locator('#analysisRunReview')).to_contain_text('Cannot run yet: Choose Cohort A in Patients')


def test_chat_copy_reply_and_clipboard_fallback(page):
    page.evaluate("""() => {
      window.copiedChat = '';
      Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async () => {throw Error('denied');}}});
      document.execCommand = command => {
        if (command === 'copy') { window.copiedChat = document.activeElement.value; return true; }
        return false;
      };
    }""")
    page.route("**/query", lambda route: route.fulfill(json={
        "intent": "summary", "reply": "A synthetic reply to copy.", "data": {"source": "deterministic"}}))
    _open_query_tab(page)
    page.locator("#question").fill("Summarize the cohort")
    page.locator("#askBtn").click()
    button = page.locator("#queryThread [data-chat-copy]").last
    button.click()
    playwright.expect(button).to_contain_text("Copied")
    assert "A synthetic reply to copy." in page.evaluate("window.copiedChat")
    assert "Copy message" not in page.evaluate("window.copiedChat")
    page.route("**/analysis", lambda route: route.fulfill(json={
        "intent": "analysis_summary", "reply": "Analysis text to copy.", "data": {"source": "deterministic", "context": {}}}))
    _open_analysis_tab(page)
    page.locator("#analysisMethodSelect").select_option("summary")
    page.locator("#analysisRunBtn").click()
    button = page.locator("#analysisThread [data-chat-copy]").last
    button.click()
    playwright.expect(button).to_contain_text("Copied")
    assert "Analysis text to copy." in page.evaluate("window.copiedChat")


def test_query_column_sort_resets_page_and_orders_download(page):
    from urllib.parse import parse_qs, urlparse
    handle = "qr_sort_fixture"
    requests = []

    def result_page(parameters):
        descending = parameters.get("sort_direction", ["asc"])[0] == "desc"
        indices = list(range(607))
        if descending:
            indices.reverse()
        start = int(parameters.get("cursor", ["0"])[0])
        selected = indices[start:start + 50]
        return {"result_handle": handle, "total_count": 607, "returned_count": len(selected),
                "patient_ids": [f"P{i:04d}" for i in selected],
                "rows": [{"patient_id": f"P{i:04d}", "visit_count": i} for i in selected],
                "has_more": start + 50 < 607, "next_cursor": str(start + 50)}

    page.route("**/query", lambda route: route.fulfill(json={
        "intent": "patient_inventory", "reply": "Found 607 patients.",
        "data": {"source": "deterministic", "result_handle": handle, "result_page": result_page({})}}))

    def pages(route):
        parameters = parse_qs(urlparse(route.request.url).query)
        requests.append(parameters)
        route.fulfill(json=result_page(parameters))

    page.route(f"**/query-results/{handle}?*", pages)
    page.route(f"**/query-results/{handle}/export?*", lambda route: route.fulfill(
        content_type="text/tab-separated-values", body="patient_id\nP0606\n"))
    _open_query_tab(page)
    page.locator("#question").fill("List all patients")
    page.locator("#askBtn").click()
    table = page.locator("#queryThread .query-result-table").last
    visits = table.locator('[data-query-sort="visit_count"]')
    assert visits.evaluate("el => getComputedStyle(el).backgroundImage") == "none"
    assert visits.evaluate("el => getComputedStyle(el).backgroundColor") == "rgba(0, 0, 0, 0)"
    assert visits.evaluate("el => getComputedStyle(el).color === getComputedStyle(el.parentElement).color")
    visits.click()
    playwright.expect(visits.locator("..")).to_have_attribute("aria-sort", "ascending")
    visits.click()
    playwright.expect(visits.locator("..")).to_have_attribute("aria-sort", "descending")
    playwright.expect(table.locator("tbody tr").first).to_contain_text("P0606")
    with page.expect_request(f"**/query-results/{handle}/export?*") as exported:
        with page.expect_download():
            page.locator('#queryThread [data-query-export="tsv"]').last.click()
    assert parse_qs(urlparse(exported.value.url).query)["sort_direction"] == ["desc"]
    page.locator('#queryThread [data-query-page-action="next"]').last.click()
    playwright.expect(table.locator("tbody tr").first).to_contain_text("P0556")
    table.locator('[data-query-sort="patient_id"]').click()
    playwright.expect(table.locator("tbody tr").first).to_contain_text("P0000")
    assert requests[-1]["sort_by"] == ["patient_id"]
    assert "cursor" not in requests[-1]
    playwright.expect(page.locator('#queryThread [data-query-page-action="previous"]')).to_have_count(0)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - depends on local runtime
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for server at {url}") from last_error


def _spawn_live_server(extra_env: dict[str, str] | None = None):
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    return process, base_url


def _prepare_default_dataset_store(runtime_root: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    env["COHORTOME_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.query_store import prepare_dataset_query_store; prepare_dataset_query_store('default')",
        ],
        cwd=os.getcwd(),
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture(scope="session")
def live_server(tmp_path_factory) -> str:
    runtime_root = tmp_path_factory.mktemp("cohortome-ui-runtime")
    _prepare_default_dataset_store(runtime_root)
    process, base_url = _spawn_live_server({"COHORTOME_RUNTIME_ROOT": str(runtime_root)})
    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            process.kill()
            process.wait(timeout=5)


@pytest.fixture
def live_server_auth(tmp_path) -> str:
    runtime_root = tmp_path / "runtime"
    _prepare_default_dataset_store(runtime_root)
    process, base_url = _spawn_live_server(
        {
            "COHORTOME_RUNTIME_ROOT": str(runtime_root),
            "COHORTOME_AUTH_MODE": "local",
            "COHORTOME_SESSION_SECRET": "ui-smoke-test-session-secret",
            "COHORTOME_LOCAL_USERS_JSON": json.dumps(
                [
                    {
                        "username": "admin",
                        "password": "secret",
                        "role": "admin",
                        "display_name": "Admin User",
                    },
                    {
                        "username": "researcher",
                        "password": "secret",
                        "role": "user",
                        "display_name": "Researcher",
                    },
                ]
            ),
        }
    )
    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            process.kill()
            process.wait(timeout=5)


def _install_dataset_lifecycle_routes(page):
    datasets = [
        {
            "dataset_id": "default",
            "name": "Synthetic demo",
            "has_imaging": True,
            "description": "Public longitudinal clinical and assay demonstration with deliberately verbose explanatory copy for the dataset-card layout.",
            "enabled": True,
            "visibility": "all_authenticated",
            "data_classification": "public",
            "allowed_users": [],
            "allowed_groups": [],
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "detailed_allowed",
            "clinical_representation": "snapshot",
            "clinical_record_count": 4,
            "assay_file_count": 2,
            "content_tags": ["2 patients", "4 timepoints", "2 matrices"],
            "query_store_status": {"status": "ready", "ready": True, "last_error": ""},
        },
        {
            "dataset_id": "secondary",
            "name": "Secondary demo",
            "description": "Private cross-sectional clinical demonstration with deliberately verbose explanatory copy for the dataset-card layout.",
            "enabled": True,
            "visibility": "all_authenticated",
            "data_classification": "private",
            "allowed_users": [],
            "allowed_groups": [],
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "detailed_allowed",
            "clinical_representation": "person",
            "clinical_record_count": 2,
            "assay_file_count": 0,
            "content_tags": ["2 patients", "2 person records"],
            "query_store_status": {"status": "ready", "ready": True, "last_error": ""},
        },
    ]
    state = {"current_ids": ["default"], "select_requests": [], "fail_next_selection": "", "datasets": datasets}

    def scope_id(dataset_ids):
        normalized = sorted(set(dataset_ids))
        if len(normalized) == 1:
            return normalized[0]
        return f"scope--{'--'.join(normalized)}" if normalized else ""

    def list_handler(route):
        current_ids = list(state["current_ids"])
        current = next((item for item in datasets if item["dataset_id"] == current_ids[0]), None) if len(current_ids) == 1 else None
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": datasets,
                    "current_dataset_id": current_ids[0] if len(current_ids) == 1 else "",
                    "current_dataset_ids": current_ids,
                    "current_dataset_scope_id": scope_id(current_ids),
                    "current_dataset": current,
                }
            ),
        )

    def select_handler(route):
        payload = json.loads(route.request.post_data or "{}")
        selected_ids = payload.get("dataset_ids") or ([payload["dataset_id"]] if payload.get("dataset_id") else [])
        selected_ids = [str(item) for item in selected_ids if str(item)]
        state["select_requests"].append(selected_ids)
        if state["fail_next_selection"]:
            detail = state["fail_next_selection"]
            state["fail_next_selection"] = ""
            route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": detail}))
            return
        state["current_ids"] = selected_ids
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "selected": bool(selected_ids),
                    "current_dataset_id": selected_ids[0] if len(selected_ids) == 1 else "",
                    "current_dataset_ids": selected_ids,
                    "current_dataset_scope_id": scope_id(selected_ids),
                }
            ),
        )

    page.route("**/datasets", list_handler)
    page.route("**/datasets/select", select_handler)
    page._cohortome_dataset_state = state
    return state


def _install_online_worker_route(page) -> None:
    page.route(
        "**/jobs/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "available": True,
                    "dependencies_available": True,
                    "redis_available": True,
                    "queue_name": "analysis",
                    "worker_count": 1,
                    "busy_worker_count": 0,
                    "activity": "idle",
                }
            ),
        ),
    )


@pytest.fixture
def page(live_server: str):
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()

            context.route(
                "https://cdn.plot.ly/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body="""
window.Plotly = {
  newPlot: async function(el) {
    el.dataset.plotlyReady = "true";
    el.on = function(name, cb) {
      this._plotlyHandlers = this._plotlyHandlers || {};
      this._plotlyHandlers[name] = cb;
    };
    return el;
  }
};
""",
                ),
            )

            page = context.new_page()
            _install_dataset_lifecycle_routes(page)
            _install_online_worker_route(page)
            page.goto(live_server, wait_until="networkidle")
            yield page
            context.close()
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"Playwright browser is unavailable: {exc}")


@pytest.fixture
def page_auth(live_server_auth: str):
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()

            context.route(
                "https://cdn.plot.ly/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body="""
window.Plotly = {
  newPlot: async function(el) {
    el.dataset.plotlyReady = "true";
    el.on = function(name, cb) {
      this._plotlyHandlers = this._plotlyHandlers || {};
      this._plotlyHandlers[name] = cb;
    };
    return el;
  }
};
""",
                ),
            )

            page = context.new_page()
            _install_dataset_lifecycle_routes(page)
            _install_online_worker_route(page)
            page.goto(live_server_auth, wait_until="networkidle")
            yield page
            context.close()
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"Playwright browser is unavailable: {exc}")


def _open_pheno_tab(page) -> None:
    _ensure_detailed_workspace(page)
    page.locator("#phenoTabBtn").click()
    page.locator("#phenoPrompt").wait_for()


def _ensure_detailed_workspace(page) -> None:
    pheno_tab = page.locator("#phenoTabBtn")
    if pheno_tab.get_attribute("aria-disabled") != "true":
        return

    page.locator("#datasetsTabBtn").click()
    dataset_values = page.locator("#datasetPicker [data-dataset-checkbox]").evaluate_all(
        "(inputs) => inputs.map((input) => input.getAttribute('data-dataset-checkbox'))"
    )
    target = "default" if "default" in dataset_values else (dataset_values[0] if dataset_values else None)
    if target is None:
        raise AssertionError("No dataset options are available for the UI smoke test.")
    for value in dataset_values:
        if not value:
            continue
        checkbox = page.locator(f"#datasetPicker [data-dataset-checkbox='{value}']")
        if value == target:
            checkbox.check(force=True)
        else:
            checkbox.uncheck(force=True)
    page.locator("#loadBtn").wait_for()
    page.locator("#loadBtn").click()
    playwright.expect(pheno_tab).not_to_have_attribute("aria-disabled", "true")
    playwright.expect(page.locator("#loadBtn")).to_be_enabled()


def _mock_pheno_reference_ids(
    page,
    patient_ids: list[str] | None = None,
    record_ids: list[str] | None = None,
    reference_files: list[str] | None = None,
) -> None:
    payload = {
        "patient_ids": patient_ids or ["SYN001", "SYN002", "SYN003"],
        "record_ids": record_ids or ["SYN001:week_0", "SYN002:week_0", "SYN003:week_0"],
        "reference_files": reference_files or ["synthetic_longitudinal.json"],
    }

    page.route(
        "**/pheno-ranker/patient-ids?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        ),
    )
    _ensure_detailed_workspace(page)


def _open_query_tab(page) -> None:
    page.locator("#queryTabBtn").click()
    page.locator("#question").wait_for()


def _open_analysis_tab(page) -> None:
    page.locator("#analysisTabBtn").click()
    page.locator("#analysisRequestDetails").evaluate("element => { element.open = true; }")
    page.locator("#analysisPrompt").wait_for()


def _mock_available_lm(page) -> None:
    page.route(
        "**/lm-status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "available": True,
                    "status": "ready",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model": "openai/gpt-oss-20b",
                    "detail": "Provider is reachable.",
                    "selected_provider_id": "system-default",
                }
            ),
        ),
    )


def _mock_pheno_plan(page, expected_mode: str, patient_id: str = "", selected_ids: str = "") -> None:
    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "source": "deterministic",
                    "reasoning": [
                        "Detected action: compare.",
                        f"Detected mode: {expected_mode}.",
                    ],
                    "plan": {
                        "action": "compare",
                        "mode": expected_mode,
                        "data_dir": "data",
                        "patient_id": patient_id,
                        "selected_patient_ids": selected_ids,
                        "include_terms": ["diseases"],
                        "exclude_terms": [],
                        "max_out": 10,
                        "align": True,
                        "render_heatmap": True,
                        "render_mds": True,
                    },
                }
            ),
        )

    page.route("**/pheno-ranker/plan", handler)


def _mock_cohort_run(page, metric: str = "", prefixed_ids: bool = False, request_capture: dict | None = None) -> None:
    ids = (
        ["C1_SYN001:week_0", "C1_SYN002:week_0", "C2_SYN003:week_0"]
        if prefixed_ids
        else ["SYN001:week_0", "SYN002:week_0", "SYN003:week_0"]
    )
    matrix_text = (
        f"\t{ids[0]}\t{ids[1]}\t{ids[2]}\n"
        f"{ids[0]}\t0\t1\t2\n"
        f"{ids[1]}\t1\t0\t1\n"
        f"{ids[2]}\t2\t1\t0\n"
    )
    patient_ids = ["SYN001", "SYN002", "SYN003"]
    mds_text = (
        "record_id\tpatient_id\tx\ty\n"
        f"{ids[0]}\t{patient_ids[0]}\t-0.4\t0.1\n"
        f"{ids[1]}\t{patient_ids[1]}\t0.2\t-0.3\n"
        f"{ids[2]}\t{patient_ids[2]}\t0.4\t0.2\n"
    )

    def run_handler(route):
        if request_capture is not None:
            request_capture["body"] = json.loads(route.request.post_data or "{}")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "job-cohort",
                    "mode": "cohort",
                    "files": [
                        {"name": "matrix.txt", "url": "/pheno-ranker/results/job-cohort/matrix.txt", "size": 120},
                        {"name": "mds_points.tsv", "url": "/pheno-ranker/results/job-cohort/mds_points.tsv", "size": 110},
                    ],
                    "stderr": "",
                    "command": "pheno cohort command",
                    "pre_commands": [],
                    "plots": [],
                    "similarity_metric_cohort": metric,
                }
            ),
        )

    page.route("**/pheno-ranker/run", run_handler)
    page.route(
        "**/pheno-ranker/results/job-cohort/matrix.txt",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=matrix_text),
    )
    page.route(
        "**/pheno-ranker/results/job-cohort/mds_points.tsv",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=mds_text),
    )


def _mock_patient_run(page) -> None:
    rank_text = (
        "reference\ttarget\thamming\n"
        "SYN002:week_0\tSYN001:week_0\t0.12\n"
        "SYN003:week_0\tSYN001:week_0\t0.19\n"
    )

    page.route(
        "**/pheno-ranker/run",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body="""
{
  "job_id": "job-patient",
  "mode": "patient",
  "files": [
    {"name": "rank.txt", "url": "/pheno-ranker/results/job-patient/rank.txt", "size": 98},
    {"name": "alignment.target.csv", "url": "/pheno-ranker/results/job-patient/alignment.target.csv", "size": 42}
  ],
  "stderr": "",
  "command": "pheno patient command",
  "pre_commands": [],
  "plots": []
}
""",
        ),
    )
    page.route(
        "**/pheno-ranker/results/job-patient/rank.txt",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=rank_text),
    )
    page.route(
        "**/pheno-ranker/results/job-patient/alignment.target.csv",
        lambda route: route.fulfill(status=200, content_type="text/plain", body="bucket,label\n"),
    )


def _mock_dashboard_load(page, clinical_representation: str = "snapshot") -> None:
    page.route(
        "**/patients?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "patient_id": "SYN001",
                        "visit_count": 5,
                        "original_record_ids": ["SYN001:week_0"],
                        "sex": "female",
                        "clarid": {
                            "subject_id": 1,
                            "human_id": "SyntheticStudy-00001-Case-K50.9-Female-A40_49",
                            "stub_id": "SyntheticStudy00001CASE",
                            "study": "SyntheticStudy",
                            "type": "Case",
                            "condition": "K50.9",
                            "condition_name": "Crohn's disease, unspecified",
                            "sex": "Female",
                            "age_group": "Age40to49",
                            "codebook_version": "0.04",
                            "tools_version": "0.04",
                        },
                        "evidence": {"diseases": {"count": 1}},
                        "first_event_date": "2024-01-01",
                        "last_event_date": "2024-06-01",
                    },
                    {
                        "patient_id": "SYN002",
                        "visit_count": 4,
                        "sex": "male",
                        "evidence": {"diseases": {"count": 2}},
                        "first_event_date": "2024-01-05",
                        "last_event_date": "2024-05-10",
                    },
                ]
            ),
        ),
    )
    page.route(
        "**/dashboard?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "clinical_representation": clinical_representation,
                    "patients": 2,
                    "visits": 9,
                    "top_diseases": [["Crohn Disease", 2]],
                    "top_treatments": [["Infliximab", 1]],
                    "sex_counts": {"female": 1, "male": 1},
                    "visit_distribution": {"4": 1, "5": 1},
                    "disease_medication_matrix": {
                        "diseases": ["Crohn Disease"],
                        "medications": ["Infliximab"],
                        "values": [[1]],
                    },
                    "timelines": [
                        {
                            "patient_id": "SYN001",
                            "visit_count": 5,
                            "first_event_date": "2024-01-01",
                            "last_event_date": "2024-06-01",
                            "events": [
                                {
                                    "visit_id": "week_0",
                                    "event_date": "2024-01-01",
                                    "event_type": "baseline",
                                    "diagnosis": "Crohn Disease",
                                    "domains": [
                                        {"key": "diseases", "label": "Disease", "count": 1, "examples": ["Crohn Disease"]},
                                        {"key": "treatments", "label": "Treatment", "count": 1, "examples": ["Infliximab"]},
                                    ],
                                }
                            ],
                        },
                        {
                            "patient_id": "SYN002",
                            "visit_count": 4,
                            "first_event_date": "2024-01-05",
                            "last_event_date": "2024-05-10",
                            "events": [
                                {
                                    "visit_id": "week_0",
                                    "event_date": "2024-01-05",
                                    "event_type": "baseline",
                                    "diagnosis": "Ulcerative Colitis",
                                    "domains": [
                                        {"key": "phenotypic_features", "label": "Phenotype", "count": 1, "examples": ["Abdominal pain"]}
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ),
        ),
    )
    page.route(
        "**/patients/*/workspace?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "patient_id": route.request.url.split("/patients/", 1)[1].split("/workspace", 1)[0],
                    "summary": {"patient_id": route.request.url.split("/patients/", 1)[1].split("/workspace", 1)[0]},
                    "patient_context": {"sex": "female", "date_of_birth": "", "vital_status": "", "source_files": []},
                    "evidence": {
                        "diseases": {"count": 1, "examples": ["Crohn Disease"]},
                        "phenotypic_features": {"count": 1, "examples": ["Abdominal pain"]},
                        "measures": {"count": 0, "examples": []},
                        "treatments": {"count": 1, "examples": ["Infliximab"]},
                        "procedures": {"count": 0, "examples": []},
                        "exposures": {"count": 0, "examples": []},
                    },
                    "key_fragments": [],
                    "visits": [],
                }
            ),
        ),
    )


def _mock_assay_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002", "SYN003", "SYN004"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0", "SYN003:week_0", "SYN004:week_0"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "clinical_overlap_ratio": 1.0,
                            "scope_overlap_patient_count": 0,
                            "scope_overlap_ratio": 0.0,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        }
                    ]
                }
            ),
        ),
    )


def _mock_rsem_only_assay_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_rsem_expected_counts",
                            "modality": "transcriptomics",
                            "data_type": "rsem_expected_counts",
                            "supports_expression_summary": False,
                            "feature_label": "genes",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001", "SYN002"],
                            "sample_count": 2,
                            "patient_count": 2,
                            "feature_count": 1200,
                            "clinical_overlap_patient_count": 2,
                        }
                    ]
                }
            ),
        ),
    )


def _mock_dicom_studies(page) -> None:
    page.route(
        "**/dicom/studies?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "ohif_public_url": "http://ohif.example",
                    "dicomweb_public_url": "http://orthanc.example/dicom-web",
                    "studies": [
                        {
                            "study_id": "syn001-mri",
                            "label": "Synthetic MRI baseline SYN001",
                            "patient_id": "SYN001",
                            "sample_id": "SYN001:week_0",
                            "timepoint": "week_0",
                            "modality": "MR",
                            "study_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1",
                            "ohif_url": "http://ohif.example/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1",
                            "series": [
                                {
                                    "series_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1.1",
                                    "series_description": "Synthetic axial T1",
                                    "instance_count": 1,
                                }
                            ],
                        }
                    ],
                }
            ),
        ),
    )


def _mock_dicom_status(page) -> None:
    page.route(
        "**/dicom/status?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "ohif_public_url": "http://ohif.example",
                    "dicomweb_public_url": "http://orthanc.example/dicom-web",
                    "manifest_found": True,
                    "manifest_count": 1,
                    "study_count": 1,
                    "orthanc": {
                        "checked": True,
                        "reachable": True,
                        "message": "Orthanc is reachable.",
                    },
                }
            ),
        ),
    )


def _mock_multimodal_readiness(page) -> None:
    page.route(
        "**/assays/readiness?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "workspace": {
                        "patient_count": 3,
                        "sample_count": 3,
                        "modality_count": 4,
                        "multimodal_patient_count": 2,
                        "exact_sample_overlap_count": 1,
                    },
                    "modalities": [
                        {"key": "clinical", "label": "Clinical", "dataset_count": 1, "study_count": 0, "patient_count": 3, "sample_count": 3, "feature_count": 0, "clinical_overlap_count": 3},
                        {"key": "transcriptomics", "label": "Transcriptomics", "dataset_count": 1, "study_count": 0, "patient_count": 2, "sample_count": 2, "feature_count": 12, "clinical_overlap_count": 2},
                        {"key": "imaging", "label": "Imaging features", "dataset_count": 1, "study_count": 0, "patient_count": 1, "sample_count": 1, "feature_count": 6, "clinical_overlap_count": 1},
                        {"key": "dicom", "label": "DICOM studies", "dataset_count": 0, "study_count": 1, "patient_count": 1, "sample_count": 1, "feature_count": 0, "clinical_overlap_count": 1},
                    ],
                    "pairwise_overlaps": [
                        {"left": "imaging", "right": "transcriptomics", "left_label": "Imaging features", "right_label": "Transcriptomics", "patient_overlap_count": 1, "sample_overlap_count": 1},
                        {"left": "dicom", "right": "imaging", "left_label": "DICOM studies", "right_label": "Imaging features", "patient_overlap_count": 1, "sample_overlap_count": 1},
                    ],
                    "issues": [
                        {"severity": "warning", "kind": "dicom_sample_without_clinical_timepoint", "message": "DICOM study sample needs clinical timepoint review."}
                    ],
                    "suggestions": [
                        {"key": "dicom_review", "label": "Review DICOM studies in OHIF", "enabled": True, "reason": "DICOM studies are linked to this workspace."},
                        {"key": "imaging_feature_summary", "label": "Summarize derived imaging features", "enabled": True, "reason": "Imaging feature matrices overlap clinical patients."},
                        {"key": "patient_level_cross_modal", "label": "Explore patient-level cross-modal associations", "enabled": True, "reason": "At least two modalities share 1 patient."},
                        {"key": "visit_matched_multimodal", "label": "Explore visit-matched multimodal associations", "enabled": True, "reason": "At least two modalities share 1 exact sample ID."},
                    ],
                }
            ),
        ),
    )


def _mock_multimodal_matrix(page) -> None:
    page.route(
        "**/assays/matrix?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "metadata": {
                        "join_level": "sample",
                        "row_count": 2,
                        "preview_row_count": 2,
                        "column_count": 6,
                        "assay_dataset_count": 2,
                        "feature_group_count": 3,
                        "selected_feature_count": 3,
                        "missing_cell_count": 1,
                        "missing_fraction": 0.0833,
                    },
                    "columns": [
                        {"key": "patient_id", "label": "Patient ID", "role": "identifier"},
                        {"key": "sample_id", "label": "Sample/timepoint ID", "role": "identifier"},
                        {"key": "clinical.sex", "label": "Sex", "role": "covariate"},
                        {"key": "synthetic_transcriptome_raw_counts_infliximab.ENSG00000111111", "label": "ENSG00000111111", "role": "feature", "modality": "transcriptomics"},
                        {"key": "synthetic_mri_derived_measurements.lesion_volume_ml", "label": "lesion_volume_ml", "role": "feature", "modality": "imaging"},
                        {"key": "dicom.study_count", "label": "DICOM study count", "role": "viewer_metadata", "modality": "dicom"},
                    ],
                    "rows": [
                        {
                            "row_id": "SYN001:week_0",
                            "patient_id": "SYN001",
                            "sample_id": "SYN001:week_0",
                            "values": {
                                "patient_id": "SYN001",
                                "sample_id": "SYN001:week_0",
                                "clinical.sex": "female",
                                "synthetic_transcriptome_raw_counts_infliximab.ENSG00000111111": 42,
                                "synthetic_mri_derived_measurements.lesion_volume_ml": 1.4,
                                "dicom.study_count": 1,
                            },
                        }
                    ],
                    "missingness": [
                        {"key": "synthetic_mri_derived_measurements.lesion_volume_ml", "label": "lesion_volume_ml", "missing_count": 1, "missing_fraction": 0.5}
                    ],
                    "feature_groups": [
                        {"dataset_name": "synthetic_transcriptome_raw_counts_infliximab", "label": "Transcriptomics", "modality": "transcriptomics", "feature_count_selected": 1, "exact_sample_match_count": 1},
                        {"dataset_name": "synthetic_mri_derived_measurements", "label": "MRI derived measurements", "modality": "imaging", "feature_count_selected": 1, "exact_sample_match_count": 1},
                        {"dataset_name": "dicom_studies", "label": "DICOM studies", "modality": "dicom", "feature_count_selected": 1, "exact_sample_match_count": 1},
                    ],
                    "warnings": [
                        {"severity": "warning", "kind": "patient_overlap_without_exact_sample_match", "message": "A modality overlaps patients but not exact sample IDs."}
                    ],
                }
            ),
        ),
    )


def _mock_multimodal_assay_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics",
                            "data_type": "raw_counts",
                            "feature_label": "genes",
                            "feature_id_type": "ensembl_gene_id",
                            "patient_ids": ["SYN001", "SYN002", "SYN003", "SYN004"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        },
                        {
                            "dataset_name": "synthetic_olink_inflammation_panel",
                            "modality": "proteomics",
                            "data_type": "npX",
                            "feature_label": "proteins",
                            "feature_id_type": "uniprot_accession",
                            "patient_ids": ["SYN001", "SYN002", "SYN003", "SYN004"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 12,
                            "patient_count": 2,
                            "feature_count": 92,
                            "clinical_overlap_patient_count": 2,
                        },
                        {
                            "dataset_name": "synthetic_immune_cell_abundance",
                            "modality": "flow_cytometry",
                            "data_type": "cell_population_abundance",
                            "feature_label": "immune-cell populations",
                            "feature_id_type": "immune_cell_population",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 2,
                            "patient_count": 2,
                            "feature_count": 8,
                            "clinical_overlap_patient_count": 2,
                        },
                        {
                            "dataset_name": "synthetic_quantitative_serology",
                            "modality": "serology",
                            "data_type": "quantitative_measurement",
                            "feature_label": "serology markers",
                            "feature_id_type": "serology_marker",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 2,
                            "patient_count": 2,
                            "feature_count": 6,
                            "clinical_overlap_patient_count": 2,
                        },
                        {
                            "dataset_name": "synthetic_mri_derived_measurements",
                            "modality": "imaging",
                            "data_type": "derived_measurements",
                            "feature_label": "radiology measurements",
                            "feature_id_type": "dicom_tag",
                            "patient_ids": ["SYN001"],
                            "sample_ids": ["SYN001:week_0"],
                            "sample_count": 1,
                            "patient_count": 1,
                            "feature_count": 6,
                            "clinical_overlap_patient_count": 1,
                        },
                    ]
                }
            ),
        ),
    )


def _mock_assay_datasets_with_nonmatching_dataset(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002", "SYN003", "SYN004"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        },
                        {
                            "dataset_name": "unrelated_transcriptome_raw_counts",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["OTHER001", "OTHER002"],
                            "sample_count": 12,
                            "patient_count": 2,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 0,
                            "mean_total_counts_per_sample": 512.0,
                            "mean_detected_genes_per_sample": 8.2,
                            "top_genes": [],
                        },
                    ]
                }
            ),
        ),
    )


def _mock_assay_datasets_with_two_matching_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002", "SYN003", "SYN004"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        },
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_ustekinumab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002", "SYN003", "SYN004"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 980.0,
                            "mean_detected_genes_per_sample": 9.8,
                            "top_genes": [],
                        },
                    ]
                }
            ),
        ),
    )


def _mock_methylation_catalog_and_assay(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_methylation_m_values",
                            "modality": "methylation",
                            "data_type": "m_values",
                            "feature_label": "CpG probes",
                            "feature_id_type": "illumina_cpg_probe_id",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 2,
                            "patient_count": 2,
                            "feature_count": 12,
                            "clinical_overlap_patient_count": 2,
                        }
                    ]
                }
            ),
        ),
    )
    page.route(
        "**/analysis/catalog?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": [
                        {
                            "id": "methylation-qc-pca",
                            "name": "Methylation QC and PCA",
                            "category": "Assays",
                            "kind": "methylation_qc_pca",
                            "description": "Run processed-matrix QC and PCA.",
                            "guidance": "Select one methylation M-value assay.",
                            "default_prompt": "Run methylation QC and PCA for the selected assay in the current Analysis scope.",
                            "execution_mode": "deterministic",
                            "execution_backend": "job",
                            "runner_type": "rscript",
                            "runner_ref": "methylation_qc_pca",
                            "default_compare_mode": False,
                            "supports_compare_mode": False,
                            "requires_detailed_access": True,
                            "requires_assays": True,
                            "required_modalities": ["methylation"],
                            "required_data_types": ["m_values"],
                            "analysis_level": "sample",
                            "tags": ["methylation", "pca"],
                            "available": True,
                            "unavailable_reason": "",
                            "workspace_requirements": ["Requires methylation assay data (m_values)."],
                        }
                    ],
                    "workspace": {
                        "granularity_ceiling": "detailed",
                        "has_assay_datasets": True,
                        "assay_dataset_count": 1,
                        "assay_modalities": ["methylation"],
                        "assay_data_types": ["m_values"],
                    },
                }
            ),
        ),
    )


def _mock_analysis_trajectory_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_trajectory",
                    "reply": "CRP declines after Infliximab with early separation from baseline.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "mode": "trajectory_response",
                            "measure": "CRP",
                            "unit": "mg/L",
                            "treatment": "Infliximab",
                            "patient_count": 3,
                            "patient_series": [
                                {
                                    "label": "SYN001",
                                    "points": [
                                        {"x": "week_0", "x_label": "week_0", "value": 16},
                                        {"x": "week_2", "x_label": "week_2", "value": 9},
                                        {"x": "week_6", "x_label": "week_6", "value": 5},
                                    ],
                                },
                                {
                                    "label": "SYN002",
                                    "points": [
                                        {"x": "week_0", "x_label": "week_0", "value": 14},
                                        {"x": "week_2", "x_label": "week_2", "value": 8},
                                        {"x": "week_6", "x_label": "week_6", "value": 4},
                                    ],
                                },
                            ],
                            "summary_series": {
                                "label": "Cohort median",
                                "points": [
                                    {"x": "week_0", "x_label": "week_0", "value": 15},
                                    {"x": "week_2", "x_label": "week_2", "value": 8.5},
                                    {"x": "week_6", "x_label": "week_6", "value": 4.5},
                                ],
                            },
                            "summary_points": [
                                {"x": "week_0", "x_label": "week_0", "value": 15},
                                {"x": "week_2", "x_label": "week_2", "value": 8.5},
                                {"x": "week_6", "x_label": "week_6", "value": 4.5},
                            ],
                        },
                    },
                }
            ),
        ),
    )


def _mock_analysis_assay_volcano_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_transcriptomics_medication_compare",
                    "reply": "Expression differs between medication-aligned transcriptomics datasets within the current Analysis scope, with exploratory fold-change shifts across multiple genes.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "mode": "transcriptomics_medication_compare",
                            "scope_patient_count": 2,
                            "exploratory_note": "Exploratory transcriptomics comparison based on log2(CPM+1) normalization and a simple per-gene normal-approximation test. This is preliminary and not DESeq2-grade differential expression.",
                            "comparisons": [
                                {
                                    "medication_a": "Infliximab",
                                    "medication_b": "Vedolizumab",
                                    "scoped_patient_ids_a": ["SYN001"],
                                    "scoped_patient_ids_b": ["SYN006"],
                                    "exploratory_volcano_points": [
                                        {
                                            "gene_id": "ENSG000001",
                                            "mean_log2_cpm_a": 8.1,
                                            "mean_log2_cpm_b": 6.7,
                                            "log2_fold_change": 1.4,
                                            "p_value": 0.002,
                                            "neg_log10_p": 2.69,
                                        },
                                        {
                                            "gene_id": "ENSG000002",
                                            "mean_log2_cpm_a": 5.9,
                                            "mean_log2_cpm_b": 7.0,
                                            "log2_fold_change": -1.1,
                                            "p_value": 0.01,
                                            "neg_log10_p": 2.0,
                                        },
                                    ],
                                }
                            ],
                        },
                    },
                }
            ),
        ),
    )


def _mock_query_reply(page) -> None:
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "disease_cohort",
                    "reply": "Patients matching disease query 'Crohn Disease': SYN001, SYN002.",
                    "data": {
                        "source": "deterministic",
                        "execution": "deterministic",
                        "dataset_id": "default",
                        "dataset_ids": ["default"],
                        "dataset_name": "Synthetic demo",
                        "dataset_names": ["Synthetic demo"],
                        "granularity_requested": "detailed",
                        "granularity_applied": "detailed",
                        "ai_provider_access": "detailed_allowed",
                        "ai_provider_context_granularity": "detailed",
                        "external_llm_allowed": True,
                        "patient_ids": ["SYN001", "SYN002"],
                        "patient_count": 2,
                        "available_actions": {
                            "open_in_analysis": True,
                            "save_cohort": True,
                            "copy_patient_ids": True,
                            "use_in_pheno_ranker": False,
                        },
                        "follow_up_suggestions": [
                            "How many patients take Infliximab?",
                            "What evidence supports the treatment pattern?",
                        ],
                        "follow_up_suggestion_metadata": [
                            {
                                "prompt": "How many patients take Infliximab?",
                                "execution_kind": "deterministic",
                                "execution_mode": "deterministic_only",
                                "label": "Deterministic",
                            },
                            {
                                "prompt": "What evidence supports the treatment pattern?",
                                "execution_kind": "planner",
                                "execution_mode": "planner_only",
                                "label": "LLM-planned",
                            },
                        ],
                    },
                    "action_context": {
                        "patient_ids": ["SYN001", "SYN002"],
                        "record_ids": [],
                        "id_type": "patient",
                        "analysis_prompt": "Interpret this selected workspace subset and summarize the main clinical and treatment patterns.",
                    },
                }
            ),
        ),
    )


def _mock_saved_cohorts(page) -> None:
    page.route(
        "**/saved-cohorts?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "cohorts": [
                        {
                            "id": "cohort-a",
                            "name": "Infliximab responders",
                            "data_dir": "data",
                            "patient_ids": ["SYN001", "SYN002"],
                            "id_type": "patient",
                            "source": {"kind": "query", "prompt": "Which patients take Infliximab?"},
                        },
                        {
                            "id": "cohort-b",
                            "name": "Comparator cohort",
                            "data_dir": "data",
                            "patient_ids": ["SYN003", "SYN004"],
                            "id_type": "patient",
                            "source": {"kind": "query", "prompt": "Which patients are comparators?"},
                        }
                    ]
                }
            ),
        ),
    )


def _mock_disease_inventory(page) -> None:
    page.route(
        "**/cohorts/diseases?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {"disease": "Crohn Disease", "patient_count": 2, "patients": ["SYN001", "SYN002"]},
                    {"disease": "Ulcerative Colitis", "patient_count": 2, "patients": ["SYN003", "SYN004"]},
                ]
            ),
        ),
    )


def _mock_analysis_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_deterministic",
                    "reply": "This cohort is dominated by Crohn Disease and recurrent Infliximab exposure.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "source": "clinical summary",
                            "notable_findings": ["Crohn Disease enriched", "Infliximab common"],
                        },
                    },
                }
            ),
        ),
    )


def test_primary_wordmark_emphasizes_cohort(page) -> None:
    wordmark = page.locator("#appShell .brand-wordmark")
    primary = wordmark.locator(".brand-wordmark-primary")
    secondary = wordmark.locator(".brand-wordmark-secondary")

    playwright.expect(wordmark).to_have_attribute("aria-label", "COHORTome")
    playwright.expect(primary).to_have_text("COHORT")
    playwright.expect(secondary).to_have_text("ome")
    assert page.title() == "COHORTome"
    assert int(primary.evaluate("element => getComputedStyle(element).fontWeight")) > int(
        secondary.evaluate("element => getComputedStyle(element).fontWeight")
    )
    assert primary.evaluate("element => getComputedStyle(element).color") != secondary.evaluate(
        "element => getComputedStyle(element).color"
    )
    visible_text = page.locator("body").inner_text()
    assert "CohorToMe" not in visible_text
    assert "Cohort2Me" not in visible_text
    assert "Cohortome" not in visible_text


def test_pheno_run_button_requires_prompt(page) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    run_button = page.locator("#phenoRunBtn")
    expect = playwright.expect

    expect(run_button).to_be_disabled()
    page.locator("#phenoPrompt").fill("Find closest matches to SYN005:week_0 by disease")
    expect(run_button).to_be_enabled()


@pytest.mark.parametrize(
    ("plan_source", "data_source", "expected_class", "expected_mode", "expected_label"),
    [
        ("deterministic", "deterministic", "query-chip-deterministic", "deterministic", "Deterministic"),
        ("lm_studio", "llm", "query-chip-planner", "llm_planned", "LLM-planned"),
    ],
)
def test_pheno_plan_followups_disclose_planning_path_before_click(
    page,
    plan_source: str,
    data_source: str,
    expected_class: str,
    expected_mode: str,
    expected_label: str,
) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    suggestion = "Compare all patients by diseases"
    plan_calls = {"count": 0}

    def plan_handler(route):
        plan_calls["count"] += 1
        data = {"source": data_source}
        if data_source == "llm":
            data["planner"] = {"provider": "lm_studio", "model": "test-model"}
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "source": plan_source,
                    "data": data,
                    "reasoning": ["Detected action: compare.", "Detected mode: cohort."],
                    "follow_up_suggestions": [suggestion],
                    "plan": {
                        "action": "compare",
                        "mode": "cohort",
                        "data_dir": "data",
                        "patient_id": "",
                        "selected_patient_ids": "",
                        "include_terms": ["diseases"],
                        "exclude_terms": [],
                        "max_out": 10,
                        "align": False,
                        "render_heatmap": True,
                        "render_mds": True,
                        "render_graph": True,
                    },
                }
            ),
        )

    page.route("**/pheno-ranker/plan", plan_handler)
    page.locator("#phenoPrompt").fill("Compare the current cohort")
    page.locator("#phenoSetupDetails > summary").click()
    page.locator("#phenoPlanBtn").click()

    chip = page.locator("#phenoPlanFollowups [data-pheno-followup-prompt]")
    playwright.expect(chip).to_be_visible()
    playwright.expect(chip).to_have_class(re.compile(rf"\b{expected_class}\b"))
    playwright.expect(chip.locator(".followup-mode-label")).to_have_text(expected_label)
    playwright.expect(chip).to_have_attribute("data-followup-execution-mode", expected_mode)
    playwright.expect(chip).to_have_attribute("title", re.compile("does not run it"))
    playwright.expect(chip).to_have_attribute("aria-label", re.compile(expected_label))

    chip.click()

    playwright.expect(page.locator("#phenoPrompt")).to_have_value(suggestion)
    playwright.expect(page.locator("#phenoPlanFollowups")).to_be_hidden()
    playwright.expect(page.locator("#phenoPlanStatus")).to_contain_text(f"{expected_label} follow-up prepared")
    assert plan_calls["count"] == 1


def test_pheno_cohort_run_shows_interactive_plots_and_hides_patient_only_cards(page) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    expect = playwright.expect
    expect(page.locator("#phenoRenderGraph")).to_be_checked()
    _mock_pheno_plan(page, expected_mode="cohort", selected_ids="SYN001:week_0,SYN002:week_0,SYN003:week_0")
    _mock_cohort_run(page)

    page.locator("#phenoPrompt").fill("Cluster these three records by disease")
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed cohort run")
    expect(page.locator("#phenoHeatmapPlot")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#phenoMdsPlot")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#phenoExplainCard")).to_be_hidden()
    expect(page.locator("#phenoAlignmentCard")).to_be_hidden()


def test_pheno_patient_run_shows_patient_only_cards(page) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    _mock_pheno_plan(page, expected_mode="patient", patient_id="SYN001:week_0")
    _mock_patient_run(page)
    expect = playwright.expect

    page.locator("#phenoPrompt").fill("Find closest matches to SYN001:week_0 by disease")
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed patient run")
    expect(page.locator("#phenoExplainCard")).to_be_visible()
    expect(page.locator("#phenoAlignmentCard")).to_be_visible()
    expect(page.locator("#phenoOutputPreview")).to_contain_text("rank.txt loaded as TSV")


def test_dashboard_load_renders_clinical_overview(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#dashboard")).to_contain_text("Patients2")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-medications")).to_have_attribute("data-plotly-ready", "true")


def test_dataset_picker_uses_accessible_structured_trait_icons_and_legend(page) -> None:
    expect = playwright.expect
    page.locator("#datasetsTabBtn").click()

    legend = page.locator("#datasetPickerLegend")
    expect(legend).to_be_visible()
    expect(legend.locator("[data-dataset-trait-legend]")).to_have_count(6)
    expect(legend).to_contain_text("Imaging")
    expect(legend).to_contain_text("Private")
    expect(legend).to_contain_text("Cross-sectional")
    expect(legend).to_contain_text("Longitudinal")
    expect(legend).to_contain_text("Clinical")
    expect(legend).to_contain_text("Assay data")
    expect(legend).not_to_contain_text("Public")
    expect(legend).not_to_contain_text("Transcriptomics")

    default_card = page.locator("[data-dataset-card='default']")
    secondary_card = page.locator("[data-dataset-card='secondary']")
    expect(default_card.get_by_role("img", name="Imaging data")).to_be_visible()
    expect(secondary_card.locator("[data-dataset-trait='imaging']")).to_have_count(0)
    expect(default_card.locator("[data-dataset-trait='private']")).to_have_count(0)
    expect(default_card.get_by_role("img", name="Longitudinal clinical records")).to_have_attribute(
        "title", "Longitudinal clinical records"
    )
    expect(default_card.get_by_role("img", name="Clinical data")).to_be_visible()
    expect(default_card.get_by_role("img", name="Assay data")).to_be_visible()
    expect(default_card).to_contain_text("2 patients")
    expect(default_card).to_contain_text("4 timepoints")

    private_icon = secondary_card.get_by_role("img", name="Private data")
    expect(private_icon).to_be_visible()
    expect(private_icon).to_have_attribute("title", "Private data")
    expect(secondary_card.get_by_role("img", name="Cross-sectional clinical records")).to_be_visible()
    expect(secondary_card.get_by_role("img", name="Clinical data")).to_be_visible()
    expect(secondary_card.get_by_role("img", name="Assay data")).to_have_count(0)

    description = secondary_card.locator(".dataset-picker-description")
    expect(description).to_have_attribute(
        "title",
        "Private cross-sectional clinical demonstration with deliberately verbose explanatory copy for the dataset-card layout.",
    )
    assert description.evaluate("(element) => getComputedStyle(element).webkitLineClamp") == "2"
    assert description.evaluate("(element) => getComputedStyle(element).overflow") == "hidden"


def test_dataset_picker_does_not_overflow_at_narrow_viewport(page) -> None:
    page.set_viewport_size({"width": 760, "height": 900})
    page.locator("#datasetsTabBtn").click()

    measurements = page.locator("#datasetsTab").evaluate(
        """
        (tab) => {
          const row = tab.querySelector(".dataset-loader-row");
          const shell = tab.querySelector("#datasetPickerShell");
          const button = tab.querySelector("#loadBtn");
          const targets = [tab, row, shell, ...tab.querySelectorAll("[data-dataset-card]")];
          const rowRect = row.getBoundingClientRect();
          const buttonRect = button.getBoundingClientRect();
          return {
            overflow: targets.map((element) => ({
              clientWidth: element.clientWidth,
              scrollWidth: element.scrollWidth,
            })),
            buttonInsideRow: buttonRect.left >= rowRect.left - 1 && buttonRect.right <= rowRect.right + 1,
            buttonGridColumn: getComputedStyle(button).gridColumnStart,
            shellGridColumn: getComputedStyle(shell).gridColumnStart,
          };
        }
        """
    )

    assert all(item["scrollWidth"] <= item["clientWidth"] + 1 for item in measurements["overflow"])
    assert measurements["buttonInsideRow"] is True
    assert measurements["buttonGridColumn"] == "1"
    assert measurements["shellGridColumn"] == "1"


@pytest.mark.parametrize(
    ("user_role", "expected_action"),
    [
        ("user", "Ask an admin to prepare it in Admin > Data."),
        ("admin", "Prepare or rebuild it in Admin > Data."),
    ],
)
def test_unready_dataset_selection_explains_disabled_apply_action(page_auth, user_role: str, expected_action: str) -> None:
    expect = playwright.expect
    state = page_auth._cohortome_dataset_state
    state["current_ids"] = ["default"]
    state["datasets"][1]["query_store_status"] = {"status": "stale", "ready": False, "last_error": ""}

    username = "admin" if user_role == "admin" else "researcher"
    page_auth.locator("#authUsername").fill(username)
    page_auth.locator("#authPassword").fill("secret")
    page_auth.locator("#authLoginBtn").click()
    expect(page_auth.locator("#appShell")).to_be_visible()
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded")

    page_auth.locator("#datasetsTabBtn").click()
    page_auth.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page_auth.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()

    expect(page_auth.locator("#loadBtn")).to_be_disabled()
    assert page_auth.locator("#loadBtn").evaluate("(element) => getComputedStyle(element).cursor") == "not-allowed"
    expect(page_auth.locator("#loadStatus")).to_have_attribute("role", "status")
    expect(page_auth.locator("#loadStatus")).to_have_attribute("aria-live", "polite")
    expect(page_auth.locator("#loadStatus")).to_have_text(
        f'Cannot apply workspace: dataset store for "Secondary demo" is stale. {expected_action}'
    )
    expect(page_auth.locator("#loadStatus")).to_have_class(re.compile(r"\bwarning\b"))

    page_auth.locator("#datasetPicker [data-dataset-checkbox='secondary']").uncheck()
    page_auth.locator("#datasetPicker [data-dataset-checkbox='default']").check()
    expect(page_auth.locator("#loadStatus")).to_contain_text("ready")
    expect(page_auth.locator("#loadStatus")).not_to_have_class(re.compile(r"\bwarning\b"))


def test_applying_first_dataset_uses_pending_selection_key(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect
    page._cohortome_dataset_state["current_ids"] = []
    page.reload(wait_until="networkidle")
    patient_request_urls = []
    page.on(
        "request",
        lambda request: patient_request_urls.append(request.url)
        if "/patients?" in request.url
        else None,
    )

    page.locator("#datasetsTabBtn").click()
    page.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()
    expect(page.locator("#loadBtnLabel")).to_have_text("Apply workspace")
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#datasetScopeSummary")).to_contain_text("Active workspace: Secondary demo")
    assert patient_request_urls[0].endswith("/patients?dataset_id=secondary")
    assert page._cohortome_dataset_state["current_ids"] == ["secondary"]


def test_workspace_unload_persists_empty_selection_and_clears_dataset_scoped_views(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_query_reply(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")

    _open_query_tab(page)
    page.locator("#question").fill("Which patients have Crohn disease?")
    page.locator("#askBtn").click()
    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")

    _open_analysis_tab(page)
    page.locator("#analysisPrompt").fill("Summarize this workspace")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisThread")).to_contain_text("dominated by Crohn Disease")

    page.locator("#datasetsTabBtn").click()
    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    expect(page.locator("#loadBtnLabel")).to_have_text("Unload workspace")
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_have_text("Workspace unloaded.")
    expect(page.locator("#loadBtn")).to_be_disabled()
    expect(page.locator("#dashboard")).to_contain_text("Select a workspace")
    expect(page.locator("#assayDashboardCards")).to_contain_text("No assays loaded")
    expect(page.locator("#dicomDashboardStudies")).to_contain_text("No DICOM studies loaded")
    expect(page.locator("#multimodalReadinessContent")).to_contain_text("Load a workspace")
    expect(page.locator("#queryThread")).to_contain_text("Ask a query to start")
    expect(page.locator("#analysisThread")).to_contain_text("Run an analysis prompt to start")
    assert page._cohortome_dataset_state["current_ids"] == []
    assert page._cohortome_dataset_state["select_requests"][-1] == []


def test_late_dashboard_response_cannot_repopulate_unloaded_workspace(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect
    pending_dashboard_routes = []
    page.route("**/dashboard?*", lambda route: pending_dashboard_routes.append(route))

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    for _ in range(50):
        if pending_dashboard_routes:
            break
        page.wait_for_timeout(20)
    assert len(pending_dashboard_routes) == 1

    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_have_text("Workspace unloaded.")
    expect(page.locator("#dashboard")).to_contain_text("Select a workspace")

    pending_dashboard_routes[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"patients": 999, "visits": 999}),
    )
    page.wait_for_timeout(100)
    expect(page.locator("#dashboard")).to_contain_text("Select a workspace")
    expect(page.locator("#dashboard")).not_to_contain_text("Patients999")


def test_failed_workspace_switch_keeps_previous_workspace_and_query_state(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_query_reply(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    _open_query_tab(page)
    page.locator("#question").fill("Which patients have Crohn disease?")
    page.locator("#askBtn").click()
    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")

    page.locator("#datasetsTabBtn").click()
    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()
    page._cohortome_dataset_state["fail_next_selection"] = "Secondary dataset store is not ready."
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Secondary dataset store is not ready.")
    expect(page.locator("#loadStatus")).to_contain_text("Your previous workspace remains active.")
    expect(page.locator("#datasetScopeSummary")).to_contain_text("Active workspace: Synthetic demo")
    expect(page.locator("[data-dataset-card='default'] .dataset-picker-state-active")).to_have_text("Active")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")
    assert page._cohortome_dataset_state["current_ids"] == ["default"]
    assert page._cohortome_dataset_state["select_requests"][-1] == ["secondary"]


def test_failed_assay_preflight_does_not_commit_workspace_switch(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    committed_request_count = len(page._cohortome_dataset_state["select_requests"])

    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "Selected dataset assay store is unavailable."}),
        ),
    )
    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Selected dataset assay store is unavailable.")
    expect(page.locator("#loadStatus")).to_contain_text("Your previous workspace remains active.")
    expect(page.locator("#datasetScopeSummary")).to_contain_text("Active workspace: Synthetic demo")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    assert page._cohortome_dataset_state["current_ids"] == ["default"]
    assert len(page._cohortome_dataset_state["select_requests"]) == committed_request_count


def test_dashboard_failure_retries_summary_without_switching_workspace(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    def fail(route):
        route.fulfill(status=503, content_type='application/json', body='{"detail":"Unavailable"}')
    page.route('**/dashboard?*', fail)
    expect = playwright.expect
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    expect(page.locator('#dashboard [data-workspace-state="unavailable"]')).to_have_count(1)
    selections = len(page._cohortome_dataset_state['select_requests'])
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardClinicalBtn').click()
    expect(page.locator('#dashboard')).to_contain_text('Retry without changing the selected workspace.')
    expect(page.locator('#dashboard [role="status"]')).to_have_attribute('aria-busy', 'false')
    page.unroute('**/dashboard?*', fail)
    page.locator('#dashboard [data-dashboard-retry]').click()
    expect(page.locator('#dashboard-plot-diseases')).to_have_attribute('data-plotly-ready', 'true')
    expect(page.locator('#dashboard [data-workspace-state]')).to_have_count(0)
    assert len(page._cohortome_dataset_state['select_requests']) == selections


def test_empty_workspace_is_not_a_dashboard_failure(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    page.route('**/patients?*', lambda route: route.fulfill(status=200, content_type='application/json', body='[]'))
    expect = playwright.expect
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    expect(page.locator('#loadStatus')).to_contain_text('Workspace loaded successfully. No patient records')
    expect(page.locator('#dashboard [data-workspace-state="empty"]')).to_have_count(1)
    expect(page.locator('#dashboard [data-dashboard-retry]')).to_have_count(0)
    expect(page.locator('#loadBtn')).not_to_have_class(re.compile('is-loading'))


def test_multimodal_association_handoff_and_plot(page):
    _mock_dashboard_load(page)
    _mock_multimodal_assay_datasets(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    def features(route):
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(route.request.url).query)
        ids = ['CD4_T_cells_fraction', 'CD8_T_cells_fraction'] if query['assay_id'][0] == 'synthetic_immune_cell_abundance' else ['CRP_mg_L']
        needle = query.get('q', [''])[0].lower()
        annotations = {'CRP_mg_L': {'label': 'C-reactive protein', 'description': 'Simulated soluble protein measurement.', 'unit': 'mg/L'}}
        route.fulfill(content_type='application/json', body=json.dumps({'genes': [value for value in ids if needle in (value + ' ' + annotations.get(value, {}).get('label', '')).lower()], 'annotations': annotations}))
    page.route('**/assays/features?*', features)
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    playwright.expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#dashboardTabBtn').click()
    page.locator('#dashboardMultimodalBtn').click()
    playwright.expect(page.locator('#dashboardMultimodalPanel #associationAssayX')).to_have_count(0)
    page.locator('#multimodalCompareShortcut').click()
    playwright.expect(page.locator('#analysisMeasurementComparison')).to_be_visible()
    page.locator('#associationAssayX').select_option('synthetic_immune_cell_abundance')
    page.locator('#associationAssayY').select_option('synthetic_quantitative_serology')
    playwright.expect(page.locator('#associationFeatureX option')).to_have_count(3)
    page.locator('#associationFeatureX').select_option('CD8_T_cells_fraction')
    playwright.expect(page.locator('#associationDescriptionX')).to_contain_text('No description supplied')
    page.locator('#associationSearchX').fill('no-match')
    playwright.expect(page.locator('#associationFeatureX')).to_be_disabled()
    playwright.expect(page.locator('#associationFeatureStatusX')).to_contain_text('0 available')
    page.locator('#associationSearchX').fill('CD4')
    playwright.expect(page.locator('#associationFeatureX option')).to_have_count(2)
    playwright.expect(page.locator('#associationFeatureX')).to_have_value('')
    page.locator('#associationFeatureX').select_option('CD4_T_cells_fraction')
    page.locator('#associationFeatureY').select_option('CRP_mg_L')
    playwright.expect(page.locator('#associationFeatureY option:checked')).to_contain_text('C-reactive protein')
    playwright.expect(page.locator('#associationDescriptionY')).to_contain_text('Units: mg/L')
    page.locator('#associationSearchY').fill('C-reactive')
    playwright.expect(page.locator('#associationFeatureY')).to_have_value('')
    page.locator('#associationFeatureY').select_option('CRP_mg_L')
    page.locator('#associationAssayY').select_option('')
    playwright.expect(page.locator('#associationFeatureY')).to_have_value('')
    playwright.expect(page.locator('#associationSearchY')).to_be_disabled()
    page.locator('#associationAssayY').select_option('synthetic_quantitative_serology')
    page.locator('#associationFeatureY').select_option('CRP_mg_L')
    page.locator('#associationOpenBtn').click()
    prompt = page.locator('#analysisPrompt').input_value()
    assert prompt.startswith('Compare measurements: ')
    params = json.loads(prompt.split(': ', 1)[1])
    context = dict(mode='cross_modal_association', parameters=params, counts={'matched_patients': 3},
                   points=[dict(x=i, y=i, group='Synthetic group') for i in range(3)],
                   groups=[dict(label='Synthetic group', n=3, spearman_rho=1)],
                   matching='Exact sample matching', limitations='Exploratory association', provenance=[])
    page.route('**/analysis', lambda route: route.fulfill(content_type='application/json', body=json.dumps({
        'intent': 'analysis_cross_modal_association', 'reply': 'Spearman rho: 1.000.',
        'data': {'source': 'deterministic', 'context': context}})))
    page.locator('#analysisRunBtn').click()
    playwright.expect(page.locator('#analysisThread')).to_contain_text('Spearman rho: 1.000')
    playwright.expect(page.locator('[id$="-association"]')).to_have_attribute('data-plotly-ready', 'true')
    playwright.expect(page.locator('#analysisThread')).to_contain_text('Synthetic group')
    playwright.expect(page.locator('#analysisThread')).to_contain_text('Parameters and provenance')


def test_analysis_runs_without_research_framing_controls(page):
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    requests = []
    def result(route):
        requests.append(route.request.post_data_json)
        route.fulfill(content_type='application/json', body=json.dumps({
            'intent': 'analysis_summary', 'reply': 'Synthetic analysis complete.',
            'data': {'source': 'deterministic', 'context': {}}}))
    page.route('**/analysis', result)
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    playwright.expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#analysisTabBtn').click()
    playwright.expect(page.locator('#analysisFraming')).to_have_count(0)
    page.locator('#analysisContextGeneralBtn').click()
    playwright.expect(page.locator('#analysisFraming')).to_have_count(0)
    page.locator('#analysisContextWorkspaceBtn').click()
    page.locator('[data-analysis-flow-target="prompt"]').click()
    page.locator('#analysisRunBtn').click()
    playwright.expect(page.locator('#analysisThread')).to_contain_text('Synthetic analysis complete.')
    assert 'framing' not in requests[0]
    page.reload()
    page.locator('#analysisTabBtn').click()
    playwright.expect(page.locator('#analysisThread')).to_contain_text('Synthetic analysis complete.')


def test_multimodal_synthetic_discovery_examples(page):
    _mock_dashboard_load(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    page.route('**/assays?*', lambda route: route.fulfill(content_type='application/json', body=json.dumps({'datasets': [
        {'dataset_name': 'synthetic_autoimmune_flow_cytometry', 'modality': 'flow_cytometry'},
        {'dataset_name': 'synthetic_autoimmune_serology', 'modality': 'serology'},
    ]})))
    def features(route):
        ids = ['CD4_T_cells_fraction', 'B_cells_fraction'] if 'flow_cytometry' in route.request.url else ['CRP_mg_L', 'Anti_dsDNA_IU_mL']
        route.fulfill(content_type='application/json', body=json.dumps({'genes': ids}))
    page.route('**/assays/features?*', features)
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    playwright.expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#analysisTabBtn').click()
    page.locator('#analysisMethodSelect').select_option('association')
    page.locator('#associationExamples button').first.click()
    playwright.expect(page.locator('#associationFeatureX')).to_have_value('CD4_T_cells_fraction')
    playwright.expect(page.locator('#associationFeatureY')).to_have_value('CRP_mg_L')
    page.locator('#associationExamples button').nth(1).click()
    playwright.expect(page.locator('#associationFeatureX')).to_have_value('B_cells_fraction')
    playwright.expect(page.locator('#associationFeatureY')).to_have_value('Anti_dsDNA_IU_mL')
    playwright.expect(page.locator('#analysisMeasurementComparison')).to_be_visible()
    playwright.expect(page.locator('#associationExamples')).to_contain_text('not biological findings')


def test_analysis_method_picker_without_llm(page):
    _mock_dashboard_load(page)
    _mock_multimodal_assay_datasets(page)
    page.locator('#datasetsTabBtn').click()
    page.locator('#loadBtn').click()
    playwright.expect(page.locator('#loadStatus')).to_contain_text('Loaded 2 patients.')
    page.locator('#analysisTabBtn').click()
    picker = page.locator('#analysisMethodSelect')
    playwright.expect(picker).to_have_value('summary')
    playwright.expect(page.locator('#analysisFlowBar .analysis-flow-step')).to_have_count(5)
    playwright.expect(page.locator('[data-analysis-flow-target="requirements"]')).to_contain_text('Not required')
    page.locator('[data-analysis-flow-target="scope"]').click()
    playwright.expect(page.locator('#analysisWorkspaceSetup')).to_have_attribute('open', '')
    playwright.expect(page.locator('#analysisMeasurementComparison')).to_be_hidden()
    playwright.expect(page.locator('#analysisPrompt')).to_be_hidden()
    playwright.expect(page.locator('#analysisMethodDescription')).to_contain_text('No assay selection or language model')
    calls = []
    def result(route):
        calls.append(route.request.post_data_json)
        route.fulfill(content_type='application/json', body=json.dumps({'intent': 'analysis_summary', 'reply': 'Cohort summary.', 'data': {'source': 'deterministic', 'context': {}}}))
    page.route('**/analysis', result)
    page.locator('#analysisRunBtn').click()
    playwright.expect(page.locator('#analysisThread')).to_contain_text('Cohort summary.')
    assert calls[0]['deterministic_only'] is True
    picker.select_option('association')
    playwright.expect(page.locator('#analysisMeasurementComparison')).to_be_visible()
    playwright.expect(page.locator('[data-analysis-flow-target="requirements"]')).to_contain_text('Choose measurements')
    playwright.expect(page.locator('[data-analysis-flow-target="requirements"]')).to_have_attribute('aria-current', 'step')
    page.locator('[data-analysis-flow-target="requirements"]').click()
    playwright.expect(page.locator('#associationAssayX')).to_be_focused()
    page.locator('#analysisRunBtn').click()
    playwright.expect(page.locator('#analysisStatus')).to_contain_text('Choose a matrix and feature')
    assert len(calls) == 1
    picker.select_option('custom')
    playwright.expect(page.locator('#analysisMeasurementComparison')).to_be_hidden()
    playwright.expect(page.locator('#analysisPrompt')).to_be_visible()
    page.locator('#analysisContextGeneralBtn').click()
    playwright.expect(picker).to_be_hidden()
    playwright.expect(page.locator('#analysisFlowBar')).to_be_hidden()
    playwright.expect(page.locator('#analysisPrompt')).to_be_visible()


def test_dashboard_imaging_panel_lists_dicom_studies(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_dicom_studies(page)
    _mock_dicom_status(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardImagingBtn").click()

    expect(page.locator("#dicomDashboardPanel")).to_be_visible()
    expect(page.locator("#dicomDashboardStatus")).to_contain_text("Loaded 1 DICOM study")
    expect(page.locator("#dicomDashboardHealth")).to_contain_text("Orthanc")
    expect(page.locator("#dicomDashboardHealth")).to_contain_text("Reachable")
    expect(page.locator("#dicomDashboardHealth")).to_contain_text("http://ohif.example")
    expect(page.locator("#dicomDashboardStudies")).to_contain_text("Synthetic MRI baseline SYN001")
    expect(page.locator("#dicomDashboardStudies a", has_text="Open in OHIF")).to_have_attribute(
        "href",
        "http://ohif.example/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1",
    )
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()

    page.locator("#dashboardMultimodalBtn").click()

    expect(page.locator("#dashboardMultimodalBtn")).to_have_class(re.compile("active"))
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("Multimodal feature matrix")
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("Sample-level matrix")


def test_dashboard_assays_panel_filters_modalities(page) -> None:
    _mock_dashboard_load(page)
    _mock_multimodal_assay_datasets(page)
    _mock_dicom_studies(page)
    _mock_dicom_status(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardAssaysBtn").click()

    expect(page.locator("#assayDashboardOverview")).to_contain_text("Assays")
    expect(page.locator("#assayModalityTabs")).to_contain_text("Transcriptomics")
    expect(page.locator("#assayModalityTabs")).not_to_contain_text("Imaging")
    expect(page.locator("#assayModalityTabs")).to_contain_text("Immune-cell abundance")
    expect(page.locator("#assayModalityTabs")).to_contain_text("Serology")
    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#assayDashboardCards")).not_to_contain_text("synthetic_mri_derived_measurements")
    expect(page.locator("#multimodalReadinessPanel")).not_to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardPanel")).not_to_be_visible()
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).not_to_be_visible()

    page.locator("#dashboardMultimodalBtn").click()

    expect(page.locator("#multimodalReadinessPanel")).to_be_visible()
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Multimodal analysis readiness")
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Imaging features")
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Review DICOM studies in OHIF")
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Requirements met")
    page.locator("[data-readiness-analysis-key='imaging_feature_summary']").click()
    expect(page.locator("#analysisTab")).to_have_class(re.compile("active"))
    expect(page.locator("#analysisPrompt")).to_have_value(re.compile("Summarize the derived imaging features"))

    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardMultimodalBtn").click()
    expect(page.locator("#multimodalMatrixPanel")).to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("MRI derived measurements")
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("lesion_volume_ml")

    page.locator("#dashboardAssaysBtn").click()

    page.locator("[data-assay-modality-filter='transcriptomics']").click()

    expect(page.locator("[data-assay-modality-filter='transcriptomics']")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#assayDashboardCards")).not_to_contain_text("synthetic_mri_derived_measurements")
    expect(page.locator("#multimodalReadinessPanel")).not_to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardPanel")).not_to_be_visible()
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).to_be_visible()

    page.locator("#dashboardImagingBtn").click()

    expect(page.locator("#dashboardImagingBtn")).to_have_class(re.compile("active"))
    expect(page.locator("#imagingDashboardCards")).to_contain_text("synthetic_mri_derived_measurements")
    expect(page.locator("#imagingDashboardCards")).not_to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#multimodalReadinessPanel")).not_to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardPanel")).to_be_visible()
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardStudies")).to_contain_text("Synthetic MRI baseline SYN001")


def test_dashboard_quick_expression_excludes_rsem_only_transcriptomics(page) -> None:
    _mock_dashboard_load(page)
    _mock_rsem_only_assay_datasets(page)
    _mock_dicom_studies(page)
    _mock_dicom_status(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardAssaysBtn").click()
    page.locator("[data-assay-modality-filter='transcriptomics']").click()

    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_rsem_expected_counts")
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).not_to_be_visible()
    expect(page.locator("#analysisAssayDatasetList")).not_to_contain_text("synthetic_rsem_expected_counts")
    expect(page.locator("#analysisAssayDatasetList")).to_contain_text("No raw-count transcriptomics assays available")
    expect(page.locator("#analysisAssayStatus")).to_contain_text("No raw-count transcriptomics assays")


def test_dashboard_load_mounts_plotly_overview_cards(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#dashboard-plot-sex")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-visits")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-medications")).to_have_attribute("data-plotly-ready", "true")


def test_dashboard_timeline_filters_events_and_selects_patient(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardTimelineBtn").click()

    expect(page.locator("#dashboard-plot-timeline")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-timeline-controls")).to_contain_text("Disease")
    expect(page.locator("#dashboard-timeline-controls")).to_contain_text("Treatment")
    expect(page.locator("#dashboard-timeline-controls")).to_contain_text("Assay")
    expect(page.locator("#dashboard-timeline-controls-label")).to_have_text("Show events")
    expect(page.locator("#dashboard-timeline-actions")).not_to_be_visible()
    page.locator("#dashboard-timeline-controls input[value='diseases']").uncheck()
    expect(page.locator("#dashboard-timeline-controls input[value='diseases']")).not_to_be_checked()
    page.evaluate(
        """
        () => {
          const plot = document.getElementById("dashboard-plot-timeline");
          plot._plotlyHandlers.plotly_click({ points: [{ customdata: "SYN002" }] });
        }
        """
    )
    expect(page.locator("#detail")).to_contain_text("SYN002")
    expect(page.locator("#dashboard-timeline-actions")).not_to_be_visible()
    expect(page.locator("[data-dashboard-select-patient]:checked")).to_have_count(0)
    page.locator("[data-dashboard-select-patient='SYN002']").first.check()
    expect(page.locator("#dashboard-timeline-selection-status")).to_contain_text("1 patient selected")
    expect(page.locator("#dashboard-timeline-selection-status")).to_contain_text("Whole patients")
    expect(page.locator("[data-dashboard-event-patient='SYN001']").first).to_be_visible()
    page.locator("[data-dashboard-event-inspect]").first.click()
    expect(page.locator("#detail")).to_contain_text("Timeline inspector")
    expect(page.locator(".dashboard-timeline-table tbody tr.is-inspected")).to_have_count(1)
    expect(page.locator("[data-dashboard-event-inspect][aria-pressed='true']")).to_have_count(1)
    page.locator("#dashboardTimelineEventSearch").fill("SYN001")
    expect(page.locator("#dashboard-timeline-event-count")).to_contain_text("matching events")
    page.locator("[data-dashboard-select-patient='SYN001']").first.check()
    expect(page.locator("#dashboard-timeline-selection-status")).to_contain_text("2 patients selected")
    page.locator("#dashboardTimelineUseAnalysisBtn").click()
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("SYN001,SYN002")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardTimelineBtn").click()
    page.locator("#dashboardTimelineClearSelectionBtn").click()
    expect(page.locator("#dashboard-timeline-actions")).not_to_be_visible()
    for value in page.locator("#dashboard-timeline-controls input:enabled:checked").evaluate_all(
        "inputs => inputs.map(input => input.value)"
    ):
        page.locator(f"#dashboard-timeline-controls input[value='{value}']").uncheck()
    expect(page.locator("#dashboard-timeline-controls input:checked:enabled")).to_have_count(0)
    expect(page.locator("#dashboard-timeline-event-table")).to_contain_text("No events match")
    page.locator("#dashboard-timeline-controls input[value='treatments']").check()
    expect(page.locator("#dashboard-timeline-event-table tbody tr")).to_have_count(1)


def test_dashboard_resolves_and_decodes_subject_clarid_in_timeline(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardTimelineBtn").click()

    search = page.locator("#dashboardTimelineEventSearch")
    search.fill("SyntheticStudy00001CASE")
    expect(page.locator("#dashboard-timeline-event-count")).to_contain_text(
        "ClarID recognized as patient SYN001"
    )
    expect(page.locator("#dashboard-timeline-event-table tbody tr")).to_have_count(2)
    expect(page.locator("#dashboard-timeline-event-table tbody")).to_contain_text("SYN001")
    expect(page.locator("#dashboard-timeline-event-table tbody")).not_to_contain_text("SYN002")

    badge = page.locator("#dashboard-timeline-event-table [data-clarid-toggle]").first
    badge.click()
    expect(badge).to_have_attribute("aria-expanded", "true")
    popover = badge.locator("xpath=..").locator(".clarid-popover")
    expect(popover).to_be_visible()
    assert popover.evaluate("element => getComputedStyle(element).position") == "static"
    expect(popover).to_contain_text("SyntheticStudy · Case · Crohn's disease, unspecified (K50.9) · Female · Age40to49")
    expect(popover).to_contain_text("SyntheticStudy-00001-Case-K50.9-Female-A40_49")
    expect(popover).to_contain_text("SyntheticStudy00001CASE")
    expect(popover).to_contain_text("Codebook 0.04")
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.locator('.dashboard-timeline-domain').evaluate_all('''chips => chips.every(chip => {
            const bounds = chip.getBoundingClientRect();
            return [...chip.children].every(child => {
                const box = child.getBoundingClientRect();
                return box.left >= bounds.left && box.right <= bounds.right
                    && box.top >= bounds.top && box.bottom <= bounds.bottom;
            });
        })''')
        for selector in ('.dashboard-timeline-event-header', '.dashboard-timeline-table-wrap'):
            element = page.locator(selector)
            assert element.evaluate('''el => {
                const box = el.getBoundingClientRect();
                const parent = el.parentElement.getBoundingClientRect();
                return box.right <= parent.right && box.left >= parent.left;
            }'''), selector
        assert page.locator('.dashboard-timeline-event-header').evaluate(
            'el => el.scrollWidth <= el.clientWidth')
        assert popover.evaluate("el => el.scrollWidth <= el.clientWidth")
        assert popover.locator(".clarid-decoded-summary").evaluate(
            "el => getComputedStyle(el).whiteSpace === 'normal' && el.scrollWidth <= el.clientWidth"
        )
    page.locator("#dashboard-timeline-event-table [data-clarid-toggle]").nth(1).hover()
    expect(page.locator("#dashboard-timeline-event-table .clarid-popover:visible")).to_have_count(1)


def test_dashboard_exposes_timeline_for_person_representation(page) -> None:
    _mock_dashboard_load(page, clinical_representation="person")
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#dashboardTimelineBtn").click()
    expect(page.locator("#dashboardTimelinePanel")).to_have_class(re.compile(r".*active.*"))
    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#dashboardTimelineBtn")).to_be_visible()
    expect(page.locator("#dashboardTimelineBtn")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#dashboardTimelinePanel")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#dashboardTimeline")).to_contain_text("Clinical coverage")
    expect(page.locator("#dashboardTimeline")).to_contain_text("Patient records")


def test_query_chats_persist_in_shared_list_and_reopen(page):
    _open_query_tab(page)
    _mock_query_reply(page)
    expect = playwright.expect
    page.set_viewport_size({'width': 1400, 'height': 900})
    page.locator('#analysisNewSessionBtn').click()
    expect(page.locator('#newChatChoices')).to_be_visible()
    page.locator('#newQueryChatBtn').click()
    question = 'Which patients have Crohn Disease?'
    page.locator('#question').fill(question)
    page.locator('#askBtn').click()
    expect(page.locator('#queryThread')).to_contain_text('Patients matching disease query')
    expect(page.locator('#askBtn')).to_be_enabled()
    row = page.locator('[data-query-session-id]').filter(has_text=question).first
    expect(row).to_be_visible()
    expect(row.locator('svg')).to_be_visible()
    chat_id = row.get_attribute('data-query-session-id')
    page.reload(wait_until='networkidle')
    row = page.locator(f'[data-query-session-id="{chat_id}"]')
    expect(row).to_be_visible()
    row.click()
    expect(page.locator('#queryTab')).to_have_class(re.compile(r'\bactive\b'))
    expect(page.locator('#queryThread')).to_contain_text('Patients matching disease query')
    expect(page.locator('#queryThread [data-query-action]')).to_have_count(0)
    expect(page.locator('#queryChatContextNotice')).to_contain_text('Saved results')
    row.locator('..').locator('summary').click()
    page.once('dialog', lambda dialog: dialog.accept('My saved Query'))
    page.locator(f'[data-query-rename="{chat_id}"]').click()
    expect(page.locator(f'[data-query-session-id="{chat_id}"]')).to_contain_text('My saved Query')
    page.locator('#analysisNewSessionBtn').click()
    page.locator('#newAnalysisChatBtn').click()
    expect(page.locator('#analysisTab')).to_have_class('tab-panel active')
    expect(page.locator('[data-query-session-id]').first).to_be_visible()
    expect(page.locator('[data-analysis-session-id]').first).to_be_visible()
    page.locator(f'[data-query-session-id="{chat_id}"]').click()
    page.locator(f'[data-query-session-id="{chat_id}"]').locator('..').locator('summary').click()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator(f'[data-query-delete="{chat_id}"]').click()
    expect(page.locator(f'[data-query-session-id="{chat_id}"]')).to_have_count(0)
    expect(page.locator('#queryThread')).not_to_contain_text('Patients matching disease query')


def test_query_chat_save_failure_retry_and_conflict_recovery(page):
    _open_query_tab(page)
    expect = playwright.expect
    page.set_viewport_size({'width': 1400, 'height': 900})
    def fail_save(route):
        if route.request.method == 'POST':
            route.fulfill(status=503, content_type='application/json', body='{"detail":"Temporary save failure"}')
        else:
            route.continue_()
    page.route('**/query-sessions', fail_save)
    page.locator('#question').fill('Draft to retain')
    expect(page.locator('#queryChatPersistence')).to_have_text('Not saved')
    page.locator('#analysisChatsDrawerCloseBtn').click()
    expect(page.locator('#queryChatMessage')).to_contain_text('Temporary save failure')
    expect(page.locator('#question')).to_have_value('Draft to retain')
    page.unroute('**/query-sessions', fail_save)
    page.locator('#queryChatSaveRetry').click()
    expect(page.locator('#queryChatPersistence')).to_have_text('Saved')
    expect(page.locator('#queryCurrentChatTitle')).to_have_text('Draft to retain')
    expect(page.locator('#queryChatMessage')).to_be_hidden()
    page.locator('#analysisChatsDrawerBtn').click()
    chat_id = page.locator('[data-query-session-id][aria-current="true"]').get_attribute('data-query-session-id')
    base_url = page.url.rstrip('/')
    saved = page.request.get(f'{base_url}/query-sessions/{chat_id}').json()
    saved.update(title='Changed in another window', title_custom=True)
    assert page.request.post(f'{base_url}/query-sessions', data=saved).ok
    page.locator('#question').fill('Unsaved conflicting draft')
    expect(page.locator('#queryChatPersistence')).to_have_text('Not saved')
    expect(page.locator('#queryChatSaveRetry')).to_have_text('Reload saved chat')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#queryChatSaveRetry').click()
    expect(page.locator('#queryCurrentChatTitle')).to_have_text('Changed in another window')
    expect(page.locator('#question')).to_have_value('Draft to retain')
    expect(page.locator('#queryChatPersistence')).to_have_text('Saved')


def test_restored_query_chat_general_history_excludes_workspace(page):
    _mock_available_lm(page)
    page.reload(wait_until='networkidle')
    _open_query_tab(page)
    _mock_query_reply(page)
    expect = playwright.expect
    page.set_viewport_size({'width': 1400, 'height': 900})
    page.locator('#question').fill('Which patients have Crohn Disease?')
    page.locator('#askBtn').click()
    expect(page.locator('#queryThread')).to_contain_text('Patients matching disease query')
    expect(page.locator('#askBtn')).to_be_enabled()
    chat_id = page.locator('[data-query-session-id][aria-current="true"]').get_attribute('data-query-session-id')
    page.reload(wait_until='networkidle')
    page.locator(f'[data-query-session-id="{chat_id}"]').click()
    page.locator('#queryContextGeneralBtn').click()
    captured = []
    def answer(route):
        captured.append(route.request.post_data_json)
        route.fulfill(status=200, content_type='application/json', body=json.dumps({
            'intent': 'general_llm', 'reply': 'A general answer.', 'data': {'source': 'general_llm'}}))
    page.route('**/llm/general', answer)
    page.locator('#question').fill('What is a cohort?')
    page.locator('#askBtn').click()
    expect(page.locator('#queryThread')).to_contain_text('A general answer.')
    expect(page.locator('#askBtn')).to_be_enabled()
    assert captured == [{'prompt': 'What is a cohort?', 'history': []}]
    page.reload(wait_until='networkidle')
    page.locator(f'[data-query-session-id="{chat_id}"]').click()
    expect(page.locator('#queryContextGeneralBtn')).to_have_attribute('aria-pressed', 'true')
    page.locator('#question').fill('Explain that again')
    page.locator('#askBtn').click()
    expect(page.locator('#askBtn')).to_be_enabled()
    assert captured[-1]['history'] == [{'role': 'user', 'content': 'What is a cohort?'}, {'role': 'assistant', 'content': 'A general answer.'}]


def test_query_result_focus_error_and_reset(page) -> None:
    _open_query_tab(page)
    expect = playwright.expect
    expect(page.locator('#queryStarterTopHost > #queryStarterPanel')).to_be_visible()
    page.route('**/query', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic service unavailable"}'))
    page.locator('#question').fill('List patients')
    page.locator('#askBtn').click()
    expect(page.locator('#queryThread')).to_contain_text('Synthetic service unavailable')
    expect(page.locator('#queryStarterPanel')).to_be_hidden()
    expect(page.locator('.query-thread-turn-latest > .analysis-turn-label')).to_have_text('Query not completed')
    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('#queryClearBtn').click()
    expect(page.locator('#queryStarterTopHost > #queryStarterPanel')).to_be_visible()
    expect(page.locator('#queryComposerTitle')).to_have_text('Ask a question')
    expect(page.locator('#queryStarterHost')).to_be_hidden()


def test_query_deterministic_reply_renders_and_handoff_to_analysis(page) -> None:
    _open_query_tab(page)
    _mock_query_reply(page)
    expect = playwright.expect
    captured = {}
    page.on(
        "request",
        lambda request: captured.setdefault("body", request.post_data_json)
        if request.url.endswith("/query")
        else None,
    )

    page.locator("#question").fill("Which patients have Crohn Disease?")
    page.locator("#askBtn").click()

    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")
    expect(page.locator("#queryThread")).to_contain_text("Dataset: Synthetic demo")
    details = page.locator("#queryThread .query-response-details").last
    expect(details.locator("summary")).to_be_visible()
    expect(details).not_to_have_attribute("open", "")
    expect(details.locator(".query-thread-turn-meta")).to_be_hidden()
    expect(page.locator("#queryThread [data-chat-copy-content]").last).to_contain_text(
        "Patients matching disease query")
    details.locator("summary").click()
    expect(details.locator(".query-thread-turn-meta")).to_be_visible()
    expect(page.locator("#queryThread")).to_contain_text("Response detail: Detailed")
    expect(page.locator("#queryThread .query-thread-turn-user .analysis-turn-body")).to_have_text("Which patients have Crohn Disease?")
    expect(page.locator("#queryThread .query-thread-turn-user")).to_have_css("background-color", "rgb(248, 250, 252)")
    expect(page.locator("#queryThread .query-thread-turn-user")).to_have_css("background-image", "none")
    expect(page.locator("#queryThread .query-thread-turn-user .analysis-turn-body")).to_have_css("color", "rgb(19, 34, 56)")
    expect(page.locator("#question")).to_have_value("")
    expect(page.locator("#queryMeta")).to_have_count(0)
    expect(page.locator("#queryStatus")).to_be_hidden()
    expect(page.locator("#queryStarterPanel")).to_be_hidden()
    expect(page.locator("#queryStarterHost > #queryStarterPanel")).to_have_count(1)
    expect(page.locator("#queryComposerTitle")).to_have_text("Ask a follow-up")
    expect(page.locator("#queryThread .query-thread-turn-latest > .analysis-turn-label")).to_have_text("Result")
    page.locator("#queryComposerExamplesBtn").click()
    expect(page.locator("#queryStarterPanel")).to_be_visible()
    expect(page.locator("#queryComposerExamplesBtn")).to_have_attribute("aria-expanded", "true")
    page.locator("#queryComposerExamplesBtn").click()
    expect(page.locator("#queryStarterPanel")).to_be_hidden()
    expect(page.locator("#queryThread .query-thread-turn-assistant")).to_have_css("background-color", "rgb(255, 255, 255)")
    expect(page.locator("#queryThread .query-thread-turn-assistant")).to_have_css("background-image", "none")
    expect(page.locator("#queryThread .query-thread-turn-assistant .analysis-turn-body")).to_have_css("color", "rgb(19, 34, 56)")
    deterministic_followup = page.locator("#queryThread [data-query-followup-mode='deterministic_only']")
    planner_followup = page.locator("#queryThread [data-query-followup-mode='planner_only']")
    expect(deterministic_followup).to_have_class(re.compile(r".*query-chip-deterministic.*"))
    expect(deterministic_followup).to_contain_text("Deterministic")
    expect(planner_followup).to_have_class(re.compile(r".*query-chip-planner.*"))
    expect(planner_followup).to_contain_text("LLM-planned")
    planner_followup.click()
    expect(page.locator("#question")).to_have_value("What evidence supports the treatment pattern?")
    expect(page.locator("#queryPlannerBtn")).to_have_attribute("aria-pressed", "true")
    assert captured["body"]["dataset_id"] == "default"
    assert "data_dir" not in captured["body"]
    expect(page.locator("#queryThread")).to_contain_text("Open in Analysis")
    page.locator("[data-query-action='use-analysis']").click()

    expect(page.locator("#analysisTab")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("SYN001,SYN002")


def test_query_external_assay_summary_renders_bounded_aggregate_table(page) -> None:
    _open_query_tab(page)
    expect = playwright.expect
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "external_assay_summary",
                    "reply": (
                        "Descriptive sample-level summary for Quantitative serology (4 samples; no inferential test).\n\n"
                        "| Feature | N | Missing | Mean | Median | Min | Max |\n"
                        "|---|---:|---:|---:|---:|---:|---:|\n"
                        "| Marker_A | 4 | 0 | 4 | 4 | 2 | 6 |"
                    ),
                    "data": {
                        "execution": "deterministic",
                        "source_boundary": "external_manifest_assay",
                        "modality": "serology",
                        "assay_results": [
                            {
                                "feature_id": "Marker_A",
                                "sample_count": 4,
                                "missing_count": 0,
                                "mean": 4.0,
                                "median": 4.0,
                                "min": 2.0,
                                "max": 6.0,
                            }
                        ],
                    },
                    "action_context": {"patient_ids": [], "record_ids": [], "id_type": "patient"},
                }
            ),
        ),
    )

    page.locator("#question").fill("Summarize Marker_A in serology")
    page.locator("#askBtn").click()

    turn = page.locator("#queryThread .query-thread-turn-assistant").last
    expect(turn).to_contain_text("Assay summary")
    expect(turn).to_contain_text("Deterministic")
    expect(turn.locator("table thead")).to_contain_text("Feature")
    expect(turn.locator("table tbody")).to_contain_text("Marker_A")
    expect(turn).to_contain_text("no inferential test")


def test_query_large_patient_result_is_bounded_and_pages_by_handle(page) -> None:
    _open_query_tab(page)
    expect = playwright.expect
    all_ids = [f"SYN{i:04d}" for i in range(1, 606)]
    result_handle = "query-result-test-handle"
    page_requests: list[str] = []
    query_bodies: list[dict] = []
    saved_cohort_bodies: list[dict] = []

    def result_page(start: int) -> dict:
        ids = all_ids[start : start + 50]
        next_start = start + len(ids)
        return {
            "result_handle": result_handle,
            "total_count": len(all_ids),
            "returned_count": len(ids),
            "page_size": 50,
            "has_more": next_start < len(all_ids),
            "next_cursor": f"cursor-{next_start}" if next_start < len(all_ids) else "",
            "expires_at": "2099-01-01T00:00:00Z",
            "patient_ids": ids,
            "sample_ids": [],
            "rows": [{"patient_id": patient_id, "sex": "", "visit_count": 1, "medication_count": 0} for patient_id in ids],
        }

    def query_handler(route):
        query_bodies.append(route.request.post_data_json)
        initial = result_page(0)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "patient_inventory",
                    "reply": "Patients: " + ", ".join(all_ids),
                    "data": {
                        "source": "deterministic",
                        "execution": "deterministic",
                        "patient_count": len(all_ids),
                        "result_handle": result_handle,
                        "result_page": initial,
                        "available_actions": {
                            "open_in_analysis": True,
                            "save_cohort": True,
                            "copy_patient_ids": True,
                            "use_in_pheno_ranker": True,
                        },
                    },
                    "action_context": {
                        "result_handle": result_handle,
                        "patient_ids": [],
                        "record_ids": [],
                        "id_type": "patient",
                        "analysis_prompt": "Summarize this selected patient cohort.",
                    },
                }
            ),
        )

    def page_handler(route):
        page_requests.append(route.request.url)
        match = re.search(r"cursor=cursor-(\d+)", route.request.url)
        start = int(match.group(1)) if match else 0
        route.fulfill(status=200, content_type="application/json", body=json.dumps(result_page(start)))

    def saved_cohort_handler(route):
        saved_cohort_bodies.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "id": "saved-large-query",
                    "name": "Large Query cohort",
                    "patient_ids": [],
                    "sample_ids": [],
                    "patient_count": len(all_ids),
                    "sample_count": 0,
                    "id_type": "patient",
                    "source": {"kind": "query", "prompt": "List all patients in this workspace"},
                }
            ),
        )

    page.route("**/saved-cohorts", saved_cohort_handler)
    _mock_analysis_reply(page)
    page.route("**/query-results/query-result-test-handle?*", page_handler)
    page.route("**/query", query_handler)
    page.locator("#question").fill("List all patients in this workspace")
    page.locator("#askBtn").click()

    latest_turn = page.locator("#queryThread .query-thread-turn-assistant").last
    expect(latest_turn.locator(".query-result-range")).to_have_text("Showing 1–50 of 605")
    expect(latest_turn.locator(".query-result-table tbody tr")).to_have_count(50)
    expect(latest_turn).to_contain_text("SYN0001")
    expect(latest_turn).not_to_contain_text("SYN0051")
    expect(latest_turn).not_to_contain_text("SYN0605")
    expect(latest_turn.locator("[data-query-action][data-query-patient-ids]")).to_have_count(0)
    expect(latest_turn.locator("[data-query-action][data-query-scope-ids]")).to_have_count(0)
    expect(latest_turn.locator("[data-query-action='copy-ids']")).to_have_count(0)

    page.once("dialog", lambda dialog: dialog.accept("Large Query cohort"))
    with page.expect_request("**/saved-cohorts"):
        latest_turn.locator("[data-query-action='save-cohort']").click()
    expect(page.locator("#queryStatus")).to_contain_text('Saved cohort "Large Query cohort"')
    assert saved_cohort_bodies[-1]["result_handle"] == result_handle
    assert saved_cohort_bodies[-1]["patient_ids"] == []
    assert saved_cohort_bodies[-1]["sample_ids"] == []

    latest_turn.locator("[data-query-action='use-analysis']").click()
    expect(page.locator("#analysisTab")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("")
    expect(page.locator("#analysisSelectedPatientIdsSummary")).to_contain_text("identifiers remain server-side")
    with page.expect_request("**/analysis") as analysis_request:
        page.locator("#analysisRunBtn").click()
    analysis_body = analysis_request.value.post_data_json
    assert analysis_body["query_result_handle"] == result_handle
    assert analysis_body["selected_patient_ids"] == ""
    page.locator("#queryTabBtn").click()

    latest_turn.get_by_role("button", name="Load more").click()
    expect(latest_turn.locator(".query-result-range")).to_have_text("Showing 51–100 of 605")
    expect(latest_turn.locator(".query-result-table tbody tr")).to_have_count(50)
    expect(latest_turn).to_contain_text("SYN0051")
    expect(latest_turn).not_to_contain_text("SYN0001")
    assert page_requests and "cursor=cursor-50" in page_requests[-1]
    assert "limit=50" in page_requests[-1]

    latest_turn.get_by_role("button", name="Previous").click()
    expect(latest_turn.locator(".query-result-range")).to_have_text("Showing 1–50 of 605")
    expect(latest_turn).to_contain_text("SYN0001")
    assert "cursor=" not in page_requests[-1]

    expect(page.locator("#queryMemoryBtn")).to_have_attribute("aria-pressed", "false")
    page.locator("#queryMemoryBtn").click()
    expect(page.locator("#queryMemoryBtn")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#queryMemoryBtn")).to_contain_text("previous result (605 patients)")
    page.locator("#question").fill("Which of those patients have more than one medication?")
    with page.expect_request("**/query") as followup_request:
        page.locator("#askBtn").click()
    followup_body = followup_request.value.post_data_json
    assert followup_body["scoped_result_handle"] == result_handle
    assert followup_body["scoped_patient_ids"] == []
    assert followup_body["history"][-1]["content"] == "Query result: 605 patients matched (patient_inventory)."


def test_query_expired_result_retires_handle_actions_and_prompt_scope(page) -> None:
    _open_query_tab(page)
    expect = playwright.expect
    patient_ids = [f"SYN{i:04d}" for i in range(1, 61)]
    result_handle = "query-result-expired-handle"
    query_bodies: list[dict] = []

    def query_handler(route):
        query_bodies.append(route.request.post_data_json)
        if len(query_bodies) > 1:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "intent": "patient_inventory",
                        "reply": "60 patients are in the workspace.",
                        "data": {
                            "source": "deterministic",
                            "patient_count": 60,
                            "count_only": True,
                            "available_actions": {
                                "open_in_analysis": False,
                                "save_cohort": False,
                                "copy_patient_ids": False,
                                "use_in_pheno_ranker": False,
                            },
                        },
                        "action_context": {"patient_ids": [], "record_ids": [], "id_type": ""},
                    }
                ),
            )
            return
        visible_ids = patient_ids[:50]
        result_page = {
            "result_handle": result_handle,
            "total_count": len(patient_ids),
            "returned_count": len(visible_ids),
            "page_size": 50,
            "has_more": True,
            "next_cursor": "cursor-50",
            "expires_at": "2000-01-01T00:00:00Z",
            "patient_ids": visible_ids,
            "sample_ids": [],
            "rows": [{"patient_id": patient_id} for patient_id in visible_ids],
        }
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "patient_inventory",
                    "reply": "Patients: " + ", ".join(patient_ids),
                    "data": {
                        "source": "deterministic",
                        "execution": "deterministic",
                        "patient_count": len(patient_ids),
                        "result_handle": result_handle,
                        "result_page": result_page,
                        "available_actions": {
                            "open_in_analysis": True,
                            "save_cohort": True,
                            "copy_patient_ids": False,
                            "use_in_pheno_ranker": False,
                        },
                    },
                    "action_context": {
                        "result_handle": result_handle,
                        "patient_ids": [],
                        "record_ids": [],
                        "id_type": "patient",
                    },
                }
            ),
        )

    page.route(
        "**/query-results/query-result-expired-handle?*",
        lambda route: route.fulfill(
            status=410,
            content_type="application/json",
            body=json.dumps({"detail": "Query result has expired."}),
        ),
    )
    page.route("**/query", query_handler)
    page.evaluate(
        """
        () => {
          const originalFetch = window.fetch.bind(window);
          window.__queryResultFetchCacheModes = [];
          window.fetch = (input, init = {}) => {
            const url = typeof input === "string" ? input : String(input && input.url || input);
            if (url.includes("/query-results/")) {
              window.__queryResultFetchCacheModes.push(String(init.cache || ""));
            }
            return originalFetch(input, init);
          };
        }
        """
    )

    page.locator("#question").fill("List all patients in this workspace")
    page.locator("#askBtn").click()
    latest_turn = page.locator("#queryThread .query-thread-turn-assistant").last
    expect(latest_turn.locator("[data-query-action='save-cohort']")).to_have_count(1)
    expect(latest_turn.locator("[data-query-action='use-analysis']")).to_have_count(1)
    page.locator("#queryMemoryBtn").click()
    expect(page.locator("#queryMemoryBtn")).to_have_attribute("aria-pressed", "true")

    latest_turn.get_by_role("button", name="Load more").click()

    expect(latest_turn.locator(".query-result-page-error")).to_contain_text(
        "This Query result has expired. Run the query again to recreate it."
    )
    expect(latest_turn.locator(".query-result-table tbody tr")).to_have_count(50)
    expect(latest_turn).to_contain_text("SYN0001")
    expect(latest_turn.locator("[data-query-action]")).to_have_count(0)
    expect(latest_turn.locator("[data-query-page-action]")).to_have_count(0)
    expect(page.locator("#queryMemoryBtn")).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#queryMemoryBtn")).to_contain_text("Prompt scope: workspace")
    assert page.evaluate("window.__queryResultFetchCacheModes") == ["no-store"]

    page.locator("#queryMemoryBtn").click()
    page.locator("#question").fill("How many of those patients are female?")
    with page.expect_request("**/query") as followup_request:
        page.locator("#askBtn").click()
    assert followup_request.value.post_data_json["scoped_result_handle"] == ""


@pytest.mark.parametrize("sample_level", [False, True])
def test_query_tables_show_linked_subject_clarid(page, sample_level):
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    playwright.expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    _open_query_tab(page)
    identifiers = ["SYN001:week_0", "unlinked-sample"] if sample_level else ["SYN001", "SYN002"]
    key = "sample_ids" if sample_level else "patient_ids"
    payload = {"intent": "sample_inventory" if sample_level else "patient_inventory",
               "reply": "Matching records", "data": {key: identifiers, "source": "deterministic"},
               "action_context": {"id_type": "sample" if sample_level else "patient"}}
    page.route("**/query", lambda route: route.fulfill(content_type="application/json", body=json.dumps(payload)))
    page.locator("#question").fill("List records")
    page.locator("#askBtn").click()
    table = page.locator("#queryThread .query-result-table").last
    playwright.expect(table.locator("thead")).to_contain_text("Subject ClarID" if sample_level else "ClarID")
    badge = table.locator("[data-clarid-toggle]")
    playwright.expect(badge).to_have_count(1)
    badge.click()
    playwright.expect(badge).to_have_attribute("aria-expanded", "true")
    playwright.expect(table).to_contain_text("SyntheticStudy-00001-Case-K50.9-Female-A40_49")
    playwright.expect(table).to_contain_text("Crohn's disease, unspecified (K50.9)")
    playwright.expect(table.locator("tbody tr").last).to_contain_text("Not available")


def test_query_sample_result_uses_sample_table_and_sample_count(page) -> None:
    _open_query_tab(page)
    expect = playwright.expect
    sample_ids = [f"SYN{i:03d}:week_0" for i in range(1, 51)]
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "sample_inventory",
                    "reply": "Samples: " + ", ".join(sample_ids),
                    "data": {
                        "source": "deterministic",
                        "sample_count": 120,
                        "result_handle": "sample-result-handle",
                        "result_page": {
                            "result_handle": "sample-result-handle",
                            "total_count": 120,
                            "returned_count": 50,
                            "page_size": 50,
                            "has_more": True,
                            "next_cursor": "sample-cursor-50",
                            "sample_ids": sample_ids,
                            "patient_ids": [],
                            "rows": [{"sample_id": sample_id} for sample_id in sample_ids],
                        },
                        "available_actions": {"open_in_analysis": True, "save_cohort": True},
                    },
                    "action_context": {
                        "result_handle": "sample-result-handle",
                        "patient_ids": [],
                        "record_ids": [],
                        "id_type": "sample",
                    },
                }
            ),
        ),
    )

    page.locator("#question").fill("List all samples")
    page.locator("#askBtn").click()
    latest_turn = page.locator("#queryThread .query-thread-turn-assistant").last
    expect(latest_turn).to_contain_text("120 samples match this query")
    expect(latest_turn.locator(".query-result-range")).to_have_text("Showing 1–50 of 120")
    expect(latest_turn.locator(".query-result-table thead")).to_have_text("SampleSubject ClarID")
    expect(latest_turn.locator(".query-result-table thead")).not_to_contain_text("Patient")
    expect(latest_turn.locator(".query-result-table tbody tr")).to_have_count(50)


def test_query_disease_cohort_keeps_patient_ids_visible_and_scrollable(page) -> None:
    page.set_viewport_size({"width": 600, "height": 900})
    _open_query_tab(page)
    expect = playwright.expect
    patient_ids = [f"SLE{i:04d}" for i in range(1, 51)]
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "disease_cohort",
                    "reply": "Patients matching Systemic Lupus Erythematosus are shown below.",
                    "data": {
                        "source": "deterministic",
                        "patient_count": 62,
                        "result_handle": "disease-result-handle",
                        "result_page": {
                            "result_handle": "disease-result-handle",
                            "total_count": 62,
                            "returned_count": 50,
                            "page_size": 50,
                            "has_more": True,
                            "next_cursor": "disease-cursor-50",
                            "patient_ids": patient_ids,
                            "sample_ids": [],
                            # The identifier list is canonical even when optional row metadata omits it.
                            "rows": [
                                {"sex": "female", "visit_count": 1, "medication_count": 2}
                                for _patient_id in patient_ids
                            ],
                        },
                        "available_actions": {"open_in_analysis": True, "save_cohort": True},
                    },
                    "action_context": {
                        "result_handle": "disease-result-handle",
                        "patient_ids": [],
                        "record_ids": [],
                        "id_type": "patient",
                    },
                }
            ),
        ),
    )

    page.locator("#question").fill("Which patients have Systemic Lupus Erythematosus?")
    page.locator("#askBtn").click()
    latest_turn = page.locator("#queryThread .query-thread-turn-assistant").last
    first_id = latest_turn.locator(".query-result-table tbody .query-result-id-cell").first
    expect(first_id).to_have_text("SLE0001")
    expect(first_id).to_be_visible()
    table_scroll = latest_turn.locator(".query-result-table-scroll")
    measurements = table_scroll.evaluate(
        "element => ({clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, overflowX: getComputedStyle(element).overflowX})"
    )
    assert measurements["scrollWidth"] > measurements["clientWidth"]
    assert measurements["overflowX"] == "auto"
    assert first_id.evaluate("element => getComputedStyle(element).position") == "sticky"


def test_query_provenance_separates_response_detail_from_model_context(page) -> None:
    _open_query_tab(page)
    expect = playwright.expect
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "llm_fallback",
                    "reply": "There are 42 patients receiving biologic therapy.",
                    "data": {
                        "provider": "lm_studio",
                        "source": "llm",
                        "dataset_name": "Private study",
                        "granularity_requested": "detailed",
                        "granularity_applied": "detailed",
                        "ai_provider_access": "safe_summary",
                        "ai_provider_context_granularity": "safe_summary",
                        "model": "openai/gpt-oss-20b",
                    },
                }
            ),
        ),
    )

    page.locator("#question").fill("How many patients take biologics?")
    page.locator("#askBtn").click()

    expect(page.locator("#queryThread")).to_contain_text("Response detail: Detailed")
    expect(page.locator("#queryThread")).to_contain_text("Model context: Safe summary")
    expect(page.locator("#queryThread")).to_contain_text("LLM answer")
    expect(page.locator("#queryThread")).not_to_contain_text("Disclosure:")


def test_latest_query_details_user_setting_controls_panel_visibility(page) -> None:
    expect = playwright.expect
    settings = {"latest_query_details": True}

    def settings_handler(route):
        if route.request.method == "PATCH":
            settings.update(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(settings))

    page.route("**/user-settings", settings_handler)
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"intent": "count", "reply": "2 patients.", "data": {"source": "deterministic"}}),
        ),
    )
    page.reload(wait_until="networkidle")
    expect(page.locator("#userSettingsStatus")).to_have_text("Preferences loaded.")
    expect(page.locator("#loadStatus")).to_contain_text("Loaded")
    _open_query_tab(page)
    page.locator("#question").fill("How many patients are in the workspace?")
    page.locator("#askBtn").click()
    expect(page.locator("#queryThread")).to_contain_text("2 patients.")
    expect(page.locator("#queryLatestDetails")).to_be_visible()

    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator("#userSettingsBtn").click()
    expect(page.locator("#settingsLatestQueryDetails")).to_be_checked()
    page.locator("#settingsLatestQueryDetails").uncheck()
    page.locator("#userSettingsSaveBtn").click()
    expect(page.locator("#userSettingsStatus")).to_have_text("Preferences saved.")
    _open_query_tab(page)
    expect(page.locator("#queryLatestDetails")).to_be_hidden()

    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator("#userSettingsBtn").click()
    page.locator("#settingsLatestQueryDetails").check()
    page.locator("#userSettingsSaveBtn").click()
    expect(page.locator("#userSettingsStatus")).to_have_text("Preferences saved.")
    _open_query_tab(page)
    expect(page.locator("#queryLatestDetails")).to_be_visible()


def test_query_general_question_mode_sends_no_workspace_context(page) -> None:
    expect = playwright.expect
    captured = []
    workspace_query_called = {"value": False}
    page._cohortome_dataset_state["current_ids"] = []
    _mock_available_lm(page)

    def general_handler(route):
        captured.append(route.request.post_data_json)
        reply = (
            "Aspirin is a medicine with analgesic, anti-inflammatory, and antiplatelet uses."
            if len(captured) == 1
            else "It irreversibly inhibits platelet cyclooxygenase-1 and reduces thromboxane production."
        )
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "general_llm",
                    "reply": reply,
                    "data": {
                        "source": "general_llm",
                        "execution": "llm",
                        "context_mode": "none",
                        "workspace_context_used": False,
                        "model": "openai/gpt-oss-20b",
                    },
                }
            ),
        )

    def unexpected_workspace_query(route):
        workspace_query_called["value"] = True
        route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "unexpected"}))

    page.route("**/llm/general", general_handler)
    page.route("**/query", unexpected_workspace_query)
    page.reload(wait_until="networkidle")
    _open_query_tab(page)

    page.locator("#queryContextGeneralBtn").click()
    expect(page.locator("#queryContextGeneralBtn")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#queryGranularityModeValue")).to_have_text("No workspace context")
    page.locator("#question").fill("What is aspirin?")
    page.locator("#askBtn").click()

    expect(page.locator("#queryThread")).to_contain_text("General LLM answer")
    expect(page.locator("#queryThread")).to_contain_text("No workspace context")
    expect(page.locator("#queryThread")).to_contain_text("openai/gpt-oss-20b")
    expect(page.locator("#queryThread")).not_to_contain_text("Response detail:")
    assert captured[0] == {"prompt": "What is aspirin?", "history": []}
    assert workspace_query_called["value"] is False

    page.locator("#question").fill("How does it reduce platelet aggregation?")
    page.locator("#askBtn").click()
    expect(page.locator("#queryThread")).to_contain_text("reduces thromboxane production")
    assert captured[1]["history"] == [
        {"role": "user", "content": "What is aspirin?"},
        {"role": "assistant", "content": "Aspirin is a medicine with analgesic, anti-inflammatory, and antiplatelet uses."},
    ]


def test_query_disease_selector_runs_deterministic_cohort(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_disease_inventory(page)
    _mock_query_reply(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    expect(page.locator("#loadBtn")).to_be_visible()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")

    _open_query_tab(page)
    expect(page.locator("#queryDiseaseStatus")).to_contain_text("Click a disease")

    page.locator("#queryDiseaseBuilderBtn").click()
    expect(page.locator("#queryDiseasePanel")).to_be_visible()
    page.locator("[data-query-disease-chip='Crohn Disease']").click()

    expect(page.locator("#question")).to_have_value("Which patients have Crohn Disease?")
    expect(page.locator("#queryDiseaseStatus")).to_contain_text("Prompt prepared for disease workspace Crohn Disease")


def test_analysis_deterministic_reply_renders_in_thread(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this workspace.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("Crohn Disease and recurrent Infliximab exposure")
    expect(page.locator("#analysisThread")).to_contain_text("Deterministic")
    expect(page.locator("#analysisThread .analysis-turn-user")).to_have_css("background-color", "rgb(248, 250, 252)")
    expect(page.locator("#analysisThread .analysis-turn-user")).to_have_css("background-image", "none")
    expect(page.locator("#analysisThread .analysis-turn-user .analysis-turn-body")).to_have_css("color", "rgb(19, 34, 56)")
    expect(page.locator("#analysisThread .analysis-turn-assistant")).to_have_css("background-color", "rgb(255, 255, 255)")
    expect(page.locator("#analysisThread .analysis-turn-assistant")).to_have_css("background-image", "none")
    expect(page.locator("#analysisThread .analysis-turn-assistant .analysis-turn-body")).to_have_css("color", "rgb(19, 34, 56)")


def test_analysis_general_question_mode_bypasses_workspace_analysis(page) -> None:
    expect = playwright.expect
    captured = []
    workspace_analysis_called = {"value": False}
    _mock_available_lm(page)

    page.route(
        "**/llm/general",
        lambda route: (
            captured.append(route.request.post_data_json),
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "intent": "general_llm",
                        "reply": "Aspirin irreversibly inhibits platelet cyclooxygenase-1.",
                        "data": {
                            "source": "general_llm",
                            "execution": "llm",
                            "context_mode": "none",
                            "workspace_context_used": False,
                            "model": "openai/gpt-oss-20b",
                        },
                    }
                ),
            ),
        ),
    )

    def unexpected_workspace_analysis(route):
        workspace_analysis_called["value"] = True
        route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "unexpected"}))

    page.route("**/analysis", unexpected_workspace_analysis)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)

    page.locator("#analysisContextGeneralBtn").click()
    expect(page.locator("#analysisContextGeneralBtn")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#analysisWorkspaceSetup")).to_be_hidden()
    expect(page.locator("#analysisRunBtnLabel")).to_have_text("Ask")
    page.locator("#analysisPrompt").fill("How does aspirin affect platelets?")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("General LLM answer")
    expect(page.locator("#analysisThread")).to_contain_text("No workspace context")
    expect(page.locator("#analysisThread")).to_contain_text("Aspirin irreversibly inhibits")
    expect(page.locator("#analysisThread .analysis-turn-user").last).not_to_contain_text("Scope:")
    assert captured == [{"prompt": "How does aspirin affect platelets?", "history": []}]
    assert workspace_analysis_called["value"] is False


def test_analysis_delete_confirmation_takes_precedence_over_open_chats_drawer(page) -> None:
    expect = playwright.expect
    page.set_viewport_size({'width': 900, 'height': 900})
    _open_analysis_tab(page)

    page.locator("#analysisChatsDrawerBtn").click()
    expect(page.locator("#analysisChatsDrawer")).to_be_visible()
    page.locator('#analysisSessionList .analysis-chat-menu summary').first.click()
    delete_button = page.locator("#analysisSessionList [data-analysis-session-delete]").first
    expect(delete_button).to_be_visible()
    delete_button.click()

    dialog = page.locator("#analysisSessionDeleteDialog")
    expect(dialog).to_be_visible()
    for button in ('analysisSessionDeleteCloseBtn', 'analysisSessionDeleteOnlyBtn', 'analysisSessionDeleteAllBtn'):
        assert page.locator(f'#{button}').evaluate('el => getComputedStyle(el).fontSize') == '13px'
        assert page.locator(f'#{button}').evaluate('el => getComputedStyle(el).paddingTop') == '8px'
    expect(page.locator("#analysisSessionDeleteDialog .analysis-session-delete-dialog-panel")).to_be_visible()
    layers = page.evaluate(
        """() => ({
          drawer: Number.parseInt(getComputedStyle(document.getElementById('analysisChatsDrawer')).zIndex, 10),
          dialog: Number.parseInt(getComputedStyle(document.getElementById('analysisSessionDeleteDialog')).zIndex, 10),
        })"""
    )
    assert layers["dialog"] > layers["drawer"]
    dialog_owns_drawer_hit_area = page.evaluate(
        """() => {
          const drawerPanel = document.querySelector('#analysisChatsDrawer .analysis-chats-drawer-panel');
          const dialog = document.getElementById('analysisSessionDeleteDialog');
          const bounds = drawerPanel.getBoundingClientRect();
          const hit = document.elementFromPoint(bounds.left + 20, bounds.bottom - 20);
          return Boolean(hit && dialog.contains(hit));
        }"""
    )
    assert dialog_owns_drawer_hit_area is True

    page.locator("#analysisSessionDeleteCloseBtn").click()
    expect(dialog).to_be_hidden()
    expect(page.locator("#analysisChatsDrawer")).to_be_visible()


def test_navigation_rail_account_and_runs(page):
    expect = playwright.expect
    expect(page.locator('.app-header #globalContextBar')).to_be_visible()
    expect(page.locator('.app-content #globalContextBar')).to_have_count(0)
    page.set_viewport_size({'width': 1400, 'height': 900})
    compose = page.get_by_role('button', name='New chat', exact=True)
    expect(compose).to_be_visible()
    assert compose.bounding_box()['width'] <= 36
    assert compose.bounding_box()['y'] == pytest.approx(
        page.locator('#analysisChatsDrawerCloseBtn').bounding_box()['y'], abs=3)
    expect(page.get_by_role('button', name='Hide chats', exact=True)).to_be_visible()
    compose.focus()
    expect(compose).to_be_focused()
    assert compose.evaluate('el => getComputedStyle(el).outlineStyle') != 'none'
    expect(page.locator('.app-header #runHistoryDrawerBtn')).to_have_count(0)
    expect(page.locator('#accountMenu')).to_be_hidden()
    page.locator('#accountMenuButton').click()
    expect(page.locator('#userSettingsBtn')).to_be_visible()
    expect(page.locator('#heroLogoutBtn')).to_be_hidden()
    page.keyboard.press('Escape')
    expect(page.locator('#accountMenu')).to_be_hidden()
    expect(page.locator('#accountMenuButton')).to_be_focused()
    page.locator('#accountMenuButton').click()
    if not page.locator("#userSettingsBtn").is_visible(): page.locator("#accountMenuButton").click()
    page.locator('#userSettingsBtn').click()
    expect(page.locator('#userSettingsPanel')).to_be_visible()
    expect(page.locator('#accountMenu')).to_be_hidden()
    page.locator('#userSettingsCloseBtn').click()
    page.locator('#runHistoryDrawerBtn').click()
    expect(page.locator('#runHistoryDrawer')).to_be_visible()
    page.locator('#jobsDrawerBtn').click()
    expect(page.locator('#jobsDrawer')).to_be_visible()
    expect(page.locator('#runHistoryDrawer')).to_be_hidden()
    page.locator('#jobsDrawerCloseBtn').click()
    page.locator('#dashboardTabBtn').click()
    expect(page.locator('#dashboardTab .dashboard-page-tabs')).to_be_visible()
    assert page.locator('.dashboard-page-tabs .dashboard-subtab.active').evaluate(
        'el => getComputedStyle(el).borderRadius') == '0px'
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.locator('#globalContextBar').evaluate('el => el.scrollWidth <= el.clientWidth')
    page.locator('#accountMenuButton').click()
    expect(page.locator('#userSettingsBtn')).to_be_in_viewport()


def test_bulk_chat_selection_and_clear_history_scope(page):
    expect = playwright.expect
    base = page.url.rstrip('/')
    for kind in ('query', 'analysis'):
        assert page.request.post(base + f'/{kind}-sessions', data={
            'id': 'bulk-' + kind, 'title': 'Bulk ' + kind, 'dataset_id': 'default',
        }).ok
    assert page.request.post(base + '/chat-folders/pin', data={'kind': 'query', 'chat_id': 'bulk-query', 'pinned': True}).ok
    page.reload(wait_until='networkidle')
    page.locator('#analysisNewSessionBtn').click()
    page.locator('#selectChatsBtn').click()
    for kind in ('query', 'analysis'):
        page.locator(f'[data-select-chat="{kind}:bulk-{kind}"]').first.check()
    expect(page.locator('.chat-selection-bar')).to_contain_text('2 selected')
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.locator('[data-delete-selected]').click()
    expect(page.locator('[data-select-chat="query:bulk-query"]').first).to_be_checked()
    page.once('dialog', lambda dialog: dialog.accept())
    with page.expect_request(lambda request: request.method == 'DELETE' and '/analysis-sessions/bulk-analysis' in request.url) as deleted_request:
        page.locator('[data-delete-selected]').click()
    assert 'keep_generated_jobs=true' in deleted_request.value.url
    expect(page.locator('#chatFolderStatus')).to_contain_text('Deleted 2 chats')
    for kind in ('query', 'analysis'):
        saved = page.request.get(base + f'/{kind}-sessions').json()['sessions']
        assert not any(item['id'] == 'bulk-' + kind for item in saved)
    assert page.request.post(base + '/query-sessions', data={'id': 'bulk-pinned', 'title': 'Keep pinned', 'dataset_id': 'default'}).ok
    assert page.request.post(base + '/chat-folders/pin', data={'kind': 'query', 'chat_id': 'bulk-pinned', 'pinned': True}).ok
    page.reload(wait_until='networkidle')
    page.locator('#accountMenuButton').click()
    page.locator('#userSettingsBtn').click()
    page.locator('#userDeleteChatsBtn').evaluate('(el) => el.click()')
    expect(page.locator('#clearChatsDialog')).to_be_visible()
    page.locator('#clearChatsKind').select_option('query')
    count = int(page.locator('#clearChatsCount').inner_text().split()[0])
    page.locator('#clearChatsPinned').check()
    expect(page.locator('#clearChatsCount')).to_contain_text(f'{count + 1} chats')
    page.locator('#clearChatsCancel').click()
    assert page.request.get(base + '/query-sessions/bulk-pinned').ok
    assert page.request.post(base + '/chat-folders/pin', data={'kind': 'query', 'chat_id': 'bulk-pinned', 'pinned': False}).ok
    assert page.request.delete(base + '/query-sessions/bulk-pinned').ok


def test_shared_chat_folders_move_pin_rename_search_and_delete(page):
    expect = playwright.expect
    page.set_viewport_size({'width': 1400, 'height': 900})
    base = page.url.rstrip('/')
    assert page.request.post(base + '/query-sessions', data={'id': 'folder-query', 'title': 'Folder Query', 'title_custom': True, 'dataset_id': 'default'}).ok
    assert page.request.post(base + '/analysis-sessions', data={'id': 'folder-analysis', 'title': 'Folder Analysis', 'dataset_id': 'default'}).ok
    page.reload(wait_until='networkidle')
    expect(page.locator('#analysisChatSearch')).to_be_hidden()
    page.locator('#analysisNewSessionBtn').click()
    page.once('dialog', lambda dialog: dialog.accept('Research'))
    page.locator('#newChatFolderBtn').click()
    folder = page.locator('.chat-folder').filter(has=page.locator('[data-folder-toggle]', has_text='Research'))
    expect(folder).to_be_visible()
    expect(folder.locator('[data-chat-kind="folder"] .chat-menu-icon svg')).to_have_count(1)
    expect(folder.locator('[data-folder-rename] .chat-menu-icon svg')).to_have_count(1)
    expect(folder.locator('[data-folder-delete] .chat-menu-icon svg')).to_have_count(1)
    folder_button = folder.locator('[data-folder-toggle]')
    assert folder_button.locator('svg').bounding_box()['x'] - folder_button.bounding_box()['x'] < 10
    folder_id = folder.get_attribute('data-folder-id')
    for kind in ('query', 'analysis'):
        chat_id = 'folder-' + kind
        page.locator(f'[data-{kind}-session-id="{chat_id}"]').first.locator('..').locator('summary').click()
        page.locator(f'[data-chat-move="{chat_id}"]').first.click()
        expect(page.locator('#chatMoveDialog')).to_be_visible()
        page.locator('#chatMoveDestination').select_option(folder_id)
        page.locator('#chatMoveConfirm').click()
        expect(page.locator('#chatMoveDialog')).not_to_be_visible()
        expect(folder.locator(f'[data-{kind}-session-id="{chat_id}"]')).to_be_visible()
        assert folder.locator(f'[data-{kind}-session-id="{chat_id}"]').bounding_box()['x'] > folder_button.bounding_box()['x'] + 16
    folder.locator('[data-query-session-id="folder-query"]').locator('..').locator('summary').click()
    folder.locator('[data-chat-pin="folder-query"]').click()
    expect(page.locator('[aria-label="Pinned"] [data-query-session-id="folder-query"]')).to_be_visible()
    expect(folder.locator('[data-query-session-id="folder-query"]')).to_be_visible()
    folder.locator('.chat-folder-heading summary').click()
    folder.locator('[data-chat-kind="folder"]').click()
    expect(page.locator('[aria-label="Pinned"] [data-folder-open]')).to_have_count(1)
    shortcut = page.locator('[aria-label="Pinned"] [data-folder-open]')
    assert shortcut.locator('svg').bounding_box()['x'] - shortcut.bounding_box()['x'] < 10
    folder.locator('.chat-folder-heading summary').click()
    page.once('dialog', lambda dialog: dialog.accept('Exploration'))
    folder.locator('[data-folder-rename]').click()
    expect(page.locator('[data-folder-toggle]', has_text='Exploration')).to_be_visible()
    page.reload(wait_until='networkidle')
    folder = page.locator(f'[data-folder-id="{folder_id}"]')
    expect(folder.locator('[data-query-session-id="folder-query"]')).to_be_visible()
    expect(folder.locator('[data-analysis-session-id="folder-analysis"]')).to_be_visible()
    folder.locator('[data-folder-toggle]').click()
    expect(folder.locator('.chat-folder-body')).to_be_hidden()
    page.locator('#chatSearchToggle').click()
    page.locator('#analysisChatSearch').fill('Folder Analysis')
    expect(folder.locator('[data-analysis-session-id="folder-analysis"]')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#analysisChatSearch')).to_be_hidden()
    expect(page.locator('#chatSearchToggle')).to_be_focused()
    folder.locator('.chat-folder-heading summary').click()
    page.once('dialog', lambda dialog: dialog.accept())
    folder.locator('[data-folder-delete]').click()
    expect(folder).to_have_count(0)
    expect(page.locator('[aria-label="Unfiled"] [data-analysis-session-id="folder-analysis"]')).to_be_visible()
    expect(page.locator('[aria-label="Pinned"] [data-query-session-id="folder-query"]')).to_be_visible()
    expect(page.locator('[data-folder-open]')).to_have_count(0)
    assert page.request.post(base + '/chat-folders/pin', data={'kind': 'query', 'chat_id': 'folder-query', 'pinned': False}).ok
    assert page.request.delete(base + '/query-sessions/folder-query').ok
    assert page.request.delete(base + '/analysis-sessions/folder-analysis').ok


def test_chat_sidebar_resize_drag_keyboard_and_reload(page):
    expect = playwright.expect
    page.set_viewport_size({'width': 1500, 'height': 1000})
    divider = page.get_by_role('separator', name='Chats width')
    expect(divider).to_be_visible()
    initial = int(divider.get_attribute('aria-valuenow'))
    box = divider.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 60)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] / 2 + 70, box['y'] + 60)
    page.mouse.up()
    expect(divider).to_have_attribute('aria-valuenow', str(initial + 70))
    assert page.locator('.app-sidebar').bounding_box()['width'] == pytest.approx(initial + 70, abs=1)
    divider.focus()
    page.keyboard.press('ArrowRight')
    expected = initial + 80
    expect(divider).to_have_attribute('aria-valuenow', str(expected))
    page.reload(wait_until='networkidle')
    expect(divider).to_have_attribute('aria-valuenow', str(expected))
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    expect(divider).to_be_visible()
    page.locator('#analysisChatsDrawerCloseBtn').click()
    expect(divider).to_be_hidden()
    page.locator('#analysisChatsDrawerBtn').click()
    expect(divider).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(divider).to_be_hidden()


def test_analysis_chat_sidebar_search_and_responsive_drawer(page):
    page.set_viewport_size({'width': 1600, 'height': 1000})
    _open_analysis_tab(page)
    expect = playwright.expect
    dock = page.locator('#analysisChatDock')
    expect(dock).to_be_visible()
    expect(page.locator('.app-icon-rail #accountAvatar')).to_be_visible()
    expect(page.locator('#analysisNewSessionTopBtn')).to_have_count(0)
    expect(page.locator('#analysisChatsDrawerBtn')).to_be_hidden()
    expect(dock.locator('#accountAvatar')).to_have_count(0)
    expect(dock.locator('#analysisSessionList')).to_be_visible()
    assert dock.evaluate('el => Boolean(el.closest(".app-sidebar"))')
    page.locator('#queryTabBtn').click()
    expect(dock).to_be_visible()
    page.locator('#analysisSessionList [data-analysis-session-id]').first.click()
    expect(page.locator('#analysisTab')).to_have_class('tab-panel active')
    expect(dock.locator('.analysis-session-main[aria-current="true"]')).to_have_count(1)
    expect(dock.locator('.analysis-chat-date').first).to_have_text('Today')
    page.locator('#chatSearchToggle').click()
    page.locator('#analysisChatSearch').fill('no-such-conversation-9876')
    expect(page.locator('#analysisSessionList')).to_contain_text('No matching chats')
    page.locator('#analysisChatSearch').fill('')
    page.locator('#analysisSessionList .analysis-chat-menu summary').first.click()
    page.once('dialog', lambda dialog: dialog.accept('My renamed analysis'))
    page.locator('[data-analysis-session-rename]').first.click()
    expect(page.locator('#analysisSessionList')).to_contain_text('My renamed analysis')
    page.locator('#analysisChatsDrawerCloseBtn').click()
    expect(dock).to_be_hidden()
    page.locator('#analysisChatsDrawerBtn').click()
    expect(dock).to_be_visible()
    page.set_viewport_size({'width': 900, 'height': 900})
    expect(dock).to_be_hidden()
    expect(page.locator('.app-icon-rail #accountAvatar')).to_be_visible()
    page.locator('#analysisChatsDrawerBtn').click()
    expect(page.locator('#analysisChatsDrawer')).to_be_visible()
    expect(page.get_by_role('button', name='Close chats', exact=True)).to_be_visible()
    expect(page.locator('#analysisChatsDrawerCloseBtn svg')).to_be_visible()
    expect(page.locator('#analysisChatSearch')).to_be_visible()
    page.locator('[data-analysis-session-id]').first.click()
    expect(page.locator('#analysisChatsDrawer')).to_be_hidden()


def test_analysis_deterministic_starter_chip_forces_deterministic_mode(page) -> None:
    _open_analysis_tab(page)
    page.locator("#analysisMethodSelect").select_option("custom")
    page.locator("#analysisComposerExamplesBtn").click()
    captured = {}

    def handler(route):
        captured["body"] = route.request.post_data_json
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_deterministic",
                    "reply": "### Deterministic Cohort Summary\n\n- **Patients:** 5",
                    "data": {"provider": "deterministic", "context": {"source": "clinical summary"}},
                }
            ),
        )

    page.route("**/analysis", handler)
    page.locator("[data-analysis-prompt='Summarize the main clinical patterns in this workspace and tell me what stands out.']").click()
    if not page.locator("#analysisPrompt").is_visible():
        page.locator("#analysisRequestDetails > summary").click()
    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this workspace.")
    page.locator("#analysisRunBtn").click()

    assert captured["body"]["llm_only"] is False
    assert captured["body"]["deterministic_only"] is True
    assert captured["body"]["dataset_id"] == "default"
    assert "data_dir" not in captured["body"]


def test_analysis_llm_starter_chip_blocks_when_lm_unavailable(page) -> None:
    expect = playwright.expect
    page.route(
        "**/lm-status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "available": False,
                    "status": "no_model",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model": "",
                    "detail": "No model loaded.",
                }
            ),
        ),
    )
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)

    analysis_called = {"value": False}

    def unexpected_analysis(route):
        analysis_called["value"] = True
        route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "unexpected"}))

    page.route("**/analysis", unexpected_analysis)
    page.locator("#analysisMethodSelect").select_option("custom")
    page.locator("#analysisComposerExamplesBtn").click()
    if page.locator("#analysisStarterPanel .query-chip-toggle").count():
        page.locator("#analysisStarterPanel .query-chip-toggle").click()
    page.locator("[data-analysis-prompt='Interpret the disease and medication profiles in this workspace and summarize the main themes.']").click()
    expect(page.locator("#analysisStatus")).to_contain_text("LLM unavailable")
    page.locator("#analysisPrompt").fill("Interpret the medication profiles in three sentences.")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisStatus")).to_contain_text("LLM unavailable")
    expect(page.locator("#analysisThread")).to_contain_text("LLM unavailable")
    assert analysis_called["value"] is False


def test_analysis_catalog_item_prefills_prompt_and_compare_mode(page) -> None:
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisCatalogBrowseBtn").click()
    expect(page.locator("#analysisCatalogDrawer")).to_be_visible()
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Ready now")
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Needs setup")
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Trajectory analysis")
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='trajectory-single']").click()

    expect(page.locator("#analysisPrompt")).to_have_value(re.compile(r"Show the trajectory of Leukocyte Count over time"))
    expect(page.locator("#analysisCompareMode")).not_to_be_checked()


def test_analysis_measurement_selection_controls_readiness(page):
    page.route("**/analysis/measurements", lambda route: route.fulfill(json={"measurements": [
        {"measure": "CRP", "units": ["mg/L"], "compatible_units": True,
         "groups": [{"patient_count": 12, "dated_patient_count": 12, "repeated_patient_count": 8}]},
        {"measure": "Single visit", "units": ["mg/L"], "compatible_units": True,
         "groups": [{"patient_count": 12, "dated_patient_count": 12, "repeated_patient_count": 0}]},
    ]}))
    _open_analysis_tab(page)
    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='trajectory-single']").click()
    selector = page.locator("#analysisMeasurement")
    playwright.expect(selector.locator("option")).to_have_count(3)
    playwright.expect(page.locator("#analysisRunBtn")).to_be_disabled()
    selector.select_option("CRP")
    playwright.expect(page.locator("#analysisRunBtn")).to_be_enabled()
    playwright.expect(page.locator("#analysisCatalogAssayPanel")).to_contain_text("8 with values on two or more dates")
    selector.select_option("Single visit")
    playwright.expect(page.locator("#analysisRunBtn")).to_be_disabled()


def test_analysis_queued_job_opens_jobs_drawer_and_loads_result(page) -> None:
    _open_analysis_tab(page)
    expect = playwright.expect

    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_job",
                    "reply": "Submitted External R clinical scope profile as a background job. Open Jobs to monitor progress and view the result when it completes.",
                    "data": {
                        "source": "job",
                        "execution": "queued",
                        "job_id": "job-123",
                        "job_status": "queued",
                        "catalog_item_id": "external-r-clinical-profile",
                        "runner_type": "rscript",
                    },
                }
            ),
        ),
    )
    page.route(
        "**/jobs",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "jobs": [
                        {
                            "job_id": "job-123",
                            "job_type": "analysis",
                            "feature": "analysis",
                            "status": "completed",
                            "submitted_at": "2026-04-18T12:00:00+00:00",
                            "name": "External R clinical scope profile",
                            "catalog_item_id": "external-r-clinical-profile",
                            "runner_type": "rscript",
                            "reply_preview": "External analysis done.",
                            "result_available": True,
                            "artifacts": [
                                {"name": "summary.json", "url": "/jobs/job-123/artifacts/summary.json"},
                                {"name": "workflow/01-deseq2/de_results.tsv", "url": "/jobs/job-123/artifacts/workflow/01-deseq2/de_results.tsv"},
                            ],
                        }
                    ]
                }
            ),
        ),
    )
    page.route(
        "**/jobs/job-123",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "job-123",
                    "job_type": "analysis",
                    "feature": "analysis",
                    "status": "completed",
                    "name": "External R clinical scope profile",
                    "analysis_session_id": "",
                    "result_available": True,
                    "artifacts": [],
                    "result_payload": {
                        "intent": "analysis_external_rscript",
                        "reply": "External analysis done.",
                        "data": {
                            "source": "deterministic",
                            "execution": "external_runner",
                            "context": {"mode": "external_rscript_profile"},
                            "runner_type": "rscript",
                            "job_id": "job-123",
                        },
                    },
                }
            ),
        ),
    )

    page.locator("#analysisPrompt").fill("Run the external R clinical scope profile for the current Analysis scope.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#jobsDrawer")).to_be_visible()
    expect(page.locator("#jobsDrawerList")).to_contain_text("External R clinical scope profile")
    expect(page.locator("#jobsDrawerList details.job-card-artifacts")).not_to_have_attribute("open", "")
    expect(page.locator("#jobsDrawerList .job-card-artifact-links")).to_be_hidden()
    page.locator("#jobsDrawerList details.job-card-artifacts summary").click()
    expect(page.locator("#jobsDrawerList .job-card-artifact-links")).to_be_visible()
    expect(page.locator("#jobsDrawerList .job-card-artifact-links")).to_contain_text("workflow/01-deseq2/de_results.tsv")
    page.locator("[data-job-open-result='job-123']").click()
    expect(page.locator("#jobsDrawer")).to_be_hidden()
    expect(page.locator("#analysisThread")).to_contain_text("External analysis done.")


def test_run_history_shows_worker_online_but_idle(page) -> None:
    expect = playwright.expect
    page.route(
        "**/jobs/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "available": True,
                    "dependencies_available": True,
                    "redis_available": True,
                    "queue_name": "analysis",
                    "worker_count": 1,
                    "busy_worker_count": 0,
                    "activity": "idle",
                }
            ),
        ),
    )
    page.route(
        "**/run-history",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"runs": [], "expired_deleted_count": 0}),
        ),
    )

    page.locator("#runHistoryDrawerBtn").click()

    expect(page.locator("#runHistoryWorkerStatus")).to_contain_text(
        "Background workers: Online · 1 worker · idle"
    )
    expect(page.locator("#runHistoryWorkerStatus")).to_have_class(re.compile(r"is-online"))
    expect(page.locator("#runHistoryWorkerStatus")).not_to_contain_text("working")


def test_analysis_open_result_recovers_missing_session(page) -> None:
    _open_analysis_tab(page)
    expect = playwright.expect

    page.route(
        "**/jobs/job-orphaned",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "job-orphaned",
                    "job_type": "analysis",
                    "feature": "analysis",
                    "status": "completed",
                    "name": "Orphaned external result",
                    "prompt": "Run the persisted analysis.",
                    "analysis_session_id": "analysis-orphaned-session",
                    "result_available": True,
                    "artifacts": [],
                    "result_payload": {
                        "intent": "analysis_external_rscript",
                        "reply": "Recovered persisted result.",
                        "data": {
                            "source": "deterministic",
                            "execution": "external_runner",
                            "context": {"mode": "external_rscript_profile"},
                            "runner_type": "rscript",
                            "job_id": "job-orphaned",
                        },
                    },
                }
            ),
        ),
    )

    page.evaluate(
        """
        () => {
          const list = document.getElementById('jobsDrawerList');
          list.innerHTML = '<div class="job-card"><button type="button" class="query-chip action" data-job-open-result="job-orphaned">Open result</button></div>';
          const drawer = document.getElementById('jobsDrawer');
          drawer.classList.remove('is-hidden');
          drawer.setAttribute('aria-hidden', 'false');
        }
        """
    )

    page.locator("[data-job-open-result='job-orphaned']").click()

    expect(page.locator("#jobsDrawer")).to_be_hidden()
    expect(page.locator("#analysisThread")).to_contain_text("Recovered persisted result.")
    expect(page.locator("#analysisSessionList")).to_contain_text("Orphaned external result")


def test_analysis_starter_panel_stays_visible_after_run(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this workspace.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisStarterPanel")).to_be_visible()
    expect(page.locator("#analysisComposerExamplesBtn")).to_contain_text("Prompts")

    page.locator("#analysisComposerExamplesBtn").click()
    expect(page.locator("#analysisStarterPanel")).to_be_visible()
    expect(page.locator("#analysisComposerExamplesBtn")).to_contain_text("Prompts")


def test_analysis_saved_cohort_disables_manual_scope_for_cohort_a(page) -> None:
    _mock_saved_cohorts(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()

    expect(page.locator("#analysisSelectedPatientIds")).to_be_disabled()
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("")
    expect(page.locator("#analysisSelectedPatientIdsSummary")).to_contain_text("using saved cohort")
    expect(page.locator("#analysisSelectedSavedCohortSelection")).to_contain_text("Cohort A source")


def test_analysis_compare_mode_requires_saved_cohorts(page) -> None:
    _mock_saved_cohorts(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()

    expect(page.locator("#analysisSelectedPatientIds")).to_be_disabled()
    expect(page.locator("#analysisCompareSelectedPatientIds")).to_be_hidden()
    expect(page.locator("#analysisSelectedPatientIdsSummary")).to_contain_text("Cohort A: select a saved cohort")
    expect(page.locator("#analysisCompareSelectedPatientIdsSummary")).to_contain_text("Cohort B: select a saved cohort")

    page.locator("#analysisPrompt").fill("Compare Cohort A and Cohort B by disease burden")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisStatus")).to_contain_text("requires saved Cohort A and Cohort B")


def test_analysis_differential_expression_enables_after_saved_cohorts_selected(page) -> None:
    _mock_saved_cohorts(page)
    _mock_assay_datasets(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    flow_labels = page.locator("#analysisFlowBar .analysis-flow-step-copy > span")
    assert flow_labels.all_text_contents() == ["Analysis", "Setup", "Prompt", "Results"]
    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='transcriptomics-deseq2-differential-expression']").click()

    checklist = page.locator("#analysisSetupChecklist")
    expect(checklist.locator("[data-analysis-setup-step='workspace']")).to_contain_text("Done")
    expect(checklist.locator("[data-analysis-setup-step='cohort-a']")).to_have_class(re.compile("is-current"))
    expect(checklist.locator("[data-analysis-setup-step='cohort-a']")).to_contain_text("Next")
    expect(checklist.locator("[data-analysis-setup-step='cohort-b']")).to_contain_text("Waiting")
    expect(checklist.locator("[data-analysis-setup-step='assay']")).to_contain_text("Waiting")
    expect(page.locator("#analysisRunBtn")).to_be_disabled()

    checklist.locator("[data-analysis-setup-action='choose-cohort-a']").click()
    expect(page.locator("#analysisWorkspaceSetup")).to_have_attribute("open", "")
    expect(page.locator("#analysisTab .analysis-setup-saved-cohorts")).to_have_attribute("open", "")
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()
    expect(checklist.locator("[data-analysis-setup-step='cohort-a']")).to_contain_text("Done")
    expect(checklist.locator("[data-analysis-setup-step='cohort-b']")).to_have_class(re.compile("is-current"))
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis-b']").nth(1).click()

    expect(checklist.locator("[data-analysis-setup-step='cohort-b']")).to_contain_text("Done")
    expect(checklist.locator("[data-analysis-setup-step='assay']")).to_contain_text("Done")
    expect(checklist.locator("[data-analysis-setup-step='worker']")).to_contain_text("online")
    expect(checklist.locator("[data-analysis-setup-step='prompt']")).to_contain_text("Done")
    expect(page.locator("#analysisRunBtn")).to_be_enabled()
    expect(page.locator("#analysisFlowBar [data-analysis-flow-target='requirements']")).to_contain_text("ready")


def test_analysis_workflow_filter_shows_assay_dataset_selector(page) -> None:
    _mock_saved_cohorts(page)
    _mock_assay_datasets_with_nonmatching_dataset(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis-b']").nth(1).click()

    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerFilters [data-analysis-catalog-filter='workflow']").click()
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Transcriptomics signature workflow")
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='transcriptomics-signature-workflow']").click()

    expect(page.locator("#analysisCatalogAssayPanel")).to_be_visible()
    expect(page.locator("#analysisCatalogAssayDatasetList")).to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#analysisCatalogAssayDatasetList")).not_to_contain_text("unrelated_transcriptome_raw_counts")
    expect(page.locator("#analysisCatalogAssayDatasetList input[type='checkbox']")).to_be_checked()
    expect(page.locator("#analysisCatalogAssayStatus")).to_contain_text("Selected assay: synthetic_transcriptome_raw_counts_infliximab")


def test_analysis_workflow_assay_selector_keeps_one_dataset_selected(page) -> None:
    _mock_saved_cohorts(page)
    _mock_assay_datasets_with_two_matching_datasets(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis-b']").nth(1).click()

    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerFilters [data-analysis-catalog-filter='workflow']").click()
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='transcriptomics-signature-workflow']").click()

    first_dataset = page.locator("#analysisCatalogAssayDatasetList input[value='synthetic_transcriptome_raw_counts_infliximab']")
    second_dataset = page.locator("#analysisCatalogAssayDatasetList input[value='synthetic_transcriptome_raw_counts_ustekinumab']")
    first_dataset.check()
    expect(first_dataset).to_be_checked()
    second_dataset.check()
    expect(second_dataset).to_be_checked()
    expect(first_dataset).not_to_be_checked()
    expect(page.locator("#analysisCatalogAssayStatus")).to_contain_text("Selected assay: synthetic_transcriptome_raw_counts_ustekinumab")


@pytest.mark.parametrize("adjusted", [False, True])
def test_analysis_renders_completed_limma_voom_result(page, adjusted) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_external_rscript",
                    "reply": "limma-voom differential expression completed.",
                    "data": {
                        "source": "deterministic",
                        "execution": "external_runner",
                        "runner_ref": "transcriptomics_limma_voom_differential_expression",
                        "context": {
                            "mode": "external_rscript_transcriptomics_limma_voom_differential_expression",
                            "dataset_name": "synthetic_rsem_expected_counts",
                            "cohort_a_sample_count": 12,
                            "cohort_b_sample_count": 14,
                            "tested_gene_count": 1200,
                            "filtered_gene_count": 420,
                            **({"input_gene_count": 1200, "tested_gene_count": 420,
                                "covariates_used": ["batch", "age"], "adjustment_status": "covariate_adjusted"}
                               if adjusted else {}),
                            "significant_gene_count": 37,
                            "top_gene": "ENSG000001",
                            "top_log2_fold_change": 1.234,
                            "top_adj_p_value": 0.000012,
                            "method": "limma-voom",
                        },
                        "artifacts": [
                            {"name": "volcano_plot.png", "url": "/jobs/limma/artifacts/volcano_plot.png"},
                            {"name": "de_results.tsv", "url": "/jobs/limma/artifacts/de_results.tsv"},
                            {"name": "volcano_points.tsv", "url": "/jobs/limma/artifacts/volcano_points.tsv"},
                            {"name": "summary.json", "url": "/jobs/limma/artifacts/summary.json"},
                            *([{"name": "model.json", "url": "/jobs/limma/artifacts/model.json"},
                               {"name": "design_matrix.tsv", "url": "/jobs/limma/artifacts/design_matrix.tsv"}]
                              if adjusted else []),
                        ],
                    },
                }
            ),
        ),
    )
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Run the completed limma-voom comparison.")
    page.locator("#analysisRunBtn").click()

    summary = page.locator("[data-analysis-summary='differential-expression']")
    expect(summary).to_contain_text("Cohort A samples")
    expect(summary).to_contain_text("12")
    expect(summary).to_contain_text("1,200")
    expect(summary).to_contain_text("420")
    expect(summary).to_contain_text("37")
    result = page.locator("[data-analysis-result='differential-expression']")
    expect(result).to_contain_text("RSEM expected counts")
    expect(result).to_contain_text("filterByExpr")
    expect(result).to_contain_text("TMM-normalized")
    if adjusted:
        expect(result).to_contain_text("model adjusts for batch, age")
        expect(result).not_to_contain_text("cohort-only and unadjusted")
        result.locator("summary").filter(has_text="Result files").click()
        expect(result.locator("a[href='/jobs/limma/artifacts/model.json']")).to_be_visible()
        expect(result.locator("a[href='/jobs/limma/artifacts/design_matrix.tsv']")).to_be_visible()
    else:
        expect(result).to_contain_text("cohort-only and unadjusted")
    expect(result).to_contain_text("Top-ranked gene: ENSG000001")
    expect(result).to_contain_text("higher expression in Cohort A")
    expect(result.locator("img[alt='Differential expression volcano plot']")).to_have_attribute(
        "src", "/jobs/limma/artifacts/volcano_plot.png"
    )
    result.locator("details.analysis-artifact-downloads > summary").click()
    expect(result).to_contain_text("de_results.tsv")
    expect(result).to_contain_text("volcano_points.tsv")
    expect(page.locator('#analysisThread .is-latest-result > .analysis-turn-label')).to_have_text('Analysis result')
    expect(result.locator('.analysis-file-count')).to_contain_text('files')
    file_link = result.locator('a.analysis-result-file').filter(has_text='de_results.tsv')
    expect(file_link).to_have_attribute('href', '/jobs/limma/artifacts/de_results.tsv')
    expect(file_link.locator('.analysis-file-format')).to_have_text('TSV')
    expect(file_link).to_have_attribute('target', '_blank')

    page.route('**/jobs/limma/artifacts/volcano_points.tsv', lambda route: route.fulfill(
        content_type='text/tab-separated-values', body='"gene_id"\t"log2_fold_change"\t"p_value"\t"adj_p_value"\t"neg_log10_p"\n"ENSG000001"\t2\t0.001\t0.01\t3\n'))
    page.evaluate('''() => {
        const original = window.Plotly.newPlot;
        window.Plotly.newPlot = (el, traces, ...args) => {
            el.dataset.testPoints = JSON.stringify(traces[0].x);
            return original(el, traces, ...args);
        };
    }''')
    result.locator('[data-de-view-btn="interactive"]').click()
    expect(result.locator('[id$="-de-volcano"]')).to_have_attribute('data-test-points', '[2]')
    latest = page.locator('#analysisThread .is-latest-result')
    followups = latest.locator('.analysis-result-followups')
    expect(followups).to_be_visible()
    assert followups.bounding_box()['y'] > result.bounding_box()['y'] + result.bounding_box()['height']
    setup = page.locator('#analysisSetupDisclosure')
    expect(setup).not_to_have_attribute('open', '')
    technical = latest.locator('.analysis-response-details')
    expect(technical).not_to_have_attribute('open', '')
    expect(technical.locator('.analysis-turn-meta')).to_be_hidden()
    technical.locator(':scope > summary').click()
    expect(technical.locator('.analysis-turn-meta')).to_be_visible()
    # Earlier answers remain readable after another turn, as in a conversation.
    page.locator('[data-analysis-flow-target="prompt"]').click()
    expect(setup).to_have_attribute('open', '')
    page.locator('#analysisRunBtn').click()
    expect(page.locator('#analysisThread .analysis-turn-assistant')).to_have_count(2)
    expect(page.locator('#analysisThread .is-previous-result .analysis-turn-body')).to_be_visible()


def test_analysis_renders_quantitative_assay_wilcoxon_result(page) -> None:
    results = [
        {
            "feature_id": f"Marker_{index:02d}",
            "status": "tested",
            "cohort_a_n": 12,
            "cohort_b_n": 14,
            "cohort_a_missing": 0,
            "cohort_b_missing": 1,
            "cohort_a_mean": 2.1 + index,
            "cohort_a_median": 2.0 + index,
            "cohort_a_q1": 1.5 + index,
            "cohort_a_q3": 2.5 + index,
            "cohort_b_mean": 1.7 + index,
            "cohort_b_median": 1.6 + index,
            "cohort_b_q1": 1.2 + index,
            "cohort_b_q3": 2.1 + index,
            "mean_difference": 0.4,
            "median_difference": 0.4,
            "rank_biserial_effect": 0.72 - index * 0.04,
            "p_value": 0.0001 + index * 0.001,
            "adj_p_value": 0.001 + index * 0.01,
        }
        for index in reversed(range(13))
    ]
    results.append(
        {
            "feature_id": "Marker_skipped",
            "status": "insufficient_complete_cases",
            "cohort_a_n": 2,
            "cohort_b_n": 14,
            "cohort_a_missing": 10,
            "cohort_b_missing": 0,
            "cohort_a_median": 1.0,
            "cohort_b_median": 2.0,
            "median_difference": -1.0,
            "rank_biserial_effect": None,
            "p_value": None,
            "adj_p_value": None,
        }
    )
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_external_rscript",
                    "reply": "Exploratory quantitative-serology cohort comparison completed.",
                    "data": {
                        "source": "deterministic",
                        "execution": "external_runner",
                        "runner_ref": "quantitative_assay_wilcoxon_comparison",
                        "context": {
                            "mode": "external_rscript_quantitative_assay_wilcoxon_comparison",
                            "runner": "quantitative_assay_wilcoxon_comparison",
                            "dataset_name": "synthetic_quantitative_serology",
                            "assay_label": "Quantitative serology",
                            "modality": "serology",
                            "data_type": "quantitative_measurement",
                            "adjustment_status": "unadjusted_exploratory",
                            "cohort_a_sample_count": 12,
                            "cohort_a_patient_count": 12,
                            "cohort_b_sample_count": 14,
                            "cohort_b_patient_count": 14,
                            "feature_count": 14,
                            "tested_feature_count": 13,
                            "skipped_feature_count": 1,
                            "significant_feature_count": 5,
                            "top_feature": "Marker_00",
                            "top_rank_biserial_effect": 0.72,
                            "top_adj_p_value": 0.001,
                            "source_matrix_materialized_in_duckdb": False,
                            "source_matrix_copied_to_job": False,
                            "supplied_scale": True,
                            "method": "wilcoxon_rank_sum",
                            "results": results,
                        },
                        "artifacts": [
                            {"name": "compact_assay_results.tsv", "url": "/jobs/serology/artifacts/compact_assay_results.tsv"},
                            {"name": "summary.json", "url": "/jobs/serology/artifacts/summary.json"},
                            {"name": "sample_table.tsv", "url": "/jobs/serology/artifacts/sample_table.tsv"},
                        ],
                    },
                }
            ),
        ),
    )
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Run the quantitative assay cohort comparison.")
    page.locator("#analysisRunBtn").click()

    summary = page.locator("[data-analysis-summary='quantitative-assay-wilcoxon']")
    expect(summary).to_contain_text("Cohort A samples")
    expect(summary).to_contain_text("12")
    expect(summary).to_contain_text("Features tested")
    expect(summary).to_contain_text("13")
    expect(summary).to_contain_text("Features skipped")
    expect(summary).to_contain_text("1")
    expect(summary).to_contain_text("BH < 0.05")
    expect(summary).to_contain_text("5")

    result = page.locator("[data-analysis-result='quantitative-assay-wilcoxon']")
    expect(result).to_contain_text("Exploratory and unadjusted")
    expect(result).to_contain_text("supplied measurement scale")
    expect(result).to_contain_text("No covariate adjustment")
    expect(result).to_contain_text("Top-ranked feature: Marker_00")
    expect(result).to_contain_text("remained external to DuckDB")
    expect(result.locator(".query-result-table thead")).to_contain_text("Missing A")
    expect(result.locator(".query-result-table thead")).to_contain_text("Missing B")
    expect(result.locator(".query-result-table tbody tr")).to_have_count(12)
    expect(result.locator(".query-result-table tbody tr").first).to_contain_text("Marker_00")
    expect(result.locator(".query-result-table tbody")).not_to_contain_text("Marker_skipped")
    expect(result.locator("[id$='-quantitative-assay-wilcoxon']")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator(".analysis-result-followups")).to_contain_text("rank-biserial effects")

    result.locator("details.analysis-artifact-downloads > summary").click()
    expect(result).to_contain_text("compact_assay_results.tsv")
    expect(result).not_to_contain_text("sample_table.tsv")


def test_analysis_setup_rechecks_background_worker(page) -> None:
    _mock_methylation_catalog_and_assay(page)
    worker_state = {"online": False}

    def worker_status(route):
        online = worker_state["online"]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "available": online,
                    "dependencies_available": True,
                    "redis_available": online,
                    "queue_name": "analysis",
                    "worker_count": 1 if online else 0,
                    "busy_worker_count": 0,
                    "activity": "idle" if online else "offline",
                }
            ),
        )

    page.route("**/jobs/status", worker_status)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='methylation-qc-pca']").click()
    worker_step = page.locator("#analysisSetupChecklist [data-analysis-setup-step='worker']")
    expect(worker_step).to_have_class(re.compile("is-current"))
    expect(worker_step).to_contain_text("No background worker is online")
    expect(page.locator("#analysisRunBtn")).to_be_disabled()

    worker_state["online"] = True
    worker_step.locator("[data-analysis-setup-action='check-worker']").click()
    expect(worker_step).to_contain_text("worker is online")
    expect(page.locator("#analysisRunBtn")).to_be_enabled()


def test_analysis_methylation_catalog_keeps_selected_assay_in_run_request(page) -> None:
    _mock_methylation_catalog_and_assay(page)
    captured = {}

    def analysis_handler(route):
        captured["body"] = route.request.post_data_json
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_external_rscript",
                    "reply": "Processed methylation matrix QC complete.",
                    "data": {
                        "execution": "external_runner",
                        "runner_type": "rscript",
                        "runner_ref": "methylation_qc_pca",
                        "context": {
                            "mode": "external_rscript_methylation_qc_pca",
                            "dataset_name": "synthetic_methylation_m_values",
                            "sample_count": 6,
                            "patient_count": 6,
                            "observed_feature_count": 8000,
                            "variable_feature_count": 7200,
                            "pca_feature_count": 1000,
                            "pca_component_count": 5,
                            "pc1_variance_fraction": 0.214,
                            "pc2_variance_fraction": 0.103,
                            "missing_fraction": 0.0012,
                            "covariates_used": ["age", "plate"],
                            "strongest_covariate": "plate",
                            "strongest_covariate_component": "PC1",
                            "strongest_covariate_p_value": 0.00042,
                            "strongest_covariate_adj_p_value": 0.00168,
                            "association_scope": "exploratory_one_covariate_at_a_time_bh_adjusted",
                            "feature_view": "feature_panel",
                            "feature_panel": {
                                "panel_id": "independent_sle_ewas",
                                "panel_version": "1",
                                "label": "Independent replicated SLE EWAS panel",
                                "requested_feature_count": 7245,
                                "matched_feature_count": 5584,
                                "missing_feature_count": 1660,
                                "excluded_nonfinite_feature_count": 1,
                                "source_publication_doi": "10.1136/annrheumdis-2017-212379",
                                "independent_of_target_cohort": True,
                            },
                            "source_matrix_materialized_in_duckdb": False,
                            "source_matrix_copied_to_job": False,
                        },
                        "artifacts": [
                            {"name": "pca_plot.png", "url": "/jobs/methylation-qc/artifacts/pca_plot.png"},
                            {"name": "sample_qc.tsv", "url": "/jobs/methylation-qc/artifacts/sample_qc.tsv"},
                            {"name": "pca_scores.tsv", "url": "/jobs/methylation-qc/artifacts/pca_scores.tsv"},
                            {"name": "pca_variance.tsv", "url": "/jobs/methylation-qc/artifacts/pca_variance.tsv"},
                            {"name": "pca_covariate_associations.tsv", "url": "/jobs/methylation-qc/artifacts/pca_covariate_associations.tsv"},
                            {"name": "summary.json", "url": "/jobs/methylation-qc/artifacts/summary.json"},
                        ],
                    },
                }
            ),
        )

    page.route("**/analysis", analysis_handler)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisCatalogBrowseBtn").click()
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Methylation QC and PCA")
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Requires DNA methylation")
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Requires M-values")
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='methylation-qc-pca']").click()

    methylation_assay = page.locator("#analysisCatalogAssayDatasetList input[value='synthetic_methylation_m_values']")
    expect(methylation_assay).to_be_checked()
    expect(page.locator("#analysisCatalogAssayStatus")).to_contain_text("Ready to run with synthetic_methylation_m_values")
    expect(page.locator("#analysisCompareMode")).not_to_be_checked()
    expect(page.locator("#analysisRunBtn")).to_be_enabled()

    page.locator("#analysisPrompt").fill("Run methylation QC and retain this reviewer note.")
    page.locator("#analysisRunBtn").click()

    assert captured["body"]["catalog_item_id"] == "methylation-qc-pca"
    assert captured["body"]["prompt"] == "Run methylation QC and retain this reviewer note."
    assert captured["body"]["assay_id"] == "synthetic_methylation_m_values"
    assert captured["body"]["compare_mode"] is False
    summary = page.locator("[data-methylation-summary='qc']")
    expect(summary).to_contain_text("CpGs scanned")
    expect(summary).to_contain_text("8,000")
    expect(summary).to_contain_text("PC1 variance")
    expect(summary).to_contain_text("21.4%")
    panel_summary = page.locator("[data-methylation-panel-summary='true']")
    expect(panel_summary).to_contain_text("Panel requested")
    expect(panel_summary).to_contain_text("7,245")
    expect(panel_summary).to_contain_text("Absent from source")
    expect(panel_summary).to_contain_text("1,660")
    expect(panel_summary).to_contain_text("Non-finite excluded")
    expect(panel_summary).to_contain_text("Panel retained")
    expect(panel_summary).to_contain_text("5,584")
    expect(panel_summary).to_contain_text("Feature selection was independent")
    result = page.locator("[data-methylation-result='qc-pca']")
    expect(result).to_contain_text("Covariates assessed against the leading components: age, plate")
    expect(result).to_contain_text("Strongest exploratory association: plate with PC1")
    expect(result).to_contain_text("BH-adjusted p = 0.00168")
    expect(result).to_contain_text("remained external to DuckDB")
    expect(result.locator("img[alt='Methylation PCA plot']")).to_have_attribute(
        "src", "/jobs/methylation-qc/artifacts/pca_plot.png"
    )
    result.locator("details.analysis-artifact-downloads > summary").click()
    expect(result).to_contain_text("sample_qc.tsv")
    expect(result).to_contain_text("pca_covariate_associations.tsv")


def test_analysis_renders_completed_differential_methylation_result(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_external_rscript",
                    "reply": "Differential methylation completed.",
                    "data": {
                        "source": "deterministic",
                        "execution": "external_runner",
                        "runner_type": "rscript",
                        "runner_ref": "methylation_limma_differential_methylation",
                        "context": {
                            "mode": "external_rscript_methylation_limma_differential_methylation",
                            "dataset_name": "synthetic_methylation_m_values",
                            "cohort_a_sample_count": 12,
                            "cohort_b_sample_count": 14,
                            "patient_count": 26,
                            "observed_feature_count": 8000,
                            "analyzed_feature_count": 7200,
                            "significant_cpg_count": 125,
                            "hypermethylated_cpg_count": 73,
                            "hypomethylated_cpg_count": 52,
                            "top_cpg": "cg00000001",
                            "top_m_value_difference": 0.8124,
                            "top_adj_p_value": 2.4e-12,
                            "covariates_used": ["age", "sex", "plate"],
                            "design_rank": 6,
                            "residual_degrees_of_freedom": 20,
                            "contrast": "Cohort A - Cohort B",
                            "source_matrix_materialized_in_duckdb": False,
                            "source_matrix_copied_to_job": False,
                        },
                        "artifacts": [
                            {"name": "volcano_plot.png", "url": "/jobs/methylation-dm/artifacts/volcano_plot.png"},
                            {"name": "dm_results.tsv", "url": "/jobs/methylation-dm/artifacts/dm_results.tsv"},
                            {"name": "volcano_points.tsv", "url": "/jobs/methylation-dm/artifacts/volcano_points.tsv"},
                            {"name": "summary.json", "url": "/jobs/methylation-dm/artifacts/summary.json"},
                            {"name": "manifest.yaml", "url": "/jobs/methylation-dm/artifacts/manifest.yaml"},
                            {"name": "params.yaml", "url": "/jobs/methylation-dm/artifacts/params.yaml"},
                        ],
                    },
                }
            ),
        ),
    )
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Run differential methylation for the current comparison.")
    page.locator("#analysisRunBtn").click()

    summary = page.locator("[data-methylation-summary='differential']")
    expect(summary).to_contain_text("CpGs analyzed")
    expect(summary).to_contain_text("7,200")
    expect(summary).to_contain_text("BH < 0.05")
    expect(summary).to_contain_text("125")
    result = page.locator("[data-methylation-result='differential']")
    expect(result).to_contain_text("Adjusted for: age, sex, plate")
    expect(result).to_contain_text("Top CpG: cg00000001")
    expect(result).to_contain_text("Positive M-value differences indicate higher methylation in Cohort A")
    expect(result.locator("img[alt='Differential methylation volcano plot']")).to_have_attribute(
        "src", "/jobs/methylation-dm/artifacts/volcano_plot.png"
    )
    result.locator("details.analysis-artifact-downloads > summary").click()
    expect(result).to_contain_text("dm_results.tsv")
    expect(result).to_contain_text("volcano_points.tsv")
    expect(result).to_contain_text("manifest.yaml")


def test_analysis_deterministic_trajectory_mounts_plotly_cards(page) -> None:
    _mock_available_lm(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    _mock_analysis_trajectory_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Show response to Infliximab using CRP.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisComposerStatus")).to_contain_text("Analysis complete")
    expect(page.locator("#analysisThread")).to_contain_text("CRP declines after Infliximab")
    expect(page.locator("#analysisThread")).to_contain_text("Trajectory analysis")
    expect(page.locator("[id$='-trajectory']")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("[id$='-trajectory-coverage']")).to_have_attribute("data-plotly-ready", "true")
    followup = page.locator("#analysisThread [data-analysis-followup-mode='llm_only']").first
    expect(followup).to_have_class(re.compile(r".*query-chip-llm.*"))
    expect(followup).to_contain_text("LLM interpretation")
    followup.click()
    expect(page.locator("#analysisPrompt")).to_have_value("Can you explain this response to Infliximab plot?")
    expect(page.locator("#analysisStatus")).to_contain_text("LLM interpretation follow-up prepared")
    # Personalizing an explicitly LLM-based follow-up must not switch to Auto.
    page.locator("#analysisPrompt").fill("Explain this plot in three short sentences, including limitations.")
    with page.expect_request(lambda request: request.url.endswith("/analysis") and request.method == "POST") as submitted:
        page.locator("#analysisRunBtn").click()
    assert submitted.value.post_data_json["llm_only"] is True
    assert submitted.value.post_data_json["deterministic_only"] is False


def test_analysis_transcriptomics_medication_compare_mounts_volcano_plot(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_assay_volcano_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Explain differences in gene expression according to medication")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("within the current Analysis scope")
    expect(page.locator("#analysisThread")).to_contain_text("Transcriptomics by medication")
    expect(page.locator("#analysisThread")).to_contain_text("Exploratory transcriptomics comparison")
    expect(page.locator("#analysisThread")).to_contain_text("Positive log2FC means higher in Infliximab")
    expect(page.locator("#analysisThread")).to_contain_text("gray = everything else")
    expect(page.locator("[id*='assay-volcano-']")).to_have_attribute("data-plotly-ready", "true")


def test_pheno_manual_metric_override_skips_planner_and_shows_notice(page) -> None:
    _open_pheno_tab(page)
    expect = playwright.expect
    plan_calls = {"count": 0}
    request_capture = {}

    def unexpected_plan(route):
        plan_calls["count"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"source": "deterministic", "reasoning": [], "plan": {}}),
        )

    page.route("**/pheno-ranker/plan", unexpected_plan)
    _mock_cohort_run(page, metric="jaccard", request_capture=request_capture)

    page.locator("#phenoPrompt").fill("Compare all patients by phenotypicFeatures and diseases")
    page.locator("#phenoTab summary").filter(has_text="Setup").click()
    page.locator("#phenoTab summary").filter(has_text="Advanced options").click()
    page.locator("#phenoSimilarityMetric").select_option("jaccard")

    expect(page.locator("#phenoPlanStatus")).to_contain_text("Settings changed after preview")
    expect(page.locator("#phenoPlan")).to_contain_text('"similarity_metric_cohort": "jaccard"')
    expect(page.locator("#phenoPrompt")).to_have_value(re.compile("Use jaccard cohort similarity"))
    page.locator("#phenoPlanBtn").click()
    expect(page.locator("#phenoPlanStatus")).to_contain_text("Previewing current form settings")
    expect(page.locator("#phenoSimilarityMetric")).to_have_value("jaccard")
    expect(page.locator("#phenoPlan")).to_contain_text('"similarity_metric_cohort": "jaccard"')
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed cohort run")
    assert plan_calls["count"] == 0
    assert request_capture["body"]["similarity_metric_cohort"] == "jaccard"
    assert "Use jaccard cohort similarity" in request_capture["body"]["prompt"]


def test_pheno_mds_cohort_chips_render_for_prefixed_ids(page) -> None:
    _open_pheno_tab(page)
    _mock_pheno_plan(page, expected_mode="cohort", selected_ids="SYN001,SYN002,SYN003")
    _mock_cohort_run(page, prefixed_ids=True)
    expect = playwright.expect

    page.locator("#phenoPrompt").fill("Cluster these three records by disease")
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoMdsPlot")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#phenoMdsCohortLegend")).to_contain_text("C1")
    expect(page.locator("#phenoMdsCohortLegend")).to_contain_text("C2")


def test_local_auth_gates_dataset_loading_to_admin(page_auth) -> None:
    _mock_dashboard_load(page_auth)
    _mock_assay_datasets(page_auth)
    expect = playwright.expect

    expect(page_auth.locator("#authGate")).to_be_visible()
    expect(page_auth.locator("#appShell")).to_be_hidden()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Signed out")
    expect(page_auth.locator("#datasetsTabBtn")).to_be_hidden()
    expect(page_auth.locator("#adminTabBtn")).to_be_hidden()
    expect(page_auth.locator("#dataTabBtn")).to_be_hidden()
    expect(page_auth.locator("#usersTabBtn")).to_be_hidden()

    page_auth.locator("#authUsername").fill("admin")
    page_auth.locator("#authPassword").fill("secret")
    page_auth.locator("#authLoginBtn").click()

    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User")
    expect(page_auth.locator("#authGate")).to_be_hidden()
    expect(page_auth.locator("#appShell")).to_be_visible()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User")
    expect(page_auth.locator("#datasetsTabBtn")).to_be_visible()
    expect(page_auth.locator("#adminTabBtn")).to_be_visible()
    expect(page_auth.locator("#dataTabBtn")).to_be_hidden()
    expect(page_auth.locator("#usersTabBtn")).to_be_hidden()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User (admin)")
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page_auth.wait_for_load_state("networkidle")

    if not page_auth.locator("#adminTabBtn").is_visible(): page_auth.locator("#accountMenuButton").click()
    page_auth.locator("#adminTabBtn").click()
    expect(page_auth.locator("#adminTabBtn")).to_have_class(re.compile(r"\bactive\b"))
    expect(page_auth.locator("#dataTabBtn")).to_be_visible()
    expect(page_auth.locator("#usersTabBtn")).to_be_visible()
    expect(page_auth.locator("#modelsTabBtn")).to_be_visible()
    nav_order = page_auth.locator("#phenoTabBtn, #adminTabBtn").evaluate_all("elements => elements.map(element => element.id)")
    assert nav_order == ["phenoTabBtn", "adminTabBtn"]
    expect(page_auth.locator("#dataTabBtn")).to_have_class(re.compile(r"\bactive\b"))
    admin_card = page_auth.locator("#datasetAdminList [data-dataset-admin-card]").first
    expect(admin_card).to_be_visible()
    expect(admin_card).not_to_have_attribute("open", "")
    expect(admin_card.locator(".dataset-admin-body")).to_be_hidden()
    admin_card.locator("summary").click()
    expect(admin_card.locator(".dataset-admin-body")).to_be_visible()
    provider_context = admin_card.locator("[data-dataset-ai-provider-access]")
    expect(provider_context).to_have_value("detailed_allowed")
    expect(provider_context.locator('option[value="detailed_allowed"]')).to_be_enabled()
    expect(provider_context.locator('option[value="detailed_allowed"]')).to_have_text("Detailed allowed")

    page_auth.locator("#usersTabBtn").click()
    user_card = page_auth.locator("#usersList [data-auth-user-card]").first
    expect(user_card).to_be_visible()
    expect(user_card).not_to_have_attribute("open", "")
    expect(user_card.locator(".dataset-admin-body")).to_be_hidden()
    user_card.locator("summary").click()
    expect(user_card.locator(".dataset-admin-body")).to_be_visible()

    page_auth.locator("#modelsTabBtn").click()
    expect(page_auth.locator("#modelsTab")).to_have_class(re.compile(r"\bactive\b"))
    expect(page_auth.locator("#adminTabBtn")).to_have_class(re.compile(r"\bactive\b"))

    page_auth.locator("#datasetsTabBtn").click()
    expect(page_auth.locator("#loadBtn")).to_be_visible()
    expect(page_auth.locator("#loadBtn")).to_be_enabled()
    page_auth.locator("#loadBtn").click()
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")

    page_auth.locator("#heroLogoutBtn").click()
    expect(page_auth.locator("#authGate")).to_be_visible()
    expect(page_auth.locator("#appShell")).to_be_hidden()


def test_admin_can_manage_model_providers_in_app(page_auth) -> None:
    expect = playwright.expect
    page_auth.locator("#authUsername").fill("admin")
    page_auth.locator("#authPassword").fill("secret")
    page_auth.locator("#authLoginBtn").click()
    expect(page_auth.locator("#appShell")).to_be_visible()
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded")
    page_auth.wait_for_load_state("networkidle")

    if not page_auth.locator("#adminTabBtn").is_visible(): page_auth.locator("#accountMenuButton").click()
    page_auth.locator("#adminTabBtn").click()
    page_auth.locator("#modelsTabBtn").click()
    expect(page_auth.locator("#modelsCreateCard")).to_be_visible()
    expect(page_auth.locator("[data-lm-provider-card='system-default']")).to_be_visible()

    page_auth.locator("#modelCreateId").fill("ui-local")
    page_auth.locator("#modelCreateLabel").fill("UI local model")
    page_auth.locator("#modelCreateBaseUrl").fill("http://127.0.0.1:1/v1")
    page_auth.locator("#modelCreateModel").fill("test-model")
    page_auth.locator("#modelCreateBoundary").select_option("local")
    page_auth.locator("#modelCreateApiKey").fill("ui-route-secret")
    page_auth.locator("#modelCreateBtn").click()

    managed_card = page_auth.locator("[data-lm-provider-card='ui-local']")
    expect(managed_card).to_be_visible()
    expect(managed_card).to_contain_text("In-app")
    expect(managed_card).to_contain_text("local boundary")
    expect(managed_card).to_contain_text("API key stored")
    expect(page_auth.locator("body")).not_to_contain_text("ui-route-secret")

    managed_body = managed_card.locator(".dataset-admin-body")
    if not managed_body.is_visible():
        managed_card.locator("summary").click()
    expect(managed_body).to_be_visible()
    managed_card.locator('[data-lm-provider-field="label"]').fill("Updated UI model")
    managed_card.locator('[data-lm-provider-action="save"]').click()
    updated_card = page_auth.locator("[data-lm-provider-card='ui-local']")
    expect(updated_card).to_contain_text("Updated UI model")

    page_auth.on("dialog", lambda dialog: dialog.accept())
    if not page_auth.locator("#modelsTab").is_visible():
        if not page_auth.locator("#adminTabBtn").is_visible(): page_auth.locator("#accountMenuButton").click()
        page_auth.locator("#adminTabBtn").click()
        page_auth.locator("#modelsTabBtn").click()
    expect(page_auth.locator("#modelsTab")).to_be_visible()
    expect(updated_card).to_be_visible()
    updated_body = updated_card.locator(".dataset-admin-body")
    if not updated_body.is_visible():
        updated_card.locator("summary").click()
    expect(updated_body).to_be_visible()
    updated_card.locator("[data-lm-provider-action='delete']").click()
    expect(page_auth.locator("[data-lm-provider-card='ui-local']")).to_have_count(0)
