"""Stage Strawberry Perl and checksum-verified CPAN Pheno-Ranker on a clean CI host."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from build_unix_pheno import TOOLS, fetch_source, retain_notices, test_relocated, write_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--perl", type=Path, required=True, help="Strawberry perl.exe selected by PowerShell")
    parser.add_argument("--compiler", type=Path, required=True, help="Strawberry gcc.exe selected by PowerShell")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This builder requires Windows and Strawberry Perl")
    perl = str(args.perl.absolute())
    compiler = str(args.compiler.absolute())
    if not args.perl.is_file():
        parser.error(f"Perl executable does not exist: {str(args.perl)!r}")
    if not args.compiler.is_file():
        parser.error(f"Compiler executable does not exist: {str(args.compiler)!r}")
    # Match Pheno-Ranker's successful Windows workflow: use the selected
    # executable's directory, not Perl's self-reported $^X installation path.
    prefix = Path(perl).absolute().parent.parent
    runtime_perl = prefix / "bin/perl.exe"
    version = subprocess.check_output([perl, "-e", 'printf "%vd", $^V'], text=True).strip()
    staged_version = subprocess.check_output([str(runtime_perl), "-e", 'printf "%vd", $^V'], text=True).strip()
    if version != staged_version:
        raise RuntimeError("Selected Perl and staged runtime differ")
    perl = str(runtime_perl)
    marker = prefix.parent / "portable.perl"
    if not marker.is_file():
        raise RuntimeError(f"Strawberry portable.perl marker is required: {marker}")
    if not version.startswith("5.42."):
        raise RuntimeError("Expected Strawberry Perl 5.42.x")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "sources"
    sources.mkdir()
    # Keep relocation on the output volume: cross-drive shutil.move falls
    # back to copy/delete, which fails on CPAN's read-only installed scripts.
    with tempfile.TemporaryDirectory(prefix="cohortome-strawberry-", dir=output.parent) as temporary:
        work = Path(temporary)
        cpanm = fetch_source("cpanm", work, sources)
        pheno = fetch_source("pheno", work, sources)
        convert = fetch_source("convert", work, sources)
        clarid = fetch_source("clarid", work, sources)
        net_idn = fetch_source("net_idn", work, sources)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PERL", "PHENO_RANKER_"))}
        env.update(PERL_CPANM_HOME=str(work / "cpanm"))
        env["PATH"] = os.pathsep.join([str(prefix / "site/bin"), str(prefix / "bin"),
                                      str(Path(compiler).parent), env.get("PATH", "")])
        # cpanm recognizes '.' as a local distribution; a drive-letter path
        # with backslashes can instead be parsed as a CPAN module name.
        # Same Perl 5.42 compatibility patch as Convert-Pheno Desktop, installed first.
        for source in (net_idn, pheno, convert, clarid):
            subprocess.run([perl, str(cpanm / "bin/cpanm"), "--notest", "--mirror",
                            "https://cpan.metacpan.org", "--mirror-only", "--save-dists", str(sources),
                            "File::HomeDir", "."], cwd=source, env=env, check=True)
        retain_notices(output, [pheno, convert, clarid, net_idn])
        staged = output / "perl"
        for name in ("bin", "lib", "site", "vendor"):
            if (prefix / name).is_dir():
                shutil.copytree(prefix / name, staged / name)
        shutil.copy2(marker, output / "portable.perl")
        for dll in Path(compiler).resolve().parent.glob("*.dll"):
            shutil.copy2(dll, staged / "bin" / dll.name)
        # CPAN installs commands under site/bin on Strawberry; use one fixed location.
        (output / "bin").mkdir()
        for tool in TOOLS:
            candidates = [staged / "site/bin" / tool, staged / "bin" / tool]
            script = next((p for p in candidates if p.is_file()), None)
            if script is None:
                raise RuntimeError(f"CPAN did not install {tool}")
            if script != staged / "bin" / tool:
                shutil.copy2(script, staged / "bin" / tool)
            shutil.copy2(script, output / "bin" / tool)
        env["PHENO_RANKER_INLINE_DIR"] = str(output / "inline")
        subprocess.run([str(staged / "bin/perl.exe"), "-MPheno::Ranker::Metrics", "-e",
                        "die 'Bad metric' unless Pheno::Ranker::Metrics::hd_fast('01','11') == 1"],
                       cwd=work, env=env, check=True)
        scratch = output / "inline/build"
        if scratch.exists():
            shutil.rmtree(scratch)
        test_relocated(output, pheno / "t/data/individuals.json", work)
        write_manifest(output, version)
    shutil.make_archive(str(output), "zip", root_dir=output.parent, base_dir=output.name)
    print("PASS: Strawberry/CPAN runtime built and relocated")


if __name__ == "__main__":
    main()
