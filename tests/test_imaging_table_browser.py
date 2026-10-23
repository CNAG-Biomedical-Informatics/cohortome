from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def test_imaging_study_table_counts_and_viewer_actions():
    root = Path(__file__).resolve().parents[1]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route('http://imaging.test/', lambda r: r.fulfill(content_type='text/html',
            body='<input id="data" value="demo"><div id="health"></div><div id="status"></div><div id="studies"></div>'))
        page.route('http://imaging.test/static/js/**', lambda r: r.fulfill(content_type='text/javascript',
            body=(root / 'static/js' / r.request.url.rsplit('/', 1)[-1]).read_text()))
        page.route('http://imaging.test/local-viewer/open/**', lambda r: r.fulfill(body='Test viewer'))
        page.goto('http://imaging.test/')
        page.evaluate('''async () => {
          const {createDashboardUi} = await import('/static/js/dashboard.js');
          window.ui = createDashboardUi({refs:{
            dataDirEl:document.querySelector('#data'),
            dicomDashboardHealthEl:document.querySelector('#health'),
            dicomDashboardStatusEl:document.querySelector('#status'),
            dicomDashboardStudiesEl:document.querySelector('#studies')},
            helpers:{escapeHtml:s=>String(s)}, callbacks:{}, constants:{}, state:{}});
          ui.renderDicomStudies({enabled:false,studies:[
            {label:'Demo MRI',patient_id:'P01',timepoint:'Baseline',modality:'MR',
              series:[{instance_count:1}],local_viewer_url:'/local-viewer/open/demo'},
            {label:'External study',patient_id:'P02',series:[]}
          ]});
        }''')
        expect(page.locator('tbody tr')).to_have_count(2)
        expect(page.locator('#status')).to_have_text('2 patients · 2 imaging studies')
        expect(page.get_by_role('columnheader', name='Series in study')).to_be_visible()
        expect(page.locator('tbody tr').first).to_contain_text('Dataset-linked DICOM files')
        expect(page.locator('tbody tr').nth(1)).to_contain_text('Not reported')
        expect(page.get_by_role('button', name='Unavailable')).to_be_disabled()
        page.get_by_role('button', name='View images', exact=True).click()
        expect(page.locator('dialog iframe')).to_have_attribute('src', 'http://imaging.test/local-viewer/open/demo')
        page.get_by_role('button', name='Close viewer').click()
        expect(page.locator('dialog')).to_have_count(0)
        page.get_by_text('What do these counts mean?', exact=True).click()
        expect(page.get_by_text('A study is an imaging examination.', exact=False)).to_be_visible()
        page.evaluate("ui.renderDicomStudies({enabled:true,studies:[{label:'External',series:[{instance_count:12},{instance_count:20}],ohif_url:'https://viewer.example/viewer'}]})")
        expect(page.locator('tbody tr td').nth(4)).to_have_text('2')
        expect(page.locator('tbody tr td').nth(5)).to_have_text('32')
        expect(page.get_by_role('link', name='View images')).to_have_attribute('href', 'https://viewer.example/viewer')
        expect(page.locator('#status')).to_have_text('0 linked patients · 1 imaging study · 1 without patient linkage')
        page.evaluate("ui.renderDicomStudies({studies:[{patient_id:'P01',source_dataset_id:'a'},{patient_id:'P01',source_dataset_id:'a'},{patient_id:'P01',source_dataset_id:'b'}]})")
        expect(page.locator('#status')).to_have_text('2 patients · 3 imaging studies')
        page.get_by_label('Patient', exact=True).fill('b · P01')
        expect(page.locator('tbody tr')).to_have_count(1)
        expect(page.locator('#status')).to_have_text('2 patients · 3 imaging studies')
        page.get_by_role('button', name='All patients', exact=True).click()
        expect(page.locator('tbody tr')).to_have_count(3)
        page.evaluate("ui.renderDicomStudies({studies:Array.from({length:51},(_,i)=>({patient_id:'P'+(i+1),label:'Study '+i,series:[]}))})")
        expect(page.locator('tbody tr')).to_have_count(25)
        page.get_by_role('button', name='Next', exact=True).click()
        expect(page.locator('tbody tr')).to_have_count(25)
        page.get_by_role('button', name='Next', exact=True).click()
        expect(page.locator('tbody tr')).to_have_count(1)
        page.get_by_label('Patient', exact=True).fill('P1')
        expect(page.locator('tbody tr')).to_have_count(1)
        expect(page.locator('tbody tr').first).to_contain_text('Study 0')
        page.get_by_label('Patient', exact=True).fill('nonexistent')
        expect(page.locator('tbody tr')).to_have_count(0)
        expect(page.get_by_text('No studies match this patient.', exact=False)).to_be_visible()
        page.get_by_role('button', name='All patients', exact=True).click()
        expect(page.locator('tbody tr')).to_have_count(25)
        page.route('http://imaging.test/local-viewer/datasets/demo/folder', lambda r: r.fulfill(
            json={'studies': 2, 'instances': 12, 'patients': 1}))
        page.evaluate("ui.renderDicomStudies({studies:[],link_datasets:[{id:'demo',name:'Synthetic demo'}]})")
        expect(page.get_by_role('button', name='Link DICOM folder', exact=True)).to_have_count(0)
        page.evaluate('''async () => {
          const {createDatasetsUi} = await import('/static/js/datasets_ui.js');
          const host = document.createElement('div'); host.id='admin'; document.body.append(host);
          window.datasetsUi = createDatasetsUi({refs:{datasetAdminListEl:host},
            state:{availableDatasets:[{dataset_id:'demo',name:'Synthetic demo'}],datasetAdminFeedback:{},authUsers:[]},
            helpers:{escapeHtml:s=>String(s)},callbacks:{canManageDataset:()=>true}});
          datasetsUi.renderDatasetAdminList();
        }''')
        page.locator('[data-dataset-admin-card] summary').click()
        imaging_setup = page.get_by_role('region', name='Imaging', exact=True)
        expect(imaging_setup.locator('svg')).to_have_count(1)
        expect(imaging_setup).to_contain_text('Connect existing DICOM files; files stay in place.')
        imaging_setup.get_by_role('button', name='Link folder…', exact=True).click()
        expect(page.get_by_role('option', name='Synthetic demo')).to_have_count(1)
        page.get_by_placeholder('Absolute folder path').fill('/tmp/synthetic-dicom')
        page.get_by_role('button', name='Validate and link', exact=True).click()
        expect(page.locator('dialog [role=status]')).to_contain_text('Linked 2 studies, 12 instances and 1 patients.')
        page.get_by_role('button', name='Done', exact=True).click()
        expect(page.locator('dialog')).to_have_count(0)
        browser.close()
