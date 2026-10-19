"""Reference selection needs no external executable; fixtures are synthetic."""
import json

import pytest
from fastapi import HTTPException

from app.pheno import extract_selected_records


def test_packaged_perl_command_preserves_paths_with_spaces(monkeypatch):
    import app.pheno as pheno
    monkeypatch.setattr(pheno, "app_env", lambda key, default="": "C:/Program Files/COHORTome/perl.exe")
    monkeypatch.setattr(pheno, "PHENO_RANKER_BIN", "C:/Program Files/COHORTome/pheno-ranker")
    assert pheno.pheno_ranker_command() == [
        "C:/Program Files/COHORTome/perl.exe", "C:/Program Files/COHORTome/pheno-ranker"]


def test_selection_matches_patient_or_record_across_files(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    first = {"id": "SYN001:v1", "patient_id": "SYN001", "label": "Málaga"}
    second = {"id": "SYN001:v2", "patient_id": "SYN001"}
    third = {"id": "SYN002:v1", "patient_id": "SYN002"}
    paths = [tmp_path / "array.json", tmp_path / "object.json"]
    paths[0].write_text(json.dumps([first, [second], None, 42,
                                   {"id": "other"}, {"id": []}]), encoding="utf-8")
    paths[1].write_text(json.dumps(third), encoding="utf-8")
    output = tmp_path / "selected.json"

    command, result, records = extract_selected_records(paths, ["SYN001", "SYN002:v1"], output)

    assert records == [first, second, third]
    assert json.loads(output.read_text()) == records
    assert command[0] == "internal:extract-selected-records"
    assert result.returncode == 0
    assert result.stdout == "Selected 3 records.\n"
    assert "Málaga" not in result.stdout


@pytest.mark.parametrize("ids,status", [([], 400), (["absent"], 404), (["SYN001", "absent"], 404)])
def test_selection_rejects_empty_or_incomplete_scope(tmp_path, ids, status):
    source = tmp_path / "records.json"
    source.write_text(json.dumps([{"id": "SYN001"}]), encoding="utf-8")
    output = tmp_path / "selected.json"
    with pytest.raises(HTTPException) as error:
        extract_selected_records([source], ids, output)
    assert error.value.status_code == status
    assert not output.exists()


@pytest.mark.parametrize("content", [None, "not valid JSON", '{"id":'])
def test_selection_reports_unreadable_reference_without_partial_output(tmp_path, content):
    valid = tmp_path / "valid.json"
    valid.write_text('[{"id":"SYN001"}]', encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    if content is not None:
        invalid.write_text(content, encoding="utf-8")
    output = tmp_path / "selected.json"
    with pytest.raises(HTTPException) as error:
        extract_selected_records([valid, invalid], ["SYN001"], output)
    assert error.value.status_code == 500
    assert error.value.detail == "Could not read Pheno-Ranker reference JSON."
    assert not output.exists()
