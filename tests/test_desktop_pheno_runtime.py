import importlib.util
from pathlib import Path
import subprocess

import pytest


def builder():
    spec = importlib.util.spec_from_file_location("build_unix_pheno", Path(__file__).parents[1] / "desktop/build_unix_pheno.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_checksum_checked_before_extraction(tmp_path, monkeypatch):
    module = builder()
    url, _ = module.SOURCES["pheno"]
    (tmp_path / url.rsplit("/", 1)[1]).write_bytes(b"wrong archive")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        module.fetch_source("pheno", tmp_path, tmp_path)


def test_relocation_removes_original_prefix_and_restores_on_failure(tmp_path, monkeypatch):
    module = builder()
    original = tmp_path / "runtime"
    original.mkdir()
    (original / "marker").touch()
    def run(command, **kwargs):
        assert not original.exists()
        assert "relocated runtime with spaces" in command[0]
        assert kwargs["env"]["PATH"] == ""
        assert "PERL5LIB" not in kwargs["env"]
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        module.test_relocated(original, tmp_path / "fixture.json", tmp_path)
    assert (original / "marker").exists()
