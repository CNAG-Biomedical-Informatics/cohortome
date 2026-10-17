"""Resolve cohort membership against authorized, dataset-specific inventories."""
from app.bff import ensure_data_dir, extract_patient_id, normalize_value, read_bff_records
from app.identities import qualified_member, decode_identity


def source_inventory(root):
    patients, samples = set(), {}
    for _, _, record in read_bff_records(ensure_data_dir(root)):
        pid = str(extract_patient_id(record) or '').strip()
        sid = str(normalize_value(record.get('id')) or '').strip()
        if pid:
            patients.add(pid)
        if sid and pid:
            samples.setdefault(sid, set()).add(pid)
    # Includes assay-only participants and explicitly declared sample links.
    from app.patient_overview import sample_inventory
    rows, _ = sample_inventory(root, include_imaging=True)
    for row in rows:
        patients.add(row['patient_id'])
        samples.setdefault(row['sample_id'], set()).add(row['patient_id'])
    return patients, samples


def resolve_members(roots, *, members=None, patient_ids=(), sample_ids=(), id_type='patient'):
    inventories = {dataset: source_inventory(root) for dataset, root in roots.items()}
    resolved = []
    if members is not None:
        for member in members:
            dataset, pid = member['dataset_id'], member['patient_id']
            sid = member.get('sample_id') or ''
            if dataset not in inventories:
                raise ValueError('A cohort member belongs to a dataset outside this workspace.')
            patients, samples = inventories[dataset]
            if pid not in patients or (sid and pid not in samples.get(sid, set())):
                raise ValueError('A cohort member or its sample link is not present in its source dataset.')
            if id_type != 'patient' and not sid:
                raise ValueError('Sample cohorts require a source sample ID for every member.')
            resolved.append(dict(dataset_id=dataset, patient_id=pid, **({'sample_id': sid} if sid and id_type != 'patient' else {})))
    else:
        ids = patient_ids if id_type == 'patient' else sample_ids
        for value in dict.fromkeys(ids):
            candidates = []
            decoded = decode_identity(value)
            for dataset, (patients, samples) in inventories.items():
                if decoded and (decoded[0] != dataset or decoded[1] != ('patient' if id_type == 'patient' else 'sample')):
                    continue
                source_id = decoded[2] if decoded else value
                if id_type == 'patient' and source_id in patients:
                    candidates.append(dict(dataset_id=dataset, patient_id=source_id))
                elif id_type != 'patient':
                    candidates.extend(dict(dataset_id=dataset, patient_id=pid, sample_id=source_id)
                                      for pid in samples.get(source_id, set()))
            if len(candidates) != 1:
                raise ValueError('An ID is missing or ambiguous across datasets. Supply dataset-qualified cohort members.')
            resolved.extend(candidates)
    unique = {(m['dataset_id'], m['patient_id'], m.get('sample_id', '')): m for m in resolved}
    if not unique:
        raise ValueError('A saved cohort requires at least one member.')
    return [qualified_member(unique[k]) for k in sorted(unique)]
