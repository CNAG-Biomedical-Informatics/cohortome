import React from 'react';
export function Rail({ onNavigate, accountOpen, onAccountToggle, avatarRef }) {
  return (
    <>
      <button
        id="dashboardTabBtn"
        onClick={() => onNavigate?.('dashboard')}
        className="tab-btn app-nav-parent active"
        type="button"
        aria-current="page"
        aria-expanded="true"
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
            <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
          </svg>
        </span>
        <span>Dashboard</span>
      </button>
      <button
        id="datasetsTabBtn"
        onClick={() => onNavigate?.('datasets')}
        className="tab-btn"
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
            <ellipse cx="12" cy="5" rx="7" ry="3"></ellipse>
            <path d="M5 5v6c0 1.66 3.13 3 7 3s7-1.34 7-3V5"></path>
            <path d="M5 11v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6"></path>
          </svg>
        </span>
        <span>Datasets</span>
      </button>
      <button
        id="cohortsTabBtn"
        onClick={() => onNavigate?.('cohorts')}
        className="tab-btn"
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
            <circle cx="9" cy="7" r="3" />
            <path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3" />
          </svg>
        </span>
        <span>Cohorts</span>
      </button>
      <button
        id="queryTabBtn"
        onClick={() => onNavigate?.('query')}
        className="tab-btn"
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
            <path d="M4 4h16v12H9l-5 4Z"></path>
          </svg>
        </span>
        <span>Query</span>
      </button>
      <button
        id="analysisTabBtn"
        onClick={() => onNavigate?.('analysis')}
        className="tab-btn"
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
            <path d="M3 3v18h18"></path>
            <path d="M18 17V9"></path>
            <path d="M13 17V5"></path>
            <path d="M8 17v-3"></path>
          </svg>
        </span>
        <span>Analysis</span>
      </button>
      <button
        id="phenoTabBtn"
        onClick={() => onNavigate?.('pheno')}
        className="tab-btn"
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
            <circle cx="6" cy="6" r="3"></circle>
            <circle cx="18" cy="8" r="3"></circle>
            <circle cx="10" cy="19" r="3"></circle>
            <path d="m9 6 6 1M7 9l2 7m7-5-4 6"></path>
          </svg>
        </span>
        <span>Pheno-Ranker</span>
      </button>
      <button
        id="analysisChatsDrawerBtn"
        type="button"
        className="app-sidebar-settings"
        aria-label="Show chats"
        title="Show chats"
      >
        <span className="button-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
        </span>
      </button>
      <div id="deploymentBrand" className="deployment-brand" hidden />
      <button
        id="accountMenuButton"
        ref={avatarRef}
        onClick={onAccountToggle}
        type="button"
        aria-label="Open account menu"
        aria-expanded={!!accountOpen}
        aria-controls="accountMenu"
      >
        <span id="accountAvatar" className="account-avatar" aria-hidden="true">
          LU
        </span>
      </button>
    </>
  );
}
