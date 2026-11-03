"""Optional Beacon v2 biosample records; never infer specimen identity."""
import json
from pathlib import Path


def read_biosamples(root, patient_ids=None):
    root = Path(root).resolve()
    manifest = root / 'manifest.json'
    if not manifest.is_file():
        return []
    try:
        config = json.loads(manifest.read_text(encoding='utf-8-sig')).get('biosamples')
        if config is None:
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
        return records
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise ValueError('Biosample input is invalid: check its relative file path, unique IDs, patient links and ontology terms.') from None


def origin_key(record):
    return (record.get('sampleOriginType') or {}).get('id', '')
