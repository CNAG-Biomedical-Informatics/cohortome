import React from 'react';

export function JobsDrawer() {
  return (
    <div id="jobsDrawer" className="jobs-drawer is-hidden" aria-hidden="true">
      <div className="jobs-drawer-backdrop" data-jobs-drawer-close="true"></div>
      <div
        className="jobs-drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="jobsDrawerTitle"
      >
        <div className="jobs-drawer-header">
          <div>
            <strong id="jobsDrawerTitle">Queue</strong>
            <div className="section-note">
              Background runs that are waiting, running, or recently finished.
            </div>
          </div>
          <button
            id="jobsDrawerCloseBtn"
            type="button"
            className="job-card-action-icon"
            title="Close queue"
            aria-label="Close queue"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18"></path>
              <path d="m6 6 12 12"></path>
            </svg>
          </button>
        </div>
        <div
          id="jobsWorkerStatus"
          className="background-worker-status is-checking"
          role="status"
          aria-live="polite"
        >
          Checking background workers…
        </div>
        <div id="jobsDrawerStatus" className="query-status">
          Loading queue...
        </div>
        <div id="jobsDrawerList" className="jobs-drawer-list">
          <div className="empty">Loading queue...</div>
        </div>
      </div>
    </div>
  );
}

export function RunHistoryDrawer() {
  return (
    <div id="runHistoryDrawer" className="jobs-drawer is-hidden" aria-hidden="true">
      <div className="jobs-drawer-backdrop" data-run-history-drawer-close="true"></div>
      <div
        className="jobs-drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="runHistoryDrawerTitle"
      >
        <div className="jobs-drawer-header">
          <div>
            <strong id="runHistoryDrawerTitle">Run History</strong>
            <div className="section-note">
              Generated results from Analysis, Pheno-Ranker, and workflow tools.
            </div>
          </div>
          <div className="job-card-actions">
            <button
              id="runHistoryDeleteAllBtn"
              type="button"
              className="job-card-action-icon danger"
              title="Delete completed runs"
              aria-label="Delete completed runs"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M3 6h18"></path>
                <path d="M8 6V4h8v2"></path>
                <path d="M19 6l-1 14H6L5 6"></path>
                <path d="M10 11v5"></path>
                <path d="M14 11v5"></path>
              </svg>
            </button>
            <button
              id="runHistoryDrawerCloseBtn"
              type="button"
              className="job-card-action-icon"
              title="Close run history"
              aria-label="Close run history"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M18 6 6 18"></path>
                <path d="m6 6 12 12"></path>
              </svg>
            </button>
          </div>
        </div>
        <div
          id="runHistoryWorkerStatus"
          className="background-worker-status is-checking"
          role="status"
          aria-live="polite"
        >
          Checking background workers…
        </div>
        <div id="runHistoryDrawerStatus" className="query-status">
          Loading run history...
        </div>
        <div id="runHistoryDrawerList" className="jobs-drawer-list">
          <div className="empty">Loading run history...</div>
        </div>
      </div>
    </div>
  );
}
