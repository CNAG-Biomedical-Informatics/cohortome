import {Activity} from './activity.jsx';
import React from 'react';
import {createRoot} from 'react-dom/client';

function Reasoning({model}) {
  const plan=model.plan;
  const scope=typeof plan?.selected_patient_ids==='string' ? plan.selected_patient_ids.split(',').filter(s=>s.trim()) : Array.isArray(plan?.selected_patient_ids) ? plan.selected_patient_ids.filter(Boolean) : [];
  return <>{model.warning && <div className="planner-warning"><strong>{model.warning.title}</strong>{model.warning.detail && <div>{model.warning.detail}</div>}{model.warning.issues?.length>0 && <ul className="mini-list">{model.warning.issues.map((issue,i)=><li key={i}>{issue}</li>)}</ul>}</div>}{!model.warningOnly && <>{plan && <div className="pheno-plan-chip-row"><span className="pheno-plan-chip pheno-plan-chip-action">{plan.action==='extract' ? 'Extract' : 'Compare'}</span><span className={`pheno-plan-chip pheno-plan-chip-${plan.mode==='patient' ? 'patient' : 'cohort'}`}>{plan.mode==='patient' ? 'Patient mode' : 'Cohort mode'}</span>{plan.invalid_patient_id ? <span className="pheno-plan-chip pheno-plan-chip-invalid">Invalid target: {plan.invalid_patient_id}</span> : plan.patient_id && <span className="pheno-plan-chip pheno-plan-chip-target">Target: {plan.patient_id}</span>}{scope.length>0 && <span className="pheno-plan-chip pheno-plan-chip-scope">Scope: {scope.length} ID{scope.length===1 ? '' : 's'}</span>}</div>}{model.lines?.length ? <ul className="mini-list">{model.lines.map((line,i)=><li key={i}>{line}</li>)}</ul> : <div className="empty">No planner reasoning yet.</div>}</>}</>;
}
export function createPhenoPlanningView(host) {
  const root=createRoot(host);
  let model={};
  const draw=()=>root.render(model.activity ? <Activity {...model.activity}/> : <Reasoning model={model}/>);
  return {render(next){model=next;draw();},warn(warning,warningOnly=false){model={...model,warning,warningOnly};draw();}};
}
export function createPhenoFollowupsView(host) {
  if(!host) return {render(){}};
  const root=createRoot(host);
  return {render({suggestions=[],llmPlanned=false}={}) {
    host.classList.toggle('is-hidden',!suggestions.length);
    const label=llmPlanned ? 'LLM-planned' : 'Deterministic';
    const title=llmPlanned ? 'This follow-up was suggested by the LLM planner. Clicking prepares it for review and does not run it.' : 'This follow-up is supported by deterministic Pheno-Ranker planning. Clicking prepares it for review and does not run it.';
    root.render(suggestions.length ? <><div className="query-followups-label">Suggested follow-up questions</div><div className="query-followups-list">{suggestions.map(prompt=><button key={prompt} type="button" className={`query-chip ${llmPlanned ? 'query-chip-planner' : 'query-chip-deterministic'}`} data-pheno-followup-prompt={prompt} data-followup-execution-mode={llmPlanned ? 'llm_planned' : 'deterministic'} title={title} aria-label={`${prompt}. ${label} planning; prepares the prompt without running it.`}><span>{prompt}</span><span className="followup-mode-label">{label}</span></button>)}</div></> : null);
  }};
}
