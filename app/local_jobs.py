"""Single-owner desktop queue; analysis execution remains in app.jobs.

Only the desktop backend starts this supervisor. Children inherit its isolated
runtime, never the web deployment's configuration. No arbitrary command API.
"""
from __future__ import annotations

import os
import queue
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import uuid4
from app.analysis_resources import single_thread_environment

_runner = None


def status():
    available = bool(_runner and _runner.thread.is_alive() and not _runner.stopping.is_set())
    busy = bool(available and _runner.busy)
    return dict(backend="local", available=available, dependencies_available=True,
                redis_available=False, queue_name="analysis", worker_count=int(available),
                busy_worker_count=int(busy), activity="working" if busy else "idle" if available else "offline")


def start():
    global _runner
    if _runner is not None:
        raise RuntimeError("Desktop runner already started.")
    runner = LocalRunner()
    _runner = runner
    runner.thread.start()


def stop():
    global _runner
    if _runner:
        _runner.close()
        _runner = None


def enqueue(kind, job_id, user_id, timeout):
    if not status()["available"]:
        raise RuntimeError("Desktop background runner is unavailable.")
    return _runner.enqueue(kind, job_id, user_id, timeout)


def _terminate(process):
    # Terminate the entire analysis tree, including R/Perl subprocesses.
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def _cleanup_container(name):
    if not name:
        return
    from app.script_sandbox import _control
    if _control(["ps", "-aq", "--filter", f"name=^/{name}$"], timeout=3).strip():
        _control(["rm", "--force", name], timeout=3)


class LocalRunner:
    def __init__(self):
        from app.config import STATE_ROOT_DIR
        from app import jobs
        STATE_ROOT_DIR.mkdir(parents=True, exist_ok=True)
        # SQLite's OS lock prevents two desktop supervisors sharing a runtime.
        # This is a lifetime lock, not a second job database.
        self.lock = sqlite3.connect(STATE_ROOT_DIR / ".desktop-runner.sqlite", timeout=0)
        try:
            self.lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError:
            self.lock.close()
            raise RuntimeError("This desktop workspace is already open.") from None
        for path in (STATE_ROOT_DIR / "users").glob("*/jobs/*/job.json"):
            record = jobs._read_json(path)
            if record.get("job_backend") == "local" and record.get("status") in {"queued", "running"}:
                jobs.update_job_record(path.parent.name, path.parents[2].name,
                    status="failed", completed_at=jobs._now_iso(),
                    error="Desktop closed before this job finished. Submit it again to rerun.")
        self.pending = queue.Queue()
        self.stopping = threading.Event()
        self.busy = False
        self.guard = threading.Lock()
        self.thread = threading.Thread(target=self.work, name="desktop-jobs", daemon=True)

    def enqueue(self, kind, job_id, user_id, timeout):
        from app import jobs
        if kind not in {"analysis", "pheno"}:
            raise ValueError("Unsupported desktop job type.")
        with self.guard:
            if self.stopping.is_set():
                raise RuntimeError("Desktop is closing; no new jobs can be submitted.")
            jobs.update_job_record(job_id, user_id, job_backend="local")
            self.pending.put((kind, job_id, user_id, max(1, int(timeout))))
        return ""

    def work(self):
        from app import jobs
        while True:
            item = self.pending.get()
            if item is None:
                return
            kind, job_id, user_id, timeout = item
            process = None
            container_name = ""
            try:
                if self.stopping.is_set():
                    raise RuntimeError("Desktop closed before this queued job started.")
                self.busy = True
                env = single_thread_environment()
                env["PYTHONPATH"] = os.pathsep.join(sys.path)
                env["COHORTOME_LOCAL_JOB_CHILD"] = "1"
                record = jobs._load_job_record_raw(job_id, user_id)
                if record.get("runner_type") == "container":
                    container_name = "cohortome-script-" + uuid4().hex
                env["COHORTOME_LOCAL_CONTAINER_NAME"] = container_name
                command = [sys.executable, "-m", "app.local_jobs", kind, job_id, user_id]
                # Runners already persist governed logs/artifacts. Do not leak
                # child stdout into the desktop bootstrap protocol or terminal.
                process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=os.name != "nt")
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    if self.stopping.wait(.1):
                        raise RuntimeError("Desktop closed while this job was running.")
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Desktop analysis exceeded its configured time limit.")
                record = jobs._load_job_record_raw(job_id, user_id)
                if record.get("status") in {"queued", "running"}:
                    raise RuntimeError(f"Analysis process exited without a result (exit {process.returncode}).")
            except Exception as exc:
                if process is not None:
                    try:
                        _terminate(process)
                    except (OSError, subprocess.SubprocessError):
                        # Do not lose the supervisor or leave subsequent jobs stuck.
                        exc = RuntimeError(f"{exc} Process cleanup could not be confirmed.")
                try:
                    _cleanup_container(container_name)
                except (RuntimeError, OSError, subprocess.SubprocessError):
                    exc = RuntimeError(f"{exc} Sandbox cleanup could not be confirmed; check Docker.")
                jobs.update_job_record(job_id, user_id, status="failed",
                    completed_at=jobs._now_iso(), error=str(exc))
            finally:
                if process is not None and process.stdin:
                    process.stdin.close()
                self.busy = False

    def close(self):
        with self.guard:
            self.stopping.set()
            self.pending.put(None)
        self.thread.join()
        self.lock.close()


if __name__ == "__main__":
    if os.environ.get("COHORTOME_LOCAL_JOB_CHILD") != "1" or len(sys.argv) != 4:
        raise SystemExit("This entrypoint is only for desktop-managed job processes.")
    def parent_closed():
        # A daemon blocked on BufferedReader holds Python's stdin lock and can
        # abort interpreter shutdown after an otherwise successful analysis.
        # Read the pipe directly, without owning a buffered-I/O lock.
        while os.read(0, 1):
            pass
        # Backend crash/forced close must not leave an orphaned analysis tree.
        try:
            _cleanup_container(os.environ.get("COHORTOME_LOCAL_CONTAINER_NAME", ""))
        except (RuntimeError, OSError, subprocess.SubprocessError):
            pass  # Startup history reports interrupted jobs; never retry them.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(os.getpid()), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if os.getpgrp() == os.getpid():
                os.killpg(os.getpgrp(), signal.SIGKILL)
            os._exit(1)
    threading.Thread(target=parent_closed, daemon=True).start()
    from app.jobs import run_analysis_job, run_pheno_job
    kind, job_id, user_id = sys.argv[1:]
    {"analysis": run_analysis_job, "pheno": run_pheno_job}[kind](job_id, user_id)
