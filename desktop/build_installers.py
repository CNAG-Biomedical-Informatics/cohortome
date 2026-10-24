"""Wrap a verified desktop test bundle in native installers; never publish it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from package_desktop import source_is_dirty
from collect_installer import collect

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {'linux': ['appimage'], 'darwin': ['app'], 'win32': ['nsis']}
TAURI_CLI = '@tauri-apps/cli@2.11.4'


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify_package(package, commit):
    manifest = json.loads((package / 'package-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('platform') != sys.platform or manifest.get('architecture') != platform.machine():
        raise ValueError('The package must match the installer build host.')
    if manifest.get('git_commit') != commit or manifest.get('working_tree_changes'):
        raise ValueError('Rebuild the portable package from this clean source commit.')
    hashes = manifest.get('sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('Package checksums are missing.')
    actual = {}
    for path in package.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(package):
            raise ValueError('Package contains an external symbolic link.')
        if path.is_file() and path != package / 'package-manifest.json':
            actual[str(path.relative_to(package))] = sha256(path)
    if actual != hashes:
        raise ValueError('Package content does not match its checksum manifest.')
    backend = 'cohortome-backend.exe' if sys.platform == 'win32' else 'cohortome-backend'
    if not (package / 'engine' / backend).is_file():
        raise ValueError('Packaged Python backend is missing.')
    return manifest


def installer_config(package, system):
    if system not in TARGETS:
        raise ValueError('Unsupported installer platform.')
    bundle = {
        'active': True, 'targets': TARGETS[system], 'category': 'Medical',
        'shortDescription': 'Clinical and multimodal research workspace',
        'license': 'Apache-2.0',
        'resources': {str(package / 'engine'): 'engine',
                      str(package / 'package-manifest.json'): 'package-manifest.json'},
    }
    if system == 'darwin':
        # Test installers only. Ad-hoc signing is not notarization.
        bundle['macOS'] = {'signingIdentity': '-'}
    if system == 'linux':
        bundle['linux'] = {'appimage': {'bundleMediaFramework': True}}
    if system == 'win32':
        bundle['windows'] = {'nsis': {'installMode': 'currentUser'},
                             'webviewInstallMode': {'type': 'downloadBootstrapper'}}
    return {'productName': 'COHORTome Desktop Preview', 'bundle': bundle}


def build_macos_dmg(artifacts, output):
    """Create a plain DMG without mounting a writable image for customization."""
    apps = list((artifacts / 'macos').glob('*.app'))
    if len(apps) != 1:
        raise ValueError('Expected exactly one signed macOS application.')
    app = apps[0]
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    staging = output / 'dmg-staging'
    staging.mkdir(exist_ok=False)
    # ditto preserves the signed bundle's metadata and internal symbolic links.
    subprocess.run(['ditto', str(app), str(staging / app.name)], check=True)
    (staging / 'Applications').symlink_to('/Applications', target_is_directory=True)
    dmg_dir = artifacts / 'dmg'
    dmg_dir.mkdir(exist_ok=False)
    dmg = dmg_dir / 'COHORTome.dmg'
    subprocess.run(['hdiutil', 'create', '-volname', 'COHORTome',
                    '-srcfolder', str(staging), '-fs', 'HFS+', '-format', 'UDZO',
                    str(dmg)], check=True)
    subprocess.run(['hdiutil', 'verify', str(dmg)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New installer build directory')
    args = parser.parse_args()
    package = args.package.resolve()
    output = args.output.resolve()
    if output == package or output.is_relative_to(package):
        parser.error('Installer output must be outside the portable package.')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if source_is_dirty():
        parser.error('Commit application and packaging changes before building installers.')
    manifest = verify_package(package, commit)
    config = installer_config(package, sys.platform)
    if sys.platform == 'linux':
        # GTK_PATH inside the AppImage does not include the host's modules.
        libdir = Path(subprocess.check_output(
            ['pkg-config', '--variable=libdir', 'gtk+-3.0'], text=True).strip())
        module = libdir / 'gtk-3.0/modules/libcanberra-gtk-module.so'
        if not module.is_file():
            parser.error('Install libcanberra-gtk3-module before building the AppImage.')
        config['bundle']['linux']['appimage']['files'] = {
            'usr/lib/gtk-3.0/modules/libcanberra-gtk-module.so': str(module.resolve()),
        }
    output.mkdir(parents=True, exist_ok=False)
    config_path = output / 'installer-config.json'
    config_path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    # Reuse the portable build's dependencies; Cargo tracks configuration changes.
    target = ROOT / 'desktop/target'
    bundle = target / 'release/bundle'
    if bundle.exists():
        parser.error(f'Existing installer output at {bundle}; move it aside before rebuilding.')
    env = dict(os.environ, CARGO_TARGET_DIR=str(target))
    npm = shutil.which('npm')
    if not npm:
        parser.error('Node.js/npm is required for the pinned Tauri installer builder.')
    subprocess.run([npm, 'exec', '--yes', '--package', TAURI_CLI, '--', 'tauri', 'build', '--verbose',
                    '--config', str(config_path), '--bundles', ','.join(TARGETS[sys.platform]),
                    '--', '--locked'], cwd=ROOT / 'desktop', env=env, check=True)
    # Keep installer artifacts separate without discarding compiled dependencies.
    artifacts = output / 'bundle'
    shutil.move(str(bundle), artifacts)
    if sys.platform == 'darwin':
        build_macos_dmg(artifacts, output)
    files = {str(p.relative_to(artifacts)): sha256(p) for p in sorted(artifacts.rglob('*')) if p.is_file()}
    if not files:
        raise RuntimeError('Tauri did not produce installers.')
    (output / 'installer-manifest.json').write_text(json.dumps({
        'kind': 'desktop-installer-test', 'git_commit': commit, 'platform': sys.platform,
        'architecture': platform.machine(), 'tauri_cli': TAURI_CLI,
        'package_manifest_sha256': sha256(package / 'package-manifest.json'),
        'redistribution_review': 'pending', 'sha256': files,
        'not_bundled': manifest.get('not_bundled', []),
    }, indent=2) + '\n', encoding='utf-8')
    collect(output, output / 'downloads')
    print(f'Installer test output (not approved for publication): {output / "downloads"}')


if __name__ == '__main__':
    main()
