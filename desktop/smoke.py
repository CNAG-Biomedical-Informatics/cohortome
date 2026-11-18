"""Exercise the isolated preview backend and persistence without a GUI."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import httpx

ROOT = Path(__file__).resolve().parents[1]


def start(runtime):
    child = subprocess.Popen([sys.executable, str(ROOT / "desktop/server.py"), "--runtime-dir", runtime], cwd=ROOT,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    url = json.loads(child.stdout.readline())["url"]
    origin = f"http://{urlsplit(url).netloc}"
    client = httpx.Client(base_url=origin, trust_env=False, timeout=60, follow_redirects=True)
    assert client.get("/").status_code == 403
    assert client.get(url).status_code == 200
    return child, client, origin


def stop(child, client):
    client.close()
    child.stdin.close()
    assert child.wait(timeout=15) == 0


def check(runtime):
    child, client, origin = start(runtime)
    try:
        assert client.get("/", headers={"Origin": "http://example.org"}).status_code == 403
        assert client.get("/", headers={"Host": "example.org"}).status_code == 403
        auth = client.get("/auth/me").json()
        assert auth["enabled"] is False
        page = client.get("/").text
        assert 'id="applicationRoot"' in page and '/static/app.js' in page
        assert client.get("/static/js/react/ui.js").is_success
        assert client.post("/datasets/default/prepare-store").status_code == 200
        response = client.get("/query", params={"q": "List all patients", "dataset_id": "default"})
        assert response.status_code == 200, response.text[:300]
        settings = client.get("/user-settings").json()
        response = client.patch("/user-settings", json={"appearance": "dark"})
        assert response.status_code == 200, response.text[:300]
    finally:
        stop(child, client)
    child, client, origin = start(runtime)
    try:
        value = client.get("/user-settings").json()
        assert "dark" in json.dumps(value), value
    finally:
        stop(child, client)
    print("PASS: private backend, shared UI, synthetic store/query, settings restart, clean shutdown")


if __name__ == "__main__":
    with TemporaryDirectory(prefix="cohortome-desktop-smoke-") as runtime:
        check(runtime)
