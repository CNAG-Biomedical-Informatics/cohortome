"""Package-authored documentation, independent of query-store readiness."""
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.auth import require_authenticated
from app.bff import resolve_project_data_dir
from app.datasets import authorized_datasets_for_user

router = APIRouter(tags=['datasets'])
MAX_DOCUMENT_BYTES = 256 * 1024


@router.get('/datasets/{dataset_id}/about/{filename}', response_class=PlainTextResponse)
def dataset_document(dataset_id: str, filename: str, request: Request):
    data = dataset_about(dataset_id, request)
    document = next((d for d in data['documents'] if d['filename'] == filename), None)
    if document is None:
        raise HTTPException(404, 'Documentation not found.')
    return PlainTextResponse(document['text'], headers={'Cache-Control': 'no-store',
                                                       'X-Content-Type-Options': 'nosniff'})


@router.get('/datasets/{dataset_id}/about')
def dataset_about(dataset_id: str, request: Request):
    user = require_authenticated(request)
    dataset = next((d for d in authorized_datasets_for_user(user)
                    if d['dataset_id'] == dataset_id), None)
    if dataset is None:
        raise HTTPException(404, 'Dataset not found.')
    documents = []
    unavailable = []
    description = dataset.get('description') or ''
    try:
        if not dataset.get('root_path'):
            raise ValueError('Missing package root')
        root = resolve_project_data_dir(dataset['root_path']).resolve()
        # Older imports registered only "Imported resource <version>".
        # Recover the author's summary without changing an edited description.
        if not description.strip() or description.startswith('Imported resource '):
            resource = root / 'resource.json'
            if resource.is_file() and not resource.is_symlink():
                try:
                    with resource.open('rb') as handle:
                        raw = handle.read(MAX_DOCUMENT_BYTES + 1)
                    if len(raw) <= MAX_DOCUMENT_BYTES:
                        metadata = json.loads(raw)
                        summary = metadata.get('description') if isinstance(metadata, dict) else None
                        if isinstance(summary, str) and summary.strip():
                            description = summary.strip()
                except (OSError, ValueError):
                    pass
        # Only these human-facing documents are published, never provenance
        # JSON, arbitrary paths, or clinical/sample records.
        for filename, title in [('README.md', 'Overview'), ('TERMS.md', 'Terms and attribution')]:
            path = root / filename
            if path.is_symlink():
                unavailable.append(title)
                continue
            if not path.is_file():
                continue
            try:
                with path.open('rb') as handle:
                    content = handle.read(MAX_DOCUMENT_BYTES + 1)
                if len(content) > MAX_DOCUMENT_BYTES:
                    raise ValueError('Document too large')
                documents.append({'filename': filename, 'title': title,
                                  'text': content.decode('utf-8-sig')})
            except (OSError, ValueError):
                unavailable.append(title)
    except (OSError, ValueError):
        unavailable.append('Package documentation')
    return {'dataset_id': dataset_id, 'name': dataset.get('name') or dataset_id,
            'description': description,
            'documents': documents, 'unavailable': unavailable}
