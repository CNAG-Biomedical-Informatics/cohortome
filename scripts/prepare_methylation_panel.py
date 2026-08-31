#!/usr/bin/env python3
"""Build and extract governed DNA-methylation feature panels.

The first supported publication panel is the independently replicated SLE
EWAS panel from Imgenberg-Kreuz et al. (Ann Rheum Dis. 2018;77:736-743).
The probe list is reconstructed from the authors' supplementary Table S2 and
is intentionally not vendored in this Apache-licensed source repository.

The complete methylation matrix is scanned once as bytes. Only its header and
the requested CpG rows are written to the compact output, so numeric values do
not need to be parsed or materialized in memory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SLE_DISCOVERY_COUNT = 7_625
SLE_REPLICATED_COUNT = 7_245
SLE_REPLICATION_P_THRESHOLD = 6.6e-6
SLE_SOURCE_DOI = "10.1136/annrheumdis-2017-212379"
SLE_SOURCE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC5909746/"
SLE_SOURCE_LICENSE = "CC BY-NC 4.0"

_NUMBER = r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][-+]?[0-9]+)?"
_BETA = r"(?:0(?:\.[0-9]+)?|1(?:\.0+)?)"
_SLE_ROW = re.compile(
    r"^\s*(?P<chromosome>\S+)\s+"
    r"(?P<position>\d+)\s+"
    r"(?P<cpg_id>cg\d{8})\s+"
    r"(?P<gene>.*?)\s*"
    rf"(?P<discovery_sle>{_BETA})\s+"
    rf"(?P<discovery_control>{_BETA})\s+"
    rf"(?P<discovery_delta_beta>{_NUMBER})\s+"
    rf"(?P<discovery_p_value>{_NUMBER})\s+"
    rf"(?P<replication_sle>{_BETA})\s+"
    rf"(?P<replication_control>{_BETA})\s+"
    rf"(?P<replication_delta_beta>{_NUMBER})\s+"
    rf"(?P<replication_p_value>{_NUMBER})\s*$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ensure_external_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError:
        return resolved
    raise ValueError(
        "Methylation panel outputs may contain restricted assay values and must be written outside the repository."
    )


def extract_pdf_text(pdf_path: Path) -> str:
    command = ["pdftotext", "-layout", str(pdf_path.expanduser().resolve()), "-"]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError("pdftotext is required to read the published supplementary table.") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "Unable to read the supplementary PDF.").strip())
    return result.stdout


def parse_sle_supplement(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    malformed_probe_lines: list[str] = []
    for line in str(text or "").splitlines():
        if not re.search(r"\bcg\d{8}\b", line):
            continue
        match = _SLE_ROW.match(line)
        if not match:
            malformed_probe_lines.append(line)
            continue
        row: dict[str, Any] = match.groupdict()
        row["position"] = int(row["position"])
        for field in (
            "discovery_sle",
            "discovery_control",
            "discovery_delta_beta",
            "discovery_p_value",
            "replication_sle",
            "replication_control",
            "replication_delta_beta",
            "replication_p_value",
        ):
            row[field] = float(row[field])
            if not math.isfinite(row[field]):
                raise ValueError(f"Supplementary table contains a non-finite {field} value.")
        row["gene"] = str(row["gene"] or "").strip()
        rows.append(row)
    if malformed_probe_lines:
        raise ValueError(
            f"Unable to parse {len(malformed_probe_lines)} CpG row(s) from the supplementary table."
        )
    cpg_ids = [str(row["cpg_id"]) for row in rows]
    if len(cpg_ids) != len(set(cpg_ids)):
        raise ValueError("The supplementary table contains duplicate CpG identifiers.")
    return rows


def replicated_sle_panel(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    panel: list[dict[str, Any]] = []
    for source in rows:
        discovery_delta = float(source["discovery_delta_beta"])
        replication_delta = float(source["replication_delta_beta"])
        replication_p = float(source["replication_p_value"])
        if replication_p >= SLE_REPLICATION_P_THRESHOLD:
            continue
        if discovery_delta * replication_delta <= 0:
            continue
        direction = "higher_in_sle" if replication_delta > 0 else "lower_in_sle"
        panel.append(
            {
                "cpg_id": str(source["cpg_id"]),
                "chromosome": str(source["chromosome"]),
                "position": int(source["position"]),
                "gene": str(source.get("gene") or ""),
                "direction": direction,
                "discovery_delta_beta": discovery_delta,
                "discovery_p_value": float(source["discovery_p_value"]),
                "replication_delta_beta": replication_delta,
                "replication_p_value": replication_p,
            }
        )
    return panel


def _write_panel(path: Path, rows: list[dict[str, Any]]) -> str:
    fields = [
        "cpg_id",
        "chromosome",
        "position",
        "gene",
        "direction",
        "discovery_delta_beta",
        "discovery_p_value",
        "replication_delta_beta",
        "replication_p_value",
    ]
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)
    return _sha256(path)


def _matrix_delimiter(header: bytes) -> bytes:
    candidates = (b"\t", b";", b",")
    delimiter = max(candidates, key=header.count)
    if header.count(delimiter) < 2:
        raise ValueError("The methylation matrix header needs a feature field and at least two sample fields.")
    return delimiter


def _feature_id(raw: bytes) -> str:
    value = raw.decode("utf-8-sig").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def extract_compact_matrix(
    source_path: Path,
    output_path: Path,
    requested_ids: Iterable[str],
    *,
    expected_source_sha256: str = "",
) -> dict[str, Any]:
    requested = {str(value or "").strip() for value in requested_ids if str(value or "").strip()}
    if not requested:
        raise ValueError("The methylation panel is empty.")
    source_digest = hashlib.sha256()
    compact_digest = hashlib.sha256()
    matched: set[str] = set()
    duplicate_source_ids: set[str] = set()
    with source_path.expanduser().resolve().open("rb") as source, tempfile.NamedTemporaryFile(
        mode="wb",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        delete=False,
    ) as target:
        temporary = Path(target.name)
        header = source.readline()
        if not header:
            raise ValueError("The methylation matrix is empty.")
        source_digest.update(header)
        compact_digest.update(header)
        target.write(header)
        delimiter = _matrix_delimiter(header)
        sample_count = header.rstrip(b"\r\n").count(delimiter)
        for line in source:
            source_digest.update(line)
            first_field = line.split(delimiter, 1)[0]
            cpg_id = _feature_id(first_field)
            if cpg_id not in requested:
                continue
            if cpg_id in matched:
                duplicate_source_ids.add(cpg_id)
                continue
            matched.add(cpg_id)
            target.write(line)
            compact_digest.update(line)
    if duplicate_source_ids:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            f"The source matrix contains {len(duplicate_source_ids)} duplicate requested CpG identifier(s)."
        )
    source_sha256 = source_digest.hexdigest()
    expected = str(expected_source_sha256 or "").strip().lower()
    if expected and source_sha256.lower() != expected:
        temporary.unlink(missing_ok=True)
        raise ValueError("The source matrix SHA-256 does not match the expected fingerprint.")
    os.replace(temporary, output_path)
    missing = sorted(requested - matched)
    return {
        "requested_feature_count": len(requested),
        "matched_feature_count": len(matched),
        "missing_feature_count": len(missing),
        "duplicate_source_feature_count": 0,
        "sample_count": sample_count,
        "source_matrix_sha256": source_sha256,
        "compact_matrix_sha256": compact_digest.hexdigest(),
        "missing_feature_ids": missing,
    }


def _open_delimited(path: Path):
    handle = path.open("r", encoding="utf-8-sig", newline="")
    first_line = handle.readline()
    if not first_line:
        handle.close()
        raise ValueError("A compact methylation matrix is empty.")
    delimiter = _matrix_delimiter(first_line.encode("utf-8"))
    handle.seek(0)
    return handle, csv.reader(handle, delimiter=delimiter.decode("ascii")), delimiter.decode("ascii")


def merge_compact_matrices(paths: list[Path], output_path: Path) -> dict[str, Any]:
    if len(paths) < 2:
        raise ValueError("At least two compact matrices are required for merging.")
    handles = []
    readers = []
    headers: list[list[str]] = []
    try:
        for path in paths:
            handle, reader, _delimiter = _open_delimited(path)
            handles.append(handle)
            readers.append(reader)
            header = next(reader, [])
            if len(header) < 3:
                raise ValueError("A compact methylation matrix has an invalid header.")
            headers.append([str(value or "").strip() for value in header])
        feature_labels = {header[0] for header in headers}
        if len(feature_labels) != 1:
            raise ValueError("Compact methylation matrices use different feature columns.")
        merged_samples: list[str] = []
        sample_positions: list[dict[str, int]] = []
        for header in headers:
            positions: dict[str, int] = {}
            for index, sample_id in enumerate(header[1:], start=1):
                if not sample_id or sample_id in positions:
                    raise ValueError("A compact methylation matrix contains empty or duplicate sample identifiers.")
                positions[sample_id] = index
                if sample_id not in merged_samples:
                    merged_samples.append(sample_id)
            sample_positions.append(positions)
        sample_sources = {
            sample_id: [index for index, positions in enumerate(sample_positions) if sample_id in positions]
            for sample_id in merged_samples
        }
        duplicated_samples = {
            sample_id: indices for sample_id, indices in sample_sources.items() if len(indices) > 1
        }
        row_count = 0
        temporary: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            delete=False,
        ) as target:
            temporary = Path(target.name)
            writer = csv.writer(target, delimiter=";", lineterminator="\n")
            writer.writerow([headers[0][0], *merged_samples])
            for grouped_rows in zip_longest(*readers):
                if any(row is None for row in grouped_rows):
                    raise ValueError("Compact methylation matrices contain different feature counts.")
                normalized_rows = [list(row or []) for row in grouped_rows]
                if any(len(row) != len(headers[index]) for index, row in enumerate(normalized_rows)):
                    raise ValueError("A compact methylation matrix contains an inconsistent row width.")
                cpg_ids = {str(row[0] or "").strip() for row in normalized_rows}
                if len(cpg_ids) != 1:
                    raise ValueError("Compact methylation matrices have different CpG identifiers or ordering.")
                for sample_id, source_indices in duplicated_samples.items():
                    values = {
                        normalized_rows[index][sample_positions[index][sample_id]]
                        for index in source_indices
                    }
                    if len(values) != 1:
                        raise ValueError("A duplicated sample has conflicting methylation values across source matrices.")
                merged_values: list[str] = []
                for sample_id in merged_samples:
                    source_index = next(
                        index for index, positions in enumerate(sample_positions) if sample_id in positions
                    )
                    merged_values.append(normalized_rows[source_index][sample_positions[source_index][sample_id]])
                writer.writerow([normalized_rows[0][0], *merged_values])
                row_count += 1
        os.replace(temporary, output_path)
        temporary = None
    finally:
        for handle in handles:
            handle.close()
        if "temporary" in locals() and temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "matched_feature_count": row_count,
        "sample_count": len(merged_samples),
        "duplicate_sample_count": len(duplicated_samples),
        "compact_matrix_sha256": _sha256(output_path),
    }


def filter_nonfinite_features(path: Path) -> dict[str, Any]:
    handle, reader, delimiter = _open_delimited(path)
    temporary: Path | None = None
    excluded_feature_ids: list[str] = []
    retained_feature_count = 0
    try:
        header = next(reader, [])
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as target:
            temporary = Path(target.name)
            writer = csv.writer(target, delimiter=delimiter, lineterminator="\n")
            writer.writerow(header)
            for row in reader:
                if len(row) != len(header):
                    raise ValueError("The compact methylation matrix contains an inconsistent row width.")
                exclude = False
                for raw_value in row[1:]:
                    value = str(raw_value or "").strip()
                    if value in {"", "NA", "NaN"}:
                        continue
                    try:
                        numeric = float(value)
                    except ValueError:
                        raise ValueError("The compact methylation matrix contains a non-numeric value.") from None
                    if math.isinf(numeric):
                        exclude = True
                    elif math.isnan(numeric):
                        raise ValueError("The compact methylation matrix contains an unsupported NaN spelling.")
                if exclude:
                    excluded_feature_ids.append(str(row[0] or "").strip())
                    continue
                writer.writerow(row)
                retained_feature_count += 1
        os.replace(temporary, path)
        temporary = None
    finally:
        handle.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "retained_feature_count": retained_feature_count,
        "excluded_nonfinite_feature_count": len(excluded_feature_ids),
        "excluded_nonfinite_feature_ids": excluded_feature_ids,
        "compact_matrix_sha256": _sha256(path),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def build_sle_panel(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = _ensure_external_output(Path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.supplement_pdf:
        supplement_text = extract_pdf_text(Path(args.supplement_pdf))
        supplement_sha256 = _sha256(Path(args.supplement_pdf).expanduser().resolve())
        supplement_kind = "published_supplement_pdf"
    else:
        supplement_path = Path(args.supplement_text).expanduser().resolve()
        supplement_text = supplement_path.read_text(encoding="utf-8")
        supplement_sha256 = _sha256(supplement_path)
        supplement_kind = "pdftotext_layout_derivative"
    source_rows = parse_sle_supplement(supplement_text)
    if len(source_rows) != SLE_DISCOVERY_COUNT:
        raise ValueError(
            f"Expected {SLE_DISCOVERY_COUNT} discovery rows from Table S2; parsed {len(source_rows)}."
        )
    panel_rows = replicated_sle_panel(source_rows)
    if len(panel_rows) != SLE_REPLICATED_COUNT:
        raise ValueError(
            f"Expected {SLE_REPLICATED_COUNT} replicated CpGs; selected {len(panel_rows)}."
        )
    panel_path = output_dir / "panel.tsv"
    compact_path = output_dir / "m_values.csv"
    panel_sha256 = _write_panel(panel_path, panel_rows)
    source_paths = [Path(value).expanduser().resolve() for value in args.source_matrix]
    if args.expected_source_sha256 and len(source_paths) != 1:
        raise ValueError("--expected-source-sha256 currently applies only to one source matrix.")
    if len(source_paths) == 1:
        extraction = extract_compact_matrix(
            source_paths[0],
            compact_path,
            (row["cpg_id"] for row in panel_rows),
            expected_source_sha256=args.expected_source_sha256,
        )
        source_sha256s = [str(extraction["source_matrix_sha256"])]
        extraction["source_matrix_count"] = 1
        extraction["duplicate_sample_count"] = 0
    else:
        with tempfile.TemporaryDirectory(prefix="panel-parts-", dir=output_dir) as temporary_dir:
            part_paths: list[Path] = []
            part_stats: list[dict[str, Any]] = []
            for index, source_path in enumerate(source_paths, start=1):
                part_path = Path(temporary_dir) / f"part-{index}.csv"
                stats = extract_compact_matrix(
                    source_path,
                    part_path,
                    (row["cpg_id"] for row in panel_rows),
                )
                part_paths.append(part_path)
                part_stats.append(stats)
            missing_sets = {tuple(stats["missing_feature_ids"]) for stats in part_stats}
            if len(missing_sets) != 1:
                raise ValueError("Source methylation matrices have different panel coverage.")
            merged = merge_compact_matrices(part_paths, compact_path)
            extraction = {
                "requested_feature_count": len(panel_rows),
                "matched_feature_count": int(merged["matched_feature_count"]),
                "missing_feature_count": len(part_stats[0]["missing_feature_ids"]),
                "duplicate_source_feature_count": 0,
                "sample_count": int(merged["sample_count"]),
                "duplicate_sample_count": int(merged["duplicate_sample_count"]),
                "source_matrix_count": len(source_paths),
                "compact_matrix_sha256": str(merged["compact_matrix_sha256"]),
                "missing_feature_ids": list(part_stats[0]["missing_feature_ids"]),
            }
            source_sha256s = [str(stats["source_matrix_sha256"]) for stats in part_stats]
            extraction["source_matrix_sha256"] = hashlib.sha256(
                "\n".join(source_sha256s).encode("ascii")
            ).hexdigest()
    source_matched_feature_count = int(extraction["matched_feature_count"])
    filtering = filter_nonfinite_features(compact_path)
    extraction["source_matched_feature_count"] = source_matched_feature_count
    extraction["matched_feature_count"] = int(filtering["retained_feature_count"])
    extraction["excluded_nonfinite_feature_count"] = int(filtering["excluded_nonfinite_feature_count"])
    extraction["excluded_nonfinite_feature_ids"] = list(filtering["excluded_nonfinite_feature_ids"])
    extraction["compact_matrix_sha256"] = str(filtering["compact_matrix_sha256"])
    panel_id = str(args.panel_id).strip()
    version = str(args.panel_version).strip()
    metadata = {
        "schema_version": 1,
        "panel_id": panel_id,
        "panel_version": version,
        "label": str(args.label).strip(),
        "view_type": "feature_panel",
        "feature_namespace": "illumina_cpg_probe_id",
        "scientific_selection_rule": (
            "Discovery DMCs with replication p < 6.6e-6 and the same direction of effect "
            "in the independent replication cohort."
        ),
        "intended_use": "Independent replication of a whole-blood SLE methylation signature.",
        "independent_of_target_cohort": True,
        "source_publication_doi": SLE_SOURCE_DOI,
        "source_publication_url": SLE_SOURCE_URL,
        "source_material_license": SLE_SOURCE_LICENSE,
        "source_material_kind": supplement_kind,
        "source_supplement_sha256": supplement_sha256,
        "source_matrix_sha256s": source_sha256s,
        "panel_file": panel_path.name,
        "panel_sha256": panel_sha256,
        "compact_matrix_file": compact_path.name,
        **extraction,
    }
    _write_json(output_dir / "panel.json", metadata)
    return metadata


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    source = cli.add_mutually_exclusive_group(required=True)
    source.add_argument("--supplement-pdf", help="Published supplementary Table S2 PDF.")
    source.add_argument("--supplement-text", help="A pdftotext -layout derivative of Table S2.")
    cli.add_argument(
        "--source-matrix",
        required=True,
        action="append",
        help="Complete processed methylation matrix. Repeat for disease-partition matrices.",
    )
    cli.add_argument("--output-dir", required=True, help="Protected output directory outside this repository.")
    cli.add_argument("--panel-id", default="independent_sle_ewas")
    cli.add_argument("--panel-version", default="1")
    cli.add_argument("--label", default="Independent replicated SLE EWAS panel")
    cli.add_argument("--expected-source-sha256", default="")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        metadata = build_sle_panel(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                key: metadata[key]
                for key in (
                    "panel_id",
                    "panel_version",
                    "requested_feature_count",
                    "matched_feature_count",
                    "missing_feature_count",
                    "excluded_nonfinite_feature_count",
                    "sample_count",
                    "panel_sha256",
                    "source_matrix_sha256",
                    "compact_matrix_sha256",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
