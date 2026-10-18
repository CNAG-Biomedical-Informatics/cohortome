import json
import multiprocessing
import os

import pytest

from app.state_io import advisory_file_lock, atomic_write_json


def _increment(path):
    for _ in range(12):
        with advisory_file_lock(path.with_suffix(".lock")):
            value = json.loads(path.read_text(encoding="utf-8"))
            atomic_write_json(path, value + 1)


def test_lock_serializes_processes(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, 0)
    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=_increment, args=(path,)) for _ in range(3)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(30)
            assert process.exitcode == 0
        assert json.loads(path.read_text()) == 36
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()


def test_atomic_write_preserves_previous_file_on_error(tmp_path):
    path = tmp_path / "nested/state.json"
    atomic_write_json(path, {"name": "ü"}, file_mode=0o600)
    with pytest.raises(TypeError):
        atomic_write_json(path, object())
    assert json.loads(path.read_text(encoding="utf-8")) == {"name": "ü"}
    assert list(path.parent.iterdir()) == [path]
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_lock_released_after_exception(tmp_path):
    path = tmp_path / "state.lock"
    with pytest.raises(ValueError), advisory_file_lock(path):
        raise ValueError("test")
    with advisory_file_lock(path):
        pass
