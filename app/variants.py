"""Read prepared biallelic panels, separately from quantitative assay matrices."""
import csv
import gzip
import json
from pathlib import Path
import re

from app.biosamples import read_biosamples


def _table(root, relative, required):
    path = Path(relative)
    if (not relative or '\\' in relative or path.is_absolute()
            or '..' in path.parts or path.parts[0] == 'clinical'
            or not (root / path).resolve().is_relative_to(root)):
        raise ValueError
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(root / path, 'rt', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not required <= set(headers):
            raise ValueError
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError
            yield row


def _unique(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if not value.strip() or value != value.strip() or value in result:
            raise ValueError
        result[value] = row
    if not result:
        raise ValueError
    return result


def read_variant_panel(root, patient_ids=None):
    """Validate a complete sample×variant grid; return annotations and carrier links.

    Raw GTs remain in the source file. A carrier here has a fully called genotype
    with positive alternate dosage; this is not a clinical diagnosis.
    """
    root = Path(root).resolve()
    manifest = root / 'manifest.json'
    if not manifest.is_file():
        return None
    try:
        config = json.loads(manifest.read_text(encoding='utf-8-sig')).get('variants')
        if config is None:
            return None
        if type(config['schema_version']) is not int or config['schema_version'] != 1:
            raise ValueError
        provenance = config.get('provenance', {})
        if not isinstance(provenance, dict) or any(not isinstance(v, str) for v in provenance.values()):
            raise ValueError
        if provenance.get('technology', '') not in ('', 'dna_sequencing', 'genotyping_array', 'synthetic'):
            raise ValueError
        variants = _unique(_table(root, config['annotations_file'], {
            'variant_id', 'assembly', 'chromosome', 'position', 'ref', 'alt'}), 'variant_id')
        for row in variants.values():
            if (not all(row[k].strip() for k in ('assembly', 'chromosome'))
                    or not row['position'].isdigit() or int(row['position']) < 1
                    or not re.fullmatch('[ACGTN]+', row['ref'])
                    or not re.fullmatch('[ACGTN]+', row['alt']) or row['ref'] == row['alt']):
                raise ValueError
        samples = _unique(_table(root, config['samples_file'], {
            'sample_id', 'patient_id'}), 'sample_id')
        biosamples = {r['id']: r for r in read_biosamples(root, patient_ids)}
        for row in samples.values():
            patient, specimen = row['patient_id'], row.get('biosample_id')
            if (not patient.strip() or patient != patient.strip()
                    or (patient_ids is not None and patient not in patient_ids)
                    or (specimen and (specimen not in biosamples
                        or biosamples[specimen]['individualId'] != patient))):
                raise ValueError
        seen = {key: set() for key in variants}
        carriers = {key: set() for key in variants}
        counts = dict(called=0, partial=0, missing=0)
        variant_counts = {key: dict(reference=0, alternate=0, partial=0, missing=0) for key in variants}
        for row in _table(root, config['genotypes_file'], {
                'variant_id', 'sample_id', 'GT', 'call_status', 'alt_dosage', 'ploidy', 'phased'}):
            vid, sid, gt = row['variant_id'], row['sample_id'], row['GT']
            if vid not in variants or sid not in samples or sid in seen[vid]:
                raise ValueError
            if not re.fullmatch(r'[01.](?:[/|][01.])*', gt) or ('/' in gt and '|' in gt):
                raise ValueError
            alleles = re.split(r'[/|]', gt)
            status = 'missing' if all(a == '.' for a in alleles) else 'partial' if '.' in alleles else 'called'
            dosage = str(alleles.count('1')) if status == 'called' else ''
            if (row['call_status'] != status or row['alt_dosage'] != dosage
                    or row['ploidy'] != ('' if gt == '.' else str(len(alleles)))
                    or row['phased'] != str('|' in gt).lower()):
                raise ValueError
            seen[vid].add(sid)
            counts[status] += 1
            variant_counts[vid][('alternate' if int(dosage) > 0 else 'reference') if status == 'called' else status] += 1
            if status == 'called' and int(dosage) > 0:
                carriers[vid].add(samples[sid]['patient_id'])
        if any(len(ids) != len(samples) for ids in seen.values()):
            raise ValueError
        return dict(variants=list(variants.values()), samples=list(samples.values()),
                    carriers=carriers, call_counts=counts, variant_counts=variant_counts,
                    provenance=provenance)
    except (OSError, EOFError, UnicodeError, csv.Error, ValueError, TypeError,
            KeyError, AttributeError, IndexError):
        raise ValueError('Variant panel is invalid: check contained TSV paths, unique IDs, patient/specimen links and the complete genotype grid.') from None
