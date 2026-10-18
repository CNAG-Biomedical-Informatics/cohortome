import importlib.util
from pathlib import Path
import sys

from app import local_jobs


def load_packager():
    spec = importlib.util.spec_from_file_location("package_linux", Path(__file__).parents[1] / "desktop/package_linux.py")
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
