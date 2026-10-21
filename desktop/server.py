"""Private desktop backend, shared by the source preview and packaged app."""
import argparse
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def initialize_windows_blas():
    # First loading BLAS while watch_parent blocks on piped stdin can deadlock
    # on Windows (numpy/numpy#24290). Load it before any parent-reader thread.
    # SciPy is optional in bundles without UMAP; broken installations still fail.
    if sys.platform == "win32" and importlib.util.find_spec("scipy") is not None:
        importlib.import_module("scipy.linalg")


def runtime_directory():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--diagnostic-stacks", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.diagnostic_stacks:
        import faulthandler
        faulthandler.dump_traceback_later(60, repeat=True)
    if args.runtime_dir:
        if not args.runtime_dir.is_absolute():
            parser.error("--runtime-dir must be absolute")
        return args.runtime_dir.resolve()
    app_dir = "org.cnag.cohortome.preview" if getattr(sys, "frozen", False) else "org.cnag.cohortome.source-preview"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support" / app_dir
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / app_dir
    return (Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / app_dir).resolve()


def configure_environment(runtime):
    for name in list(os.environ):
        if name.startswith(("COHORTOME_", "LM_STUDIO_", "UVICORN_")):
            del os.environ[name]
    os.environ.update(COHORTOME_RUNTIME_ROOT=str(runtime), COHORTOME_AUTH_MODE="none",
                      COHORTOME_SESSION_SECRET=secrets.token_urlsafe(32),
                      COHORTOME_JOBS_REDIS_URL="redis://127.0.0.1:1/0",
                      COHORTOME_JOBS_BACKEND="local",
                      COHORTOME_DESKTOP_MODE="true",
                      LM_STUDIO_ENABLED="false")
    if getattr(sys, 'frozen', False):
        tools = Path(sys.executable).resolve().parent / 'runtimes/perl/bin'
        r_runtime = tools.parents[1] / 'r'
        entrypoint = 'R/bin/x64/Rscript.exe' if sys.platform == 'win32' else 'bin/Rscript'
        os.environ['COHORTOME_RSCRIPT_BIN'] = str(r_runtime / entrypoint)
        # The Windows executable has no wrapper. Keep every platform isolated
        # from a user's R installation, startup files and package libraries.
        os.environ.update(R_HOME=str(r_runtime / 'R'), RHOME=str(r_runtime / 'R'),
                          R_LIBS=str(r_runtime / 'R/library'), R_LIBS_USER='NULL',
                          R_LIBS_SITE='NULL', R_ENVIRON_USER=os.devnull,
                          R_PROFILE_USER=os.devnull,
                          R_SHARE_DIR=str(r_runtime / 'R/share'),
                          R_INCLUDE_DIR=str(r_runtime / 'R/include'),
                          R_DOC_DIR=str(r_runtime / 'R/doc'))
        os.environ['NUMBA_CACHE_DIR'] = str(runtime / 'cache/numba')
        os.environ['NUMBA_NUM_THREADS'] = '1'
        # Never fall back to a developer checkout or host tools in a package.
        os.environ['COHORTOME_PHENO_RANKER_BIN'] = str(tools / 'pheno-ranker')
        os.environ['COHORTOME_CONVERT_PHENO_BIN'] = str(tools / 'convert-pheno')
        os.environ['COHORTOME_CLARID_TOOLS_BIN'] = str(tools / 'clarid-tools')
        os.environ['COHORTOME_PREPARATION_PERL_BIN'] = str(tools.parent / ('perl/bin/perl.exe' if os.name == 'nt' else 'perl/bin/perl'))
        if os.name == 'nt':
            os.environ['COHORTOME_PHENO_RANKER_PERL_BIN'] = str(tools.parent / 'perl/bin/perl.exe')
            os.environ['PHENO_RANKER_INLINE_DIR'] = str(tools.parent / 'inline')
            os.environ['PATH'] = str(tools.parent / 'perl/bin') + os.pathsep + os.environ.get('PATH', '')
            for name in ('PERL5LIB', 'PERLLIB', 'PERL5OPT'):
                os.environ.pop(name, None)
    sys.path.insert(0, str(ROOT))
    from app.analysis_resources import THREAD_ENV
    os.environ.update(THREAD_ENV)


def main():
    runtime = runtime_directory()
    configure_environment(runtime)
    initialize_windows_blas()
    import uvicorn
    from starlette.responses import PlainTextResponse, RedirectResponse
    from starlette.requests import Request
    from app.auth import create_local_user, find_local_user
    from app.main import app
    from app.state_io import atomic_write_json
    from app.lm import initialize_desktop_default_provider

    initialize_desktop_default_provider()

    registry = runtime / "state/datasets/registry.json"
    if not registry.exists():
        seed = json.loads((ROOT / "config/datasets/registry.json").read_text())
        atomic_write_json(registry, [item for item in seed if item["dataset_id"] in
                                   {"default", "synthetic-autoimmune-demo"}], file_mode=0o600)
    if not find_local_user("local"):
        create_local_user(username="local", password=secrets.token_urlsafe(32),
                          role="admin", display_name="Local owner")

    # Inside the existing SessionMiddleware, identify the same owner for admin routes.
    class LocalOwner:
        def __init__(self, app): self.app = app
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope["session"].update(username="local", role="admin", display_name="Local owner")
                headers = []
                for key, value in scope["headers"]:
                    if key == b"x-user-id": continue
                    if key == b"cookie":
                        value = b"; ".join(part.strip() for part in value.split(b";")
                                           if not part.strip().startswith(b"pn_user_id="))
                    headers.append((key, value))
                scope["headers"] = headers
            await self.app(scope, receive, send)
    from starlette.middleware import Middleware
    app.user_middleware.append(Middleware(LocalOwner))

    token = secrets.token_urlsafe(32)
    bootstrap = secrets.token_urlsafe(32)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"

    async def protected(scope, receive, send):
        nonlocal bootstrap
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        request = Request(scope)
        if request.headers.get("host") != origin.removeprefix("http://"):
            response = PlainTextResponse("Invalid local host", status_code=403)
        elif request.headers.get("origin") not in (None, origin):
            response = PlainTextResponse("Invalid local origin", status_code=403)
        elif bootstrap and request.url.path == "/desktop/open" and secrets.compare_digest(request.query_params.get("key", ""), bootstrap):
            bootstrap = None
            response = RedirectResponse("/", status_code=303)
            response.set_cookie("cohortome_desktop", token, httponly=True, samesite="strict")
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
        elif not secrets.compare_digest(request.cookies.get("cohortome_desktop", ""), token):
            response = PlainTextResponse("Open this workspace from COHORTome Desktop.", status_code=403)
        else:
            await app(scope, receive, send)
            return
        await response(scope, receive, send)

    server = uvicorn.Server(uvicorn.Config(protected, log_level="warning", access_log=False))
    def watch_parent():
        while os.read(0, 1):
            pass
        server.should_exit = True
    threading.Thread(target=watch_parent, daemon=True).start()

    async def serve():
        from app import local_jobs
        local_jobs.start()
        try:
            task = asyncio.create_task(server.serve(sockets=[listener]))
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Desktop backend did not start")
                await asyncio.sleep(.05)
            print(json.dumps({"url": f"{origin}/desktop/open?key={bootstrap}"}), flush=True)
            await task
        finally:
            local_jobs.stop()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
