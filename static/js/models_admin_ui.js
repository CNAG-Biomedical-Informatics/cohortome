import {createModelsAdminView} from './react/ui.js';

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
    renderModels(currentProviders);
  }



  function setStatus(message, loading = false) {
    if (!modelsStatusEl) return;
    modelsStatusEl.className = loading ? "query-status loading" : "query-status";
    modelsStatusEl.textContent = message;
  }

  const modelsView = modelsListEl ? createModelsAdminView(modelsListEl, id => {
    if (!saveFeedback.get(id)?.saving) showSaveFeedback(id, 'Unsaved changes');
  }) : null;
  function renderModels(providers, expandId = '') {
    modelsView?.render(providers,saveFeedback,expandId);
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
      modelsView.render([],saveFeedback,'','Model provider registry unavailable.');
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
