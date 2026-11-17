import React from 'react';
import {ClarID} from './clarid.jsx';
import {decodeIdentity,displayIdentity} from '../../static/js/identities.js';

export function QueryTable({model}) {
  if(!model) return null;
  const {payload,page,patients=[],navigation:n={}}=model;
  const data=payload.data || {}, sample=payload.action_context?.id_type==='sample';
  const rows=page.rows.length ? page.rows : (sample ? page.sampleIds : page.patientIds).map(id=>sample ? {sample_id:id} : {patient_id:id});
  if(!rows.length) {
    const type=Array.isArray(data.medications) && data.medications.length ? 'medication' : Array.isArray(data.diseases) && data.diseases.length ? 'disease' : null;
    if(!type) return null;
    const items=data[type==='medication' ? 'medications' : 'diseases'], label=type==='medication' ? 'Medication' : 'Disease';
    return <><div className="section-note">{label} inventory ({items.length}).</div><table><thead><tr><th>{label}</th><th>Patients</th></tr></thead><tbody>{items.slice(0,100).map((item,i)=><tr key={i}><td>{String(item[type] || '')}</td><td>{String(item.patient_count ?? '')}</td></tr>)}</tbody></table></>;
  }
  const byId=new Map(patients.map(p=>[String(p.patient_id),p])), bySample=new Map();
  patients.forEach(p=>(p.original_record_ids || []).forEach(id=>{const key=String(id);bySample.set(key,bySample.has(key) ? null : p);}));
  const showDataset=rows.some(item=>decodeIdentity(item.patient_id || item.sample_id || item.record_id));
  const offset=Math.max(0,Number(n.start || 0)), count=Math.max(rows.length,page.returnedCount);
  const start=count ? offset+1 : 0, end=Math.min(page.totalCount || offset+count,offset+count), total=page.totalCount || end;
  const loading=!!n.loading, terminal=!!n.terminal, sortBy=String(n.sortBy || ''), direction=String(n.sortDirection || 'asc');
  const columns=sample ? [['sample_id','Sample'],['subject_clarid','Subject ClarID']] : [['patient_id','Patient'],['subject_clarid','ClarID'],...(showDataset ? [['dataset_names','Dataset']] : []),['sex','Sex'],['visit_count','Visits'],['medication_count','Medications']];
  return <>
    {page.resultHandle || terminal ? <><div className="query-result-pagination" aria-live="polite"><span className="query-result-range">Showing {start}–{end} of {total}</span><span className="query-result-boundary-note">{terminal ? 'This bounded page remains visible, but the server-side result is no longer active.' : 'Only this page is kept in the browser.'}</span><span className="query-result-page-actions">
      {page.resultHandle && !terminal && ['tsv','csv','json'].map(format=><button key={format} type="button" className="query-chip" data-query-export={format} data-query-export-handle={page.resultHandle} data-query-export-sort={sortBy} data-query-export-direction={direction} title={format==='json' ? 'Download metadata for this query result' : 'Download all matching rows in the selected order, not just this page'}>{format==='json' ? 'Metadata JSON' : `Export all · ${format.toUpperCase()}`}</button>)}
      {page.resultHandle && n.previous?.length>0 && <button type="button" className="query-chip query-chip-deterministic" data-query-page-action="previous" disabled={loading}>Previous</button>}
      {page.resultHandle && page.hasMore && page.nextCursor && <button type="button" className="query-chip query-chip-deterministic" data-query-page-action="next" disabled={loading}>{loading ? 'Loading…' : 'Load more'}</button>}
    </span></div>{n.error && <div className="query-result-page-error" role="status">{String(n.error).trim()}</div>}</> : <div className="section-note">Matching {sample ? 'samples' : 'patients'} ({total}).</div>}
    <div className="query-result-table-scroll"><table className="query-result-table"><thead><tr>{columns.map(([key,label])=>{
      const sortable=page.resultHandle && !terminal, selected=sortBy===key;
      return <th key={key} aria-sort={sortable ? selected ? direction==='asc' ? 'ascending' : 'descending' : 'none' : undefined}>{sortable ? <button type="button" className="query-sort-button" data-query-sort={key} disabled={loading} title={`Sort all results by ${label}`}>{label}{selected ? direction==='asc' ? ' ↑' : ' ↓' : ' ↕'}</button> : label}</th>;
    })}</tr></thead><tbody>{rows.slice(0,50).map((item,index)=>{
      const id=sample ? item.sample_id || item.record_id || page.sampleIds[index] || '' : item.patient_id || page.patientIds[index] || '';
      const patient=(sample ? bySample : byId).get(String(id)), clarid=patient?.clarid;
      return <tr key={`${id}:${index}`}><td className="query-result-id-cell">{displayIdentity(id,sample)}</td><td>{clarid?.human_id && clarid.stub_id ? <ClarID clarid={clarid} compact={true}/> : <span className="section-note">Not available</span>}</td>{!sample && <>{showDataset && <td>{decodeIdentity(item.patient_id)?.datasetId || (patient?.dataset_names || []).join(', ') || 'n/a'}</td>}<td>{String(item.sex || '')}</td><td>{String(item.visit_count ?? '')}</td><td>{String(item.medication_count ?? '')}</td></>}</tr>;
    })}</tbody></table></div>
  </>;
}
