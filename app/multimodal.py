from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Set

from app.dicom import dicom_studies
from app.query_store import assay_dataset_inventory, clinical_workspace_inventory


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_modality(value: Any) -> str:
    text = _clean(value).lower()
    if text.startswith("transcriptomics"):
        return "transcriptomics"
    if text.startswith("imaging") or text == "dicom":
        return "imaging"
    if text.startswith("olink"):
        return "olink"
    if text.startswith("proteomics"):
        return "proteomics"
    if text.startswith("genotyping") or text.startswith("variant"):
        return "genotyping"
    return text or "assay"


def _label_for_modality(key: str) -> str:
    labels = {
        "clinical": "Clinical",
        "transcriptomics": "Transcriptomics",
        "imaging": "Imaging features",
        "dicom": "DICOM studies",
        "olink": "OLINK",
        "proteomics": "Proteomics",
        "genotyping": "Genotyping",
    }
    return labels.get(key, key.replace("_", " ").title())


def _modality_item(
    key: str,
    *,
    dataset_count: int = 0,
    study_count: int = 0,
    patient_ids: Set[str] | None = None,
    sample_ids: Set[str] | None = None,
    feature_count: int = 0,
    clinical_patient_ids: Set[str] | None = None,
) -> Dict[str, Any]:
    patients = sorted(patient_ids or set())
    samples = sorted(sample_ids or set())
    clinical_patients = clinical_patient_ids or set()
    return {
        "key": key,
        "label": _label_for_modality(key),
        "dataset_count": int(dataset_count),
        "study_count": int(study_count),
        "patient_count": len(patients),
        "sample_count": len(samples),
        "feature_count": int(feature_count),
        "clinical_overlap_count": len(set(patients).intersection(clinical_patients)),
        "patient_ids": patients,
        "sample_ids": samples,
    }


def _compact_ids(values: Set[str], limit: int = 6) -> str:
    ordered = sorted(value for value in values if value)
    if not ordered:
        return ""
    suffix = f" and {len(ordered) - limit} more" if len(ordered) > limit else ""
    return ", ".join(ordered[:limit]) + suffix


def _ms_like_study(study: Dict[str, Any]) -> bool:
    text = " ".join(
        [
            _clean(study.get("label")),
            _clean(study.get("study_description")),
            _clean(study.get("study_id")),
        ]
    ).lower()
    return "multiple sclerosis" in text or "ms brain" in text or " ms " in f" {text} "


