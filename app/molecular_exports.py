"""Bounded exports of declared feature-by-sample matrices, never raw assay files."""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

from fastapi import HTTPException
from app import exports
from app.export_settings import byte_limit
from app.cohort_members import resolve_members
from app.query_store import _manifest_assay_sample_patient_links, _detect_matrix_delimiter

MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 1024 * 1024 * 1024


def _inside(root, relative):
    path = (root / str(relative or '')).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Required assay file is unavailable or outside the dataset.')
    limit = byte_limit("source_mib", MAX_SOURCE_BYTES)
    if path.stat().st_size > limit:
        raise ValueError(f'Source exceeds the {limit / (1024 * 1024):g} MiB limit. Review Export limits in Settings.')
    return path


def _items(root):
    # No inferred manifests: export requires declared measurement and linkage metadata.
    path = root / 'assays' / 'manifest.json'
    if not path.exists():
        return []
    with _inside(root, 'assays/manifest.json').open(encoding='utf-8') as handle:
        payload = json.load(handle)
    items = payload.get('assays') if isinstance(payload, dict) else None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError('Assay manifest is invalid.')
    return items


def _prepare(root, item, members, sample_scope):
    if item.get('modality') == 'imaging':
        raise ValueError('Imaging measurements are not included in molecular export.')
    if item.get('sample_id_column') != 'matrix_columns' or not item.get('feature_id_column'):
        raise ValueError('Requires a declared feature-by-sample matrix.')
    if not item.get('data_type'):
        raise ValueError('Measurement type is not declared.')
    if not (item.get('sample_metadata_file') or item.get('patient_linkage') == 'exact_sample_id'
            or item.get('patient_id_column') == 'derived_from_sample_id_prefix'):
        raise ValueError('Patient linkage is not declared.')
    metadata_path = _inside(root, item['sample_metadata_file']) if item.get('sample_metadata_file') else None
    if item.get('modality') == 'methylation' and not metadata_path:
        raise ValueError('Methylation requires explicit sample-to-patient metadata.')
    path = _inside(root, item.get('file'))
    with path.open(encoding='utf-8-sig', newline='') as handle:
        first = handle.readline()
        delimiter = _detect_matrix_delimiter(first)
        handle.seek(0)
        header = next(csv.reader(handle, delimiter=delimiter), [])
    if len(header) < 2 or header[0] != item['feature_id_column']:
        raise ValueError('Matrix header does not match its declared feature column.')
    samples = header[1:]
    if any(not sid or sid != sid.strip() for sid in samples) or len(set(samples)) != len(samples):
        raise ValueError('Matrix sample IDs are blank, duplicated, or contain surrounding whitespace.')
    linkage = _manifest_assay_sample_patient_links(root, item, samples)
    if linkage['unlinked_sample_ids']:
        raise ValueError('Matrix has samples without patient linkage; review its metadata first.')
    patients = {m['patient_id'] for m in members}
    saved_samples = {m.get('sample_id') for m in members}
    selected = [sid for sid in samples if linkage['links'].get(sid) in patients
                and (not sample_scope or sid in saved_samples)]
    if not selected:
        raise ValueError('No matching samples in this cohort.')
    snapshot = dict(item=item, header=header, links=linkage['links'], selected=selected,
                    matrix_stat=[path.stat().st_size, path.stat().st_mtime_ns],
                    metadata_stat=([metadata_path.stat().st_size, metadata_path.stat().st_mtime_ns] if metadata_path else None))
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return dict(path=path, delimiter=delimiter, header=header, selected=selected,
                linkage=linkage, fingerprint=fingerprint)


def inventory(cohort, roots):
    try:
        members = resolve_members(roots, members=cohort['members'], id_type=cohort['id_type'])
        result, prepared = [], {}
        for dataset, directory in roots.items():
            root = Path(directory)
            local_members = [m for m in members if m['dataset_id'] == dataset]
            items = _items(root)
            ids = [str(item.get('assay_id') or '') for item in items]
            for item in items:
                aid = str(item.get('assay_id') or '')
                key = json.dumps([dataset, aid], separators=(',', ':'))
                row = dict(key=key, dataset_id=dataset, assay_id=aid,
                           label=str(item.get('label') or aid or 'Unnamed assay'),
                           modality=item.get('modality'), data_type=item.get('data_type'), available=False)
                try:
                    if not aid or ids.count(aid) != 1:
                        raise ValueError('Assay identifier is missing or duplicated.')
                    spec = _prepare(root, item, local_members, cohort['id_type'] != 'patient')
                    row.update(available=True, sample_count=len(spec['selected']),
                               patient_count=len({spec['linkage']['links'][sid] for sid in spec['selected']}),
                               source_bytes=spec['path'].stat().st_size, fingerprint=spec['fingerprint'])
                    prepared[key] = (root, item, local_members, spec)
                except (OSError, UnicodeError, csv.Error):
                    row['reason'] = 'Assay input cannot be read.'
                except ValueError as exc:
                    row['reason'] = str(exc)
                result.append(row)
        return result, prepared
    except (ValueError, OSError, KeyError):
        raise HTTPException(409, 'Cohort sources or assay manifest are unavailable. Review the dataset before exporting.') from None


