#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLINICAL_PATH = ROOT / "data" / "clinical" / "synthetic_longitudinal.json"
MOLECULAR_DIR = ROOT / "data" / "molecular"

VISITS = [
    ("week_0", 0),
    ("week_2", 14),
    ("week_6", 42),
    ("week_14", 98),
    ("week_26", 182),
]

SEXES = [
    {"id": "NCIT:C16576", "label": "Female"},
    {"id": "NCIT:C20197", "label": "Male"},
]
ETHNICITIES = [
    {"id": "NCIT:C41261", "label": "White"},
    {"id": "NCIT:C41260", "label": "Black or African American"},
    {"id": "NCIT:C17459", "label": "Asian"},
    {"id": "NCIT:C41259", "label": "Hispanic or Latino"},
]


@dataclass(frozen=True)
class CohortSpec:
    disease: str
    disease_id: str
    medication: str
    medication_id: str
    route: str
    route_id: str
    count: int
    baseline_modules: dict[str, float]
    treatment_targets: dict[str, float]
    measure_baseline: dict[str, float]
    measure_response: dict[str, float]


COHORT_SPECS = [
    CohortSpec(
        disease="Crohn Disease",
        disease_id="NCIT:C2965",
        medication="Infliximab",
        medication_id="RXNORM:153286",
        route="Intravenous Route of Administration",
        route_id="NCIT:C38288",
        count=5,
        baseline_modules={"inflammatory": 1.25, "barrier": 0.85, "housekeeping": 0.0},
        treatment_targets={"inflammatory": -0.70, "barrier": 0.20},
        measure_baseline={"CRP": 18.0, "Leukocyte Count": 13.0, "Hemoglobin": 10.5},
        measure_response={"CRP": -8.0, "Leukocyte Count": -2.2, "Hemoglobin": 0.9},
    ),
    CohortSpec(
        disease="Ulcerative Colitis",
        disease_id="NCIT:C123613",
        medication="Vedolizumab",
        medication_id="RXNORM:1792776",
        route="Intravenous Route of Administration",
        route_id="NCIT:C38288",
        count=5,
        baseline_modules={"inflammatory": 1.05, "barrier": 0.95, "housekeeping": 0.0},
        treatment_targets={"inflammatory": -0.45, "barrier": 0.15},
        measure_baseline={"CRP": 12.5, "Leukocyte Count": 10.8, "Hemoglobin": 11.2},
        measure_response={"CRP": -4.5, "Leukocyte Count": -1.2, "Hemoglobin": 0.5},
    ),
    CohortSpec(
        disease="Multiple Sclerosis",
        disease_id="NCIT:C3243",
        medication="Ocrelizumab",
        medication_id="RXNORM:1792525",
        route="Intravenous Route of Administration",
        route_id="NCIT:C38288",
        count=4,
        baseline_modules={"interferon": 1.15, "b_cell": 1.00, "housekeeping": 0.0},
        treatment_targets={"b_cell": -0.85, "interferon": -0.20},
        measure_baseline={"CRP": 4.0, "Leukocyte Count": 7.8, "Hemoglobin": 12.8},
        measure_response={"CRP": -0.5, "Leukocyte Count": -0.3, "Hemoglobin": 0.1},
    ),
    CohortSpec(
        disease="Systemic Lupus Erythematosus",
        disease_id="NCIT:C2871",
        medication="Belimumab",
        medication_id="RXNORM:1357547",
        route="Intravenous Route of Administration",
        route_id="NCIT:C38288",
        count=4,
        baseline_modules={"interferon": 1.35, "b_cell": 0.95, "inflammatory": 0.35},
        treatment_targets={"interferon": -0.40, "b_cell": -0.35},
        measure_baseline={"CRP": 7.0, "Leukocyte Count": 8.8, "Hemoglobin": 10.9},
        measure_response={"CRP": -1.8, "Leukocyte Count": -0.6, "Hemoglobin": 0.6},
    ),
    CohortSpec(
        disease="Rheumatoid Arthritis",
        disease_id="NCIT:C2884",
        medication="Adalimumab",
        medication_id="RXNORM:327361",
        route="Subcutaneous Route of Administration",
        route_id="NCIT:C38276",
        count=4,
        baseline_modules={"inflammatory": 1.10, "stromal": 1.20, "housekeeping": 0.0},
        treatment_targets={"inflammatory": -0.55, "stromal": -0.35},
        measure_baseline={"CRP": 14.0, "Leukocyte Count": 9.9, "Hemoglobin": 10.8},
        measure_response={"CRP": -5.0, "Leukocyte Count": -1.0, "Hemoglobin": 0.8},
    ),
    CohortSpec(
        disease="Asthma",
        disease_id="NCIT:C28397",
        medication="Mepolizumab",
        medication_id="RXNORM:1792773",
        route="Subcutaneous Route of Administration",
        route_id="NCIT:C38276",
        count=4,
        baseline_modules={"airway": 1.10, "eosinophil": 1.25, "housekeeping": 0.0},
        treatment_targets={"eosinophil": -0.75, "airway": -0.30},
        measure_baseline={"CRP": 5.5, "Leukocyte Count": 8.4, "Hemoglobin": 12.5},
        measure_response={"CRP": -1.0, "Leukocyte Count": -0.7, "Hemoglobin": 0.1},
    ),
    CohortSpec(
        disease="Chronic Obstructive Pulmonary Disease",
        disease_id="NCIT:C3199",
        medication="Dupilumab",
        medication_id="RXNORM:1792772",
        route="Subcutaneous Route of Administration",
        route_id="NCIT:C38276",
        count=4,
        baseline_modules={"airway": 0.95, "eosinophil": 0.65, "inflammatory": 0.60},
        treatment_targets={"airway": -0.28, "eosinophil": -0.35},
        measure_baseline={"CRP": 8.2, "Leukocyte Count": 9.3, "Hemoglobin": 12.0},
        measure_response={"CRP": -1.6, "Leukocyte Count": -0.5, "Hemoglobin": 0.2},
    ),
]


