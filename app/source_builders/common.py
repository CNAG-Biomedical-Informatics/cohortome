"""Shared operations for the shipped Store conversion recipes."""
import csv
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
import zipfile
import yaml

FIELDS = ['unique_id', 'subject_id', 'study', 'type', 'condition', 'sex', 'age_group']


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def encode_subjects(rows, output, executable, codebook, study, study_stub):
    """Shared encoder; dataset adapters supply their reviewed subject fields."""
    vocabulary = yaml.safe_load(codebook.read_text())
    version = subprocess.check_output([*executable, '--version'], text=True, timeout=30).strip()
    if str(vocabulary['metadata']['version']) != '0.04' or version.split()[-1] != '0.04':
        raise ValueError('Requires clarid-tools and codebook 0.04')
    output.mkdir(parents=True, exist_ok=False)
    vocabulary['entities']['subject']['study'][study] = dict(
        code=study, stub_code=study_stub, label=study, id='NCIT:C17998')
    vocabulary['metadata']['local_version'] = study + '-1'
    book = output / 'clarid-codebook.yaml'
    book.write_text(yaml.safe_dump(vocabulary, sort_keys=False))
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        source = directory / 'subjects.csv'
        write_csv(source, rows, FIELDS)
        for fmt, column in [('human', 'clar_id'), ('stub', 'stub_id')]:
            target = directory / f'{fmt}.csv'
            base = [*executable, 'code', '--entity', 'subject', '--format', fmt,
                    '--codebook', str(book), '--sep', ',']
            subprocess.run(base + ['--action', 'encode', '--infile', str(source),
                                  '--outfile', str(target)], check=True, capture_output=True, timeout=120)
            with target.open() as handle:
                encoded = {r['unique_id']: r[column] for r in csv.DictReader(handle)}
            for row in rows:
                row[column] = encoded[row['unique_id']]
            decoded = directory / f'{fmt}-decoded.csv'
            # Decode only IDs: original fields cannot mask decoding failures.
            ids = directory / f'{fmt}-ids.csv'
            write_csv(ids, rows, ['unique_id', column])
            subprocess.run(base + ['--action', 'decode', '--infile', str(ids),
                                  '--outfile', str(decoded), '--with-condition-name'],
                           check=True, capture_output=True, timeout=120)
            with decoded.open() as handle:
                result = {r['unique_id']: r for r in csv.DictReader(handle)}
            for row in rows:
                recovered = result[row['unique_id']]
                for field in ['condition', 'type', 'sex', 'age_group', 'study']:
                    expected = study_stub if fmt == 'stub' and field == 'study' else row[field]
                    if fmt == 'human' and field in {'sex', 'type'}:
                        entry = vocabulary['entities']['subject'][field].get(row[field])
                        entry = entry or vocabulary['entities']['_defaults'][row[field]]
                        expected = entry['code']
                    if recovered[field] != expected:
                        raise ValueError(f'{fmt} round-trip mismatch: {field}')
                if int(recovered['subject_id']) != row['subject_id']:
                    raise ValueError('Subject-number round-trip mismatch')
                row['condition_name'] = recovered['condition_name']
    write_csv(output / 'clarid_subjects.csv', rows, FIELDS + ['clar_id', 'stub_id', 'condition_name'])
