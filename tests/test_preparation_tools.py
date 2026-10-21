from app import preparation_tools as tools


def test_explicit_missing_tool_never_falls_back(tmp_path, monkeypatch):
    host = tmp_path / "host-tool"
    host.touch()
    monkeypatch.setattr(tools.shutil, "which", lambda _: str(host))
    monkeypatch.setenv("COHORTOME_CONVERT_PHENO_BIN", str(tmp_path / "missing"))
    assert tools.preparation_command("convert-pheno") is None


def test_windows_invokes_selected_perl_and_script_without_shell(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "win32")
    script, perl = tmp_path / "tool with spaces", tmp_path / "perl.exe"
    script.touch()
    perl.touch()
    monkeypatch.setenv("COHORTOME_CLARID_TOOLS_BIN", str(script))
    monkeypatch.setenv("COHORTOME_PREPARATION_PERL_BIN", str(perl))
    assert tools.preparation_command("clarid-tools") == [str(perl), str(script)]
    perl.unlink()
    assert tools.preparation_command("clarid-tools") is None
