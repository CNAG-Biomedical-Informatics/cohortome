"""Foreground native web/worker launcher; never prepares or imports datasets."""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def worker_command():
    # Keep Redis credentials out of the process command line.
    return [sys.executable, "-c", 'import os; from rq.cli import main; '
            'main(["worker", os.environ.get("COHORTOME_JOBS_QUEUE_NAME", "analysis"), '
            '"--url", os.environ.get("COHORTOME_JOBS_REDIS_URL", "redis://127.0.0.1:6379/0")])']


def configuration(path):
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise ValueError("Install Python dependencies first: python3 -m pip install -e .")
    if not path.is_file():
        raise ValueError("Copy native.env.example to native.env and edit it first.")
    if path.stat().st_mode & 0o077:
        raise ValueError("Configuration must be private: chmod 600 your-config-file")
    values = dotenv_values(path, interpolate=False)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("COHORTOME_", "LM_STUDIO_", "UVICORN_"))}
    env.update({k: v for k, v in values.items() if v is not None})
    raw = env.get("COHORTOME_RUNTIME_ROOT", "")
    runtime = Path(raw)
    if not raw or not runtime.is_absolute() or not runtime.is_dir():
        raise ValueError("Set COHORTOME_RUNTIME_ROOT to an existing absolute runtime directory. "
                         "No new runtime is created automatically.")
    env["COHORTOME_RUNTIME_ROOT"] = str(runtime.resolve())
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / ".deps"), str(ROOT)])
    perl = Path.home() / "perl5"
    if "PERL5LIB" not in values and (perl / "lib/perl5").is_dir():
        env["PERL5LIB"] = str(perl / "lib/perl5") + (
            os.pathsep + env["PERL5LIB"] if env.get("PERL5LIB") else "")
    if (perl / "bin").is_dir():
        env["PATH"] = str(perl / "bin") + os.pathsep + env.get("PATH", "")
    return env


def validate(env):
    mode = env.get("COHORTOME_AUTH_MODE", "")
    if mode not in {"local", "oidc", "none"}:
        raise ValueError("Set COHORTOME_AUTH_MODE explicitly to local, oidc, or none.")
    secret = env.get("COHORTOME_SESSION_SECRET", "")
    if mode != "none" and (len(secret) < 32 or secret.startswith("replace-")):
        raise ValueError("Set a persistent COHORTOME_SESSION_SECRET of at least 32 characters.")
    if mode == "oidc":
        for suffix in ("ISSUER", "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI"):
            if not env.get("COHORTOME_OIDC_" + suffix):
                raise ValueError("OIDC requires COHORTOME_OIDC_" + suffix)
    host = env.get("COHORTOME_HOST", "127.0.0.1")
    if mode == "none" and host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Network access requires local or OIDC authentication.")
    try:
        port = int(env.get("COHORTOME_PORT", "8001"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("COHORTOME_PORT must be an integer from 1 to 65535.")
    return host, port


def doctor(env):
    validate(env)
    missing = [name for name in ("uvicorn", "fastapi", "jinja2", "itsdangerous",
               "pydantic", "duckdb", "numpy", "yaml", "redis", "rq")
               if importlib.util.find_spec(name) is None]
    if missing:
        raise ValueError("Missing Python dependencies: " + ", ".join(missing))
    from redis import Redis
    try:
        client = Redis.from_url(env.get("COHORTOME_JOBS_REDIS_URL", "redis://127.0.0.1:6379/0"),
                                socket_connect_timeout=3, socket_timeout=3)
        try:
            client.ping()
        finally:
            client.close()
    except Exception:
        raise ValueError("Redis is unavailable. Check COHORTOME_JOBS_REDIS_URL; for a local "
                         "systemd installation, run sudo systemctl start redis-server.") from None
    print("OK: configuration, Python dependencies, Redis.", flush=True)
    checks = [
        ("R analysis packages", ["Rscript", "-e",
         'p <- c("jsonlite","limma","edgeR","DESeq2","apeglm","fgsea","msigdbr","ggplot2"); '
         'quit(status=if(all(vapply(p,requireNamespace,logical(1),quietly=TRUE))) 0 else 1)']),
    ]
    pheno = env.get("COHORTOME_PHENO_RANKER_BIN")
    if pheno:
        checks.append(("Pheno-Ranker Perl dependencies", ["perl", "-c", pheno]))
    else:
        print("WARNING: set COHORTOME_PHENO_RANKER_BIN to check your native Pheno-Ranker installation.")
    for label, command in checks:
        try:
            result = subprocess.run(command, env=env, cwd=ROOT, timeout=30,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        print(("OK: " if ok else "WARNING: unavailable or incomplete: ") + label, flush=True)
    if not shutil.which("jq", path=env.get("PATH")):
        print("WARNING: jq is missing; Pheno-Ranker requires it.")


def control_path(env):
    path = Path(env["COHORTOME_RUNTIME_ROOT"]) / ".native.sock"
    if len(os.fsencode(path)) > 103:
        raise ValueError("Runtime path is too long for the native control socket (maximum 90 bytes).")
    return path


def request(path, action):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(3)
        try:
            client.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError):
            print("Native launcher: stopped (independently started services are not managed).")
            return 1 if action == "status" else 0
        client.sendall(action.encode())
        print(client.recv(4096).decode())
    return 0


def serve(env):
    path = control_path(env)
    host, port = validate(env)
    with open(path.with_suffix(".lock"), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A native launcher already manages this runtime. Use make status.")
        doctor(env)
        try:
            probe = socket.create_server((host, port), family=socket.AF_INET6 if ":" in host else socket.AF_INET)
            probe.close()
        except OSError:
            raise ValueError("Cannot bind the configured address/port. Check for an existing web service.") from None
        children = {}
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            path.unlink(missing_ok=True)
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(path))
                path.chmod(0o600)
                server.listen(4)
                server.settimeout(0.5)
                commands = {
                    "web": [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
                    "worker": worker_command(),
                }
                for name, command in commands.items():
                    children[name] = subprocess.Popen(command, env=env, cwd=ROOT, start_new_session=True)
                print(f"Starting Uvicorn on {host}:{port} and the RQ worker. "
                      "Wait for their startup messages. Ctrl+C or make stop shuts down both.", flush=True)
                while not stopping:
                    if any(child.poll() is not None for child in children.values()):
                        raise ValueError("Web or worker exited; stopping the other process. See logs above.")
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(1)
                        try:
                            action = connection.recv(32).decode()
                            if action == "stop":
                                stopping = True
                                response = "Stop requested. Waiting for active work to finish in the start terminal."
                            else:
                                response = json.dumps({name: {"pid": child.pid, "process_alive": child.poll() is None}
                                                       for name, child in children.items()})
                            connection.sendall(response.encode())
                        except (OSError, UnicodeError):
                            pass
        finally:
            print("Stopping web and worker; active jobs may take time to finish.", flush=True)
            for child in children.values():
                if child.poll() is None:
                    try:
                        child.terminate()
                    except ProcessLookupError:
                        pass
            for child in children.values():
                child.wait()
            path.unlink(missing_ok=True)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "doctor", "worker"))
    parser.add_argument("--config", type=Path, default=ROOT / "native.env")
    args = parser.parse_args()
    try:
        env = configuration(args.config)
        if args.action in {"stop", "status"}:
            return request(control_path(env), args.action)
        if args.action == "doctor":
            doctor(env)
            return 0
        if args.action == "worker":
            doctor(env)
            os.chdir(ROOT)
            os.execve(sys.executable, worker_command(), env)
        return serve(env)
    except (ValueError, OSError) as exc:
        print("Cannot " + args.action + ": " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
