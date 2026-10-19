"""Test a frozen backend with no developer PATH, Python packages or user state."""
import argparse
import csv
import io
import json
import math
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


def test_pheno(client, with_umap=False):
    """Run real Perl comparisons through the frozen app, including Python extraction."""
    response = client.get("/pheno-ranker/patient-ids", params={"dataset_id": "default"})
    assert response.status_code == 200, response.text[:1000]
    count = 8 if with_umap else 3
    selected = response.json()["record_ids"][:count]
    assert len(selected) == count

    def artifact(payload, name):
        files = {item["name"]: item for item in payload["files"]}
        assert name in files, f"Missing Pheno output: {name}"
        response = client.get(files[name]["url"])
        assert response.status_code == 200 and response.content, name
        return response.text

    for mode in ("cohort", "patient"):
        print(f"Checking packaged Pheno-Ranker {mode} run", flush=True)
        request = {"dataset_id": "default", "mode": mode,
                   "include_terms": ["diseases"], "render_umap": with_umap and mode == "cohort"}
        if mode == "cohort":
            request.update(selected_patient_ids=",".join(selected), similarity_metric_cohort="jaccard")
        else:
            request.update(patient_id=selected[0], max_out=3)
        response = client.post("/pheno-ranker/run", json=request, timeout=300 if with_umap else 120)
        assert response.status_code == 200, response.text[:2000]
        result = response.json()
        assert result["returncode"] == 0, result.get("stderr")
        assert "runtimes/pheno/bin/pheno-ranker" in result["command"].replace("\\", "/")
        assert any(step.startswith("internal:extract-selected-records") for step in result["pre_commands"])
        if mode == "cohort":
            records = json.loads(artifact(result, "reference.selected.json"))
            assert {record["id"] for record in records} == set(selected)
            matrix = list(csv.reader(io.StringIO(artifact(result, "matrix.txt")), delimiter="\t"))
            assert len(matrix) == count + 1 and set(matrix[0][1:]) == set(selected)
            assert {row[0] for row in matrix[1:]} == set(selected)
            assert all(len(row) == count + 1 for row in matrix)
            points = list(csv.DictReader(io.StringIO(artifact(result, "mds_points.tsv")), delimiter="\t"))
            assert len(points) == count
            if with_umap:
                points = list(csv.DictReader(io.StringIO(artifact(result, "umap_points.tsv")), delimiter="\t"))
                assert len(points) == count
                assert all(math.isfinite(float(row[axis])) for row in points for axis in ('x', 'y'))
                print("PASS: packaged UMAP projection")
            graph = json.loads(artifact(result, "graph.json"))
            assert graph
        else:
            target = json.loads(artifact(result, "target.json"))
            assert [record["id"] for record in target] == [selected[0]]
            assert len(artifact(result, "rank.txt").splitlines()) >= 2
    print("PASS: packaged Perl cohort matrix, graph, Python MDS and patient ranking with empty PATH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path)
    parser.add_argument("--require-pheno", action="store_true", help="Require real packaged Pheno-Ranker analyses")
    parser.add_argument("--require-r", action="store_true", help="Require real packaged R analysis")
    parser.add_argument("--require-umap", action="store_true", help="Require packaged Pheno-Ranker UMAP")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cohortome-relocation-") as temporary:
        root = Path(temporary)
        # Deliberately use spaces in both installation and writable-state paths.
        engine = root / "installed app/engine"
        shutil.copytree(args.engine.resolve(), engine, symlinks=True)
        binary = engine / ("cohortome-backend.exe" if os.name == "nt" else "cohortome-backend")
        runtime = root / "user state"
        environment = {"PATH": "", "HOME": str(root), "LANG": "C.UTF-8",
                       "PYTHONPATH": str(root / "nonexistent"), "PYTHONNOUSERSITE": "1"}
        if os.name == "nt":
            for key in ("SystemRoot", "WINDIR"):
                if key in os.environ:
                    environment[key] = os.environ[key]
            environment.update(USERPROFILE=str(root), LOCALAPPDATA=str(root / "local"),
                               APPDATA=str(root / "roaming"), TEMP=str(root), TMP=str(root))
        probe = subprocess.run([str(binary), "--check-package", "--runtime-dir", str(root / "probe")],
                               cwd=root, env=environment, capture_output=True, text=True, timeout=180)
        assert probe.returncode == 0, probe.stderr
        assert "PASS: packaged job" in probe.stdout, probe.stdout
        if args.require_r:
            assert "PASS: packaged R adapter" in probe.stdout, probe.stdout
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
                            if args.require_pheno or args.require_umap:
                                test_pheno(client, args.require_umap)
                except Exception:
                    # Only this test's fresh synthetic runtime is inspected.
                    # Emit diagnostics before TemporaryDirectory removes it.
                    errors.seek(0)
                    print("Packaged backend stderr:\n" + errors.read()[-12000:], flush=True)
                    logs = set(runtime.rglob("*.log")) | set(runtime.rglob("pheno_ranker_main.*.txt"))
                    for path in sorted(logs):
                        print(f"Synthetic test log {path.relative_to(runtime)}:\n" +
                              path.read_text(errors="replace")[-4000:], flush=True)
                    raise
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
