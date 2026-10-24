"""Keep virtual-display configuration separate from startup warning checks."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    'native_smoke', Path(__file__).parents[1] / 'desktop/test_native_package.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def launch(monkeypatch, tmp_path, flags, output):
    binary = tmp_path / 'test.AppImage'
    binary.touch()
    captured = {}

    def popen(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, communicate=lambda **_: (output, None))

    monkeypatch.setattr(smoke.subprocess, 'Popen', popen)
    monkeypatch.setattr(sys, 'argv', ['test_native_package.py', str(binary), *flags])
    smoke.main()
    return captured


@pytest.mark.parametrize('virtual', [False, True])
def test_only_virtual_display_forces_software(monkeypatch, tmp_path, virtual):
    monkeypatch.setenv('LIBGL_ALWAYS_SOFTWARE', '0')
    flags = ['--check-linux-warnings', *(['--xvfb'] if virtual else [])]
    captured = launch(monkeypatch, tmp_path, flags, 'PASS: packaged native window loaded')
    assert captured['env']['LIBGL_ALWAYS_SOFTWARE'] == ('1' if virtual else '0')
    assert 'WEBKIT_DISABLE_DMABUF_RENDERER' not in captured['env']
    assert captured['env']['GTK_MODULES'] == 'canberra-gtk-module'
    if virtual:
        assert captured['command'][:2] == ['xvfb-run', '-a']


@pytest.mark.parametrize('warning', [
    'Failed to load module "canberra-gtk-module"',
    'GStreamer element appsink not found',
    'libEGL warning: DRI3 error: Could not get DRI3 device',
])
def test_virtual_display_still_rejects_warnings(monkeypatch, tmp_path, warning):
    with pytest.raises(RuntimeError, match='missing plugins or unusable graphics'):
        launch(monkeypatch, tmp_path, ['--xvfb', '--check-linux-warnings'],
               warning + '\nPASS: packaged native window loaded')
