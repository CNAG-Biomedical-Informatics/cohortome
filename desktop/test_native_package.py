"""Open the packaged native window with temporary state, then exit automatically."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--xvfb", action="store_true", help="Use a virtual display on Linux CI")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="cohortome-native-") as temporary:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("COHORTOME_", "LM_STUDIO_", "UVICORN_", "PYTHON", "PERL", "DYLD_"))}
        env.update(HOME=temporary, XDG_DATA_HOME=str(Path(temporary) / "data"),
                   XDG_CACHE_HOME=str(Path(temporary) / "cache"),
                   COHORTOME_DESKTOP_SMOKE_TEST="1", WEBKIT_DISABLE_DMABUF_RENDERER="1")
        command = [str(binary)]
        if args.xvfb:
            command = ["xvfb-run", "-a", *command]
        process = subprocess.Popen(command, cwd=temporary, env=env, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            output, _ = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
            raise RuntimeError("Native startup timed out:\n" + output) from None
        print(output)
        if process.returncode or "PASS: packaged native window loaded" not in output:
            raise RuntimeError(f"Native startup failed (exit {process.returncode})")


if __name__ == "__main__":
    main()
