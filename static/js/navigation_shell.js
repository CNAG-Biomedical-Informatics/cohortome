import {mountChatResize} from './react/ui.js';
// Reuse navigation controls and their existing permission/event handling.
export function initializeNavigationShell() {
  const workbench = document.querySelector('.app-workbench');
  const sidebar = document.querySelector('.app-sidebar');
  const menu = document.getElementById('accountMenu');
  const avatarButton = document.getElementById('accountMenuButton');
  mountChatResize(workbench, sidebar);
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
