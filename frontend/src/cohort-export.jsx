import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

export function createMolecularExportView(host) {
  const root=createRoot(host);
  return {destroy:()=>root.unmount(),render:m=>flushSync(()=>root.render(<>
    <h3 id="cohortExportTitle">Export molecular data</h3><p className="cohort-export-scope">{m.scope}</p>
    <div className="cohort-export-assays">{m.items.map((item,index)=><label key={item.key || index} className="cohort-export-option">
      <input type="checkbox" value={index} checked={m.selected.includes(index)} disabled={m.busy || !item.available} onChange={e=>m.onSelect(index,e.target.checked)}/>
      <span><strong>{item.label}</strong><small>{item.dataset_id} · {item.data_type || 'Unknown measurement type'}</small><small>{item.available ? `${item.patient_count} patients · ${item.sample_count} samples · ${(item.source_bytes / 1048576).toFixed(1)} MiB source` : item.reason}</small></span>
    </label>)}</div>
    <details className="view-help"><summary>Contents and limits</summary>
      <p>ZIP with feature-by-sample TSV matrices, patient–sample links, and a manifest. Values are not normalized, rounded, or imputed. Clinical records, raw sequencing files, images, and additional sample covariates are not included.</p>
      <p>Limits: 64 MiB per source, 128 MiB total sources, 32 MiB exported content, and 100,000 feature rows across up to 32 assays. Source size is not the final download size. Large matrices require a separate export workflow.</p>
      <p>Import matrices with R or Python. Treat all downloads as research data; permission to use data is not permission to redistribute it.</p>
    </details><p role="status">{m.status}</p>
    <div className="saved-cohort-actions"><button type="button" data-download disabled={m.downloadDisabled} onClick={m.onDownload}><svg className="button-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5"/></svg>Download ZIP</button><button type="button" data-close disabled={m.busy} onClick={m.onClose}>Close</button></div>
  </>))};
}
