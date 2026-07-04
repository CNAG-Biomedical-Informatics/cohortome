#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASETS = [
    ROOT / "default_dataset",
    ROOT / "dataset-large",
    ROOT / "private_dataset",
]


def _read_manifest(dataset_root: Path) -> dict:
    path = dataset_root / "assays" / "imaging" / "dicom_studies.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _pixel_array(seed: int, rows: int = 64, cols: int = 64) -> np.ndarray:
    y, x = np.mgrid[0:rows, 0:cols]
    image = ((x * 7 + y * 11 + seed * 19) % 256).astype(np.uint8)
    image[rows // 4 : rows // 2, cols // 4 : cols // 2] = (80 + seed * 31) % 256
    image[rows // 2 : rows * 3 // 4, cols // 2 : cols * 3 // 4] = (170 + seed * 17) % 256
    return image


def _write_instance(path: Path, study: dict, series: dict, sop_instance_uid: str, seed: int) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0)
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.10.54321.999"

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop_instance_uid
    ds.StudyInstanceUID = str(study["study_instance_uid"])
    ds.SeriesInstanceUID = str(series["series_instance_uid"])
    ds.Modality = str(study.get("modality") or "OT")
    ds.PatientID = str(study.get("patient_id") or "SYNTHETIC")
    ds.PatientName = "Synthetic^BRN"
    ds.PatientBirthDate = ""
    ds.PatientSex = "O"
    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")
    ds.SeriesDate = ds.StudyDate
    ds.SeriesTime = ds.StudyTime
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime
    ds.StudyDescription = str(study.get("study_description") or "Synthetic BRN study")
    ds.SeriesDescription = str(series.get("series_description") or "Synthetic BRN series")
    ds.BodyPartExamined = "SYNTHETIC"
    ds.Manufacturer = "Biomedical Research Navigator"
    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 64
    ds.Columns = 64
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.InstanceNumber = 1
    ds.PixelData = _pixel_array(seed).tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(path, write_like_original=False)


def generate_dataset(dataset_root: Path) -> int:
    manifest = _read_manifest(dataset_root)
    studies = manifest.get("studies") if isinstance(manifest.get("studies"), list) else []
    output_dir = dataset_root / "assays" / "imaging" / "dicom"
    written = 0
    for study_index, study in enumerate(studies, start=1):
        if not isinstance(study, dict) or not study.get("study_instance_uid"):
            continue
        series_items = study.get("series") if isinstance(study.get("series"), list) else []
        for series_index, series in enumerate(series_items, start=1):
            if not isinstance(series, dict) or not series.get("series_instance_uid"):
                continue
            sop_uids = series.get("sop_instance_uids") if isinstance(series.get("sop_instance_uids"), list) else []
            if not sop_uids:
                sop_uids = [f"{series['series_instance_uid']}.1"]
            for instance_index, sop_uid in enumerate(sop_uids, start=1):
                filename = f"{study.get('study_id') or 'study'}__series{series_index}__instance{instance_index}.dcm"
                _write_instance(output_dir / filename, study, series, str(sop_uid), seed=study_index * 10 + instance_index)
                written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate tiny synthetic DICOM files for BRN fixture manifests.")
    parser.add_argument("dataset_roots", nargs="*", type=Path, help="Dataset roots to generate. Defaults to bundled fixtures.")
    args = parser.parse_args()
    roots = args.dataset_roots or DEFAULT_DATASETS
    total = 0
    for root in roots:
        count = generate_dataset(root.resolve())
        print(f"{root}: wrote {count} DICOM file{'s' if count != 1 else ''}")
        total += count
    print(f"Total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
