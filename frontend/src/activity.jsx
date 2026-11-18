import React from 'react';
import { createRoot } from 'react-dom/client';

export function Activity({ label = 'Working', detail = 'Working on your request.' }) {
  return (
    <div className="analysis-pending-card">
      <div className="analysis-turn-meta">
        <span className="query-chip badge">pending</span>
        <span className="query-chip badge">{label || 'Working'}</span>
      </div>
      <div className="analysis-pending-row">
        <div className="analysis-thinking-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <span>{detail || 'Working on your request.'}</span>
      </div>
    </div>
  );
}

export function createPlanPreviewView(host) {
  const root = createRoot(host);
  return { render: (m) => root.render(m.activity ? <Activity {...m.activity} /> : m.text || '') };
}
