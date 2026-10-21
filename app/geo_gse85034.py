"""GSE85034 clinical/matrix adapter, based on the reviewed Store preparation.

Uses Convert-Pheno for BFF mapping. Does not register or activate a dataset.
Only the reviewed normalized microarray product is supported, not raw counts.
"""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import zipfile
from collections import defaultdict
from urllib.parse import quote

from app.geo_source import SourcePreparationError, verify_source
from app.preparation_tools import preparation_command
from app.env import app_env
import yaml

DRUGS = {"ADA": ("Adalimumab", "NCIT:C65216"), "MTX": ("Methotrexate", "NCIT:C642")}
MISSING = {"", "NA", "N/A", "NaN", "nan", "null"}
MAPPING = """mappingVersion: 2
source: {profile: csv}
target: {model: beacon, schemaVersion: '2.0.0'}
project: {id: gse85034, version: '0.1'}
defaults: {ontology: ncit}
records: {}
beacon:
  individuals:
    id: {sourceFields: [snapshot_id], primaryKey: patient_id}
    sex: {sourceField: sex, query: {from: value}}
    diseases:
      rules:
        - sourceField: diagnosis
          diseaseCode: {query: Psoriasis}
    treatments:
      rules:
        - sourceField: treatment
          treatmentCode: {query: {from: value}}
    measures:
      rules:
        - sourceField: pasi
          when: {nonEmpty: true}
          assayCode: {query: Psoriasis Area and Severity Index Clinical Classification}
          measurementValue:
            quantity:
              unit: {term: {id: 'UCUM:1', label: score}}
"""


def fail(message):
    raise SourcePreparationError(message)


def metadata(path, required=None):
    fields = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if not row:
                continue
            if row[0] == "!series_matrix_table_begin":
                break
            key = {"!Sample_geo_accession": "sample_id", "!Sample_title": "title"}.get(row[0])
            values = row[1:]
            if row[0] == "!Sample_characteristics_ch1":
                pairs = [value.partition(":") for value in values]
                if not pairs or any(not sep or label != pairs[0][0] for label, sep, _ in pairs):
                    fail("Unexpected GEO characteristic layout.")
                key = pairs[0][0]
                values = [value.strip() for _, _, value in pairs]
            if key:
                original, suffix = key, 2
                while key in fields:
                    key = f"{original}__{suffix}"
                    suffix += 1
                fields[key] = values
        else:
            fail("GEO expression table is missing.")
    required = {"sample_id", "title", "treatment", "timepoint", "tissue", "pasi"} if required is None else required
    if not required <= fields.keys() or len({len(v) for v in fields.values()}) != 1:
        fail("GEO sample metadata is incomplete or misaligned.")
    samples = fields["sample_id"]
    if not samples or len(set(samples)) != len(samples):
        fail("GEO sample identifiers are empty or duplicated.")
    return [dict(zip(fields, values)) for values in zip(*fields.values())]


def clinical_inputs(rows):
    people = defaultdict(list)
    for row in rows:
        match = re.match(r"^Subject\s+(\d+)\s+", row["title"])
        if not match or row["treatment"] not in DRUGS:
            fail("Unrecognized GSE85034 subject or treatment metadata.")
        people[match[1]].append(row)
    records, samples, inputs = [], [], []
    for pid, person in sorted(people.items()):
        if len({r["treatment"] for r in person}) != 1:
            fail("Conflicting treatment groups within a subject.")
        patient = "GSE85034-" + pid
        visits = defaultdict(list)
        for row in person:
            visit = {"LS": "Baseline", "NL": "Baseline", "WK2": "WK 2"}.get(row["timepoint"], row["timepoint"])
            visits[visit].append(row)
        for visit, group in visits.items():
            try:
                values = {float(r["pasi"]) for r in group if r["pasi"] not in MISSING}
            except ValueError:
                fail("A source PASI measurement is not numeric.")
            if len(values) > 1 or any(not math.isfinite(v) or not 0 <= v <= 72 for v in values):
                fail("Conflicting or out-of-range PASI measurements within a visit.")
            treatment = DRUGS[group[0]["treatment"]][0]
            info = dict(visit_id=visit, source_metadata=group, source_patient_id=pid,
                        source_sample_ids=[r["sample_id"] for r in group],
                        treatment_group=group[0]["treatment"])
            if visit == "Baseline":
                info["days_from_baseline"] = 0
            elif re.fullmatch(r"(?:WK|Week) \d+", visit):
                info["days_from_baseline"] = int(visit.split()[-1]) * 7
            else:
                info["timing_note"] = "Source timing label ambiguous; no elapsed day assigned"
            record = dict(id=patient + ":" + quote(visit, safe=""), patient_id=patient, info=info)
            records.append(record)
            inputs.append(dict(snapshot_id=record["id"], patient_id=patient, sex="Not Reported",
                               diagnosis="Psoriasis", treatment=treatment, pasi=next(iter(values), "")))
            for row in group:
                samples.append(dict(sample_id=patient + ":" + row["sample_id"], patient_id=patient,
                                    source_sample_id=row["sample_id"], visit_id=visit, timepoint=visit,
                                    days_from_baseline=info.get("days_from_baseline", ""),
                                    tissue="Non-lesional skin" if row["timepoint"] in {"NL", "WK 1NL"} else "Lesional skin",
                                    treatment=row["treatment"]))
    return records, samples, inputs


