import React from 'react';
import { createRoot } from 'react-dom/client';

const icons = {
  job: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),
  summary: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 6h8"></path>
      <path d="M8 12h8"></path>
      <path d="M8 18h5"></path>
      <rect x="4" y="3" width="16" height="18" rx="2"></rect>
    </svg>
  ),
  response: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path>
      <circle cx="12" cy="12" r="2.5"></circle>
    </svg>
  ),
  provider: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 10V7a4 4 0 1 1 8 0v3"></path>
      <rect x="5" y="10" width="14" height="10" rx="2"></rect>
      <path d="M12 14v2"></path>
    </svg>
  ),
  planner: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3v6"></path>
      <path d="M9 6h6"></path>
      <path d="M5 13a7 7 0 1 0 14 0"></path>
      <path d="m9 13 2 2 4-4"></path>
    </svg>
  ),
  deterministic: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m5 12 4 4L19 6"></path>
    </svg>
  ),
  llm: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 9h8"></path>
      <path d="M8 13h5"></path>
      <path d="M6 4h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-4 4v-4H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path>
    </svg>
  ),
  blocked: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="9"></circle>
      <path d="m8.5 8.5 7 7"></path>
      <path d="m15.5 8.5-7 7"></path>
    </svg>
  ),
  unavailable: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="9"></circle>
      <path d="M12 8v5"></path>
      <path d="M12 16h.01"></path>
    </svg>
  ),
  no_context: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <ellipse cx="12" cy="6" rx="7" ry="3"></ellipse>
      <path d="M5 6v6c0 1.7 3.1 3 7 3 1.1 0 2.1-.1 3-.3"></path>
      <path d="m5 4 14 16"></path>
    </svg>
  ),
};
export function QueryProvenance({
  items = [],
  className = 'query-thread-turn-meta',
  analysis = false,
}) {
  return (
    <div className={className}>
      {items.map((item, index) => (
        <span
          key={index}
          className={`query-chip badge ${analysis ? 'analysis-badge' : 'provenance-badge'}`}
          title={item.title || undefined}
        >
          {item.iconKind && (
            <span
              className={analysis ? 'analysis-badge-icon' : 'provenance-badge-icon'}
              aria-hidden="true"
            >
              {icons[item.iconKind] || icons.summary}
            </span>
          )}
          <span>{item.label}</span>
        </span>
      ))}
    </div>
  );
}
export function createProvenanceView(host, analysis = false) {
  if (!host) return { render() {} };
  const root = createRoot(host);
  return {
    render: (items) =>
      root.render(<QueryProvenance items={items} className="" analysis={analysis} />),
  };
}