EXISTING_CORE_GENES = [
    "ENSG00000111640",
    "ENSG00000169429",
    "ENSG00000124256",
    "ENSG00000143546",
    "ENSG00000197971",
    "ENSG00000105383",
    "ENSG00000170421",
    "ENSG00000119888",
    "ENSG00000185479",
    "ENSG00000171862",
    "ENSG00000198888",
    "ENSG00000100906",
    "ENSG00000141510",
    "ENSG00000136997",
    "ENSG00000148773",
]


def generated_ensg_ids(start: int, count: int) -> list[str]:
    return [f"ENSG{value:011d}" for value in range(start, start + count)]


GENE_MODULES: dict[str, list[str]] = {
    "inflammatory": EXISTING_CORE_GENES[:6] + generated_ensg_ids(2500000, 10),
    "barrier": EXISTING_CORE_GENES[6:10] + generated_ensg_ids(2600000, 8),
    "housekeeping": EXISTING_CORE_GENES[10:] + generated_ensg_ids(2700000, 30),
    "interferon": generated_ensg_ids(2800000, 14),
    "b_cell": generated_ensg_ids(2900000, 14),
    "stromal": generated_ensg_ids(3000000, 14),
    "airway": generated_ensg_ids(3100000, 14),
    "eosinophil": generated_ensg_ids(3200000, 14),
}


GENE_BASELINES: dict[str, float] = {}
GENE_MODULE_BY_ID: dict[str, str] = {}
for module_name, gene_ids in GENE_MODULES.items():
    for index, gene_id in enumerate(gene_ids):
        if module_name == "housekeeping":
            baseline = 7.8 + 0.02 * index
        elif module_name in {"inflammatory", "interferon", "b_cell", "stromal"}:
            baseline = 5.6 + 0.04 * index
        else:
            baseline = 4.9 + 0.035 * index
        GENE_BASELINES[gene_id] = baseline
        GENE_MODULE_BY_ID[gene_id] = module_name


def visit_effect(days: int) -> float:
    if days <= 0:
        return 0.0
    return min(1.0, math.log1p(days) / math.log(183))


def signal_value(base: float, delta: float, days: int) -> float:
    return base + delta * visit_effect(days)


