import {mountChatResize} from './react/ui.js';
export function initializeNavigationShell() {
  const workbench = document.querySelector('.app-workbench');
  const sidebar = document.querySelector('.app-sidebar');
  mountChatResize(workbench, sidebar);
}
