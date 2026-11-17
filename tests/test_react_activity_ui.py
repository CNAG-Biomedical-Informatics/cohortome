from test_ui_smoke import live_server, page, playwright


def test_plan_progress_and_result_are_plain_text(page):
    page.evaluate('''async () => {
      const {createPlanPreviewView} = await import('/static/js/react/ui.js');
      const host=document.createElement('pre');host.id='planPreviewTest';document.body.append(host);
      window.previewTest=createPlanPreviewView(host);
      previewTest.render({activity:{label:'<img src=x>',detail:'<script>not code</script>'}});
    }''')
    host = page.locator('#planPreviewTest')
    playwright.expect(host).to_contain_text('<img src=x>')
    playwright.expect(host.locator('img,script')).to_have_count(0)
    playwright.expect(host.locator('.analysis-thinking-dots')).to_have_count(1)
    page.evaluate("previewTest.render({text:'{\"patient\":\"<example>\"}'})")
    playwright.expect(host).to_have_text('{"patient":"<example>"}')
    playwright.expect(host.locator('.analysis-thinking-dots')).to_have_count(0)
