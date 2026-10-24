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
    parser.add_argument("--check-linux-warnings", action="store_true",
                        help="Reject missing GTK/GStreamer plugins and DRI3 warnings")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="cohortome-native-") as temporary:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("COHORTOME_", "LM_STUDIO_", "UVICORN_", "PYTHON", "PERL", "DYLD_"))}
        env.update(HOME=temporary, XDG_DATA_HOME=str(Path(temporary) / "data"),
                   XDG_CACHE_HOME=str(Path(temporary) / "cache"),
                   COHORTOME_DESKTOP_SMOKE_TEST="1", WEBKIT_DISABLE_DMABUF_RENDERER="1")
        if args.check_linux_warnings:
            env.pop('WEBKIT_DISABLE_DMABUF_RENDERER', None)
            env['GTK_MODULES'] = 'canberra-gtk-module'
        command = [str(binary)]
        if args.xvfb:
            command = ["xvfb-run", "-a", *command]
        process = subprocess.Popen(command, cwd=temporary, env=env, start_new_session=os.name != "nt",
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            output, _ = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
            raise RuntimeError("Native startup timed out:\n" + output) from None
        print(output)
        if process.returncode or "PASS: packaged native window loaded" not in output:
            raise RuntimeError(f"Native startup failed (exit {process.returncode})")
        if args.check_linux_warnings and any(message in output for message in (
            'Failed to load module "canberra-gtk-module"',
            'GStreamer element appsink not found', 'DRI3 error:',
        )):
            raise RuntimeError('AppImage startup reported missing plugins or unusable graphics.')


if __name__ == "__main__":
    main()
