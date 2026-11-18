from playwright.sync_api import expect
from test_ui_smoke import live_server, page


def test_result_hosts_persist_within_chat_but_reset_for_other_chats(page):
    page.evaluate('''async () => {
      const {createAnalysisThreadView}=await import('/static/js/react/ui.js');
      const host=document.createElement('div');host.id='resultLifecycle';document.body.append(host);
      window.resultView=createAnalysisThreadView(host);
      window.resultTurn={latest:true,badges:[],contextParts:[],followups:[],provenance:[],
        reply:{text:'Example'},data:{artifacts:[]},visuals:{turnIndex:0,context:{},scientific:{
          kind:'expression',context:{},metrics:[],downloads:[],isLimmaVoom:true,
          volcanoArtifact:{url:'/example.tsv'}}}};
      resultView.render([resultTurn],'first');
      window.originalPlot=host.querySelector('.analysis-plot-frame');
      host.querySelector('[data-de-view-panel="interactive"]').dataset.loaded='true';
      resultView.render([{...resultTurn,reply:{text:'Updated explanation'}}],'first');
    }''')
    assert page.evaluate('originalPlot === document.querySelector("#resultLifecycle .analysis-plot-frame")')
    panel = page.locator('#resultLifecycle [data-de-view-panel="interactive"]')
    expect(panel).to_have_attribute('data-loaded', 'true')
    page.evaluate("resultView.render([resultTurn],'second')")
    assert page.evaluate('!originalPlot.isConnected')
    assert panel.get_attribute('data-loaded') is None
    page.evaluate('''() => {
      window.secondPlot=document.querySelector('#resultLifecycle .analysis-plot-frame');
      resultView.render([{...resultTurn,data:{artifacts:[{name:'volcano_points.tsv',url:'/new.tsv'}]}}],'second');
    }''')
    assert page.evaluate('!secondPlot.isConnected')
