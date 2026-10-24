import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'desktop'))
spec = importlib.util.spec_from_file_location('build_installers', Path(__file__).parents[1] / 'desktop/build_installers.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
sys.path.pop(0)


@pytest.mark.parametrize('system,targets', [('linux', ['appimage']), ('darwin', ['app']), ('win32', ['nsis'])])
def test_installer_resources_preserve_engine_layout(tmp_path, system, targets):
    package = tmp_path / 'package with spaces'
    config = builder.installer_config(package, system)
    assert config['bundle']['resources'][str(package / 'engine')] == 'engine'
    assert config['bundle']['targets'] == targets
    # Do not silently move existing preview user data to a new app identifier.
    assert 'identifier' not in config
    if system == 'win32':
        assert config['bundle']['windows']['nsis']['installMode'] == 'currentUser'


@pytest.mark.parametrize('damage', ['', 'modified', 'extra', 'commit', 'dirty', 'platform', 'symlink', 'missing'])
def test_installer_rejects_unverified_package(tmp_path, damage):
    package = tmp_path / 'package'
    (package / 'engine').mkdir(parents=True)
    filename = 'cohortome-backend.exe' if sys.platform == 'win32' else 'cohortome-backend'
    backend = package / 'engine' / filename
    backend.write_bytes(b'synthetic executable')
    manifest = {'platform': sys.platform, 'architecture': platform.machine(), 'git_commit': 'a' * 40,
                'working_tree_changes': False,
                'sha256': {str(backend.relative_to(package)): hashlib.sha256(backend.read_bytes()).hexdigest()}}
    if damage == 'modified':
        backend.write_bytes(b'changed')
    elif damage == 'extra':
        (package / 'extra').write_text('unreviewed')
    elif damage == 'commit':
        manifest['git_commit'] = 'b' * 40
    elif damage == 'dirty':
        manifest['working_tree_changes'] = True
    elif damage == 'platform':
        manifest['platform'] = 'other'
    elif damage == 'symlink':
        (tmp_path / 'external').write_text('external')
        (package / 'link').symlink_to(tmp_path / 'external')
    elif damage == 'missing':
        backend.unlink()
    (package / 'package-manifest.json').write_text(json.dumps(manifest))
    if damage:
        with pytest.raises(ValueError):
            builder.verify_package(package, 'a' * 40)
    else:
        assert builder.verify_package(package, 'a' * 40) == manifest


def test_macos_dmg_uses_folder_without_writable_mount(tmp_path, monkeypatch):
    artifacts = tmp_path / 'bundle'
    app = artifacts / 'macos' / 'App with spaces.app'
    app.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(builder.subprocess, 'run', lambda command, **kwargs: calls.append((command, kwargs)))
    builder.build_macos_dmg(artifacts, tmp_path)
    assert calls[0][0] == ['codesign', '--verify', '--deep', '--strict', str(app)]
    assert calls[1][0] == ['ditto', str(app), str(tmp_path / 'dmg-staging' / app.name)]
    assert (tmp_path / 'dmg-staging' / 'Applications').readlink() == Path('/Applications')
    assert calls[2][0] == ['hdiutil', 'create', '-volname', 'COHORTome',
                           '-srcfolder', str(tmp_path / 'dmg-staging'), '-fs', 'HFS+',
                           '-format', 'UDZO', str(artifacts / 'dmg' / 'COHORTome.dmg')]
    assert calls[3][0] == ['hdiutil', 'verify', str(artifacts / 'dmg' / 'COHORTome.dmg')]
    assert all(options == {'check': True} for _, options in calls)


def test_macos_dmg_stops_on_signing_failure(tmp_path, monkeypatch):
    app = tmp_path / 'bundle' / 'macos' / 'Test.app'
    app.mkdir(parents=True)
    def fail(command, **kwargs):
        raise builder.subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(builder.subprocess, 'run', fail)
    with pytest.raises(builder.subprocess.CalledProcessError):
        builder.build_macos_dmg(tmp_path / 'bundle', tmp_path)
    assert not (tmp_path / 'dmg-staging').exists()


@pytest.mark.parametrize('system', ['linux', 'darwin', 'win32'])
def test_installer_reuses_cargo_target_and_moves_bundle(tmp_path, monkeypatch, system):
    package = tmp_path / 'package'
    package.mkdir()
    (package / 'package-manifest.json').write_text('{}')
    output = tmp_path / 'installers'
    target = tmp_path / 'desktop/target'
    (target / 'release/deps').mkdir(parents=True)
    dependency = target / 'release/deps/compiled-dependency'
    dependency.write_text('keep')
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'sys', SimpleNamespace(platform=system))
    monkeypatch.setattr(sys, 'argv', ['build_installers.py', '--package', str(package), '--output', str(output)])
    monkeypatch.setattr(builder, 'source_is_dirty', lambda: False)
    monkeypatch.setattr(builder, 'verify_package', lambda *_: {})
    monkeypatch.setattr(builder.subprocess, 'check_output', lambda *a, **k: 'commit')
    monkeypatch.setattr(builder.shutil, 'which', lambda _: '/npm')
    monkeypatch.setattr(builder, 'collect', lambda *_: None)
    monkeypatch.setattr(builder, 'build_macos_dmg', lambda *_: None)
    def build(command, **options):
        assert options['env']['CARGO_TARGET_DIR'] == str(target)
        bundle = target / 'release/bundle'
        bundle.mkdir()
        (bundle / 'installer').write_text('new')
    monkeypatch.setattr(builder.subprocess, 'run', build)
    builder.main()
    assert dependency.read_text() == 'keep'
    assert not (target / 'release/bundle').exists()
    assert (output / 'bundle/installer').read_text() == 'new'
    manifest = json.loads((output / 'installer-manifest.json').read_text())
    assert set(manifest['sha256']) == {'installer'}


@pytest.mark.parametrize('system,arch,filename', [
    ('linux', 'aarch64', 'Preview.AppImage'),
    ('linux', 'x86_64', 'Preview.AppImage'),
    ('darwin', 'arm64', 'Preview.dmg'),
    ('darwin', 'x86_64', 'Preview.dmg'),
    ('win32', 'AMD64', 'Preview-setup.exe'),
])
def test_collect_only_verified_installer(tmp_path, system, arch, filename):
    module = sys.modules['collect_installer']
    source = tmp_path / 'source'
    source.mkdir()
    (source / filename).write_bytes(b'synthetic installer')
    (source / 'portable.tar.gz').write_bytes(b'not a download')
    digest = hashlib.sha256(b'synthetic installer').hexdigest()
    (source / 'installer-manifest.json').write_text(json.dumps({
        'platform': system, 'architecture': arch, 'sha256': {'bundle\\' + filename: digest},
    }))
    output = tmp_path / 'downloads'
    module.collect(source, output)
    name = module.NAMES[(system, arch)]
    assert sorted(p.name for p in output.iterdir()) == [name, name + '.sha256']
    assert (output / (name + '.sha256')).read_text() == f'{digest}  {name}\n'
    (source / filename).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='manifest'):
        module.collect(source, tmp_path / 'rejected')
    assert not (tmp_path / 'rejected').exists()
