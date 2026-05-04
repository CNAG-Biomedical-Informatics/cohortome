#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ROOT = ROOT / "default_dataset"
CLINICAL_PATH = DEFAULT_DATASET_ROOT / "clinical" / "synthetic_longitudinal.json"
HC_CLINICAL_PATH = DEFAULT_DATASET_ROOT / "clinical" / "synthetic_hc_baseline.json"
MOLECULAR_DIR = DEFAULT_DATASET_ROOT / "molecular"
DEFAULT_LARGE_DATASET_ROOT = ROOT / "dataset-large"
REAL_GENE_PANEL_PATH = ROOT / "scripts" / "data" / "hgnc_protein_coding_symbols.tsv"

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
HC_COUNT = 8
HC_DISEASE = {"diseaseCode": {"id": "NCIT:C94342", "label": "Healthy Control"}}


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
    relapse_weights: dict[str, float]
    relapse_schedule: Optional[list[Optional[str]]] = None


COHORT_SPECS = [
    CohortSpec(
        disease="Crohn Disease",
        disease_id="NCIT:C2965",
        medication="Infliximab",
        medication_id="RXNORM:153286",
        route="Intravenous Route of Administration",
        route_id="NCIT:C38288",
        count=3,
        baseline_modules={"inflammatory": 1.25, "barrier": 0.85, "housekeeping": 0.0},
        treatment_targets={"inflammatory": -0.70, "barrier": 0.20},
        measure_baseline={"CRP": 18.0, "Leukocyte Count": 13.0, "Hemoglobin": 10.5},
        measure_response={"CRP": -8.0, "Leukocyte Count": -2.2, "Hemoglobin": 0.9},
        relapse_weights={"week_6": 0.08, "week_14": 0.14, "week_26": 0.18},
        relapse_schedule=["week_6", "week_14", "week_26"],
    ),
    CohortSpec(
        disease="Crohn Disease",
        disease_id="NCIT:C2965",
        medication="Ustekinumab",
        medication_id="RXNORM:1797901",
        route="Subcutaneous Route of Administration",
        route_id="NCIT:C38276",
        count=2,
        baseline_modules={"inflammatory": 1.18, "barrier": 0.82, "housekeeping": 0.0},
        treatment_targets={"inflammatory": -0.58, "barrier": 0.12},
        measure_baseline={"CRP": 17.0, "Leukocyte Count": 12.2, "Hemoglobin": 10.8},
        measure_response={"CRP": -6.0, "Leukocyte Count": -1.5, "Hemoglobin": 0.7},
        relapse_weights={"week_6": 0.10, "week_14": 0.16, "week_26": 0.20},
        relapse_schedule=[None, "week_26"],
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
        relapse_weights={"week_6": 0.10, "week_14": 0.18, "week_26": 0.22},
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
        relapse_weights={"week_6": 0.03, "week_14": 0.07, "week_26": 0.10},
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
        relapse_weights={"week_6": 0.09, "week_14": 0.15, "week_26": 0.18},
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
        relapse_weights={"week_6": 0.11, "week_14": 0.17, "week_26": 0.20},
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
        relapse_weights={"week_6": 0.05, "week_14": 0.10, "week_26": 0.14},
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
        relapse_weights={"week_6": 0.08, "week_14": 0.13, "week_26": 0.17},
    ),
]


GENE_MODULE_ORDER = [
    "inflammatory",
    "barrier",
    "housekeeping",
    "interferon",
    "b_cell",
    "stromal",
    "airway",
    "eosinophil",
]

