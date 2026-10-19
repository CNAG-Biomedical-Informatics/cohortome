"""Stage and relocation-test macOS/Windows R; run on a clean CI build host."""
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

from build_linux_r import PROBE, EXTENDED_PROBE
from build_unix_pheno import vendor_macos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-installed", action="store_true",
                        help="Run statistical probes against the build host before packaging")
    args = parser.parse_args()
    if sys.platform not in {"darwin", "win32"}:
        parser.error("Use build_linux_r.py on Linux")
    binary = shutil.which("Rscript")
    if not binary:
        parser.error("Install R and the analysis packages first")
    if args.check_installed:
        with tempfile.TemporaryDirectory(prefix="cohortome-r-installed-") as temporary:
            work = Path(temporary)
            script = work / "probe.R"
            # The build host intentionally has external package libraries;
            # retain the strict library-location assertions for relocation only.
            installed_probe = "set.seed(42)" + PROBE.split("set.seed(42)", 1)[1]
            script.write_text(installed_probe + EXTENDED_PROBE,
                              encoding="utf-8")
            subprocess.run([binary, "--vanilla", str(script)], cwd=work,
                           stdin=subprocess.DEVNULL, check=True, timeout=300)
        print("PASS: installed R statistical probes before relocation")
        return
    if args.output is None:
        parser.error("--output is required unless --check-installed is used")
    expression = '''
required <- c("limma","edgeR","jsonlite","DESeq2","apeglm","fgsea","msigdbr","ggplot2")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]
if (length(missing)) stop("Missing R packages: ", paste(missing, collapse=", "))
ip <- installed.packages()
deps <- setdiff(unique(c(required, unlist(tools::package_dependencies(required, ip,
 which=c("Depends","Imports","LinkingTo"), recursive=TRUE)))), "R")
packages <- lapply(deps, function(p) list(name=p, version=as.character(packageVersion(p)), path=find.package(p)))
cat(jsonlite::toJSON(list(home=R.home(), version=as.character(getRversion()), packages=packages), auto_unbox=TRUE))
'''
    # Avoid Windows Rscript command-line parsing of multiline/quoted -e input.
    with tempfile.TemporaryDirectory(prefix="cohortome-r-metadata-") as temporary:
        script = Path(temporary) / "metadata.R"
        script.write_text(expression, encoding="utf-8")
        metadata = json.loads(subprocess.check_output([binary, "--vanilla", str(script)], text=True))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rhome = output / "R"
    shutil.copytree(metadata["home"], rhome, symlinks=False,
                    ignore=shutil.ignore_patterns("library", "site-library", "*.dSYM"))
    # Retain base/recommended packages and choose each required package's
    # resolved version before copying (no deletion of read-only Windows files).
    packages = {p.name: p for p in (Path(metadata["home"]) / "library").iterdir() if p.is_dir()}
    packages.update({p["name"]: Path(p["path"]) for p in metadata["packages"]})
    for name, source in packages.items():
        shutil.copytree(source, rhome / "library" / name, symlinks=False,
                        ignore=shutil.ignore_patterns("*.dSYM"))
    for name in ("Renviron.site", "Rprofile.site"):
        (rhome / "etc" / name).write_text("", encoding="utf-8")
    if sys.platform == "darwin":
        (rhome / "etc/Renviron").write_text(
            "R_LIBS_USER=NULL\nR_LIBS_SITE=NULL\nEDITOR=vi\nPAGER=cat\nR_PAPERSIZE=letter\n", encoding="utf-8")
        (rhome / "bin/R").write_text('#!/bin/sh\nexec "$R_HOME/bin/exec/R" "$@"\n')
        (rhome / "bin/R").chmod(0o755)
        (output / "lib").mkdir()
        (output / "bin").mkdir()
        # copy2 also copies Apple's protected file flags; only bytes/mode are needed.
        shutil.copyfile("/bin/rm", output / "bin/rm")
        (output / "bin/rm").chmod(0o755)
        vendor_macos(output, [rhome / "bin/exec/R", rhome / "bin/Rscript"])
        launcher = output / "bin/Rscript"
        launcher.write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "${0%/*}/.." && pwd)
