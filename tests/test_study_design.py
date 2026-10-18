import json

import pytest

from app.datasets import dataset_content_metadata, dataset_study_design


@pytest.mark.parametrize('representation', ['person', 'snapshot'])
@pytest.mark.parametrize('design', [None, 'cross_sectional', 'longitudinal', 'unknown'])
def test_design_is_explicit_and_independent_of_record_format(tmp_path, representation, design):
    manifest = {'schema_version': 1, 'clinical': {'representation': representation}}
    if design is not None:
        manifest['study_design'] = design
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'clinical').mkdir()
    expected = design if design in ('cross_sectional', 'longitudinal') else ''
    assert dataset_study_design(str(tmp_path)) == expected
    assert dataset_content_metadata(str(tmp_path))['study_design'] == expected
