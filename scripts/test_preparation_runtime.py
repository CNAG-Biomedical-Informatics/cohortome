"""Check installed preparation tools with one fictional subject, without downloads."""
from pathlib import Path
import tempfile

from app.geo_gse85034 import clinical_inputs, codebook_path, convert_clinical, preflight
from app.preparation_tools import preparation_command
from app.source_builders.common import encode_subjects


def check():
    preflight()
    with tempfile.TemporaryDirectory(prefix="cohortome-preparation-check-") as temporary:
        work = Path(temporary)
        records, _, inputs = clinical_inputs([
            dict(sample_id="TEST-S1", title="Subject 1 example", treatment="ADA",
                 timepoint="LS", tissue="skin", pasi="7.5")
        ])
        convert_clinical(records, inputs, work, preparation_command("convert-pheno"))
        if (records[0]["diseases"][0]["diseaseCode"]["id"] != "NCIT:C3346"
                or records[0]["measures"][0]["measurementValue"]["quantity"]["value"] != 7.5):
            raise RuntimeError("Preparation runtime changed the fictional clinical record")
        # This shared encoder verifies both human/stub round trips and condition names.
        subjects = [dict(unique_id="TEST-1", subject_id=1, study="TEST", type="Case",
                         condition="L40.9", sex="Not Available", age_group="Not Available")]
        encode_subjects(subjects, work / "identifiers", preparation_command("clarid-tools"),
                        codebook_path(), "TEST", "TST")
        if subjects[0]["condition_name"] != "Psoriasis, unspecified":
            raise RuntimeError("Unexpected ClarID condition description")
    print("PASS: Convert-Pheno clinical mapping and ClarID human/stub round trips")


if __name__ == "__main__":
    check()
