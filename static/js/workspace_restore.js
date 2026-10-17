// An explicit action: inspecting a saved chat never changes active datasets.
export function addWorkspaceRestoreAction(container, { scope, currentScope, restore, reopen }) {
  if (!container || !scope || scope === currentScope || !restore) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'query-chip';
  button.textContent = 'Load this chat’s datasets';
  button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = 'Loading datasets…';
    container.querySelector('[data-restore-error]')?.remove();
    try {
      await restore(scope);
      await reopen();
      button.remove();
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Retry loading datasets';
      let notice = container.querySelector('[data-restore-error]');
      if (!notice) {
        notice = document.createElement('span');
        notice.dataset.restoreError = 'true';
        notice.setAttribute('role', 'status');
        container.append(notice);
      }
      notice.textContent = error.message || 'The original workspace is unavailable.';
    }
  });
  container.append(document.createTextNode(' '), button);
}
