// Reuse navigation controls and their existing permission/event handling.
export function initializeNavigationShell() {
  const workbench = document.querySelector('.app-workbench');
  const sidebar = document.querySelector('.app-sidebar');
  const rail = document.createElement('nav');
  rail.className = 'app-icon-rail';
  rail.setAttribute('aria-label', 'Application navigation');
  for (const id of ['dashboardTabBtn', 'datasetsTabBtn', 'queryTabBtn', 'analysisTabBtn', 'phenoTabBtn']) {
    const button = document.getElementById(id);
    const label = button.textContent.trim();
    button.title = label;
    button.setAttribute('aria-label', label);
    rail.append(button);
  }
  const chats = document.getElementById('analysisChatsDrawerBtn');
  chats.title = 'Show chats';
  chats.innerHTML = '<span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg></span>';
  rail.append(chats);
  const runs = document.getElementById('runHistoryDrawerBtn');
  runs.setAttribute('aria-label', 'Runs');
  runs.title = 'Runs — history and active jobs';
  runs.classList.add('rail-runs');
  rail.append(runs);
  // Keep the existing queue drawer available from Run history.
  const queue = document.getElementById('jobsDrawerBtn');
  document.querySelector('#runHistoryDrawer .jobs-drawer-header').append(queue);
  runs.append(document.getElementById('jobsDrawerCount'));
  const dashboardTabs = document.querySelector('.dashboard-subtabs');
  dashboardTabs.classList.add('dashboard-page-tabs');
  document.getElementById('dashboardTab').prepend(dashboardTabs);

  const menu = document.createElement('div');
  menu.id = 'accountMenu';
  menu.className = 'account-menu';
  menu.hidden = true;
  menu.setAttribute('role', 'dialog');
  menu.setAttribute('aria-label', 'Account and application settings');
  const account = sidebar.querySelector('.app-sidebar-account');
  const avatarButton = document.createElement('button');
  avatarButton.id = 'accountMenuButton';
  avatarButton.type = 'button';
  avatarButton.setAttribute('aria-label', 'Open account menu');
  avatarButton.setAttribute('aria-expanded', 'false');
  avatarButton.setAttribute('aria-controls', menu.id);
  avatarButton.append(document.getElementById('accountAvatar'));
  menu.append(account);
  menu.append(document.getElementById('userSettingsBtn'));
  menu.append(document.getElementById('adminTabBtn').closest('.app-nav-group'));
  menu.append(sidebar.querySelector('.app-sidebar-help'));
  menu.append(document.getElementById('heroLogoutBtn'));
  rail.append(avatarButton);
  workbench.prepend(rail);
  document.body.append(menu);
  sidebar.querySelector('.app-sidebar-nav').remove();
  workbench.classList.add('has-icon-rail');
  function setOpen(open, restoreFocus = false) {
    menu.hidden = !open;
    avatarButton.setAttribute('aria-expanded', String(open));
    if (open) {
      const bounds = avatarButton.getBoundingClientRect();
      menu.style.left = `${Math.max(8, Math.min(bounds.right + 8, window.innerWidth - 296))}px`;
      menu.style.bottom = `${Math.max(8, window.innerHeight - bounds.bottom)}px`;
      menu.querySelector('#userSettingsBtn').focus();
    } else if (restoreFocus) avatarButton.focus();
  }
  avatarButton.addEventListener('click', () => setOpen(menu.hidden));
  document.addEventListener('click', event => {
    if (!menu.hidden && !menu.contains(event.target) && !avatarButton.contains(event.target)) setOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !menu.hidden) { setOpen(false, true); event.stopPropagation(); }
  });
  menu.addEventListener('click', event => {
    const action = event.target.closest('button, a');
    if (action && action.id !== 'adminTabBtn') setOpen(false);
  });
  window.addEventListener('resize', () => setOpen(false));
}