def quantity(value: float, unit_id: str, unit_label: str) -> dict:
    return {
        "quantity": {
            "value": round(value, 2),
            "unit": {
                "id": unit_id,
                "label": unit_label,
            },
        }
    }


def make_measure(label: str, code_id: str, value: float, unit_id: str, unit_label: str) -> dict:
    return {
        "assayCode": {
            "id": code_id,
            "label": label,
        },
        "measurementValue": quantity(value, unit_id, unit_label),
    }


def patient_ids() -> list[tuple[str, CohortSpec]]:
    output: list[tuple[str, CohortSpec]] = []
    current = 1
    for spec in COHORT_SPECS:
        for _ in range(spec.count):
            output.append((f"SYN{current:03d}", spec))
            current += 1
    return output


def build_clinical_records() -> list[dict]:
    records: list[dict] = []
    start_date = date(2024, 1, 1)
    rng = random.Random(314159)
    for patient_index, (patient_id, spec) in enumerate(patient_ids()):
        sex = SEXES[patient_index % len(SEXES)]
        ethnicity = ETHNICITIES[patient_index % len(ETHNICITIES)]
        disease = {"diseaseCode": {"id": spec.disease_id, "label": spec.disease}}
        for visit_index, (visit_label, days) in enumerate(VISITS):
            event_date = start_date + timedelta(days=days + patient_index)
            treatments = []
            if visit_index > 0:
                treatments = [{
                    "treatmentCode": {
                        "id": spec.medication_id,
                        "label": spec.medication,
                    },
                    "routeOfAdministration": {
                        "id": spec.route_id,
                        "label": spec.route,
                    },
                }]
            patient_offset = ((patient_index % 5) - 2) * 0.35
            jitter = rng.uniform(-0.18, 0.18)
            crp = max(0.3, signal_value(spec.measure_baseline["CRP"], spec.measure_response["CRP"], days) + patient_offset + jitter)
            leuk = max(3.5, signal_value(spec.measure_baseline["Leukocyte Count"], spec.measure_response["Leukocyte Count"], days) + patient_offset * 0.4 + jitter * 0.5)
            hemo = max(8.5, signal_value(spec.measure_baseline["Hemoglobin"], spec.measure_response["Hemoglobin"], days) - patient_offset * 0.15 + jitter * 0.1)
            records.append(
                {
                    "id": f"{patient_id}:{visit_label}",
                    "patient_id": patient_id,
                    "sex": dict(sex),
                    "ethnicity": dict(ethnicity),
                    "diseases": [disease],
                    "treatments": treatments,
                    "measures": [
                        make_measure("CRP", "LOINC:1988-5", crp, "UO:0000275", "mg/L"),
                        make_measure("Leukocyte Count", "LOINC:6690-2", leuk, "UO:0000175", "10^9/L"),
                        make_measure("Hemoglobin", "LOINC:718-7", hemo, "UO:0000175", "g/dL"),
                    ],
                    "info": {
                        "event_date": event_date.isoformat(),
                    },
                }
            )
    return records


def gene_count_for_sample(patient_index: int, spec: CohortSpec, gene_id: str, visit_days: int, rng: random.Random) -> int:
    module = GENE_MODULE_BY_ID[gene_id]
    baseline_log2 = GENE_BASELINES[gene_id]
    disease_effect = spec.baseline_modules.get(module, 0.0)
    response_effect = spec.treatment_targets.get(module, 0.0)
    patient_effect = ((patient_index % 4) - 1.5) * 0.12
    time_effect = response_effect * visit_effect(visit_days)
    library_shift = ((patient_index % 7) - 3) * 0.04
    noise = rng.gauss(0.0, 0.08)
    log2_cpm = baseline_log2 + disease_effect + time_effect + patient_effect + library_shift + noise
    counts = max(5.0, (2 ** log2_cpm) * 18.0)
    return int(round(counts))


def build_matrix_for_samples(sample_ids: list[str], sample_meta: dict[str, tuple[int, CohortSpec, int]]) -> list[list[str]]:
    rows: list[list[str]] = []
    rng = random.Random(271828)
    for gene_id in sorted(GENE_BASELINES.keys()):
        row = [gene_id]
        for sample_id in sample_ids:
            patient_index, spec, visit_days = sample_meta[sample_id]
            row.append(str(gene_count_for_sample(patient_index, spec, gene_id, visit_days, rng)))
        rows.append(row)
    return rows


