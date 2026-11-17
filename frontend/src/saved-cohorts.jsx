import React, {useLayoutEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal} from 'react-dom';

function Icon({name}) {
  const path={
    download:'M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5',
    inspect:'M3 10h18M9 10v10',
    'clinical-summary':'M4 3v17h17M8 16v-4M13 16V7M18 16v-7',
    'load-analysis':'M4 3v17h17M8 16v-4M13 16V7M18 16v-7',
    'load-datasets':'M3 7h7l2 2h9v11H3ZM3 7V4h7l2 3h8v2',
    rename:'m16 3 5 5-12 12H4v-5ZM14 5l5 5',
    delete:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  };
  return <span className="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {path[name] && <path d={path[name]}/>}{name==='inspect' && <rect x="3" y="4" width="18" height="16" rx="2"/>}
    {name==='cohort' && <><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3"/></>}
    {name==='load-pheno' && <><circle cx="5" cy="6" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="10" cy="19" r="3"/><path d="m8 6 7 1M6 9l3 7m7-6-4 6"/></>}
    {name==='more' && [5,12,19].map(x=><circle key={x} cx={x} cy="12" r="1"/>)}
  </svg></span>;
}
function Action({item,action,children,disabled=false,icons=false,className='',title}) {
  return <button type="button" className={`query-chip ${action==='delete' ? 'danger-btn' : ''} ${className}`} data-saved-cohort-id={item.id} data-saved-cohort-action={action} disabled={disabled} title={title}>{(icons || action.startsWith('export')) && <Icon name={action.startsWith('export') ? 'download' : action}/>} {children}</button>;
}
function Exports({item}) {
  return <><Action item={item} action="export-clinical">Export clinical data</Action><Action item={item} action="export-molecular">Export molecular data</Action><Action item={item} action="export" title="Membership TSV and metadata JSON only; no clinical records or assay matrices">Export membership</Action></>;
}
function SavedCohorts({items,mode,notice}) {
  return <>{notice && <div className="saved-cohort-inline-status">{notice}</div>}{!items.length ? <div className="empty">No saved cohorts yet.</div> : <div className="saved-cohort-list">{items.map(item=><div className="saved-cohort-card" key={item.id}>
    <strong>{item.name || 'Unnamed cohort'}</strong><small>{item.patientCount} patients • {item.sampleCount} samples • source: {item.source?.kind || 'manual'}</small>
    {!!item.datasetLabels.length && <small>{item.datasetLabels.join(', ')}</small>}<small>{item.preview}</small>
    <div className="saved-cohort-actions"><Action item={item} action="clinical-summary">Apply to scope</Action><Action item={item} action={mode==='pheno' ? 'load-pheno' : 'load-analysis'} className="action">{mode==='pheno' ? 'Use in Pheno-Ranker' : 'Use as Cohort A'}</Action>{mode==='analysis' && <Action item={item} action="load-analysis-b" className="action">Use as Cohort B</Action>}<Action item={item} action="copy">Copy IDs</Action><Action item={item} action="rename">Rename</Action><Exports item={item}/>
      {item.active && <span className="query-chip badge" title="Detach this cohort from the current Analysis or Pheno state before deleting it here.">In use here</span>}
      <Action item={item} action="delete" disabled={item.active} title={item.active ? 'Detach this cohort from the current Analysis or Pheno state before deleting it here.' : undefined}>Delete</Action>
    </div></div>)}</div>}</>;
}
export function createSavedCohortsView(host) {
  const root=createRoot(host); return {render(model){root.render(<SavedCohorts {...model}/>);}};
}
export function createCohortReferencesView(host) {
  const root=createRoot(host); return {render(items){root.render(items.length ? <div className="saved-cohort-actions"><span className="query-chip badge">Separate references</span>{items.map(item=><button key={item.id} type="button" className="query-chip query-chip-deterministic" data-pheno-selected-cohort-id={item.id}>{item.name || 'Unnamed cohort'} ×</button>)}</div> : 'No saved cohorts attached as separate references.');}};
}
function LibraryCard({item}) {
  const date=new Date(item.created_at);
  return <article className="cohort-library-card"><div className="cohort-card-top"><span className="cohort-card-symbol"><Icon name="cohort"/></span><span className={`cohort-card-state ${item.available ? 'is-loaded' : ''}`}>{item.available ? 'Datasets loaded' : 'Datasets not loaded'}</span><details className="cohort-card-menu cohort-card-manage"><summary aria-label={`Manage ${item.name}`} title="Manage cohort"><Icon name="more"/></summary><div className="cohort-card-menu-items"><Action item={item} action="rename" icons>Rename</Action><Action item={item} action="delete" icons>Delete</Action></div></details></div>
    <h3>{item.name}</h3><div className="cohort-library-datasets">{item.labels.map((label,i)=><span key={i}>{label}</span>)}</div>
    <dl className="cohort-card-counts"><div><dt>Patients</dt><dd>{Number(item.patient_count || 0).toLocaleString()}</dd></div><div><dt>Samples</dt><dd>{Number(item.sample_count || 0).toLocaleString()}</dd></div></dl>
    <div className="cohort-card-actions saved-cohort-actions"><Action item={item} action="inspect" icons>Members</Action><Action item={item} action="clinical-summary" icons disabled={!item.available}>Apply to scope</Action><details className="cohort-card-menu cohort-library-more"><summary><Icon name="download"/>Export</summary><div className="cohort-card-menu-items"><Exports item={item}/></div></details></div>
    <div className="cohort-card-footer"><small>Created {Number.isNaN(date.getTime()) ? 'date unavailable' : date.toLocaleDateString()}</small><div className="saved-cohort-actions">{item.available ? <><span className="cohort-card-use-label">Use in</span><Action item={item} action="load-analysis" icons>Analysis</Action><Action item={item} action="load-pheno" icons>Pheno-Ranker</Action></> : <Action item={item} action="load-datasets" icons>Add required datasets</Action>}</div></div>
  </article>;
}
export function createCohortLibraryView(host,pages,suggestions) {
  const root=createRoot(host);
  return {render(m){root.render(<>
    {m.items.length ? <div className="cohort-library-grid">{m.items.map(item=><LibraryCard key={item.id} item={item}/>)}</div> : <div className="empty">{m.hasItems ? 'No cohorts match your search.' : 'No accessible saved cohorts. Save a patient or sample selection to create one.'}</div>}
    {suggestions && createPortal(m.suggestions.map(item=><option key={item.id} value={item.name} label={item.labels.join(' · ')}/>),suggestions)}
    {pages && createPortal(m.total>m.pageSize ? <><button type="button" className="query-chip" data-page="-1" disabled={m.page===0}>Previous</button><span>{m.page*m.pageSize+1}–{Math.min(m.total,(m.page+1)*m.pageSize)} of {m.total}</span><button type="button" className="query-chip" data-page="1" disabled={(m.page+1)*m.pageSize>=m.total}>Next</button></> : null,pages)}
  </>);}};
}
function NameForm({dialog,defaultName,rename,setResult}) {
  const input=useRef(null);
  useLayoutEffect(()=>{dialog.showModal();input.current.focus();input.current.select();},[]);
  return <form onSubmit={event=>{event.preventDefault();const name=input.current.value.trim();if(!name){input.current.setCustomValidity('Enter a cohort name.');input.current.reportValidity();return;}setResult(name);dialog.close();}}><h3 id="cohortNameTitle">{rename ? 'Rename cohort' : 'Save cohort'}</h3><label htmlFor="cohortNameInput">Cohort name</label><input ref={input} id="cohortNameInput" type="text" required autoComplete="off" defaultValue={defaultName} onInput={()=>input.current.setCustomValidity('')}/><div className="chat-move-actions"><button type="button" className="secondary-btn" data-cohort-name-cancel onClick={()=>dialog.close()}>Cancel</button><button type="submit" className="primary-btn">{rename ? 'Rename' : 'Save cohort'}</button></div></form>;
}
export function requestCohortName(defaultName,rename=false) {
  return new Promise(resolve=>{
    const dialog=document.createElement('dialog');dialog.id='cohortNameDialog';dialog.className='chat-move-dialog';dialog.setAttribute('aria-labelledby','cohortNameTitle');document.body.append(dialog);
    const root=createRoot(dialog);let result=null;
    dialog.addEventListener('close',()=>{root.unmount();dialog.remove();resolve(result);},{once:true});
    root.render(<NameForm dialog={dialog} defaultName={defaultName} rename={rename} setResult={value=>{result=value;}}/>);
  });
}
function Members({item,labels,dialog}) {
  const [offset,setOffset]=useState(0), members=item.members || [];
  useLayoutEffect(()=>{dialog.showModal();},[]);
  return <><h3 id="cohortMembersTitle">{item.name}</h3><div className="cohort-members-table"><table className="assay-table"><thead><tr><th>Dataset</th><th>Patient ID</th><th>Sample ID</th></tr></thead><tbody>{members.slice(offset,offset+50).map((m,i)=><tr key={offset+i}><td>{labels([m.dataset_id])[0] || m.dataset_id}</td><td>{m.patient_id}</td><td>{m.sample_id || '—'}</td></tr>)}</tbody></table></div><div className="saved-cohort-actions"><button type="button" className="query-chip" data-prev disabled={!offset} onClick={()=>setOffset(offset-50)}>Previous</button><span role="status">{members.length ? `${offset+1}–${Math.min(offset+50,members.length)} of ${members.length}` : 'No members'}</span><button type="button" className="query-chip" data-next disabled={offset+50>=members.length} onClick={()=>setOffset(offset+50)}>Next</button><button type="button" className="query-chip" data-close onClick={()=>dialog.close()}>Close</button></div></>;
}
export function inspectCohortMembers(item,labels) {
  document.getElementById('cohortMembersDialog')?.close();
  const dialog=document.createElement('dialog');dialog.id='cohortMembersDialog';dialog.className='chat-move-dialog cohort-members-dialog';dialog.setAttribute('aria-labelledby','cohortMembersTitle');document.body.append(dialog);
  const root=createRoot(dialog);dialog.addEventListener('close',()=>{root.unmount();dialog.remove();},{once:true});
  root.render(<Members item={item} labels={labels} dialog={dialog}/>);
}
