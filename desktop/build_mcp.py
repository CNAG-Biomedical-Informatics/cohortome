"""Freeze the stdio connector in an isolated environment, without app dependencies."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Connector output already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('COHORTOME_', 'LM_STUDIO_', 'PYTHON', 'VIRTUAL_ENV'))}
    with tempfile.TemporaryDirectory(prefix='cohortome-mcp-build-') as temporary:
        work = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(work / 'venv')
        python = work / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                        str(ROOT / 'desktop/requirements-mcp.txt')], env=env, check=True)
        env['PYINSTALLER_CONFIG_DIR'] = str(work / 'cache')
        subprocess.run([str(python), '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
                        '--name', 'cohortome-mcp', '--distpath', str(work / 'dist'),
                        '--workpath', str(work / 'work'), '--specpath', str(work),
                        '--copy-metadata', 'mcp', '--exclude-module', 'tkinter',
                        str(ROOT / 'integrations/mcp/cohortome_mcp.py')],
                       cwd=work, env=env, check=True)
        frozen = work / 'dist/cohortome-mcp'
        # Collect notices from this environment, not the app's different pins.
        subprocess.run([str(python), '-c',
                        'import runpy,sys; from pathlib import Path; '
                        'runpy.run_path(sys.argv[1])["collect"](Path(sys.argv[2]))',
                        str(ROOT / 'desktop/python_notices.py'), str(frozen / 'licenses')],
                       cwd=work, env=env, check=True)
        import shutil
        shutil.move(str(frozen), output)
    size = sum(p.stat().st_size for p in output.rglob('*') if p.is_file() and not p.is_symlink())
    manifest = {'sdk': 'mcp==1.30.0', 'transport': 'stdio', 'installed_bytes': size}
    (output / 'connector-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Bundled MCP connector: {size / 1024**2:.1f} MiB installed', flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
