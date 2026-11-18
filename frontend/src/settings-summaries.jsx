import React from 'react';
import { createRoot } from 'react-dom/client';

export function createAuthSummaryView(host) {
  if (!host) return { render() {} };
  const root = createRoot(host);
  return {
    render(rows) {
      root.render(
        <>
          <strong>Authentication</strong>
          <div className="user-settings-auth-grid">
            {rows.map(([label, value]) => (
              <React.Fragment key={label}>
                <div className="user-settings-auth-label">{label}</div>
                <div className="user-settings-auth-value">{value}</div>
              </React.Fragment>
            ))}
          </div>
          <div className="section-note">
            Dataset access is managed by COHORTome roles and groups.
          </div>
        </>,
      );
    },
  };
}
