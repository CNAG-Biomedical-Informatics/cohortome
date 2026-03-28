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


@pytest.fixture(scope="session")
def live_server() -> str:
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
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


def _open_pheno_tab(page) -> None:
    page.locator("#phenoTabBtn").click()
    page.locator("#phenoPrompt").wait_for()


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
        "**/patients?data_dir=*",
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
        "**/dashboard?data_dir=*",
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
    _open_pheno_tab(page)
    run_button = page.locator("#phenoRunBtn")
    expect = playwright.expect

    expect(run_button).to_be_disabled()
    page.locator("#phenoPrompt").fill("Find closest matches to SYN005:week_0 by disease")
    expect(run_button).to_be_enabled()


def test_pheno_cohort_run_shows_interactive_plots_and_hides_patient_only_cards(page) -> None:
    _open_pheno_tab(page)
    _mock_pheno_plan(page, expected_mode="cohort", selected_ids="SYN001,SYN002,SYN003")
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
    expect = playwright.expect

    page.locator("#loadBtn").click()

    expect(page.locator("#loadStatus")).to_contain_text("Loaded 2 patients.")
    expect(page.locator("#patients")).to_contain_text("SYN001")
    expect(page.locator("#patients")).to_contain_text("SYN002")


def test_query_deterministic_reply_renders_and_handoff_to_analysis(page) -> None:
    _open_query_tab(page)
    _mock_query_reply(page)
    expect = playwright.expect

    page.locator("#question").fill("Which patients have Crohn Disease?")
    page.locator("#askBtn").click()

    expect(page.locator("#queryThread")).to_contain_text("Patients matching disease query")
    expect(page.locator("#queryThread")).to_contain_text("Open cohort in Analysis")
    page.locator("[data-query-action='use-analysis']").click()

    expect(page.locator("#analysisTab")).to_have_class(re.compile(r".*active.*"))
    expect(page.locator("#analysisSelectedPatientIds")).to_have_value("SYN001,SYN002")


def test_analysis_deterministic_reply_renders_in_thread(page) -> None:
    _open_analysis_tab(page)
    _mock_analysis_reply(page)
    expect = playwright.expect

    page.locator("#analysisPrompt").fill("Summarize the main clinical patterns in this cohort.")
    page.locator("#analysisRunBtn").click()

    expect(page.locator("#analysisThread")).to_contain_text("Crohn Disease and recurrent Infliximab exposure")
    expect(page.locator("#analysisThread")).to_contain_text("Deterministic")


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
    expect(page.locator("#phenoMdsCohortLegend")).to_contain_text("Cohort 1")
    expect(page.locator("#phenoMdsCohortLegend")).to_contain_text("Cohort 2")
