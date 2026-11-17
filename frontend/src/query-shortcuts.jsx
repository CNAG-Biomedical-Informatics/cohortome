import React from 'react';
import {createRoot} from 'react-dom/client';

export function createQueryShortcutsView(host) {
  if (!host) return {render(){}};
  const root = createRoot(host);
  return {render(diseases, prompt) {
    root.render(diseases.slice(0, 8).map(item => {
      const disease = String(item.disease || '').trim();
      return <button key={disease} type="button" className={`query-chip query-chip-deterministic${prompt.includes(disease.toLowerCase()) ? ' is-active-chip' : ''}`} data-query-disease-chip={disease}>{disease} <span className="query-chip badge">{Number(item.patient_count || 0)}</span></button>;
    }));
  }};
}
