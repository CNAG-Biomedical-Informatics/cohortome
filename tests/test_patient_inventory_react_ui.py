from playwright.sync_api import expect

from test_ui_smoke import live_server, page


def test_patient_inventory_groups_visits_and_keeps_clarid_entity(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.evaluate('''async () => {
      const {createPatientInspectorView} = await import('/static/js/react/ui.js');
      const host = document.createElement('div'); host.id = 'inventoryTest'; document.body.append(host);
      window.inventoryView = createPatientInspectorView(host);
      window.inventoryModel = {ticket:1, patient:{events:[], samples:['10','2','1'].map(n => ({
        sample_id:'S'+n, visit:'visit_'+n, modality:'proteomics', assay:'Protein panel',
        biosample_id:'specimen-'+n, biosample_clarid:{entity:'biosample', subject_id:41,
          human_id:'shared', stub_id:'shared-stub', tissue:'Blood', condition_name:'<script>', condition:'C22.0'}}))},
        records:['10','2','1'].map(n => ({visit_id:'visit_'+n, record:{info:{}, measures:[{
          assayCode:{id:'TEST:1',label:'Example'}, measurementValue:{quantity:{value:0,unit:{label:'mg/L'}}}}]}})),
        clarid:{human_id:'subject-label',stub_id:'subject-stub',subject_id:41}, label:'Example patient',
        status:'3 records', hasMore:false, all:()=>{}, more:()=>{}};
      inventoryView.render(inventoryModel);
    }''')
    host = page.locator('#inventoryTest')
    expect(host.locator('[data-visit]')).to_have_count(3)
    assert host.locator('[data-visit]').evaluate_all('(els) => els.map(el => el.dataset.visit)') == ['visit_1', 'visit_2', 'visit_10']
    assert host.locator('[data-clinical-index]').evaluate_all('(els) => els.map(el => el.dataset.clinicalIndex)') == ['2', '1', '0']
    expect(host.locator('[data-clarid-toggle]')).to_have_count(6)
    expect(host.locator('script')).to_have_count(0)
    assert 'ClarID subject 41' in host.text_content()
    assert '<script>' in host.text_content()
    host.locator('.clinical-record').first.locator('summary').first.click()
    expect(host.locator('.clinical-measures').first).to_contain_text('0')
    page.evaluate('inventoryView.render({...inventoryModel, status:"Updated status"})')
    expect(host.locator('.clinical-record').first).to_have_attribute('open', '')
    page.evaluate('''() => inventoryView.render({...inventoryModel, ticket:2,
      patient:{samples:[{sample_id:'no-visit',collection_date:'2026-01-01'},
        {sample_id:'same-sample',visit:'V2'}, {sample_id:'same-sample',visit:'V1'}]},
      records:[{visit_id:'V1',event_date:'2026-01-01',record:{}}]})''')
    expect(host.locator('[data-visit]')).to_have_count(3)
    assert host.locator('[data-visit]').evaluate_all('(els) => els.map(el => el.dataset.visit)') == ['V1','V2','']
    expect(host.get_by_text('same-sample', exact=True)).to_have_count(2)
    assert not errors
