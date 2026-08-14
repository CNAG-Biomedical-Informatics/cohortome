from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Set

from app.dicom import dicom_studies
from app.query_store import assay_dataset_inventory, assay_dataset_matrix_preview, clinical_workspace_inventory


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
    if text.startswith("flow_cytometry") or text.startswith("immune_cell"):
        return "flow_cytometry"
    if text.startswith("serology"):
        return "serology"
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
        "flow_cytometry": "Immune-cell abundance",
        "serology": "Serology",
        "genotyping": "Genotyping",
    }
    return labels.get(key, key.replace("_", " ").title())


def _column_key(*parts: Any) -> str:
    return ".".join(str(part or "").strip().replace(" ", "_") for part in parts if str(part or "").strip())


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


def _base_matrix_columns() -> List[Dict[str, Any]]:
    return [
        {"key": "patient_id", "label": "Patient ID", "source": "clinical", "role": "identifier", "modality": "clinical"},
        {"key": "sample_id", "label": "Sample/timepoint ID", "source": "clinical", "role": "identifier", "modality": "clinical"},
        {"key": "visit_id", "label": "Visit ID", "source": "clinical", "role": "identifier", "modality": "clinical"},
        {"key": "event_date", "label": "Event date", "source": "clinical", "role": "identifier", "modality": "clinical"},
        {"key": "clinical.sex", "label": "Sex", "source": "clinical", "role": "covariate", "modality": "clinical"},
        {"key": "clinical.disease_count", "label": "Disease count", "source": "clinical", "role": "covariate", "modality": "clinical"},
        {"key": "clinical.medication_count", "label": "Medication count", "source": "clinical", "role": "covariate", "modality": "clinical"},
        {"key": "clinical.diseases", "label": "Diseases", "source": "clinical", "role": "annotation", "modality": "clinical"},
        {"key": "clinical.medications", "label": "Medications", "source": "clinical", "role": "annotation", "modality": "clinical"},
    ]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _missingness(columns: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    data_columns = [column for column in columns if column.get("role") != "identifier"]
    payload = []
    row_count = len(rows)
    for column in data_columns:
        key = str(column.get("key") or "")
        missing = sum(1 for row in rows if _is_missing((row.get("values") or {}).get(key)))
        payload.append(
            {
                "key": key,
                "label": column.get("label") or key,
                "missing_count": missing,
                "missing_fraction": round(missing / row_count, 4) if row_count else 0.0,
            }
        )
    return payload


def _row_values_for_sample(preview: Dict[str, Any], sample_id: str) -> Dict[str, Any]:
    sample_values = preview.get("sample_values")
    if not isinstance(sample_values, dict):
        return {}
    values = sample_values.get(sample_id)
    return values if isinstance(values, dict) else {}


def multimodal_feature_matrix(data_dir: str, max_features_per_dataset: int = 3, max_rows: int = 25) -> Dict[str, Any]:
    clinical = clinical_workspace_inventory(data_dir)
    patients_by_id = {
        _clean(item.get("patient_id")): item
        for item in clinical.get("patients") or []
        if isinstance(item, dict) and _clean(item.get("patient_id"))
    }
    diseases_by_patient = {
        _clean(patient_id): [str(disease or "").strip() for disease in diseases or [] if str(disease or "").strip()]
        for patient_id, diseases in (clinical.get("diseases_by_patient") or {}).items()
    }
    medications_by_patient = {
        _clean(patient_id): [str(medication or "").strip() for medication in medications or [] if str(medication or "").strip()]
        for patient_id, medications in (clinical.get("medications_by_patient") or {}).items()
    }
    sample_items = [item for item in clinical.get("samples") or [] if isinstance(item, dict)]
    if not sample_items:
        sample_items = [
            {"patient_id": patient_id, "sample_id": "", "visit_id": "", "event_date": ""}
            for patient_id in sorted(patients_by_id)
        ]

    columns = _base_matrix_columns()
    rows: List[Dict[str, Any]] = []
    for item in sample_items:
        patient_id = _clean(item.get("patient_id"))
        sample_id = _clean(item.get("sample_id"))
        patient = patients_by_id.get(patient_id, {})
        values = {
            "patient_id": patient_id,
            "sample_id": sample_id,
            "visit_id": _clean(item.get("visit_id")),
            "event_date": _clean(item.get("event_date")),
            "clinical.sex": _clean(patient.get("sex")),
            "clinical.disease_count": int(patient.get("disease_count") or len(diseases_by_patient.get(patient_id, []))),
            "clinical.medication_count": int(patient.get("medication_count") or len(medications_by_patient.get(patient_id, []))),
            "clinical.diseases": "; ".join(diseases_by_patient.get(patient_id, [])),
            "clinical.medications": "; ".join(medications_by_patient.get(patient_id, [])),
        }
        rows.append(
            {
                "row_id": sample_id or patient_id,
                "patient_id": patient_id,
                "sample_id": sample_id,
                "visit_id": values["visit_id"],
                "event_date": values["event_date"],
                "values": values,
            }
        )

    row_by_sample = {row["sample_id"]: row for row in rows if row.get("sample_id")}
    feature_groups: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    selected_feature_count = 0
    assay_items = assay_dataset_inventory(data_dir)
    for assay in assay_items:
        dataset_name = _clean(assay.get("dataset_name") or assay.get("assay_id"))
        if not dataset_name:
            continue
        preview = assay_dataset_matrix_preview(data_dir, dataset_name, feature_limit=max_features_per_dataset)
        if not preview:
            continue
        modality = _normalize_modality(preview.get("modality"))
        features = [feature for feature in preview.get("features") or [] if isinstance(feature, dict)]
        assay_sample_ids = {_clean(sample_id) for sample_id in preview.get("sample_ids") or [] if _clean(sample_id)}
        exact_matches = sorted(sample_id for sample_id in assay_sample_ids if sample_id in row_by_sample)
        if assay_sample_ids and not exact_matches and set(assay.get("patient_ids") or []).intersection(patients_by_id):
            warnings.append(
                {
                    "severity": "warning",
                    "kind": "patient_overlap_without_exact_sample_match",
                    "dataset_name": dataset_name,
                    "message": f"{assay.get('label') or dataset_name} overlaps clinical patients but has no exact sample/timepoint ID match.",
                }
            )
        group_columns = []
        for feature in features:
            feature_id = _clean(feature.get("feature_id"))
            if not feature_id:
                continue
            key = _column_key(dataset_name, feature_id)
            label = _clean(feature.get("label")) or feature_id
            column = {
                "key": key,
                "label": label,
                "source": "assay",
                "role": "feature",
                "modality": modality,
                "dataset_name": dataset_name,
                "feature_id": feature_id,
                "value_kind": preview.get("value_kind") or preview.get("data_type") or "feature_value",
            }
            columns.append(column)
            group_columns.append(column)
            selected_feature_count += 1
            for sample_id in exact_matches:
                row_values = _row_values_for_sample(preview, sample_id)
                row_by_sample[sample_id]["values"][key] = row_values.get(feature_id)
        if group_columns:
            feature_groups.append(
                {
                    "dataset_name": dataset_name,
                    "label": preview.get("label") or assay.get("label") or dataset_name,
                    "modality": modality,
                    "data_type": preview.get("data_type") or assay.get("data_type") or "",
                    "feature_count_selected": len(group_columns),
                    "sample_count": len(assay_sample_ids),
                    "exact_sample_match_count": len(exact_matches),
                    "columns": [{"key": column["key"], "label": column["label"], "feature_id": column["feature_id"]} for column in group_columns],
                }
            )

    studies = dicom_studies(data_dir)
    if studies:
        dicom_count_key = "dicom.study_count"
        dicom_ready_key = "dicom.ohif_ready"
        columns.extend(
            [
                {"key": dicom_count_key, "label": "DICOM study count", "source": "dicom", "role": "viewer_metadata", "modality": "dicom"},
                {"key": dicom_ready_key, "label": "OHIF-ready DICOM", "source": "dicom", "role": "viewer_metadata", "modality": "dicom"},
            ]
        )
        selected_feature_count += 2
        dicom_by_sample: Dict[str, List[Dict[str, Any]]] = {}
        dicom_by_patient: Dict[str, List[Dict[str, Any]]] = {}
        for study in studies:
            sample_id = _clean(study.get("sample_id"))
            patient_id = _clean(study.get("patient_id"))
            if sample_id:
                dicom_by_sample.setdefault(sample_id, []).append(study)
            if patient_id:
                dicom_by_patient.setdefault(patient_id, []).append(study)
        exact_dicom_matches = 0
        for row in rows:
            matched = dicom_by_sample.get(row.get("sample_id") or "")
            if matched:
                exact_dicom_matches += 1
            else:
                matched = dicom_by_patient.get(row.get("patient_id") or "")
            row["values"][dicom_count_key] = len(matched or [])
            row["values"][dicom_ready_key] = "yes" if matched else "no"
        feature_groups.append(
            {
                "dataset_name": "dicom_studies",
                "label": "DICOM studies",
                "modality": "dicom",
                "data_type": "viewer_metadata",
                "feature_count_selected": 2,
                "sample_count": len({_clean(study.get("sample_id")) for study in studies if _clean(study.get("sample_id"))}),
                "exact_sample_match_count": exact_dicom_matches,
                "columns": [{"key": dicom_count_key, "label": "DICOM study count"}, {"key": dicom_ready_key, "label": "OHIF-ready DICOM"}],
            }
        )

    missingness = _missingness(columns, rows)
    missing_cells = sum(item["missing_count"] for item in missingness)
    total_cells = len(rows) * len([column for column in columns if column.get("role") != "identifier"])
    preview_rows = rows[: max(1, int(max_rows or 25))]
    return {
        "metadata": {
            "join_level": "sample",
            "row_count": len(rows),
            "preview_row_count": len(preview_rows),
            "column_count": len(columns),
            "assay_dataset_count": len(assay_items),
            "feature_group_count": len(feature_groups),
            "selected_feature_count": selected_feature_count,
            "missing_cell_count": missing_cells,
            "missing_fraction": round(missing_cells / total_cells, 4) if total_cells else 0.0,
            "notes": [
                "Values are joined at exact clinical sample/timepoint ID when available.",
                "DICOM contributes viewer metadata only; raw pixels are not converted into numeric imaging features by this matrix builder.",
            ],
        },
        "columns": columns,
        "rows": preview_rows,
        "missingness": missingness,
        "feature_groups": feature_groups,
        "warnings": warnings,
    }


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
