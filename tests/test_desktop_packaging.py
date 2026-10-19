import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import runpy
from types import SimpleNamespace

import pytest

from app import local_jobs


@pytest.mark.parametrize("arguments,module_name", [
    ([], "server"), (["--job"], "app.local_jobs"), (["--check-package"], "package_probe"),
])
def test_frozen_entrypoint_handles_multiprocessing_before_dispatch(monkeypatch, arguments, module_name):
    import multiprocessing
    calls = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: calls.append("freeze_support"))
    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(main=lambda: calls.append("main")))
    monkeypatch.setattr(sys, "argv", ["cohortome-backend", *arguments])
    runpy.run_path(str(Path(__file__).parents[1] / "desktop/backend.py"), run_name="__main__")
    assert calls == ["freeze_support", "main"]


def test_stack_diagnostics_are_opt_in(tmp_path, monkeypatch):
    import faulthandler
    spec = importlib.util.spec_from_file_location("desktop_server_test", Path(__file__).parents[1] / "desktop/server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "argv", ["backend", "--runtime-dir", str(tmp_path)])
    assert module.runtime_directory() == tmp_path
    assert not calls
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--diagnostic-stacks"])
    assert module.runtime_directory() == tmp_path
    assert calls == [((60,), {"repeat": True})]


def test_windows_resource_icon_exists():
    desktop = Path(__file__).parents[1] / "desktop"
    config = json.loads((desktop / "tauri.conf.json").read_text())
    icons = [desktop / name for name in config["bundle"]["icon"] if name.endswith(".ico")]
    assert icons
    for icon in icons:
        assert icon.read_bytes()[:4] == b"\x00\x00\x01\x00"


def load_packager():
    spec = importlib.util.spec_from_file_location("package_desktop", Path(__file__).parents[1] / "desktop/package_desktop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_application_and_bundled_fixtures_are_allowed():
    allowed = load_packager().allowed
    for name in ("app/routes.py", "templates/index.html", "static/app.js",
                 "default_dataset/clinical/example.json", "synthetic_autoimmune_demo/manifest.json",
                 "scripts/analysis_r_limma_voom_differential_expression.R"):
        assert allowed(name)
    for name in ("runtime/state/users.json", "native.env", "docker/.env", "pdf/example.pdf",
                 "SESSION_NOTES.md", "AGENTS.md", "private_dataset/clinical/example.json",
                 "scripts/publication_evaluation.py", "docs-site/docs/overview.mdx"):
        assert not allowed(name)


def test_frozen_worker_reuses_packaged_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert local_jobs.child_command("analysis", "job-id", "local") == [
        sys.executable, "--job", "analysis", "job-id", "local"]


def test_source_worker_keeps_existing_entrypoint(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert local_jobs.child_command("pheno", "job-id", "local") == [
        sys.executable, "-m", "app.local_jobs", "pheno", "job-id", "local"]


def pheno_runtime_fixture(tmp_path, monkeypatch):
    module = load_packager()
    monkeypatch.setattr(module.sys, "platform", "linux")
    source = tmp_path / "runtime"
    hashes = {}
    for name in ("bin/pheno-ranker", "perl/bin/perl", "inline/metrics.so"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic test executable")
        path.chmod(0o755)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"platform": "linux", "architecture": module.platform.machine(),
                "perl": "5.42.3", "pheno_ranker": "1.09", "runtime_sha256": hashes}
    (source / "runtime-manifest.json").write_text(json.dumps(manifest))
    return module, source, manifest


def test_stage_verified_pheno_runtime(tmp_path, monkeypatch):
    module, source, manifest = pheno_runtime_fixture(tmp_path, monkeypatch)
    engine = tmp_path / "engine"
    assert module.stage_pheno_runtime(source, engine) == manifest
    executable = engine / "runtimes/pheno/bin/pheno-ranker"
    assert executable.read_bytes() == b"synthetic test executable"
    assert executable.stat().st_mode & 0o111


@pytest.mark.parametrize("damage", ["checksum", "missing", "unlisted", "architecture", "platform", "symlink", "traversal"])
def test_stage_pheno_rejects_invalid_runtime(tmp_path, monkeypatch, damage):
    module, source, manifest = pheno_runtime_fixture(tmp_path, monkeypatch)
    if damage == "checksum":
        (source / "bin/pheno-ranker").write_bytes(b"changed")
    elif damage == "missing":
        del manifest["runtime_sha256"]["perl/bin/perl"]
    elif damage == "unlisted":
        (source / "extra").touch()
    elif damage == "architecture":
        manifest["architecture"] = "wrong-architecture"
    elif damage == "platform":
        manifest["platform"] = "wrong-platform"
    elif damage == "symlink":
        (source / "external").symlink_to(tmp_path)
    elif damage == "traversal":
        manifest["runtime_sha256"]["../outside"] = "invalid"
    (source / "runtime-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        module.stage_pheno_runtime(source, tmp_path / "engine")
    assert not (tmp_path / "engine").exists()


@pytest.mark.parametrize("platform_name", ["darwin", "win32"])
def test_stage_other_platform_runtimes(tmp_path, monkeypatch, platform_name):
    module, source, manifest = pheno_runtime_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(module.sys, "platform", platform_name)
    manifest["platform"] = platform_name
    if platform_name == "win32":
        manifest["perl"] = "5.42.0"
        for name in ("bin/pheno-ranker", "perl/bin/perl.exe", "portable.perl"):
            path = source / name
            path.write_bytes(b"synthetic Windows fixture")
            manifest["runtime_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (source / "runtime-manifest.json").write_text(json.dumps(manifest))
    assert module.stage_pheno_runtime(source, tmp_path / "engine") == manifest


def test_frozen_server_selects_only_bundled_pheno(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("desktop_server", Path(__file__).parents[1] / "desktop/server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "engine/cohortome-backend"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(module.os, "environ", {"COHORTOME_PHENO_RANKER_BIN": "/host/pheno-ranker"})
    module.configure_environment(tmp_path / "state")
    assert module.os.environ["COHORTOME_PHENO_RANKER_BIN"] == str(tmp_path / "engine/runtimes/pheno/bin/pheno-ranker")
    assert module.os.environ["COHORTOME_RSCRIPT_BIN"] == str(tmp_path / "engine/runtimes/r/bin/Rscript")


@pytest.mark.parametrize("damage", [None, "package", "checksum", "architecture"])
def test_stage_r_runtime(tmp_path, monkeypatch, damage):
    module = load_packager()
    monkeypatch.setattr(module.sys, "platform", "linux")
    source = tmp_path / "r-runtime"
    hashes = {}
    for name in ("bin/Rscript", "R/bin/exec/R"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic R fixture")
        path.chmod(0o755)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"platform": "linux", "architecture": module.platform.machine(),
                "packages": {name: "test" for name in ("limma", "edgeR", "jsonlite")},
                "runtime_sha256": hashes}
    if damage == "package":
        del manifest["packages"]["limma"]
    elif damage == "architecture":
        manifest["architecture"] = "wrong"
    elif damage == "checksum":
        (source / "bin/Rscript").write_bytes(b"changed")
    (source / "runtime-manifest.json").write_text(json.dumps(manifest))
    if damage:
        with pytest.raises(ValueError):
            module.stage_r_runtime(source, tmp_path / "engine")
        assert not (tmp_path / "engine").exists()
    else:
        assert module.stage_r_runtime(source, tmp_path / "engine") == manifest
        assert (tmp_path / "engine/runtimes/r/bin/Rscript").stat().st_mode & 0o111
