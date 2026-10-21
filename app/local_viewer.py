"""Local OHIF prototype: bundled synthetic DICOM only, governed on every read."""
import json
import mimetypes
import gzip
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.auth import require_authenticated
from app.config import BASE_DIR
from app.env import app_env
from app.routes import _require_detailed_assay_access, _resolve_route_dataset_dir

router = APIRouter(prefix='/local-viewer', tags=['dicom'])
ASSETS = BASE_DIR / 'runtime' / 'ohif'
SYNTHETIC_ROOT = BASE_DIR / 'default_dataset'
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
           'X-Content-Type-Options': 'nosniff'}


@lru_cache(maxsize=16)
def rebased_bundle(path, modified):
    # The pinned Docker build targets /. A release build should set PUBLIC_URL.
    source = gzip.decompress(Path(path).read_bytes())
    original = b'__webpack_require__.p = "/";'
    source = source.replace(original, b'__webpack_require__.p = "/local-viewer/";')
    if path.endswith('.css.gz'):
        source = source.replace(b'url(/', b'url(/local-viewer/')
        source = source.replace(b'url("/', b'url("/local-viewer/')
    return gzip.compress(source)


def authorized_root(request, dataset_id):
    require_authenticated(request)
    ids = _require_detailed_assay_access(request, dataset_id, '')
    if ids != [dataset_id]:
        raise HTTPException(403, 'Choose one authorized dataset.')
    root = Path(_resolve_route_dataset_dir(request, dataset_id, '')).resolve()
    if root != SYNTHETIC_ROOT.resolve():
        raise HTTPException(404, 'Local viewing currently supports the bundled synthetic dataset only.')
    return root


def instances(root, study_uid):
    import pydicom
    results = []
    for path in sorted((root / 'assays/imaging/dicom').glob('*.dcm')):
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            continue
        ds = pydicom.dcmread(path, stop_before_pixels=True)
        if str(ds.StudyInstanceUID) == study_uid:
            results.append((path, ds))
    if not results:
        raise HTTPException(404, 'Study not available.')
    return results


@router.get('/data/{dataset_id}/{study_uid}/metadata')
def metadata(request: Request, dataset_id: str, study_uid: str):
    rows = instances(authorized_root(request, dataset_id), study_uid)
    series = {}
    for _, ds in rows:
        # OHIF expects naturalized DICOM metadata, not tag-number JSON.
        fields = {}
        for element in ds:
            if not element.keyword or element.VR in {'SQ', 'OB', 'OW', 'UN'}:
                continue
            values = element.to_json_dict(None, 1024).get('Value', [])
            if element.VR == 'PN':
                values = [v.get('Alphabetic', '') for v in values]
            fields[element.keyword] = values if element.VM > 1 else (values[0] if values else '')
        sid = str(ds.SeriesInstanceUID)
        item = series.setdefault(sid, dict(SeriesInstanceUID=sid,
            SeriesNumber=int(ds.get('SeriesNumber', 0)), Modality=str(ds.get('Modality', '')),
            SeriesDescription=str(ds.get('SeriesDescription', '')), instances=[]))
        url = request.url_for('local_dicom_instance', dataset_id=dataset_id,
            study_uid=study_uid, instance_uid=str(ds.SOPInstanceUID))
        item['instances'].append(dict(metadata=fields, url=f'dicomweb:{url}'))
    first = rows[0][1]
    study = {k: str(first.get(k, '')) for k in (
        'StudyInstanceUID', 'StudyDate', 'StudyTime', 'PatientName', 'PatientID', 'StudyDescription')}
    study.update(series=list(series.values()), NumInstances=len(rows))
    return JSONResponse({'studies': [study]}, headers=HEADERS)


@router.get('/data/{dataset_id}/{study_uid}/{instance_uid}', name='local_dicom_instance')
def instance(request: Request, dataset_id: str, study_uid: str, instance_uid: str):
    rows = instances(authorized_root(request, dataset_id), study_uid)
    matches = [path for path, ds in rows if str(ds.SOPInstanceUID) == instance_uid]
    if len(matches) != 1:
        raise HTTPException(404, 'Image not available.')
    return FileResponse(matches[0], media_type='application/dicom', headers=HEADERS)


@router.get('/open/{dataset_id}/{study_uid}')
def launch(request: Request, dataset_id: str, study_uid: str):
    instances(authorized_root(request, dataset_id), study_uid)
    if not (ASSETS / 'index.html').is_file():
        raise HTTPException(503, 'Bundled viewer assets are not installed.')
    from fastapi.responses import RedirectResponse
    source = str(request.url_for('metadata', dataset_id=dataset_id, study_uid=study_uid))
    return RedirectResponse('/local-viewer/viewer/dicomjson?url=' + quote(source, safe=''), headers=HEADERS)


@router.get('/{asset:path}')
def assets(request: Request, asset: str):
    require_authenticated(request)
    if asset == 'app-config.js':
        # WebKitGTK can advertise WebGL2 yet draw a blank viewport in a VM.
        # The bundled viewer currently serves only 2D synthetic stacks, for
        # which OHIF's CPU renderer avoids that graphics-driver dependency.
        cpu_rendering = sys.platform == 'linux' and app_env('COHORTOME_DESKTOP_MODE').strip().lower() in {'1', 'true', 'yes', 'on'}
        config = dict(routerBasename='/local-viewer', showStudyList=False,
            useCPURendering=cpu_rendering,
            maxNumberOfWebWorkers=1, extensions=[], modes=['@ohif/mode-longitudinal'],
            dataSources=[dict(namespace='@ohif/extension-default.dataSourcesModule.dicomjson',
                             sourceName='dicomjson', configuration={})],
            defaultDataSourceName='dicomjson', showWarningMessageForCrossOrigin=False)
        return Response('window.config=' + json.dumps(config), media_type='text/javascript', headers=HEADERS)
    if asset in {'init-service-worker.js', 'sw.js'}:
        return Response('// Offline patient caching is disabled.', media_type='text/javascript', headers=HEADERS)
    if asset == 'viewer/dicomjson':
        path = ASSETS / 'index.html'
        if not path.is_file():
            raise HTTPException(503, 'Bundled viewer assets are not installed.')
        html = path.read_text().replace('="/', '="/local-viewer/').replace("window.PUBLIC_URL = '/'", "window.PUBLIC_URL = '/local-viewer/'")
        headers = dict(HEADERS)
        headers['Content-Security-Policy'] = "default-src 'self' blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' blob:; worker-src 'self' blob:; frame-ancestors 'self'; object-src 'none'"
        return HTMLResponse(html, headers=headers)
    path = (ASSETS / asset).resolve()
    if not path.is_relative_to(ASSETS.resolve()) or not path.is_file():
        raise HTTPException(404, 'Viewer asset not found.')
    compressed = path.with_name(path.name + '.gz')
    if path.stat().st_size == 0 and compressed.is_file():
        if path.suffix in {'.js', '.css'}:
            return Response(rebased_bundle(str(compressed), compressed.stat().st_mtime_ns),
                media_type=mimetypes.guess_type(path.name)[0], headers=dict(HEADERS, **{'Content-Encoding': 'gzip'}))
        return FileResponse(compressed, media_type=mimetypes.guess_type(path.name)[0],
                            headers=dict(HEADERS, **{'Content-Encoding': 'gzip'}))
    return FileResponse(path, headers=HEADERS)
