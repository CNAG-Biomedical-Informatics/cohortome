// Reuse navigation controls and their existing permission/event handling.
export function initializeNavigationShell() {
  const workbench = document.querySelector('.app-workbench');
  const sidebar = document.querySelector('.app-sidebar');
  const rail = document.createElement('nav');
  rail.className = 'app-icon-rail';
  rail.setAttribute('aria-label', 'Application navigation');
  for (const id of ['dashboardTabBtn', 'datasetsTabBtn', 'cohortsTabBtn', 'queryTabBtn', 'analysisTabBtn', 'phenoTabBtn']) {
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
  // Capture descendants before moving their parent into the detached menu.
  // append(null) would otherwise insert the literal text "null".
  const accountMenuItems = [
    account,
    document.getElementById('userSettingsBtn'),
    document.getElementById('adminTabBtn').closest('.app-nav-group'),
    sidebar.querySelector('.app-sidebar-help'),
    document.getElementById('heroLogoutBtn'),
  ];
  const avatarButton = document.createElement('button');
  avatarButton.id = 'accountMenuButton';
  avatarButton.type = 'button';
  avatarButton.setAttribute('aria-label', 'Open account menu');
  avatarButton.setAttribute('aria-expanded', 'false');
  avatarButton.setAttribute('aria-controls', menu.id);
  avatarButton.append(document.getElementById('accountAvatar'));
  menu.append(...accountMenuItems.filter(Boolean));
  rail.append(avatarButton);
  workbench.prepend(rail);
  document.body.append(menu);
  sidebar.querySelector('.app-sidebar-nav').remove();
  workbench.classList.add('has-icon-rail');
  initializeChatResize(workbench, sidebar);
  function setOpen(open, restoreFocus = false) {
    // Close the higher settings layer before opening this menu. Its click
    // bubbles to the outside-click handler, so it must happen first.
    if (open) document.getElementById('userSettingsCloseBtn')?.click();
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

function initializeChatResize(workbench, sidebar) {
  const divider = document.createElement('div');
  divider.className = 'chat-width-divider';
  divider.tabIndex = 0;
  divider.setAttribute('role', 'separator');
  divider.setAttribute('aria-orientation', 'vertical');
  divider.setAttribute('aria-label', 'Chats width');
  divider.setAttribute('aria-controls', 'analysisChatDock');
  divider.title = 'Drag to resize Chats. Use arrow keys when focused.';
  sidebar.after(divider);
  const storageKey = 'cohortome.chatSidebarWidth';
  let width = 232;
  let drag = null;
  try { width = Number(localStorage.getItem(storageKey)) || width; } catch (_) { /* Storage is optional. */ }
  if (!Number.isFinite(width)) width = 232;
  let preferredWidth = width;
  function setWidth(value) {
    const maximum = Math.max(200, Math.min(420, (workbench.clientWidth || 920) - 500));
    width = Math.round(Math.max(200, Math.min(maximum, value)));
    workbench.style.setProperty('--chat-sidebar-width', `${width}px`);
    divider.setAttribute('aria-valuemin', '200');
    divider.setAttribute('aria-valuemax', String(maximum));
    divider.setAttribute('aria-valuenow', String(width));
  }
  function persist() {
    preferredWidth = width;
    try { localStorage.setItem(storageKey, String(width)); } catch (_) { /* Keep in-memory width. */ }
  }
  setWidth(width);
  divider.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    drag = { x: event.clientX, width };
    divider.setPointerCapture(event.pointerId);
    divider.focus();
    workbench.classList.add('is-resizing-chats');
    event.preventDefault();
  });
  divider.addEventListener('pointermove', event => {
    if (drag) setWidth(drag.width + event.clientX - drag.x);
  });
  function finish() {
    if (!drag) return;
    drag = null;
    workbench.classList.remove('is-resizing-chats');
    persist();
  }
  divider.addEventListener('pointerup', finish);
  divider.addEventListener('pointercancel', finish);
  divider.addEventListener('lostpointercapture', finish);
  divider.addEventListener('keydown', event => {
    const step = event.shiftKey ? 25 : 10;
    const values = { ArrowLeft: width - step, ArrowRight: width + step, Home: 200, End: 420 };
    if (!(event.key in values)) return;
    event.preventDefault(); setWidth(values[event.key]); persist();
  });
  window.addEventListener('resize', () => setWidth(preferredWidth));
}
