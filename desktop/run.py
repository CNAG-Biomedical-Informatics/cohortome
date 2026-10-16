"""Launch the isolated Linux source preview; no deployment configuration is loaded."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ)
deps = ROOT / ".deps"
if deps.is_dir():
    env["PYTHONPATH"] = str(deps)
env["COHORTOME_DESKTOP_PYTHON"] = sys.executable
subprocess.run(["cargo", "build", "--offline", "--locked", "--manifest-path",
                str(ROOT / "desktop/Cargo.toml"), "--features", "custom-protocol"],
               cwd=ROOT, env=env, check=True)
raise SystemExit(subprocess.call([str(ROOT / "desktop/target/debug/cohortome-desktop")],
                                cwd=ROOT, env=env))