def _suggestions(modalities: Dict[str, Dict[str, Any]], pairwise: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    transcriptomics = modalities.get("transcriptomics", {})
    imaging = modalities.get("imaging", {})
    dicom = modalities.get("dicom", {})
    nonclinical_modalities = [item for key, item in modalities.items() if key != "clinical" and item.get("patient_count", 0)]
    nonclinical_pairwise = [item for item in pairwise if item.get("left") != "clinical" and item.get("right") != "clinical"]
    patient_overlap = max((item.get("patient_overlap_count", 0) for item in nonclinical_pairwise), default=0)
    sample_overlap = max((item.get("sample_overlap_count", 0) for item in nonclinical_pairwise), default=0)
    return [
        {
            "key": "dicom_review",
            "label": "Review DICOM studies in OHIF",
            "enabled": bool(dicom.get("study_count", 0)),
            "reason": "DICOM studies are linked to this workspace." if dicom.get("study_count", 0) else "No DICOM studies are configured.",
        },
        {
            "key": "imaging_feature_summary",
            "label": "Summarize derived imaging features",
            "enabled": bool(imaging.get("feature_count", 0) and imaging.get("clinical_overlap_count", 0)),
            "reason": "Imaging feature matrices overlap clinical patients." if imaging.get("clinical_overlap_count", 0) else "No clinical-linked imaging feature matrix is available.",
        },
        {
            "key": "transcriptomics_summary",
            "label": "Run transcriptomics summary",
            "enabled": bool(transcriptomics.get("dataset_count", 0) and transcriptomics.get("clinical_overlap_count", 0)),
            "reason": "Transcriptomics assays overlap clinical patients." if transcriptomics.get("clinical_overlap_count", 0) else "No clinical-linked transcriptomics assay is available.",
        },
        {
            "key": "patient_level_cross_modal",
            "label": "Explore patient-level cross-modal associations",
            "enabled": len(nonclinical_modalities) >= 2 and patient_overlap > 0,
            "reason": f"At least two modalities share {patient_overlap} patient{'s' if patient_overlap != 1 else ''}." if patient_overlap else "No patient-level overlap across non-clinical modalities.",
        },
        {
            "key": "visit_matched_multimodal",
            "label": "Explore visit-matched multimodal associations",
            "enabled": sample_overlap > 0,
            "reason": f"At least two modalities share {sample_overlap} exact sample ID{'s' if sample_overlap != 1 else ''}." if sample_overlap else "No exact sample ID overlap across modalities.",
        },
    ]


def multimodal_readiness(data_dir: str) -> Dict[str, Any]:
    clinical = clinical_workspace_inventory(data_dir)
    clinical_patients = set(clinical.get("patient_ids") or [])
    clinical_samples = set(clinical.get("sample_ids") or [])
    diseases_by_patient = {
        _clean(patient_id): {str(disease or "").strip() for disease in diseases or []}
        for patient_id, diseases in (clinical.get("diseases_by_patient") or {}).items()
    }
    assay_items = assay_dataset_inventory(data_dir)
    studies = dicom_studies(data_dir)

    modalities: Dict[str, Dict[str, Any]] = {
        "clinical": _modality_item(
            "clinical",
            dataset_count=1 if clinical_patients else 0,
            patient_ids=clinical_patients,
            sample_ids=clinical_samples,
            clinical_patient_ids=clinical_patients,
        )
    }
    modality_accumulators: Dict[str, Dict[str, Any]] = {}
    for assay in assay_items:
        key = _normalize_modality(assay.get("modality"))
        accumulator = modality_accumulators.setdefault(
            key,
            {"dataset_count": 0, "patient_ids": set(), "sample_ids": set(), "feature_count": 0},
        )
        accumulator["dataset_count"] += 1
        accumulator["patient_ids"].update(_clean(item) for item in assay.get("patient_ids") or [] if _clean(item))
        accumulator["sample_ids"].update(_clean(item) for item in assay.get("sample_ids") or [] if _clean(item))
        accumulator["feature_count"] += int(assay.get("feature_count") or assay.get("gene_count") or 0)
    for key, accumulator in modality_accumulators.items():
        modalities[key] = _modality_item(
            key,
            dataset_count=accumulator["dataset_count"],
            patient_ids=accumulator["patient_ids"],
            sample_ids=accumulator["sample_ids"],
            feature_count=accumulator["feature_count"],
            clinical_patient_ids=clinical_patients,
        )

    dicom_patients = {_clean(study.get("patient_id")) for study in studies if _clean(study.get("patient_id"))}
    dicom_samples = {_clean(study.get("sample_id")) for study in studies if _clean(study.get("sample_id"))}
    modalities["dicom"] = _modality_item(
        "dicom",
        study_count=len(studies),
        patient_ids=dicom_patients,
        sample_ids=dicom_samples,
        clinical_patient_ids=clinical_patients,
    )

    pairwise = []
    for left_key, right_key in combinations(sorted(modalities), 2):
        left = modalities[left_key]
        right = modalities[right_key]
        patient_overlap = set(left.get("patient_ids") or []).intersection(right.get("patient_ids") or [])
        sample_overlap = set(left.get("sample_ids") or []).intersection(right.get("sample_ids") or [])
        pairwise.append(
            {
                "left": left_key,
                "right": right_key,
                "left_label": left.get("label", _label_for_modality(left_key)),
                "right_label": right.get("label", _label_for_modality(right_key)),
                "patient_overlap_count": len(patient_overlap),
                "sample_overlap_count": len(sample_overlap),
                "patient_ids": sorted(patient_overlap),
                "sample_ids": sorted(sample_overlap),
            }
        )

    issues = []
    for key, item in modalities.items():
        if key == "clinical":
            continue
        missing = set(item.get("patient_ids") or []).difference(clinical_patients)
        if missing:
            issues.append(
                {
                    "severity": "warning",
                    "kind": "missing_clinical_patient",
                    "modality": key,
                    "message": f"{item.get('label')} has {len(missing)} patient{'s' if len(missing) != 1 else ''} absent from clinical records: {_compact_ids(missing)}.",
                    "patient_ids": sorted(missing),
                }
            )
    for study in studies:
        patient_id = _clean(study.get("patient_id"))
        sample_id = _clean(study.get("sample_id"))
        if patient_id and patient_id not in clinical_patients:
            issues.append(
                {
                    "severity": "warning",
                    "kind": "dicom_patient_without_clinical_record",
                    "modality": "dicom",
                    "message": f"DICOM study {study.get('label') or study.get('study_instance_uid')} links to patient {patient_id}, but that patient is not in clinical records.",
                    "patient_id": patient_id,
                    "study_instance_uid": study.get("study_instance_uid", ""),
                }
            )
        if sample_id and sample_id not in clinical_samples:
            issues.append(
                {
                    "severity": "warning",
                    "kind": "dicom_sample_without_clinical_timepoint",
                    "modality": "dicom",
                    "message": f"DICOM study {study.get('label') or study.get('study_instance_uid')} links to sample {sample_id}, but that sample is not an exact clinical timepoint ID.",
                    "sample_id": sample_id,
                    "study_instance_uid": study.get("study_instance_uid", ""),
                }
            )
        if _ms_like_study(study) and patient_id and "Multiple Sclerosis" not in diseases_by_patient.get(patient_id, set()):
            issues.append(
                {
                    "severity": "error",
                    "kind": "ms_dicom_without_ms_diagnosis",
                    "modality": "dicom",
                    "message": f"MS-labeled DICOM study {study.get('label') or study.get('study_instance_uid')} is linked to {patient_id}, but that patient does not carry a Multiple Sclerosis diagnosis.",
                    "patient_id": patient_id,
                    "study_instance_uid": study.get("study_instance_uid", ""),
                }
            )

    nonclinical_patient_sets = [
        set(item.get("patient_ids") or [])
        for key, item in modalities.items()
        if key != "clinical" and item.get("patient_ids")
    ]
    multimodal_patients = set().union(*nonclinical_patient_sets) if nonclinical_patient_sets else set()
    multimodal_patients = {patient for patient in multimodal_patients if sum(patient in patients for patients in nonclinical_patient_sets) >= 2}
    exact_sample_overlap_count = max(
        (
            item.get("sample_overlap_count", 0)
            for item in pairwise
            if item.get("left") != "clinical" and item.get("right") != "clinical"
        ),
        default=0,
    )
    ordered_modalities = [modalities[key] for key in sorted(modalities)]
    return {
        "workspace": {
            "patient_count": len(clinical_patients),
            "sample_count": len(clinical_samples),
            "modality_count": sum(1 for key, item in modalities.items() if key != "clinical" and (item.get("dataset_count") or item.get("study_count"))),
            "multimodal_patient_count": len(multimodal_patients),
            "exact_sample_overlap_count": exact_sample_overlap_count,
        },
        "modalities": ordered_modalities,
        "pairwise_overlaps": pairwise,
        "issues": issues,
        "suggestions": _suggestions(modalities, pairwise),
    }
