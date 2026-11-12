// Explicit handoffs only: this selection never changes Analysis or Timeline.
export function openClinicalSummary(selection) {
  window.dispatchEvent(new CustomEvent('cohortome:clinical-summary', {detail:selection}));
}

export function createClinicalSummaryUi({state, navigation, renderDashboard, renderGlobalContext}) {
  let generation = 0, controller;
  const refresh = () => {
    renderDashboard(state.dashboardSummaryState || {});
    renderGlobalContext();
  };
  const reset = () => {
    generation++; controller?.abort(); state.clinicalSelection = null;
  };
  window.addEventListener('cohortome:workspace-changing', reset);
  window.addEventListener('cohortome:clinical-summary', async ({detail}) => {
    reset();
    const workspace = state.currentDatasetScopeId;
    const ticket = generation;
    if (!workspace) return;
    controller = new AbortController();
    const activeController = controller;
    state.clinicalSelection = {workspace, status:'loading', label:detail.label || 'Selected patients'};
    navigation.setActiveTab('dashboard'); navigation.setDashboardSubtab('clinical'); refresh();
    const timeout = setTimeout(() => activeController.abort(), 30000);
    try {
      const {members, patient_ids, result_handle, cohort_id} = detail;
      const response = await fetch('/dashboard/selection', {method:'POST', signal:controller.signal,
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dataset_id:workspace, members, patient_ids, result_handle, cohort_id})});
      const data = await response.json();
      if (ticket !== generation || workspace !== state.currentDatasetScopeId) return;
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to summarize this selection.');
      state.clinicalSelection = {...state.clinicalSelection, status:'ready', data};
    } catch (error) {
      if (ticket !== generation || workspace !== state.currentDatasetScopeId) return;
      state.clinicalSelection = {...state.clinicalSelection, status:'error',
        error:error.name === 'AbortError' ? 'The summary timed out. Send the selection again to retry.' : error.message};
    } finally {
      clearTimeout(timeout);
      if (ticket === generation && workspace === state.currentDatasetScopeId) refresh();
    }
  });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-clinical-reset]')) { reset(); refresh(); }
  });
}
