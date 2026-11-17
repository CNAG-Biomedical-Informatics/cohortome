import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

export function createResourceTermsView(host) {
  const root=createRoot(host);
  return {render:m=>flushSync(()=>root.render(<>
    <h3 id="resourceTermsTitle">Download from {m.resource.source_label}</h3>
    <p id="resourceTermsDescription">COHORTome will download {m.resource.name} and prepare it locally.</p>
    <p>Review the source’s usage conditions and cite the original study. Public availability does not imply unrestricted redistribution rights.</p>
    <p className="resource-terms-links"><a id="resourceTermsStudy" href={m.resource.source_page} target="_blank" rel="noopener noreferrer">{m.resource.source_label} study record</a><a id="resourceTermsPolicy" href={m.resource.source_policy_url} target="_blank" rel="noopener noreferrer">{m.resource.source_policy_label}</a></p>
    <div id="resourceTermsAdditional" className="resource-terms-links">{(m.resource.additional_source_links || []).map((link,index)=><a key={index} href={link.url} target="_blank" rel="noopener noreferrer">{link.label}</a>)}</div>
    <label className="resource-terms-check"><input id="resourceTermsCheck" type="checkbox" checked={m.checked} onChange={e=>m.onCheck(e.target.checked)}/><span id="resourceTermsStatement">{m.resource.review_statement}</span></label>
    <div className="saved-cohort-actions"><button id="resourceTermsCancel" type="button" className="query-chip" autoFocus onClick={m.onCancel}>Cancel</button><button id="resourceTermsAccept" type="button" className="query-chip" disabled={!m.checked} onClick={m.onAccept}>Download and prepare</button></div>
  </>))};
}
export function createResourceNoticeView(host) {
  const root=createRoot(host);
  return {render:m=>root.render(m ? <div className="job-completion-notice resource-completion-notice"><span role="status">{m.message}</span><button type="button" onClick={m.onView}>View import</button><button type="button" onClick={m.onDismiss}>Dismiss</button></div> : null)};
}
