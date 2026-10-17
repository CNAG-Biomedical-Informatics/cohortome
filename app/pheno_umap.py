"""Optional cohort projection matching Pheno-Ranker desktop's UMAP parameters."""
import csv
import json
import re
from importlib.metadata import version
import numpy as np


def load_distances(path, metric, limit):
    if metric not in {'hamming', 'jaccard'}:
        raise ValueError('Unsupported cohort metric.')
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.reader(handle, delimiter='\t')
        labels = next(reader, [])[1:]
        count = len(labels)
        if count > limit:
            raise ValueError(f'UMAP is limited to {limit} records; the cohort matrix is still available.')
        if count < 3 or len(set(labels)) != count or any(not label for label in labels):
            raise ValueError('UMAP requires at least three uniquely labelled records.')
        distances = np.empty((count, count), dtype=float)
        rows = 0
        for index, row in enumerate(reader):
            if index >= count or len(row) != count + 1 or row[0] != labels[index]:
                raise ValueError('UMAP matrix row and column IDs must match in order.')
            distances[index] = [float(value) for value in row[1:]]
            rows += 1
        if rows != count or not np.isfinite(distances).all():
            raise ValueError('UMAP requires a finite square matrix.')
        if (distances < 0).any() or not np.allclose(distances, distances.T):
            raise ValueError('UMAP requires nonnegative symmetric values.')
        if metric == 'jaccard':
            if (distances > 1).any():
                raise ValueError('Jaccard similarity must lie between zero and one.')
            distances = 1 - distances
        if not np.allclose(np.diag(distances), 0):
            raise ValueError('UMAP distance diagonal must be zero.')
    return labels, distances


def generate_umap_points(matrix_path, metric, record_patients=None, limit=2500):
    """Projection failure does not discard a successful cohort comparison."""
    status = {'script': 'umap_points', 'returncode': '0', 'stdout': '', 'stderr': ''}
    try:
        labels, distances = load_distances(matrix_path, metric or 'hamming', limit)
        try:
            from umap import UMAP
        except ImportError:
            raise RuntimeError('UMAP is not installed. Install cohortome[umap] in the app and worker environment.') from None
        parameters = dict(n_components=2, metric='precomputed', n_neighbors=min(30, len(labels) - 1),
                          min_dist=0.3, random_state=42, n_jobs=1, init='random')
        coordinates = UMAP(**parameters).fit_transform(distances)
        if coordinates.shape != (len(labels), 2) or not np.isfinite(coordinates).all():
            raise ValueError('UMAP produced invalid coordinates.')
        from app.identities import decode_identity
        with matrix_path.with_name('umap_points.tsv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle, delimiter='\t')
            writer.writerow(['record_id', 'patient_id', 'x', 'y'])
            for label, (x, y) in zip(labels, coordinates):
                source = re.sub(r'^C\d+_', '', label)
                patient = (record_patients or {}).get(source, '' if decode_identity(source) else source.split(':', 1)[0])
                writer.writerow([label, patient, float(x), float(y)])
        metadata = dict(method='UMAP', source_metric=metric or 'hamming', parameters=parameters,
                        versions={'numpy': np.__version__, 'umap-learn': version('umap-learn')},
                        note='UMAP emphasizes local neighbourhoods; cluster separation is not original distance.')
        matrix_path.with_name('umap_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        status['stdout'] = 'Wrote umap_points.tsv and umap_metadata.json.'
    except Exception as error:
        status.update(returncode='1', stderr=str(error))
    return status
