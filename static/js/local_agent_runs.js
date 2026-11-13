// Owner-only decisions. MCP tokens cannot reach these management routes.
export function createAgentRunApprovals() {
  const host = document.getElementById('localAgentsPlans');
  if (!host) return;
  let signature = '', busy = false, polling = false, notice = null, stopped = false;
  const element = (tag, text, className = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    node.className = className;
    return node;
  };
  async function refresh() {
    if (busy || polling || stopped) return;
    polling = true;
    try {
      const response = await fetch('/local-agent/plans', {cache:'no-store'});
      if (!response.ok) throw new Error('Unable to check MCP approvals. Reopen Settings to retry.');
      const data = await response.json();
      const plans = data.plans || [];
      const key = JSON.stringify(plans);
      if (key === signature) return;
      signature = key;
      host.replaceChildren();
      notice?.remove();
      if (!plans.length) return;
      host.append(element('h4', 'Analysis requests awaiting your approval'));
      for (const plan of plans) {
        const card = element('section', '', 'agent-run-plan');
        card.append(element('strong', plan.analysis));
        card.append(element('p', `${plan.dataset_id} · ${plan.assay_id}`));
        const counts = plan.validated_inputs || {};
        card.append(element('p', `Cohort A: ${plan.cohort_a_patient_count} patients, ${counts.cohort_a_sample_count ?? 'unknown'} usable samples. Cohort B: ${plan.cohort_b_patient_count} patients, ${counts.cohort_b_sample_count ?? 'unknown'} usable samples.`));
        card.append(element('p', `${counts.data_type || 'Source scale'} · ${counts.feature_count ?? counts.gene_count ?? 'Unknown'} features. Covariates: ${(counts.analysis_covariates || []).join(', ') || 'none'}.`));
        const patients = element('details', '');
        patients.append(element('summary', 'Review patient IDs'));
        patients.append(element('p', `A: ${(plan.cohort_a || []).join(', ')}`));
        patients.append(element('p', `B: ${(plan.cohort_b || []).join(', ')}`));
        card.append(patients);
        const consent = element('label', '', 'user-settings-check');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        consent.append(checkbox, document.createTextNode(' Also allow this agent to read feature-level result tables. Its model may process them externally.'));
        card.append(consent);
        const actions = element('div', '', 'user-settings-actions');
        const message = element('p', '', 'section-note');
        message.setAttribute('role', 'status');
        for (const [approve, label, style] of [[true, 'Approve and run', 'primary-btn'], [false, 'Reject', 'secondary-btn']]) {
          const button = element('button', label, style);
          button.type = 'button';
          button.addEventListener('click', async () => {
            if (busy) return;
            busy = true;
            host.querySelectorAll('button').forEach(b => b.disabled = true);
            message.textContent = approve ? 'Validating and submitting…' : 'Rejecting request…';
            try {
              const reply = await fetch(`/local-agent/plans/${encodeURIComponent(plan.plan_id)}`, {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({approve, allow_results:approve && checkbox.checked})});
              const result = await reply.json();
              if (!reply.ok) throw new Error(result.detail || 'Unable to process this request.');
              signature = '';
              window.dispatchEvent(new CustomEvent('cohortome:mcp-run', {detail:result}));
              document.getElementById('localAgentsMessage').textContent = result.status === 'submitted'
                ? 'Approved run submitted. It appears in Analysis chats, Jobs and Run history. Your current workspace is unchanged.'
                : result.status === 'failed' ? 'Run submission failed. Check Jobs and the MCP Analysis chat.' : 'Request rejected.';
            } catch (error) {
              message.textContent = error.message;
            } finally {
              busy = false;
              host.querySelectorAll('button').forEach(b => b.disabled = false);
              void refresh();
            }
          });
          actions.append(button);
        }
        card.append(actions, message);
        host.append(card);
      }
      notice = element('div', '', 'job-completion-notice');
      notice.append(element('span', `MCP: ${plans.length} analysis request(s) need your approval.`));
      const review = element('button', 'Review requests');
      review.type = 'button';
      review.onclick = () => {
        window.dispatchEvent(new CustomEvent('cohortome:review-agent-plans'));
        notice.remove();
      };
      notice.append(review);
      document.body.append(notice);
    } catch (error) {
      host.replaceChildren(element('p', error.message, 'section-note'));
      signature = '';
      notice?.remove();
    } finally { polling = false; }
  }
  const timer = window.setInterval(refresh, 5000);
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); notice?.remove(); });
  void refresh();
}
