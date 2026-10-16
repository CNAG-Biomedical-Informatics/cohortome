"""Generate an independent fictional RA/SLE/control demo; no study inputs used."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import random
import shutil

ROOT = Path(__file__).resolve().parents[1]
LABEL = "Synthetic autoimmune demo — not real PRECISESADS data"
SEED = 20260907
IFN = "IFI27 IFI44 IFI44L IFIT1 IFIT2 IFIT3 ISG15 MX1 OAS1 RSAD2".split()
INFLAMMATION = "IL6 TNF CXCL8 CCL2 IL1B S100A8 S100A9 NFKB1 PTGS2 CXCL10".split()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def table(path, rows, delimiter=";"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, delimiter=delimiter, lineterminator="\n").writerows(rows)


def build(output):
    # Refuse overwrites: regeneration should never remove an existing dataset.
    if output.exists():
        raise ValueError("Output already exists; choose a new directory.")
    rng = random.Random(SEED)
    write_json(output / "manifest.json", {"schema_version": 1, "name": LABEL,
               "clinical": {"representation": "snapshot"},
               "identifiers": {"clarid_subjects": {
                   "entity": "subject", "file": "identifiers/clarid_subjects.csv",
                   "delimiter": ",", "codebook_version": "0.04", "tools_version": "0.04"}}})
    (output / "identifiers").mkdir()
    shutil.copyfile(ROOT / "scripts/data/synthetic_autoimmune_clarid_subjects.csv",
                    output / "identifiers/clarid_subjects.csv")
    people, clinical = [], []
    groups = [("RA", "Rheumatoid Arthritis", "MONDO:0008383"),
              ("SLE", "Systemic Lupus Erythematosus", "MONDO:0007915"),
              ("HC", "Healthy Control", "NCIT:C94342")]
    for group, disease, code in groups:
        for j in range(30):
            i = len(people)
            pid = f"DEMOAI{30000 + i + 1:05d}"
            age = 25 + (j * 7) % 40
            sex = "Female" if j % 2 else "Male"
            latent = rng.gauss(0, 0.35)
            person = dict(patient_id=pid, sample_id=pid + ":baseline", group=group,
                          age=age, sex=sex, batch=f"B{j % 3 + 1}",
                          center=f"Demo center {j // 3 % 3 + 1}", latent=latent)
            people.append(person)
            clinical.append({
                "id": person["sample_id"], "patient_id": pid,
                "sex": {"id": "NCIT:C16576" if sex == "Female" else "NCIT:C20197", "label": sex},
                "diseases": [{"diseaseCode": {"id": code, "label": disease}}],
                "treatments": [],
                "measures": [{"assayCode": {"id": "LOINC:1988-5", "label": "CRP"},
                              "measurementValue": {"quantity": {"value": round(max(0.2, (12 if group == 'RA' else 4) + latent * 3), 3),
                                   "unit": {"id": "UO:0000275", "label": "mg/L"}}}}],
                "info": {"event_date": "2025-01-01", "synthetic": True,
                         "description": LABEL, "recruitment_center": person["center"],
                         "phenopacket": {"dateOfBirth": f"{2025-age}-01-01"}},
            })
    write_json(output / "clinical/fictional_participants.json", clinical)
    with (ROOT / "scripts/data/hgnc_protein_coding_symbols.tsv").open() as handle:
        genes = list(csv.DictReader(handle, delimiter="\t"))
    signals = set(IFN + INFLAMMATION)
    panel = [g for g in genes if g["symbol"] in signals]
    panel += [g for g in genes if g["symbol"] not in signals][:1000-len(panel)]
    specs = [
        ("transcriptomics", "rsem_expected_counts", "ensembl_gene_id", [g["ensembl_gene_id"] for g in panel]),
        ("methylation", "m_values", "synthetic_cpg_id", [f"SYNCPG{i:04d}" for i in range(1, 129)]),
        ("flow_cytometry", "cell_population_abundance", "immune_cell_population",
         ["CD4_T_cells_fraction", "CD8_T_cells_fraction", "B_cells_fraction", "NK_cells_fraction", "Monocytes_fraction", "Neutrophils_fraction"]),
        ("serology", "quantitative_measurement", "serology_marker",
         ["Anti_dsDNA_IU_mL", "Rheumatoid_factor_IU_mL", "Complement_C3_g_L", "Complement_C4_g_L", "CXCL10_pg_mL", "CRP_mg_L"]),
    ]
    assays, truth = [], []
    feature_annotations = json.loads((ROOT / "scripts/data/synthetic_autoimmune_feature_annotations.json").read_text())
    for modality, data_type, namespace, features in specs:
        # Different absent samples per assay, balanced across the three groups.
        excluded = {"methylation": {0, 1}, "flow_cytometry": {2, 3, 4}, "serology": {5}}.get(modality, set())
        selected = [p for i, p in enumerate(people) if i % 30 not in excluded]
        rows = [["feature_id", *[p["sample_id"] for p in selected]]]
        for f, feature in enumerate(features):
            symbol = panel[f]["symbol"] if modality == "transcriptomics" else feature
            effect_group = ("SLE" if symbol in IFN else "RA" if symbol in INFLAMMATION else "") if modality == "transcriptomics" else ("SLE" if f % 2 == 0 else "RA")
            if modality == "methylation" and f >= 24:
                effect_group = ""
            truth.append(dict(modality=modality, feature_id=feature, label=symbol,
                              elevated_group=effect_group or "none"))
            baseline = rng.uniform(30, 300) if modality == "transcriptomics" else rng.gauss(0, 0.8)
            values = []
            for p in selected:
                effect = float(p["group"] == effect_group)
                batch = (int(p["batch"][1:]) - 2) * 0.12
                noise = rng.gauss(0, 0.20)
                shared = p["latent"]
                if modality == "transcriptomics":
                    value = baseline * math.exp(effect * 1.3 + batch + shared * 0.2 + noise)
                elif modality == "methylation":
                    value = baseline + effect * 0.9 + batch + shared * 0.25 + noise
                elif modality == "flow_cytometry":
                    value = 0.08 + f * 0.025 + effect * 0.08 + shared * 0.01 + noise * 0.04
                else:
                    base = [15, 15, 0.8, 0.15, 150, 3][f]
                    value = base * math.exp(effect * 1.0 + shared * 0.2 + noise)
                missing = modality in {"flow_cytometry", "serology"} and rng.random() < 0.035
                values.append("NA" if missing else round(value, 5))
            rows.append([feature, *values])
        relative = f"assays/{modality}/synthetic_{modality}.csv"
        metadata = f"assays/{modality}/sample_metadata.tsv"
        table(output / relative, rows)
        fields = ["sample_id", "patient_id", "group", "age", "sex", "batch", "center"]
        table(output / metadata, [fields] + [[p[k] for k in fields] for p in selected], "\t")
        assays.append(dict(assay_id=f"synthetic_autoimmune_{modality}", label=f"Synthetic demo {modality}",
                           modality=modality, data_type=data_type, value_kind=data_type, level="sample",
                           feature_namespace=namespace, feature_id_column="feature_id",
                           sample_id_column="matrix_columns", patient_id_column="patient_id",
                           patient_linkage="sample_metadata_file", sample_metadata_file=metadata,
                           file=relative, feature_count=len(features)))
        if modality in feature_annotations:
            assays[-1]["feature_annotations"] = feature_annotations[modality]
    write_json(output / "assays/manifest.json", {"version": 1, "assays": assays})
    write_json(output / "simulation_truth.json", {"label": LABEL, "seed": SEED, "features": truth})
    write_json(output / "provenance.json", {"label": LABEL, "seed": SEED,
               "source": "Independent mathematical simulation; no restricted study inputs or fitted distributions.",
               "participants": 90, "groups": {"RA": 30, "SLE": 30, "HC": 30},
               "limitations": "Expected-count-like values are simulated, not RSEM output. CpG identifiers are fictional. Cell fractions are separate measurements, not a compositional partition. Effects are test signals, not biological claims."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "synthetic_autoimmune_demo")
    args = parser.parse_args()
    build(args.output)
    print("Generated 90 fictional participants and four linked assay modalities.")
