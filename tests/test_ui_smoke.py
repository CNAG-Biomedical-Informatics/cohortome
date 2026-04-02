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


@pytest.fixture(scope="session")
def live_server() -> str:
    process, base_url = _spawn_live_server()
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
def live_server_auth() -> str:
    process, base_url = _spawn_live_server(
        {
            "PN_AUTH_MODE": "local",
            "PN_LOCAL_USERS_JSON": json.dumps(
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
            page.goto(live_server_auth, wait_until="networkidle")
            yield page
            context.close()
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"Playwright browser is unavailable: {exc}")


def _open_pheno_tab(page) -> None:
    page.locator("#phenoTabBtn").click()
    page.locator("#phenoPrompt").wait_for()


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
    page.locator("#loadBtn").click()


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


def _mock_dashboard_load(page) -> None:
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
                    "patients": 2,
                    "visits": 9,
                    "top_diseases": [["Crohn Disease", 2]],
                    "top_treatments": [["Infliximab", 1]],
                    "sex_counts": {"female": 1, "male": 1},
                    "disease_medication_matrix": {
                        "diseases": ["Crohn Disease"],
                        "medications": ["Infliximab"],
                        "values": [[1]],
                    },
                }
            ),
        ),
    )


def _mock_molecular_datasets(page) -> None:
    page.route(
        "**/molecular/datasets?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_name": "synthetic_transcriptome_raw_counts_infliximab",
                            "modality": "transcriptomics_raw_counts",
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


def _mock_analysis_molecular_volcano_reply(page) -> None:
    page.route(
        "**/analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "intent": "analysis_molecular_medication_compare",
                    "reply": "Expression differs between medication-aligned transcriptomics datasets within the current Analysis scope, with exploratory fold-change shifts across multiple genes.",
                    "data": {
                        "provider": "deterministic",
                        "context": {
                            "mode": "molecular_medication_compare",
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
                        "provider": "deterministic",
                        "patient_ids": ["SYN001", "SYN002"],
                        "patient_count": 2,
                        "follow_up_suggestions": ["How many patients take Infliximab?"],
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
    _mock_pheno_plan(page, expected_mode="cohort", selected_ids="SYN001:week_0,SYN002:week_0,SYN003:week_0")
    _mock_cohort_run(page)
    expect = playwright.expect

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


def test_dashboard_load_renders_patients_and_dashboard_cards(page) -> None:
    _mock_dashboard_load(page)
    _mock_molecular_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#patients")).to_contain_text("SYN001")
    expect(page.locator("#patients")).to_contain_text("SYN002")


def test_dashboard_load_mounts_plotly_overview_cards(page) -> None:
    _mock_dashboard_load(page)
    _mock_molecular_datasets(page)
    expect = playwright.expect

    page.locator("#datasetsTabBtn").click()
    page.locator("#loadBtn").click()
    page.locator("#dashboardTabBtn").click()

    expect(page.locator("#dashboard-plot-sex")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-visits")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-diseases")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("#dashboard-plot-medications")).to_have_attribute("data-plotly-ready", "true")


def test_query_deterministic_reply_renders_and_handoff_to_analysis(page) -> None:
    _open_query_tab(page)
    _mock_query_reply(page)
    expect = playwright.expect

    page.locator("#question").fill("Which patients have Crohn Disease?")
    page.locator("#askBtn").click()

    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")
    expect(page.locator("#queryThread")).to_contain_text("Open in Analysis")
    page.locator("[data-query-action='use-analysis']").click()

    expect(page.locator("#analysisTab")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("SYN001,SYN002")


def test_query_disease_selector_runs_deterministic_cohort(page) -> None:
    _mock_dashboard_load(page)
    _mock_molecular_datasets(page)
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


def test_analysis_starter_panel_stays_visible_after_run(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this workspace.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisStarterPanel")).to_be_visible()
    expect(page.locator("#analysisComposerExamplesBtn")).to_contain_text("Starter prompts")

    page.locator("#analysisComposerExamplesBtn").click()
    expect(page.locator("#analysisStarterPanel")).to_be_visible()
    expect(page.locator("#analysisComposerExamplesBtn")).to_contain_text("Starter prompts")


def test_analysis_saved_cohort_disables_manual_scope_for_cohort_a(page) -> None:
    _mock_saved_cohorts(page)
    page.reload(wait_until="networkidle")
    _open_analysis_tab(page)
    expect = playwright.expect

    page.locator("#analysisTab summary").filter(has_text="Saved Cohorts").click()
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

    page.locator("#analysisCompareMode").check()

    expect(page.locator("#analysisSelectedPatientIds")).to_be_disabled()
    expect(page.locator("#analysisCompareSelectedPatientIds")).to_be_hidden()
    expect(page.locator("#analysisSelectedPatientIdsSummary")).to_contain_text("Cohort A: select a saved cohort")
    expect(page.locator("#analysisCompareSelectedPatientIdsSummary")).to_contain_text("Cohort B: select a saved cohort")

    page.locator("#analysisPrompt").fill("Compare Cohort A and Cohort B by disease burden")
    page.locator("#analysisRunBtn").click()
    expect(page.locator("#analysisStatus")).to_contain_text("requires saved Cohort A and Cohort B")


def test_analysis_deterministic_trajectory_mounts_plotly_cards(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_trajectory_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Show response to Infliximab using CRP")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("CRP declines after Infliximab")
    expect(page.locator("#analysisThread")).to_contain_text("Trajectory analysis")
    expect(page.locator("[id$='-trajectory']")).to_have_attribute("data-plotly-ready", "true")
    expect(page.locator("[id$='-trajectory-coverage']")).to_have_attribute("data-plotly-ready", "true")


def test_analysis_molecular_medication_compare_mounts_volcano_plot(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_molecular_volcano_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Explain differences in gene expression according to medication")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("within the current Analysis scope")
    expect(page.locator("#analysisThread")).to_contain_text("Molecular by medication")
    expect(page.locator("#analysisThread")).to_contain_text("Exploratory transcriptomics comparison")
    expect(page.locator("#analysisThread")).to_contain_text("Positive log2FC means higher in Infliximab")
    expect(page.locator("#analysisThread")).to_contain_text("gray = everything else")
    expect(page.locator("[id*='molecular-volcano-']")).to_have_attribute("data-plotly-ready", "true")


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
    page.locator("summary").filter(has_text="Advanced options").click()
    page.locator("#phenoSimilarityMetric").select_option("jaccard")

    expect(page.locator("#phenoManualOverrideNote")).to_be_visible()
    page.locator("#phenoRunBtn").click()

    expect(page.locator("#phenoStatus")).to_contain_text("Completed cohort run")
    assert plan_calls["count"] == 0
    assert request_capture["body"]["similarity_metric_cohort"] == "jaccard"


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
    _mock_molecular_datasets(page_auth)
    expect = playwright.expect

    expect(page_auth.locator("#authGate")).to_be_visible()
    expect(page_auth.locator("#appShell")).to_be_hidden()
    expect(page_auth.locator("#contextAuth")).to_contain_text("Signed out")
    expect(page_auth.locator("#datasetsTabBtn")).to_be_hidden()
    expect(page_auth.locator("#dataTabBtn")).to_be_hidden()
    expect(page_auth.locator("#usersTabBtn")).to_be_hidden()

    page_auth.locator("#authUsername").fill("admin")
    page_auth.locator("#authPassword").fill("secret")
    page_auth.locator("#authLoginBtn").click()

    expect(page_auth.locator("#authGate")).to_be_hidden()
    expect(page_auth.locator("#appShell")).to_be_visible()
    expect(page_auth.locator("#heroAuthIdentity")).to_contain_text("Admin User")
    expect(page_auth.locator("#datasetsTabBtn")).to_be_visible()
    expect(page_auth.locator("#dataTabBtn")).to_be_visible()
    expect(page_auth.locator("#usersTabBtn")).to_be_visible()
    expect(page_auth.locator("#contextAuth")).to_contain_text("Admin User (admin)")

    page_auth.locator("#datasetsTabBtn").click()
    expect(page_auth.locator("#loadBtn")).to_be_visible()
    expect(page_auth.locator("#loadBtn")).to_be_enabled()
    page_auth.locator("#loadBtn").click()
    expect(page_auth.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")

    page_auth.locator("#heroLogoutBtn").click()
    expect(page_auth.locator("#authGate")).to_be_visible()
    expect(page_auth.locator("#appShell")).to_be_hidden()
