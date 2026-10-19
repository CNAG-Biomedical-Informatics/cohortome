import importlib
import json
from pathlib import Path


def test_windows_relocation_preserves_platform_metadata_not_host_path(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "desktop"))
    builder = importlib.import_module("build_native_r")
    source = tmp_path / "installed R"
    (source / "bin/x64").mkdir(parents=True)
    (source / "bin/x64/Rscript.exe").touch()
    (source / "etc").mkdir()
    (source / "library/base").mkdir(parents=True)
    output = tmp_path / "bundle"
    monkeypatch.setattr(builder.sys, "platform", "win32")
    monkeypatch.setattr(builder.sys, "argv", ["build_native_r.py", "--output", str(output)])
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
    monkeypatch.setenv("PATH", "developer tools must not leak")
    monkeypatch.setattr(builder.shutil, "which", lambda name: "Rscript.exe")
    monkeypatch.setattr(builder.subprocess, "check_output", lambda *a, **kw: json.dumps(
        {"home": str(source), "version": "4.5.2", "packages": []}))
    monkeypatch.setattr(builder.shutil, "make_archive", lambda *a, **kw: None)
    calls = []

    def run(command, *, cwd, env, **kwargs):
        calls.append(command)
        assert env["PROCESSOR_ARCHITECTURE"] == "AMD64"
        assert env["PATH"] == ""
        assert env["R_LIBS_USER"] == env["R_LIBS_SITE"] == "NULL"
        assert "runtime with spaces" in command[0]
        assert Path(command[0]).parts[-4:] == ("R", "bin", "x64", "Rscript.exe")
        assert not output.exists()
        for name in ("probe.json", "probe.png", "probe.svg", "extended.png"):
            (cwd / name).write_text("test artifact")

    monkeypatch.setattr(builder.subprocess, "run", run)
    builder.main()
    assert len(calls) == 1
    assert (output / "R/bin/x64/Rscript.exe").exists()
    assert json.loads((output / "runtime-manifest.json").read_text())["entrypoint"] == "R/bin/x64/Rscript.exe"
