import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

function Rail() {
  return <>
<button id="dashboardTabBtn" className="tab-btn app-nav-parent active" type="button" aria-current="page" aria-expanded="true">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
              <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
              <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
              <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
            </svg>
          </span>
          <span>Dashboard</span>
        </button>
<button id="datasetsTabBtn" className="tab-btn" type="button">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <ellipse cx="12" cy="5" rx="7" ry="3"></ellipse>
              <path d="M5 5v6c0 1.66 3.13 3 7 3s7-1.34 7-3V5"></path>
              <path d="M5 11v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6"></path>
            </svg>
          </span>
          <span>Datasets</span>
        </button>
<button id="cohortsTabBtn" className="tab-btn" type="button">
          <span className="tab-btn-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3"/></svg></span>
          <span>Cohorts</span>
        </button>
<button id="queryTabBtn" className="tab-btn" type="button">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 4h16v12H9l-5 4Z"></path>
            </svg>
          </span>
          <span>Query</span>
        </button>
<button id="analysisTabBtn" className="tab-btn" type="button">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v18h18"></path>
              <path d="M18 17V9"></path>
              <path d="M13 17V5"></path>
              <path d="M8 17v-3"></path>
            </svg>
          </span>
          <span>Analysis</span>
        </button>
<button id="phenoTabBtn" className="tab-btn" type="button">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="6" cy="6" r="3"></circle>
              <circle cx="18" cy="8" r="3"></circle>
              <circle cx="10" cy="19" r="3"></circle>
              <path d="m9 6 6 1M7 9l2 7m7-5-4 6"></path>
            </svg>
          </span>
          <span>Pheno-Ranker</span>
        </button>
    <button id="analysisChatsDrawerBtn" type="button" className="app-sidebar-settings" aria-label="Show chats" title="Show chats"><span className="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg></span></button>
    <div id="deploymentBrand" className="deployment-brand" hidden/>
    <button id="accountMenuButton" type="button" aria-label="Open account menu" aria-expanded="false" aria-controls="accountMenu"><span id="accountAvatar" className="account-avatar" aria-hidden="true">LU</span></button>
  </>;
}
function AccountMenu({helpUrl,name}) {
  return <>
    <div className="app-sidebar-account"><div className="account-copy"><strong id="heroAuthIdentity">Signed out</strong></div></div>
<button id="userSettingsBtn" type="button" className="app-sidebar-settings" title="Open user settings.">
              <span className="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5z"></path>
                  <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.04.04a2 2 0 0 1-2.83 2.83l-.04-.04a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.04 1.56V21a2 2 0 0 1-4 0v-.08A1.7 1.7 0 0 0 8.96 19.36a1.7 1.7 0 0 0-1.87.34l-.04.04a2 2 0 1 1-2.83-2.83l.04-.04A1.7 1.7 0 0 0 4.6 15 1.7 1.7 0 0 0 3 14H3a2 2 0 0 1 0-4h.08A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.04-.04a2 2 0 1 1 2.83-2.83l.04.04A1.7 1.7 0 0 0 8.96 4.64 1.7 1.7 0 0 0 10 3.08V3a2 2 0 0 1 4 0v.08a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.87-.34l.04-.04a2 2 0 0 1 2.83 2.83l-.04.04A1.7 1.7 0 0 0 19.4 9 1.7 1.7 0 0 0 21 10h.08a2 2 0 0 1 0 4H21a1.7 1.7 0 0 0-1.6 1z"></path>
                </svg>
              </span>
              <span>Settings</span>
            </button>
<div className="app-nav-group">
        <button id="adminTabBtn" className="tab-btn app-nav-parent is-hidden" type="button" aria-expanded="false">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Z"></path>
              <path d="m9 12 2 2 4-4"></path>
            </svg>
          </span>
          <span>Admin</span>
        </button>
        <div className="admin-subtabs app-sidebar-subnav">
        <button id="dataTabBtn" className="dashboard-subtab is-hidden" type="button">
          <span className="tab-btn-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m-5-5 5 5 5-5M5 21h14"/></svg></span>
          <span>Data</span>
        </button>
        <button id="usersTabBtn" className="dashboard-subtab is-hidden" type="button">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
              <circle cx="9" cy="7" r="4"></circle>
              <path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
            </svg>
          </span>
          <span>Users</span>
        </button>
        <button id="modelsTabBtn" className="dashboard-subtab is-hidden" type="button">
          <span className="tab-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
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
        <button id="deploymentAppearanceBtn" className="dashboard-subtab is-hidden" type="button" aria-haspopup="dialog">
          <span className="tab-btn-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/></svg></span>
          <span>Appearance</span>
        </button>
        </div>
        </div>
<a className="app-sidebar-settings app-sidebar-help" href={helpUrl} target="_blank" rel="noopener noreferrer" title={`Open ${name} documentation.`}>
              <span className="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"></path>
                  <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"></path>
                  <path d="M8 6h8"></path>
                  <path d="M8 10h8"></path>
                </svg>
              </span>
              <span>Help</span>
            </a>
<button id="heroLogoutBtn" type="button" className="account-signout is-hidden">Sign out</button>
  </>;
}
function DashboardTabs() {return <div className="dashboard-subtabs app-sidebar-subnav dashboard-page-tabs">
          <div className="dashboard-view-group" role="group" aria-labelledby="dashboardExploreLabel">
          <span id="dashboardExploreLabel" className="dashboard-view-group-label">Explore data</span>
          <div className="dashboard-view-buttons">
          <button id="dashboardClinicalBtn" type="button" className="dashboard-subtab active">
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 3h6"></path>
                <path d="M8 5h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"></path>
                <path d="M9 10h6"></path>
                <path d="M9 14h6"></path>
              </svg>
            </span>
            <span>Clinical</span>
          </button>
          <button id="dashboardTimelineBtn" type="button" className="dashboard-subtab"><span className="dashboard-subtab-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="11" cy="18" r="2"/></svg></span><span>Timeline</span></button>
          <button id="dashboardAssaysBtn" type="button" className="dashboard-subtab">
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M7 3c0 4 3 4 3 8s-3 4-3 8"></path>
                <path d="M17 3c0 4-3 4-3 8s3 4 3 8"></path>
                <path d="M8 6h8"></path>
                <path d="M8 18h8"></path>
              </svg>
            </span>
            <span>Assays</span>
          </button>
          <button id="dashboardImagingBtn" type="button" className="dashboard-subtab">
            <span className="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="18" height="18" rx="3"></rect><circle cx="12" cy="12" r="5"></circle><path d="M12 9v6M9 12h6"></path></svg></span>
            <span>Imaging</span>
          </button>
          </div></div>
          <div className="dashboard-view-group" role="group" aria-labelledby="dashboardBuildLabel">
          <span id="dashboardBuildLabel" className="dashboard-view-group-label">Build a cohort</span>
          <div className="dashboard-view-buttons">
          <button id="dashboardPatientsBtn" type="button" className="dashboard-subtab">
            <span className="dashboard-subtab-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/></svg></span>
            <span>Patients</span>
          </button>
          <button id="dashboardMultimodalBtn" type="button" className="dashboard-subtab">
            <span className="dashboard-subtab-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="m12 3 9 5-9 5-9-5 9-5Z"></path>
                <path d="m3 12 9 5 9-5M3 16l9 5 9-5"></path>
              </svg>
            </span>
            <span>Multimodal</span>
          </button>
          </div></div>
        </div>;}
