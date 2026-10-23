"""Dataset-scoped references to DICOM files; images are never copied or deleted."""
import hashlib
import json
from pathlib import Path

from app.config import STATE_ROOT_DIR
from app.state_io import atomic_write_json


def index_path(root):
    key = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
    return STATE_ROOT_DIR / 'dicom-links' / (key + '.json')


def linked_index(root):
    path = index_path(root)
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def safe_file(folder, relative):
    folder = Path(folder)
    path = folder / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Invalid image path.')
    if folder.is_symlink() or any(p.is_symlink() for p in [path, *path.parents] if p != folder.parent):
        raise ValueError('Symbolic links are not supported for DICOM files.')
    if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file():
        raise ValueError('An image is missing. Relink the DICOM folder.')
    return path


def scan_folder(folder, patients):
    import pydicom
    from pydicom.errors import InvalidDicomError
    folder = Path(folder)
    if not folder.is_absolute() or not folder.is_dir() or folder.is_symlink():
        raise ValueError('Choose an existing absolute DICOM folder, not a symbolic link.')
    folder = folder.resolve()
    studies, seen, rows = {}, set(), []
    unmatched = 0
    for path in sorted(folder.rglob('*')):
        if not path.is_file():
            continue
        path = safe_file(folder, str(path.relative_to(folder)))
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True)
        except InvalidDicomError:
            continue
        keys = ('PatientID', 'StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID')
        patient, study, series, instance = (str(ds.get(k, '')).strip() for k in keys)
        if not all((patient, study, series, instance)):
            raise ValueError('A DICOM file lacks a patient, study, series or instance identifier.')
        from app.dicom import _clean_uid
        if not all(_clean_uid(uid) == uid for uid in (study, series, instance)):
            raise ValueError('A DICOM file has an invalid UID.')
        if patient not in patients:
            unmatched += 1
            continue
        if instance in seen:
            raise ValueError('Duplicate DICOM instance UIDs found. Choose one copy of each image.')
        seen.add(instance)
        item = studies.setdefault(study, dict(study_id=study, study_instance_uid=study,
            patient_id=patient, label=str(ds.get('StudyDescription', 'DICOM study')),
            study_description=str(ds.get('StudyDescription', '')), modality=str(ds.get('Modality', '')),
            timepoint=str(ds.get('StudyDate', '')), series={}))
        if item['patient_id'] != patient:
            raise ValueError('One study is assigned to multiple patients.')
        series_item = item['series'].setdefault(series, dict(series_instance_uid=series,
            series_description=str(ds.get('SeriesDescription', '')), instance_count=0, sop_instance_uids=[]))
        series_item['instance_count'] += 1
        series_item['sop_instance_uids'].append(instance)
        stat = path.stat()
        rows.append(dict(file=str(path.relative_to(folder)), patient_id=patient,
            study_uid=study, series_uid=series, instance_uid=instance,
            size=stat.st_size, modified=stat.st_mtime_ns))
    if unmatched:
        raise ValueError(f'{unmatched} DICOM files have PatientID values absent from this dataset. '
                         'Provide files with matching patient IDs; nothing was linked.')
    if not rows:
        raise ValueError('No readable DICOM files found. Use standard DICOM files with a file header.')
    for item in studies.values():
        item['series'] = list(item['series'].values())
    return dict(folder=str(folder), instances=rows, studies=list(studies.values()))


def link_folder(root, folder):
    from app.bff import list_patient_summaries
    patients = {patient.patient_id for patient in list_patient_summaries(str(root))}
    payload = scan_folder(folder, patients)
    atomic_write_json(index_path(root), payload, file_mode=0o600)
    return payload


def indexed_instances(root, study_uid):
    import pydicom
    payload = linked_index(root)
    if payload is None:
        return None
    result = []
    for row in payload['instances']:
        if row['study_uid'] != study_uid:
            continue
        path = safe_file(payload['folder'], row['file'])
        stat = path.stat()
        if stat.st_size != row['size'] or stat.st_mtime_ns != row['modified']:
            raise ValueError('An image changed. Relink the DICOM folder before viewing it.')
        ds = pydicom.dcmread(path, stop_before_pixels=True)
        if (str(ds.PatientID), str(ds.StudyInstanceUID), str(ds.SeriesInstanceUID), str(ds.SOPInstanceUID)) != (
                row['patient_id'], row['study_uid'], row['series_uid'], row['instance_uid']):
            raise ValueError('Image identifiers changed. Relink the DICOM folder.')
        result.append((path, ds))
    return result
