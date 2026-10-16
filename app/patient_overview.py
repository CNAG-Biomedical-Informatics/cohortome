"""Dataset-scoped patient lookup and sample inventory, without matrix scans."""
import csv
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth import require_authenticated
from app.datasets import get_dataset
from app.query_store import (
    _connect, _relation_exists, _assay_manifest_items_for_root,
    _manifest_assay_sample_patient_links, _detect_matrix_delimiter,
    ensure_query_store, QueryStoreNotReadyError,
)
from app.routes import _require_detailed_assay_access, _resolve_route_dataset_dir

router = APIRouter(prefix='/patient-overview', tags=['patients'])


def sources(request, workspace):
    require_authenticated(request)
    ids = _require_detailed_assay_access(request, workspace)
    return [(identifier, _resolve_route_dataset_dir(request, identifier, ''),
             str((get_dataset(identifier) or {}).get('name') or identifier)) for identifier in ids]


def lookup(root, term, limit=12, exact=False):
    ensure_query_store(root)
    con = _connect(root)
    try:
        has_clarids = _relation_exists(con, 'patient_clarids')
        join = 'LEFT JOIN patient_clarids c ON c.patient_id = p.patient_id' if has_clarids else ''
        human = "coalesce(c.human_id, '')" if has_clarids else "''"
        predicate = 'p.patient_id = ?' if exact else f'(contains(lower(p.patient_id), lower(?)) OR contains(lower({human}), lower(?)))'
        params = [term] if exact else [term, term]
        rows = con.execute(f'''SELECT p.patient_id, p.sex, p.visit_count, {human}
            FROM patients p {join} WHERE {predicate} ORDER BY p.patient_id LIMIT ?''', params + [limit]).fetchall()
        return [dict(patient_id=r[0], sex=r[1], clinical_record_count=r[2], clarid=r[3]) for r in rows]
    finally:
        con.close()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Unavailable assay input')
    return path


def sample_inventory(root, patient_id):
    root = Path(root)
    rows, warnings = [], []
    for item in _assay_manifest_items_for_root(root):
        assay_id = str(item.get('assay_id') or '')
        label = str(item.get('label') or assay_id or 'Assay')
        if str(item.get('modality', '')).lower() == 'imaging':
            continue  # Imaging studies are not biosamples.
        declared = item.get('sample_metadata_file') or item.get('patient_linkage') == 'exact_sample_id' or item.get('patient_id_column') == 'derived_from_sample_id_prefix'
        if not declared:
            warnings.append(f'{label}: no declared patient linkage; not included.')
            continue
        try:
            path = inside(root, str(item.get('file') or ''))
            with path.open(encoding='utf-8-sig', newline='') as handle:
                first = handle.readline()
                delimiter = _detect_matrix_delimiter(first)
                samples = next(csv.reader([first], delimiter=delimiter))[1:]
                samples = [s.strip() for s in samples if s.strip()]
            links = _manifest_assay_sample_patient_links(root, item, samples)
            if links.get('unlinked_sample_ids'):
                warnings.append(f"{label}: {len(links['unlinked_sample_ids'])} sample identifiers have no patient link and cannot be assigned here.")
            selected = [s for s in samples if links['links'].get(s) == patient_id]
            metadata = {}
            if selected and item.get('sample_metadata_file'):
                with inside(root, item['sample_metadata_file']).open(encoding='utf-8-sig', newline='') as handle:
                    first = handle.readline()
                    delimiter = '\t' if '\t' in first else _detect_matrix_delimiter(first)
                    handle.seek(0)
                    for row in csv.DictReader(handle, delimiter=delimiter):
                        sid = str(row.get('sample_id') or '').strip()
                        if sid in selected:
                            if sid in metadata:
                                raise ValueError('Ambiguous metadata')
                            metadata[sid] = row
            for sid in selected:
                meta = metadata.get(sid, {})
                rows.append(dict(sample_id=sid, assay_id=assay_id, assay=label,
                    modality=item.get('modality') or 'assay', data_type=item.get('data_type') or 'Not recorded',
                    linkage=links['linkage_source'], visit=meta.get('visit_id') or '',
                    collection_date=meta.get('collection_date') or '', material=meta.get('material') or '',
                    sample_clarid=meta.get('clarid') or ''))
        except (OSError, ValueError, UnicodeError, csv.Error, StopIteration):
            warnings.append(f'{label}: sample inventory unavailable; not included in counts.')
    rows.sort(key=lambda r: (r['sample_id'], r['assay']))
    return rows, warnings


@router.get('/search')
def search(request: Request, workspace: str, q: str = Query('', max_length=150)):
    available = sources(request, workspace)
    if not q.strip():
        return {'matches': []}
    matches = []
    try:
        for identifier, root, label in available:
            remaining = 12 - len(matches)
            if not remaining:
                break
            matches.extend(dict(row, dataset_id=identifier, dataset_label=label)
                           for row in lookup(root, q.strip(), remaining))
    except (FileNotFoundError, QueryStoreNotReadyError):
        raise HTTPException(409, 'Patient search is unavailable until the dataset stores are ready.') from None
    return {'matches': matches}


@router.get('/detail')
def detail(request: Request, workspace: str, dataset_id: str, patient_id: str = Query(max_length=512)):
    available = {identifier: (root, label) for identifier, root, label in sources(request, workspace)}
    if dataset_id not in available:
        raise HTTPException(403, 'Select an authorized dataset in the active workspace.')
    root, label = available[dataset_id]
    try:
        patients = lookup(root, patient_id, 1, exact=True)
        if not patients:
            raise HTTPException(404, 'Patient not found in this dataset.')
        rows, warnings = sample_inventory(root, patient_id)
    except (FileNotFoundError, QueryStoreNotReadyError):
        raise HTTPException(409, 'Patient data are unavailable until the dataset store is ready.') from None
    return dict(patient=patients[0], dataset_id=dataset_id, dataset_label=label,
                samples=rows, warnings=warnings)