export function mountNavigationShell() {
  const sidebar=document.querySelector('.app-sidebar');
  const workbench=document.querySelector('.app-workbench');
  const rail=document.createElement('nav');
  rail.className='app-icon-rail';
  rail.setAttribute('aria-label','Application navigation');
  workbench.prepend(rail);
  const menu=document.createElement('div');
  menu.id='accountMenu'; menu.className='account-menu'; menu.hidden=true;
  menu.setAttribute('role','dialog'); menu.setAttribute('aria-label','Account and application settings');
  document.body.append(menu);
  const dashboard=document.createElement('div');
  dashboard.style.display='contents';
  document.getElementById('dashboardTab').prepend(dashboard);
  flushSync(()=>{
    createRoot(rail).render(<Rail/>);
    createRoot(menu).render(<AccountMenu helpUrl={sidebar.dataset.helpUrl} name={sidebar.dataset.brandName}/>);
    createRoot(dashboard).render(<DashboardTabs/>);
  });
  for (const id of ['dashboardTabBtn','datasetsTabBtn','cohortsTabBtn','queryTabBtn','analysisTabBtn','phenoTabBtn']) {
    const button=document.getElementById(id), label=button.textContent.trim();
    button.title=label; button.setAttribute('aria-label',label);
  }
  const runs=document.getElementById('runHistoryDrawerBtn');
  runs.setAttribute('aria-label','Runs'); runs.title='Runs — history and active jobs';
  runs.classList.add('rail-runs');
  rail.insertBefore(runs,document.getElementById('accountMenuButton'));
  document.querySelector('#runHistoryDrawer .jobs-drawer-header').append(document.getElementById('jobsDrawerBtn'));
  runs.append(document.getElementById('jobsDrawerCount'));
  workbench.classList.add('has-icon-rail');
}
