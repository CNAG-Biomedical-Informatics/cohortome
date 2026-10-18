"""Test a frozen backend with no developer PATH, Python packages or user state."""
import argparse
import io
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import zipfile
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cohortome-relocation-") as temporary:
        root = Path(temporary)
        # Deliberately use spaces in both installation and writable-state paths.
        engine = root / "installed app/engine"
        shutil.copytree(args.engine.resolve(), engine)
        binary = engine / "cohortome-backend"
        runtime = root / "user state"
        environment = {"PATH": "", "HOME": str(root), "LANG": "C.UTF-8",
                       "PYTHONPATH": str(root / "nonexistent"), "PYTHONNOUSERSITE": "1"}
        probe = subprocess.run([str(binary), "--check-package", "--runtime-dir", str(root / "probe")],
                               cwd=root, env=environment, capture_output=True, text=True, timeout=65)
        assert probe.returncode == 0, probe.stderr
        assert "PASS: packaged job" in probe.stdout, probe.stdout
        print(probe.stdout.strip())
        for restart in (False, True):
            with (root / "stderr.log").open("w+") as errors:
                child = subprocess.Popen([str(binary), "--runtime-dir", str(runtime)], cwd=root,
                                         env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=errors, text=True)
                ready = queue.Queue()
                threading.Thread(target=lambda: ready.put(child.stdout.readline()), daemon=True).start()
                try:
                    try:
                        line = ready.get(timeout=40)
                    except queue.Empty:
                        raise AssertionError("Packaged backend startup timed out") from None
                    errors.seek(0)
                    assert line, errors.read()
                    url = json.loads(line)["url"]
                    origin = f"http://{urlsplit(url).netloc}"
                    with httpx.Client(base_url=origin, timeout=60, trust_env=False, follow_redirects=True) as client:
                        assert client.get("/").status_code == 403
                        response = client.get(url)
                        assert response.status_code == 200, response.text[:200]
                        assert client.get("/", headers={"Origin": "https://example.org"}).status_code == 403
                        assert client.get("/", headers={"Host": "example.org"}).status_code == 403
                        assert client.get("/auth/me").json()["enabled"] is False
                        for asset in ("plotly.js-dist-min/plotly.min.js", "cytoscape/cytoscape.min.js"):
                            assert client.get("/static/vendor/" + asset).status_code == 200
                        if restart:
                            assert client.get("/user-settings").json()["appearance"] == "dark"
                        else:
                            for dataset in ("default", "synthetic-autoimmune-demo"):
                                prepared = client.post(f"/datasets/{dataset}/prepare-store")
                                assert prepared.status_code == 200, prepared.text[:200]
                                response = client.get("/query", params={"q": "List all patients", "dataset_id": dataset})
                                assert response.status_code == 200, response.text[:200]
                                assert response.json()["data"].get("patient_count", 0) > 0
                            # Save the synthetic Query result through its server-side handle.
                            handle = response.json()["data"]["result_handle"]
                            saved = client.post("/saved-cohorts", json={"name": "Package test",
                                "dataset_id": "synthetic-autoimmune-demo", "result_handle": handle,
                                "source_kind": "query", "id_type": "patient"})
                            assert saved.status_code == 200, saved.text[:200]
                            identifier = saved.json()["id"]
                            for kind in ("membership", "clinical"):
                                exported = client.get(f"/saved-cohorts/{identifier}/export", params={"include": kind})
                                assert exported.status_code == 200, exported.text[:200]
                                assert zipfile.is_zipfile(io.BytesIO(exported.content))
                            assert client.patch("/user-settings", json={"appearance": "dark"}).status_code == 200
                finally:
                    child.stdin.close()
                    try:
                        code = child.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                        raise AssertionError("Packaged backend did not shut down") from None
                    child.stdout.close()
                    assert code == 0, f"Backend exited with {code}"
        print("PASS: relocated backend, both synthetic stores/queries, cohort save/export, local charts, access guards, settings restart, shutdown")


if __name__ == "__main__":
    main()
