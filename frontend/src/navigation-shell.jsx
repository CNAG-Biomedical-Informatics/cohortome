import { AccountNavigation } from './shell/account-navigation.jsx';
import { DashboardTabs } from './shell/dashboard-tabs.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

export function mountNavigationShell({ onNavigate, onDashboardNavigate } = {}) {
  const sidebar = document.querySelector('.app-sidebar');
  const workbench = document.querySelector('.app-workbench');
  const rail = document.createElement('nav');
  rail.className = 'app-icon-rail';
  rail.setAttribute('aria-label', 'Application navigation');
  workbench.prepend(rail);
  const dashboard = document.createElement('div');
  dashboard.style.display = 'contents';
  document.getElementById('dashboardTab').prepend(dashboard);
  flushSync(() => {
    createRoot(rail).render(
      <AccountNavigation
        helpUrl={sidebar.dataset.helpUrl}
        name={sidebar.dataset.brandName}
        onNavigate={onNavigate}
      />,
    );
    createRoot(dashboard).render(<DashboardTabs onNavigate={onDashboardNavigate} />);
  });
  for (const id of [
    'dashboardTabBtn',
    'datasetsTabBtn',
    'cohortsTabBtn',
    'queryTabBtn',
    'analysisTabBtn',
    'phenoTabBtn',
  ]) {
    const button = document.getElementById(id),
      label = button.textContent.trim();
    button.title = label;
    button.setAttribute('aria-label', label);
  }
  const runs = document.getElementById('runHistoryDrawerBtn');
  runs.setAttribute('aria-label', 'Runs');
  runs.title = 'Runs — history and active jobs';
  runs.classList.add('rail-runs');
  rail.insertBefore(runs, document.getElementById('accountMenuButton'));
  document
    .querySelector('#runHistoryDrawer .jobs-drawer-header')
    .append(document.getElementById('jobsDrawerBtn'));
  runs.append(document.getElementById('jobsDrawerCount'));
  workbench.classList.add('has-icon-rail');
}
