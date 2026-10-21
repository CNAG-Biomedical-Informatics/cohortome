"""Resolve reviewed preparation CLIs for packaged and native deployments."""
from pathlib import Path
import shutil
import sys

from app.env import app_env

TOOLS = {"convert-pheno": "COHORTOME_CONVERT_PHENO_BIN",
         "clarid-tools": "COHORTOME_CLARID_TOOLS_BIN"}


def preparation_command(tool):
    variable = TOOLS[tool]
    configured = app_env(variable, "").strip()
    executable = configured or shutil.which(tool)
    if not executable or not Path(executable).is_file():
        return None
    # Unix bundles use their relocatable wrappers; Windows calls perl.exe directly.
    if sys.platform == "win32":
        configured_perl = app_env("COHORTOME_PREPARATION_PERL_BIN", "").strip()
        perl = configured_perl or shutil.which("perl")
        if not perl or not Path(perl).is_file():
            return None
        return [perl, executable]
    return [executable]
