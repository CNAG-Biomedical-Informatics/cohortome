import React from 'react';
export function AccountMenu({ helpUrl, name, onNavigate }) {
  return (
    <>
      <div className="app-sidebar-account">
        <div className="account-copy">
          <strong id="heroAuthIdentity">Signed out</strong>
        </div>
      </div>
      <button
        id="userSettingsBtn"
        type="button"
        className="app-sidebar-settings"
        title="Open user settings."
      >
        <span className="button-icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5z"></path>
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.04.04a2 2 0 0 1-2.83 2.83l-.04-.04a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.04 1.56V21a2 2 0 0 1-4 0v-.08A1.7 1.7 0 0 0 8.96 19.36a1.7 1.7 0 0 0-1.87.34l-.04.04a2 2 0 1 1-2.83-2.83l.04-.04A1.7 1.7 0 0 0 4.6 15 1.7 1.7 0 0 0 3 14H3a2 2 0 0 1 0-4h.08A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.04-.04a2 2 0 1 1 2.83-2.83l.04.04A1.7 1.7 0 0 0 8.96 4.64 1.7 1.7 0 0 0 10 3.08V3a2 2 0 0 1 4 0v.08a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.87-.34l.04-.04a2 2 0 0 1 2.83 2.83l-.04.04A1.7 1.7 0 0 0 19.4 9 1.7 1.7 0 0 0 21 10h.08a2 2 0 0 1 0 4H21a1.7 1.7 0 0 0-1.6 1z"></path>
          </svg>
        </span>
        <span>Settings</span>
      </button>
      <div className="app-nav-group">
        <button
          id="adminTabBtn"
          onClick={() => onNavigate?.('admin')}
          className="tab-btn app-nav-parent is-hidden"
          type="button"
          aria-expanded="false"
        >
          <span className="tab-btn-icon" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Z"></path>
              <path d="m9 12 2 2 4-4"></path>
            </svg>
          </span>
          <span>Admin</span>
        </button>
        <div className="admin-subtabs app-sidebar-subnav">
          <button
            id="dataTabBtn"
            onClick={() => onNavigate?.('data')}
            className="dashboard-subtab is-hidden"
            type="button"
          >
            <span className="tab-btn-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 3v12m-5-5 5 5 5-5M5 21h14" />
              </svg>
            </span>
            <span>Data</span>
          </button>
          <button
            id="usersTabBtn"
            onClick={() => onNavigate?.('users')}
            className="dashboard-subtab is-hidden"
            type="button"
          >
            <span className="tab-btn-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
                <circle cx="9" cy="7" r="4"></circle>
                <path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
              </svg>
            </span>
            <span>Users</span>
          </button>
          <button
            id="modelsTabBtn"
            onClick={() => onNavigate?.('models')}
            className="dashboard-subtab is-hidden"
            type="button"
          >
            <span className="tab-btn-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 3v4"></path>
                <path d="M12 17v4"></path>
                <path d="M3 12h4"></path>
                <path d="M17 12h4"></path>
                <circle cx="12" cy="12" r="5"></circle>
                <path d="M8.5 8.5 6 6"></path>
                <path d="m18 18-2.5-2.5"></path>
              </svg>
            </span>
            <span>Models</span>
          </button>
          <button
            id="deploymentAppearanceBtn"
            className="dashboard-subtab is-hidden"
            type="button"
            aria-haspopup="dialog"
          >
            <span className="tab-btn-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="3" y="3" width="18" height="18" rx="3" />
                <circle cx="8" cy="8" r="1.5" />
                <path d="m3 17 6-6 4 4 3-3 5 5" />
              </svg>
            </span>
            <span>Appearance</span>
          </button>
        </div>
      </div>
      <a
        className="app-sidebar-settings app-sidebar-help"
        href={helpUrl}
        target="_blank"
        rel="noopener noreferrer"
        title={`Open ${name} documentation.`}
      >
        <span className="button-icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"></path>
            <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"></path>
            <path d="M8 6h8"></path>
            <path d="M8 10h8"></path>
          </svg>
        </span>
        <span>Help</span>
      </a>
      <button id="heroLogoutBtn" type="button" className="account-signout is-hidden">
        Sign out
      </button>
    </>
  );
}
