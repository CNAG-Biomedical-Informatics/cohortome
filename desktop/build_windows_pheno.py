"""Stage Strawberry Perl and checksum-verified CPAN Pheno-Ranker on a clean CI host."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from build_unix_pheno import fetch_source, test_relocated, write_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This builder requires Windows and Strawberry Perl")
    perl = shutil.which("perl")
    compiler = shutil.which("gcc")
    if not perl or not compiler:
        parser.error("Set up Strawberry Perl with its compiler first")
    # Ask Perl itself: setup actions may place wrapper scripts on PATH.
    perl = subprocess.check_output([perl, "-e", "print $^X"], text=True).strip()
    prefix = Path(perl).resolve().parent.parent
    marker = prefix.parent / "portable.perl"
    if not marker.is_file():
        raise RuntimeError("Strawberry portable.perl marker is required")
    version = subprocess.check_output([perl, "-e", 'printf "%vd", $^V'], text=True).strip()
    if not version.startswith("5.42."):
        raise RuntimeError("Expected Strawberry Perl 5.42.x")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "sources"
    sources.mkdir()
    with tempfile.TemporaryDirectory(prefix="cohortome-strawberry-") as temporary:
        work = Path(temporary)
        cpanm = fetch_source("cpanm", work, sources)
        pheno = fetch_source("pheno", work, sources)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PERL", "PHENO_RANKER_"))}
        env.update(PERL_CPANM_HOME=str(work / "cpanm"))
        subprocess.run([perl, str(cpanm / "bin/cpanm"), "--notest", "--mirror",
                        "https://cpan.metacpan.org", "--mirror-only", "--save-dists", str(sources),
                        "File::HomeDir", str(pheno)], cwd=work, env=env, check=True)
        staged = output / "perl"
        for name in ("bin", "lib", "site", "vendor"):
            if (prefix / name).is_dir():
                shutil.copytree(prefix / name, staged / name)
        shutil.copy2(marker, output / "portable.perl")
        for dll in Path(compiler).resolve().parent.glob("*.dll"):
            shutil.copy2(dll, staged / "bin" / dll.name)
        # CPAN installs commands under site/bin on Strawberry; use one fixed location.
        candidates = [staged / "site/bin/pheno-ranker", staged / "bin/pheno-ranker"]
        script = next((p for p in candidates if p.is_file()), None)
        if script is None:
            raise RuntimeError("CPAN did not install the Pheno-Ranker script")
        if script != staged / "bin/pheno-ranker":
            shutil.copy2(script, staged / "bin/pheno-ranker")
        env["PHENO_RANKER_INLINE_DIR"] = str(output / "inline")
        subprocess.run([str(staged / "bin/perl.exe"), "-MPheno::Ranker::Metrics", "-e",
                        "die 'Bad metric' unless Pheno::Ranker::Metrics::hd_fast('01','11') == 1"],
                       cwd=work, env=env, check=True)
        scratch = output / "inline/build"
        if scratch.exists():
            shutil.rmtree(scratch)
        (output / "bin").mkdir()
        subprocess.run([compiler, "-municode", "-O2", "-static-libgcc",
                        str(Path(__file__).with_name("pheno_launcher_windows.c")),
                        "-o", str(output / "bin/pheno-ranker.exe")], check=True)
        test_relocated(output, pheno / "t/data/individuals.json", work)
        write_manifest(output, version)
    shutil.make_archive(str(output), "zip", root_dir=output.parent, base_dir=output.name)
    print("PASS: Strawberry/CPAN runtime built and relocated")


if __name__ == "__main__":
    main()
