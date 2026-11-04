"""Keep Docker preparation pins and checks aligned with the desktop runtime."""
import ast
from pathlib import Path

import pytest

from app import geo_gse85034 as recipe
from app.geo_source import SourcePreparationError

ROOT = Path(__file__).resolve().parents[1]


def test_docker_preparation_sources_match_desktop():
    module = ast.parse((ROOT / "desktop/build_unix_pheno.py").read_text())
    sources = next(ast.literal_eval(node.value) for node in module.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "SOURCES" for target in node.targets))
    installer = (ROOT / "docker/install_preparation_tools.sh").read_text()
    for tool in ("convert", "clarid"):
        url, digest = sources[tool]
        assert url in installer
        assert f"{digest}  {url.rsplit('/', 1)[1]}" in installer
    assert installer.index("sha256sum --check --strict") < installer.index("cpanm --notest")
    dockerfile = (ROOT / "docker/Dockerfile").read_text()
    assert "COHORTOME_CLARID_CODEBOOK=/usr/local/share/cohortome/clarid-codebook.yaml" in dockerfile
    assert "sh /tmp/install_preparation_tools.sh" in dockerfile
    assert dockerfile.index("USER cohortome") < dockerfile.index("RUN python -m scripts.test_preparation_runtime")
    assert '"-m", "scripts.test_preparation_runtime"' in (ROOT / "scripts/test_docker_deployment.py").read_text()


def test_preflight_accepts_installed_tools_and_explicit_codebook(tmp_path, monkeypatch):
    book = tmp_path / "clarid-codebook.yaml"
    book.touch()
    monkeypatch.setenv("COHORTOME_CLARID_CODEBOOK", str(book))
    monkeypatch.setattr(recipe, "preparation_command", lambda tool: [f"/usr/local/bin/{tool}"])
    versions = {"convert-pheno": "0.35", "clarid-tools": "0.05"}
    monkeypatch.setattr(recipe.subprocess, "check_output",
                        lambda args, **kw: f"version {versions[Path(args[0]).name]}\n")
    recipe.preflight()
    assert recipe.codebook_path() == book
    versions["clarid-tools"] = "0.04"
    with pytest.raises(SourcePreparationError, match="requires clarid-tools 0.05"):
        recipe.preflight()
    versions["clarid-tools"] = "0.05"
    book.unlink()
    with pytest.raises(SourcePreparationError, match="configured ClarID codebook is unavailable"):
        recipe.preflight()
