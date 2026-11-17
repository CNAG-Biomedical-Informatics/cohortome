import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

export function createStorageSettingsView(host) {
  const root=createRoot(host);
  return {render(m) {
    flushSync(()=>root.render(<>
      <h4>Dataset storage</h4><label htmlFor="resourceStorageDirectory">Folder for new imports</label>
      <input id="resourceStorageDirectory" type="text" spellCheck={false} autoComplete="off" value={m.directory} disabled={m.busy} onChange={e=>m.onChange(e.target.value)}/>
      <button id="resourceStorageBrowse" type="button" className="query-chip" hidden={!m.canBrowse} disabled={m.busy} onClick={m.onBrowse}>Choose folder…</button>
      <button id="resourceStorageSave" type="button" className="query-chip" disabled={m.busy} onClick={m.onSave}>Save storage folder</button>
      <p id="resourceStorageStatus" role="status" className="section-note">{m.status}</p>
      <details className="view-help"><summary>What changes?</summary><p>New downloads and imports only. Existing datasets and query-store caches stay in place. On web this is a server path; Docker requires a persistent volume.</p></details>
    </>));
  }};
}

export function createExportSettingsView(host) {
  const root=createRoot(host);
  return {render(m) {
    flushSync(()=>root.render(<>
      <h4>Export limits</h4><p className="section-note">Applies to all users of this installation. Exports use RAM; memory use can exceed file size, especially with simultaneous downloads.</p>
      <div className="user-settings-grid">{[
        ['source_mib','exportSourceMib','Per source file (MiB)',2048],
        ['total_source_mib','exportTotalMib','Combined source files (MiB)',4096],
        ['output_mib','exportOutputMib','Exported content (MiB)',1024],
      ].map(([key,id,label,max])=><div key={key}><label htmlFor={id}>{label}</label><input id={id} type="number" min="1" max={max} step="1" value={m.values[key] ?? ''} disabled={m.busy} onChange={e=>m.onChange(key,e.target.value)}/></div>)}</div>
      <button id="exportLimitsSave" type="button" className="query-chip" disabled={m.busy} onClick={m.onSave}>Save export limits</button>
      <button id="exportLimitsDefaults" type="button" className="query-chip" disabled={m.busy} onClick={m.onDefaults}>Use defaults</button>
      <p id="exportLimitsStatus" role="status" className="section-note">{m.status}</p>
    </>));
  }};
}
