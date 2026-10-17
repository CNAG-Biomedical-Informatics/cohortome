#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASETS = [
    ROOT / "default_dataset",
    ROOT / "dataset-large",
    ROOT / "private_dataset",
]
SOURCE_DICOM_NAME = "procedural-brain-phantom-v1"
SYNTHETIC_LESION_PROFILES = {
    "ms_brain_mild": [
        (24, 40, 2, 650),
        (42, 28, 2, 520),
    ],
    "ms_brain_moderate": [
        (20, 38, 3, 760),
        (31, 45, 2, 620),
        (43, 25, 3, 700),
        (36, 18, 2, 540),
    ],
}


def _read_manifest(dataset_root: Path) -> dict:
    path = dataset_root / "assays" / "imaging" / "dicom_studies.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _source_image() -> FileDataset:
    """An anatomical-style phantom, not a patient scan or disease simulation."""
    size = 256
    y, x = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    radius = np.sqrt((x / .76) ** 2 + (y / .91) ** 2)
    angle = np.arctan2(y / .91, x / .76)
    pixels = np.zeros((size, size), dtype=float)
    pixels[(radius < 1) & (radius > .94)] = 480  # scalp
    pixels[(radius <= .94) & (radius > .89)] = 75  # dark skull
    pixels[(radius <= .89) & (radius > .85)] = 160  # CSF rim
    brain = radius <= .85
    folds = np.sin(26 * angle + 6 * np.sin(5 * angle) + 22 * radius)
    cortex = brain & (radius > .67 + .035 * folds)
    pixels[brain] = 700
    pixels[cortex] = 490
    sulci = cortex & (folds > .77) & (radius > .72)
    pixels[sulci] = 145
    # Two ventricular horns and interhemispheric fissure.
    ventricles = (((np.abs(x) - .13) / .085) ** 2 + ((y + .04) / .28) ** 2 < 1)
    pixels[ventricles] = 95
    pixels[(np.abs(x) < .012) & brain & (np.abs(y) > .28)] = 140
    # Smooth bias field and fixed noise give visible texture without source data.
    rng = np.random.default_rng(42)
    pixels[brain] += (22 * np.sin(35 * x) * np.cos(27 * y) + 45 * y + rng.normal(0, 9, pixels.shape))[brain]
    pixels = np.clip(pixels, 0, 1200).astype('<u2')
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset('', {}, file_meta=meta, preamble=b'\0' * 128)
    ds.SOPClassUID = MRImageStorage
    ds.Modality = 'MR'
    ds.Rows = ds.Columns = size
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelSpacing = [1, 1]
    ds.SliceThickness = 3
    ds.ImagePositionPatient = [-128, -128, 0]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.RescaleIntercept = 0
    ds.RescaleSlope = 1
    ds.WindowCenter = 450
    ds.WindowWidth = 1000
    ds.PixelData = pixels.tobytes()
    return ds


def _copy_attr(target: Dataset, source: Dataset, name: str) -> None:
    if name in source:
        setattr(target, name, getattr(source, name))


def _pixel_data(source: FileDataset, profile: str) -> tuple[bytes, int, int]:
    pixels = source.pixel_array.astype(np.int32, copy=True)
    for row, column, radius, boost in SYNTHETIC_LESION_PROFILES.get(profile, []):
        row, column, radius = row * 4, column * 4, radius * 4
        yy, xx = np.ogrid[: pixels.shape[0], : pixels.shape[1]]
        distance = ((yy - row) ** 2 + (xx - column) ** 2) ** 0.5
        mask = distance <= radius
        falloff = np.clip(1.0 - (distance / max(radius, 1)), 0.25, 1.0)
        pixels[mask] += (boost * falloff[mask]).astype(np.int32)
    pixels = np.clip(pixels, 0, np.iinfo(source.pixel_array.dtype).max).astype(source.pixel_array.dtype)
    return pixels.tobytes(), int(pixels.min()), int(pixels.max())


def _write_instance(path: Path, source: FileDataset, study: dict, series: dict, sop_instance_uid: str, instance_number: int) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0)
    profile = str(study.get("synthetic_profile") or "").strip()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = source.SOPClassUID
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.10.54321.999"
    file_meta.ImplementationVersionName = "COHORTOME_DICOM"

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.SOPClassUID = source.SOPClassUID
    ds.SOPInstanceUID = sop_instance_uid
    ds.StudyInstanceUID = str(study["study_instance_uid"])
    ds.SeriesInstanceUID = str(series["series_instance_uid"])
    ds.Modality = str(study.get("modality") or source.get("Modality", "MR"))
    ds.PatientID = str(study.get("patient_id") or "SYNTHETIC")
    ds.PatientName = "Synthetic^COHORTome"
    ds.PatientBirthDate = ""
    ds.PatientSex = "O"
    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")
    ds.SeriesDate = ds.StudyDate
    ds.SeriesTime = ds.StudyTime
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime
    ds.StudyDescription = str(study.get("study_description") or "Synthetic COHORTome study")
    ds.SeriesDescription = str(series.get("series_description") or "Synthetic COHORTome series")
    ds.BodyPartExamined = str(study.get("body_part") or ("BRAIN" if profile.startswith("ms_brain") else "SYNTHETIC"))
    ds.Manufacturer = "COHORTome"
    ds.ManufacturerModelName = "Procedural brain phantom"
    ds.ImageType = ["DERIVED", "SECONDARY", "COHORTOME"]
    ds.ProtocolName = ds.SeriesDescription
    ds.ScanningSequence = "SE"
    ds.SequenceVariant = "SK"
    ds.MRAcquisitionType = "2D"
    ds.MagneticFieldStrength = "1.5"
    ds.ImagedNucleus = "1H"
    ds.DerivationDescription = (
        f"Entirely procedural synthetic phantom ({SOURCE_DICOM_NAME}), not a patient scan or validated disease model; "
        f"profile={profile or 'source'}."
    )
    for name in [
        "SamplesPerPixel",
        "PhotometricInterpretation",
        "Rows",
        "Columns",
        "PixelSpacing",
        "BitsAllocated",
        "BitsStored",
        "HighBit",
        "PixelRepresentation",
        "SmallestImagePixelValue",
        "LargestImagePixelValue",
        "RescaleIntercept",
        "RescaleSlope",
        "WindowCenter",
        "WindowWidth",
        "SliceThickness",
        "ImagePositionPatient",
        "ImageOrientationPatient",
    ]:
        _copy_attr(ds, source, name)
    pixel_data, smallest_pixel, largest_pixel = _pixel_data(source, profile)
    ds.SmallestImagePixelValue = smallest_pixel
    ds.LargestImagePixelValue = largest_pixel
    ds.VOILUTFunction = "LINEAR"
    ds.PresentationLUTShape = "IDENTITY"
    ds.SeriesNumber = 1
    ds.InstanceNumber = instance_number
    ds.PixelData = pixel_data
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(path, write_like_original=False)


def generate_dataset(dataset_root: Path) -> int:
    manifest = _read_manifest(dataset_root)
    studies = manifest.get("studies") if isinstance(manifest.get("studies"), list) else []
    output_dir = dataset_root / "assays" / "imaging" / "dicom"
    source = _source_image()
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
                _write_instance(output_dir / filename, source, study, series, str(sop_uid), instance_number=instance_index)
                written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate tiny synthetic DICOM files for COHORTome fixture manifests.")
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
