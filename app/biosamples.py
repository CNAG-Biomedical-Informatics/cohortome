"""Optional Beacon v2 biosample records; never infer specimen identity."""
import csv
import json
from pathlib import Path


def read_biosamples(root, patient_ids=None, *, include_clarids=True):
    root = Path(root).resolve()
    manifest = root / 'manifest.json'
    if not manifest.is_file():
        return []
    try:
        document = json.loads(manifest.read_text(encoding='utf-8-sig'))
        config = document.get('biosamples')
        if config is None:
            if document.get('identifiers', {}).get('clarid_biosamples') is not None:
                raise ValueError
            return []
        relative = config['file']
        path = Path(relative)
        if (not isinstance(relative, str) or not relative or '\\' in relative
                or path.is_absolute() or '..' in path.parts
                or path.parts[0] == 'clinical'
                or not (root / path).resolve().is_relative_to(root)):
            raise ValueError
        records = json.loads((root / path).read_text(encoding='utf-8-sig'))
        if not isinstance(records, list):
            raise ValueError
        seen = set()
        for row in records:
            for key in ('id', 'individualId'):
                value = row[key]
                if not isinstance(value, str) or not value.strip() or value != value.strip():
                    raise ValueError
            if row['id'] in seen or (patient_ids is not None and row['individualId'] not in patient_ids):
                raise ValueError
            seen.add(row['id'])
            for key in ('sampleOriginType', 'sampleOriginDetail', 'biosampleStatus'):
                term = row.get(key)
                if term is not None and (not isinstance(term, dict)
                        or not all(isinstance(term.get(k), str) and term[k].strip() for k in ('id', 'label'))):
                    raise ValueError
        if include_clarids:
            _attach_clarids(root, document, records)
        return records
    except (OSError, UnicodeError, csv.Error, ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise ValueError('Biosample input is invalid: check its relative file path, unique IDs, patient links, ontology terms and optional ClarID table.') from None


def _attach_clarids(root, manifest, records):
    """Join prepared labels by source ID, never by ClarID or patient alone.

    Partial coverage is allowed. Shared human/stub labels are intentional.
    Decoded values are prepared upstream with the versioned codebook.
    """
    config = manifest.get('identifiers', {}).get('clarid_biosamples')
    if config is None:
        return
    relative = config['file']
    path = Path(relative)
    if (not relative or '\\' in relative or path.is_absolute() or '..' in path.parts
            or not (root / path).resolve().is_relative_to(root)
            or config.get('entity', 'biosample') != 'biosample'
            or not all(isinstance(config.get(k), str) and config[k].strip()
                       for k in ('codebook_version', 'tools_version'))):
        raise ValueError
    delimiter = config.get('delimiter', ',').replace('\\t', '\t')
    if delimiter not in (',', ';', '\t'):
        raise ValueError
    fields = ('project', 'species', 'tissue', 'sample_type', 'assay', 'condition', 'timepoint', 'duration')
    required = {'unique_id', 'individual_id', 'subject_id', 'clar_id', 'stub_id', *fields}
    by_id = {row['id']: row for row in records}
    seen, subject_numbers, number_owners = set(), {}, {}
    if manifest.get('identifiers', {}).get('clarid_subjects') is not None:
        from app.query_store import _read_subject_clarid_rows
        from app.bff import group_patients, ensure_data_dir
        # Use the same validated mapping as subject labels, including patients
        # without biosamples. Never allocate new subject numbers in the reader.
        patients = set(group_patients(ensure_data_dir(str(root))))
        for row in _read_subject_clarid_rows(root, patients):
            subject_numbers[row[0]] = row[1]
            number_owners[row[1]] = row[0]
    with (root / path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not required <= set(headers):
            raise ValueError
        for raw in reader:
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError
            row = {k: v.strip() for k, v in raw.items()}
            if any(not row[k] for k in required) or not row['subject_id'].isascii() or not row['subject_id'].isdigit():
                raise ValueError
            bid, pid, number = row['unique_id'], row['individual_id'], int(row['subject_id'])
            if (bid in seen or bid not in by_id or by_id[bid]['individualId'] != pid
                    or subject_numbers.get(pid, number) != number
                    or number_owners.get(number, pid) != pid):
                raise ValueError
            seen.add(bid)
            subject_numbers[pid], number_owners[number] = number, pid
            by_id[bid]['clarid'] = dict(
                entity='biosample', subject_id=number, human_id=row['clar_id'], stub_id=row['stub_id'],
                **{k: row.get(k, '') for k in (*fields, 'batch', 'replicate', 'condition_name')},
                **{k: config[k] for k in ('codebook_version', 'tools_version')})


def origin_key(record):
    return (record.get('sampleOriginType') or {}).get('id', '')
