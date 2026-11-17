import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

function FolderForm({datasets,desktop,canBrowse,onBrowse,onSubmit,onClose,busy,message,done}) {
  const [dataset,setDataset]=useState(datasets[0]?.id || '');
  const [directory,setDirectory]=useState('');
  return <form onSubmit={event=>{event.preventDefault();onSubmit(dataset,directory.trim());}}>
    <h3>Link DICOM files</h3>
    <label>Dataset<select name="dataset" value={dataset} disabled={busy || done} onChange={e=>setDataset(e.target.value)}>{datasets.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
    <label>{desktop ? 'Local folder' : 'Folder on the server'}<input name="directory" required autoComplete="off" placeholder="Absolute folder path" value={directory} disabled={busy || done} onChange={e=>setDirectory(e.target.value)}/></label>
    <button type="button" className="query-chip" data-browse hidden={!canBrowse} disabled={busy || done} onClick={()=>onBrowse(setDirectory)}>Choose folder…</button>
    <p>Files stay in this folder. DICOM PatientID must match a patient ID in this dataset. Linking replaces its previous folder links; no images are copied or deleted.</p>
    <p>COHORTome does not anonymize or certify these files. Only link data you are permitted to use.</p>
    <div role="status" aria-live="polite">{message}</div>
    <div className="dicom-folder-actions"><button type="button" className="query-chip" data-cancel disabled={busy} onClick={onClose}>{done ? 'Done' : 'Cancel'}</button><button type="submit" className="query-chip" disabled={busy || !dataset} hidden={done}>Validate and link</button></div>
  </form>;
}
export function createDicomFolderView(host) {
  const root=createRoot(host);
  return {render:model=>flushSync(()=>root.render(<FolderForm {...model}/>)),destroy:()=>root.unmount()};
}