LEGACY_CORE_GENES = [
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


LEGACY_GENE_MODULES: dict[str, list[str]] = {
    "inflammatory": LEGACY_CORE_GENES[:6] + generated_ensg_ids(2500000, 10),
    "barrier": LEGACY_CORE_GENES[6:10] + generated_ensg_ids(2600000, 8),
    "housekeeping": LEGACY_CORE_GENES[10:] + generated_ensg_ids(2700000, 30),
    "interferon": generated_ensg_ids(2800000, 14),
    "b_cell": generated_ensg_ids(2900000, 14),
    "stromal": generated_ensg_ids(3000000, 14),
    "airway": generated_ensg_ids(3100000, 14),
    "eosinophil": generated_ensg_ids(3200000, 14),
}

REAL_MODULE_SEED_SYMBOLS: dict[str, list[str]] = {
    "inflammatory": [
        "IL1B",
        "IL6",
        "TNF",
        "CXCL8",
        "CCL2",
        "PTGS2",
        "NFKB1",
        "ICAM1",
        "MMP9",
        "S100A8",
        "S100A9",
        "CXCL10",
    ],
    "barrier": [
        "EPCAM",
        "OCLN",
        "TJP1",
        "CLDN1",
        "CLDN4",
        "MUC1",
        "KRT8",
        "KRT18",
        "KRT19",
        "DSG2",
    ],
    "housekeeping": [
        "ACTB",
        "GAPDH",
        "HPRT1",
        "RPLP0",
        "B2M",
        "PPIA",
        "TBP",
        "UBC",
        "RPL13A",
        "EEF1A1",
        "TUBB",
        "YWHAZ",
    ],
    "interferon": [
        "IFI27",
        "IFI44L",
        "IFIT1",
        "IFIT2",
        "IFIT3",
        "ISG15",
        "MX1",
        "OAS1",
        "OAS2",
        "OASL",
        "STAT1",
        "IRF7",
        "RSAD2",
        "XAF1",
    ],
    "b_cell": [
        "CD19",
        "MS4A1",
        "CD79A",
        "CD79B",
        "CD22",
        "CD37",
        "CD74",
        "BANK1",
        "BLK",
        "PAX5",
        "MZB1",
        "TNFRSF13C",
    ],
    "stromal": [
        "COL1A1",
        "COL1A2",
        "COL3A1",
        "COL6A1",
        "COL6A3",
        "DCN",
        "LUM",
        "TAGLN",
        "VIM",
        "THY1",
        "FN1",
        "ACTA2",
        "FAP",
        "PDGFRB",
    ],
    "airway": [
        "KRT5",
        "KRT14",
        "KRT17",
        "BPIFA1",
        "SCGB1A1",
        "FOXJ1",
        "MUC5AC",
        "MUC5B",
        "CEACAM6",
        "AGR2",
    ],
    "eosinophil": [
        "CLC",
        "IL5RA",
        "CCR3",
        "RNASE2",
        "RNASE3",
        "SIGLEC8",
        "ALOX15",
        "PRG2",
        "EPX",
        "CSF2RB",
    ],
}

MODULE_PANEL_WEIGHTS = {
    module_name: len(gene_ids)
    for module_name, gene_ids in LEGACY_GENE_MODULES.items()
}

MAX_SYNTHETIC_COUNT = 2_000_000_000


def _baseline_for_gene(module_name: str, index: int) -> float:
    scaled_index = math.log2(index + 1) if index > 0 else 0.0
    if module_name == "housekeeping":
        return 7.8 + 0.12 * scaled_index
    if module_name in {"inflammatory", "interferon", "b_cell", "stromal"}:
        return 5.6 + 0.18 * scaled_index
    return 4.9 + 0.16 * scaled_index


def compile_gene_panel(gene_modules: dict[str, list[str]]) -> tuple[list[str], dict[str, str], dict[str, float]]:
    gene_ids: list[str] = []
    gene_module_by_id: dict[str, str] = {}
    gene_baselines: dict[str, float] = {}
    seen: set[str] = set()
    for module_name in GENE_MODULE_ORDER:
        module_gene_ids = list(gene_modules.get(module_name, []))
        for index, gene_id in enumerate(module_gene_ids):
            if gene_id in seen:
                raise ValueError(f"Duplicate gene identifier in panel: {gene_id}")
            seen.add(gene_id)
            gene_ids.append(gene_id)
            gene_module_by_id[gene_id] = module_name
            gene_baselines[gene_id] = _baseline_for_gene(module_name, index)
    return gene_ids, gene_module_by_id, gene_baselines


LEGACY_GENE_IDS, LEGACY_GENE_MODULE_BY_ID, LEGACY_GENE_BASELINES = compile_gene_panel(LEGACY_GENE_MODULES)


def load_hgnc_gene_rows(path: Path = REAL_GENE_PANEL_PATH) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Expected HGNC symbol file at {path}. Regenerate it before requesting extended matrices."
        )
    rows: list[dict[str, str]] = []
    seen_symbols: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            symbol = str(row.get("symbol") or "").strip()
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "ensembl_gene_id": str(row.get("ensembl_gene_id") or "").strip(),
                    "name": str(row.get("name") or "").strip(),
                }
            )
    return rows


def _stable_symbol_sort_key(symbol: str) -> str:
    return hashlib.sha1(symbol.encode("utf-8")).hexdigest()


def target_module_gene_counts(total_gene_count: int) -> dict[str, int]:
    minimum_gene_count = sum(len(REAL_MODULE_SEED_SYMBOLS[module_name]) for module_name in GENE_MODULE_ORDER)
    if total_gene_count < minimum_gene_count:
        raise ValueError(
            f"Extended panel size {total_gene_count} is too small; need at least {minimum_gene_count} genes "
            "to preserve the curated module seeds."
        )
    remaining = total_gene_count - minimum_gene_count
    total_weight = sum(MODULE_PANEL_WEIGHTS.values())
    extra_counts: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    for module_name in GENE_MODULE_ORDER:
        scaled = remaining * MODULE_PANEL_WEIGHTS[module_name] / total_weight
        whole = int(math.floor(scaled))
        extra_counts[module_name] = whole
        remainders.append((scaled - whole, module_name))
    assigned = sum(extra_counts.values())
    for _remainder, module_name in sorted(remainders, key=lambda item: (-item[0], item[1]))[: remaining - assigned]:
        extra_counts[module_name] += 1
    return {
        module_name: len(REAL_MODULE_SEED_SYMBOLS[module_name]) + extra_counts[module_name]
        for module_name in GENE_MODULE_ORDER
    }


def build_real_gene_modules(total_gene_count: int, path: Path = REAL_GENE_PANEL_PATH) -> dict[str, list[str]]:
    hgnc_rows = load_hgnc_gene_rows(path)
    available_rows = [row for row in hgnc_rows if row["symbol"] and row["ensembl_gene_id"]]
    available_symbols = {row["symbol"] for row in available_rows}
    symbol_to_ensembl = {row["symbol"]: row["ensembl_gene_id"] for row in available_rows}
    missing_seeds = sorted(
        {
            symbol
            for module_name in GENE_MODULE_ORDER
            for symbol in REAL_MODULE_SEED_SYMBOLS[module_name]
            if symbol not in available_symbols
        }
    )
    if missing_seeds:
        raise ValueError(
            "The vendored HGNC symbol file is missing curated module seed genes: "
            + ", ".join(missing_seeds[:10])
        )
    module_counts = target_module_gene_counts(total_gene_count)
    modules = {
        module_name: [symbol_to_ensembl[symbol] for symbol in REAL_MODULE_SEED_SYMBOLS[module_name]]
        for module_name in GENE_MODULE_ORDER
    }
    used_gene_ids = {
        gene_id
        for module_name in GENE_MODULE_ORDER
        for gene_id in modules[module_name]
    }
    filler_pool = sorted(
        (row for row in available_rows if row["ensembl_gene_id"] not in used_gene_ids),
        key=lambda row: _stable_symbol_sort_key(row["symbol"]),
    )
    cursor = 0
    for module_name in GENE_MODULE_ORDER:
        needed = module_counts[module_name] - len(modules[module_name])
        if needed <= 0:
            continue
        chunk = filler_pool[cursor : cursor + needed]
        if len(chunk) != needed:
            raise ValueError(
                f"Unable to construct a {total_gene_count}-gene panel from the vendored HGNC symbol set."
            )
        modules[module_name].extend(row["ensembl_gene_id"] for row in chunk)
        cursor += needed
    return modules


def extended_gene_panel(total_gene_count: int) -> tuple[list[str], dict[str, str], dict[str, float]]:
    return compile_gene_panel(build_real_gene_modules(total_gene_count))


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
    per_spec_index: dict[tuple[str, str], int] = {}
    for patient_index, (patient_id, spec) in enumerate(patient_ids()):
        sex = SEXES[patient_index % len(SEXES)]
        ethnicity = ETHNICITIES[patient_index % len(ETHNICITIES)]
        disease = {"diseaseCode": {"id": spec.disease_id, "label": spec.disease}}
        spec_key = (spec.disease, spec.medication)
        spec_patient_index = per_spec_index.get(spec_key, 0)
        per_spec_index[spec_key] = spec_patient_index + 1
        relapse_visit_index = None
        scheduled_relapse = None
        if spec.relapse_schedule and spec_patient_index < len(spec.relapse_schedule):
            scheduled_relapse = spec.relapse_schedule[spec_patient_index]
        if scheduled_relapse:
            for visit_index, (visit_label, _days) in enumerate(VISITS[1:], start=1):
                if visit_label == scheduled_relapse:
                    relapse_visit_index = visit_index
                    break
        else:
            for visit_index, (visit_label, _days) in enumerate(VISITS[1:], start=1):
                hazard = spec.relapse_weights.get(visit_label, 0.0)
                patient_modifier = ((patient_index % 3) - 1) * 0.015
                relapse_roll = min(max(hazard + patient_modifier, 0.0), 0.85)
                if rng.random() < relapse_roll:
                    relapse_visit_index = visit_index
                    break
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
            relapse = 1.0 if relapse_visit_index is not None and visit_index >= relapse_visit_index else 0.0
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
                        make_measure("Clinical relapse", "PN:CLINICAL_RELAPSE", relapse, "UO:0000187", "binary"),
                    ],
                    "info": {
                        "event_date": event_date.isoformat(),
                    },
                }
            )
    return records


def build_hc_clinical_records() -> list[dict]:
    records: list[dict] = []
    start_date = date(2024, 1, 1)
    rng = random.Random(161803)
    for patient_index in range(HC_COUNT):
        patient_id = f"HC{patient_index + 1:03d}"
        sex = SEXES[patient_index % len(SEXES)]
        ethnicity = ETHNICITIES[patient_index % len(ETHNICITIES)]
        event_date = start_date + timedelta(days=patient_index)
        patient_offset = ((patient_index % 5) - 2) * 0.18
        jitter = rng.uniform(-0.10, 0.10)
        crp = max(0.1, 1.1 + patient_offset + jitter)
        leuk = max(4.2, 6.7 + patient_offset * 0.5 + jitter * 0.4)
        hemo = max(11.8, 13.7 - patient_offset * 0.15 + jitter * 0.2)
        records.append(
            {
                "id": f"{patient_id}:week_0",
                "patient_id": patient_id,
                "sex": dict(sex),
                "ethnicity": dict(ethnicity),
                "diseases": [dict(HC_DISEASE)],
                "measures": [
                    make_measure("CRP", "LOINC:1988-5", crp, "UO:0000275", "mg/L"),
                    make_measure("Leukocyte Count", "LOINC:6690-2", leuk, "UO:0000175", "10^9/L"),
                    make_measure("Hemoglobin", "LOINC:718-7", hemo, "UO:0000175", "g/dL"),
                ],
                "info": {
                    "event_date": event_date.isoformat(),
                    "cohort": "Healthy Control",
                },
            }
        )
    return records


def gene_count_for_sample(
    patient_index: int,
    spec: CohortSpec,
    gene_id: str,
    visit_days: int,
    rng: random.Random,
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
) -> int:
    module = gene_module_by_id[gene_id]
    baseline_log2 = gene_baselines[gene_id]
    disease_effect = spec.baseline_modules.get(module, 0.0)
    response_effect = spec.treatment_targets.get(module, 0.0)
    patient_effect = ((patient_index % 4) - 1.5) * 0.12
    time_effect = response_effect * visit_effect(visit_days)
    library_shift = ((patient_index % 7) - 3) * 0.04
    noise = rng.gauss(0.0, 0.08)
    log2_cpm = baseline_log2 + disease_effect + time_effect + patient_effect + library_shift + noise
    counts = max(5.0, (2 ** log2_cpm) * 18.0)
    return min(MAX_SYNTHETIC_COUNT, int(round(counts)))


def build_matrix_for_samples(
    sample_ids: list[str],
    sample_meta: dict[str, tuple[int, CohortSpec, int]],
    gene_ids: list[str],
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
) -> list[list[str]]:
    rows: list[list[str]] = []
    rng = random.Random(271828)
    for gene_id in gene_ids:
        row = [gene_id]
        for sample_id in sample_ids:
            patient_index, spec, visit_days = sample_meta[sample_id]
            row.append(
                str(
                    gene_count_for_sample(
                        patient_index,
                        spec,
                        gene_id,
                        visit_days,
                        rng,
                        gene_module_by_id,
                        gene_baselines,
                    )
                )
            )
        rows.append(row)
    return rows


def build_hc_matrix_for_samples(
    sample_ids: list[str],
    sample_meta: dict[str, tuple[int, int]],
    gene_ids: list[str],
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
) -> list[list[str]]:
    rows: list[list[str]] = []
    rng = random.Random(141421)
    for gene_id in gene_ids:
        row = [gene_id]
        module = gene_module_by_id[gene_id]
        baseline_log2 = gene_baselines[gene_id]
        for sample_id in sample_ids:
            patient_index, _visit_days = sample_meta[sample_id]
            patient_effect = ((patient_index % 4) - 1.5) * 0.07
            library_shift = ((patient_index % 5) - 2) * 0.03
            noise = rng.gauss(0.0, 0.05)
            module_offset = -0.55 if module in {"inflammatory", "interferon", "b_cell", "stromal", "airway", "eosinophil"} else 0.0
            log2_cpm = baseline_log2 + module_offset + patient_effect + library_shift + noise
            counts = max(5.0, (2 ** log2_cpm) * 18.0)
            row.append(str(min(MAX_SYNTHETIC_COUNT, int(round(counts)))))
        rows.append(row)
    return rows


def write_matrix(
    path: Path,
    sample_ids: list[str],
    sample_meta: dict[str, tuple[int, CohortSpec, int]],
    gene_ids: list[str],
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
) -> None:
    rows = build_matrix_for_samples(sample_ids, sample_meta, gene_ids, gene_module_by_id, gene_baselines)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["gene_id", *sample_ids])
        writer.writerows(rows)


def write_hc_matrix(
    path: Path,
    sample_ids: list[str],
    sample_meta: dict[str, tuple[int, int]],
    gene_ids: list[str],
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
) -> None:
    rows = build_hc_matrix_for_samples(sample_ids, sample_meta, gene_ids, gene_module_by_id, gene_baselines)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["gene_id", *sample_ids])
        writer.writerows(rows)


def build_molecular_matrices(
    gene_ids: list[str],
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
    *,
    molecular_dir: Path = MOLECULAR_DIR,
    filename_suffix: str = "",
) -> None:
    molecular_dir.mkdir(parents=True, exist_ok=True)
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

    write_matrix(
        molecular_dir / f"synthetic_transcriptome_raw_counts_baseline{filename_suffix}.csv",
        all_week0,
        sample_meta,
        gene_ids,
        gene_module_by_id,
        gene_baselines,
    )
    for medication_key, sample_ids in medication_samples.items():
        write_matrix(
            molecular_dir / f"synthetic_transcriptome_raw_counts_{medication_key}{filename_suffix}.csv",
            sample_ids,
            sample_meta,
            gene_ids,
            gene_module_by_id,
            gene_baselines,
        )


def build_hc_molecular_matrix(
    gene_ids: list[str],
    gene_module_by_id: dict[str, str],
    gene_baselines: dict[str, float],
    *,
    molecular_dir: Path = MOLECULAR_DIR,
    filename_suffix: str = "",
) -> None:
    molecular_dir.mkdir(parents=True, exist_ok=True)
    sample_ids: list[str] = []
    sample_meta: dict[str, tuple[int, int]] = {}
    for patient_index in range(HC_COUNT):
        sample_id = f"HC{patient_index + 1:03d}:week_0"
        sample_ids.append(sample_id)
        sample_meta[sample_id] = (patient_index, 0)
    write_hc_matrix(
        molecular_dir / f"synthetic_transcriptome_raw_counts_hc_baseline{filename_suffix}.csv",
        sample_ids,
        sample_meta,
        gene_ids,
        gene_module_by_id,
        gene_baselines,
    )


def write_clinical_json(records: list[dict]) -> None:
    CLINICAL_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")


def write_hc_clinical_json(records: list[dict]) -> None:
    HC_CLINICAL_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")


def write_molecular_readme(
    molecular_dir: Path,
    *,
    large_dataset_gene_count: int | None = None,
    large_dataset_root: Path | None = None,
) -> None:
    examples = []
    if large_dataset_gene_count is not None and large_dataset_root is not None:
        examples.extend(
            [
                "",
                "Large transcriptome fixtures can also be regenerated with the fixture script:",
                "",
                f"- `python3 scripts/generate_synthetic_multimodal_fixture.py --large-gene-count {large_dataset_gene_count}`",
                f"  - Rebuilds `{large_dataset_root.name}` with one active molecular panel of `{large_dataset_gene_count}` HGNC-backed genes using Ensembl row identifiers.",
            ]
        )
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
        "- `synthetic_transcriptome_raw_counts_hc_baseline.csv`",
        "  - Semicolon-delimited raw count matrix",
        "  - Columns are untreated healthy-control `week_0` baseline samples",
        "  - Intended as an external HC baseline cohort with different IDs",
        "- `synthetic_transcriptome_raw_counts_infliximab.csv`",
        "  - Post-treatment samples for synthetic Crohn Disease and other synthetic patients treated with Infliximab",
        "- `synthetic_transcriptome_raw_counts_ustekinumab.csv`",
        "  - Post-treatment samples for a synthetic Crohn Disease subset treated with Ustekinumab",
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
        *examples,
        "",
        "Notes:",
        "- All sample IDs match the merged longitudinal IDs in `default_dataset/clinical/synthetic_longitudinal.json`.",
        "- Healthy control baseline sample IDs match `default_dataset/clinical/synthetic_hc_baseline.json`.",
        "- `week_0` is a true untreated baseline in the synthetic clinical fixture.",
        "- Healthy controls are baseline-only and intentionally omit the `diseases` field.",
        "- The expression panel is larger and structured into disease-relevant synthetic modules (inflammatory, interferon, B-cell, stromal, airway, eosinophil, barrier, housekeeping).",
        "- Counts are deterministic synthetic raw counts intended for exploratory UI development, not biological realism.",
        "- Large transcriptome fixtures use real HGNC-approved human protein-coding genes vendored in `scripts/data/hgnc_protein_coding_symbols.tsv`.",
        "- Matrix row identifiers use Ensembl gene IDs (`ENSG...`) even for the large fixtures.",
        "- The gene identifiers are real, but their module assignments and count dynamics remain synthetic and deterministic for timing and queue testing.",
    ]
    (molecular_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_large_dataset(
    gene_count: int,
    *,
    dataset_root: Path = DEFAULT_LARGE_DATASET_ROOT,
    clinical_records: Optional[list[dict]] = None,
    hc_clinical_records: Optional[list[dict]] = None,
) -> None:
    gene_ids, gene_module_by_id, gene_baselines = extended_gene_panel(gene_count)
    if dataset_root.exists():
        shutil.rmtree(dataset_root)
    clinical_dir = dataset_root / "clinical"
    molecular_dir = dataset_root / "molecular"
    clinical_dir.mkdir(parents=True, exist_ok=True)
    molecular_dir.mkdir(parents=True, exist_ok=True)
    active_clinical_records = clinical_records if clinical_records is not None else json.loads(CLINICAL_PATH.read_text(encoding="utf-8"))
    active_hc_clinical_records = hc_clinical_records if hc_clinical_records is not None else json.loads(HC_CLINICAL_PATH.read_text(encoding="utf-8"))
    (clinical_dir / "synthetic_longitudinal.json").write_text(json.dumps(active_clinical_records, indent=2), encoding="utf-8")
    (clinical_dir / "synthetic_hc_baseline.json").write_text(json.dumps(active_hc_clinical_records, indent=2), encoding="utf-8")
    build_molecular_matrices(
        gene_ids,
        gene_module_by_id,
        gene_baselines,
        molecular_dir=molecular_dir,
    )
    build_hc_molecular_matrix(
        gene_ids,
        gene_module_by_id,
        gene_baselines,
        molecular_dir=molecular_dir,
    )
    write_molecular_readme(
        molecular_dir,
        large_dataset_gene_count=gene_count,
        large_dataset_root=dataset_root,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate the synthetic clinical fixtures and molecular count matrices. "
            "Extended matrices are optional and use a vendored HGNC gene list with Ensembl row identifiers."
        )
    )
    parser.add_argument(
        "--large-gene-count",
        dest="large_gene_count",
        type=int,
        default=None,
        help="Rebuild dataset-large with one active large molecular panel using real HGNC-backed genes and Ensembl row identifiers.",
    )
    parser.add_argument(
        "--large-dataset-root",
        type=str,
        default=str(DEFAULT_LARGE_DATASET_ROOT),
        help="Output root for the generated large transcriptome dataset.",
    )
    parser.add_argument(
        "--skip-legacy",
        action="store_true",
        help="Skip rewriting the existing legacy 133-gene matrices.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clinical_records = build_clinical_records()
    hc_clinical_records = build_hc_clinical_records()
    if not args.skip_legacy:
        write_clinical_json(clinical_records)
        write_hc_clinical_json(hc_clinical_records)
        build_molecular_matrices(LEGACY_GENE_IDS, LEGACY_GENE_MODULE_BY_ID, LEGACY_GENE_BASELINES)
        build_hc_molecular_matrix(LEGACY_GENE_IDS, LEGACY_GENE_MODULE_BY_ID, LEGACY_GENE_BASELINES)
        write_molecular_readme(MOLECULAR_DIR)
    if args.large_gene_count is not None:
        build_large_dataset(
            args.large_gene_count,
            dataset_root=Path(args.large_dataset_root).resolve(),
            clinical_records=clinical_records,
            hc_clinical_records=hc_clinical_records,
        )
    if not args.skip_legacy:
        print(f"Wrote {len(clinical_records)} clinical records to {CLINICAL_PATH}")
        print(f"Wrote {len(hc_clinical_records)} HC clinical records to {HC_CLINICAL_PATH}")
        legacy_gene_count = len(LEGACY_GENE_IDS)
        print(f"Wrote molecular fixtures to {MOLECULAR_DIR}")
        print(f"- Legacy panel: {legacy_gene_count} genes")
    if args.large_gene_count is not None:
        print(f"- Large dataset root: {Path(args.large_dataset_root).resolve()}")
        print(f"- Large panel: {args.large_gene_count} genes")


if __name__ == "__main__":
    main()
