import pytest
from pathlib import Path
import app.analysis as analysis
from app.analysis_measurements import measurement_options, validate_measurement
from bff_test_helpers import write_json


@pytest.fixture
def clinical(tmp_path):
    records = []
    for patient, dates in [("P1", ["2024-01-01", "2024-02-01"]),
                           ("P2", ["2024-01-01"]), ("P3", ["invalid"])]:
        for index, day in enumerate(dates):
            records.append({"id": f"{patient}:v{index}", "event_date": day,
                            "measures": [{"assayCode": {"label": "Marker"},
                                          "measurementValue": {"quantity": {"value": index + 1, "unit": {"label": "mg/L"}}}}]})
    write_json(tmp_path, "records.json", records)
    return str(tmp_path)


def test_measurement_inventory_dates_and_group_coverage(clinical):
    entry = measurement_options(clinical)[0]
    assert entry["groups"] == [{"patient_count": 3, "dated_patient_count": 2, "repeated_patient_count": 1}]
    assert entry["units"] == ["mg/L"]
    with pytest.raises(RuntimeError, match="two distinct dates"):
        validate_measurement(clinical, "Marker", "P1", "P2", True)
    with pytest.raises(RuntimeError, match="not available"):
        validate_measurement(clinical, "Unknown")
    with pytest.raises(RuntimeError, match="Choose"):
        validate_measurement(clinical, "")


def test_selected_marker_overrides_example_prompt(clinical, monkeypatch):
    monkeypatch.setattr(analysis, "clinical_representation", lambda _: "snapshot")
    result = analysis.analysis_llm_reply("Show the trajectory of Absent marker over time.", clinical,
                                         catalog_item_id="trajectory-single", measurement="Marker")
    assert result["data"]["context"]["measure"] == "Marker"
    assert result["data"]["measurement"] == "Marker"
    with pytest.raises(RuntimeError, match="Choose a clinical measurement"):
        analysis.analysis_llm_reply("Show the trajectory of Marker over time.", clinical,
                                    catalog_item_id="trajectory-single")
    with pytest.raises(RuntimeError, match="Detailed"):
        analysis.analysis_llm_reply("Show the trajectory of Marker over time.", clinical,
                                    catalog_item_id="trajectory-single", measurement="Marker", granularity_ceiling="counts")


def test_measurement_units_not_silently_mixed(clinical):
    write_json(Path(clinical), "extra.json", [{"id": "P4:v0", "event_date": "2024-01-01",
                                        "measures": [{"assayCode": {"label": "Marker"}, "value": 1}]}])
    with pytest.raises(RuntimeError, match="inconsistent units"):
        validate_measurement(clinical, "Marker")


def test_measurement_endpoint_resolves_scope_and_enforces_access(clinical, monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app import routes
    from app.schemas import AnalysisRequest
    monkeypatch.setattr(routes, "require_authenticated", lambda _: None)
    monkeypatch.setattr(routes, "resolve_dataset_ids", lambda *a: ["test-study"])
    monkeypatch.setattr(routes, "resolve_dataset_dir", lambda *a: clinical)
    monkeypatch.setattr(routes, "effective_query_granularity_ceiling", lambda _: "detailed")
    request = AnalysisRequest(prompt="Inputs", dataset_id="test-study", selected_patient_ids="P2")
    payload = routes.get_analysis_measurements(request, SimpleNamespace())
    assert payload["measurements"][0]["groups"][0]["patient_count"] == 1
    assert "patient_ids" not in str(payload)
    monkeypatch.setattr(routes, "effective_query_granularity_ceiling", lambda _: "counts")
    with pytest.raises(HTTPException) as exc:
        routes.get_analysis_measurements(request, SimpleNamespace())
    assert exc.value.status_code == 403


def test_survival_uses_selected_measurement_and_checks_minimum(clinical, monkeypatch):
    monkeypatch.setattr(analysis, "clinical_representation", lambda _: "snapshot")
    result = analysis.analysis_llm_reply("Show a Kaplan-Meier curve for time to Other > 1.", clinical,
                                        catalog_item_id="survival-single", measurement="Marker")
    assert result["data"]["context"]["measure"] == "Marker"
    with pytest.raises(RuntimeError, match="at least two patients"):
        analysis.analysis_llm_reply("Show a Kaplan-Meier curve for time to Other > 1.", clinical,
                                    catalog_item_id="survival-single", measurement="Marker", selected_patient_ids="P1")
