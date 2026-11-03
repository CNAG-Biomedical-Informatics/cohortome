import gzip
import json

import pytest

from app.variants import read_variant_panel
from app.dataset_validation import validate_package, PackageValidationError


@pytest.fixture
def panel(tmp_path):
    (tmp_path / 'clinical').mkdir()
    (tmp_path / 'clinical/individuals.json').write_text('[{"id":"P1"},{"id":"P2"},{"id":"P3"}]')
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'schema_version': 1, 'clinical': {'representation': 'person'},
        'variants': {'schema_version': 1, 'annotations_file': 'variants.tsv',
                     'samples_file': 'samples.tsv', 'genotypes_file': 'genotypes.tsv.gz'}}))
    (tmp_path / 'variants.tsv').write_text(
        'variant_id\tassembly\tchromosome\tposition\tref\talt\tclassification_source\tclassification_version\n'
        'v1\tGRCh37\t22\t10\tA\tC\tExample\t1\n')
    (tmp_path / 'samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\nS2\tP2\nS3\tP3\n')
    with gzip.open(tmp_path / 'genotypes.tsv.gz', 'wt') as out:
        out.write('variant_id\tsample_id\tGT\tcall_status\talt_dosage\tploidy\tphased\n'
                  'v1\tS1\t0|1\tcalled\t1\t2\ttrue\n'
                  'v1\tS2\t./.\tmissing\t\t2\tfalse\n'
                  'v1\tS3\t1/.\tpartial\t\t2\tfalse\n')
    return tmp_path


def test_panel_counts_and_missing_are_not_reference(panel):
    result = read_variant_panel(panel, {'P1', 'P2', 'P3'})
    assert result['carriers'] == {'v1': {'P1'}}
    assert result['call_counts'] == {'called': 1, 'missing': 1, 'partial': 1}
    summary = validate_package(panel)
    assert (summary['variants'], summary['variant_samples'], summary['assays']) == (1, 3, 0)


@pytest.mark.parametrize('change', ['duplicate', 'incomplete', 'dosage', 'missing', 'unknown', 'phase', 'ploidy'])
def test_reject_invalid_grid(panel, change):
    path = panel / 'genotypes.tsv.gz'
    with gzip.open(path, 'rt') as source:
        text = source.read()
    if change == 'duplicate': text += text.splitlines(True)[1]
    if change == 'incomplete': text = ''.join(text.splitlines(True)[:-1])
    if change == 'dosage': text = text.replace('called\t1', 'called\t0')
    if change == 'missing': text = text.replace('missing\t\t', 'missing\t0\t')
    if change == 'unknown': text = text.replace('v1\tS3', 'v1\tS4')
    if change == 'phase': text = text.replace('true', 'false')
    if change == 'ploidy': text = text.replace('called\t1\t2', 'called\t1\t1')
    with gzip.open(path, 'wt') as out:
        out.write(text)
    with pytest.raises(PackageValidationError, match='Variant panel is invalid'):
        validate_package(panel)


@pytest.mark.parametrize('path', ['../variants.tsv', '/tmp/variants.tsv', 'clinical/individuals.json'])
def test_reject_paths(panel, path):
    manifest = json.loads((panel / 'manifest.json').read_text())
    manifest['variants']['annotations_file'] = path
    (panel / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Variant panel is invalid'):
        read_variant_panel(panel)


def test_unknown_patient_and_specimen(panel):
    with pytest.raises(ValueError):
        read_variant_panel(panel, {'P1'})
    (panel / 'samples.tsv').write_text('sample_id\tpatient_id\tbiosample_id\nS1\tP1\tmissing\n')
    with pytest.raises(ValueError):
        read_variant_panel(panel)


def test_optional(tmp_path):
    assert read_variant_panel(tmp_path) is None


def test_inventory_counts_samples_not_carriers(panel):
    from app.patient_overview import sample_inventory
    rows, warnings = sample_inventory(panel)
    assert not warnings
    assert len(rows) == 3  # Missing/partial calls still belong to assayed samples.
    assert {r['modality'] for r in rows} == {'genotyping'}
    rows, warnings = sample_inventory(panel, 'P2')
    assert len(rows) == 1 and rows[0]['sample_id'] == 'S2'


def test_annotations_optional(panel):
    path = panel / 'variants.tsv'
    path.write_text('\n'.join('\t'.join(line.split('\t')[:6]) for line in path.read_text().splitlines()) + '\n')
    assert validate_package(panel)['variants'] == 1


def test_browser_filters_pagination_and_qualified_carriers(panel, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import variant_browser as browser
    monkeypatch.setattr(browser, 'sources', lambda *args: [('one', panel, 'One'), ('two', panel, 'Two')])
    app = FastAPI()
    app.include_router(browser.router)
    with TestClient(app) as client:
        panels = client.get('/variants/panels', params={'workspace': 'scope'}).json()
        assert len(panels) == 2
        assert len(panels[0]['patient_ids']) == 3
        assert set(panels[0]['patient_ids']).isdisjoint(panels[1]['patient_ids'])
        assert set(panels[0]['sample_ids']).isdisjoint(panels[1]['sample_ids'])
        params = {'workspace': 'scope', 'dataset_id': 'two'}
        response = client.get('/variants/search', params=params)
        assert response.status_code == 200
        assert response.json()['rows'][0]['carriers'] == 1
        assert response.json()['classifications'] == []
        assert client.get('/variants/search', params={**params, 'chromosome': '23'}).json()['total'] == 0
        assert client.get('/variants/search', params={**params, 'offset': 25}).json()['rows'] == []
        detail = client.get('/variants/detail', params={**params, 'variant_id': 'v1'}).json()
        assert detail['members'] == [{'dataset_id': 'two', 'patient_id': 'P1'}]
        assert detail['counts'] == {'reference': 0, 'alternate': 1, 'partial': 1, 'missing': 1}
        assert client.get('/variants/detail', params={**params, 'variant_id': 'absent'}).status_code == 404
        assert client.get('/variants/search', params={**params, 'dataset_id': 'forbidden'}).status_code == 403
        # Pagination and natural chromosome/position ordering, without a large fixture.
        original = browser.read_variant_panel(panel)
        original['variants'] = [dict(original['variants'][0], variant_id=f'v{i}', position=str(i), chromosome='2' if i < 10 else '10') for i in range(1, 31)]
        original['carriers'] = {r['variant_id']: set() for r in original['variants']}
        monkeypatch.setattr(browser, 'read_variant_panel', lambda _: original)
        page = client.get('/variants/search', params=params).json()
        assert page['total'] == 30 and len(page['rows']) == 25
        assert page['rows'][0]['variant_id'] == 'v1'
        assert len(client.get('/variants/search', params={**params, 'offset': 25}).json()['rows']) == 5


def test_browser_enforces_shared_permissions(panel, monkeypatch):
    from fastapi import HTTPException
    from app import variant_browser as browser
    def denied(*args):
        raise HTTPException(403, 'Detailed access required')
    monkeypatch.setattr(browser, 'sources', denied)
    with pytest.raises(HTTPException) as error:
        browser.panel_for(None, 'scope', 'one')
    assert error.value.status_code == 403
