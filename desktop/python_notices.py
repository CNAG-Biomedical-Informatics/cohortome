"""Retain installed Python distribution notices from the clean packaging environment.

This is a build-environment inventory, not a claim that every distribution is
frozen or that the final binary's redistribution requirements are satisfied.
"""
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import sys
import sysconfig


def notice_file(path):
    return bool(re.match(r'^(licen[sc]e|copying|notice|copyright)([._-]|$)', path.name, re.I))


def collect(destination, distributions=None, python_license_candidates=None):
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for dist in sorted(distributions if distributions is not None else metadata.distributions(),
                       key=lambda item: (item.metadata.get('Name', ''), item.version)):
        name = dist.metadata.get('Name', 'unknown')
        folder = re.sub(r'[^A-Za-z0-9_.-]', '_', f'{name}-{dist.version}')
        if folder in {'.', '..'}:
            raise ValueError('Invalid Python distribution name')
        copied = []
        for entry in dist.files or []:
            relative = Path(str(entry))
            if not notice_file(relative):
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file():
                continue
            # Wheel RECORD entries can refer to sibling directories. Keep the
            # copied destination inside this package's notice directory.
            parts = [re.sub(r'[^A-Za-z0-9_.-]', '_', part) if part not in {'.', '..'} else '_parent'
                     for part in relative.parts if part not in {relative.anchor, ''}]
            target = destination / folder / Path(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(target.relative_to(destination).as_posix())
        records.append({'name': name, 'version': dist.version,
                        'license_expression': dist.metadata.get('License-Expression', ''),
                        'license_classifiers': [value for value in dist.metadata.get_all('Classifier', [])
                                                if value.startswith('License ::')],
                        'notice_files': copied,
                        'review_required': not bool(copied)})
    candidates = python_license_candidates if python_license_candidates is not None else [
        Path(sys.base_prefix) / 'LICENSE.txt', Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt']
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license:
        shutil.copyfile(python_license, destination / 'PYTHON-LICENSE.txt')
    report = {'scope': 'installed Python build environment; may include build-only packages',
              'redistribution_review': 'pending; native libraries require separate review',
              'python_version': sys.version.split()[0], 'python_license_retained': bool(python_license),
              'distributions': records}
    (destination / 'index.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
