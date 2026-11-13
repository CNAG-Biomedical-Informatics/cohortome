import { normalizeSelectionMetadata } from './app_helpers.js';
import { decodeIdentity } from './identities.js';

// Copy only when a chat is created. Applying filters never edits an old chat.
export function captureChatScope(state) {
  const active = state.activePatientScope;
  if (!active || active.workspace !== state.currentDatasetScopeId) return {};
  return normalizeSelectionMetadata(JSON.parse(JSON.stringify(active.selection || {})));
}

export function compactPatientScope(scope) {
  if (!scope?.selection_active) return {};
  return {selection_active:true, id_type:'patient', patient_count:scope.patient_count,
    members:(scope.members || []).map(({dataset_id, patient_id}) => ({dataset_id, patient_id})),
    source:scope.source || {}};
}

export function analysisScopeDefaults(state) {
  const scopeMetadata = captureChatScope(state);
  return {scopeMetadata, scope:chatExecutionIds(state, scopeMetadata).join(',')};
}

export function chatExecutionIds(state, selection) {
  return (selection.patient_ids || []).map(id => {
    const identity = decodeIdentity(id);
    return state.currentDatasetIds?.length === 1 && identity?.datasetId === state.currentDatasetIds[0]
      ? identity.sourceId : id;
  });
}
