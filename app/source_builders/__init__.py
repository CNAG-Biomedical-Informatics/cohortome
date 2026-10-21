"""Reviewed, shipped dataset preparation recipes; never downloaded code."""
import json
from pathlib import Path
import zipfile

from app.geo_source import fetch_source, verify_source, SourcePreparationError
from app.source_builders.common import sha256, write_json


def source_files(dataset_id):
    specs = json.loads(Path(__file__).with_name("sources.json").read_text())
    if dataset_id not in specs:
        raise SourcePreparationError("Unsupported source preparation recipe.")
    return specs[dataset_id]


def fetch(dataset_id, directory, check_cancel, report):
    directory.mkdir()
    specs = source_files(dataset_id)
    total, done = sum(s["bytes"] for s in specs), 0
    for spec in specs:
        check_cancel()
        fetch_source(directory / spec["filename"], spec=spec, check_cancel=check_cancel,
            report=lambda **kw: report(bytes=done + kw["bytes"], total=total))
        done += spec["bytes"]


def build(dataset_id, source, archive, check_cancel, report):
    from app.dataset_validation import validate_package
    from app.geo_gse85034 import preflight
    preflight()
    specs = source_files(dataset_id)
    for spec in specs:
        check_cancel()
        verify_source(source / spec["filename"], spec)
    if dataset_id == "ibdmdb":
        from app.source_builders.ibdmdb import prepare
    elif dataset_id == "gse117239":
        from app.source_builders.psoriasis import prepare
    elif dataset_id == "gse191328":
        from app.source_builders.ibd_rna import prepare
    elif dataset_id == "gse42296":
        from app.source_builders.cd_ra import prepare
    elif dataset_id == "gse68310":
        from app.source_builders.respiratory import prepare
    else:
        raise SourcePreparationError("Unsupported source preparation recipe.")
    package = archive.parent / dataset_id
    counts = prepare(source, package, check_cancel, report)
    check_cancel()
    report(message="Validating the prepared dataset…")
    validation = validate_package(package)
    provenance = package / "provenance"
    provenance.mkdir(exist_ok=True)
    write_json(provenance / "preparation.json", dict(recipe_version=1, sources=specs, counts=counts,
        tools={"convert-pheno": "0.35", "clarid-tools": "0.04"}))
    hashes = {p.relative_to(package).as_posix(): sha256(p) for p in sorted(package.rglob("*")) if p.is_file()}
    write_json(package / "resource.json", dict(manifest_version=1, schema_version=1, dataset_id=dataset_id,
        version="0.1.0-preview", recipe_version=1, distribution_status="locally-built", validation=validation,
        sources=[s["url"] for s in specs], source_files_sha256={s["filename"]: s["sha256"] for s in specs},
        files_sha256=hashes))
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as bundle:
        for path in sorted(package.rglob("*")):
            if not path.is_file():
                continue
            check_cancel()
            entry = zipfile.ZipInfo(dataset_id + "/" + path.relative_to(package).as_posix(), (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            with path.open("rb") as incoming, bundle.open(entry, "w") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    check_cancel()
                    outgoing.write(chunk)
    return counts
