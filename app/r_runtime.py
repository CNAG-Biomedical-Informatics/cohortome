"""Shared R executable discovery and analysis package readiness."""
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
import time

from app.env import app_env

REQUIREMENTS = {
    "transcriptomics_limma_voom_differential_expression": ("limma", "edgeR", "jsonlite"),
    "transcriptomics_deseq2_differential_expression": ("DESeq2", "apeglm", "jsonlite"),
    "transcriptomics_hallmark_pathway_enrichment": ("DESeq2", "apeglm", "fgsea", "msigdbr", "ggplot2", "jsonlite"),
    "transcriptomics_signature": ("DESeq2", "apeglm", "fgsea", "msigdbr", "ggplot2", "jsonlite"),
    "methylation_qc_pca": ("jsonlite",),
    "methylation_limma_differential_methylation": ("limma", "jsonlite"),
    "quantitative_assay_wilcoxon_comparison": ("jsonlite",),
}


def rscript_binary():
    configured = app_env("COHORTOME_RSCRIPT_BIN", "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    return shutil.which("Rscript")


@lru_cache(maxsize=8)
def _installed_packages(binary, minute):
    packages = sorted({p for values in REQUIREMENTS.values() for p in values})
    expression = 'p <- c(' + ','.join('"' + p + '"' for p in packages) + ');'
    expression += 'cat("COHORTOME_R_PACKAGES=", paste(p[vapply(p, requireNamespace, logical(1), quietly=TRUE)], collapse=","), "\\n", sep="")'
    result = subprocess.run([binary, "--vanilla", "-e", expression], capture_output=True,
                            text=True, check=True, timeout=30)
    for line in result.stdout.splitlines():
        if line.startswith("COHORTOME_R_PACKAGES="):
            return set(filter(None, line.partition("=")[2].split(",")))
    raise ValueError("Missing R package probe result")


def rscript_unavailable_reason(runner_ref):
    binary = rscript_binary()
    if not binary:
        return "Rscript is not available on this installation."
    required = REQUIREMENTS.get(runner_ref, ())
    if not required:
        return ""
    try:
        installed = _installed_packages(binary, int(time.monotonic() // 60))
    except (OSError, ValueError, subprocess.SubprocessError):
        return "Could not verify the R analysis packages on this installation."
    missing = [p for p in required if p not in installed]
    return "Missing R packages: " + ", ".join(missing) + "." if missing else ""
