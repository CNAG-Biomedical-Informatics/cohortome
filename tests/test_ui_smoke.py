from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - depends on local runtime
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for server at {url}") from last_error


def _spawn_live_server(extra_env: dict[str, str] | None = None):
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    return process, base_url


def _prepare_default_dataset_store(runtime_root: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    env["COHORTOME_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.query_store import prepare_dataset_query_store; prepare_dataset_query_store('default')",
        ],
        cwd=os.getcwd(),
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture(scope="session")
def live_server(tmp_path_factory) -> str:
    runtime_root = tmp_path_factory.mktemp("cohortome-ui-runtime")
    _prepare_default_dataset_store(runtime_root)
    process, base_url = _spawn_live_server({"COHORTOME_RUNTIME_ROOT": str(runtime_root)})
    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            process.kill()
            process.wait(timeout=5)


@pytest.fixture
def live_server_auth(tmp_path) -> str:
    runtime_root = tmp_path / "runtime"
    _prepare_default_dataset_store(runtime_root)
    process, base_url = _spawn_live_server(
        {
            "COHORTOME_RUNTIME_ROOT": str(runtime_root),
            "COHORTOME_AUTH_MODE": "local",
            "COHORTOME_SESSION_SECRET": "ui-smoke-test-session-secret",
            "COHORTOME_LOCAL_USERS_JSON": json.dumps(
                [
                    {
                        "username": "admin",
                        "password": "secret",
                        "role": "admin",
                        "display_name": "Admin User",
                    }
                ]
            ),
        }
    )
    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            process.kill()
            process.wait(timeout=5)


def _install_dataset_lifecycle_routes(page):
    datasets = [
        {
            "dataset_id": "default",
            "name": "Synthetic demo",
            "description": "Synthetic UI fixture",
            "enabled": True,
            "visibility": "all_authenticated",
            "allowed_users": [],
            "allowed_groups": [],
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "detailed_allowed",
            "clinical_representation": "snapshot",
            "query_store_status": {"status": "ready", "ready": True, "last_error": ""},
        },
        {
            "dataset_id": "secondary",
            "name": "Secondary demo",
            "description": "Secondary synthetic UI fixture",
            "enabled": True,
            "visibility": "all_authenticated",
            "allowed_users": [],
            "allowed_groups": [],
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "detailed_allowed",
            "clinical_representation": "person",
            "query_store_status": {"status": "ready", "ready": True, "last_error": ""},
        },
    ]
    state = {"current_ids": ["default"], "select_requests": [], "fail_next_selection": ""}

    def scope_id(dataset_ids):
        normalized = sorted(set(dataset_ids))
        if len(normalized) == 1:
            return normalized[0]
        return f"scope--{'--'.join(normalized)}" if normalized else ""

    def list_handler(route):
        current_ids = list(state["current_ids"])
        current = next((item for item in datasets if item["dataset_id"] == current_ids[0]), None) if len(current_ids) == 1 else None
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": datasets,
                    "current_dataset_id": current_ids[0] if len(current_ids) == 1 else "",
                    "current_dataset_ids": current_ids,
                    "current_dataset_scope_id": scope_id(current_ids),
                    "current_dataset": current,
                }
            ),
        )

    def select_handler(route):
        payload = json.loads(route.request.post_data or "{}")
        selected_ids = payload.get("dataset_ids") or ([payload["dataset_id"]] if payload.get("dataset_id") else [])
        selected_ids = [str(item) for item in selected_ids if str(item)]
        state["select_requests"].append(selected_ids)
        if state["fail_next_selection"]:
            detail = state["fail_next_selection"]
            state["fail_next_selection"] = ""
            route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": detail}))
            return
        state["current_ids"] = selected_ids
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "selected": bool(selected_ids),
                    "current_dataset_id": selected_ids[0] if len(selected_ids) == 1 else "",
                    "current_dataset_ids": selected_ids,
                    "current_dataset_scope_id": scope_id(selected_ids),
                }
            ),
        )

    page.route("**/datasets", list_handler)
    page.route("**/datasets/select", select_handler)
    page._cohortome_dataset_state = state
    return state


