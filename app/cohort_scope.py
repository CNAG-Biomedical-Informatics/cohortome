"""Explicit application of a combined patient filter draft; no persistent cohort."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app import cohort_filters, patient_overview
from app.bff import dashboard_summary
from app.clinical_characteristics import characteristics
from app.cohort_members import resolve_members
from app.datasets import clinical_representation, dataset_scope_id, resolve_dataset_dir
from app.identities import execution_ids, qualified_member
from app.query_store import QueryStoreNotReadyError, ensure_query_store
from app.user_state import request_user_id

router = APIRouter(tags=['cohorts'])


class Member(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=200)
    patient_id: str = Field(min_length=1, max_length=1000)


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace: str = Field(min_length=1, max_length=2000)
    q: str = Field(default='', max_length=150)
    diseases: list[str] = Field(default_factory=list, max_length=100)
    sample_origin: str = Field(default='', max_length=256)
    clinical_filters: list[cohort_filters.FilterClause] = Field(default_factory=list, max_length=20)
    fingerprint: str = Field(default='', max_length=64)
    modalities: list[str] = Field(default_factory=list, max_length=40)
    exact: bool = False
    cohort_id: str = Field(default='', max_length=200)
    base_members: list[Member] | None = Field(default=None, max_length=100_000)
    source_label: str = Field(default='', max_length=2000)


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace: str = Field(min_length=1, max_length=2000)
    members: list[Member] | None = Field(default=None, max_length=100_000)
    patient_ids: list[str] | None = Field(default=None, max_length=100_000)
    result_handle: str = Field(default='', max_length=96, pattern=r'^(?:|qr_[A-Za-z0-9_-]+)$')
    cohort_id: str = Field(default='', max_length=200)
    label: str = Field(default='Selected patients', max_length=2000)


def _keys(members):
    return {(m['dataset_id'], m['patient_id']) for m in members}


def _modality(value):
    """Match the coverage selector's grouping, keeping images and features distinct."""
    value = str(value).strip().lower()
    if value in {'dicom', 'imaging'}:
        return value
    for prefix, group in [('olink', 'proteomics'), ('proteomics', 'proteomics'),
                          ('immune_cell', 'flow_cytometry'), ('flow_cytometry', 'flow_cytometry'),
                          ('variant', 'genotyping')]:
        if value.startswith(prefix):
            return group
    for group in ['clinical', 'transcriptomics', 'methylation', 'serology', 'dna_sequencing', 'genotyping_array', 'genotyping']:
        if value == group or value.startswith(group + '_'):
            return group
    return value


def _saved_members(request, cohort_id, roots):
    from app.cohorts import list_saved_cohorts
    cohort = next((c for c in list_saved_cohorts(user_id=request_user_id(request)) if c['id'] == cohort_id), None)
    if not cohort or not set(cohort.get('dataset_ids') or []).issubset(roots):
        raise HTTPException(409, 'Load this cohort’s datasets before applying it to scope.')
    return cohort['members']


def _resolved(roots, members):
    # Empty is an explicit, valid scope. It must never become all patients.
    return resolve_members(roots, members=members, id_type='patient') if members else []


def _response(request, workspace, available, members, label, fingerprint):
    from app.routes import _sanitize_response_paths
    from app.scoped_dashboard import scoped_assay_inventory
    roots = {key: root for key, root, _ in available}
    root = resolve_dataset_dir(request, dataset_scope_id(list(roots)))
    ensure_query_store(root)
    ids = None if members is None else execution_ids([m['patient_key'] for m in members], list(roots))
    summary = dashboard_summary(root, patient_ids=ids)
    summary['selection_count'] = len(members) if members is not None else summary['totals']['patients']
    summary['clinical_representation'] = clinical_representation(root)
    summary['totals']['clinical_records'] = summary['totals']['visits']
    summary['characteristics'] = characteristics(available, members)
    selection = None if members is None else dict(selection_active=True, id_type='patient',
        dataset_id=workspace, dataset_ids=list(roots), members=members,
        patient_ids=[m['patient_key'] for m in members], patient_count=len(members),
        sample_ids=[], sample_count=0, source={'kind':'cohort-builder', 'prompt':label})
    assays = scoped_assay_inventory(roots, members) if members is not None else None
    if fingerprint != cohort_filters._fingerprint(available, request_user_id(request)):
        raise HTTPException(409, 'Dataset contents changed. Reload the workspace before applying filters.')
    return _sanitize_response_paths(dict(workspace=workspace, selection=selection, summary=summary,
                                         assays=assays, fingerprint=fingerprint), request)


