from playwright.sync_api import expect

from test_ui_smoke import live_server, page


def test_run_cards_preserve_expansion_and_scope_actions(page):
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.evaluate('''async () => {
      const {createJobsView} = await import('/static/js/react/ui.js');
      const host=document.createElement('div'); host.id='jobsTest'; document.body.append(host);
      window.jobsTest=createJobsView(host);
      window.jobExample={job_id:'example',name:'Example <script>',status:'completed',dataset_id:'demo',
        feature:'pheno',result_available:true,execution_backend:'job',
        started_at:'2026-01-01T00:00:00Z',completed_at:'2026-01-01T00:01:15Z',
        artifacts:[{name:'table.tsv',url:'/results/example/table.tsv'},{name:'Unsafe',url:'javascript:alert(1)'}]};
      window.jobModel={surface:'run-history',workspace:'demo',groups:[{title:'Completed',items:[jobExample]}]};
      jobsTest.render(jobModel);
    }''')
    card=page.locator('#jobsTest .job-card')
    expect(card).to_contain_text('1m 15s')
    expect(card).to_contain_text('Background')
    expect(card.locator('script')).to_have_count(0)
    expect(card.locator('[data-job-open-pheno]')).to_have_count(1)
    expect(card.locator('[data-run-history-delete]')).to_have_count(1)
    card.locator('summary').click()
    expect(card.locator('a')).to_have_count(1)
    card.evaluate('(el)=>window.originalJobCard=el')
    page.evaluate('jobsTest.render({...jobModel,workspace:"different"})')
    expect(card.locator('details')).to_have_attribute('open','')
    assert card.evaluate('(el)=>el===window.originalJobCard')
    expect(card.locator('[data-job-open-pheno]')).to_have_count(0)
    expect(card).to_contain_text('Load the original workspace')
    assert not errors
