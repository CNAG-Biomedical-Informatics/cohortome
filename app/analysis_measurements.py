"""Numeric clinical inputs for the existing longitudinal analysis runners."""
import math

MEASUREMENT_RUNNERS = {"trajectory", "trajectory_compare", "treatment_response", "survival", "survival_compare"}


def measurement_options(data_dir, scope="", compare_scope="", compare_mode=False):
    # Use the same record matching, dates and values as the clinical runners.
    from app.analysis import (ensure_data_dir, parse_scope_ids, read_bff_records,
                              record_matches_scope, extract_record_patient_id,
                              extract_event_date, _parse_iso_date, _measure_label,
                              _measure_numeric_value, _measure_unit_label)
    scopes = [set(parse_scope_ids(scope))]
    if compare_mode:
        scopes.append(set(parse_scope_ids(compare_scope)))
    inventory = {}
    for _, _, record in read_bff_records(ensure_data_dir(data_dir)):
        patient = extract_record_patient_id(record)
        if not patient:
            continue
        matches = [record_matches_scope(record, ids) for ids in scopes]
        if not any(matches):
            continue
        dated = _parse_iso_date(extract_event_date(record))
        for measure in record.get("measures") or []:
            if not isinstance(measure, dict):
                continue
            label, value = _measure_label(measure), _measure_numeric_value(measure)
            if not label or value is None or not math.isfinite(value):
                continue
            entry = inventory.setdefault(label, {"units": set(), "groups": [{} for _ in scopes]})
            entry["units"].add(_measure_unit_label(measure) or "")
            for index, matches_scope in enumerate(matches):
                if matches_scope:
                    dates = entry["groups"][index].setdefault(patient, set())
                    if dated:
                        dates.add(dated)
    return [{"measure": label, "units": sorted(entry["units"]),
             "compatible_units": len(entry["units"]) == 1,
             "groups": [{"patient_count": len(group),
                         "dated_patient_count": sum(bool(dates) for dates in group.values()),
                         "repeated_patient_count": sum(len(dates) >= 2 for dates in group.values())}
                        for group in entry["groups"]]}
            for label, entry in sorted(inventory.items())]


def validate_measurement(data_dir, measurement, scope="", compare_scope="", compare_mode=False):
    if not measurement:
        raise RuntimeError("Choose a clinical measurement in Inputs before running this analysis.")
    options = measurement_options(data_dir, scope, compare_scope, compare_mode)
    selected = next((item for item in options if item["measure"] == measurement), None)
    if selected is None:
        raise RuntimeError("The selected measurement is not available in the current analysis scope.")
    if not selected["compatible_units"]:
        raise RuntimeError("This measurement has inconsistent units. Harmonize units before analysis.")
    if any(group["repeated_patient_count"] < 1 for group in selected["groups"]):
        raise RuntimeError("The selected measurement needs observations on at least two distinct dates for a patient in each analysis group.")
    return selected
