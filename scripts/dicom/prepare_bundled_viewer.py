"""Extract pinned OHIF browser assets for the local prototype (Docker at build time only)."""
import io
from pathlib import Path
import subprocess
import tarfile

IMAGE = 'ohif/app@sha256:d3f221a4408119f8d5e07dc7ed2ce0fe4e5925bbde1310efa2e046614083c25a'
DESTINATION = Path(__file__).resolve().parents[2] / 'runtime' / 'ohif'


def main():
    if DESTINATION.exists():
        raise SystemExit('runtime/ohif already exists; preserve it or move it aside before preparing again.')
    result = subprocess.run([
        'docker', 'run', '--rm', '--network', 'none', '--read-only', '--entrypoint', 'tar',
        IMAGE, '-C', '/usr/share/nginx/html', '-cf', '-', '.',
    ], check=True, stdout=subprocess.PIPE)
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        archive.extractall(DESTINATION, filter='data')
    print(f'Prepared OHIF assets: {sum(p.stat().st_size for p in DESTINATION.rglob("*") if p.is_file()) / 1024**2:.1f} MiB')
    print('Local prototype only. Third-party notices and release packaging still require review.')


if __name__ == '__main__':
    main()
