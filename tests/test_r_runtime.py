from types import SimpleNamespace
import subprocess

import pytest

from app import r_runtime


def test_explicit_missing_r_does_not_fall_back_to_host(monkeypatch):
    monkeypatch.setenv("COHORTOME_RSCRIPT_BIN", "/missing/bundled/Rscript")
    monkeypatch.setattr(r_runtime.shutil, "which", lambda _: "/host/Rscript")
    assert r_runtime.rscript_binary() is None


def test_explicit_r_binary(tmp_path, monkeypatch):
    binary = tmp_path / "Rscript"
    binary.touch()
    monkeypatch.setenv("COHORTOME_RSCRIPT_BIN", str(binary))
    assert r_runtime.rscript_binary() == str(binary)


def test_missing_r_packages_are_reported_and_probe_is_shared(monkeypatch):
    monkeypatch.setattr(r_runtime, "rscript_binary", lambda: "/bundle/Rscript")
    r_runtime._installed_packages.cache_clear()
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout="COHORTOME_R_PACKAGES=limma,edgeR,jsonlite\n")
    monkeypatch.setattr(r_runtime.subprocess, "run", run)
    assert r_runtime.rscript_unavailable_reason("transcriptomics_limma_voom_differential_expression") == ""
    assert r_runtime.rscript_unavailable_reason("transcriptomics_deseq2_differential_expression") == "Missing R packages: DESeq2, apeglm."
    assert len(calls) == 1
    r_runtime._installed_packages.cache_clear()


def test_failed_package_probe_does_not_mark_analysis_ready(monkeypatch):
    monkeypatch.setattr(r_runtime, "rscript_binary", lambda: "/bundle/Rscript")
    def fail(*args):
        raise subprocess.TimeoutExpired("Rscript", 30)
    monkeypatch.setattr(r_runtime, "_installed_packages", fail)
    assert "Could not verify" in r_runtime.rscript_unavailable_reason("methylation_qc_pca")
