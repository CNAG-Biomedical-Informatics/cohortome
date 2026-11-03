"""Permission-checked browsing of compact prepared variant panels."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.patient_overview import sources
from app.variants import read_variant_panel
from app.identities import identity_key

router = APIRouter(prefix='/variants', tags=['variants'])


def panel_for(request, workspace, dataset_id):
    available = {key: (root, label) for key, root, label in sources(request, workspace)}
    if dataset_id not in available:
        raise HTTPException(403, 'Select an authorized dataset in the active workspace.')
    root, label = available[dataset_id]
    try:
        panel = read_variant_panel(root)
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
def panels(request: Request, workspace: str):
    result = []
    available = sources(request, workspace)
    for key, root, label in available:
        try:
            panel = read_variant_panel(root)
        except ValueError:
            raise HTTPException(409, 'Variant input is invalid. Check the dataset package.') from None
        if panel:
            result.append(dict(dataset_id=key, label=label, variants=len(panel['variants']),
                               samples=len(panel['samples']), provenance=panel['provenance'],
                               patient_ids=sorted({identity_key(key, 'patient', s['patient_id']) if len(available) > 1 else s['patient_id'] for s in panel['samples']}),
                               sample_ids=[identity_key(key, 'sample', s['sample_id']) if len(available) > 1 else s['sample_id'] for s in panel['samples']]))
    return result


@router.get('/search')
def search(request: Request, workspace: str, dataset_id: str,
           q: str = Query('', max_length=200), chromosome: str = Query('', max_length=100),
           classification: str = Query('', max_length=500), offset: int = Query(0, ge=0),
           sort_by: Literal['position', 'variant_id', 'gene', 'classification', 'carriers'] = 'position',
           direction: Literal['asc', 'desc'] = 'asc'):
    panel = panel_for(request, workspace, dataset_id)
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
def detail(request: Request, workspace: str, dataset_id: str, variant_id: str = Query(max_length=1000)):
    panel = panel_for(request, workspace, dataset_id)
    row = next((r for r in panel['variants'] if r['variant_id'] == variant_id), None)
    if row is None:
        raise HTTPException(404, 'Variant not found in this dataset.')
    return dict(annotation=annotation(row), provenance=panel['provenance'],
                counts=panel['variant_counts'][variant_id],
                members=[dict(dataset_id=dataset_id, patient_id=pid)
                         for pid in sorted(panel['carriers'][variant_id])])
