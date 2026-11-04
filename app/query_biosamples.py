"""Patient queries based on recorded biosample origins, not inferred tissue."""
import re

from app.biosamples import read_biosamples, origin_key
from app.identities import identity_key
from app.query_store import _workspace_dataset_ids, _dataset_root_path


def parse_origin_question(question):
    text = question.strip().rstrip('?.').strip()
    if re.fullmatch(r'(?:what|which|list|show)(?: are)?(?: the| all)? (?:sample origins|biosample origins|tissues)(?: are)?(?: available| recorded)?(?: in (?:this |the )?workspace)?', text, re.I):
        return {'output': 'origins'}
    prefix = r'(how many|which|list|show|find)(?: all)? patients? (?:have|has|with|having) '
    for suffix in [r'(.+?) (?:samples|specimens|biosamples)',
                   r'(?:samples|specimens|biosamples) (?:from|of|with (?:sample )?origin) (.+)']:
        match = re.fullmatch(prefix + suffix, text, re.I)
        if match:
            return {'output': 'count' if match[1].lower() == 'how many' else 'patient_list',
                    'origin': match[2].strip().strip('\"\'')}
    return None


def origin_catalog(data_dir, patient_ids):
    """Intersect explicit biosample links with the authorized, scoped inventory."""
    allowed = set(patient_ids)
    dataset_ids = _workspace_dataset_ids(data_dir)
    roots = [(d, _dataset_root_path(d)) for d in dataset_ids] if dataset_ids else [('', data_dir)]
    origins = {}
    for dataset, root in roots:
        for record in read_biosamples(root, include_clarids=False):
            patient = identity_key(dataset, 'patient', record['individualId']) if len(dataset_ids) > 1 else record['individualId']
            key = origin_key(record)
            if patient not in allowed or not key:
                continue
            item = origins.setdefault(key, {'id': key, 'labels': set(), 'patients': set()})
            item['labels'].add(record['sampleOriginType']['label'])
            item['patients'].add(patient)
    return sorted(origins.values(), key=lambda item: (sorted(item['labels'])[0].casefold(), item['id']))


def resolve_origin(catalog, term):
    normalized = term.strip().casefold()
    return [item for item in catalog if normalized == item['id'].casefold()
            or normalized in {label.casefold() for label in item['labels']}]


def public_origins(catalog):
    return [{'id': item['id'], 'label': ' / '.join(sorted(item['labels'])),
             'patient_count': len(item['patients'])} for item in catalog]


def origin_problem(query, catalog, matches):
    if not catalog:
        reply = 'No sample-origin metadata are recorded for the current patient selection. This does not mean those patients have no samples.'
    elif not matches:
        reply = 'That sample origin is not recorded under this label or ontology ID. Ask “Which sample origins are available?” and use one of the recorded terms.'
    elif len(matches) > 1:
        reply = 'That label refers to more than one sample-origin term. Use an ontology ID: ' + ', '.join(item['id'] for item in matches) + '.'
    else:
        return None
    return {'query': query, 'intent': 'sample_origin_clarification', 'reply': reply,
            'data': {'execution': 'deterministic', 'follow_up_suggestions': ['Which sample origins are available?']}}


def answer_origin_question(data_dir, query, parsed, inventory):
    catalog = origin_catalog(data_dir, [row['patient_id'] for row in inventory])
    if parsed['output'] == 'origins':
        if not catalog:
            return origin_problem(query, catalog, [])
        rows = public_origins(catalog)
        return {'query': query, 'intent': 'sample_origin_inventory',
                'reply': 'Recorded sample origins:\n' + '\n'.join(
                    f"- {r['label']} ({r['id']}): {r['patient_count']} patients" for r in rows),
                'data': {'sample_origins': rows, 'execution': 'deterministic'}}
    matches = resolve_origin(catalog, parsed['origin'])
    problem = origin_problem(query, catalog, matches)
    if problem:
        return problem
    matched = matches[0]
    # Clinical record IDs are not a specimen selection. Including them would
    # make Query's existing handoff treat this as a sample-level result.
    patients = [{k: v for k, v in row.items() if k != 'original_record_ids'}
                for row in inventory if row['patient_id'] in matched['patients']]
    label = ' / '.join(sorted(matched['labels']))
    return {'query': query, 'intent': 'sample_origin_cohort',
            'reply': f"{len(patients)} {'patient has' if len(patients) == 1 else 'patients have'} samples with recorded origin {label} ({matched['id']}). This selects patients, not individual samples.",
            'data': {'patients': patients, 'patient_ids': [r['patient_id'] for r in patients],
                     'patient_count': len(patients), 'id_type': 'patient', 'execution': 'deterministic',
                     'sample_origin': {'id': matched['id'], 'label': label},
                     'follow_up_suggestions': ['Which sample origins are available?']}}
