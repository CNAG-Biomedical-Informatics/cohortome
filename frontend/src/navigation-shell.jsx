import { AccountNavigation } from './shell/account-navigation.jsx';
import { DashboardTabs } from './shell/dashboard-tabs.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

export function mountNavigationShell({ onNavigate, onDashboardNavigate, actions } = {}) {
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
        actions={actions}
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
  workbench.classList.add('has-icon-rail');
}
