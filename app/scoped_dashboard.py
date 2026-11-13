"""Patient-scoped assay coverage without importing external measurement matrices."""
import csv
from pathlib import Path

from app.identities import identity_key
from app.query_store import (
    _assay_inventory_metadata, _assay_manifest_items_for_root, _connect,
    _detect_matrix_delimiter, _manifest_assay_sample_patient_links, ensure_query_store,
)


def scoped_assay_inventory(roots: dict, members: list) -> list:
    """Count explicitly linked samples; never reuse whole-cohort expression statistics.

    Input members must already have been authorized and resolved by the caller.
    An empty selection is deliberately different from an unrestricted inventory.
    """
    selected = {}
    for member in members:
        selected.setdefault(member['dataset_id'], set()).add(member['patient_id'])
    result = []
    multi = len(roots) > 1
    for dataset, root in roots.items():
        patients = selected.get(dataset, set())
        if not patients:
            continue
        root = Path(root).resolve()
        # Do not call the ordinary inventory here: its whole-matrix feature and
        # expression summaries can scan external values that this view discards.
        ensure_query_store(str(root))
        inventory = []
        with _connect(str(root)) as connection:
            clinical = {row[0] for row in connection.execute('SELECT patient_id FROM patients').fetchall()}
            links = {}
            for name, sample, patient in connection.execute(
                    'SELECT dataset_name, sample_id, patient_id FROM assay_samples').fetchall():
                links.setdefault(name, {})[sample] = patient
            feature_counts = dict(connection.execute(
                'SELECT dataset_name, count(DISTINCT gene_id) FROM transcript_counts GROUP BY dataset_name').fetchall())
            for name, modality, data_type in connection.execute(
                    'SELECT dataset_name, max(modality), max(data_type) FROM assay_samples GROUP BY dataset_name').fetchall():
                inventory.append(dict(dataset_name=name, label=name, modality=modality,
                    data_type=data_type, feature_count=feature_counts.get(name),
                    **_assay_inventory_metadata(modality, data_type)))
        for item in _assay_manifest_items_for_root(root):
            name = str(item.get('assay_id') or Path(str(item.get('file') or '')).stem)
            if name in links:
                continue
            path = (root / str(item.get('file') or '')).resolve()
            if not path.is_relative_to(root):
                raise ValueError('An assay input is outside its dataset.')
            with path.open(encoding='utf-8-sig', newline='') as handle:
                header = handle.readline()
            samples = [value.strip() for value in next(csv.reader([header], delimiter=_detect_matrix_delimiter(header)))[1:] if value.strip()]
            links[name] = _manifest_assay_sample_patient_links(root, item, samples)['links']
            declared_count = item.get('feature_count')
            try:
                feature_count = int(declared_count) if declared_count is not None else None
            except (TypeError, ValueError):
                feature_count = None
            if feature_count is not None and feature_count < 0:
                feature_count = None
            modality, data_type = item.get('modality') or 'assay', item.get('data_type') or 'feature_matrix'
            inventory.append(dict(dataset_name=name, label=item.get('label') or name,
                modality=modality, data_type=data_type, feature_count=feature_count,
                **_assay_inventory_metadata(modality, data_type, item)))
        for original in inventory:
            name = original['dataset_name']
            matched = {sample: patient for sample, patient in links.get(name, {}).items() if patient in patients}
            if not matched:
                continue
            patient_ids = sorted(set(matched.values()))
            sample_ids = sorted(matched)
            scoped_name = name
            if multi:
                separator = '__' if original.get('modality') == 'transcriptomics' and original.get('data_type') == 'raw_counts' else '::'
                scoped_name = dataset + separator + name
            result.append({**original,
                'dataset_name': scoped_name, 'assay_id': scoped_name,
                'label': f"{dataset} — {original.get('label') or name}" if multi else original.get('label', name),
                'sample_ids': [identity_key(dataset, 'sample', value) if multi else value for value in sample_ids],
                'patient_ids': [identity_key(dataset, 'patient', value) if multi else value for value in patient_ids],
                'sample_count': len(sample_ids), 'patient_count': len(patient_ids),
                'linked_sample_count': len(sample_ids), 'unlinked_sample_count': 0,
                'clinical_overlap_patient_count': len(set(patient_ids) & clinical),
                'mean_total_counts_per_sample': None, 'mean_detected_genes_per_sample': None,
                'top_genes': [], 'count_summary_status': 'not_calculated_for_scope',
                'scope_applied': True})
    return sorted(result, key=lambda item: item['dataset_name'])
