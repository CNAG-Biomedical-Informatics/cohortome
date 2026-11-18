"""Keep UI markup in components; chart interiors and fixed SVGs are exceptions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_controllers_do_not_regenerate_ui_html():
    allowed = {'timeline.js', 'modalities.js', 'app_navigation.js'}
    for path in (ROOT / 'static/js').glob('*.js'):
        if path.name not in allowed:
            assert 'innerHTML' not in path.read_text(), path.name
            assert 'insertAdjacentHTML' not in path.read_text(), path.name
    assert 'innerHTML' not in (ROOT / 'static/app.js').read_text()


def test_html_injection_boundary_is_only_the_fixed_icon_catalogue():
    allowed = {'timeline.jsx', 'multimodal.jsx', 'assay-overview.jsx', 'dataset-picker.jsx'}
    for path in (ROOT / 'frontend/src').rglob('*.jsx'):
        if path.name not in allowed:
            assert 'dangerouslySetInnerHTML' not in path.read_text(), path.name


def test_server_template_only_bootstraps_the_ui():
    source = (ROOT / 'templates/index.html').read_text()
    assert 'applicationRoot' in source and '| tojson' in source
    assert 'analysisThread' not in source
    assert not (ROOT / 'templates/partials/data_management.html').exists()