def write_matrix(path: Path, sample_ids: list[str], sample_meta: dict[str, tuple[int, CohortSpec, int]]) -> None:
    rows = build_matrix_for_samples(sample_ids, sample_meta)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["gene_id", *sample_ids])
        writer.writerows(rows)


def build_molecular_matrices() -> None:
    MOLECULAR_DIR.mkdir(parents=True, exist_ok=True)
    sample_meta: dict[str, tuple[int, CohortSpec, int]] = {}
    all_week0: list[str] = []
    medication_samples: dict[str, list[str]] = {}
    for patient_index, (patient_id, spec) in enumerate(patient_ids()):
        key = spec.medication.lower().replace(" ", "_")
        medication_samples.setdefault(key, [])
        for visit_index, (visit_label, days) in enumerate(VISITS):
            sample_id = f"{patient_id}:{visit_label}"
            sample_meta[sample_id] = (patient_index, spec, days)
            if visit_index == 0:
                all_week0.append(sample_id)
            else:
                medication_samples[key].append(sample_id)

    write_matrix(MOLECULAR_DIR / "synthetic_transcriptome_raw_counts_baseline.csv", all_week0, sample_meta)
    for medication_key, sample_ids in medication_samples.items():
        write_matrix(MOLECULAR_DIR / f"synthetic_transcriptome_raw_counts_{medication_key}.csv", sample_ids, sample_meta)


def write_clinical_json(records: list[dict]) -> None:
    CLINICAL_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")


def write_readme() -> None:
    lines = [
        "# Molecular Data",
        "",
        "Place molecular datasets here.",
        "",
        "Current development fixture:",
        "",
        "- `synthetic_transcriptome_raw_counts_baseline.csv`",
        "  - Semicolon-delimited raw count matrix",
        "  - Columns are untreated baseline `week_0` samples for all synthetic patients",
        "  - Intended as a pre-treatment control/reference snapshot",
        "- `synthetic_transcriptome_raw_counts_infliximab.csv`",
        "  - Post-treatment samples for synthetic Crohn Disease patients treated with Infliximab",
        "- `synthetic_transcriptome_raw_counts_vedolizumab.csv`",
        "  - Post-treatment samples for synthetic Ulcerative Colitis patients treated with Vedolizumab",
        "- `synthetic_transcriptome_raw_counts_ocrelizumab.csv`",
        "  - Post-treatment samples for synthetic Multiple Sclerosis patients treated with Ocrelizumab",
        "- `synthetic_transcriptome_raw_counts_belimumab.csv`",
        "  - Post-treatment samples for synthetic Systemic Lupus Erythematosus patients treated with Belimumab",
        "- `synthetic_transcriptome_raw_counts_adalimumab.csv`",
        "  - Post-treatment samples for synthetic Rheumatoid Arthritis patients treated with Adalimumab",
        "- `synthetic_transcriptome_raw_counts_mepolizumab.csv`",
        "  - Post-treatment samples for synthetic Asthma patients treated with Mepolizumab",
        "- `synthetic_transcriptome_raw_counts_dupilumab.csv`",
        "  - Post-treatment samples for synthetic COPD patients treated with Dupilumab",
        "",
        "Notes:",
        "- All sample IDs match the merged longitudinal IDs in `data/clinical/synthetic_longitudinal.json`.",
        "- `week_0` is a true untreated baseline in the synthetic clinical fixture.",
        "- The expression panel is larger and structured into disease-relevant synthetic modules (inflammatory, interferon, B-cell, stromal, airway, eosinophil, barrier, housekeeping).",
        "- Counts are deterministic synthetic raw counts intended for exploratory UI development, not biological realism.",
    ]
    (MOLECULAR_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    clinical_records = build_clinical_records()
    write_clinical_json(clinical_records)
    build_molecular_matrices()
    write_readme()
    print(f"Wrote {len(clinical_records)} clinical records to {CLINICAL_PATH}")
    print(f"Wrote molecular fixtures to {MOLECULAR_DIR}")


if __name__ == "__main__":
    main()
