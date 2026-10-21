"""Extract checksum-recorded OHIF static assets (Docker at build time only)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

IMAGE = 'ohif/app@sha256:d3f221a4408119f8d5e07dc7ed2ce0fe4e5925bbde1310efa2e046614083c25a'
DESTINATION = Path(__file__).resolve().parents[2] / 'runtime' / 'ohif'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DESTINATION)
    destination = parser.parse_args().output.resolve()
    if destination.exists():
        raise SystemExit('Output already exists; use a new directory.')
    # Copy static files without executing the image, regardless of host CPU.
    container = subprocess.check_output(['docker', 'create', '--platform', 'linux/arm64', IMAGE], text=True).strip()
    try:
        destination.mkdir(parents=True)
        subprocess.run(['docker', 'cp', container + ':/usr/share/nginx/html/.', str(destination)], check=True)
    finally:
        subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
    if not (destination / 'index.html').is_file():
        raise ValueError('Viewer image has no index.html')
    hashes = {}
    for path in sorted(destination.rglob('*')):
        if path.is_symlink():
            raise ValueError('Viewer assets contain a symbolic link')
        if path.is_file():
            hashes[path.relative_to(destination).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (destination / 'viewer-manifest.json').write_text(json.dumps({
        'image': IMAGE, 'sha256': hashes,
    }, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared {len(hashes)} pinned OHIF static files. No DICOM data included.')


if __name__ == '__main__':
    main()
