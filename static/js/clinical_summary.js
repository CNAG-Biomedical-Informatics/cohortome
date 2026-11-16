// Explicit Query/saved-cohort handoffs use the shared applied patient scope.
export function openClinicalSummary(selection) {
  window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:selection}));
}

export function createClinicalSummaryUi({state, navigation, renderDashboard, renderGlobalContext}) {
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
  window.addEventListener('cohortome:workspace-changing', clearNotice);
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
    navigation.setActiveTab('dashboard'); navigation.setDashboardSubtab('clinical');
    renderDashboard(state.dashboardSummaryState || {});
    renderGlobalContext();
  });
}
