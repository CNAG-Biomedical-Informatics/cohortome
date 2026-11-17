"""Molecular export selection uses fictional metadata and mocked downloads."""
from test_ui_smoke import live_server, page, playwright


def test_molecular_export_limits_retry_and_selection(page):
    items = [dict(key=str(i), fingerprint='fixture', label=f'Assay {i}',
                  dataset_id='demo', data_type='counts', available=True,
                  patient_count=2, sample_count=2, source_bytes=64*1048576)
             for i in range(3)]
    items.append(dict(key='missing', label='<Unavailable>', available=False,
                      dataset_id='demo', reason='No matching samples'))
    page.route('**/saved-cohorts/example/export-assays', lambda r: r.fulfill(json={
        'sample_scope': False, 'assays': items}))
    calls = []

    def download(route):
        calls.append(route.request.post_data_json)
        route.fulfill(status=409, json={'detail': 'Source changed; reopen export.'})

    page.route('**/saved-cohorts/example/export-molecular', download)
    page.evaluate('''async () => {
      const {openMolecularExport} = await import('/static/js/cohort_export.js');
      await openMolecularExport('example');
    }''')
    dialog = page.locator('#cohortExportDialog')
    boxes = dialog.locator('input[type=checkbox]')
    button = dialog.get_by_role('button', name='Download ZIP')
    playwright.expect(button).to_be_disabled()
    playwright.expect(boxes.nth(3)).to_be_disabled()
    boxes.nth(0).check()
    boxes.nth(1).check()
    playwright.expect(button).to_be_enabled()
    boxes.nth(2).check()
    playwright.expect(button).to_be_disabled()
    boxes.nth(2).uncheck()
    button.click()
    playwright.expect(dialog.get_by_role('status')).to_contain_text('Source changed')
    assert calls == [{'assays': [{'key': '0', 'fingerprint': 'fixture'},
                                 {'key': '1', 'fingerprint': 'fixture'}]}]
    playwright.expect(boxes.nth(0)).to_be_checked()
    playwright.expect(boxes.nth(3)).to_be_disabled()
    playwright.expect(button).to_be_enabled()
    dialog.get_by_role('button', name='Close', exact=True).click()
    playwright.expect(dialog).to_have_count(0)
