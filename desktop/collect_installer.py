"""Collect one checksum-verified installer, without the portable test archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


PATTERNS = {'linux': '*.AppImage', 'darwin': '*.dmg', 'win32': '*-setup.exe'}
NAMES = {
    ('linux', 'aarch64'): 'cohortome-linux-aarch64.AppImage',
    ('linux', 'x86_64'): 'cohortome-linux-x86_64.AppImage',
    ('darwin', 'arm64'): 'cohortome-macos-apple-silicon.dmg',
    ('darwin', 'x86_64'): 'cohortome-macos-intel.dmg',
    ('win32', 'AMD64'): 'cohortome-windows-x86_64-setup.exe',
}


def collect(source, output):
    manifests = list(source.rglob('installer-manifest.json'))
    if len(manifests) != 1:
        raise ValueError('Expected exactly one installer manifest.')
    manifest = json.loads(manifests[0].read_text(encoding='utf-8'))
    installers = list(source.rglob(PATTERNS[manifest['platform']]))
    if len(installers) != 1:
        raise ValueError('Expected exactly one platform installer.')
    installer = installers[0]
    expected = [value for name, value in manifest['sha256'].items()
                if name.replace('\\', '/').split('/')[-1] == installer.name]
    with installer.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if expected != [digest]:
        raise ValueError('Installer does not match its build manifest.')
    name = NAMES[(manifest['platform'], manifest['architecture'])]
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(installer, output / name)
    (output / (name + '.sha256')).write_text(
        f'{digest}  {name}\n', encoding='utf-8')
    print(f'{name}: {installer.stat().st_size / 1024**2:.1f} MiB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.source, args.output)
