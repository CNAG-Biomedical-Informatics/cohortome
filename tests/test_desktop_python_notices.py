from email.message import Message
import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('python_notices', Path(__file__).parents[1] / 'desktop/python_notices.py')
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


def test_collect_copies_notices_without_claiming_release_approval(tmp_path):
    installed = tmp_path / 'installed'
    installed.mkdir()
    (installed / 'LICENSE.txt').write_text('Synthetic licence fixture')
    (installed / 'module.py').write_text('not a licence')
    metadata = Message()
    metadata['Name'] = 'example'
    metadata['License-Expression'] = 'MIT'
    dist = SimpleNamespace(metadata=metadata, version='1.0',
                           files=['LICENSE.txt', 'module.py'], locate_file=lambda p: installed / p)
    output = tmp_path / 'notices'
    report = notices.collect(output, [dist], [])
    assert (output / 'example-1.0/LICENSE.txt').read_text() == 'Synthetic licence fixture'
    assert not (output / 'example-1.0/module.py').exists()
    assert report['distributions'][0]['license_expression'] == 'MIT'
    assert report['redistribution_review'].startswith('pending')
    assert report['python_license_retained'] is False


def test_missing_notices_remain_explicit_review_items(tmp_path):
    metadata = Message()
    metadata['Name'] = 'no-notices'
    dist = SimpleNamespace(metadata=metadata, version='1', files=None)
    report = notices.collect(tmp_path / 'notices', [dist], [])
    assert report['distributions'][0]['review_required'] is True
