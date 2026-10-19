"""Small, allowlisted software report. Never return command output or paths."""
from functools import lru_cache
from importlib import metadata
from pathlib import Path
import platform
import re
import shutil
import subprocess


PACKAGES = ("fastapi", "uvicorn", "duckdb", "numpy", "pydantic", "jinja2",
            "PyYAML", "itsdangerous", "python-dotenv", "redis", "rq", "pydicom", "umap-learn")
R_PACKAGES = ("limma", "edgeR", "DESeq2", "ggplot2")


def _command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=4,
                              check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _version(value):
    value = str(value).strip()
    return value if re.fullmatch(r"[0-9][0-9A-Za-z.+_-]{0,60}", value) else "Unknown"


@lru_cache(maxsize=1)
def version_report():
    root = Path(__file__).resolve().parent.parent
    try:
        source = (root / "pyproject.toml").read_text()
        app_version = re.search(r'^version\s*=\s*"([^"]+)"', source, re.M)
        app_version = _version(app_version.group(1)) if app_version else "Unknown"
    except OSError:
        app_version = "Unknown"
    revision = _command(["git", "-C", str(root), "rev-parse", "--short", "HEAD"]).strip()
    rows = {"COHORTome": app_version,
            "Source checkout revision": revision if re.fullmatch(r"[0-9a-f]{7,40}", revision) else "Unavailable",
            "Python": platform.python_version()}
    for package in PACKAGES:
        try:
            rows[package + (" (Python client)" if package == "redis" else "")] = _version(metadata.version(package))
        except metadata.PackageNotFoundError:
            rows[package] = "Not installed"
    rscript = shutil.which("Rscript")
    rows.update({name: "Unknown" if rscript else "Not installed" for name in ("R", *R_PACKAGES)})
    if rscript:
        expression = 'cat("R=", as.character(getRversion()), "\\n", sep="");'
        expression += 'for (p in c(' + ','.join('"' + p + '"' for p in R_PACKAGES) + ')) {v <- if (requireNamespace(p, quietly=TRUE)) as.character(packageVersion(p)) else "missing"; cat(p,"=",v,"\\n",sep="")}'
        for line in _command([rscript, "--vanilla", "-e", expression]).splitlines():
            name, _, value = line.partition("=")
            if name in ("R", *R_PACKAGES):
                rows[name] = "Not installed" if value == "missing" else _version(value)
    from app.pheno import PHENO_RANKER_BIN, pheno_ranker_command
    for name, executable in (("Pheno-Ranker", str(PHENO_RANKER_BIN) if PHENO_RANKER_BIN.is_file() else None),
                             ("ClarID tools (preparation tool)", shutil.which("clarid-tools"))):
        rows[name] = "Not found on web server"
        if executable:
            command = pheno_ranker_command() if name == "Pheno-Ranker" else [executable]
            output = _command([*command, "--version"])
            match = re.search(r"\b\d+\.\d+(?:[._]\d+)*(?:[-+][A-Za-z0-9.]+)?\b", output)
            rows[name] = _version(match.group()) if match else "Unknown"
    return {"components": rows, "note": "Web-server software only. External viewers, Redis server and separate workers are not probed. Checkout revision does not include uncommitted edits. No patient, user or deployment configuration is included."}
