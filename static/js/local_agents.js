import { fallbackCopyText } from './shared.js';

// Sharing is an explicit snapshot, separate from provider settings and live scope.
export function createLocalAgentsUi({state}) {
  const panel = document.getElementById('localAgentsSettings');
  if (!panel || document.documentElement.dataset.deployment !== 'desktop') {
    return {load:async () => {}, hide:() => {}};
  }
  const status = document.getElementById('localAgentsStatus');
  const scope = document.getElementById('localAgentsScope');
  const message = document.getElementById('localAgentsMessage');
  const consent = document.getElementById('localAgentsConsent');
  const share = document.getElementById('localAgentsShare');
  const revoke = document.getElementById('localAgentsRevoke');
  const secret = document.getElementById('localAgentsSecret');
  const configuration = document.getElementById('localAgentsConfiguration');
  const copy = document.getElementById('localAgentsCopy');
  let connection = {enabled:false}, loaded = false, busy = false, revision = 0, secretRevision = 0, scopeRevision = 0;

  function clearSecret() {
    secretRevision++;
    configuration.value = '';
    secret.hidden = true;
  }
  function blockedReason() {
    if (state.loadInFlight || state.cohortScope?.isBusy()) return 'Wait for the workspace to finish loading.';
    if (state.cohortScope?.isDirty()) return 'Apply or discard your draft filters before sharing.';
    const ids = state.currentDatasetIds || [];
    if (!state.currentDatasetScopeId || !ids.length) return 'Load a bundled demo first.';
    if (ids.some(id => !['default', 'synthetic-cross-sectional-demo'].includes(id))) {
      return 'This prototype accepts only the two included synthetic demos.';
    }
    const active = state.activePatientScope;
    if (active && (active.workspace !== state.currentDatasetScopeId || !Array.isArray(active.selection?.members))) {
      return 'Reload the workspace and apply your selection before sharing.';
    }
    return '';
  }
  function render() {
    const reason = blockedReason();
    const active = state.activePatientScope;
    scope.textContent = reason || (active
      ? `Ready to share: ${active.selection.members.length.toLocaleString()} selected ${active.selection.members.length === 1 ? 'patient' : 'patients'}.`
      : 'Ready to share: all patients in the current workspace.');
    share.textContent = connection?.enabled ? 'Replace shared scope' : 'Share current scope';
    share.disabled = !loaded || busy || !consent.checked || Boolean(reason);
    consent.disabled = busy;
    revoke.hidden = connection !== null && !connection.enabled;
    revoke.disabled = busy;
    status.textContent = connection === null
      ? 'Agent access could not be checked. Reopen Settings to check or revoke access.'
      : connection.enabled
      ? `${Number(connection.patient_count || 0).toLocaleString()} ${connection.patient_count === 1 ? 'patient' : 'patients'} shared · ${(connection.datasets || []).map(item => item.name).join(', ')}. Expires ${new Date(connection.expires_at).toLocaleString()}.`
      : 'Not shared.';
  }
  async function payload(response, fallback) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : fallback);
    return data;
  }
  async function refreshAfterFailure() {
    // A failed replacement may already have revoked the old token. A dropped
    // response may also hide a successful change; never guess the grant state.
    try {
      connection = await payload(await fetch('/local-agent/status', {cache:'no-store'}), 'Unable to check agent access.');
      loaded = true;
    } catch (_) {
      connection = null;
      loaded = false;
    }
  }
  async function load() {
    if (busy) return;
    clearSecret();
    consent.checked = false;
    loaded = false;
    const ticket = ++revision;
    render();
    try {
      const response = await fetch('/local-agent/status', {cache:'no-store'});
      if (ticket !== revision) return;
      if ([401, 403, 404].includes(response.status)) { panel.hidden = true; return; }
      connection = await payload(response, 'Unable to check agent access. Reopen Settings to retry.');
      if (ticket !== revision) return;
      loaded = true;
      panel.hidden = false;
      message.textContent = '';
    } catch (error) {
      if (ticket !== revision) return;
      connection = null;
      panel.hidden = false;
      message.textContent = error.message;
    }
    render();
  }
  consent.addEventListener('change', render);
  share.addEventListener('click', async () => {
    if (share.disabled || blockedReason()) return;
    const active = state.activePatientScope;
    const body = {workspace:state.currentDatasetScopeId, acknowledge:true,
      members:active ? active.selection.members.map(({dataset_id, patient_id}) => ({dataset_id, patient_id})) : null};
    clearSecret();
    const revealTicket = secretRevision;
    const scopeTicket = scopeRevision;
    ++revision;
    busy = true;
    message.textContent = 'Preparing read-only access…';
    render();
    try {
      const response = await fetch('/local-agent/share', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      const data = await payload(response, 'Unable to share this scope.');
      // Never retain the credential in application state or browser storage.
      const {url, token, ...summary} = data;
      connection = summary;
      const changed = scopeTicket !== scopeRevision || body.workspace !== state.currentDatasetScopeId;
      if (revealTicket === secretRevision && !changed) {
        configuration.value = JSON.stringify({COHORTOME_MCP_URL:url, COHORTOME_MCP_TOKEN:token}, null, 2);
        secret.hidden = false;
      }
      consent.checked = false;
      message.textContent = changed
        ? 'Your selection changed while preparing access. The earlier snapshot is shared; replace it to get connection settings for the current scope.'
        : 'Scope shared. Later selections do not change this snapshot.';
    } catch (error) {
      clearSecret();
      await refreshAfterFailure();
      message.textContent = error.message;
    } finally { busy = false; render(); }
  });
  revoke.addEventListener('click', async () => {
    if (busy) return;
    ++revision;
    clearSecret();
    busy = true;
    message.textContent = 'Revoking access…';
    render();
    try {
      const response = await fetch('/local-agent/share', {method:'DELETE'});
      if (!response.ok) await payload(response, 'Unable to revoke access. Try again or close the app.');
      connection = {enabled:false};
      consent.checked = false;
      message.textContent = 'Agent access revoked.';
    } catch (error) {
      await refreshAfterFailure();
      message.textContent = error.message;
    }
    finally { busy = false; render(); }
  });
  copy.addEventListener('click', async () => {
    if (!configuration.value) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(configuration.value);
      else if (!fallbackCopyText(configuration.value)) throw new Error();
      message.textContent = 'Connection settings copied. Keep the token private.';
    } catch (_) { message.textContent = 'Select the connection settings and copy them manually.'; }
  });
  state.cohortScope?.subscribe(render);
  for (const event of ['cohortome:scope-applied', 'cohortome:workspace-changing', 'cohortome:workspace-committed', 'cohortome:workspace-settled']) {
    window.addEventListener(event, () => {scopeRevision++; render();});
  }
  function hide() {
    clearSecret();
    consent.checked = false;
    render();
  }
  window.addEventListener('pagehide', hide);
  return {load, hide};
}
