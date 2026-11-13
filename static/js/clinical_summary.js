// Explicit Query/saved-cohort handoffs use the shared applied patient scope.
export function openClinicalSummary(selection) {
  window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:selection}));
}

export function createClinicalSummaryUi({state, navigation, renderDashboard, renderGlobalContext}) {
  let resetDialog;
  const clearNotice = () => document.getElementById('scopeHandoffStatus')?.remove();
  const showNotice = message => {
    clearNotice();
    const host = document.getElementById('globalContextBar')?.closest('.app-header');
    if (!host) return;
    const notice = document.createElement('div');
    notice.id = 'scopeHandoffStatus'; notice.className = 'query-status error'; notice.setAttribute('role', 'status');
    const text = document.createElement('span'); text.textContent = message;
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'query-chip';
    dismiss.textContent = 'Dismiss'; dismiss.onclick = clearNotice;
    notice.append(text, document.createTextNode(' '), dismiss); host.after(notice);
  };
  const refresh = () => {
    renderDashboard(state.dashboardSummaryState || {});
    renderGlobalContext();
  };
  window.addEventListener('cohortome:workspace-changing', () => {resetDialog?.close(); clearNotice();});
  window.addEventListener('cohortome:scope-applied', clearNotice);
  window.addEventListener('cohortome:clinical-summary', async ({detail}) => {
    const workspace = state.currentDatasetScopeId;
    if (!workspace || !state.cohortScope) return;
    const applied = await state.cohortScope.applySelection(detail);
    if (workspace !== state.currentDatasetScopeId) return;
    if (!applied) {
      showNotice(state.cohortScope.getError() || 'Wait for the current scope update to finish. The previous scope is unchanged.');
      return;
    }
    navigation.setActiveTab('dashboard'); navigation.setDashboardSubtab('clinical'); refresh();
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-clinical-reset]') || !state.activePatientScope || resetDialog) return;
    const selection = state.activePatientScope;
    const dialog = document.createElement('dialog');
    resetDialog = dialog;
    dialog.className = 'chat-move-dialog';
    dialog.setAttribute('aria-labelledby', 'clinicalResetTitle');
    dialog.innerHTML = `<form method="dialog"><h3 id="clinicalResetTitle">Show full workspace?</h3>
      <p>This clears the shared filters and restores the full patient scope. Existing chats and saved cohorts are kept.</p>
      <div class="chat-move-actions"><button class="secondary-btn" value="cancel" autofocus>Keep selection</button><button class="primary-btn" value="confirm">Show full workspace</button></div></form>`;
    dialog.addEventListener('close', () => {
      resetDialog = null; dialog.remove();
      if (dialog.returnValue === 'confirm' && selection === state.activePatientScope) void state.cohortScope.clearScope();
    }, {once:true});
    document.body.append(dialog); dialog.showModal();
  });
}
