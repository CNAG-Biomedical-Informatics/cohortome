import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';

function Provider({provider:p, feedback={}, expand, onEdit}) {
  const initial = () => ({label:p.label || p.id || 'Provider',base_url:p.base_url || '', model:p.model || '',
    timeout_seconds:Number(p.timeout_seconds) || 30,data_boundary:p.data_boundary === 'local' ? 'local' : 'external',enabled:p.enabled !== false});
  const [draft,setDraft] = useState(initial);
  const details = useRef(null), key = useRef(null);
  useEffect(()=>{setDraft(initial()); if(key.current) key.current.value='';},[p]);
  useEffect(()=>{if(expand && details.current) details.current.open=true;},[expand]);
  const update = (name,value) => {setDraft(old=>({...old,[name]:value})); onEdit(p.id);};
  const field = name => ({'data-lm-provider-field':name,value:draft[name],onChange:event=>update(name,event.target.value)});
  const action = name => ({'data-lm-provider-action':name,'data-lm-provider':p.id});
  const enabled = p.enabled !== false, status=p.status || (enabled ? 'unknown' : 'disabled');
  const statusClass = !enabled ? '' : p.available ? ' dataset-picker-tag-ready' : status === 'no_model' ? ' dataset-picker-tag-warning' : ' dataset-picker-tag-danger';
  const source = p.managed ? 'In-app' : p.source === 'environment' ? 'Environment' : 'Server config';
  const boundary = p.data_boundary === 'local' ? 'local' : 'external';
  const resolved = p.resolved_model || p.model || '';
  return <details ref={details} className="dataset-admin-card" data-lm-provider-card={p.id}>
    <summary className="dataset-admin-summary"><span className="dataset-admin-summary-main"><span className="dataset-picker-title">{p.label || p.id || 'Provider'}</span><div className="dataset-picker-meta"><span className={'dataset-picker-tag'+statusClass}>{enabled ? status : 'disabled'}</span><span className="dataset-picker-tag">{boundary} boundary</span><span className="dataset-picker-tag">{source}</span><span className="dataset-picker-tag">{p.id}</span>{resolved && <span className="dataset-picker-tag">{resolved}</span>}{p.api_key_configured && <span className="dataset-picker-tag">API key stored</span>}</div></span></summary>
    <div className="dataset-admin-body"><div className="dataset-picker-description">{p.base_url}</div>
      {p.model && p.model !== resolved && <div className="section-note">Configured model: {p.model}</div>}
      <div className="section-note">{boundary === 'local' ? 'May receive private dataset context when that dataset explicitly allows it.' : 'Never receives context from private datasets.'}</div>
      {p.detail && <div className="section-note">{p.detail}</div>}
      {p.managed ? <><div className="query-grid query-grid-compact">
        <div><label>Display name<input type="text" {...field('label')}/></label></div>
        <div><label>Provider ID<input type="text" value={p.id} disabled/></label></div>
        <div className="query-grid-span-2"><label>Base URL<input type="url" {...field('base_url')}/></label></div>
        <div><label>Model ID<input type="text" {...field('model')} placeholder="Discover from provider"/></label></div>
        <div><label>Timeout (seconds)<input type="number" {...field('timeout_seconds')} min="1" max="300" step="1"/></label></div>
        <div><label>Data boundary<select {...field('data_boundary')}><option value="external">External</option><option value="local">Local</option></select></label></div>
        <div><label>Replace API key<input ref={key} type="password" data-lm-provider-field="api_key" autoComplete="new-password" onChange={()=>onEdit(p.id)} placeholder={p.api_key_configured ? 'Stored; leave blank to keep' : 'Optional for local providers'}/></label></div>
      </div><div className="query-row" style={{marginTop:12}}>
        <label className="dataset-picker-check"><input type="checkbox" data-lm-provider-field="enabled" checked={draft.enabled} onChange={event=>update('enabled',event.target.checked)}/><span>Enabled</span></label>
        <button type="button" className="query-chip" {...action('test')}>Test connection</button>
        <button type="button" className="query-chip query-chip-deterministic" {...action('save')} disabled={feedback.saving}>{feedback.saving ? 'Saving…' : 'Save'}</button>
        <span className="section-note" data-lm-provider-save-status role="status" aria-live="polite">{feedback.message || ''}</span>
        {p.id !== 'system-default' && <button type="button" className="query-chip danger-btn" {...action('delete')}>Delete</button>}
      </div></> : <><div className="section-note">Managed by {source.toLowerCase()} configuration and read-only here. Change its deployment configuration, then restart the server.</div><div className="query-row" style={{marginTop:12}}><button type="button" className="query-chip" {...action('test')}>Test connection</button></div></>}
    </div>
  </details>;
}
export function createModelsAdminView(host, onEdit) {
  const root=createRoot(host);
  return {render(providers,feedback,expandId='',message='No model providers configured.') {
    root.render(providers.length ? providers.map(p=><Provider key={p.id} provider={p} feedback={feedback.get(p.id)} expand={p.id===expandId} onEdit={onEdit}/>) : <div className="empty">{message}</div>);
  }};
}
