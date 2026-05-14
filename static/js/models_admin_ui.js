export function createModelsAdminUi(ctx) {
  const { refs } = ctx;
  const {
    modelsStatusEl,
    modelsListEl,
  } = refs;

  function statusClass(status, available, enabled) {
    if (!enabled) return "dataset-picker-tag";
    if (available) return "dataset-picker-tag dataset-picker-tag-ready";
    if (status === "no_model") return "dataset-picker-tag dataset-picker-tag-warning";
    return "dataset-picker-tag dataset-picker-tag-danger";
  }

  function renderModels(providers) {
    if (!modelsListEl) return;
    if (!providers.length) {
      modelsListEl.innerHTML = '<div class="empty">No model providers configured.</div>';
      return;
    }
    modelsListEl.innerHTML = providers.map((provider) => {
      const id = String(provider.id || "");
      const label = String(provider.label || id || "Provider");
      const baseUrl = String(provider.base_url || "");
      const configuredModel = String(provider.model || "");
      const resolvedModel = String(provider.resolved_model || configuredModel || "");
      const status = String(provider.status || (provider.enabled === false ? "disabled" : "unknown"));
      const available = Boolean(provider.available);
      const enabled = provider.enabled !== false;
      const detail = String(provider.detail || "");
      return `
        <div class="dataset-picker-card">
          <div>
            <div class="dataset-picker-title">
              <span>${label.replace(/</g, "&lt;")}</span>
              <div class="dataset-picker-meta">
                <span class="${statusClass(status, available, enabled)}">${enabled ? status : "disabled"}</span>
                <span class="dataset-picker-tag">${id.replace(/</g, "&lt;")}</span>
                ${resolvedModel ? `<span class="dataset-picker-tag">${resolvedModel.replace(/</g, "&lt;")}</span>` : ""}
              </div>
            </div>
            <div class="dataset-picker-description">${baseUrl.replace(/</g, "&lt;")}</div>
            ${configuredModel && configuredModel !== resolvedModel ? `<div class="section-note">Configured model: ${configuredModel.replace(/</g, "&lt;")}</div>` : ""}
            ${detail ? `<div class="section-note">${detail.replace(/</g, "&lt;")}</div>` : ""}
          </div>
        </div>
      `;
    }).join("");
  }

  async function loadModels() {
    if (!modelsStatusEl || !modelsListEl) return;
    modelsStatusEl.className = "query-status loading";
    modelsStatusEl.textContent = "Checking approved model providers...";
    try {
      const response = await fetch("/lm-providers");
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to load model providers.");
      }
      const providers = Array.isArray(payload.providers) ? payload.providers : [];
      renderModels(providers);
      const ready = providers.filter((provider) => provider.available).length;
      modelsStatusEl.className = "query-status";
      modelsStatusEl.textContent = `${ready} of ${providers.length} approved provider${providers.length === 1 ? "" : "s"} ready.`;
    } catch (error) {
      modelsStatusEl.className = "query-status";
      modelsStatusEl.textContent = error && error.message ? error.message : "Unable to load model providers.";
      modelsListEl.innerHTML = '<div class="empty">Model provider registry unavailable.</div>';
    }
  }

  return {
    loadModels,
    renderModels,
  };
}
