"""Keep public package tests independent of unpublished runtime artifacts."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


@pytest.mark.parametrize("name", [
    "desktop-linux-aarch64-test.yml", "desktop-linux-x86_64-test.yml",
    "desktop-macos-arm64-test.yml", "desktop-macos-x86_64-test.yml",
    "desktop-windows-x86_64-test.yml", "desktop-native-r-runtime-test.yml",
])
def test_binary_upload_requires_explicit_opt_in(name):
    data = workflow(name)
    trigger = data.get("on", data.get(True))  # YAML 1.1 parses 'on' as True.
    assert set(trigger) == {"workflow_dispatch"}
    assert trigger["workflow_dispatch"]["inputs"]["upload_artifact"]["default"] is False
    uploads = [step for job in data["jobs"].values() for step in job["steps"]
               if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert uploads
    assert all(step["if"] == "inputs.upload_artifact" for step in uploads)


@pytest.mark.parametrize("name", [
    "desktop-macos-arm64-test.yml", "desktop-macos-x86_64-test.yml",
    "desktop-windows-x86_64-test.yml",
])
def test_native_packages_can_build_r_without_an_artifact(name):
    data = workflow(name)
    trigger = data.get("on", data.get(True))
    assert trigger["workflow_dispatch"]["inputs"]["r_runtime_run_id"]["required"] is False
    steps = data["jobs"]["package"]["steps"]
    build = next(s for s in steps if s.get("uses") == "./.github/actions/build-native-r")
    assert build["if"] == "inputs.r_runtime_run_id == ''"
    for title in ("Download verified R runtime", "Extract verified R runtime"):
        assert next(s for s in steps if s.get("name") == title)["if"] == "inputs.r_runtime_run_id != ''"
    action = yaml.safe_load((ROOT / ".github/actions/build-native-r/action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    assert all("shell" in step for step in action["runs"]["steps"] if "run" in step)
