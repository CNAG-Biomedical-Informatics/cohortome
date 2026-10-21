"""Build a shared Perl runtime for Pheno-Ranker, Convert-Pheno and ClarID."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

SOURCES = {
    "perl": ("https://www.cpan.org/src/5.0/perl-5.42.3.tar.gz",
             "1137740985837b5cdf15f0cfab932279dcb4352f912fed6fc144e8b4f0823627"),
    "cpanm": ("https://cpan.metacpan.org/authors/id/M/MI/MIYAGAWA/App-cpanminus-1.7049.tar.gz",
              "b9ffb88e62a06aa91bd7d5a28ef6bdbb942608aea90e3969aa29b33640035214"),
    "pheno": ("https://cpan.metacpan.org/authors/id/M/MR/MRUEDA/Pheno-Ranker-1.09.tar.gz",
              "02504c0559c6e934718a928e1641a3c3dbf4c7d4ba3d00c59b989b4c804db1c8"),
    "convert": ("https://cpan.metacpan.org/authors/id/M/MR/MRUEDA/Convert-Pheno-0.35.tar.gz",
                "e39cfd33b4c297ef1f16c27588915a32463dc4d8d9d7ae1c57981bfd7e44be0a"),
    "clarid": ("https://cpan.metacpan.org/authors/id/M/MR/MRUEDA/ClarID-Tools-0.04.tar.gz",
               "3a99768d3590a82ac04d95d3637b85e47ee08d9f12aff2abadb2ec7aadf3fcdd"),
    "net_idn": ("https://github.com/ernix/Net-IDN-Encode/archive/3ebe6f2e239b470efcb64a044edc8202798188af.tar.gz",
                "58772f38115f5a15b22d622e144200b0d9715c53560b229048d0a5f541eef4c7"),
}
TOOLS = {"pheno-ranker": "1.09", "convert-pheno": "0.35", "clarid-tools": "0.04"}


def fetch_source(kind, work, sources):
    url, digest = SOURCES[kind]
    archive = sources / url.rsplit("/", 1)[1]
    subprocess.run(["curl", "--fail", "--location", "--retry", "4", url,
                    "--output", str(archive)], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Checksum mismatch for {kind}")
    with tarfile.open(archive) as packed:
        packed.extractall(work, filter="data")
    directory = ("Net-IDN-Encode-3ebe6f2e239b470efcb64a044edc8202798188af"
                 if kind == "net_idn" else archive.name.removesuffix(".tar.gz"))
    return work / directory


def test_relocated(output, fixture, work):
    # Move, rather than copy, so the original build prefix cannot mask mistakes.
    relocated = work / "relocated runtime with spaces"
    shutil.move(output, relocated)
    home = work / "clean home"
    home.mkdir()
    env = {"PATH": "", "HOME": str(home), "LANG": "C.UTF-8"}
    if os.name == "nt":
        env.update({key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ})
        env.update(USERPROFILE=str(home), TEMP=str(home), TMP=str(home))
    try:
        result = work / "matrix.txt"
        command = [str(relocated / "bin/pheno-ranker")]
        if os.name == "nt":
            command.insert(0, str(relocated / "perl/bin/perl.exe"))
            env["PHENO_RANKER_INLINE_DIR"] = str(relocated / "inline")
            env["PATH"] = str(relocated / "perl/bin")
        subprocess.run([*command, "--reference", str(fixture),
                        "--out-file", str(result), "--no-color"],
                       cwd=home, env=env, check=True, timeout=120)
        if not result.is_file() or not result.stat().st_size:
            raise RuntimeError("Relocated Pheno-Ranker produced no matrix")
        from preparation_probe import check
        check(relocated, work / "preparation probe", env)
    finally:
        shutil.move(relocated, output)


def vendor_macos(output, executables=None):
    """Copy non-system dylibs, rewrite relative load paths, then ad-hoc sign."""
    binaries = [*(executables if executables is not None else [output / "perl/bin/perl"]), *output.rglob("*.bundle"),
                *output.rglob("*.dylib"), *output.rglob("*.so")]
    seen = set()
    for binary in binaries:
        if binary in seen or any(part.endswith(".dSYM") for part in binary.parts):
            continue
        seen.add(binary)
        binary.chmod(binary.stat().st_mode | 0o200)
        listing = subprocess.check_output(["otool", "-L", str(binary)], text=True)
        for line in listing.splitlines()[1:]:
            library = line.strip().split(" (", 1)[0]
            if not library.startswith("/") or library.startswith(("/usr/lib/", "/System/Library/")):
                continue
            source = Path(library)
            target = output / "lib" / source.name
            if source.resolve() != target.resolve() and not target.exists():
                shutil.copy2(source, target)
                binaries.append(target)
            relative = os.path.relpath(target, binary.parent)
            subprocess.run(["install_name_tool", "-change", library,
                            "@loader_path/" + relative, str(binary)], check=True)
        if binary.suffix == ".dylib":
            subprocess.run(["install_name_tool", "-id", "@loader_path/" + binary.name, str(binary)], check=True)
    for binary in seen:
        subprocess.run(["codesign", "--force", "--sign", "-", str(binary)], check=True)


def retain_notices(output, distributions):
    for source in distributions:
        destination = output / "licenses" / source.name
        destination.mkdir(parents=True)
        for name in ("LICENSE", "README", "META.json"):
            if (source / name).is_file():
                shutil.copy2(source / name, destination / name)


def write_manifest(output, perl_version):
    sources = output / "sources"
    manifest = {"perl": perl_version, "tools": TOOLS, "source": "CPAN",
                "platform": sys.platform, "architecture": platform.machine(),
                "verification": "relocated cohort CLI, CSV-to-BFF terminology mapping, ClarID human/stub round trips; clean environment",
                "licensing": "Software notices retained under licenses; vocabulary redistribution review required before release",
                "dependency_policy": "CPAN dependencies resolved at build time; source archives retained",
                "sources": {p.relative_to(sources).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sources.rglob("*") if p.is_file()},
                "runtime_sha256": {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in output.rglob("*") if p.is_file()}}
    (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform not in {"linux", "darwin"}:
        parser.error("Use build_windows_pheno.py on Windows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "sources"
    sources.mkdir()
    with tempfile.TemporaryDirectory(prefix="cohortome-perl-") as temp:
        work = Path(temp)
        perl_source = fetch_source("perl", work, sources)
        cpanm_source = fetch_source("cpanm", work, sources)
        pheno_source = fetch_source("pheno", work, sources)
        convert_source = fetch_source("convert", work, sources)
        clarid_source = fetch_source("clarid", work, sources)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("PERL", "PHENO_RANKER_", "LD_LIBRARY_PATH"))}
        env.update(HOME=str(work), PERL_CPANM_HOME=str(work / "cpanm"))
        prefix = output / "perl"
        subprocess.run(["sh", "Configure", "-des", f"-Dprefix={prefix}",
                        "-Duserelocatableinc", "-Duse64bitall"], cwd=perl_source, env=env, check=True)
        subprocess.run(["make", f"-j{min(os.cpu_count() or 2, 8)}"], cwd=perl_source, env=env, check=True)
        subprocess.run(["make", "install"], cwd=perl_source, env=env, check=True)
        perl = prefix / "bin/perl"
        env["PATH"] = str(prefix / "bin") + os.pathsep + env.get("PATH", "")
        subprocess.run([str(perl), str(cpanm_source / "bin/cpanm"), "--notest",
                        "--mirror", "https://cpan.metacpan.org", "--mirror-only",
                        "--save-dists", str(sources), "File::HomeDir", str(pheno_source),
                        str(convert_source), str(clarid_source)],
                       cwd=work, env=env, check=True)
        retain_notices(output, [pheno_source, convert_source, clarid_source])
        env["PHENO_RANKER_INLINE_DIR"] = str(output / "inline")
        subprocess.run([str(perl), "-MPheno::Ranker::Metrics", "-e",
                        "die 'Bad metric' unless Pheno::Ranker::Metrics::hd_fast('01','11') == 1"],
                       cwd=work, env=env, check=True)
        scratch = output / "inline/build"
        if scratch.exists():
            shutil.rmtree(scratch)
        # Same Linux library policy as Pheno-Ranker's desktop staging script.
        libraries = output / "lib"
        libraries.mkdir()
        for binary in ([perl, *prefix.rglob("*.so"), *(output / "inline").rglob("*.so")] if sys.platform == "linux" else []):
            linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=False)
            for line in linked.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 3 and fields[1] == "=>" and fields[2].startswith("/"):
                    library = Path(fields[2])
                    if library.name.startswith(("libssl.so", "libcrypto.so", "libexpat.so", "libbz2.so", "libz.so")):
                        shutil.copy2(library, libraries / library.name)
        (output / "bin").mkdir()
        for tool in TOOLS:
            launcher = output / "bin" / tool
            launcher.write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "${0%/*}/.." && pwd)
unset PERL5LIB PERLLIB PERL5OPT
export PHENO_RANKER_INLINE_DIR="$root/inline"
export LD_LIBRARY_PATH="$root/lib"
exec "$root/perl/bin/perl" "$root/perl/bin/TOOL_NAME" "$@"
'''.replace("TOOL_NAME", tool), encoding="utf-8")
            launcher.chmod(0o755)
        if sys.platform == "darwin":
            vendor_macos(output)
        test_relocated(output, pheno_source / "t/data/individuals.json", work)
        write_manifest(output, "5.42.3")
    shutil.make_archive(str(output), "gztar", root_dir=output.parent, base_dir=output.name)
    print(f"PASS: CPAN runtime built and relocated: {output}")


if __name__ == "__main__":
    main()
