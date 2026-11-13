import { fallbackCopyText } from './shared.js';
import { createAgentRunApprovals } from './local_agent_runs.js';

// Sharing is an explicit snapshot, separate from provider settings and live scope.
export function createLocalAgentsUi({state}) {
  const panel = document.getElementById('localAgentsSettings');
  if (!panel || document.documentElement.dataset.deployment !== 'desktop') {
    return {load:async () => {}, hide:() => {}};
  }
  const status = document.getElementById('localAgentsStatus');
  createAgentRunApprovals();
  const badge = document.getElementById('localAgentsBadge');
  const scope = document.getElementById('localAgentsScope');
  const message = document.getElementById('localAgentsMessage');
  const consent = document.getElementById('localAgentsConsent');
  const share = document.getElementById('localAgentsShare');
  const revoke = document.getElementById('localAgentsRevoke');
  const secret = document.getElementById('localAgentsSecret');
  const configuration = document.getElementById('localAgentsConfiguration');
  const copy = document.getElementById('localAgentsCopy');
  const format = document.getElementById('localAgentsFormat');
  let clientConfig = null;
  let selectionKey = '', selectionSignature = '';
  let connection = {enabled:false}, loaded = false, busy = false, revision = 0, secretRevision = 0, scopeRevision = 0;

  function clearSecret() {
    secretRevision++;
    configuration.value = '';
    clientConfig = null;
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
    const selected = state.activePatientScope?.selection?.members;
    const pairs = selected ? [...new Set(selected.map(m => JSON.stringify([m.dataset_id, m.patient_id])))].map(s => JSON.parse(s)) : null;
    // Match Python's canonical pair ordering, including non-ASCII identifiers.
    const compare = (a, b) => {
      const aa = Array.from(a, c => c.codePointAt(0)), bb = Array.from(b, c => c.codePointAt(0));
      for (let i = 0; i < Math.min(aa.length, bb.length); i++) if (aa[i] !== bb[i]) return aa[i] - bb[i];
      return aa.length - bb.length;
    };
    pairs?.sort((a, b) => compare(a[0], b[0]) || compare(a[1], b[1]));
    const key = JSON.stringify([state.currentDatasetScopeId, pairs]);
    if (key !== selectionKey) {
      selectionKey = key;
      selectionSignature = '';
      crypto.subtle.digest('SHA-256', new TextEncoder().encode(key)).then(hash => {
        if (key !== selectionKey) return;
        selectionSignature = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
        render();
      }).catch(() => {});
    }
    if (connection?.enabled && Date.parse(connection.expires_at) <= Date.now()) {
      connection = {enabled:false};
      clearSecret();
    }
    const reason = blockedReason();
    const active = state.activePatientScope;
    scope.textContent = reason || (active
      ? `Ready to share: ${active.selection.members.length.toLocaleString()} selected ${active.selection.members.length === 1 ? 'patient' : 'patients'}.`
      : 'Ready to share: all patients in the current workspace.');
    share.textContent = connection?.enabled ? 'Update shared selection' : 'Enable and share scope';
    share.disabled = !loaded || busy || !consent.checked || Boolean(reason);
    consent.disabled = busy;
    revoke.hidden = connection !== null && !connection.enabled;
    revoke.disabled = busy;
    status.textContent = connection === null
      ? 'Agent access could not be checked. Reopen Settings to check or revoke access.'
      : connection.enabled
      ? `MCP on · ${Number(connection.patient_count || 0).toLocaleString()} ${connection.patient_count === 1 ? 'patient' : 'patients'} shared · ${(connection.datasets || []).map(item => item.name).join(', ')}. Expires ${new Date(connection.expires_at).toLocaleString()}. Access enabled; this does not indicate a connected client.`
      : 'MCP off · No agent access.';
    if (connection?.enabled && selectionSignature && connection.selection_signature &&
        selectionSignature !== connection.selection_signature) {
      scope.textContent = 'Selection changed—not shared yet. ' + scope.textContent;
    }
    if (badge) {
      badge.textContent = connection === null ? 'Status unknown' : connection.enabled
        ? `On · ${Number(connection.patient_count || 0).toLocaleString()} shared` : 'Off';
      badge.dataset.active = String(Boolean(connection?.enabled));
    }
  }
  async function payload(response, fallback) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : fallback);
    return data;
  }
  async function refreshAfterFailure() {
    // A dropped response may hide a successful change or revocation. Fetch
    // authoritative status rather than guessing which snapshot is shared.
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
    const updating = Boolean(connection?.enabled);
    if (!updating) clearSecret();
    const revealTicket = secretRevision;
    const scopeTicket = scopeRevision;
    ++revision;
    busy = true;
    message.textContent = 'Preparing shared access…';
    render();
    try {
      const response = await fetch('/local-agent/share', {method:updating ? 'PUT' : 'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      const data = await payload(response, 'Unable to share this scope.');
      // Never retain the credential in application state or browser storage.
      const {url, token, connector, ...summary} = data;
      connection = summary;
      const changed = scopeTicket !== scopeRevision || body.workspace !== state.currentDatasetScopeId;
      if (!updating && revealTicket === secretRevision && !changed) {
        clientConfig = {connector, env:{COHORTOME_MCP_URL:url, COHORTOME_MCP_TOKEN:token}};
        renderConfiguration();
        secret.hidden = false;
      }
      consent.checked = false;
      message.textContent = changed
        ? 'Your selection changed while preparing access. The earlier snapshot is shared; update the shared selection when ready.'
        : updating ? 'Shared selection updated. Your token is unchanged; no client restart is needed.'
        : 'Scope shared. MCP access is on. Copy the connection settings into your client; no Save changes step is needed.';
    } catch (error) {
      clearSecret();
      await refreshAfterFailure();
      message.textContent = error.message;
    } finally { busy = false; render(); }
  });
  function renderConfiguration() {
    if (!clientConfig) return;
    const {connector, env} = clientConfig;
    format.disabled = !connector;
    if (!connector) {
      configuration.value = JSON.stringify(env, null, 2);
      document.getElementById('localAgentsSecretHelp').textContent = 'Source checkout: use the development connector setup linked above. Installed Desktop builds include the executable. Updating the shared selection keeps your token. Restart, expiry, or turning access off requires new settings.';
    } else if (format.value === 'toml') {
      // JSON basic string escaping is also valid for these TOML path/env strings.
      configuration.value = '[mcp_servers.cohortome]\ncommand = ' + JSON.stringify(connector.command)
        + '\nargs = []\n\n[mcp_servers.cohortome.env]\n'
        + Object.entries(env).map(([key, value]) => `${key} = ${JSON.stringify(value)}`).join('\n');
    } else {
      configuration.value = JSON.stringify({mcpServers:{cohortome:{...connector, env}}}, null, 2);
    }
  }
  format.addEventListener('change', renderConfiguration);
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
  // Keep expiry visible even when the settings disclosure is folded.
  window.setInterval(() => { if (loaded) render(); }, 30000);
  return {load, hide};
}
