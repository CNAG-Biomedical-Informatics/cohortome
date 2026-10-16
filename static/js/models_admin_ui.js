export function createModelsAdminUi(ctx) {
  const { refs, callbacks = {} } = ctx;
  const {
    modelsCreateCardEl,
    modelsStatusEl,
    modelsListEl,
    modelCreateIdEl,
    modelCreateLabelEl,
    modelCreateBaseUrlEl,
    modelCreateModelEl,
    modelCreateTimeoutEl,
    modelCreateBoundaryEl,
    modelCreateApiKeyEl,
    modelCreateEnabledEl,
  } = refs;
  const { onProvidersChanged } = callbacks;
  let currentProviders = [];
  const saveFeedback = new Map();

  function showSaveFeedback(id, message, saving = false) {
    saveFeedback.set(id, { message, saving });
    const card = providerCard(id);
    const button = card?.querySelector('[data-lm-provider-action="save"]');
    const status = card?.querySelector('[data-lm-provider-save-status]');
    if (button) {
      button.disabled = saving;
      button.textContent = saving ? "Saving…" : "Save";
    }
    if (status) status.textContent = message;
  }

  modelsListEl?.addEventListener("input", (event) => {
    const card = event.target.closest("[data-lm-provider-card]");
    const id = card?.dataset.lmProviderCard;
    if (id && !saveFeedback.get(id)?.saving) showSaveFeedback(id, "Unsaved changes");
  });

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function setStatus(message, loading = false) {
    if (!modelsStatusEl) return;
    modelsStatusEl.className = loading ? "query-status loading" : "query-status";
    modelsStatusEl.textContent = message;
  }

  function statusClass(status, available, enabled) {
    if (!enabled) return "dataset-picker-tag";
    if (available) return "dataset-picker-tag dataset-picker-tag-ready";
    if (status === "no_model") return "dataset-picker-tag dataset-picker-tag-warning";
    return "dataset-picker-tag dataset-picker-tag-danger";
  }

  function renderModels(providers, expandId = "") {
    if (!modelsListEl) return;
    if (!providers.length) {
      modelsListEl.innerHTML = '<div class="empty">No model providers configured.</div>';
      return;
    }
    const expandedIds = new Set(
      Array.from(modelsListEl.querySelectorAll("[data-lm-provider-card][open]"))
        .map((item) => String(item.dataset.lmProviderCard || "")),
    );
    if (expandId) expandedIds.add(String(expandId));
    modelsListEl.innerHTML = providers.map((provider) => {
      const id = String(provider.id || "");
      const label = String(provider.label || id || "Provider");
      const baseUrl = String(provider.base_url || "");
      const configuredModel = String(provider.model || "");
      const resolvedModel = String(provider.resolved_model || configuredModel || "");
      const status = String(provider.status || (provider.enabled === false ? "disabled" : "unknown"));
      const available = Boolean(provider.available);
      const enabled = provider.enabled !== false;
      const managed = provider.managed === true;
      const source = String(provider.source || "configuration");
      const dataBoundary = String(provider.data_boundary || "external").trim().toLowerCase() === "local" ? "local" : "external";
      const timeout = Number(provider.timeout_seconds || 30);
      const keyConfigured = provider.api_key_configured === true;
      const detail = String(provider.detail || "");
      const sourceLabel = managed ? "In-app" : source === "environment" ? "Environment" : "Server config";
      const safeId = escapeHtml(id);
      const safeLabel = escapeHtml(label);
      const safeBaseUrl = escapeHtml(baseUrl);
      const safeConfiguredModel = escapeHtml(configuredModel);
      const safeResolvedModel = escapeHtml(resolvedModel);
      const providerBody = managed ? `
        <div class="query-grid query-grid-compact">
          <div>
            <label>Display name</label>
            <input type="text" data-lm-provider-field="label" value="${safeLabel}">
          </div>
          <div>
            <label>Provider ID</label>
            <input type="text" value="${safeId}" disabled>
          </div>
          <div class="query-grid-span-2">
            <label>Base URL</label>
            <input type="url" data-lm-provider-field="base_url" value="${safeBaseUrl}">
          </div>
          <div>
            <label>Model ID</label>
            <input type="text" data-lm-provider-field="model" value="${safeConfiguredModel}" placeholder="Discover from provider">
          </div>
          <div>
            <label>Timeout (seconds)</label>
            <input type="number" data-lm-provider-field="timeout_seconds" min="1" max="300" step="1" value="${Number.isFinite(timeout) ? timeout : 30}">
          </div>
          <div>
            <label>Data boundary</label>
            <select data-lm-provider-field="data_boundary">
              <option value="external"${dataBoundary === "external" ? " selected" : ""}>External</option>
              <option value="local"${dataBoundary === "local" ? " selected" : ""}>Local</option>
            </select>
          </div>
          <div>
            <label>Replace API key</label>
            <input type="password" data-lm-provider-field="api_key" placeholder="${keyConfigured ? "Stored; leave blank to keep" : "Optional for local providers"}" autocomplete="new-password">
          </div>
        </div>
        <div class="query-row" style="margin-top:12px;">
          <label class="dataset-picker-check">
            <input type="checkbox" data-lm-provider-field="enabled"${enabled ? " checked" : ""}>
            <span>Enabled</span>
          </label>
          <button type="button" class="query-chip" data-lm-provider-action="test" data-lm-provider="${safeId}">Test connection</button>
          <button type="button" class="query-chip query-chip-deterministic" data-lm-provider-action="save" data-lm-provider="${safeId}"${saveFeedback.get(id)?.saving ? " disabled" : ""}>${saveFeedback.get(id)?.saving ? "Saving…" : "Save"}</button>
          <span class="section-note" data-lm-provider-save-status role="status" aria-live="polite">${escapeHtml(saveFeedback.get(id)?.message || "")}</span>
          ${id === "system-default" ? "" : `<button type="button" class="query-chip query-chip-llm" data-lm-provider-action="delete" data-lm-provider="${safeId}">Delete</button>`}
        </div>
      ` : `
        <div class="section-note">Managed by ${sourceLabel.toLowerCase()} configuration and read-only here. Change its deployment configuration, then restart the server.</div>
        <div class="query-row" style="margin-top:12px;">
          <button type="button" class="query-chip" data-lm-provider-action="test" data-lm-provider="${safeId}">Test connection</button>
        </div>
      `;
      return `
        <details class="dataset-admin-card" data-lm-provider-card="${safeId}"${expandedIds.has(id) ? " open" : ""}>
          <summary class="dataset-admin-summary">
            <span class="dataset-admin-summary-main">
              <span class="dataset-picker-title">${safeLabel}</span>
              <div class="dataset-picker-meta">
                <span class="${statusClass(status, available, enabled)}">${escapeHtml(enabled ? status : "disabled")}</span>
                <span class="dataset-picker-tag">${dataBoundary} boundary</span>
                <span class="dataset-picker-tag">${sourceLabel}</span>
                <span class="dataset-picker-tag">${safeId}</span>
                ${safeResolvedModel ? `<span class="dataset-picker-tag">${safeResolvedModel}</span>` : ""}
                ${keyConfigured ? '<span class="dataset-picker-tag">API key stored</span>' : ""}
              </div>
            </span>
          </summary>
          <div class="dataset-admin-body">
            <div class="dataset-picker-description">${safeBaseUrl}</div>
            ${configuredModel && configuredModel !== resolvedModel ? `<div class="section-note">Configured model: ${safeConfiguredModel}</div>` : ""}
            <div class="section-note">${dataBoundary === "local" ? "May receive private dataset context when that dataset explicitly allows it." : "Never receives context from private datasets."}</div>
            ${detail ? `<div class="section-note">${escapeHtml(detail)}</div>` : ""}
            ${providerBody}
          </div>
        </details>
      `;
    }).join("");
  }

  async function loadModels(options = {}) {
    if (!modelsStatusEl || !modelsListEl) return;
    setStatus("Checking approved model providers...", true);
    try {
      const response = await fetch("/lm-providers");
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to load model providers.");
      }
      const providers = Array.isArray(payload.providers) ? payload.providers : [];
      currentProviders = providers;
      renderModels(providers, options.expandId || "");
      const ready = providers.filter((provider) => provider.available).length;
      const registryError = String(payload.registry_error || "");
      setStatus(registryError || `${ready} of ${providers.length} approved provider${providers.length === 1 ? "" : "s"} ready.`);
    } catch (error) {
      currentProviders = [];
      setStatus(error && error.message ? error.message : "Unable to load model providers.");
      modelsListEl.innerHTML = '<div class="empty">Model provider registry unavailable.</div>';
    }
  }

  function clearCreateForm() {
    if (modelCreateIdEl) modelCreateIdEl.value = "";
    if (modelCreateLabelEl) modelCreateLabelEl.value = "";
    if (modelCreateBaseUrlEl) modelCreateBaseUrlEl.value = "";
    if (modelCreateModelEl) modelCreateModelEl.value = "";
    if (modelCreateTimeoutEl) modelCreateTimeoutEl.value = "30";
    if (modelCreateBoundaryEl) modelCreateBoundaryEl.value = "external";
    if (modelCreateApiKeyEl) modelCreateApiKeyEl.value = "";
    if (modelCreateEnabledEl) modelCreateEnabledEl.checked = true;
  }

  async function notifyProvidersChanged() {
    if (typeof onProvidersChanged === "function") {
      await onProvidersChanged();
    }
  }

  async function createModel() {
    setStatus("Adding model provider...", true);
    try {
      const response = await fetch("/lm-providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: modelCreateIdEl ? modelCreateIdEl.value.trim() : "",
          label: modelCreateLabelEl ? modelCreateLabelEl.value.trim() : "",
          base_url: modelCreateBaseUrlEl ? modelCreateBaseUrlEl.value.trim() : "",
          model: modelCreateModelEl ? modelCreateModelEl.value.trim() : "",
          timeout_seconds: modelCreateTimeoutEl ? Number(modelCreateTimeoutEl.value) : 30,
          data_boundary: modelCreateBoundaryEl ? modelCreateBoundaryEl.value : "external",
          api_key: modelCreateApiKeyEl ? modelCreateApiKeyEl.value : "",
          enabled: modelCreateEnabledEl ? modelCreateEnabledEl.checked : true,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to add model provider.");
      clearCreateForm();
      await loadModels({ expandId: payload.id || "" });
      await notifyProvidersChanged();
      setStatus(`Provider ${payload.label || payload.id} added.`);
    } catch (error) {
      setStatus(error && error.message ? error.message : "Unable to add model provider.");
    }
  }

  function providerCard(id) {
    return modelsListEl ? modelsListEl.querySelector(`[data-lm-provider-card="${CSS.escape(id)}"]`) : null;
  }

  async function saveModel(id) {
    const card = providerCard(id);
    if (!card || saveFeedback.get(id)?.saving) return;
    let saved = false;
    showSaveFeedback(id, "Saving settings…", true);
    setStatus(`Saving ${id}...`, true);
    try {
      const response = await fetch(`/lm-providers/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: card.querySelector('[data-lm-provider-field="label"]')?.value?.trim() || "",
          base_url: card.querySelector('[data-lm-provider-field="base_url"]')?.value?.trim() || "",
          model: card.querySelector('[data-lm-provider-field="model"]')?.value?.trim() || "",
          timeout_seconds: Number(card.querySelector('[data-lm-provider-field="timeout_seconds"]')?.value || 30),
          data_boundary: card.querySelector('[data-lm-provider-field="data_boundary"]')?.value || "external",
          api_key: card.querySelector('[data-lm-provider-field="api_key"]')?.value || "",
          enabled: Boolean(card.querySelector('[data-lm-provider-field="enabled"]')?.checked),
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to update model provider.");
      saved = true;
      showSaveFeedback(id, "Settings saved.", true);
      await loadModels({ expandId: id });
      await notifyProvidersChanged();
      showSaveFeedback(id, "Settings saved.");
      setStatus(`Provider ${payload.label || id} updated.`);
    } catch (error) {
      const message = saved ? "Settings saved, but status refresh failed. Reload to check the connection."
        : error && error.message ? error.message : "Unable to update model provider.";
      showSaveFeedback(id, message);
      setStatus(message);
    }
  }

  async function testModel(id) {
    setStatus(`Testing ${id}...`, true);
    try {
      const response = await fetch(`/lm-providers/${encodeURIComponent(id)}/test`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to test model provider.");
      currentProviders = currentProviders.map((provider) => String(provider.id || "") === id ? { ...provider, ...payload } : provider);
      renderModels(currentProviders);
      setStatus(payload.available ? `${payload.label || id} is ready.` : `${payload.label || id}: ${payload.detail || payload.status || "unavailable"}`);
    } catch (error) {
      setStatus(error && error.message ? error.message : "Unable to test model provider.");
    }
  }

  async function deleteModel(id) {
    if (!window.confirm(`Delete model provider ${id}?`)) return;
    setStatus(`Deleting ${id}...`, true);
    try {
      const response = await fetch(`/lm-providers/${encodeURIComponent(id)}`, { method: "DELETE" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to delete model provider.");
      await loadModels();
      await notifyProvidersChanged();
      setStatus(`Provider ${id} deleted.`);
    } catch (error) {
      setStatus(error && error.message ? error.message : "Unable to delete model provider.");
    }
  }

  return {
    loadModels,
    renderModels,
    createModel,
    saveModel,
    testModel,
    deleteModel,
  };
}
