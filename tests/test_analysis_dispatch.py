from pathlib import Path

import pytest

from app import analysis_external


def test_external_analysis_registry_forwards_the_shared_runner_contract(monkeypatch, tmp_path):
    captured = {}

    def runner(runner_ref, **kwargs):
        captured["runner_ref"] = runner_ref
        captured.update(kwargs)
        return {"intent": "test", "reply": "ok", "data": {}}

    monkeypatch.setitem(analysis_external.EXTERNAL_ANALYSIS_RUNNERS, "test-runner", runner)
    payload = analysis_external.run_external_analysis(
        "test-runner",
        "example",
        prompt="prompt",
        data_dir="/workspace",
        assay_id="assay-a",
        selected_patient_ids="P1",
        compare_selected_patient_ids="P2",
        job_dir=tmp_path,
        timeout_seconds=42,
    )

    assert payload["reply"] == "ok"
    assert captured == {
        "runner_ref": "example",
        "prompt": "prompt",
        "data_dir": "/workspace",
        "assay_id": "assay-a",
        "selected_patient_ids": "P1",
        "compare_selected_patient_ids": "P2",
        "job_dir": Path(tmp_path),
        "timeout_seconds": 42,
    }


def test_external_analysis_registry_rejects_unknown_runner_type():
    with pytest.raises(RuntimeError, match="Unsupported analysis runner type"):
        analysis_external.run_external_analysis(
            "missing",
            "example",
            prompt="prompt",
            data_dir="/workspace",
        )