export R_HOME="$root/R" RHOME="$root/R"
export R_SHARE_DIR="$R_HOME/share" R_INCLUDE_DIR="$R_HOME/include" R_DOC_DIR="$R_HOME/doc"
export R_LIBS="$R_HOME/library" R_LIBS_USER=NULL R_LIBS_SITE=NULL
export R_ENVIRON_USER=/dev/null R_PROFILE_USER=/dev/null
export PATH="$root/bin" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
exec "$R_HOME/bin/Rscript" "$@"
''')
        launcher.chmod(0o755)
        entry = "bin/Rscript"
    else:
        # bin/Rscript.exe is Rfe.c's shell dispatcher (system(cmd)); use the
        # real executable so an isolated PATH does not require cmd.exe.
        entry = "R/bin/x64/Rscript.exe"
        if not (output / entry).is_file():
            raise RuntimeError("Expected the official Windows x64 Rscript executable")
    with tempfile.TemporaryDirectory(prefix="cohortome-native-r-", dir=output.parent) as temporary:
        work = Path(temporary)
        moved = work / "runtime with spaces"
        shutil.move(output, moved)
        try:
            env = {"PATH": "", "HOME": str(work), "LANG": "C.UTF-8",
                   "R_HOME": str(moved / "R"), "RHOME": str(moved / "R"),
                   "R_LIBS": str(moved / "R/library"), "R_LIBS_USER": "NULL", "R_LIBS_SITE": "NULL",
                   "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
            if sys.platform == "win32":
                env.update({k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ})
                env.update(USERPROFILE=str(work), TEMP=str(work), TMP=str(work))
            script = work / "probe.R"
            script.write_text(PROBE + EXTENDED_PROBE, encoding="utf-8")
            command = [str(moved / entry), "--verbose", "--vanilla", str(script)]
            try:
                subprocess.run(command, cwd=work, env=env, stdin=subprocess.DEVNULL,
                               check=True, timeout=300)
            except subprocess.CalledProcessError:
                if sys.platform == "win32":
                    # Diagnose without relaxing the required isolation test or
                    # turning a diagnostic success into a passing build.
                    system32 = Path(os.environ["SystemRoot"]) / "System32"
                    variants = {
                        "system shell restored": {**env, "COMSPEC": str(system32 / "cmd.exe")},
                        "system PATH restored": {**env, "COMSPEC": str(system32 / "cmd.exe"),
                                                 "PATH": str(system32)},
                        "bundled DLL PATH": {**env, "PATH": str(moved / "R/bin/x64")},
                        "host PATH only": {**env, "PATH": os.environ.get("PATH", "")},
                        "host variables, empty PATH": {**os.environ, **env},
                        "host environment, bundled R libraries": {**os.environ, **env,
                                                                 "PATH": os.environ.get("PATH", "")},
                    }
                    for label, diagnostic_env in variants.items():
                        print(f"DIAGNOSTIC: {label}", flush=True)
                        try:
                            result = subprocess.run(command, cwd=work, env=diagnostic_env,
                                                    stdin=subprocess.DEVNULL, timeout=120)
                            print(f"DIAGNOSTIC RESULT: {label}: {result.returncode}", flush=True)
                        except subprocess.TimeoutExpired:
                            print(f"DIAGNOSTIC RESULT: {label}: timed out", flush=True)
                    # Find which non-base host settings are necessary, without
                    # emitting environment values (which could contain secrets).
                    extras = {k: v for k, v in os.environ.items() if k not in env}
                    extras["PATH"] = os.environ.get("PATH", "")
                    candidates = list(extras)
                    width = max(1, len(candidates) // 2)
                    while candidates:
                        for offset in range(0, len(candidates), width):
                            removed = set(candidates[offset:offset + width])
                            trial = [k for k in candidates if k not in removed]
                            trial_env = {**env, **{k: extras[k] for k in trial}}
                            with (work / "diagnostic.log").open("w") as log:
                                try:
                                    result = subprocess.run(command, cwd=work, env=trial_env,
                                                            stdin=subprocess.DEVNULL, stdout=log,
                                                            stderr=log, timeout=60)
                                    passed = result.returncode == 0
                                except subprocess.TimeoutExpired:
                                    passed = False
                            print(f"ENV BISECT: removed {len(removed)} keys; passed={passed}", flush=True)
                            if passed:
                                candidates = trial
                                width = min(width, max(1, len(candidates) // 2))
                                break
                        else:
                            if width == 1:
                                break
                            width = max(1, width // 2)
                    print("REQUIRED HOST KEYS: " + ", ".join(candidates), flush=True)
                raise
            for name in ("probe.json", "probe.png", "probe.svg", "extended.png"):
                assert (work / name).stat().st_size, name
        finally:
            shutil.move(moved, output)
    manifest = {"platform": sys.platform, "architecture": platform.machine(), "r": metadata["version"],
                "entrypoint": entry,
                "packages": {p["name"]: p["version"] for p in metadata["packages"]},
                "verification": "relocated limma/voom, DESeq2/apeglm, synthetic fgsea, JSON/PNG/SVG; no MSigDB data",
                "runtime_sha256": {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in output.rglob("*") if p.is_file()}}
    (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.make_archive(str(output), "zip" if sys.platform == "win32" else "gztar",
                        root_dir=output.parent, base_dir=output.name)
    print(f"PASS: relocated {sys.platform} R {metadata['version']} and extended analysis packages")


if __name__ == "__main__":
    main()
