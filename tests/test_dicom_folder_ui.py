"""Folder-link UI uses mocked endpoints; no DICOM files are read."""
from test_ui_smoke import live_server, page, playwright


def test_folder_link_retry_and_completion(page):
    calls = []

    def link(route):
        calls.append(route.request.post_data_json)
        if len(calls) == 1:
            route.fulfill(status=400, json={'detail': 'Patient IDs do not match.'})
        else:
            route.fulfill(json={'studies': 2, 'instances': 8, 'patients': 2})

    page.route('**/local-viewer/datasets/demo/folder', link)
    page.evaluate('''async () => {
      const {openDicomFolderDialog} = await import('/static/js/dicom_folder.js');
      openDicomFolderDialog([{id:'demo',name:'Demo <study>'}]);
    }''')
    dialog = page.locator('.dicom-folder-dialog')
    playwright.expect(dialog.locator('option')).to_have_text('Demo <study>')
    dialog.locator('[name=directory]').fill('/fictional/images')
    dialog.get_by_role('button', name='Validate and link').click()
    playwright.expect(dialog.get_by_role('status')).to_have_text('Patient IDs do not match.')
    playwright.expect(dialog.locator('[name=directory]')).to_have_value('/fictional/images')
    dialog.get_by_role('button', name='Validate and link').click()
    playwright.expect(dialog.get_by_role('status')).to_contain_text('Linked 2 studies, 8 instances and 2 patients.')
    assert calls == [{'directory': '/fictional/images'}] * 2
    playwright.expect(dialog.locator('[name=directory]')).to_be_disabled()
    dialog.get_by_role('button', name='Done').click()
    playwright.expect(dialog).to_have_count(0)


def test_folder_picker_keeps_react_draft(page):
    page.evaluate('''async () => {
      window.__COHORTOME_DESKTOP__ = true;
      window.__TAURI__ = {core:{invoke:async () => '/fictional/picked'}};
      const {openDicomFolderDialog} = await import('/static/js/dicom_folder.js');
      openDicomFolderDialog([{id:'demo',name:'Demo'}]);
    }''')
    dialog = page.locator('.dicom-folder-dialog')
    dialog.get_by_role('button', name='Choose folder…').click()
    playwright.expect(dialog.locator('[name=directory]')).to_have_value('/fictional/picked')
    dialog.get_by_role('button', name='Cancel').click()
    playwright.expect(dialog).to_have_count(0)
