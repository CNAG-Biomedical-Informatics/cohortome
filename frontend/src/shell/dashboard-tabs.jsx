import React from 'react';
export function DashboardTabs({ onNavigate }) {
  return (
    <div className="dashboard-subtabs app-sidebar-subnav dashboard-page-tabs">
      <div className="dashboard-view-group" role="group" aria-labelledby="dashboardExploreLabel">
        <span id="dashboardExploreLabel" className="dashboard-view-group-label">
          Explore data
        </span>
        <div className="dashboard-view-buttons">
          <button
            id="dashboardClinicalBtn"
            onClick={() => onNavigate?.('clinical')}
            type="button"
            className="dashboard-subtab active"
          >
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 3h6"></path>
                <path d="M8 5h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"></path>
                <path d="M9 10h6"></path>
                <path d="M9 14h6"></path>
              </svg>
            </span>
            <span>Clinical</span>
          </button>
          <button
            id="dashboardTimelineBtn"
            onClick={() => onNavigate?.('timeline')}
            type="button"
            className="dashboard-subtab"
          >
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M4 6h16M4 12h16M4 18h16" />
                <circle cx="8" cy="6" r="2" />
                <circle cx="16" cy="12" r="2" />
                <circle cx="11" cy="18" r="2" />
              </svg>
            </span>
            <span>Timeline</span>
          </button>
          <button
            id="dashboardAssaysBtn"
            onClick={() => onNavigate?.('assays')}
            type="button"
            className="dashboard-subtab"
          >
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M7 3c0 4 3 4 3 8s-3 4-3 8"></path>
                <path d="M17 3c0 4-3 4-3 8s3 4 3 8"></path>
                <path d="M8 6h8"></path>
                <path d="M8 18h8"></path>
              </svg>
            </span>
            <span>Assays</span>
          </button>
          <button
            id="dashboardImagingBtn"
            onClick={() => onNavigate?.('imaging')}
            type="button"
            className="dashboard-subtab"
          >
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="3" y="3" width="18" height="18" rx="3"></rect>
                <circle cx="12" cy="12" r="5"></circle>
                <path d="M12 9v6M9 12h6"></path>
              </svg>
            </span>
            <span>Imaging</span>
          </button>
        </div>
      </div>
      <div className="dashboard-view-group" role="group" aria-labelledby="dashboardBuildLabel">
        <span id="dashboardBuildLabel" className="dashboard-view-group-label">
          Build a cohort
        </span>
        <div className="dashboard-view-buttons">
          <button
            id="dashboardPatientsBtn"
            onClick={() => onNavigate?.('patients')}
            type="button"
            className="dashboard-subtab"
          >
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="7" r="4" />
                <path d="M4 21v-3a8 8 0 0 1 16 0v3" />
              </svg>
            </span>
            <span>Patients</span>
          </button>
          <button
            id="dashboardMultimodalBtn"
            onClick={() => onNavigate?.('multimodal')}
            type="button"
            className="dashboard-subtab"
          >
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m12 3 9 5-9 5-9-5 9-5Z"></path>
                <path d="m3 12 9 5 9-5M3 16l9 5 9-5"></path>
              </svg>
            </span>
            <span>Multimodal</span>
          </button>
        </div>
      </div>
    </div>
  );
}
