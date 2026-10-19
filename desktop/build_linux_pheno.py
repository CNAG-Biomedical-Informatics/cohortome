"""Build and relocation-test a CPAN Pheno-Ranker runtime (Linux, Python 3.12)."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

SOURCES = {
    "perl": ("https://www.cpan.org/src/5.0/perl-5.42.3.tar.gz",
             "1137740985837b5cdf15f0cfab932279dcb4352f912fed6fc144e8b4f0823627"),
    "cpanm": ("https://cpan.metacpan.org/authors/id/M/MI/MIYAGAWA/App-cpanminus-1.7049.tar.gz",
              "b9ffb88e62a06aa91bd7d5a28ef6bdbb942608aea90e3969aa29b33640035214"),
    "pheno": ("https://cpan.metacpan.org/authors/id/M/MR/MRUEDA/Pheno-Ranker-1.09.tar.gz",
              "02504c0559c6e934718a928e1641a3c3dbf4c7d4ba3d00c59b989b4c804db1c8"),
}


def fetch_source(kind, work, sources):
    url, digest = SOURCES[kind]
    archive = sources / url.rsplit("/", 1)[1]
    subprocess.run(["curl", "--fail", "--location", "--retry", "4", url,
                    "--output", str(archive)], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Checksum mismatch for {kind}")
    with tarfile.open(archive) as packed:
        packed.extractall(work, filter="data")
    return work / archive.name.removesuffix(".tar.gz")


def test_relocated(output, fixture, work):
    # Move, rather than copy, so the original build prefix cannot mask mistakes.
    relocated = work / "relocated runtime with spaces"
    shutil.move(output, relocated)
    home = work / "clean home"
    home.mkdir()
    env = {"PATH": "", "HOME": str(home), "LANG": "C.UTF-8"}
    try:
        result = work / "matrix.txt"
        subprocess.run([str(relocated / "bin/pheno-ranker"), "--reference", str(fixture),
                        "--out-file", str(result), "--no-color"],
                       cwd=home, env=env, check=True, timeout=120)
        if not result.is_file() or not result.stat().st_size:
            raise RuntimeError("Relocated Pheno-Ranker produced no matrix")
    finally:
        shutil.move(relocated, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.uname().sysname != "Linux":
        parser.error("This first runtime builder targets Linux only")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "sources"
    sources.mkdir()
    with tempfile.TemporaryDirectory(prefix="cohortome-perl-") as temp:
        work = Path(temp)
        perl_source = fetch_source("perl", work, sources)
        cpanm_source = fetch_source("cpanm", work, sources)
        pheno_source = fetch_source("pheno", work, sources)
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
                        "--save-dists", str(sources), "File::HomeDir", str(pheno_source)],
                       cwd=work, env=env, check=True)
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
        for binary in [perl, *prefix.rglob("*.so"), *(output / "inline").rglob("*.so")]:
            linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=False)
            for line in linked.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 3 and fields[1] == "=>" and fields[2].startswith("/"):
                    library = Path(fields[2])
                    if library.name.startswith(("libssl.so", "libcrypto.so", "libexpat.so", "libbz2.so", "libz.so")):
                        shutil.copy2(library, libraries / library.name)
        launcher = output / "bin/pheno-ranker"
        launcher.parent.mkdir()
        launcher.write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "${0%/*}/.." && pwd)
unset PERL5LIB PERLLIB PERL5OPT
export PHENO_RANKER_INLINE_DIR="$root/inline"
export LD_LIBRARY_PATH="$root/lib"
exec "$root/perl/bin/perl" "$root/perl/bin/pheno-ranker" "$@"
''', encoding="utf-8")
        launcher.chmod(0o755)
        test_relocated(output, pheno_source / "t/data/individuals.json", work)
        manifest = {"perl": "5.42.3", "pheno_ranker": "1.09", "source": "CPAN",
                    "platform": "linux", "architecture": platform.machine(),
                    "verification": "relocated cohort CLI with empty PATH and fresh HOME",
                    "dependency_policy": "CPAN dependencies resolved at build time; source archives retained",
                    "sources": {str(p.relative_to(sources)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sources.rglob("*") if p.is_file()}}
        manifest['runtime_sha256'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in output.rglob('*') if p.is_file()}
        (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    shutil.make_archive(str(output), "gztar", root_dir=output.parent, base_dir=output.name)
    print(f"PASS: CPAN runtime built and relocated: {output}")


if __name__ == "__main__":
    main()
