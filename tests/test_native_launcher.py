import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest

SPEC = importlib.util.spec_from_file_location("native_launcher", Path(__file__).resolve().parents[1] / "scripts/native.py")
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "native.env"
    path.write_text(f"COHORTOME_RUNTIME_ROOT={tmp_path}\nCOHORTOME_AUTH_MODE=local\n"
                    f"COHORTOME_SESSION_SECRET={'a' * 40}\nLM_STUDIO_ENABLED=false\n")
    path.chmod(0o600)
    return path


def test_config_overrides_shell_and_is_shared(config, monkeypatch):
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "none")
    monkeypatch.setenv("COHORTOME_RUNTIME_ROOT", "/wrong/runtime")
    monkeypatch.setenv("COHORTOME_AUTH_BOOTSTRAP_USERS", "stale")
    monkeypatch.setenv("UVICORN_WORKERS", "4")
    env = native.configuration(config)
    assert env["COHORTOME_AUTH_MODE"] == "local"
    assert env["COHORTOME_RUNTIME_ROOT"] == str(config.parent)
    assert "COHORTOME_AUTH_BOOTSTRAP_USERS" not in env
    assert "UVICORN_WORKERS" not in env
    assert native.validate(env) == ("127.0.0.1", 8001)


def test_private_config_required(config):
    config.chmod(0o644)
    with pytest.raises(ValueError, match="chmod 600"):
        native.configuration(config)


def test_missing_runtime_not_created(config):
    config.write_text(f"COHORTOME_RUNTIME_ROOT={config.parent / 'missing'}\n")
    with pytest.raises(ValueError, match="No new runtime"):
        native.configuration(config)
    assert not (config.parent / "missing").exists()


def test_literals_are_not_expanded(config):
    with config.open("a") as handle:
        handle.write("COHORTOME_OIDC_CLIENT_SECRET='${SECRET}'\n")
    assert native.configuration(config)["COHORTOME_OIDC_CLIENT_SECRET"] == "${SECRET}"


@pytest.mark.parametrize("change, message", [
    ({"COHORTOME_AUTH_MODE": "typo"}, "AUTH_MODE"),
    ({"COHORTOME_SESSION_SECRET": "replace-this"}, "SESSION_SECRET"),
    ({"COHORTOME_AUTH_MODE": "none", "COHORTOME_HOST": "0.0.0.0"}, "authentication"),
    ({"COHORTOME_AUTH_MODE": "oidc"}, "OIDC_ISSUER"),
    ({"COHORTOME_PORT": "65536"}, "COHORTOME_PORT"),
])
def test_invalid_settings(config, change, message):
    env = native.configuration(config)
    env.update(change)
    with pytest.raises(ValueError, match=message):
        native.validate(env)


def test_redis_error_does_not_expose_credentials(config, monkeypatch):
    import redis
    env = native.configuration(config)
    env["COHORTOME_JOBS_REDIS_URL"] = "redis://user:secret@example.invalid"

    def fail(*args, **kwargs):
        raise RuntimeError(env["COHORTOME_JOBS_REDIS_URL"])

    monkeypatch.setattr(redis.Redis, "from_url", fail)
    with pytest.raises(ValueError, match="Redis is unavailable") as exc:
        native.doctor(env)
    assert "secret" not in str(exc.value)


def test_launcher_controls_and_cleans_both_children(config, monkeypatch):
    """Exercise real locks, sockets, signals and processes, without app data/Redis."""
    env = native.configuration(config)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        env["COHORTOME_PORT"] = str(probe.getsockname()[1])
    monkeypatch.setattr(native, "doctor", lambda env: None)
    real_popen = subprocess.Popen
    children = []

    def dummy_child(command, **kwargs):
        assert kwargs["env"] == env
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(native.subprocess, "Popen", dummy_child)
    # Control requests from another thread; signal handlers stay in the main thread.
    import threading
    errors = []

    def control():
        try:
            path = native.control_path(env)
            deadline = time.monotonic() + 5
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert native.request(path, "status") == 0
            with pytest.raises(ValueError, match="already manages"):
                native.serve(env)
            assert native.request(path, "stop") == 0
        except BaseException as exc:
            errors.append(exc)
            os.kill(os.getpid(), signal.SIGTERM)

    thread = threading.Thread(target=control)
    thread.start()
    assert native.serve(env) == 0
    thread.join(timeout=5)
    assert not errors
    assert len(children) == 2
    assert all(child.poll() is not None for child in children)
    assert not native.control_path(env).exists()


def test_busy_port_does_not_start_children(config, monkeypatch):
    env = native.configuration(config)
    monkeypatch.setattr(native, "doctor", lambda env: None)
    with socket.create_server(("127.0.0.1", 0)) as occupied:
        env["COHORTOME_PORT"] = str(occupied.getsockname()[1])
        with pytest.raises(ValueError, match="Cannot bind"):
            native.serve(env)
    assert not native.control_path(env).exists()


def test_oidc_requires_client_secret(config):
    env = native.configuration(config)
    env.update(COHORTOME_AUTH_MODE="oidc", COHORTOME_OIDC_ISSUER="https://example.org",
               COHORTOME_OIDC_CLIENT_ID="cohortome", COHORTOME_OIDC_REDIRECT_URI="http://localhost/callback")
    with pytest.raises(ValueError, match="OIDC_CLIENT_SECRET"):
        native.validate(env)


def test_child_launch_failure_cleans_first_child(config, monkeypatch):
    env = native.configuration(config)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        env["COHORTOME_PORT"] = str(probe.getsockname()[1])
    monkeypatch.setattr(native, "doctor", lambda env: None)
    real_popen = subprocess.Popen
    children = []

    def launch(command, **kwargs):
        if children:
            raise OSError("Cannot start worker")
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(native.subprocess, "Popen", launch)
    with pytest.raises(OSError, match="Cannot start worker"):
        native.serve(env)
    assert children[0].poll() is not None
    assert not native.control_path(env).exists()
