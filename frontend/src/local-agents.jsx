import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal, flushSync} from 'react-dom';

export function createLocalAgentsView(host) {
  const root=createRoot(host);
  return {render(m){flushSync(()=>root.render(<>
    <summary>Agent access (MCP) <span id="localAgentsBadge" className="local-agents-badge" data-active={String(m.active)}>{m.badge}</span></summary>
    <p className="section-note">Explore the two included synthetic demos; approve analysis requests here. Access ends after eight hours or when you close the app. <a href="https://cnag-biomedical-informatics.github.io/cohortome/docs/user-guide/local-agents" target="_blank" rel="noopener noreferrer">Connector setup</a></p>
    <p id="localAgentsStatus" className="section-note" role="status">{m.status}</p><p id="localAgentsScope" className="section-note">{m.scope}</p>
    <label className="user-settings-check"><input id="localAgentsConsent" type="checkbox" checked={m.consent} disabled={m.busy} onChange={e=>m.onConsent(e.target.checked)}/> I allow the agent to read this data. A local connection does not guarantee local processing; results may be sent to a cloud model.</label>
    <div className="user-settings-actions"><button id="localAgentsShare" type="button" className="primary-btn" disabled={m.shareDisabled} onClick={m.onShare}>{m.active ? 'Update shared selection' : 'Enable and share scope'}</button><button id="localAgentsRevoke" type="button" className="danger-btn" hidden={m.hideRevoke} disabled={m.busy} onClick={m.onRevoke}>Turn off</button></div>
    <div id="localAgentsSecret" hidden={!m.configuration}>
      <label htmlFor="localAgentsFormat">Client configuration</label><select id="localAgentsFormat" value={m.format} disabled={m.formatDisabled} onChange={e=>m.onFormat(e.target.value)}><option value="toml">Codex (TOML)</option><option value="json">Other clients (JSON)</option></select>
      <label htmlFor="localAgentsConfiguration">Connection settings · keep the token private</label><textarea id="localAgentsConfiguration" rows={5} readOnly spellCheck={false} autoComplete="off" aria-describedby="localAgentsSecretHelp" value={m.configuration}/>
      <p id="localAgentsSecretHelp" className="section-note">{m.help}</p><div className="user-settings-actions"><button id="localAgentsCopy" type="button" className="secondary-btn" onClick={m.onCopy}>Copy connection settings</button></div>
    </div><p id="localAgentsMessage" className="section-note" role="status" aria-live="polite">{m.message}</p>
    <div id="localAgentsPlans"/>
  </>));}};
}
function Plan({plan,busy,message,onDecide}) {
  const [allowResults,setAllowResults]=useState(false);
  const counts=plan.validated_inputs || {};
  return <section className="agent-run-plan"><strong>{plan.analysis}</strong><p>{plan.dataset_id} · {plan.assay_id}</p>
    <p>Cohort A: {plan.cohort_a_patient_count} patients, {counts.cohort_a_sample_count ?? 'unknown'} usable samples. Cohort B: {plan.cohort_b_patient_count} patients, {counts.cohort_b_sample_count ?? 'unknown'} usable samples.</p>
    <p>{counts.data_type || 'Source scale'} · {counts.feature_count ?? counts.gene_count ?? 'Unknown'} features. Covariates: {(counts.analysis_covariates || []).join(', ') || 'none'}.</p>
    <details><summary>Review patient IDs</summary><p>A: {(plan.cohort_a || []).join(', ')}</p><p>B: {(plan.cohort_b || []).join(', ')}</p></details>
    <label className="user-settings-check"><input type="checkbox" checked={allowResults} disabled={busy} onChange={e=>setAllowResults(e.target.checked)}/> Also allow this agent to read feature-level result tables. Its model may process them externally.</label>
    <div className="user-settings-actions"><button type="button" className="primary-btn" disabled={busy} onClick={()=>onDecide(plan,true,allowResults)}>Approve and run</button><button type="button" className="secondary-btn" disabled={busy} onClick={()=>onDecide(plan,false,false)}>Reject</button></div><p className="section-note" role="status">{message}</p>
  </section>;
}
export function createAgentPlansView(host) {
  const root=createRoot(host);
  return {render(m){root.render(<>{m.error ? <p className="section-note">{m.error}</p> : <>{m.plans.length>0 && <h4>Analysis requests awaiting your approval</h4>}{m.plans.map(plan=><Plan key={`${plan.plan_id}:${m.revision}`} plan={plan} busy={m.busy} message={m.messages[plan.plan_id] || ''} onDecide={m.onDecide}/>)}</>}{m.notice && createPortal(<div className="job-completion-notice"><span>MCP: {m.plans.length} analysis request(s) need your approval.</span><button type="button" onClick={m.onReview}>Review requests</button></div>,document.body)}</>);}};
}
