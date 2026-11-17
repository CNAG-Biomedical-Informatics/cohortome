import {createRoot} from 'react-dom/client';
import {useLayoutEffect, useRef} from 'react';
import {PatientInventory} from './patient-inventory.jsx';

function Inspector({model:m}) {
  const host = useRef(null);
  useLayoutEffect(() => {host.current.scrollIntoView({block:'nearest'});},[m.ticket]);
  return <div ref={host} className="workspace-card"><h3>{m.label}</h3><p>{m.patient.events?.length || 0} clinical records · {m.patient.samples?.length || 0} linked assay entries</p>
    {m.event && <><h4>{m.event.title}</h4><p>{m.timeLabel}</p></>}
    {m.event?.diagnosis && <p>{m.event.diagnosis}</p>}
    {(m.event?.domains || []).map((domain,i) => <p key={i}><strong>{domain.label || domain.key}:</strong> {(domain.examples || []).join(', ')}</p>)}
    <h4>Clinical data, samples &amp; assays</h4><div data-patient-inventory=""><PatientInventory rows={m.patient.samples || []} records={m.records} subjectClarid={m.clarid} expandFirst={m.event?.modality === 'clinical'}/></div>
    <p data-clinical-status="" className="section-note" role="status">{m.status}</p>
    {m.event?.modality === 'clinical' && <button type="button" className="query-chip" data-clinical-all="" onClick={m.all}>All clinical timepoints</button>}
    <button type="button" className="query-chip" data-clinical-more="" hidden={!m.hasMore} disabled={m.loading || !m.hasMore} onClick={m.more}>{m.failed ? 'Retry clinical records' : 'Load more records'}</button>
  </div>;
}
export function createPatientInspectorView(host) {
  let root;
  return {render(model) {root ||= createRoot(host); root.render(<Inspector key={model.ticket} model={model}/>);}, reset() {root?.unmount(); root = null;}};
}
