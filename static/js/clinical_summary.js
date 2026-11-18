import {renderDismissibleNotice,resetSupplementalView} from './react/ui.js';
// Explicit Query/saved-cohort handoffs use the shared applied patient scope.
export function openClinicalSummary(selection) {
  window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:selection}));
}

export function createClinicalSummaryUi({state, navigation, renderDashboard, renderGlobalContext}) {
  const clearNotice = () => {const el=document.getElementById('scopeHandoffStatus');resetSupplementalView(el);el?.remove();};
  const showNotice = message => {
    clearNotice();
    const host = document.getElementById('globalContextBar')?.closest('.app-header');
    if (!host) return;
    const notice = document.createElement('div');
    notice.id = 'scopeHandoffStatus'; notice.className = 'query-status error'; notice.setAttribute('role', 'status');
    host.after(notice);
    renderDismissibleNotice(notice,message,clearNotice);
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