@router.post('/cohort-builder/apply')
def apply_draft(body: Draft, request: Request):
    available = patient_overview.sources(request, body.workspace)
    roots = {key: root for key, root, _ in available}
    if not roots:
        raise HTTPException(409, 'Select a workspace first.')
    before = cohort_filters._fingerprint(available, request_user_id(request))
    try:
        active = bool(body.q.strip() or body.diseases or body.sample_origin or body.clinical_filters
                      or body.modalities or body.exact or body.cohort_id or body.base_members is not None)
        if not active:
            return _response(request, body.workspace, available, None, 'Full workspace', before)
        candidates = None
        descriptions = []
        if body.clinical_filters:
            if body.fingerprint != before:
                raise HTTPException(409, 'Dataset contents changed. Reload clinical filters.')
            result = cohort_filters.evaluate(cohort_filters.FilterRequest(workspace=body.workspace,
                fingerprint=body.fingerprint, filters=body.clinical_filters), request)
            candidates = _keys(result['members'])
            descriptions.append(result['description'])
        if body.base_members is not None or body.cohort_id:
            if body.base_members is not None and body.cohort_id:
                raise HTTPException(422, 'Choose one starting patient group.')
            base = _saved_members(request, body.cohort_id, roots) if body.cohort_id else [m.model_dump() for m in body.base_members]
            base = _keys(_resolved(roots, base))
            candidates = base if candidates is None else candidates & base
            descriptions.append(body.source_label or 'Selected patient group')
        coverage = patient_overview.coverage(request, body.workspace)
        if (body.modalities or body.exact) and coverage.get('warnings'):
            raise HTTPException(409, 'Data availability is incomplete. Resolve dataset linkage warnings before applying modality filters.')
        patients = coverage['patients']
        if candidates is not None:
            patients = [p for p in patients if (p['dataset_id'], p['patient_id']) in candidates]
        if body.diseases:
            disease = {d.casefold() for d in patient_overview.disease_filter(body.diseases)}
            patients = [p for p in patients if disease.intersection(d.casefold() for d in p['diseases'])]
            descriptions.append('Any disease: ' + ', '.join(body.diseases))
        if body.q.strip() or body.sample_origin:
            # Source IDs plus declared ClarIDs; origin uses explicit biosample links.
            matches = patient_overview._select_patients(request, body.workspace, body.q, [], body.sample_origin)
            matching = _keys(matches['members'])
            if not body.sample_origin:
                matching.update((p['dataset_id'], p['patient_id']) for p in patients
                                if body.q.strip().casefold() in p['patient_id'].casefold())
            elif not body.q.strip():
                for key, root, _ in available:
                    matching.update((key, r['individualId']) for r in patient_overview.biosample_records(root, include_clarids=False)
                                    if patient_overview.origin_key(r) == body.sample_origin)
            patients = [p for p in patients if (p['dataset_id'], p['patient_id']) in matching]
            descriptions.extend(filter(None, [body.q, body.sample_origin]))
        required = {_modality(m) for m in body.modalities}
        def matches_modalities(patient):
            found = {_modality(m) for m in patient['modalities']}
            return required.issubset(found) and (not body.exact or found.issubset(required | {'clinical'}))
        patients = [p for p in patients if matches_modalities(p)]
        if required or body.exact:
            descriptions.append(('Only ' if body.exact else 'At least ') + ', '.join(sorted(required)))
        if len(patients) > 100_000:
            raise HTTPException(422, 'Select at most 100,000 patients. Narrow the filters.')
        # Membership came from authorized source inventories, so do not scan them again.
        members = [qualified_member(dict(dataset_id=p['dataset_id'], patient_id=p['patient_id'])) for p in patients]
        return _response(request, body.workspace, available, members, '; '.join(descriptions), before)
    except (ValueError, OSError, QueryStoreNotReadyError):
        raise HTTPException(409, 'Unable to apply filters. Check that the dataset stores and source data are available.') from None


