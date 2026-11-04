"""Dataset-scoped patient lookup and sample inventory, without matrix scans."""
import csv
import json
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth import require_authenticated
from app.bff import relative_study_days, get_patient_context
from app.biosamples import read_biosamples, origin_key
from app.variants import read_variant_panel
from app.datasets import get_dataset
from app.query_store import (
    _connect, _relation_exists, _assay_manifest_items_for_root,
    _manifest_assay_sample_patient_links, _detect_matrix_delimiter,
    ensure_query_store, QueryStoreNotReadyError,
    patient_clarid,
)
from app.routes import _require_detailed_assay_access, _resolve_route_dataset_dir

router = APIRouter(prefix='/patient-overview', tags=['patients'])


def biosample_records(root, *, include_clarids=True):
    try:
        return read_biosamples(root, include_clarids=include_clarids)
    except ValueError:
        raise HTTPException(409, 'Biosample metadata are invalid. Check the dataset package before filtering by sample origin.') from None


def sources(request, workspace):
    require_authenticated(request)
    ids = _require_detailed_assay_access(request, workspace)
    return [(identifier, _resolve_route_dataset_dir(request, identifier, ''),
             str((get_dataset(identifier) or {}).get('name') or identifier)) for identifier in ids]


def lookup(root, term, limit=12, exact=False, after='', sort_by='patient_id', descending=False, disease='', include_total=False, sample_origin='', ids_only=False):
    ensure_query_store(root)
    con = _connect(root)
    try:
        has_clarids = _relation_exists(con, 'patient_clarids')
        join = 'LEFT JOIN patient_clarids c ON c.patient_id = p.patient_id' if has_clarids else ''
        human = "coalesce(c.human_id, '')" if has_clarids else "''"
        predicate = 'p.patient_id = ?' if exact else f'(contains(lower(p.patient_id), lower(?)) OR contains(lower({human}), lower(?)))'
        params = [term] if exact else [term, term]
        if sample_origin:
            ids = sorted({r['individualId'] for r in biosample_records(root, include_clarids=False) if origin_key(r) == sample_origin})
            predicate += ' AND p.patient_id IN (SELECT unnest(?))'
            params.append(ids)
        if disease:
            if not _relation_exists(con, 'patient_diseases'):
                return []
            labels = [disease] if isinstance(disease, str) else disease
            predicate += f" AND EXISTS (SELECT 1 FROM patient_diseases d WHERE d.patient_id = p.patient_id AND lower(d.disease) IN ({','.join('?' for _ in labels)}))"
            params.extend(label.lower() for label in labels)
        if after:
            predicate += ' AND p.patient_id > ?'
            params.append(after)
        if ids_only:
            rows = con.execute(f'''SELECT DISTINCT p.patient_id FROM patients p {join}
                WHERE {predicate} ORDER BY p.patient_id LIMIT ?''', params + [limit]).fetchall()
            return [dict(patient_id=row[0]) for row in rows]
        diagnoses = ("(SELECT string_agg(DISTINCT d.disease, ', ' ORDER BY d.disease) "
                     "FROM patient_diseases d WHERE d.patient_id = p.patient_id)"
                     if _relation_exists(con, 'patient_diseases') else "''")
        sort_expression = {'patient_id': 'p.patient_id', 'dataset_label': "''",
                           'clarid': human, 'diagnosis': diagnoses}[sort_by]
        direction = 'DESC' if descending else 'ASC'
        total_column = ', count(*) OVER()' if include_total else ''
        rows = con.execute(f'''SELECT p.patient_id, p.sex, p.visit_count, {human}, {diagnoses}{total_column}
            FROM patients p {join} WHERE {predicate}
            ORDER BY lower(coalesce({sort_expression}, '')) {direction}, p.patient_id {direction}
            LIMIT ?''', params + [limit]).fetchall()
        return [dict(patient_id=r[0], sex=r[1], clinical_record_count=r[2], clarid=r[3],
                     diagnosis=r[4] or '', **({'_total': r[5]} if include_total else {})) for r in rows]
    finally:
        con.close()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Unavailable assay input')
    return path


