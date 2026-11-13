"""Permission-checked browsing of compact prepared variant panels."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.patient_overview import sources
from app.variants import read_variant_panel
from app.identities import identity_key

router = APIRouter(prefix='/variants', tags=['variants'])


class ScopeMember(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=200)
    patient_id: str = Field(min_length=1, max_length=1000)


class VariantScope(BaseModel):
    members: list[ScopeMember] = Field(max_length=100000)


def selected_ids(selection, dataset_id, available):
    if selection is None:
        return None
    if any(member.dataset_id not in available for member in selection.members):
        raise HTTPException(403, 'The patient scope contains an unavailable dataset.')
    return {member.patient_id for member in selection.members if member.dataset_id == dataset_id}


def panel_for(request, workspace, dataset_id, selection=None):
    available = {key: (root, label) for key, root, label in sources(request, workspace)}
    if dataset_id not in available:
        raise HTTPException(403, 'Select an authorized dataset in the active workspace.')
    root, label = available[dataset_id]
    try:
        panel = read_variant_panel(root) if selection is None else read_variant_panel(
            root, selected_patient_ids=selected_ids(selection, dataset_id, available))
    except ValueError:
        raise HTTPException(409, 'Variant input is invalid. Check the dataset package.') from None
    if not panel:
        raise HTTPException(404, 'No prepared variant panel in this dataset.')
    return panel


def annotation(row):
    genes = {part.split('|')[3] for part in row.get('snpeff_ann', '').split(',') if len(part.split('|')) > 3}
    return dict(row, gene=row.get('gene') or ', '.join(sorted(genes - {''})),
                classification=row.get('classification') or row.get('CLINVAR_CLNSIG', ''))


def chromosome_key(value):
    value = value.removeprefix('chr')
    return (0, int(value)) if value.isdigit() else (1, value)


@router.get('/panels')
@router.post('/panels')
def panels(request: Request, workspace: str, selection: VariantScope | None = None):
    result = []
    available = sources(request, workspace)
    for key, root, label in available:
        try:
            panel = read_variant_panel(root) if selection is None else read_variant_panel(
                root, selected_patient_ids=selected_ids(selection, key, {item[0] for item in available}))
        except ValueError:
            raise HTTPException(409, 'Variant input is invalid. Check the dataset package.') from None
        if panel and (selection is None or panel['samples']):
            result.append(dict(dataset_id=key, label=label, variants=len(panel['variants']),
                               samples=len(panel['samples']), provenance=panel['provenance'],
                               patient_ids=sorted({identity_key(key, 'patient', s['patient_id']) if len(available) > 1 else s['patient_id'] for s in panel['samples']}),
                               sample_ids=[identity_key(key, 'sample', s['sample_id']) if len(available) > 1 else s['sample_id'] for s in panel['samples']]))
    return result


@router.get('/search')
@router.post('/search')
def search(request: Request, workspace: str, dataset_id: str,
           q: str = Query('', max_length=200), chromosome: str = Query('', max_length=100),
           classification: str = Query('', max_length=500), offset: int = Query(0, ge=0),
           sort_by: Literal['position', 'variant_id', 'gene', 'classification', 'carriers'] = 'position',
           direction: Literal['asc', 'desc'] = 'asc', selection: VariantScope | None = None):
    panel = panel_for(request, workspace, dataset_id, selection)
    rows = [annotation(r) for r in panel['variants']]
    chromosomes = sorted({r['chromosome'] for r in rows}, key=chromosome_key)
    classifications = sorted({r['classification'] for r in rows if r['classification']})
    matched = []
    for row in rows:
        if chromosome and row['chromosome'] != chromosome:
            continue
        if classification and row['classification'] != classification:
            continue
        if q.strip().casefold() not in ' '.join(row.get(k, '') for k in
                ('variant_id', 'vcf_id', 'gene', 'chromosome', 'position')).casefold():
            continue
        matched.append(dict(variant_id=row['variant_id'], chromosome=row['chromosome'],
            position=int(row['position']), ref=row['ref'], alt=row['alt'], gene=row['gene'],
            classification=row['classification'], carriers=len(panel['carriers'][row['variant_id']])))
    matched.sort(key=lambda r: ((chromosome_key(r['chromosome']), r['position']) if sort_by == 'position'
                               else r[sort_by], r['variant_id']), reverse=direction == 'desc')
    return dict(rows=matched[offset:offset + 25], total=len(matched),
                chromosomes=chromosomes, classifications=classifications)


@router.get('/detail')
@router.post('/detail')
def detail(request: Request, workspace: str, dataset_id: str, variant_id: str = Query(max_length=1000), selection: VariantScope | None = None):
    panel = panel_for(request, workspace, dataset_id, selection)
    row = next((r for r in panel['variants'] if r['variant_id'] == variant_id), None)
    if row is None:
        raise HTTPException(404, 'Variant not found in this dataset.')
    return dict(annotation=annotation(row), provenance=panel['provenance'],
                counts=panel['variant_counts'][variant_id],
                members=[dict(dataset_id=dataset_id, patient_id=pid)
                         for pid in sorted(panel['carriers'][variant_id])])
