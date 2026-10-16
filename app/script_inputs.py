"""Prepared input contract for the synthetic-only custom-script prototype."""
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_ROOT = ROOT / "synthetic_autoimmune_demo"
PACKAGES = {"numpy": "2.2.6", "pandas": "2.2.3", "scipy": "1.15.3", "matplotlib": "3.10.3", "statsmodels": "0.14.4"}
R_PACKAGES = {"base": "4.2.2", "limma": "3.54.1", "edgeR": "3.40.2", "ggplot2": "3.4.1"}


def approved_inputs(data_dir):
    # Do not trust a dataset name, synthetic flag, user path or editable manifest.
    if Path(data_dir).resolve() != DEMO_ROOT.resolve():
        raise RuntimeError("Custom scripts currently accept only the bundled synthetic autoimmune demo, alone in the workspace.")
    hashes = json.loads((ROOT / "config/analysis/synthetic_script_inputs.json").read_text())
    contents = {}
    for name, digest in hashes.items():
        path = DEMO_ROOT / name
        if path.resolve() != DEMO_ROOT.resolve() / name or path.stat().st_size > 8 * 1024 * 1024:
            raise RuntimeError("The approved synthetic fixture has changed; custom execution is blocked.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError("The approved synthetic fixture has changed; custom execution is blocked.")
        contents[name] = raw.decode("utf-8")
    return contents


def _csv(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def prepare_inputs(data_dir, selected_patient_ids="", compare_selected_patient_ids="", compare_mode=False, assay_ids=None, language="python"):
    if language not in {"python", "r"}:
        raise RuntimeError("Choose Python or R.")
    contents = approved_inputs(data_dir)
    records = json.loads(contents["clinical/fictional_participants.json"])
    links = {r["id"]: r["patient_id"] for r in records}
    patient_ids = set(links.values())

    def resolve(value):
        tokens = {v.strip() for v in value.split(",") if v.strip()}
        if tokens - patient_ids - set(links):
            raise RuntimeError("Some selected IDs do not belong to this synthetic workspace.")
        return {links.get(v, v) for v in tokens}

    group_a = resolve(selected_patient_ids)
    group_b = resolve(compare_selected_patient_ids) if compare_mode else set()
    if compare_mode and not group_a:
        raise RuntimeError("Choose Cohort A in Patients to prepare this comparison.")
    if compare_mode and not group_b:
        raise RuntimeError("Choose Cohort B in Patients to prepare this comparison.")
    if compare_mode and group_a & group_b:
        raise RuntimeError("Choose two disjoint cohorts in Patients; Cohort A and Cohort B overlap.")
    if not compare_mode and not group_a:
        group_a = patient_ids
    selected = group_a | group_b
    patients, clinical, samples = [], [], []
    for record in records:
        pid = record["patient_id"]
        if pid not in selected:
            continue
        cohort = "B" if pid in group_b else "A"
        patients.append(dict(patient_id=pid, cohort=cohort, sex=record["sex"]["label"],
                             disease=record["diseases"][0]["diseaseCode"]["label"]))
        for measure in record.get("measures", []):
            quantity = measure["measurementValue"]["quantity"]
            clinical.append(dict(patient_id=pid, measurement=measure["assayCode"]["label"],
                                 value=quantity["value"], unit=quantity["unit"]["label"],
                                 timepoint=record["info"]["event_date"]))
    manifest = json.loads(contents["assays/manifest.json"])["assays"]
    wanted = set(assay_ids or [])
    if wanted - {a["assay_id"] for a in manifest}:
        raise RuntimeError("One or more selected assays are not part of the approved demo.")
    files = {"patients.csv": _csv(["patient_id", "cohort", "sex", "disease"], patients),
             "clinical.csv": _csv(["patient_id", "measurement", "value", "unit", "timepoint"], clinical)}
    assays = {}
    omitted_assays = []
    for assay in manifest:
        if wanted and assay["assay_id"] not in wanted:
            continue
        modality = assay["modality"]
        metadata = list(csv.DictReader(io.StringIO(contents[assay["sample_metadata_file"]]), delimiter="\t"))
        kept = [row for row in metadata if row["patient_id"] in selected]
        kept_ids = {row["sample_id"] for row in kept}
        rows = list(csv.reader(io.StringIO(contents[assay["file"]]), delimiter=";"))
        positions = [i for i, sid in enumerate(rows[0]) if i == 0 or sid in kept_ids]
        if len(positions) <= 1:
            omitted_assays.append({"modality": modality, "reason": "No samples in the selected scope."})
            continue
        output = io.StringIO(newline="")
        csv.writer(output).writerows([[row[i] for i in positions] for row in rows])
        files[f"{modality}.csv"] = output.getvalue()
        assays[modality] = {"assay_id": assay["assay_id"], "value_kind": assay["data_type"],
                            "features": len(rows) - 1, "samples": len(positions) - 1,
                            "cohort_a_samples": sum(row["patient_id"] in group_a for row in kept),
                            "cohort_b_samples": sum(row["patient_id"] in group_b for row in kept),
                            "feature_ids": [row[0] for row in rows[1:]],
                            "feature_namespace": assay["feature_namespace"],
                            "feature_annotations": assay.get("feature_annotations", {})}
        for row in kept:
            samples.append(dict(modality=modality, sample_id=row["sample_id"], patient_id=row["patient_id"],
                                cohort="B" if row["patient_id"] in group_b else "A", age=row["age"],
                                sex=row["sex"], batch=row["batch"], center=row["center"]))
    files["samples.csv"] = _csv(["modality", "sample_id", "patient_id", "cohort", "age", "sex", "batch", "center"], samples)
    contract = {"version": 1, "language": "Python 3.11" if language == "python" else "R 4.2.2", "packages": PACKAGES if language == "python" else R_PACKAGES, "synthetic_only": True,
                "patients": len(patients), "cohort_a": len(group_a), "cohort_b": len(group_b),
                "assays": assays, "omitted_assays": omitted_assays, "compare_mode": compare_mode,
                "schemas": {"patients": "patient_id:string (unique), cohort:A/B, sex:string, disease:string",
                            "clinical": "patient_id:string, measurement:string, value:float, unit:string, timepoint:ISO date; long format",
                            "samples": "modality:string + sample_id:string (unique pair), patient_id:string, cohort:A/B, age:years, sex:string, batch:string, center:string"},
                "semantics": ["Assay matrices have features as rows and sample IDs as columns; values are numeric, NA means missing.",
                              "samples links each assay column to patients. Align explicitly by IDs, never by row position.",
                              "Inputs are already cohort-filtered. Assay coverage differs; do not silently impute missing values.",
                              "One baseline per patient: no longitudinal or survival analysis. RNA values are simulated expected counts, not integers.",
                              "Synthetic effects are engineering tests, not biological findings. No real patient values are included in this template."]}
    digest = hashlib.sha256(json.dumps({"contract": contract, "files": files}, sort_keys=True).encode()).hexdigest()
    template = "# COHORTome synthetic custom analysis\n# Complete the analysis section; keep the loading code.\n"
    template += ("# INSTRUCTIONS FOR THE EXTERNAL CODING ASSISTANT\n"
                 "# Use only the language and installed packages declared below. Return the complete runnable script.\n"
                 "# Do not substitute a different statistical method. If the requested method is unavailable, stop and explain the setup change needed.\n"
                 "# Treat this contract as authoritative, not stale metadata. Never invent cohorts, samples or measurements.\n"
                 "# Before any A/B comparison, check that both groups have sufficient samples in the chosen assay.\n"
                 "# If requirements are missing, explain them instead of generating a fallback analysis.\n"
                 "# Generated code must raise an error (Python) or use stop() (R) when required inputs are absent; do not merely print a message and exit successfully.\n"
                 "# Do not silently impute values, drop covariates or change the requested model. Explain proposed statistical choices to the user.\n")
    template += "# No network or package installation. 90 seconds, 512 MiB RAM.\n# Save CSV, TXT or PNG to /work/output (max 8 files, 4 MiB total).\n"
    # Keep the full contract for validation/audit, not thousands of IDs in code.
    template_contract = {**contract, "assays": {
        modality: {key: value for key, value in assay.items()
                   if key not in {"feature_ids", "feature_annotations"}}
        for modality, assay in assays.items()
    }}
    template += "# Feature IDs are the matrix row names; inspect them in code when needed.\n"
    template += "\n".join("# " + line for line in json.dumps(template_contract, indent=2).splitlines()) + "\n\n"
    if language == "r":
        template += "patients <- read.csv('/input/patients.csv', stringsAsFactors=FALSE)\nclinical <- read.csv('/input/clinical.csv', stringsAsFactors=FALSE)\nsamples <- read.csv('/input/samples.csv', stringsAsFactors=FALSE)\nassays <- list()\n"
        for modality in assays:
            template += f"assays[['{modality}']] <- as.matrix(read.csv('/input/{modality}.csv', row.names=1, check.names=FALSE, na.strings='NA'))\n"
        template += "output <- '/work/output'\n\n# === YOUR ANALYSIS HERE ===\n# Starter check; replace or extend with your research question.\nwrite.csv(as.data.frame(table(patients$cohort, patients$disease)), file.path(output, 'cohort_summary.csv'), row.names=FALSE)\ncat('Prepared', nrow(patients), 'patients and', length(assays), 'assays.\\n')\n"
        return {"contract": contract, "contract_id": digest, "template": template, "files": files}
    template += "from pathlib import Path\nimport pandas as pd\nimport numpy as np\nimport matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n\n"
    template += "patients = pd.read_csv('/input/patients.csv')\nclinical = pd.read_csv('/input/clinical.csv')\nsamples = pd.read_csv('/input/samples.csv')\nassays = {}\n"
    for modality in assays:
        template += f"assays[{modality!r}] = pd.read_csv('/input/{modality}.csv', index_col=0)\n"
    template += "output = Path('/work/output')\n\n# === YOUR ANALYSIS HERE ===\n# Starter check; replace or extend with your research question.\npatients.groupby(['cohort', 'disease']).size().rename('patients').to_csv(output / 'cohort_summary.csv')\nprint('Prepared', len(patients), 'patients and', len(assays), 'assays.')\n"
    return {"contract": contract, "contract_id": digest, "template": template, "files": files}