def sample_inventory(root, patient_id=None, include_imaging=False, include_clarids=True):
    root = Path(root)
    rows, warnings = [], []
    biosamples = {r['id']: r for r in biosample_records(root, include_clarids=include_clarids)}
    for item in _assay_manifest_items_for_root(root):
        assay_id = str(item.get('assay_id') or '')
        label = str(item.get('label') or assay_id or 'Assay')
        if str(item.get('modality', '')).lower() == 'imaging' and not include_imaging:
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
            selected = [s for s in samples if links['links'].get(s)
                        and (patient_id is None or links['links'][s] == patient_id)]
            selected_set = set(selected)
            metadata = {}
            if selected and item.get('sample_metadata_file'):
                with inside(root, item['sample_metadata_file']).open(encoding='utf-8-sig', newline='') as handle:
                    first = handle.readline()
                    delimiter = '\t' if '\t' in first else _detect_matrix_delimiter(first)
                    handle.seek(0)
                    for row in csv.DictReader(handle, delimiter=delimiter):
                        sid = str(row.get('sample_id') or '').strip()
                        if sid in selected_set:
                            if sid in metadata:
                                raise ValueError('Ambiguous metadata')
                            metadata[sid] = row
            for sid in selected:
                meta = metadata.get(sid, {})
                specimen = biosamples.get(meta.get('biosample_id'), {})
                if specimen and specimen['individualId'] != links['links'][sid]:
                    raise ValueError('Conflicting biosample patient linkage')
                rows.append(dict(patient_id=links['links'][sid], sample_id=sid, assay_id=assay_id, assay=label,
                    modality=item.get('modality') or 'assay', data_type=item.get('data_type') or 'Not recorded',
                    linkage=links['linkage_source'], visit=meta.get('visit_id') or meta.get('timepoint') or '',
                    days_from_baseline=relative_study_days(meta),
                    collection_date=meta.get('collection_date') or '', material=meta.get('material') or meta.get('specimen_type') or (specimen.get('sampleOriginType') or {}).get('label', ''),
                    biosample_id=specimen.get('id', ''),
                    biosample_clarid=specimen.get('clarid'),
                    sample_clarid=meta.get('clarid') or ''))
        except (OSError, ValueError, UnicodeError, csv.Error, StopIteration):
            warnings.append(f'{label}: sample inventory unavailable; not included in counts.')
    try:
        panel = read_variant_panel(root)
        for meta in (panel or {}).get('samples', []):
            if patient_id is not None and meta['patient_id'] != patient_id:
                continue
            specimen = biosamples.get(meta.get('biosample_id'), {})
            rows.append(dict(patient_id=meta['patient_id'], sample_id=meta['sample_id'],
                assay_id='variant_panel', assay='DNA variant panel',
                modality='dna_sequencing' if panel['provenance'].get('technology') == 'dna_sequencing' else 'genotyping_array' if panel['provenance'].get('technology') == 'genotyping_array' else 'genotyping',
                data_type='annotated_genotypes', linkage='sample_metadata_file',
                visit=meta.get('visit_id', ''), days_from_baseline=relative_study_days(meta),
                collection_date=meta.get('collection_date', ''),
                material=meta.get('material') or (specimen.get('sampleOriginType') or {}).get('label', ''),
                biosample_id=specimen.get('id', ''), biosample_clarid=specimen.get('clarid'),
                sample_clarid=meta.get('clarid', '')))
    except ValueError:
        warnings.append('DNA variant panel: invalid input; not included in counts.')
    rows.sort(key=lambda r: (r['sample_id'], r['assay']))
    return rows, warnings


