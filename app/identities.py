"""Stable internal identities; source identifiers are never rewritten."""
import base64
import json


def identity_key(dataset_id: str, kind: str, source_id: str) -> str:
    if not dataset_id or not source_id or kind not in {'patient', 'sample'}:
        raise ValueError('An identity requires a dataset, entity kind and source ID.')
    payload = json.dumps([dataset_id, kind, source_id], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return 'cohortome-v1-' + base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')


def qualified_member(member):
    dataset, patient = member['dataset_id'], member['patient_id']
    result = dict(dataset_id=dataset, patient_id=patient,
                  patient_key=identity_key(dataset, 'patient', patient))
    if member.get('sample_id'):
        result.update(sample_id=member['sample_id'], sample_key=identity_key(dataset, 'sample', member['sample_id']))
    return result


def decode_identity(value):
    if not isinstance(value, str) or not value.startswith('cohortome-v1-'):
        return None
    try:
        token = value[len('cohortome-v1-'):]
        dataset, kind, source = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))
        if kind not in {'patient', 'sample'} or not all(isinstance(v, str) and v for v in [dataset, source]):
            return None
        if identity_key(dataset, kind, source) != value:
            return None
        return dataset, kind, source
    except (ValueError, TypeError, UnicodeError):
        return None
