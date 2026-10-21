"""Local IBDMDB preparation using the reviewed Store clinical/assay adapters."""
import json
from pathlib import Path
import shutil

from app.geo_gse85034 import codebook_path
from app.geo_source import SourcePreparationError
from app.preparation_tools import preparation_command
from app.source_builders import ibdmdb_assays, ibdmdb_clinical
from app.source_builders.common import encode_subjects, write_json


def prepare(source, package, check_cancel, report):
    clinical = package.parent / "clinical-work"
    report(message="Mapping IBDMDB clinical visits with Convert-Pheno…")
    ibdmdb_clinical.prepare(source / "ibdmdb-metadata.csv", clinical,
        preparation_command("convert-pheno"), Path(__file__).with_name("ibdmdb_clinical.yaml"))
    check_cancel()
    report(message="Preparing metabolomics, metaproteomics and serology locally…")
    counts = ibdmdb_assays.prepare(source, package, clinical / "individuals.json")
    records = json.loads((package / "clinical/records.json").read_text())
    people = {}
    for record in records:
        value = (record["info"]["study_group"], record["sex"]["label"])
        pid = record["patient_id"]
        if pid in people and people[pid] != value:
            raise SourcePreparationError("Conflicting IBDMDB subject metadata.")
        people[pid] = value
    if (len(people), len(records), sum(len(r["measures"]) for r in records)) != (112, 898, 224):
        raise SourcePreparationError("IBDMDB clinical counts differ from the reviewed recipe.")
    expected = {"metabolomics": (546, 81867), "proteomics": (450, 11284), "serology": (210, 5)}
    if any((counts[k]["samples"], counts[k]["features"]) != v for k, v in expected.items()):
        raise SourcePreparationError("IBDMDB assay counts differ from the reviewed recipe.")
    conditions = {"Crohn disease": "K50.9", "Ulcerative colitis": "K51.9", "Non-IBD comparison group": "Z00.00"}
    subjects = [dict(unique_id=pid, subject_id=i, study="IBDMDB", type="Control" if group == "Non-IBD comparison group" else "Case",
        condition=conditions[group], sex=sex, age_group="Not Available")
        for i, (pid, (group, sex)) in enumerate(sorted(people.items()), 1)]
    check_cancel()
    report(message="Generating IBDMDB subject ClarIDs…")
    encode_subjects(subjects, package / "identifiers", preparation_command("clarid-tools"), codebook_path(), "IBDMDB", "IBD")
    manifest = json.loads((package / "manifest.json").read_text())
    manifest["identifiers"] = {"clarid_subjects": dict(entity="subject", file="identifiers/clarid_subjects.csv",
        delimiter=",", codebook_version="0.04", tools_version="0.04")}
    write_json(package / "manifest.json", manifest)
    provenance = package / "provenance"
    provenance.mkdir()
    for name in ("clinical.yaml", "clinical.csv", "mapping-audit.json", "terminology.tsv"):
        shutil.copyfile(clinical / name, provenance / name)
    shutil.copyfile(Path(__file__).with_name("ibdmdb_README.md"), package / "README.md")
    return dict(patients=112, snapshots=898, measures=224, assays=counts)
