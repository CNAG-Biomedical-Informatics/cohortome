import gzip
import hashlib
import json

import httpx
import pytest

from app import geo_source as source
from app import geo_gse85034 as recipe


def test_download_checksum_redirect_size_and_cleanup(tmp_path, monkeypatch):
    data = b"fictional source"
    monkeypatch.setitem(source.GSE85034, "bytes", len(data))
    monkeypatch.setitem(source.GSE85034, "sha256", hashlib.sha256(data).hexdigest())
    real_client = httpx.Client
    calls = []

    def response(request):
        calls.append(request)
        assert "authorization" not in request.headers
        return httpx.Response(200, content=data)

    monkeypatch.setattr(source.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(response), **kw))
    target = tmp_path / "source.gz"
    source.fetch_source(target)
    assert target.read_bytes() == data
    assert str(calls[0].url) == source.GSE85034["url"]
    # Never overwrite/delete a file we did not create.
    with pytest.raises(FileExistsError):
        source.fetch_source(target)
    assert target.read_bytes() == data
    target.unlink()
    monkeypatch.setitem(source.GSE85034, "sha256", "0" * 64)
    with pytest.raises(source.SourcePreparationError, match="differs"):
        source.fetch_source(target)
    assert not target.exists()
    monkeypatch.setitem(source.GSE85034, "bytes", 1)
    with pytest.raises(source.SourcePreparationError, match="exceeds"):
        source.fetch_source(target)
    assert not target.exists()
    monkeypatch.setattr(source.httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda req: httpx.Response(302, headers={"location": "https://example.com"})), **kw))
    with pytest.raises(source.SourcePreparationError, match="unavailable"):
        source.fetch_source(target)
    assert not target.exists()


def rows():
    return [dict(sample_id="S1", title="Subject 1 example", treatment="ADA", timepoint="LS", tissue="skin", pasi="7.5"),
            dict(sample_id="S2", title="Subject 1 example", treatment="ADA", timepoint="NL", tissue="skin", pasi="7.5"),
            dict(sample_id="S3", title="Subject 1 example", treatment="ADA", timepoint="WK 1NL", tissue="skin", pasi="NA")]


def test_visits_do_not_turn_biopsies_into_patients():
    records, samples, inputs = recipe.clinical_inputs(rows())
    assert len(records) == 2 and len(samples) == 3
    assert len({r["patient_id"] for r in records}) == 1
    assert records[0]["info"]["days_from_baseline"] == 0
    assert "days_from_baseline" not in records[1]["info"]
    assert inputs[1]["pasi"] == ""
    assert samples[1]["tissue"] == "Non-lesional skin"
    changed = rows()
    changed[1]["pasi"] = "8"
    with pytest.raises(source.SourcePreparationError, match="Conflicting"):
        recipe.clinical_inputs(changed)


def matrix(tmp_path, body):
    path = tmp_path / "source.gz"
    with gzip.open(path, "wt") as handle:
        handle.write('!series_matrix_table_begin\n"ID_REF"\t"S2"\t"S1"\t"S3"\n' + body)
    return path


def test_streamed_matrix_aligns_by_identifier_preserves_values(tmp_path):
    _, samples, _ = recipe.clinical_inputs(rows())
    path = matrix(tmp_path, 'probe1\t1.23456789012345\t-2.5\tNA\n!series_matrix_table_end\n')
    output = tmp_path / "out.csv"
    assert recipe.expression(path, output, samples) == 1
    assert output.read_text().splitlines()[1] == "probe1,-2.5,1.23456789012345,"


@pytest.mark.parametrize("body", [
    "probe1\t1\t2\t3\n",  # missing end marker
    "probe1\t1\t2\t3\nprobe1\t1\t2\t3\n!series_matrix_table_end\n",
    "probe1\t1\tinf\t3\n!series_matrix_table_end\n",
    "probe1\t1\t2\n!series_matrix_table_end\n",
])
def test_bad_matrix_is_rejected(tmp_path, body):
    _, samples, _ = recipe.clinical_inputs(rows())
    with pytest.raises(source.SourcePreparationError):
        recipe.expression(matrix(tmp_path, body), tmp_path / "out.csv", samples)


def test_mapping_discards_placeholder_demographics(tmp_path, monkeypatch):
    records, _, inputs = recipe.clinical_inputs(rows()[:2])
    def convert(*args, **kwargs):
        (tmp_path / "converted.json").write_text(json.dumps([dict(
            id=records[0]["id"], sex={"id": "placeholder"},
            diseases=[{"diseaseCode": {"id": "NCIT:C3346"}}],
            treatments=[{"treatmentCode": {"id": "NCIT:C65216"}}],
            measures=[dict(assayCode={"id": "NCIT:C135734"}, measurementValue={"quantity": {
                "value": 7.5, "unit": {"id": "UCUM:1"}, "referenceRange": "not supplied"}})]
        )]))
    monkeypatch.setattr(recipe.subprocess, "run", convert)
    result = recipe.convert_clinical(records, inputs, tmp_path, ["converter"])[0]
    assert "sex" not in result
    assert "referenceRange" not in result["measures"][0]["measurementValue"]["quantity"]
    assert result["info"]["visit_id"] == "Baseline"


def test_source_terms_required_before_job_creation(monkeypatch):
    from fastapi import HTTPException
    from app import resource_install as installer
    monkeypatch.setattr(installer, "require_admin", lambda request: {"username": "test"})
    with pytest.raises(HTTPException) as error:
        installer.start_download(installer.DownloadRequest(dataset_id="gse85034"), None)
    assert error.value.status_code == 400
    assert "terms" in error.value.detail


def test_source_review_is_server_stamped_and_not_exposed_in_job(monkeypatch, tmp_path):
    from app import resource_install as installer
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(installer, "require_admin", lambda request: {"username": "reviewer"})
    monkeypatch.setattr(recipe, "preflight", lambda: None)
    monkeypatch.setattr(installer, "import_root", lambda root: tmp_path)
    monkeypatch.setattr(installer, "_jobs", {})
    submitted = []
    monkeypatch.setattr(ThreadPoolExecutor, "submit", lambda self, *args: submitted.append(args))
    result = installer.start_download(installer.DownloadRequest(
        dataset_id="gse85034", source_terms_acknowledged=True), None)
    job = submitted[0][1]
    review = job["_source_review"]
    assert review["acknowledged_by"] == "reviewer"
    assert review["acknowledged_at"].endswith("+00:00")
    assert review["source_policy_url"] == "https://www.ncbi.nlm.nih.gov/geo/info/disclaimer.html"
    assert review["statement"].startswith("I have reviewed")
    assert "_source_review" not in result