@router.get('/timeline')
def timeline(request: Request, workspace: str):
    """Workspace availability from clinical records and declared assay links.

    Read each assay header/metadata once, never matrix values or once per patient.
    Imaging here means linked derived measurements, not remote DICOM studies.
    """
    from app.bff import dashboard_summary
    patients, warnings = [], []
    for identifier, root, label in sources(request, workspace):
        ensure_query_store(root)
        summary = dashboard_summary(root)
        by_id = {row['patient_id']: dict(row, samples=[]) for row in summary['timelines']}
        inventory, issues = sample_inventory(root, include_imaging=True)
        warnings.extend(f'{label}: {issue}' for issue in issues)
        for sample in inventory:
            pid = sample['patient_id']
            by_id.setdefault(pid, dict(patient_id=pid, events=[], visit_count=0, samples=[]))['samples'].append(sample)
        for pid, row in by_id.items():
            patients.append(dict(row, source_patient_id=pid, dataset_id=identifier,
                                 dataset_label=label, patient_id=json.dumps([identifier, pid], separators=(',', ':'))))
    return dict(timelines=patients, warnings=warnings)


@router.get('/sample-origins')
def sample_origins(request: Request, workspace: str):
    terms = {}
    for identifier, root, label in sources(request, workspace):
        for row in biosample_records(root, include_clarids=False):
            key = origin_key(row)
            if key:
                item = terms.setdefault(key, dict(id=key, label=row['sampleOriginType']['label'], patients=set()))
                item['patients'].add((identifier, row['individualId']))
    return [dict(id=r['id'], label=r['label'], patient_count=len(r['patients']))
            for r in sorted(terms.values(), key=lambda r: (r['label'].casefold(), r['id']))]


def disease_filter(disease):
    if disease and (len(disease) > 100 or any(len(label) > 1000 for label in disease)):
        raise HTTPException(422, 'Too many or overly long disease filters.')
    return [label for label in (disease or []) if label]


@router.get('/selection')
def select_patients(request: Request, workspace: str, q: str = Query('', max_length=150),
                    disease: list[str] | None = Query(None), sample_origin: str = Query('', max_length=256)):
    """Collect a filtered patient selection once, without browsing every page."""
    disease = disease_filter(disease)
    members = []
    limit = 100_000
    try:
        for identifier, root, _ in sources(request, workspace):
            rows = lookup(root, q.strip(), limit - len(members) + 1, disease=disease,
                          sample_origin=sample_origin, ids_only=True)
            members.extend(dict(dataset_id=identifier, patient_id=r['patient_id']) for r in rows)
            if len(members) > limit:
                raise HTTPException(422, 'Select at most 100,000 patients. Narrow the filters and try again.')
    except (FileNotFoundError, QueryStoreNotReadyError):
        raise HTTPException(409, 'Patient selection is unavailable until the dataset stores are ready.') from None
    return {'members': members, 'patient_count': len(members), 'id_type': 'patient'}


@router.get('/search')
def search(request: Request, workspace: str, q: str = Query('', max_length=150),
           dataset_index: int = Query(0, ge=0), after: str = Query('', max_length=1000),
           sort_by: Literal['patient_id', 'dataset_label', 'diagnosis', 'clarid'] | None = None,
           direction: Literal['asc', 'desc'] = 'asc', offset: int = Query(0, ge=0),
           disease: list[str] | None = Query(None), sample_origin: str = Query('', max_length=256)):
    disease = disease_filter(disease)
    available = sources(request, workspace)
    matches = []
    try:
        if sort_by:
            total = 0
            for identifier, root, label in available:
                rows = lookup(root, q.strip(), offset + 21, sort_by=sort_by,
                              descending=direction == 'desc', disease=disease, include_total=True, sample_origin=sample_origin)
                total += rows[0]['_total'] if rows else 0
                for row in rows:
                    row.pop('_total', None)
                    matches.append(dict(row, dataset_id=identifier, dataset_label=label))
            matches.sort(key=lambda row: (str(row.get(sort_by) or '').lower(),
                                          row['patient_id'], row['dataset_id']),
                         reverse=direction == 'desc')
            return {'matches': matches[offset:offset + 20], 'total': total,
                    'next': {'offset': offset + 20} if len(matches) > offset + 20 else None}
        for index, (identifier, root, label) in enumerate(available):
            if index < dataset_index:
                continue
            remaining = 21 - len(matches)
            if not remaining:
                break
            matches.extend(dict(row, dataset_id=identifier, dataset_label=label, dataset_index=index)
                           for row in lookup(root, q.strip(), remaining,
                                             after=after if index == dataset_index else '',
                                             **({'sample_origin': sample_origin} if sample_origin else {}),
                                             **({'disease': disease} if disease else {})))
    except (FileNotFoundError, QueryStoreNotReadyError):
        raise HTTPException(409, 'Patient search is unavailable until the dataset stores are ready.') from None
    cursor = ({'dataset_index': matches[19]['dataset_index'], 'after': matches[19]['patient_id']}
              if len(matches) > 20 else None)
    return {'matches': matches[:20], 'next': cursor}


@router.get('/coverage')
def coverage(request: Request, workspace: str):
    """Patient-level availability; never infer specimen or visit equivalence."""
    from app.dicom import dicom_studies
    patients, warnings = [], []
    for identifier, root, label in sources(request, workspace):
        try:
            ensure_query_store(root)
            con = _connect(root)
            try:
                clinical_ids = {row[0] for row in con.execute('SELECT patient_id FROM patients').fetchall()}
                diseases = {}
                if _relation_exists(con, 'patient_diseases'):
                    for pid, disease in con.execute('SELECT DISTINCT patient_id, disease FROM patient_diseases ORDER BY disease').fetchall():
                        if disease:
                            diseases.setdefault(pid, []).append(disease)
            finally:
                con.close()
        except (FileNotFoundError, QueryStoreNotReadyError):
            raise HTTPException(409, 'Coverage is unavailable until the dataset stores are ready.') from None
        available = {pid: {'clinical'} for pid in clinical_ids}
        inventory, issues = sample_inventory(root, include_imaging=True, include_clarids=False)
        warnings.extend(f'{label}: {issue}' for issue in issues)
        for sample in inventory:
            available.setdefault(sample['patient_id'], set()).add(sample['modality'])
        for study in dicom_studies(root):
            pid = str(study.get('patient_id') or '').strip()
            if pid:
                available.setdefault(pid, set()).add('dicom')
        for pid, modalities in sorted(available.items()):
            patients.append(dict(patient_id=pid, dataset_id=identifier, dataset_label=label,
                                 modalities=sorted(modalities), diseases=diseases.get(pid, []), has_clinical=pid in clinical_ids))
    return dict(patients=patients, warnings=warnings)


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
                samples=rows, warnings=warnings,
                biosamples=[r for r in biosample_records(root) if r['individualId'] == patient_id])


@router.get('/clinical')
def clinical_records(request: Request, workspace: str, dataset_id: str,
                     patient_id: str = Query(max_length=512), offset: int = Query(0, ge=0),
                     visit_id: str = Query('', max_length=1000)):
    available = {identifier: root for identifier, root, _ in sources(request, workspace)}
    if dataset_id not in available:
        raise HTTPException(403, 'Select an authorized dataset in the active workspace.')
    root = available[dataset_id]
    try:
        ensure_query_store(root)
        patient = get_patient_context(root, patient_id)
    except (FileNotFoundError, QueryStoreNotReadyError):
        raise HTTPException(409, 'Patient records are unavailable until the dataset store is ready.') from None
    if patient is None:
        raise HTTPException(404, 'Patient not found in this dataset.')
    visits = [v for v in patient.visits if not visit_id or v.visit_id == visit_id]
    # Sort before pagination: V2 belongs before V10, even across page boundaries.
    visits.sort(key=lambda v: (
        not bool(v.visit_id),
        [(1, int(part)) if part.isdigit() else (0, part.casefold())
         for part in re.split(r'(\d+)', v.visit_id or '')],
        v.provenance.raw_bff.get('id', ''),
    ))
    records = [
        dict(visit_id=visit.visit_id, event_date=visit.event_date,
             days_from_baseline=relative_study_days(visit.provenance.raw_bff.get('info') or {}),
             record=visit.provenance.raw_bff)
        for visit in visits[offset:offset + 20]
    ]
    return dict(records=records, total=len(visits), clarid=patient_clarid(root, patient_id),
                next_offset=offset + 20 if offset + 20 < len(visits) else None)
