"""Cheap change detection for declared dataset inputs; never read matrix bodies."""
import json
from pathlib import Path


def dataset_input_signature(root):
    root = Path(root).resolve()
    paths = {Path('manifest.json'), Path('assays/manifest.json')}

    def references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if (key == 'file' or key.endswith('_file')) and isinstance(item, str) and item:
                    relative = Path(item)
                    if (relative.is_absolute() or '..' in relative.parts or '\\' in item
                            or not (root / relative).resolve().is_relative_to(root)):
                        raise ValueError('Dataset input must remain inside its package.')
                    paths.add(relative)
                elif isinstance(item, (dict, list)):
                    references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)

    for name in ('manifest.json', 'assays/manifest.json'):
        path = root / name
        if path.is_file():
            references(json.loads(path.read_text(encoding='utf-8-sig')))
    clinical = root / 'clinical' if (root / 'clinical').is_dir() else root
    for pattern in ('*.json', '*.json.gz'):
        paths.update(path.relative_to(root) for path in clinical.glob(pattern) if path.is_file())
    # Match legacy assay discovery until all supported inputs use manifests.
    paths.update(path.relative_to(root) for path in (root / 'assays').glob('*/*.csv') if path.is_file())
    result = []
    for relative in sorted(paths):
        path = root / relative
        try:
            stat = path.stat()
        except FileNotFoundError:
            result.append(dict(name=relative.as_posix(), missing=True))
        else:
            result.append(dict(name=relative.as_posix(), size=stat.st_size, mtime_ns=stat.st_mtime_ns))
    return result
