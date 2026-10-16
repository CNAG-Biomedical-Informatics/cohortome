"""Desktop queue lifecycle tests, using only temporary synthetic job records."""
import io
import os
import subprocess
import sys
import time

import pytest
from app import config, jobs, local_jobs, user_state


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setattr(user_state, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setenv("COHORTOME_JOBS_BACKEND", "local")
    yield tmp_path
    local_jobs.stop()


def record():
    return jobs.create_job_record(job_type="analysis", user_id="local", data={})


def terminal(identifier):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = jobs._load_job_record_raw(identifier, "local")
        if value["status"] in {"completed", "failed"}:
            return value
        time.sleep(.01)
    pytest.fail("Desktop job did not finish")


def test_dispatch_completion_and_status(runtime, monkeypatch):
    item = record()
    seen = []
    def launch(command, **options):
        seen.append((command, options))
        jobs.update_job_record(item["job_id"], "local", status="completed")
        return type("Process", (), {"stdin": io.BytesIO(), "returncode": 0,
                                    "poll": lambda self: 0})()
    monkeypatch.setattr(subprocess, "Popen", launch)
    local_jobs.start()
    assert jobs.analysis_worker_status()["available"]
    assert jobs.jobs_enabled()
    assert jobs.enqueue_analysis_job(item["job_id"], "local", 30) == ""
    assert terminal(item["job_id"])["job_backend"] == "local"
    local_jobs.stop()
    assert seen[0][0][-3:] == ["analysis", item["job_id"], "local"]
    assert seen[0][1]["stdin"] == subprocess.PIPE
    assert not jobs.analysis_worker_status()["available"]


def test_failed_launch_does_not_stop_queue(runtime, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("Cannot start Python")))
    local_jobs.start()
    for _ in range(2):
        item = record()
        jobs.enqueue_pheno_job(item["job_id"], "local", 30)
        assert terminal(item["job_id"])["error"] == "Cannot start Python"
    assert local_jobs.status()["available"]


def test_shutdown_marks_waiting_jobs_without_launching_them(runtime, monkeypatch):
    calls = []
    class Process:
        stdin = io.BytesIO()
        def poll(self): return None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a) or Process())
    monkeypatch.setattr(local_jobs, "_terminate", lambda process: None)
    local_jobs.start()
    first, second = record(), record()
    for item in (first, second):
        local_jobs.enqueue("analysis", item["job_id"], "local", 30)
    deadline = time.monotonic() + 2
    while not calls and time.monotonic() < deadline:
        time.sleep(.01)
    local_jobs.stop()
    assert len(calls) == 1
    assert terminal(first["job_id"])["status"] == "failed"
    assert "queued job" in terminal(second["job_id"])["error"]


def test_restart_recovery_and_exclusive_owner(runtime):
    item = record()
    untouched = record()
    jobs.update_job_record(item["job_id"], "local", job_backend="local", status="running")
    local_jobs.start()
    assert terminal(item["job_id"])["status"] == "failed"
    assert jobs._load_job_record_raw(untouched["job_id"], "local")["status"] == "queued"
    with pytest.raises(RuntimeError, match="already open"):
        local_jobs.LocalRunner()


def test_cleanup_only_targets_owned_sandbox(monkeypatch):
    from app import script_sandbox
    calls = []
    def control(arguments, timeout):
        calls.append(arguments)
        return "owned-container\n" if arguments[0] == "ps" else ""
    monkeypatch.setattr(script_sandbox, "_control", control)
    name = "cohortome-script-" + "a" * 32
    local_jobs._cleanup_container(name)
    assert calls == [["ps", "-aq", "--filter", f"name=^/{name}$"], ["rm", "--force", name]]


@pytest.mark.parametrize("shutdown", [False, True])
def test_timeout_and_shutdown_terminate_tree(runtime, monkeypatch, shutdown):
    calls = []
    class Process:
        stdin = io.BytesIO()
        def poll(self): return None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(local_jobs, "_terminate", lambda process: calls.append(process))
    local_jobs.start()
    item = record()
    local_jobs.enqueue("analysis", item["job_id"], "local", 1)
    if shutdown:
        deadline = time.monotonic() + 2
        while not local_jobs.status()["busy_worker_count"] and time.monotonic() < deadline:
            time.sleep(.01)
        local_jobs.stop()
    result = terminal(item["job_id"])
    assert "closed" in result["error"] if shutdown else "time limit" in result["error"]
    assert len(calls) == 1


def test_real_child_uses_shared_runner_and_isolated_runtime(tmp_path):
    env = dict(os.environ, COHORTOME_RUNTIME_ROOT=str(tmp_path), COHORTOME_AUTH_MODE="none")
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    # No dataset or external engine required: shared analysis runner rejects an
    # unknown catalog item and persists its normal error artifact.
    code = '''
from app import jobs, local_jobs
import time
children = []
launch = local_jobs.subprocess.Popen
def tracked_launch(*args, **kwargs):
    child = launch(*args, **kwargs)
    children.append(child)
    return child
local_jobs.subprocess.Popen = tracked_launch
item = jobs.create_job_record(job_type="analysis", user_id="local", data={"catalog_item_id":"missing-synthetic-tool"})
local_jobs.start()
try:
    local_jobs.enqueue("analysis", item["job_id"], "local", 15)
    for _ in range(300):
        result = jobs._load_job_record_raw(item["job_id"], "local")
        if result["status"] == "failed": break
        time.sleep(.05)
    assert "Unknown analysis catalog item" in result["error"], result
    assert (jobs.job_dir(item["job_id"], "local") / "error.txt").exists()
    for _ in range(100):
        if children and children[0].poll() is not None: break
        time.sleep(.02)
    assert children[0].returncode == 0, "Worker must exit cleanly after persisting its result"
finally:
    local_jobs.stop()
'''
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr
