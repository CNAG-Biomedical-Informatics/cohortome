"""Prepare subject ClarIDs for the named repository fixtures, never study inputs.

Requires clarid-tools 0.04 for regeneration only. The app consumes the CSVs.
Outputs go to a new directory for review before replacing fixture sidecars.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {"default_dataset": 0, "private_dataset": 10000, "dataset-large": 20000,
            "synthetic_autoimmune_demo": 30000}
CONDITIONS = {"Healthy Control": "Z00.0", "Crohn Disease": "K50.9",
              "Ulcerative Colitis": "K51.9", "Rheumatoid Arthritis": "M06.9",
              "Systemic Lupus Erythematosus": "M32.9", "Multiple Sclerosis": "G35",
              "Asthma": "J45.9", "Chronic Obstructive Pulmonary Disease": "J44.9"}
FIELDS = ["unique_id", "subject_id", "study", "type", "condition", "sex", "age_group"]


def add_condition_names(rows, executable, codebook, directory):
    source, target = directory / "decode.csv", directory / "decoded.csv"
    with source.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["unique_id", "clar_id"], lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    subprocess.run([str(executable), "code", "--entity", "subject", "--action", "decode",
                    "--format", "human", "--codebook", str(codebook), "--with-condition-name",
                    "--infile", str(source), "--outfile", str(target), "--sep", ","],
                   check=True, capture_output=True, text=True)
    with target.open() as handle:
        names = {row["unique_id"]: row["condition_name"] for row in csv.DictReader(handle)}
    for row in rows:
        row["condition_name"] = names[row["unique_id"]]


def subject_rows(root, offset):
    patients = {}
    records = [record for path in sorted((root / "clinical").glob("*.json"))
               for record in json.loads(path.read_text())]
    # Age refers to the earliest dated clinical observation, never today's date.
    for record in sorted(records, key=lambda r: r.get("info", {}).get("event_date") or "9999"):
        patients.setdefault(record.get("patient_id") or record["id"], record)
    rows = []
    seen = set()
    for pid, record in sorted(patients.items()):
        match = re.fullmatch(r'[A-Z]+(\d+)', pid)
        if not match:
            raise ValueError('Synthetic patient IDs must have a numeric suffix.')
        number = int(match[1])
        if not offset < number < offset + 10000 or number in seen:
            raise ValueError('Synthetic subject numbers must be unique within their reserved range.')
        seen.add(number)
        label = record["diseases"][0]["diseaseCode"]["label"]
        info = record.get("info", {})
        birth = info.get("phenopacket", {}).get("dateOfBirth")
        observed = info.get("event_date")
        age_group = "Not Available"
        if birth and observed:
            dob, when = date.fromisoformat(birth[:10]), date.fromisoformat(observed[:10])
            age = when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))
            if 0 <= age <= 99:
                lower = age // 10 * 10
                age_group = f"Age{lower}to{lower + 9}"
        sex = record.get("sex", {})
        sex = sex.get("label", "Not reported") if isinstance(sex, dict) else sex
        rows.append(dict(zip(FIELDS, [pid, number, "CNAG-Test",
                    "Control" if label == "Healthy Control" else "Case",
                    CONDITIONS[label], sex or "Not reported", age_group])))
    return rows


def build(output, executable, codebook):
    output.mkdir(parents=True, exist_ok=False)
    version = subprocess.run([str(executable), "--version"], check=True, capture_output=True, text=True).stdout
    if version.strip().split()[-1] != "0.04":
        raise ValueError("Regenerate these fixtures with clarid-tools 0.04.")
    for name, offset in FIXTURES.items():
        rows = subject_rows(ROOT / name, offset)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "subjects.csv"
            with source.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            for fmt, column in [("human", "clar_id"), ("stub", "stub_id")]:
                target = Path(temporary) / f"{fmt}.csv"
                subprocess.run([str(executable), "code", "--entity", "subject", "--action", "encode",
                                "--format", fmt, "--codebook", str(codebook),
                                "--infile", str(source), "--outfile", str(target), "--sep", ","],
                               check=True, capture_output=True, text=True)
                with target.open() as handle:
                    encoded = {row["unique_id"]: row[column] for row in csv.DictReader(handle)}
                for row in rows:
                    row[column] = encoded[row["unique_id"]]
            add_condition_names(rows, executable, codebook, Path(temporary))
            with (output / f"{name}.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS + ["clar_id", "stub_id", "condition_name"], lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        print(f"{name}: {len(rows)} subject ClarIDs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clarid-tools", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    args = parser.parse_args()
    build(args.output, args.clarid_tools.resolve(), args.codebook.resolve())