def write_csv(path, rows, delimiter=","):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def convert_clinical(records, inputs, work, command, *, drugs=None, mapping_text=MAPPING):
    source, mapping, target = work / "clinical.csv", work / "clinical.yaml", work / "converted.json"
    write_csv(source, inputs)
    mapping.write_text(mapping_text, encoding="utf-8")
    try:
        subprocess.run([*command, "-icsv", str(source), "--separator", ",", "--mapping-file", str(mapping),
                        "--search", "exact", "--no-source-info", "--term-audit", str(work / "terminology.tsv"),
                        "-obff", str(target)], check=True, capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        fail("Convert-Pheno could not prepare the clinical records. Check the installed preparation tools.")
    converted = json.loads(target.read_text(encoding="utf-8"))
    mapped = {r["id"]: r for r in converted}
    if len(mapped) != len(converted) or set(mapped) != {r["id"] for r in records}:
        fail("Converted clinical record coverage differs from the source.")
    drugs = dict(DRUGS.values()) if drugs is None else drugs
    for record, source in zip(records, inputs):
        result = mapped[record["id"]]
        diseases, treatments, measures = (result.get(key, []) for key in ("diseases", "treatments", "measures"))
        if (len(diseases) != 1 or diseases[0]["diseaseCode"]["id"] != "NCIT:C3346"
                or len(treatments) != 1 or treatments[0]["treatmentCode"]["id"] != drugs[source["treatment"]]):
            fail("Converted clinical terminology differs from the reviewed mapping.")
        record["diseases"] = [{"diseaseCode": diseases[0]["diseaseCode"]}]
        record["treatments"] = [{"treatmentCode": treatments[0]["treatmentCode"],
                                 "_info": {"interpretation": "Study treatment group, not a dated administration"}}]
        if len(measures) != (source["pasi"] != ""):
            fail("Converted measurement coverage differs from the source.")
        record["measures"] = []
        for measure in measures:
            quantity = measure["measurementValue"]["quantity"]
            if (measure["assayCode"]["id"] != "NCIT:C135734" or quantity["value"] != source["pasi"]
                    or quantity["unit"]["id"] != "UCUM:1"):
                fail("Converted PASI measurement differs from the source.")
            record["measures"].append(dict(assayCode=measure["assayCode"],
                measurementValue={"quantity": {k: quantity[k] for k in ("value", "unit")}}))
    # Sex is unavailable; discard the converter's required temporary placeholder.
    # The converter's intermediate JSON includes machine-local execution metadata.
    # Keep the mapping, audit and input CSV, not this redundant transient output.
    target.unlink()
    return records


def expression(path, output, samples, check_cancel=lambda: None):
    """Stream features without loading a full matrix or changing source values."""
    wanted = [r["source_sample_id"] for r in samples]
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8") as source, output.open("x", newline="", encoding="utf-8") as target:
        reader, writer = csv.reader(source, delimiter="\t"), csv.writer(target, lineterminator="\n")
        for row in reader:
            if row and row[0] == "!series_matrix_table_begin":
                break
        header = next(reader, [])
        if (not header or header[0] != "ID_REF" or len(set(header[1:])) != len(wanted)
                or len(header) != len(wanted) + 1 or set(header[1:]) != set(wanted)):
            fail("Expression columns do not match the clinical sample metadata.")
        positions = [header.index(sample) for sample in wanted]
        writer.writerow(["feature_id"] + [r["sample_id"] for r in samples])
        for row in reader:
            check_cancel()
            if row and row[0] == "!series_matrix_table_end":
                break
            if len(row) != len(header) or not row[0].strip() or row[0] in seen:
                fail("Expression table contains invalid or duplicate feature coordinates.")
            seen.add(row[0])
            values = [row[i] for i in positions]
            try:
                if any(not math.isfinite(float(v)) for v in values if v not in MISSING):
                    fail("Expression table contains non-finite values.")
            except ValueError:
                fail("Expression table contains invalid numeric values.")
            writer.writerow([row[0]] + ["" if v in MISSING else v for v in values])
        else:
            fail("Expression table is truncated.")
    if not seen:
        fail("Expression table contains no features.")
    return len(seen)


def prepare_data(source, output, *, check_cancel=lambda: None):
    """Prepare source products in a fresh staging directory, not an active dataset.

    The caller adds ClarIDs, manifests and validation before installation.
    """
    verify_source(source)
    command = preparation_command("convert-pheno")
    if not command:
        fail("Convert-Pheno is not installed. Install the preparation runtime first.")
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("clinical", "assays", "provenance"):
        (output / directory).mkdir()
    records, samples, inputs = clinical_inputs(metadata(source))
    check_cancel()
    convert_clinical(records, inputs, output / "provenance", command)
    check_cancel()
    (output / "clinical/records.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "assays/samples.tsv", samples, "\t")
    features = expression(source, output / "assays/expression.csv", samples, check_cancel)
    return dict(patients=len({r["patient_id"] for r in records}), snapshots=len(records),
                samples=len(samples), features=features, measures=sum(len(r["measures"]) for r in records))


def codebook_path():
    configured = app_env("COHORTOME_CLARID_CODEBOOK", "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        fail("The configured ClarID codebook is unavailable.")
    command = preparation_command("clarid-tools")
    if command:
        root = Path(command[-1]).resolve().parent.parent
        native = root / "share/versions/0.04/clarid-codebook.yaml"
        if native.is_file():
            return native
        books = list((root / "perl").glob("**/versions/0.04/clarid-codebook.yaml"))
        if len(books) == 1:
            return books[0]
    fail("ClarID codebook 0.04 is unavailable. Native installations can set COHORTOME_CLARID_CODEBOOK.")


def preflight():
    for tool, expected in (("convert-pheno", "0.35"), ("clarid-tools", "0.04")):
        command = preparation_command(tool)
        if not command:
            fail(f"{tool} is not installed. Install the preparation runtime first.")
        try:
            version = subprocess.check_output([*command, "--version"], text=True,
                                              stderr=subprocess.DEVNULL, timeout=30).strip().split()[-1]
        except (OSError, subprocess.SubprocessError, IndexError):
            fail(f"{tool} could not start. Check the preparation runtime.")
        if version != expected:
            fail(f"This recipe requires {tool} {expected}.")
    codebook_path()


def identifiers(package, check_cancel):
    book = yaml.safe_load(codebook_path().read_text(encoding="utf-8"))
    if str(book["metadata"]["version"]) != "0.04":
        fail("This recipe requires ClarID codebook 0.04.")
    book["entities"]["subject"]["study"]["GSE85034"] = dict(
        code="GSE85034", stub_code="G850", label="GSE85034", id="NCIT:C17998")
    book["metadata"]["local_version"] = "GSE85034-1"
    folder = package / "identifiers"
    folder.mkdir()
    codebook = folder / "clarid-codebook.yaml"
    codebook.write_text(yaml.safe_dump(book, sort_keys=False), encoding="utf-8")
    records = json.loads((package / "clinical/records.json").read_text(encoding="utf-8"))
    rows = [dict(unique_id=pid, subject_id=i, study="GSE85034", type="Case", condition="L40.9",
                 sex="Not Available", age_group="Not Available")
            for i, pid in enumerate(sorted({r["patient_id"] for r in records}), 1)]
    source = package / "provenance/subjects.csv"
    write_csv(source, rows)
    command = preparation_command("clarid-tools")
    for fmt, column in (("human", "clar_id"), ("stub", "stub_id")):
        check_cancel()
        encoded, ids, decoded = [package / "provenance" / f"{fmt}-{kind}.csv" for kind in ("encoded", "ids", "decoded")]
        base = [*command, "code", "--entity", "subject", "--format", fmt, "--codebook", str(codebook), "--sep", ","]
        try:
            subprocess.run([*base, "--action", "encode", "--infile", str(source), "--outfile", str(encoded)],
                           check=True, capture_output=True, timeout=120)
            with encoded.open(encoding="utf-8", newline="") as handle:
                result = {r["unique_id"]: r[column] for r in csv.DictReader(handle)}
            for row in rows:
                row[column] = result[row["unique_id"]]
            write_csv(ids, [{"unique_id": r["unique_id"], column: r[column]} for r in rows])
            subprocess.run([*base, "--action", "decode", "--infile", str(ids), "--outfile", str(decoded),
                            "--with-condition-name"], check=True, capture_output=True, timeout=120)
            with decoded.open(encoding="utf-8", newline="") as handle:
                recovered = {r["unique_id"]: r for r in csv.DictReader(handle)}
            for row in rows:
                value = recovered[row["unique_id"]]
                if (int(value["subject_id"]) != row["subject_id"] or value["condition"] != "L40.9"
                        or value["study"] != ("GSE85034" if fmt == "human" else "G850")):
                    fail("ClarID round-trip validation failed.")
                for field in ("type", "sex", "age_group"):
                    expected = row[field]
                    if fmt == "human" and field in {"type", "sex"}:
                        vocabulary = book["entities"]["subject"][field].get(expected)
                        vocabulary = vocabulary or book["entities"]["_defaults"][expected]
                        expected = vocabulary["code"]
                    if value[field] != expected:
                        fail("ClarID demographic or subject-type round-trip validation failed.")
                row["condition_name"] = value["condition_name"]
        except (OSError, subprocess.SubprocessError):
            fail("ClarID preparation failed. Check the installed preparation tools.")
        for path in (encoded, ids, decoded):
            path.unlink()
    write_csv(folder / "clarid_subjects.csv", rows)


def build_package(source, archive, *, check_cancel=lambda: None, report=lambda **kw: None):
    from app.geo_source import GSE85034
    from app.dataset_validation import validate_package

    preflight()
    package = archive.parent / "gse85034"
    report(message="Mapping clinical records and preparing expression data locally…")
    counts = prepare_data(source, package, check_cancel=check_cancel)
    if counts != dict(patients=30, snapshots=150, samples=179, features=47323, measures=149):
        fail("Prepared GSE85034 counts differ from the reviewed recipe.")
    report(message="Generating subject ClarIDs…")
    identifiers(package, check_cancel)

    def write_json(path, value):
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    name = "Psoriasis adalimumab/methotrexate skin study"
    write_json(package / "manifest.json", dict(schema_version=1, name=name, study_design="longitudinal",
        clinical={"representation": "snapshot"}, identifiers={"clarid_subjects": dict(
            entity="subject", file="identifiers/clarid_subjects.csv", delimiter=",", codebook_version="0.04", tools_version="0.04")}))
    write_json(package / "assays/manifest.json", {"version": 1, "assays": [dict(
        assay_id="gse85034_microarray", label=name + " expression", modality="transcriptomics",
        data_type="microarray_expression", level="sample", feature_namespace="illumina_probe_id",
        feature_id_column="feature_id", sample_id_column="matrix_columns", patient_id_column="patient_id",
        patient_linkage="sample_metadata_file", sample_metadata_file="assays/samples.tsv",
        file="assays/expression.csv", feature_count=counts["features"])]})
    write_json(package / "provenance/preparation.json", dict(source=GSE85034, counts=counts,
        tools={"convert-pheno": "0.35", "clarid-tools": "0.04"},
        mapping_sha256=hashlib.sha256(MAPPING.encode()).hexdigest()))
    (package / "README.md").write_text(
        "# GSE85034\n\nDownloaded directly from GEO and prepared locally by COHORTome.\n"
        "Source: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE85034\n\n"
        "Normalized microarray expression, not RNA-seq counts. All source biopsies retained; "
        "no additional normalization or feature filtering. One BFF record per subject/visit. "
        "Paired biopsies are not independent patients. PASI and treatment groups are mapped with Convert-Pheno. "
        "Unknown sex/age and calendar dates are not inferred. WK 1NL/WK 1LS retain their ambiguous source timing.\n\n"
        "Public availability does not establish an unrestricted redistribution licence. "
        "Review GEO and study-specific terms before use or redistribution; cite the original study. "
        "COHORTome Store does not host this data product.\n", encoding="utf-8")
    check_cancel()
    report(message="Validating the prepared dataset…")
    validation = validate_package(package)
    hashes = {}
    for path in sorted(package.rglob("*")):
        if path.is_file():
            with path.open("rb") as handle:
                hashes[path.relative_to(package).as_posix()] = hashlib.file_digest(handle, "sha256").hexdigest()
    write_json(package / "resource.json", dict(manifest_version=1, schema_version=1, dataset_id="gse85034",
        version="0.1.0-preview", recipe_version=1, distribution_status="locally-built",
        sources=[GSE85034["url"]], source_files_sha256={source.name: GSE85034["sha256"]},
        files_sha256=hashes, validation=validation))
    # Fixed timestamps and permissions make repeated builds byte-identical.
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as bundle:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                check_cancel()
                entry = zipfile.ZipInfo("gse85034/" + path.relative_to(package).as_posix(), (1980, 1, 1, 0, 0, 0))
                entry.external_attr = 0o100644 << 16
                with path.open("rb") as incoming, bundle.open(entry, "w") as outgoing:
                    while chunk := incoming.read(1024 * 1024):
                        check_cancel()
                        outgoing.write(chunk)
    return counts
