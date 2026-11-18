import React from 'react';
export function Metrics({ kind, items = [] }) {
  return (
    <div
      className="metrics-grid"
      data-analysis-summary={kind}
      data-methylation-summary={kind}
      style={{ gridColumn: '1 / -1', marginBottom: 0 }}
    >
      {items.map((item, index) => (
        <div key={index} className="metric-card">
          <span>{item.label || 'Metric'}</span>
          <strong>{String(item.value ?? 'n/a')}</strong>
        </div>
      ))}
    </div>
  );
}

export function ImagePreview({ artifact, alt, empty }) {
  return artifact ? (
    <div className="analysis-artifact-image-frame">
      <img className="analysis-artifact-image" src={artifact.url || ''} alt={alt} />
    </div>
  ) : (
    <div className="empty">{empty}</div>
  );
}

export function Card({ title, children, ...props }) {
  return (
    <div className="viz-card" style={{ gridColumn: '1 / -1' }} {...props}>
      {title && <h3>{title}</h3>}
      {children}
    </div>
  );
}

export function Notes({ items }) {
  return items.filter(Boolean).map((note, index) => (
    <p key={index} className="section-note">
      {note}
    </p>
  ));
}
