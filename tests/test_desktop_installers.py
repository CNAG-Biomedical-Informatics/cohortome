import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'desktop'))
spec = importlib.util.spec_from_file_location('build_installers', Path(__file__).parents[1] / 'desktop/build_installers.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
sys.path.pop(0)


@pytest.mark.parametrize('system,targets', [('linux', ['appimage']), ('darwin', ['app', 'dmg']), ('win32', ['nsis'])])
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
