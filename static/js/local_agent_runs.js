import {createAgentPlansView} from './react/ui.js';

// Owner-only decisions. MCP tokens cannot reach these management routes.
export function createAgentRunApprovals({onMessage = () => {}} = {}) {
  const host = document.getElementById('localAgentsPlans');
  if (!host) return;
  const view = createAgentPlansView(host);
  let signature = '', busy = false, polling = false, stopped = false;
  let plans = [], messages = {}, error = '', notice = false, revision = 0;
  function render() {
    view.render({plans, messages, error, notice, revision, busy, onDecide:decide,
      onReview:() => {
        notice = false;
        render();
        window.dispatchEvent(new CustomEvent('cohortome:review-agent-plans'));
      }});
  }
  async function decide(plan, approve, allowResults) {
    if (busy || stopped) return;
    busy = true;
    messages = {...messages, [plan.plan_id]:approve ? 'Validating and submitting…' : 'Rejecting request…'};
    render();
    try {
      const reply = await fetch('/local-agent/plans/' + encodeURIComponent(plan.plan_id), {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({approve, allow_results:approve && allowResults})});
      const result = await reply.json();
      if (!reply.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Unable to process this request.');
      signature = '';
      window.dispatchEvent(new CustomEvent('cohortome:mcp-run', {detail:result}));
      onMessage(result.status === 'submitted'
        ? 'Approved run submitted. It appears in Analysis chats, Jobs and Run history. Your current workspace is unchanged.'
        : result.status === 'failed' ? 'Run submission failed. Check Jobs and the MCP Analysis chat.' : 'Request rejected.');
    } catch (failure) {
      messages = {...messages, [plan.plan_id]:failure.message};
    } finally {
      busy = false;
      render();
      void refresh();
    }
  }
  async function refresh() {
    if (busy || polling || stopped) return;
    polling = true;
    try {
      const response = await fetch('/local-agent/plans', {cache:'no-store'});
      if (!response.ok) throw new Error('Unable to check MCP approvals. Reopen Settings to retry.');
      const data = await response.json();
      const next = data.plans || [];
      const key = JSON.stringify(next);
      if (key === signature || stopped) return;
      signature = key;
      plans = next;
      messages = {};
      error = '';
      revision++;
      notice = Boolean(plans.length);
      render();
    } catch (failure) {
      signature = '';
      plans = [];
      error = failure.message;
      notice = false;
      revision++;
      render();
    } finally { polling = false; }
  }
  const timer = window.setInterval(refresh, 5000);
  window.addEventListener('pagehide', () => {
    stopped = true;
    clearInterval(timer);
    notice = false;
    render();
  });
  void refresh();
}
