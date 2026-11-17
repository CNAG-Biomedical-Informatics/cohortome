import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

export function createMeasurementView(host,onChange) {
  const root=createRoot(host);
  return {render({options,value,loading,detail}) {
    flushSync(()=>root.render(<><label htmlFor="analysisMeasurement">Clinical measurement</label><select id="analysisMeasurement" value={value} disabled={loading} onChange={e=>onChange(e.target.value)}><option value="">Choose a measurement…</option>{options.map(entry=><option key={entry.measure} value={entry.measure}>{entry.measure}{entry.units.filter(Boolean).length ? ` (${entry.units.filter(Boolean).join(' / ')})` : ''}</option>)}</select><p className="section-note" aria-live="polite">{detail}</p></>));
  }};
}