@router.post('/cohort-builder/apply-selection')
def apply_selection(body: Selection, request: Request):
    available = patient_overview.sources(request, body.workspace)
    roots = {key: root for key, root, _ in available}
    before = cohort_filters._fingerprint(available, request_user_id(request))
    if sum([body.members is not None, body.patient_ids is not None, bool(body.result_handle), bool(body.cohort_id)]) != 1:
        raise HTTPException(422, 'Supply one patient selection.')
    try:
        members = [m.model_dump() for m in body.members] if body.members is not None else None
        patient_ids = body.patient_ids
        if body.result_handle:
            from app.routes import _load_authorized_query_result
            _, membership = _load_authorized_query_result(request, body.result_handle, dataset_id=body.workspace)
            patient_ids = membership['patient_ids']
        if body.cohort_id:
            members = _saved_members(request, body.cohort_id, roots)
        resolved = (_resolved(roots, members) if members is not None else
                    resolve_members(roots, patient_ids=patient_ids, id_type='patient') if patient_ids else [])
        return _response(request, body.workspace, available, resolved, body.label, before)
    except (ValueError, OSError, QueryStoreNotReadyError):
        raise HTTPException(409, 'This selection is no longer available. Reload its source data and try again.') from None


class ScopedSearch(BaseModel):
    members: list[Member] = Field(max_length=100_000)


@router.post('/patient-overview/scoped-search')
def scoped_search(body: ScopedSearch, request: Request, workspace: str,
                  sort_by: Literal['patient_id', 'dataset_label', 'diagnosis', 'clarid'] = 'patient_id',
                  direction: Literal['asc', 'desc'] = 'asc', offset: int = Query(0, ge=0)):
    sources = patient_overview.sources(request, workspace)
    allowed = {key: [] for key, _, _ in sources}
    for member in body.members:
        if member.dataset_id not in allowed:
            raise HTTPException(403, 'The selection includes a dataset outside this workspace.')
        allowed[member.dataset_id].append(member.patient_id)
    # Include linked patients without clinical records, too. A modality filter
    # must not report more selected patients than this browser can show.
    from app.cohort_members import source_inventory
    from app.query_store import _connect
    rows, total = [], 0
    for key, root, label in sources:
        selected = set(allowed[key])
        if not selected:
            continue
        clinical = patient_overview.lookup(root, '', offset + 21, sort_by=sort_by,
            descending=direction == 'desc', include_total=True, allowed_patient_ids=list(selected))
        total += clinical[0]['_total'] if clinical else 0
        for row in clinical:
            row.pop('_total', None)
            rows.append(dict(row, dataset_id=key, dataset_label=label))
        with _connect(root) as con:
            clinical_ids = {r[0] for r in con.execute('SELECT patient_id FROM patients WHERE patient_id IN (SELECT unnest(?))', [list(selected)]).fetchall()}
        remaining = selected - clinical_ids
        if remaining:
            known, _ = source_inventory(root)
            extras = remaining & known
            total += len(extras)
            rows.extend(dict(patient_id=pid, dataset_id=key, dataset_label=label,
                             diagnosis='', clarid='', clinical_record_count=0) for pid in extras)
    rows.sort(key=lambda row: (str(row.get(sort_by) or '').casefold(), row['patient_id'], row['dataset_id']),
              reverse=direction == 'desc')
    return dict(matches=rows[offset:offset+20], total=total,
                next={'offset':offset+20} if total > offset+20 else None)