def bundle(cohort, roots, selections):
    listing, prepared = inventory(cohort, roots)
    keys = [selection.key for selection in selections]
    if not keys or len(keys) != len(set(keys)):
        raise HTTPException(400, 'Select distinct assays to export.')
    if any(key not in prepared for key in keys):
        raise HTTPException(409, 'A selected assay is unavailable. Refresh the export dialog.')
    source_limit = byte_limit("total_source_mib", MAX_TOTAL_SOURCE_BYTES)
    if sum(prepared[key][3]['path'].stat().st_size for key in keys) > source_limit:
        raise HTTPException(413, f'Selected sources exceed {source_limit / (1024 * 1024):g} MiB. Select fewer assays or review Export limits in Settings.')
    limit = exports.output_limit()
    files, assay_metadata, sample_rows = {}, [], []
    total_bytes = total_rows = 0
    class BoundedText(io.StringIO):
        def write(self, value):
            nonlocal total_bytes
            total_bytes += len(value.encode('utf-8'))
            if total_bytes > limit:
                raise exports.size_error(limit)
            return super().write(value)
    for number, selection in enumerate(selections, start=1):
        root, item, members, spec = prepared[selection.key]
        if selection.fingerprint != spec['fingerprint']:
            raise HTTPException(409, 'Assay inputs changed. Refresh the export dialog.')
        dataset, aid = json.loads(selection.key)
        filename = f'assays/{number}/matrix.tsv'
        output = BoundedText(newline='')
        writer = csv.writer(output, delimiter='\t', lineterminator='\n')
        selected = set(spec['selected'])
        indices = [0] + [index for index, sid in enumerate(spec['header']) if index and sid in selected]
        features = set()
        try:
            with spec['path'].open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.reader(handle, delimiter=spec['delimiter'])
                if next(reader, []) != spec['header']:
                    raise ValueError('Changed header')
                writer.writerow([spec['header'][index] for index in indices])
                for row in reader:
                    if len(row) != len(spec['header']) or not row[0] or row[0] in features:
                        raise ValueError('Invalid feature rows')
                    features.add(row[0])
                    total_rows += 1
                    exports.check_size(total_rows)
                    writer.writerow([row[index] for index in indices])
        except (OSError, UnicodeError, ValueError, csv.Error):
            raise HTTPException(409, 'Selected matrix is unreadable or has malformed/duplicate feature rows. No partial export was created.') from None
        try:
            unchanged = _prepare(root, item, members, cohort['id_type'] != 'patient')['fingerprint'] == spec['fingerprint']
        except (ValueError, OSError, csv.Error):
            unchanged = False
        if not unchanged:
            raise HTTPException(409, 'Assay inputs changed during export. Try again.')
        files[filename] = exports.bounded_bytes(output.getvalue().encode('utf-8'))
        assay_metadata.append(dict(dataset_id=dataset, assay_id=aid, file=filename,
            sample_count=len(spec['selected']), feature_count=len(features),
            source_fingerprint=spec['fingerprint'], linkage=spec['linkage']['linkage_source'],
            **{field: item.get(field) for field in ('modality', 'data_type', 'value_kind', 'units', 'feature_namespace', 'feature_id_column')}))
        sample_rows.extend(dict(dataset_id=dataset, assay_id=aid, matrix_file=filename,
            sample_id=sid, patient_id=spec['linkage']['links'][sid]) for sid in spec['selected'])
    files['samples.tsv'] = exports.table_bytes(sample_rows, ('dataset_id', 'assay_id', 'matrix_file', 'sample_id', 'patient_id'))
    files['members.json'] = exports.json_bytes(cohort['members'])
    files['manifest.json'] = exports.json_bytes(exports.metadata('cohort_molecular_data', list(roots), total_rows,
        cohort_id=cohort['id'], name=cohort['name'], assays=assay_metadata,
        not_exported=[dict(dataset_id=row['dataset_id'], assay_id=row['assay_id'], reason=row.get('reason', 'Not selected'))
                      for row in listing if row['key'] not in keys],
        selection=('Saved samples only' if cohort['id_type'] != 'patient' else 'All linked samples of saved patients'),
        values='Source strings retained without normalization, rounding, imputation, or feature filtering. Missing units mean not declared. Import matrix TSVs with R/Python, not as executable spreadsheet formulas. Linkage TSV uses spreadsheet-safe identifier escaping.',
        omitted=['Clinical BFF records (use clinical export)', 'Raw sequencing files', 'DICOM pixels', 'Additional sample covariates'],
        provenance='Current source matrices, not frozen inputs from a previous analysis. Datasets and assays are never merged.'))
    if sum(map(len, files.values())) > limit:
        raise exports.size_error(limit)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return exports.bounded_bytes(output.getvalue())
