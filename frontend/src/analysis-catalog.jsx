import React from 'react';
import {createRoot} from 'react-dom/client';
import {ModalityIcon} from './assay-overview.jsx';

function Icon({kind}) {
  const paths={clinical:'M12 5v14M5 12h14',compare:'M8 7h8M8 17h8m-10-8 2-2 2 2m8 6-2 2-2-2',trajectory:'M4 18h16m-15-3 4-4 3 2 7-7',survival:'M4 19V5M4 19h16M6 7l4 5 3-3 5 6',assay:'M7 3c0 4 3 4 3 8s-3 4-3 8M17 3c0 4-3 4-3 8s3 4 3 8M8 6h8M8 18h8',external:'M14 5h5v5M10 14l9-9M19 14v5H5V5h5',general:'M8 8h8M8 12h8M8 16h5',queue:'M8 6h11M8 12h11M8 18h11m-15-12 0 .01m0 5.99 0 .01m0 5.99 0 .01'};
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{kind==='general' && <rect x="4" y="4" width="16" height="16" rx="3"/>}<path d={paths[kind] || paths.general}/></svg>;
}
function Card({model:m,compact,drawer}) {
  const {item,availability:a,setupState:s}=m;
  return <article className={`analysis-catalog-card${compact ? ' is-compact' : ''}${drawer ? ' is-drawer' : ''}${a.available ? '' : ' is-disabled'}${s.ready ? ' is-ready' : ' is-needs-setup'}${m.selected ? ' is-selected' : ''}`}>
    <div className="analysis-catalog-head"><div className="analysis-catalog-icon" aria-hidden="true"><Icon kind={m.iconKind}/></div><div><div className="analysis-catalog-title">{item.name || 'Curated analysis'}</div><div className="analysis-catalog-meta">{m.badges.map((b,i)=><span key={i} className={`query-chip badge ${b.css || ''}`}>{b.modality && <span className="analysis-badge-icon"><ModalityIcon modality={b.modality}/></span>}{b.queue && <Icon kind="queue"/>}{b.label}</span>)}</div></div></div>
    <div className="analysis-catalog-description">{item.description || ''}</div>
    {!compact && !!item.workspace_requirements?.length && <div className="section-note">{item.workspace_requirements.join(' ')}</div>}
    {!compact && item.guidance && <div className="section-note">{item.guidance}</div>}
    {!compact && !!item.tags?.length && <div className="analysis-catalog-tags">{item.tags.map((tag,i)=><span key={i} className="query-chip badge">{tag}</span>)}</div>}
    {!a.available && <div className="analysis-catalog-unavailable">{a.unavailableReason || 'Unavailable in this workspace.'}</div>}
    <div className={`analysis-catalog-readiness ${s.ready ? 'is-ready' : 'is-blocked'}`}><strong>{a.available ? s.ready ? 'Ready now' : 'Needs setup' : 'Unavailable'}</strong>{s.message && <> <span>{s.message}</span></>}</div>
    <div className="analysis-catalog-actions"><button type="button" className="query-chip action" data-analysis-catalog-id={item.id || ''} disabled={!a.available}>{a.available ? s.ready ? 'Use analysis' : 'Set up' : 'Unavailable'}</button></div>
  </article>;
}
export function createAnalysisCatalogView(host,{compact=false,drawer=false}={}) {
  const root=createRoot(host);
  return {render({groups=[],message=''}) {
    root.render(message ? <div className="empty">{message}</div> : groups.map(g=>{
      const ready=g.label==='Ready now';
      return <section key={g.label} className={`analysis-catalog-group${g.items.length ? '' : ' analysis-catalog-group-empty'} ${ready ? 'is-ready' : 'is-needs-setup'}`}><div className="analysis-catalog-group-header"><div><div className="analysis-catalog-group-label">{g.label}</div><div className="analysis-catalog-group-note">{ready ? 'Can run with the current scope and inputs.' : 'Needs one or more inputs before it can run.'}</div></div><span className="analysis-catalog-group-count">{g.items.length}</span></div>{g.items.length ? <div className={`analysis-catalog-grid${compact ? ' analysis-catalog-grid-compact' : ''}`}>{g.items.map(m=><Card key={m.item.id} model={m} compact={compact} drawer={drawer}/>)}</div> : <div className="empty">{ready ? 'No analyses are ready with the current selection.' : 'No analyses need setup in this view.'}</div>}</section>;
    }));
  }};
}
export function createAnalysisChecklistView(host) {
  const root=createRoot(host);return {render(steps) {
    const first=steps.findIndex(s=>!s.complete);
    root.render(steps.map((s,i)=>{const current=i===first;return <div key={s.key} className={`analysis-setup-check ${s.complete ? 'is-complete' : current ? 'is-current' : 'is-waiting'}`} data-analysis-setup-step={s.key}><span className="analysis-setup-check-index" aria-hidden="true">{s.complete ? '✓' : i+1}</span><span className="analysis-setup-check-copy"><strong>{s.label}</strong><small>{s.detail}</small></span><span className="analysis-setup-check-state">{s.complete ? 'Done' : current ? 'Next' : 'Waiting'}</span>{current && s.action && <button type="button" className="query-chip action" data-analysis-setup-action={s.action}>{s.actionLabel || 'Continue'}</button>}</div>;}));
  }};
}
