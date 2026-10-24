"""Build a desktop test bundle, not an installer. Run in a clean build venv."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TREES = {"app", "static", "templates", "datasets/synthetic-longitudinal-demo", "datasets/synthetic-cross-sectional-demo"}
FILES = {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "licenses/pydicom-3.0.2.txt", "scripts/data/README.md", "pyproject.toml", "config/analysis/catalog.yaml", "config/resources.json",
         "config/analysis/synthetic_script_inputs.json", "scripts/data/hgnc_protein_coding_symbols.tsv"}
SOURCE_PATHS = ['app', 'desktop', 'static', 'templates', 'datasets', 'config', 'scripts',
                'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'licenses', 'pyproject.toml']
CHARTS = {
    "plotly.js-dist-min": ("2.35.2", "plotly.min.js", "https://cdn.plot.ly/plotly-2.35.2.min.js"),
    "cytoscape": ("3.33.1", "dist/cytoscape.min.js", "https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.33.1/cytoscape.min.js"),
}


def allowed(path):
    parts = Path(path).parts
    return (any(path.startswith(tree + "/") for tree in TREES) or path in FILES or
            (len(parts) == 2 and parts[0] == "scripts" and parts[1].startswith("analysis_") and path.endswith(".R")))


def source_is_dirty():
    return bool(subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--', *SOURCE_PATHS], cwd=ROOT))


def stage(destination, chart_modules):
    # Explicit allowlist AND tracked files: never recursively copy a checkout,
    # runtime, local config, untracked data, notebooks or sibling directories.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, tracked):
        if not allowed(name):
            continue
        source = ROOT / name
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(ROOT):
            raise ValueError(f"Not a regular in-checkout package file: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    registry = json.loads((ROOT / "config/datasets/registry.json").read_text(encoding="utf-8"))
    registry = [item for item in registry if item["dataset_id"] in {"default", "synthetic-cross-sectional-demo"}]
    assert len(registry) == 2
    assert {item["root_path"] for item in registry} == {"datasets/synthetic-longitudinal-demo", "datasets/synthetic-cross-sectional-demo"}
    (destination / "config/datasets").mkdir(parents=True)
    (destination / "config/datasets/registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    template = destination / "templates/index.html"
    html = template.read_text(encoding="utf-8")
    for package, (version, asset, url) in CHARTS.items():
        vendor = destination / "static/vendor" / package
        vendor.mkdir(parents=True)
        package_dir = chart_modules / package
        if json.loads((package_dir / "package.json").read_text(encoding="utf-8"))["version"] != version:
            raise ValueError(f"Packaging requires {package}@{version}, matching the web app")
        shutil.copyfile(package_dir / asset, vendor / Path(asset).name)
        for filename in ("LICENSE", "package.json"):
            shutil.copyfile(package_dir / filename, vendor / filename)
        assert url in html
        html = html.replace(url, f"/static/vendor/{package}/{Path(asset).name}")
    template.write_text(html, encoding="utf-8")
    for name in ("backend.py", "server.py", "package_probe.py", "r_package_probe.py", "preparation_probe.py"):
        shutil.copyfile(ROOT / "desktop" / name, destination / name)


def stage_perl_runtime(source, engine):
    source = source.resolve()
    manifest = json.loads((source / 'runtime-manifest.json').read_text())
    if manifest.get('platform') != sys.platform or manifest.get('architecture') != platform.machine():
        raise ValueError('Perl runtime must match this build platform and architecture')
    perl_version = str(manifest.get('perl', ''))
    if (not perl_version.startswith('5.42.') if sys.platform == 'win32' else perl_version != '5.42.3') or manifest.get('tools') != {
            'pheno-ranker': '1.09', 'convert-pheno': '0.35', 'clarid-tools': '0.04'}:
        raise ValueError('Unsupported or incomplete Perl runtime')
    executables = ('bin/pheno-ranker', 'perl/bin/perl.exe', 'portable.perl') if sys.platform == 'win32' else ('bin/pheno-ranker', 'perl/bin/perl')
    executables += ('bin/convert-pheno', 'bin/clarid-tools')
    return copy_verified_runtime(source, engine / 'runtimes/perl', manifest, executables)


def stage_r_runtime(source, engine):
    source = source.resolve()
    manifest = json.loads((source / 'runtime-manifest.json').read_text())
    if sys.platform not in {'linux', 'darwin', 'win32'} or manifest.get('platform') != sys.platform or manifest.get('architecture') != platform.machine():
        raise ValueError('R runtime must match this build platform and architecture')
    if not {'limma', 'edgeR', 'jsonlite'}.issubset(manifest.get('packages', {})):
        raise ValueError('R runtime is missing core analysis packages')
    entrypoint = 'R/bin/x64/Rscript.exe' if sys.platform == 'win32' else 'bin/Rscript'
    if manifest.get('entrypoint', entrypoint) != entrypoint:
        raise ValueError('Unexpected R runtime entrypoint')
    executables = (entrypoint, 'R/bin/x64/R.dll') if sys.platform == 'win32' else (entrypoint, 'R/bin/exec/R')
    return copy_verified_runtime(source, engine / 'runtimes/r', manifest, executables)


def copy_verified_runtime(source, destination, manifest, executables):
    hashes = manifest.get('runtime_sha256') or {}
    for required in executables:
        if required not in hashes:
            raise ValueError('Runtime manifest is missing required executables')
    for path in source.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(source):
            raise ValueError('Runtime contains an external symlink')
        if path.is_file() and path.name != 'runtime-manifest.json':
            name = path.relative_to(source).as_posix()
            if hashes.get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('Runtime checksum mismatch')
    for name, digest in hashes.items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Runtime checksum mismatch')
    shutil.copytree(source, destination, symlinks=True)
    return manifest


def stage_ohif_assets(source, destination):
    source = source.resolve()
    manifest = json.loads((source / 'viewer-manifest.json').read_text(encoding='utf-8'))
    hashes = manifest.get('sha256') or {}
    if 'index.html' not in hashes or not str(manifest.get('image', '')).startswith('ohif/app@sha256:'):
        raise ValueError('OHIF assets need a pinned image and index.html checksum')
    actual = {}
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('OHIF assets must not contain symbolic links')
        if path.is_file() and path.name != 'viewer-manifest.json':
            actual[path.relative_to(source).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != hashes:
        raise ValueError('OHIF asset checksum mismatch')
    shutil.copytree(source, destination)
    return manifest


def main():
    from python_notices import collect as collect_python_notices
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing directories are refused")
    parser.add_argument("--with-native", action="store_true", help="Also build the Tauri window and archive")
    parser.add_argument("--chart-modules", type=Path, default=ROOT / "node_modules")
    parser.add_argument('--perl-runtime', type=Path, help='Verified shared Perl runtime with Pheno-Ranker, Convert-Pheno and ClarID')
    parser.add_argument('--r-runtime', type=Path, help='Verified platform-matched R runtime')
    parser.add_argument('--with-umap', action='store_true', help='Bundle the installed UMAP stack')
    parser.add_argument('--ohif-assets', type=Path, help='Reviewed OHIF static assets to embed; no image data')
    args = parser.parse_args()
    if sys.platform not in {"linux", "darwin", "win32"}:
        parser.error("Packaging targets Linux, macOS and Windows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="cohortome-freeze-") as temporary:
        staging = Path(temporary) / "source"
        staging.mkdir()
        stage(staging, args.chart_modules.resolve())
        collect_python_notices(staging / 'licenses/python')
        viewer_manifest = stage_ohif_assets(args.ohif_assets, staging / 'runtime/ohif') if args.ohif_assets else None
        command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
                   "--name", "cohortome-backend", "--distpath", str(output / "frozen"),
                   "--workpath", str(Path(temporary) / "work"), "--specpath", temporary,
                   "--paths", str(staging), "--collect-submodules", "app",
                   "--collect-submodules", "uvicorn", "--collect-all", "pydicom", "--hidden-import", "preparation_probe",
                   "--copy-metadata", "cohortome", "--exclude-module", "tkinter"]
        if args.with_umap:
            # Same dynamic-import handling as Pheno-Ranker Desktop's Python helper.
            command.extend(['--collect-all', 'umap', '--collect-all', 'pynndescent',
                            '--collect-submodules', 'scipy._external.array_api_compat.numpy'])
            for package in ('umap-learn', 'numba', 'llvmlite', 'scikit-learn', 'scipy'):
                command.extend(['--copy-metadata', package])
        # Include readable analysis implementations for the existing audit export.
        for child in staging.iterdir():
            if child.name in {"backend.py", "server.py", "package_probe.py", "r_package_probe.py", "preparation_probe.py"}:
                continue
            command.extend(["--add-data", f"{child}:{child.name if child.is_dir() else '.'}"])
        command.append(str(staging / "backend.py"))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("COHORTOME_", "LM_STUDIO_", "UVICORN_", "PYTHONPATH"))}
        environment["PYINSTALLER_CONFIG_DIR"] = str(Path(temporary) / "cache")
        subprocess.run(command, cwd=staging, env=environment, check=True)
    shutil.move(str(output / "frozen/cohortome-backend"), output / "engine")
    (output / "frozen").rmdir()
    perl_manifest = stage_perl_runtime(args.perl_runtime, output / 'engine') if args.perl_runtime else None
    r_manifest = stage_r_runtime(args.r_runtime, output / 'engine') if args.r_runtime else None
    if args.with_native:
        subprocess.run(["cargo", "build", "--release", "--locked", "--manifest-path",
                        str(ROOT / "desktop/Cargo.toml"), "--features", "custom-protocol"],
                       env=dict(os.environ, CARGO_TARGET_DIR=str(ROOT / 'desktop/target')), check=True)
        native = "cohortome-desktop.exe" if os.name == "nt" else "cohortome-desktop"
        shutil.copy2(ROOT / "desktop/target/release" / native, output / native)
        if sys.platform == "darwin":
            subprocess.run(["codesign", "--force", "--sign", "-", str(output / "cohortome-desktop")], check=True)
    manifest = {"kind": "desktop-packaging-test", "platform": sys.platform, "architecture": platform.machine(),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "working_tree_changes": source_is_dirty(),
                "perl_runtime": perl_manifest,
                "r_runtime": r_manifest,
                "viewer": viewer_manifest,
                "not_bundled": ([] if perl_manifest else ["Perl/Pheno-Ranker/Convert-Pheno/ClarID"]) + ([] if r_manifest else ["R/Bioconductor"]) + ([] if args.with_umap else ["UMAP"]) + ([] if args.ohif_assets else ["OHIF"]) + ["Docker"],
                "python_packages": json.loads(subprocess.check_output(
                    [sys.executable, "-m", "pip", "list", "--format=json"], text=True)),
                "sha256": {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted(output.rglob("*")) if path.is_file()}}
    (output / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.with_native:
        shutil.make_archive(str(output), "zip" if os.name == "nt" else "gztar", root_dir=output.parent, base_dir=output.name)
    print(f"Test bundle: {output}")


if __name__ == "__main__":
    main()
