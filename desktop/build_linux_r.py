"""Stage an installed Linux R and selected packages; never modify the host installation."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

PROBE = '''
stopifnot(normalizePath(R.home()) == normalizePath(Sys.getenv("R_HOME")))
stopifnot(all(startsWith(normalizePath(.libPaths()), normalizePath(R.home()))))
set.seed(42)
counts <- matrix(rnbinom(800, mu=100, size=5), nrow=100)
group <- factor(rep(c("A", "B"), each=4))
y <- edgeR::calcNormFactors(edgeR::DGEList(counts))
design <- model.matrix(~group)
v <- limma::voom(y, design, plot=FALSE)
fit <- limma::eBayes(limma::lmFit(v, design))
result <- limma::topTable(fit, coef=2, number=Inf)
stopifnot(nrow(result)==100, all(is.finite(result$P.Value)))
svg("probe.svg"); plot(result$logFC, -log10(result$P.Value)); dev.off()
png("probe.png"); plot(result$logFC, -log10(result$P.Value)); dev.off()
jsonlite::write_json(list(genes=nrow(result), packages=as.list(sapply(
 c("limma","edgeR","jsonlite"), function(p) as.character(packageVersion(p))))), "probe.json")
'''

EXTENDED_PROBE = '''
set.seed(43)
counts <- matrix(rnbinom(2400, mu=100, size=5), nrow=300)
rownames(counts) <- paste0("gene", seq_len(nrow(counts)))
group <- factor(rep(c("A", "B"), each=4))
dds <- DESeq2::DESeqDataSetFromMatrix(counts, data.frame(group), ~group)
dds <- DESeq2::DESeq(dds, quiet=TRUE)
res <- DESeq2::lfcShrink(dds, coef=2, type="apeglm")
stopifnot(nrow(res)==300, any(is.finite(res$log2FoldChange)))
stats <- setNames(rnorm(300), rownames(counts))
pathways <- list(synthetic_one=names(stats)[1:25], synthetic_two=names(stats)[26:60])
enriched <- fgsea::fgseaMultilevel(pathways, stats, minSize=10, maxSize=100, nproc=1)
stopifnot(nrow(enriched)==2, all(is.finite(enriched$pval)))
ggplot2::ggsave("extended.png", ggplot2::ggplot(data.frame(x=stats),
 ggplot2::aes(x=x)) + ggplot2::geom_histogram(bins=20), width=5, height=4)
stopifnot(requireNamespace("msigdbr", quietly=TRUE))
# No MSigDB gene sets are fetched or redistributed by this synthetic test.
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extended", action="store_true", help="Include DESeq2, apeglm and pathway packages")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("This builder targets Linux")
    rscript = shutil.which("Rscript")
    if not rscript:
        parser.error("Install R, limma, edgeR and jsonlite on the build host first")
    # Query only package metadata, never workspace inputs or user profiles.
    expression = '''
required <- c("limma","edgeR","jsonlite")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]
if (length(missing)) stop("R packages unavailable: ", paste(missing, collapse=", "))
ip <- installed.packages()
deps <- unique(c(required, unlist(tools::package_dependencies(required, ip,
  which=c("Depends","Imports","LinkingTo"), recursive=TRUE))))
deps <- setdiff(deps, "R")
packages <- lapply(deps, function(p) list(name=p, version=as.character(packageVersion(p)), path=find.package(p)))
cat(jsonlite::toJSON(list(home=R.home(), share=R.home("share"), include=R.home("include"),
 doc=R.home("doc"), version=as.character(getRversion()), packages=packages), auto_unbox=TRUE))
'''
    if args.extended:
        expression = expression.replace('required <- c("limma","edgeR","jsonlite")',
            'required <- c("limma","edgeR","jsonlite","DESeq2","apeglm","fgsea","msigdbr","ggplot2")')
    metadata = json.loads(subprocess.check_output([rscript, "--vanilla", "-e", expression], text=True))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rhome = output / "R"
    shutil.copytree(metadata["home"], rhome, symlinks=False, ignore=shutil.ignore_patterns("site-library"))
    for name in ("share", "include", "doc"):
        if not (rhome / name).exists():
            shutil.copytree(metadata[name], rhome / name, symlinks=False)
    for package in metadata["packages"]:
        target = rhome / "library" / package["name"]
        if not target.exists():
            shutil.copytree(package["path"], target, symlinks=False)
    # Replace distribution-specific paths and startup configuration.
    (rhome / "etc/Renviron").write_text(
        "R_LIBS_USER=NULL\nR_LIBS_SITE=NULL\nEDITOR=vi\nPAGER=cat\nR_PAPERSIZE=letter\n", encoding="utf-8")
    for name in ("Renviron.site", "Rprofile.site"):
        (rhome / "etc" / name).write_text("", encoding="utf-8")
    (rhome / "bin/R").write_text('#!/bin/sh\nexec "$R_HOME/bin/exec/R" "$@"\n', encoding="utf-8")
    (rhome / "bin/R").chmod(0o755)
    libraries = output / "lib"
    libraries.mkdir()
    (output / "bin").mkdir()
    # R uses rm to remove its temporary directory on normal shutdown.
    shutil.copy2("/bin/rm", output / "bin/rm")
    system = ("libc.so", "libm.so", "libpthread.so", "libdl.so", "librt.so", "ld-linux")
    for binary in [output / "bin/rm", rhome / "bin/exec/R", rhome / "bin/Rscript", *rhome.rglob("*.so")]:
        linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
        if "not found" in linked.stdout:
            raise RuntimeError("Unresolved R runtime library")
        for line in linked.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[1] == "=>" and fields[2].startswith("/"):
                library = Path(fields[2])
                if not library.name.startswith(system):
                    shutil.copy2(library, libraries / library.name)
    launcher = output / "bin/Rscript"
    launcher.write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "${0%/*}/.." && pwd)
export R_HOME="$root/R"
export RHOME="$R_HOME"
export PATH="$root/bin"
export R_SHARE_DIR="$R_HOME/share"
export R_INCLUDE_DIR="$R_HOME/include"
export R_DOC_DIR="$R_HOME/doc"
export R_LIBS="$R_HOME/library"
export R_LIBS_SITE=NULL R_LIBS_USER=NULL
export R_ENVIRON_USER=/dev/null R_PROFILE_USER=/dev/null
export LD_LIBRARY_PATH="$root/lib:$R_HOME/lib"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
exec "$R_HOME/bin/Rscript" "$@"
''', encoding="utf-8")
    launcher.chmod(0o755)
    with tempfile.TemporaryDirectory(prefix="cohortome-r-check-") as temporary:
        work = Path(temporary)
        relocated = work / "runtime with spaces"
        shutil.move(output, relocated)
        try:
            subprocess.run([str(relocated / "bin/Rscript"), "--vanilla", "-e", PROBE + (EXTENDED_PROBE if args.extended else "")],
                           cwd=work, env={"PATH": "", "HOME": str(work), "LANG": "C.UTF-8"},
                           check=True, timeout=300 if args.extended else 120)
            if not all((work / name).is_file() and (work / name).stat().st_size
                       for name in ("probe.svg", "probe.png", "probe.json")):
                raise RuntimeError("R runtime probe did not produce its artifacts")
            if args.extended and not (work / "extended.png").stat().st_size:
                raise RuntimeError("Extended R probe did not produce its plot")
        finally:
            shutil.move(relocated, output)
    manifest = {"platform": "linux", "architecture": platform.machine(), "r": metadata["version"],
                "packages": {p["name"]: p["version"] for p in metadata["packages"]},
                "verification": "relocated TMM/voom/limma, JSON, PNG and SVG without host R/package paths" +
                    ("; DESeq2/apeglm, synthetic fgsea pathways and ggplot2 (no MSigDB data)" if args.extended else ""),
                "runtime_sha256": {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in output.rglob("*") if p.is_file()}}
    (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.make_archive(str(output), "gztar", root_dir=output.parent, base_dir=output.name)
    print(f"PASS: relocated R {metadata['version']} with limma/edgeR/jsonlite: {output}")


if __name__ == "__main__":
    main()