@pytest.fixture
def page(live_server: str):
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()

            context.route(
                "https://cdn.plot.ly/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body="""
window.Plotly = {
  newPlot: async function(el) {
    el.dataset.plotlyReady = "true";
    el.on = function(name, cb) {
      this._plotlyHandlers = this._plotlyHandlers || {};
      this._plotlyHandlers[name] = cb;
    };
    return el;
  }
};
""",
                ),
            )

            page = context.new_page()
            _install_dataset_lifecycle_routes(page)
            page.goto(live_server, wait_until="networkidle")
            yield page
            context.close()
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"Playwright browser is unavailable: {exc}")


@pytest.fixture
def page_auth(live_server_auth: str):
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()

            context.route(
                "https://cdn.plot.ly/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body="""
window.Plotly = {
  newPlot: async function(el) {
    el.dataset.plotlyReady = "true";
    el.on = function(name, cb) {
      this._plotlyHandlers = this._plotlyHandlers || {};
      this._plotlyHandlers[name] = cb;
    };
    return el;
  }
};
""",
                ),
            )

            page = context.new_page()
            _install_dataset_lifecycle_routes(page)
            page.goto(live_server_auth, wait_until="networkidle")
            yield page
            context.close()
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"Playwright browser is unavailable: {exc}")


def _open_pheno_tab(page) -> None:
    _ensure_detailed_workspace(page)
    page.locator("#phenoTabBtn").click()
    page.locator("#phenoPrompt").wait_for()


def _ensure_detailed_workspace(page) -> None:
    pheno_tab = page.locator("#phenoTabBtn")
    if pheno_tab.get_attribute("aria-disabled") != "true":
        return

    page.locator("#datasetsTabBtn").click()
    dataset_values = page.locator("#datasetPicker [data-dataset-checkbox]").evaluate_all(
        "(inputs) => inputs.map((input) => input.getAttribute('data-dataset-checkbox'))"
    )
    target = "default" if "default" in dataset_values else (dataset_values[0] if dataset_values else None)
    if target is None:
        raise AssertionError("No dataset options are available for the UI smoke test.")
    for value in dataset_values:
        if not value:
            continue
        checkbox = page.locator(f"#datasetPicker [data-dataset-checkbox='{value}']")
        if value == target:
            checkbox.check(force=True)
        else:
            checkbox.uncheck(force=True)
    page.locator("#loadBtn").wait_for()
    page.locator("#loadBtn").click()
    playwright.expect(pheno_tab).not_to_have_attribute("aria-disabled", "true")
    playwright.expect(page.locator("#loadBtn")).to_be_enabled()


def _mock_pheno_reference_ids(
    page,
    patient_ids: list[str] | None = None,
    record_ids: list[str] | None = None,
    reference_files: list[str] | None = None,
) -> None:
    payload = {
        "patient_ids": patient_ids or ["SYN001", "SYN002", "SYN003"],
        "record_ids": record_ids or ["SYN001:week_0", "SYN002:week_0", "SYN003:week_0"],
        "reference_files": reference_files or ["synthetic_longitudinal.json"],
    }

    page.route(
        "**/pheno-ranker/patient-ids?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        ),
    )
    _ensure_detailed_workspace(page)


def _open_query_tab(page) -> None:
    page.locator("#queryTabBtn").click()
    page.locator("#question").wait_for()


def _open_analysis_tab(page) -> None:
    page.locator("#analysisTabBtn").click()
    page.locator("#analysisPrompt").wait_for()


def _mock_pheno_plan(page, expected_mode: str, patient_id: str = "", selected_ids: str = "") -> None:
    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "source": "deterministic",
                    "reasoning": [
                        "Detected action: compare.",
                        f"Detected mode: {expected_mode}.",
                    ],
                    "plan": {
                        "action": "compare",
                        "mode": expected_mode,
                        "data_dir": "data",
                        "patient_id": patient_id,
                        "selected_patient_ids": selected_ids,
                        "include_terms": ["diseases"],
                        "exclude_terms": [],
                        "max_out": 10,
                        "align": True,
                        "render_heatmap": True,
                        "render_mds": True,
                    },
                }
            ),
        )

    page.route("**/pheno-ranker/plan", handler)


def _mock_cohort_run(page, metric: str = "", prefixed_ids: bool = False, request_capture: dict | None = None) -> None:
    ids = (
        ["C1_SYN001:week_0", "C1_SYN002:week_0", "C2_SYN003:week_0"]
        if prefixed_ids
        else ["SYN001:week_0", "SYN002:week_0", "SYN003:week_0"]
    )
    matrix_text = (
        f"\t{ids[0]}\t{ids[1]}\t{ids[2]}\n"
        f"{ids[0]}\t0\t1\t2\n"
        f"{ids[1]}\t1\t0\t1\n"
        f"{ids[2]}\t2\t1\t0\n"
    )
    patient_ids = ["SYN001", "SYN002", "SYN003"]
    mds_text = (
        "record_id\tpatient_id\tx\ty\n"
        f"{ids[0]}\t{patient_ids[0]}\t-0.4\t0.1\n"
        f"{ids[1]}\t{patient_ids[1]}\t0.2\t-0.3\n"
        f"{ids[2]}\t{patient_ids[2]}\t0.4\t0.2\n"
    )

    def run_handler(route):
        if request_capture is not None:
            request_capture["body"] = json.loads(route.request.post_data or "{}")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "job-cohort",
                    "mode": "cohort",
                    "files": [
                        {"name": "matrix.txt", "url": "/pheno-ranker/results/job-cohort/matrix.txt", "size": 120},
                        {"name": "mds_points.tsv", "url": "/pheno-ranker/results/job-cohort/mds_points.tsv", "size": 110},
                    ],
                    "stderr": "",
                    "command": "pheno cohort command",
                    "pre_commands": [],
                    "plots": [],
                    "similarity_metric_cohort": metric,
                }
            ),
        )

    page.route("**/pheno-ranker/run", run_handler)
    page.route(
        "**/pheno-ranker/results/job-cohort/matrix.txt",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=matrix_text),
    )
    page.route(
        "**/pheno-ranker/results/job-cohort/mds_points.tsv",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=mds_text),
    )


def _mock_patient_run(page) -> None:
    rank_text = (
        "reference\ttarget\thamming\n"
        "SYN002:week_0\tSYN001:week_0\t0.12\n"
        "SYN003:week_0\tSYN001:week_0\t0.19\n"
    )

    page.route(
        "**/pheno-ranker/run",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body="""
{
  "job_id": "job-patient",
  "mode": "patient",
  "files": [
    {"name": "rank.txt", "url": "/pheno-ranker/results/job-patient/rank.txt", "size": 98},
    {"name": "alignment.target.csv", "url": "/pheno-ranker/results/job-patient/alignment.target.csv", "size": 42}
  ],
  "stderr": "",
  "command": "pheno patient command",
  "pre_commands": [],
  "plots": []
}
""",
        ),
    )
    page.route(
        "**/pheno-ranker/results/job-patient/rank.txt",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=rank_text),
    )
    page.route(
        "**/pheno-ranker/results/job-patient/alignment.target.csv",
        lambda route: route.fulfill(status=200, content_type="text/plain", body="bucket,label\n"),
    )


def _mock_dashboard_load(page, clinical_representation: str = "snapshot") -> None:
    page.route(
        "**/patients?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "patient_id": "SYN001",
                        "visit_count": 5,
                        "sex": "female",
                        "evidence": {"diseases": {"count": 1}},
                        "first_event_date": "2024-01-01",
                        "last_event_date": "2024-06-01",
                    },
                    {
                        "patient_id": "SYN002",
                        "visit_count": 4,
                        "sex": "male",
                        "evidence": {"diseases": {"count": 2}},
                        "first_event_date": "2024-01-05",
                        "last_event_date": "2024-05-10",
                    },
                ]
            ),
        ),
    )
    page.route(
        "**/dashboard?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "clinical_representation": clinical_representation,
                    "patients": 2,
                    "visits": 9,
                    "top_diseases": [["Crohn Disease", 2]],
                    "top_treatments": [["Infliximab", 1]],
                    "sex_counts": {"female": 1, "male": 1},
                    "visit_distribution": {"4": 1, "5": 1},
                    "disease_medication_matrix": {
                        "diseases": ["Crohn Disease"],
                        "medications": ["Infliximab"],
                        "values": [[1]],
                    },
                    "timelines": [
                        {
                            "patient_id": "SYN001",
                            "visit_count": 5,
                            "first_event_date": "2024-01-01",
                            "last_event_date": "2024-06-01",
                            "events": [
                                {
                                    "visit_id": "week_0",
                                    "event_date": "2024-01-01",
                                    "event_type": "baseline",
                                    "diagnosis": "Crohn Disease",
                                    "domains": [
                                        {"key": "diseases", "label": "Disease", "count": 1, "examples": ["Crohn Disease"]},
                                        {"key": "treatments", "label": "Treatment", "count": 1, "examples": ["Infliximab"]},
                                    ],
                                }
                            ],
                        },
                        {
                            "patient_id": "SYN002",
                            "visit_count": 4,
                            "first_event_date": "2024-01-05",
                            "last_event_date": "2024-05-10",
                            "events": [
                                {
                                    "visit_id": "week_0",
                                    "event_date": "2024-01-05",
                                    "event_type": "baseline",
                                    "diagnosis": "Ulcerative Colitis",
                                    "domains": [
                                        {"key": "phenotypic_features", "label": "Phenotype", "count": 1, "examples": ["Abdominal pain"]}
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ),
        ),
    )
    page.route(
        "**/patients/*/workspace?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "patient_id": route.request.url.split("/patients/", 1)[1].split("/workspace", 1)[0],
                    "summary": {"patient_id": route.request.url.split("/patients/", 1)[1].split("/workspace", 1)[0]},
                    "patient_context": {"sex": "female", "date_of_birth": "", "vital_status": "", "source_files": []},
                    "evidence": {
                        "diseases": {"count": 1, "examples": ["Crohn Disease"]},
                        "phenotypic_features": {"count": 1, "examples": ["Abdominal pain"]},
                        "measures": {"count": 0, "examples": []},
                        "treatments": {"count": 1, "examples": ["Infliximab"]},
                        "procedures": {"count": 0, "examples": []},
                        "exposures": {"count": 0, "examples": []},
                    },
                    "key_fragments": [],
                    "visits": [],
                }
            ),
        ),
    )


def _mock_assay_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "clinical_overlap_ratio": 1.0,
                            "scope_overlap_patient_count": 0,
                            "scope_overlap_ratio": 0.0,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        }
                    ]
                }
            ),
        ),
    )


def _mock_dicom_studies(page) -> None:
    page.route(
        "**/dicom/studies?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "ohif_public_url": "http://ohif.example",
                    "dicomweb_public_url": "http://orthanc.example/dicom-web",
                    "studies": [
                        {
                            "study_id": "syn001-mri",
                            "label": "Synthetic MRI baseline SYN001",
                            "patient_id": "SYN001",
                            "sample_id": "SYN001:week_0",
                            "timepoint": "week_0",
                            "modality": "MR",
                            "study_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1",
                            "ohif_url": "http://ohif.example/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1",
                            "series": [
                                {
                                    "series_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1.1",
                                    "series_description": "Synthetic axial T1",
                                    "instance_count": 1,
                                }
                            ],
                        }
                    ],
                }
            ),
        ),
    )


def _mock_dicom_status(page) -> None:
    page.route(
        "**/dicom/status?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "ohif_public_url": "http://ohif.example",
                    "dicomweb_public_url": "http://orthanc.example/dicom-web",
                    "manifest_found": True,
                    "manifest_count": 1,
                    "study_count": 1,
                    "orthanc": {
                        "checked": True,
                        "reachable": True,
                        "message": "Orthanc is reachable.",
                    },
                }
            ),
        ),
    )


def _mock_multimodal_readiness(page) -> None:
    page.route(
        "**/assays/readiness?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "workspace": {
                        "patient_count": 3,
                        "sample_count": 3,
                        "modality_count": 4,
                        "multimodal_patient_count": 2,
                        "exact_sample_overlap_count": 1,
                    },
                    "modalities": [
                        {"key": "clinical", "label": "Clinical", "dataset_count": 1, "study_count": 0, "patient_count": 3, "sample_count": 3, "feature_count": 0, "clinical_overlap_count": 3},
                        {"key": "transcriptomics", "label": "Transcriptomics", "dataset_count": 1, "study_count": 0, "patient_count": 2, "sample_count": 2, "feature_count": 12, "clinical_overlap_count": 2},
                        {"key": "imaging", "label": "Imaging features", "dataset_count": 1, "study_count": 0, "patient_count": 1, "sample_count": 1, "feature_count": 6, "clinical_overlap_count": 1},
                        {"key": "dicom", "label": "DICOM studies", "dataset_count": 0, "study_count": 1, "patient_count": 1, "sample_count": 1, "feature_count": 0, "clinical_overlap_count": 1},
                    ],
                    "pairwise_overlaps": [
                        {"left": "imaging", "right": "transcriptomics", "left_label": "Imaging features", "right_label": "Transcriptomics", "patient_overlap_count": 1, "sample_overlap_count": 1},
                        {"left": "dicom", "right": "imaging", "left_label": "DICOM studies", "right_label": "Imaging features", "patient_overlap_count": 1, "sample_overlap_count": 1},
                    ],
                    "issues": [
                        {"severity": "warning", "kind": "dicom_sample_without_clinical_timepoint", "message": "DICOM study sample needs clinical timepoint review."}
                    ],
                    "suggestions": [
                        {"key": "dicom_review", "label": "Review DICOM studies in OHIF", "enabled": True, "reason": "DICOM studies are linked to this workspace."},
                        {"key": "imaging_feature_summary", "label": "Summarize derived imaging features", "enabled": True, "reason": "Imaging feature matrices overlap clinical patients."},
                        {"key": "patient_level_cross_modal", "label": "Explore patient-level cross-modal associations", "enabled": True, "reason": "At least two modalities share 1 patient."},
                        {"key": "visit_matched_multimodal", "label": "Explore visit-matched multimodal associations", "enabled": True, "reason": "At least two modalities share 1 exact sample ID."},
                    ],
                }
            ),
        ),
    )


def _mock_multimodal_matrix(page) -> None:
    page.route(
        "**/assays/matrix?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "metadata": {
                        "join_level": "sample",
                        "row_count": 2,
                        "preview_row_count": 2,
                        "column_count": 6,
                        "assay_dataset_count": 2,
                        "feature_group_count": 3,
                        "selected_feature_count": 3,
                        "missing_cell_count": 1,
                        "missing_fraction": 0.0833,
                    },
                    "columns": [
                        {"key": "patient_id", "label": "Patient ID", "role": "identifier"},
                        {"key": "sample_id", "label": "Sample/timepoint ID", "role": "identifier"},
                        {"key": "clinical.sex", "label": "Sex", "role": "covariate"},
                        {"key": "synthetic_transcriptome_raw_counts_infliximab.ENSG00000111111", "label": "ENSG00000111111", "role": "feature", "modality": "transcriptomics"},
                        {"key": "synthetic_mri_derived_measurements.lesion_volume_ml", "label": "lesion_volume_ml", "role": "feature", "modality": "imaging"},
                        {"key": "dicom.study_count", "label": "DICOM study count", "role": "viewer_metadata", "modality": "dicom"},
                    ],
                    "rows": [
                        {
                            "row_id": "SYN001:week_0",
                            "patient_id": "SYN001",
                            "sample_id": "SYN001:week_0",
                            "values": {
                                "patient_id": "SYN001",
                                "sample_id": "SYN001:week_0",
                                "clinical.sex": "female",
                                "synthetic_transcriptome_raw_counts_infliximab.ENSG00000111111": 42,
                                "synthetic_mri_derived_measurements.lesion_volume_ml": 1.4,
                                "dicom.study_count": 1,
                            },
                        }
                    ],
                    "missingness": [
                        {"key": "synthetic_mri_derived_measurements.lesion_volume_ml", "label": "lesion_volume_ml", "missing_count": 1, "missing_fraction": 0.5}
                    ],
                    "feature_groups": [
                        {"dataset_name": "synthetic_transcriptome_raw_counts_infliximab", "label": "Transcriptomics", "modality": "transcriptomics", "feature_count_selected": 1, "exact_sample_match_count": 1},
                        {"dataset_name": "synthetic_mri_derived_measurements", "label": "MRI derived measurements", "modality": "imaging", "feature_count_selected": 1, "exact_sample_match_count": 1},
                        {"dataset_name": "dicom_studies", "label": "DICOM studies", "modality": "dicom", "feature_count_selected": 1, "exact_sample_match_count": 1},
                    ],
                    "warnings": [
                        {"severity": "warning", "kind": "patient_overlap_without_exact_sample_match", "message": "A modality overlaps patients but not exact sample IDs."}
                    ],
                }
            ),
        ),
    )


def _mock_multimodal_assay_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics",
                            "data_type": "raw_counts",
                            "feature_label": "genes",
                            "feature_id_type": "ensembl_gene_id",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        },
                        {
                            "dataset_name": "synthetic_olink_inflammation_panel",
                            "modality": "proteomics",
                            "data_type": "npX",
                            "feature_label": "proteins",
                            "feature_id_type": "uniprot_accession",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                            "sample_count": 12,
                            "patient_count": 2,
                            "feature_count": 92,
                            "clinical_overlap_patient_count": 2,
                        },
                        {
                            "dataset_name": "synthetic_mri_derived_measurements",
                            "modality": "imaging",
                            "data_type": "derived_measurements",
                            "feature_label": "radiology measurements",
                            "feature_id_type": "dicom_tag",
                            "patient_ids": ["SYN001"],
                            "sample_ids": ["SYN001:week_0"],
                            "sample_count": 1,
                            "patient_count": 1,
                            "feature_count": 6,
                            "clinical_overlap_patient_count": 1,
                        },
                    ]
                }
            ),
        ),
    )


def _mock_assay_datasets_with_nonmatching_dataset(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        },
                        {
                            "dataset_name": "unrelated_transcriptome_raw_counts",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["OTHER001", "OTHER002"],
                            "sample_count": 12,
                            "patient_count": 2,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 0,
                            "mean_total_counts_per_sample": 512.0,
                            "mean_detected_genes_per_sample": 8.2,
                            "top_genes": [],
                        },
                    ]
                }
            ),
        ),
    )


def _mock_assay_datasets_with_two_matching_datasets(page) -> None:
    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 1024.0,
                            "mean_detected_genes_per_sample": 10.4,
                            "top_genes": [],
                        },
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_ustekinumab",
                            "modality": "transcriptomics_raw_counts",
                            "patient_ids": ["SYN001", "SYN002"],
                            "sample_count": 25,
                            "patient_count": 5,
                            "gene_count": 12,
                            "clinical_overlap_patient_count": 5,
                            "mean_total_counts_per_sample": 980.0,
                            "mean_detected_genes_per_sample": 9.8,
                            "top_genes": [],
                        },
                    ]
                }
            ),
        ),
    )


def _mock_analysis_trajectory_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_trajectory",
                    "reply": "CRP declines after Infliximab with early separation from baseline.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "mode": "trajectory_response",
                            "measure": "CRP",
                            "unit": "mg/L",
                            "treatment": "Infliximab",
                            "patient_count": 3,
                            "patient_series": [
                                {
                                    "label": "SYN001",
                                    "points": [
                                        {"x": "week_0", "x_label": "week_0", "value": 16},
                                        {"x": "week_2", "x_label": "week_2", "value": 9},
                                        {"x": "week_6", "x_label": "week_6", "value": 5},
                                    ],
                                },
                                {
                                    "label": "SYN002",
                                    "points": [
                                        {"x": "week_0", "x_label": "week_0", "value": 14},
                                        {"x": "week_2", "x_label": "week_2", "value": 8},
                                        {"x": "week_6", "x_label": "week_6", "value": 4},
                                    ],
                                },
                            ],
                            "summary_series": {
                                "label": "Cohort median",
                                "points": [
                                    {"x": "week_0", "x_label": "week_0", "value": 15},
                                    {"x": "week_2", "x_label": "week_2", "value": 8.5},
                                    {"x": "week_6", "x_label": "week_6", "value": 4.5},
                                ],
                            },
                            "summary_points": [
                                {"x": "week_0", "x_label": "week_0", "value": 15},
                                {"x": "week_2", "x_label": "week_2", "value": 8.5},
                                {"x": "week_6", "x_label": "week_6", "value": 4.5},
                            ],
                        },
                    },
                }
            ),
        ),
    )


def _mock_analysis_assay_volcano_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_transcriptomics_medication_compare",
                    "reply": "Expression differs between medication-aligned transcriptomics datasets within the current Analysis scope, with exploratory fold-change shifts across multiple genes.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "mode": "transcriptomics_medication_compare",
                            "scope_patient_count": 2,
                            "exploratory_note": "Exploratory transcriptomics comparison based on log2(CPM+1) normalization and a simple per-gene normal-approximation test. This is preliminary and not DESeq2-grade differential expression.",
                            "comparisons": [
                                {
                                    "medication_a": "Infliximab",
                                    "medication_b": "Vedolizumab",
                                    "scoped_patient_ids_a": ["SYN001"],
                                    "scoped_patient_ids_b": ["SYN006"],
                                    "exploratory_volcano_points": [
                                        {
                                            "gene_id": "ENSG000001",
                                            "mean_log2_cpm_a": 8.1,
                                            "mean_log2_cpm_b": 6.7,
                                            "log2_fold_change": 1.4,
                                            "p_value": 0.002,
                                            "neg_log10_p": 2.69,
                                        },
                                        {
                                            "gene_id": "ENSG000002",
                                            "mean_log2_cpm_a": 5.9,
                                            "mean_log2_cpm_b": 7.0,
                                            "log2_fold_change": -1.1,
                                            "p_value": 0.01,
                                            "neg_log10_p": 2.0,
                                        },
                                    ],
                                }
                            ],
                        },
                    },
                }
            ),
        ),
    )


def _mock_query_reply(page) -> None:
    page.route(
        "**/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "disease_cohort",
                    "reply": "Patients matching disease query 'Crohn Disease': SYN001, SYN002.",
                    "data": {
                        "source": "deterministic",
                        "execution": "deterministic",
                        "dataset_id": "default",
                        "dataset_ids": ["default"],
                        "dataset_name": "Synthetic demo",
                        "dataset_names": ["Synthetic demo"],
                        "granularity_requested": "detailed",
                        "granularity_applied": "detailed",
                        "ai_provider_access": "detailed_allowed",
                        "ai_provider_context_granularity": "detailed",
                        "external_llm_allowed": True,
                        "patient_ids": ["SYN001", "SYN002"],
                        "patient_count": 2,
                        "available_actions": {
                            "open_in_analysis": True,
                            "save_cohort": True,
                            "copy_patient_ids": True,
                            "use_in_pheno_ranker": False,
                        },
                        "follow_up_suggestions": ["How many patients take Infliximab?"],
                    },
                    "action_context": {
                        "patient_ids": ["SYN001", "SYN002"],
                        "record_ids": [],
                        "id_type": "patient",
                        "analysis_prompt": "Interpret this selected workspace subset and summarize the main clinical and treatment patterns.",
                    },
                }
            ),
        ),
    )


def _mock_saved_cohorts(page) -> None:
    page.route(
        "**/saved-cohorts?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "cohorts": [
                        {
                            "id": "cohort-a",
                            "name": "Infliximab responders",
                            "data_dir": "data",
                            "patient_ids": ["SYN001", "SYN002"],
                            "id_type": "patient",
                            "source": {"kind": "query", "prompt": "Which patients take Infliximab?"},
                        }
                    ]
                }
            ),
        ),
    )


def _mock_disease_inventory(page) -> None:
    page.route(
        "**/cohorts/diseases?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {"disease": "Crohn Disease", "patient_count": 2, "patients": ["SYN001", "SYN002"]},
                    {"disease": "Ulcerative Colitis", "patient_count": 2, "patients": ["SYN003", "SYN004"]},
                ]
            ),
        ),
    )


def _mock_analysis_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_deterministic",
                    "reply": "This cohort is dominated by Crohn Disease and recurrent Infliximab exposure.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "source": "clinical summary",
                            "notable_findings": ["Crohn Disease enriched", "Infliximab common"],
                        },
                    },
                }
            ),
        ),
    )


def test_primary_wordmark_emphasizes_cohort(page) -> None:
    wordmark = page.locator("#appShell .brand-wordmark")
    primary = wordmark.locator(".brand-wordmark-primary")
    secondary = wordmark.locator(".brand-wordmark-secondary")

    playwright.expect(wordmark).to_have_attribute("aria-label", "COHORTome")
    playwright.expect(primary).to_have_text("COHORT")
    playwright.expect(secondary).to_have_text("ome")
    assert page.title() == "COHORTome"
    assert int(primary.evaluate("element => getComputedStyle(element).fontWeight")) > int(
        secondary.evaluate("element => getComputedStyle(element).fontWeight")
    )
    assert primary.evaluate("element => getComputedStyle(element).color") != secondary.evaluate(
        "element => getComputedStyle(element).color"
    )
    visible_text = page.locator("body").inner_text()
    assert "CohorToMe" not in visible_text
    assert "Cohort2Me" not in visible_text
    assert "Cohortome" not in visible_text


def test_pheno_run_button_requires_prompt(page) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    run_button = page.locator("#phenoRunBtn")
    expect = playwright.expect

    expect(run_button).to_be_disabled()
    page.locator("#phenoPrompt").fill("Find closest matches to SYN005:week_0 by disease")
    expect(run_button).to_be_enabled()


def test_pheno_cohort_run_shows_interactive_plots_and_hides_patient_only_cards(page) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    expect = playwright.expect
    expect(page.locator("#phenoRenderGraph")).to_be_checked()
    _mock_pheno_plan(page, expected_mode="cohort", selected_ids="SYN001:week_0,SYN002:week_0,SYN003:week_0")
    _mock_cohort_run(page)

    page.locator("#phenoPrompt").fill("Cluster these three records by disease")
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed cohort run")
    expect(page.locator("#phenoHeatmapPlot")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#phenoMdsPlot")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#phenoExplainCard")).to_be_hidden()
    expect(page.locator("#phenoAlignmentCard")).to_be_hidden()


def test_pheno_patient_run_shows_patient_only_cards(page) -> None:
    _mock_pheno_reference_ids(page)
    _open_pheno_tab(page)
    _mock_pheno_plan(page, expected_mode="patient", patient_id="SYN001:week_0")
    _mock_patient_run(page)
    expect = playwright.expect

    page.locator("#phenoPrompt").fill("Find closest matches to SYN001:week_0 by disease")
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed patient run")
    expect(page.locator("#phenoExplainCard")).to_be_visible()
    expect(page.locator("#phenoAlignmentCard")).to_be_visible()
    expect(page.locator("#phenoOutputPreview")).to_contain_text("rank.txt loaded as TSV")


def test_dashboard_load_renders_clinical_overview(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#dashboard")).to_contain_text("Patients2")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-medications")).to_have_attribute("data-plotly-ready", "true")


def test_applying_first_dataset_uses_pending_selection_key(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect
    page._cohortome_dataset_state["current_ids"] = []
    page.reload(wait_until="networkidle")
    patient_request_urls = []
    page.on(
        "request",
        lambda request: patient_request_urls.append(request.url)
        if "/patients?" in request.url
        else None,
    )

    page.locator("#datasetsTabBtn").click()
    page.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()
    expect(page.locator("#loadBtnLabel")).to_have_text("Apply workspace")
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#datasetScopeSummary")).to_contain_text("Active workspace: Secondary demo")
    assert patient_request_urls[0].endswith("/patients?dataset_id=secondary")
    assert page._cohortome_dataset_state["current_ids"] == ["secondary"]


def test_workspace_unload_persists_empty_selection_and_clears_dataset_scoped_views(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_query_reply(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")

    _open_query_tab(page)
    page.locator("#question").fill("Which patients have Crohn disease?")
    page.locator("#askBtn").click()
    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")

    _open_analysis_tab(page)
    page.locator("#analysisPrompt").fill("Summarize this workspace")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisThread")).to_contain_text("dominated by Crohn Disease")

    page.locator("#datasetsTabBtn").click()
    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    expect(page.locator("#loadBtnLabel")).to_have_text("Unload workspace")
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_have_text("Workspace unloaded.")
    expect(page.locator("#loadBtn")).to_be_disabled()
    expect(page.locator("#dashboard")).to_contain_text("Select a workspace")
    expect(page.locator("#assayDashboardCards")).to_contain_text("No assays loaded")
    expect(page.locator("#dicomDashboardStudies")).to_contain_text("No DICOM studies loaded")
    expect(page.locator("#multimodalReadinessContent")).to_contain_text("Load a workspace")
    expect(page.locator("#queryThread")).to_contain_text("Ask a query to start")
    expect(page.locator("#analysisThread")).to_contain_text("Run an analysis prompt to start")
    assert page._cohortome_dataset_state["current_ids"] == []
    assert page._cohortome_dataset_state["select_requests"][-1] == []


def test_late_dashboard_response_cannot_repopulate_unloaded_workspace(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect
    pending_dashboard_routes = []
    page.route("**/dashboard?*", lambda route: pending_dashboard_routes.append(route))

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    for _ in range(50):
        if pending_dashboard_routes:
            break
        page.wait_for_timeout(20)
    assert len(pending_dashboard_routes) == 1

    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_have_text("Workspace unloaded.")
    expect(page.locator("#dashboard")).to_contain_text("Select a workspace")

    pending_dashboard_routes[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"patients": 999, "visits": 999}),
    )
    page.wait_for_timeout(100)
    expect(page.locator("#dashboard")).to_contain_text("Select a workspace")
    expect(page.locator("#dashboard")).not_to_contain_text("Patients999")


def test_failed_workspace_switch_keeps_previous_workspace_and_query_state(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_query_reply(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    _open_query_tab(page)
    page.locator("#question").fill("Which patients have Crohn disease?")
    page.locator("#askBtn").click()
    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")

    page.locator("#datasetsTabBtn").click()
    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()
    page._cohortome_dataset_state["fail_next_selection"] = "Secondary dataset store is not ready."
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_have_text("Secondary dataset store is not ready.")
    expect(page.locator("#datasetScopeSummary")).to_contain_text("Active workspace: Synthetic demo")
    expect(page.locator("[data-dataset-card='default'] .dataset-picker-state-active")).to_have_text("Active")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")
    assert page._cohortome_dataset_state["current_ids"] == ["default"]
    assert page._cohortome_dataset_state["select_requests"][-1] == ["secondary"]


def test_failed_assay_preflight_does_not_commit_workspace_switch(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    committed_request_count = len(page._cohortome_dataset_state["select_requests"])

    page.route(
        "**/assays?*",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "Selected dataset assay store is unavailable."}),
        ),
    )
    page.locator("#datasetPicker [data-dataset-checkbox='default']").uncheck()
    page.locator("#datasetPicker [data-dataset-checkbox='secondary']").check()
    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_have_text("Selected dataset assay store is unavailable.")
    expect(page.locator("#datasetScopeSummary")).to_contain_text("Active workspace: Synthetic demo")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    assert page._cohortome_dataset_state["current_ids"] == ["default"]
    assert len(page._cohortome_dataset_state["select_requests"]) == committed_request_count


def test_dashboard_assays_panel_lists_dicom_studies(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_dicom_studies(page)
    _mock_dicom_status(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardAssaysBtn").click()

    expect(page.locator("#dicomDashboardStatus")).to_contain_text("Loaded 1 DICOM study")
    expect(page.locator("#dicomDashboardHealth")).to_contain_text("Orthanc")
    expect(page.locator("#dicomDashboardHealth")).to_contain_text("Reachable")
    expect(page.locator("#dicomDashboardHealth")).to_contain_text("http://ohif.example")
    expect(page.locator("#dicomDashboardStudies")).to_contain_text("Synthetic MRI baseline SYN001")
    expect(page.locator("#dicomDashboardStudies a", has_text="Open in OHIF")).to_have_attribute(
        "href",
        "http://ohif.example/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1",
    )
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()

    page.locator("#dashboardMultimodalBtn").click()

    expect(page.locator("#dashboardMultimodalBtn")).to_have_class(re.compile("active"))
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("Multimodal feature matrix")
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("Sample-level matrix")


def test_dashboard_assays_panel_filters_modalities(page) -> None:
    _mock_dashboard_load(page)
    _mock_multimodal_assay_datasets(page)
    _mock_dicom_studies(page)
    _mock_dicom_status(page)
    _mock_multimodal_readiness(page)
    _mock_multimodal_matrix(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardAssaysBtn").click()

    expect(page.locator("#assayDashboardOverview")).to_contain_text("Datasets")
    expect(page.locator("#assayModalityTabs")).to_contain_text("Transcriptomics")
    expect(page.locator("#assayModalityTabs")).to_contain_text("Imaging")
    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_mri_derived_measurements")
    expect(page.locator("#multimodalReadinessPanel")).not_to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardPanel")).to_be_visible()
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).not_to_be_visible()

    page.locator("#dashboardMultimodalBtn").click()

    expect(page.locator("#multimodalReadinessPanel")).to_be_visible()
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Multimodal analysis readiness")
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Imaging features")
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Review DICOM studies in OHIF")
    expect(page.locator("#multimodalReadinessPanel")).to_contain_text("Requirements met")
    page.locator("[data-readiness-analysis-key='imaging_feature_summary']").click()
    expect(page.locator("#analysisTab")).to_have_class(re.compile("active"))
    expect(page.locator("#analysisPrompt")).to_have_value(re.compile("Summarize the derived imaging features"))

    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardMultimodalBtn").click()
    expect(page.locator("#multimodalMatrixPanel")).to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("MRI derived measurements")
    expect(page.locator("#multimodalMatrixPanel")).to_contain_text("lesion_volume_ml")

    page.locator("#dashboardAssaysBtn").click()

    page.locator("[data-assay-modality-filter='transcriptomics']").click()

    expect(page.locator("[data-assay-modality-filter='transcriptomics']")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#assayDashboardCards")).not_to_contain_text("synthetic_mri_derived_measurements")
    expect(page.locator("#multimodalReadinessPanel")).not_to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardPanel")).not_to_be_visible()
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).to_be_visible()

    page.locator("[data-assay-modality-filter='imaging']").click()

    expect(page.locator("[data-assay-modality-filter='imaging']")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#assayDashboardCards")).to_contain_text("synthetic_mri_derived_measurements")
    expect(page.locator("#assayDashboardCards")).not_to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#multimodalReadinessPanel")).not_to_be_visible()
    expect(page.locator("#multimodalMatrixPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardPanel")).to_be_visible()
    expect(page.locator("#transcriptomicsQuickExpressionPanel")).not_to_be_visible()
    expect(page.locator("#dicomDashboardStudies")).to_contain_text("Synthetic MRI baseline SYN001")


def test_dashboard_load_mounts_plotly_overview_cards(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#dashboard-plot-sex")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-visits")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-medications")).to_have_attribute("data-plotly-ready", "true")


def test_dashboard_timeline_filters_events_and_selects_patient(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()
    page.locator("#dashboardTimelineBtn").click()

    expect(page.locator("#dashboard-plot-timeline")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-timeline-controls")).to_contain_text("Disease")
    expect(page.locator("#dashboard-timeline-controls")).to_contain_text("Treatment")
    expect(page.locator("#dashboard-timeline-controls")).to_contain_text("Assay")
    page.locator("#dashboard-timeline-controls input[value='diseases']").uncheck()
    expect(page.locator("#dashboard-timeline-controls input[value='diseases']")).not_to_be_checked()
    page.evaluate(
        """
        () => {
          const plot = document.getElementById("dashboard-plot-timeline");
          plot._plotlyHandlers.plotly_click({ points: [{ customdata: "SYN002" }] });
        }
        """
    )
    expect(page.locator("#dashboard-timeline-selection-status")).to_contain_text("1 patient selected")
    page.locator("[data-dashboard-event-inspect]").first.click()
    expect(page.locator("#detail")).to_contain_text("Timeline inspector")
    expect(page.locator(".dashboard-timeline-table tbody tr.is-inspected")).to_have_count(1)
    expect(page.locator("[data-dashboard-event-inspect][aria-pressed='true']")).to_have_count(1)
    page.locator("#dashboardTimelineEventSearch").fill("SYN001")
    expect(page.locator("#dashboard-timeline-event-count")).to_contain_text("matching events")
    page.locator("[data-dashboard-event-patient='SYN001']").first.click()
    expect(page.locator("#dashboard-timeline-selection-status")).to_contain_text("2 patients selected")
    page.locator("#dashboardTimelineUseAnalysisBtn").click()
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("SYN001,SYN002")


def test_dashboard_exposes_timeline_for_person_representation(page) -> None:
    _mock_dashboard_load(page, clinical_representation="person")
    _mock_assay_datasets(page)
    expect = playwright.expect

    page.locator("#dashboardTimelineBtn").click()
    expect(page.locator("#dashboardTimelinePanel")).to_have_class(re.compile(r".*active.*"))
    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#dashboardTimelineBtn")).to_be_visible()
    expect(page.locator("#dashboardTimelineBtn")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#dashboardTimelinePanel")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#dashboardTimeline")).to_contain_text("Clinical coverage")
    expect(page.locator("#dashboardTimeline")).to_contain_text("Patient records")


def test_query_deterministic_reply_renders_and_handoff_to_analysis(page) -> None:
    _open_query_tab(page)
    _mock_query_reply(page)
    expect = playwright.expect
    captured = {}
    page.on(
        "request",
        lambda request: captured.setdefault("body", request.post_data_json)
        if request.url.endswith("/query")
        else None,
    )

    page.locator("#question").fill("Which patients have Crohn Disease?")
    page.locator("#askBtn").click()

    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")
    expect(page.locator("#queryThread")).to_contain_text("Dataset: Synthetic demo")
    assert captured["body"]["dataset_id"] == "default"
    assert "data_dir" not in captured["body"]
    expect(page.locator("#queryThread")).to_contain_text("Open in Analysis")
    page.locator("[data-query-action='use-analysis']").click()

    expect(page.locator("#analysisTab")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("SYN001,SYN002")


def test_query_disease_selector_runs_deterministic_cohort(page) -> None:
    _mock_dashboard_load(page)
    _mock_assay_datasets(page)
    _mock_disease_inventory(page)
    _mock_query_reply(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    expect(page.locator("#loadBtn")).to_be_visible()
    page.locator("#loadBtn").click()
    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")

    _open_query_tab(page)
    expect(page.locator("#queryDiseaseStatus")).to_contain_text("Click a disease")

    page.locator("#queryDiseaseBuilderBtn").click()
    expect(page.locator("#queryDiseasePanel")).to_be_visible()
    page.locator("[data-query-disease-chip='Crohn Disease']").click()

    expect(page.locator("#question")).to_have_value("Which patients have Crohn Disease?")
    expect(page.locator("#queryDiseaseStatus")).to_contain_text("Prompt prepared for disease workspace Crohn Disease")


def test_analysis_deterministic_reply_renders_in_thread(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this workspace.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("Crohn Disease and recurrent Infliximab exposure")
    expect(page.locator("#analysisThread")).to_contain_text("Deterministic")


def test_analysis_deterministic_starter_chip_forces_deterministic_mode(page) -> None:
    _open_analysis_tab(page)
    captured = {}

    def handler(route):
        captured["body"] = route.request.post_data_json
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_deterministic",
                    "reply": "### Deterministic Cohort Summary\n\n- **Patients:** 5",
                    "data": {"provider": "deterministic", "context": {"source": "clinical summary"}},
                }
            ),
        )

    page.route("**/analysis", handler)
    page.locator("[data-analysis-prompt='Summarize the main clinical patterns in this workspace and tell me what stands out.']").click()
    page.locator("#analysisRunBtn").click()

    assert captured["body"]["llm_only"] is False
    assert captured["body"]["deterministic_only"] is True
    assert captured["body"]["dataset_id"] == "default"
    assert "data_dir" not in captured["body"]


def test_analysis_llm_starter_chip_blocks_when_lm_unavailable(page) -> None:
    expect = playwright.expect
    page.route(
        "**/lm-status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "available": False,
                    "status": "no_model",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model": "",
                    "detail": "No model loaded.",
                }
            ),
        ),
    )
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)

    analysis_called = {"value": False}

    def unexpected_analysis(route):
        analysis_called["value"] = True
        route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "unexpected"}))

    page.route("**/analysis", unexpected_analysis)
    if page.locator("#analysisStarterPanel .query-chip-toggle").count():
        page.locator("#analysisStarterPanel .query-chip-toggle").click()
    page.locator("[data-analysis-prompt='Interpret the disease and medication profiles in this workspace and summarize the main themes.']").click()
    expect(page.locator("#analysisStatus")).to_contain_text("LLM unavailable")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisStatus")).to_contain_text("LLM unavailable")
    expect(page.locator("#analysisThread")).to_contain_text("LLM unavailable")
    assert analysis_called["value"] is False


def test_analysis_catalog_item_prefills_prompt_and_compare_mode(page) -> None:
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisCatalogBrowseBtn").click()
    expect(page.locator("#analysisCatalogDrawer")).to_be_visible()
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Ready now")
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Needs setup")
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Trajectory analysis")
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='trajectory-single']").click()

    expect(page.locator("#analysisPrompt")).to_have_value(re.compile(r"Show the trajectory of Leukocyte Count over time"))
    expect(page.locator("#analysisCompareMode")).not_to_be_checked()


def test_analysis_queued_job_opens_jobs_drawer_and_loads_result(page) -> None:
    _open_analysis_tab(page)
    expect = playwright.expect

    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_job",
                    "reply": "Submitted External R clinical scope profile as a background job. Open Jobs to monitor progress and view the result when it completes.",
                    "data": {
                        "source": "job",
                        "execution": "queued",
                        "job_id": "job-123",
                        "job_status": "queued",
                        "catalog_item_id": "external-r-clinical-profile",
                        "runner_type": "rscript",
                    },
                }
            ),
        ),
    )
    page.route(
        "**/jobs",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "jobs": [
                        {
                            "job_id": "job-123",
                            "job_type": "analysis",
                            "feature": "analysis",
                            "status": "completed",
                            "submitted_at": "2026-04-18T12:00:00+00:00",
                            "name": "External R clinical scope profile",
                            "catalog_item_id": "external-r-clinical-profile",
                            "runner_type": "rscript",
                            "reply_preview": "External analysis done.",
                            "result_available": True,
                            "artifacts": [
                                {"name": "summary.json", "url": "/jobs/job-123/artifacts/summary.json"},
                                {"name": "workflow/01-deseq2/de_results.tsv", "url": "/jobs/job-123/artifacts/workflow/01-deseq2/de_results.tsv"},
                            ],
                        }
                    ]
                }
            ),
        ),
    )
    page.route(
        "**/jobs/job-123",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "job-123",
                    "job_type": "analysis",
                    "feature": "analysis",
                    "status": "completed",
                    "name": "External R clinical scope profile",
                    "analysis_session_id": "",
                    "result_available": True,
                    "artifacts": [],
                    "result_payload": {
                        "intent": "analysis_external_rscript",
                        "reply": "External analysis done.",
                        "data": {
                            "source": "deterministic",
                            "execution": "external_runner",
                            "context": {"mode": "external_rscript_profile"},
                            "runner_type": "rscript",
                            "job_id": "job-123",
                        },
                    },
                }
            ),
        ),
    )

    page.locator("#analysisPrompt").fill("Run the external R clinical scope profile for the current Analysis scope.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#jobsDrawer")).to_be_visible()
    expect(page.locator("#jobsDrawerList")).to_contain_text("External R clinical scope profile")
    expect(page.locator("#jobsDrawerList details.job-card-artifacts")).not_to_have_attribute("open", "")
    expect(page.locator("#jobsDrawerList .job-card-artifact-links")).to_be_hidden()
    page.locator("#jobsDrawerList details.job-card-artifacts summary").click()
    expect(page.locator("#jobsDrawerList .job-card-artifact-links")).to_be_visible()
    expect(page.locator("#jobsDrawerList .job-card-artifact-links")).to_contain_text("workflow/01-deseq2/de_results.tsv")
    page.locator("[data-job-open-result='job-123']").click()
    expect(page.locator("#jobsDrawer")).to_be_hidden()
    expect(page.locator("#analysisThread")).to_contain_text("External analysis done.")


def test_analysis_open_result_recovers_missing_session(page) -> None:
    _open_analysis_tab(page)
    expect = playwright.expect

    page.route(
        "**/jobs/job-orphaned",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "job-orphaned",
                    "job_type": "analysis",
                    "feature": "analysis",
                    "status": "completed",
                    "name": "Orphaned external result",
                    "prompt": "Run the persisted analysis.",
                    "analysis_session_id": "analysis-orphaned-session",
                    "result_available": True,
                    "artifacts": [],
                    "result_payload": {
                        "intent": "analysis_external_rscript",
                        "reply": "Recovered persisted result.",
                        "data": {
                            "source": "deterministic",
                            "execution": "external_runner",
                            "context": {"mode": "external_rscript_profile"},
                            "runner_type": "rscript",
                            "job_id": "job-orphaned",
                        },
                    },
                }
            ),
        ),
    )

    page.evaluate(
        """
        () => {
          const list = document.getElementById('jobsDrawerList');
          list.innerHTML = '<div class="job-card"><button type="button" class="query-chip action" data-job-open-result="job-orphaned">Open result</button></div>';
          const drawer = document.getElementById('jobsDrawer');
          drawer.classList.remove('is-hidden');
          drawer.setAttribute('aria-hidden', 'false');
        }
        """
    )

    page.locator("[data-job-open-result='job-orphaned']").click()

    expect(page.locator("#jobsDrawer")).to_be_hidden()
    expect(page.locator("#analysisThread")).to_contain_text("Recovered persisted result.")
    expect(page.locator("#analysisSessionList")).to_contain_text("Orphaned external result")


def test_analysis_starter_panel_stays_visible_after_run(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this workspace.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisStarterPanel")).to_be_visible()
    expect(page.locator("#analysisComposerExamplesBtn")).to_contain_text("Prompts")

    page.locator("#analysisComposerExamplesBtn").click()
    expect(page.locator("#analysisStarterPanel")).to_be_visible()
    expect(page.locator("#analysisComposerExamplesBtn")).to_contain_text("Prompts")


def test_analysis_saved_cohort_disables_manual_scope_for_cohort_a(page) -> None:
    _mock_saved_cohorts(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()

    expect(page.locator("#analysisSelectedPatientIds")).to_be_disabled()
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("")
    expect(page.locator("#analysisSelectedPatientIdsSummary")).to_contain_text("using saved cohort")
    expect(page.locator("#analysisSelectedSavedCohortSelection")).to_contain_text("Cohort A source")


def test_analysis_compare_mode_requires_saved_cohorts(page) -> None:
    _mock_saved_cohorts(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()

    expect(page.locator("#analysisSelectedPatientIds")).to_be_disabled()
    expect(page.locator("#analysisCompareSelectedPatientIds")).to_be_hidden()
    expect(page.locator("#analysisSelectedPatientIdsSummary")).to_contain_text("Cohort A: select a saved cohort")
    expect(page.locator("#analysisCompareSelectedPatientIdsSummary")).to_contain_text("Cohort B: select a saved cohort")

    page.locator("#analysisPrompt").fill("Compare Cohort A and Cohort B by disease burden")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisStatus")).to_contain_text("requires saved Cohort A and Cohort B")


def test_analysis_differential_expression_enables_after_saved_cohorts_selected(page) -> None:
    _mock_saved_cohorts(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis-b']").first.click()

    page.locator("#analysisCatalogBrowseBtn").click()


def test_analysis_workflow_filter_shows_assay_dataset_selector(page) -> None:
    _mock_saved_cohorts(page)
    _mock_assay_datasets_with_nonmatching_dataset(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis-b']").first.click()

    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerFilters [data-analysis-catalog-filter='workflow']").click()
    expect(page.locator("#analysisCatalogDrawerList")).to_contain_text("Transcriptomics signature workflow")
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='transcriptomics-signature-workflow']").click()

    expect(page.locator("#analysisCatalogAssayPanel")).to_be_visible()
    expect(page.locator("#analysisCatalogAssayDatasetList")).to_contain_text("synthetic_transcriptome_raw_counts_infliximab")
    expect(page.locator("#analysisCatalogAssayDatasetList")).not_to_contain_text("unrelated_transcriptome_raw_counts")
    expect(page.locator("#analysisCatalogAssayDatasetList input[type='checkbox']")).to_be_checked()
    expect(page.locator("#analysisCatalogAssayStatus")).to_contain_text("Selected assay: synthetic_transcriptome_raw_counts_infliximab")


def test_analysis_workflow_assay_selector_keeps_one_dataset_selected(page) -> None:
    _mock_saved_cohorts(page)
    _mock_assay_datasets_with_two_matching_datasets(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab .analysis-setup-card > summary").click()
    page.locator("#analysisCompareMode").check()
    page.locator("#analysisTab .analysis-setup-saved-cohorts > summary").click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis']").first.click()
    page.locator("#savedCohorts [data-saved-cohort-action='load-analysis-b']").first.click()

    page.locator("#analysisCatalogBrowseBtn").click()
    page.locator("#analysisCatalogDrawerFilters [data-analysis-catalog-filter='workflow']").click()
    page.locator("#analysisCatalogDrawerList [data-analysis-catalog-id='transcriptomics-signature-workflow']").click()

    first_dataset = page.locator("#analysisCatalogAssayDatasetList input[value='synthetic_transcriptome_raw_counts_infliximab']")
    second_dataset = page.locator("#analysisCatalogAssayDatasetList input[value='synthetic_transcriptome_raw_counts_ustekinumab']")
    first_dataset.check()
    expect(first_dataset).to_be_checked()
    second_dataset.check()
    expect(second_dataset).to_be_checked()
    expect(first_dataset).not_to_be_checked()
    expect(page.locator("#analysisCatalogAssayStatus")).to_contain_text("Selected assay: synthetic_transcriptome_raw_counts_ustekinumab")


def test_analysis_deterministic_trajectory_mounts_plotly_cards(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_trajectory_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Show response to Infliximab using CRP.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisComposerStatus")).to_contain_text("Analysis complete")
    expect(page.locator("#analysisThread")).to_contain_text("CRP declines after Infliximab")
    expect(page.locator("#analysisThread")).to_contain_text("Trajectory analysis")
    expect(page.locator("[id$='-trajectory']")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("[id$='-trajectory-coverage']")).to_have_attribute("data-plotly-ready", "true")


def test_analysis_transcriptomics_medication_compare_mounts_volcano_plot(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_assay_volcano_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Explain differences in gene expression according to medication")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("within the current Analysis scope")
    expect(page.locator("#analysisThread")).to_contain_text("Transcriptomics by medication")
    expect(page.locator("#analysisThread")).to_contain_text("Exploratory transcriptomics comparison")
    expect(page.locator("#analysisThread")).to_contain_text("Positive log2FC means higher in Infliximab")
    expect(page.locator("#analysisThread")).to_contain_text("gray = everything else")
    expect(page.locator("[id*='assay-volcano-']")).to_have_attribute("data-plotly-ready", "true")


def test_pheno_manual_metric_override_skips_planner_and_shows_notice(page) -> None:
    _open_pheno_tab(page)
    expect = playwright.expect
    plan_calls = {"count": 0}
    request_capture = {}

    def unexpected_plan(route):
        plan_calls["count"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"source": "deterministic", "reasoning": [], "plan": {}}),
        )

    page.route("**/pheno-ranker/plan", unexpected_plan)
    _mock_cohort_run(page, metric="jaccard", request_capture=request_capture)

    page.locator("#phenoPrompt").fill("Compare all patients by phenotypicFeatures and diseases")
    page.locator("#phenoTab summary").filter(has_text="Setup").click()
    page.locator("#phenoTab summary").filter(has_text="Advanced options").click()
    page.locator("#phenoSimilarityMetric").select_option("jaccard")

    expect(page.locator("#phenoPlanStatus")).to_contain_text("Settings changed after preview")
    expect(page.locator("#phenoPlan")).to_contain_text('"similarity_metric_cohort": "jaccard"')
    expect(page.locator("#phenoPrompt")).to_have_value(re.compile("Use jaccard cohort similarity"))
    page.locator("#phenoPlanBtn").click()
    expect(page.locator("#phenoPlanStatus")).to_contain_text("Previewing current form settings")
    expect(page.locator("#phenoSimilarityMetric")).to_have_value("jaccard")
    expect(page.locator("#phenoPlan")).to_contain_text('"similarity_metric_cohort": "jaccard"')
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed cohort run")
    assert plan_calls["count"] == 0
    assert request_capture["body"]["similarity_metric_cohort"] == "jaccard"
    assert "Use jaccard cohort similarity" in request_capture["body"]["prompt"]


def test_pheno_mds_cohort_chips_render_for_prefixed_ids(page) -> None:
    _open_pheno_tab(page)
    _mock_pheno_plan(page, expected_mode="cohort", selected_ids="SYN001,SYN002,SYN003")
    _mock_cohort_run(page, prefixed_ids=True)
    expect = playwright.expect

    page.locator("#phenoPrompt").fill("Cluster these three records by disease")
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoMdsPlot")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#phenoMdsCohortLegend")).to_contain_text("C1")
    expect(page.locator("#phenoMdsCohortLegend")).to_contain_text("C2")


def test_local_auth_gates_dataset_loading_to_admin(page_auth) -> None:
    _mock_dashboard_load(page_auth)
    _mock_assay_datasets(page_auth)
    expect = playwright.expect

    expect(page_auth.locator("#authGate")).to_be_visible()
    expect(page_auth.locator("#appShell")).to_be_hidden()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Signed out")
    expect(page_auth.locator("#datasetsTabBtn")).to_be_hidden()
    expect(page_auth.locator("#dataTabBtn")).to_be_hidden()
    expect(page_auth.locator("#usersTabBtn")).to_be_hidden()

    page_auth.locator("#authUsername").fill("admin")
    page_auth.locator("#authPassword").fill("secret")
    page_auth.locator("#authLoginBtn").click()

    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User")
    expect(page_auth.locator("#authGate")).to_be_hidden()
    expect(page_auth.locator("#appShell")).to_be_visible()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User")
    expect(page_auth.locator("#datasetsTabBtn")).to_be_visible()
    expect(page_auth.locator("#dataTabBtn")).to_be_visible()
    expect(page_auth.locator("#usersTabBtn")).to_be_visible()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User (admin)")
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    page_auth.wait_for_load_state("networkidle")

    page_auth.locator("#dataTabBtn").click()
    admin_card = page_auth.locator("#datasetAdminList [data-dataset-admin-card]").first
    expect(admin_card).to_be_visible()
    expect(admin_card).not_to_have_attribute("open", "")
    expect(admin_card.locator(".dataset-admin-body")).to_be_hidden()
    admin_card.locator("summary").click()
    expect(admin_card.locator(".dataset-admin-body")).to_be_visible()

    page_auth.locator("#usersTabBtn").click()
    user_card = page_auth.locator("#usersList [data-auth-user-card]").first
    expect(user_card).to_be_visible()
    expect(user_card).not_to_have_attribute("open", "")
    expect(user_card.locator(".dataset-admin-body")).to_be_hidden()
    user_card.locator("summary").click()
    expect(user_card.locator(".dataset-admin-body")).to_be_visible()

    page_auth.locator("#datasetsTabBtn").click()
    expect(page_auth.locator("#loadBtn")).to_be_visible()
    expect(page_auth.locator("#loadBtn")).to_be_enabled()
    page_auth.locator("#loadBtn").click()
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")

    page_auth.locator("#heroLogoutBtn").click()
    expect(page_auth.locator("#authGate")).to_be_visible()
    expect(page_auth.locator("#appShell")).to_be_hidden()
