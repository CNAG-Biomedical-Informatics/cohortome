import React from 'react';
import {createRoot} from 'react-dom/client';

function duration(item) {
  const start=Date.parse(item.started_at || ''), end=Date.parse(item.completed_at || '');
  if (!Number.isFinite(start) || !Number.isFinite(end) || end<=start) return '';
  const total=Math.max(1,Math.round((end-start)/1000));
  if(total<60) return `${total}s`;
  const hours=Math.floor(total/3600), minutes=Math.floor(total%3600/60), seconds=total%60;
  return `${hours ? hours+'h ' : ''}${minutes}m${seconds ? ' '+seconds+'s' : ''}`;
}
function Action({attribute,id,label,icon}) {
  const paths = {
    open:'M14 3h7v7M10 14 21 3M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5',
    pheno:'M7 7h10v10H7zM4 12h3M17 12h3M12 4v3M12 17v3M9 10h6M9 14h6',
    delete:'M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5',
  };
  return <button type="button" className={`job-card-action-icon ${icon === 'delete' ? 'danger' : 'action'}`} {...{[attribute]:id}} aria-label={label} title={label}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[icon]}/></svg></button>;
}
function artifactUrl(value) {
  try {const url=new URL(value,window.location.href); return ['http:','https:'].includes(url.protocol) ? url.href : null;} catch {return null;}
}
function JobCard({item,surface,workspace}) {
  const status=String(item.status || 'queued').trim(), feature=String(item.feature || '').trim();
  const terminal=['completed','failed','cancelled'].includes(status);
  const known=['queued','running','completed','failed','cancelled'].includes(status);
  const background=item.execution_backend === 'job' || !!String(item.rq_job_id || '').trim();
  const matches=String(workspace || '').trim() === String(item.dataset_id || '').trim();
  const open=item.result_available && (feature === 'analysis' || (feature === 'pheno' && matches));
  const files=(item.artifacts || []).filter(a=>a.name && a.url && artifactUrl(a.url));
  const meta=[item.job_code,item.dataset_id && `dataset ${item.dataset_id}`,item.assay_id && `assay ${item.assay_id}`,item.analysis_session_title].filter(Boolean).join(' · ');
  const elapsed=duration(item);
  return <article className="job-card"><div className="job-card-topline"><div className="job-card-badges"><span className={`job-status-chip ${known ? 'is-'+status : ''}`}>{status}</span>{surface === 'run-history' && <span className={`job-execution-chip ${background ? 'is-background' : 'is-direct'}`}>{background ? 'Background' : 'Direct'}</span>}</div><span className="job-card-time">{item.submitted_at || 'Submitted just now'}{elapsed && ` · ${elapsed}`}</span></div>
    <div className="job-card-header"><div className="job-card-title"><strong>{item.name || 'Generated run'}</strong><div className="job-card-subtitle">{meta}</div></div></div>
    {item.prompt && <div className="job-card-prompt">{item.prompt}</div>}{item.reply_preview && <div className="job-card-preview">{item.reply_preview}</div>}
    {item.result_available && feature === 'pheno' && !matches && <div className="job-card-preview">Load the original workspace to reopen this Pheno-Ranker run.</div>}
    {item.error && <div className="job-card-error">{item.error}</div>}
    {(open || terminal || !!files.length) && <div className="job-card-footer">{(open || terminal) && <div className="job-card-actions">
      {open && <Action attribute={feature === 'pheno' ? 'data-job-open-pheno' : 'data-job-open-result'} id={item.job_id} label={feature === 'pheno' ? 'Open in Pheno-Ranker' : 'Open result'} icon={feature === 'pheno' ? 'pheno' : 'open'}/>}
      {terminal && <Action attribute={surface === 'run-history' ? 'data-run-history-delete' : 'data-job-delete'} id={item.job_id} label="Delete generated run" icon="delete"/>}
    </div>}{!!files.length && <details className="job-card-artifacts"><summary>Result files</summary><div className="job-card-artifact-links">{files.map((a,i)=><a key={a.url+':'+i} className="query-chip" href={artifactUrl(a.url)} target="_blank" rel="noopener">{a.name}</a>)}</div></details>}</div>}
  </article>;
}
export function createJobsView(host) {
  const root=createRoot(host);
  return {render({groups=[],surface='jobs',workspace='',message=''}) {
    root.render(message ? <div className="empty">{message}</div> : groups.filter(g=>g.items.length).map(g=><section key={g.title} className="job-group"><div className="job-group-title">{g.title}</div><div className="job-group-list">{g.items.map(item=><JobCard key={item.job_id} item={item} surface={surface} workspace={workspace}/>)}</div></section>));
  }};
}
