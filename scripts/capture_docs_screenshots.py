from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "docs-site" / "static" / "img" / "screenshots"


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
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for server at {url}") from last_error


def _spawn_server() -> tuple[subprocess.Popen, str]:
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["PN_AUTH_MODE"] = "local"
    env["PN_LOCAL_USERS_JSON"] = json.dumps(
        [
            {
                "username": "admin",
                "password": "secret",
                "role": "admin",
                "display_name": "Admin User",
                "groups": ["admin"],
            },
            {
                "username": "mrueda",
                "password": "mrueda",
                "role": "user",
                "display_name": "mrueda",
                "groups": ["cnag"],
            },
        ]
    )
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
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process, f"http://127.0.0.1:{port}"


def _install_plotly_stub(context) -> None:
    body = r"""
window.Plotly = {
  newPlot: async function(el) {
    el.dataset.plotlyReady = "true";
    el.innerHTML = `
      <svg viewBox="0 0 640 360" width="100%" height="100%" role="img" aria-label="Plot placeholder">
        <rect x="0" y="0" width="640" height="360" rx="18" fill="#f8fbff"></rect>
        <line x1="72" y1="36" x2="72" y2="300" stroke="#94a3b8" stroke-width="2"></line>
        <line x1="72" y1="300" x2="596" y2="300" stroke="#94a3b8" stroke-width="2"></line>
        <polyline points="86,252 164,228 246,198 330,182 420,142 510,118 584,96" fill="none" stroke="#2563eb" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"></polyline>
        <circle cx="164" cy="228" r="5" fill="#0ea5e9"></circle>
        <circle cx="330" cy="182" r="5" fill="#0ea5e9"></circle>
        <circle cx="510" cy="118" r="5" fill="#0ea5e9"></circle>
        <text x="88" y="334" font-size="15" fill="#61758c">Illustrative plot preview</text>
      </svg>
    `;
    el.on = function(name, cb) {
      this._plotlyHandlers = this._plotlyHandlers || {};
      this._plotlyHandlers[name] = cb;
    };
    return el;
  }
};
"""
    context.route(
        "https://cdn.plot.ly/**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body=body,
        ),
    )


def _login(page) -> None:
    page.locator("#authUsername").fill("admin")
    page.locator("#authPassword").fill("secret")
    page.locator("#authLoginBtn").click()
    page.locator("#datasetsTabBtn").wait_for()


def _apply_default_workspace(page) -> None:
    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").wait_for()
    page.locator("#loadBtn").click()
    page.locator("#loadStatus").wait_for()
    page.wait_for_timeout(1200)


def _capture_login(page) -> None:
    page.locator("#authGate").wait_for()
    page.screenshot(
        path=str(SCREENSHOT_DIR / "login-page.png"),
        clip={"x": 0, "y": 0, "width": 1600, "height": 760},
    )


def _capture_datasets(page) -> None:
    page.locator("#datasetsTabBtn").click()
    page.locator("[data-dataset-card='private-dataset']").click()
    page.wait_for_timeout(250)
    page.locator("#datasetsTab .dashboard-loader").screenshot(path=str(SCREENSHOT_DIR / "datasets-tab.png"))
    page.locator("#loadBtn").click()
    page.wait_for_timeout(1200)


def _capture_query(page) -> None:
    page.locator("#queryTabBtn").click()
    page.locator("#question").fill("Which patients have Crohn Disease?")
    page.locator("#askBtn").click()
    page.locator("#queryThread .query-thread-turn-assistant").wait_for(timeout=15000)
    page.wait_for_timeout(500)
    page.locator("#queryTab .controls").screenshot(path=str(SCREENSHOT_DIR / "query-tab.png"))


def _capture_analysis(page) -> None:
    page.locator("#analysisTabBtn").click()
    page.locator("#analysisPrompt").fill("Show a Kaplan-Meier curve for time to Clinical relapse > 0")
    page.locator("#analysisRunBtn").click()
    page.locator("#analysisThread .analysis-turn-assistant").wait_for(timeout=15000)
    page.wait_for_timeout(800)
    page.locator("#analysisTab .analysis-main").screenshot(path=str(SCREENSHOT_DIR / "analysis-tab.png"))


def _capture_pheno(page) -> None:
    page.locator("#phenoTabBtn").click()
    page.locator("#phenoPrompt").wait_for()
    page.wait_for_timeout(500)
    page.locator("#phenoTab .controls").screenshot(path=str(SCREENSHOT_DIR / "pheno-tab.png"))


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    process, base_url = _spawn_server()
    try:
        _wait_for_server(base_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1600, "height": 1400})
            _install_plotly_stub(context)
            page = context.new_page()
            page.goto(base_url, wait_until="networkidle")

            _capture_login(page)
            _login(page)
            _apply_default_workspace(page)
            _capture_datasets(page)
            _capture_query(page)
            _capture_analysis(page)
            _capture_pheno(page)

            context.close()
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
