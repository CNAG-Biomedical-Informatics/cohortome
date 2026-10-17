import csv
import json
import numpy as np
import pytest

from app.pheno_umap import generate_umap_points, load_distances
from app.schemas import PhenoRankerRequest, UserSettingsResponse
from app.user_settings import normalize_user_settings


def matrix(tmp_path, metric='hamming'):
    path = tmp_path / 'matrix.txt'
    values = np.array([[0, .1, .8, .9], [.1, 0, .7, .8], [.8, .7, 0, .2], [.9, .8, .2, 0]])
    if metric == 'jaccard':
        values = 1 - values
    with path.open('w') as handle:
        writer = csv.writer(handle, delimiter='\t')
        writer.writerow(['id', 'a', 'b', 'c', 'd'])
        for label, row in zip('abcd', values):
            writer.writerow([label, *row])
    return path


def test_umap_is_opt_in():
    assert not UserSettingsResponse().pheno_render_umap
    assert not PhenoRankerRequest().render_umap
    assert not normalize_user_settings({})['pheno_render_umap']
    assert normalize_user_settings({'pheno_render_umap': True})['pheno_render_umap']


def test_distance_contract_and_size_guard(tmp_path):
    path = matrix(tmp_path, 'jaccard')
    labels, values = load_distances(path, 'jaccard', 4)
    assert labels == list('abcd')
    assert values[0, 1] == pytest.approx(.1)
    with pytest.raises(ValueError, match='limited'):
        load_distances(path, 'jaccard', 3)
    path.write_text('id\ta\tb\tc\na\t0\t1\t2\nb\t1\t0\t1\nwrong\t2\t1\t0\n')
    with pytest.raises(ValueError, match='IDs'):
        load_distances(path, 'hamming', 4)


def test_real_umap_is_reproducible_and_records_parameters(tmp_path):
    pytest.importorskip('umap')
    path = matrix(tmp_path)
    result = generate_umap_points(path, 'hamming', {'a': 'patient-a'})
    assert result['returncode'] == '0', result['stderr']
    first = path.with_name('umap_points.tsv').read_text()
    assert 'patient-a' in first
    assert generate_umap_points(path, 'hamming', {'a': 'patient-a'})['returncode'] == '0'
    assert path.with_name('umap_points.tsv').read_text() == first
    metadata = json.loads(path.with_name('umap_metadata.json').read_text())
    assert metadata['parameters']['n_jobs'] == 1
    assert metadata['parameters']['random_state'] == 42
    assert metadata['parameters']['n_neighbors'] == 3
