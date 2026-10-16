import { fallbackCopyText } from "./shared.js";

const DEFAULT_USER_SETTINGS = {
  appearance: "light",
  plot_palette: "default",
  heatmap_palette: "default",
  diverging_palette: "default",
  version: 1,
  landing_tab_mode: "fixed",
  landing_tab: "dashboard",
  query_disclosure_default: "detailed",
  query_default_mode: "auto",
  latest_query_details: true,
  analysis_auto_open_jobs: true,
  job_notifications: true,
  run_history_retention_days: 30,
  pheno_default_metric: "",
  pheno_advanced_open: false,
  pheno_render_heatmap: true,
  pheno_render_mds: true,
  pheno_render_graph: true,
  dashboard_assays_open: false,
  dataset_compact_view: false,
  llm_provider_id: "system-default",
};

const ALLOWED_LANDING_TAB_MODES = new Set(["fixed", "last"]);
const ALLOWED_TABS = new Set(["dashboard", "datasets", "query", "analysis", "pheno"]);
const ALLOWED_DISCLOSURE = new Set(["summary", "detailed"]);
const ALLOWED_QUERY_MODES = new Set(["auto", "planner_only"]);
const ALLOWED_RUN_RETENTION_DAYS = new Set([0, 7, 30, 90, 180, 365]);
const ALLOWED_PHENO_METRICS = new Set(["", "hamming", "jaccard"]);

function normalizeChoice(value, allowed, fallback) {
  const normalized = String(value || "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function normalizeRetentionDays(value, fallback) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && ALLOWED_RUN_RETENTION_DAYS.has(numeric) ? numeric : fallback;
}

function normalizeUserSettings(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  return {
    version: 1,
    plot_palette: normalizeChoice(source.plot_palette, new Set(["default", "okabe-ito", "muted"]), "default"),
    heatmap_palette: normalizeChoice(source.heatmap_palette, new Set(["default", "viridis", "cividis"]), "default"),
    diverging_palette: normalizeChoice(source.diverging_palette, new Set(["default", "blue-orange", "purple-green"]), "default"),
    appearance: normalizeChoice(source.appearance, new Set(["light", "dark", "system"]), "light"),
    landing_tab_mode: normalizeChoice(source.landing_tab_mode, ALLOWED_LANDING_TAB_MODES, DEFAULT_USER_SETTINGS.landing_tab_mode),
    landing_tab: normalizeChoice(source.landing_tab, ALLOWED_TABS, DEFAULT_USER_SETTINGS.landing_tab),
    query_disclosure_default: normalizeChoice(source.query_disclosure_default, ALLOWED_DISCLOSURE, DEFAULT_USER_SETTINGS.query_disclosure_default),
    query_default_mode: normalizeChoice(source.query_default_mode, ALLOWED_QUERY_MODES, DEFAULT_USER_SETTINGS.query_default_mode),
    latest_query_details: source.latest_query_details !== false,
    analysis_auto_open_jobs: source.analysis_auto_open_jobs !== false,
    job_notifications: source.job_notifications !== false,
    run_history_retention_days: normalizeRetentionDays(source.run_history_retention_days, DEFAULT_USER_SETTINGS.run_history_retention_days),
    pheno_default_metric: normalizeChoice(source.pheno_default_metric, ALLOWED_PHENO_METRICS, DEFAULT_USER_SETTINGS.pheno_default_metric),
    pheno_advanced_open: Boolean(source.pheno_advanced_open),
    pheno_render_heatmap: source.pheno_render_heatmap !== false,
    pheno_render_mds: source.pheno_render_mds !== false,
    pheno_render_graph: source.pheno_render_graph !== false,
    dashboard_assays_open: Boolean(source.dashboard_assays_open),
    dataset_compact_view: Boolean(source.dataset_compact_view),
    llm_provider_id: String(source.llm_provider_id || DEFAULT_USER_SETTINGS.llm_provider_id).trim() || DEFAULT_USER_SETTINGS.llm_provider_id,
  };
}

export function createUserSettingsUi(ctx) {
  const { refs, state, callbacks } = ctx;
  const about = document.getElementById("settingsAbout");
  const report = document.getElementById("aboutVersionReport");
  const copy = document.getElementById("aboutCopyReport");
  let aboutLoaded = false;
  let aboutLoading = false;
  about?.addEventListener("toggle", async () => {
    if (!about.open || aboutLoaded || aboutLoading) return;
    aboutLoading = true;
    report.textContent = "Detecting installed versions…";
    try {
      const response = await fetch("/about");
      if (!response.ok) throw new Error();
      const payload = await response.json();
      const rows = Object.entries(payload.components || {});
      for (const [label, version] of [["Plotly (browser)", window.Plotly?.version], ["Cytoscape (browser)", window.cytoscape?.version]]) {
        if (version) rows.push([label, version]);
      }
      report.textContent = rows.map(([name, version]) => `${name}: ${version}`).join("\n") + `\n\n${payload.note}`;
      aboutLoaded = true;
      copy.disabled = false;
    } catch (_) {
      report.textContent = "Unable to load versions. Close and reopen About to retry.";
    } finally { aboutLoading = false; }
  });
  copy?.addEventListener("click", async () => {
    const status = document.getElementById("aboutCopyStatus");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(report.textContent);
      } else {
        if (!fallbackCopyText(report.textContent)) throw new Error();
      }
      status.textContent = "Copied.";
    } catch (_) { status.textContent = "Select the report text and copy it manually."; }
  });
  const {
    userSettingsBtnEl,
    userSettingsPanelEl,
    userSettingsAuthSummaryEl,
    userSettingsStatusEl,
    userSettingsSaveBtnEl,
    userSettingsResetBtnEl,
    settingsLandingTabModeEl,
    settingsAppearanceEl,
    settingsLandingTabEl,
    settingsQueryDisclosureEl,
    settingsQueryDefaultModeEl,
    settingsRunRetentionEl,
    settingsAnalysisAutoOpenJobsEl,
    settingsLatestQueryDetailsEl,
    settingsPhenoDefaultMetricEl,
    settingsLlmProviderEl,
    settingsPhenoAdvancedOpenEl,
    settingsPhenoRenderHeatmapEl,
    settingsPhenoRenderMdsEl,
    settingsPhenoRenderGraphEl,
    settingsDashboardAssaysOpenEl,
    settingsDatasetCompactViewEl,
    userDeleteChatsBtnEl,
    userDeleteJobsBtnEl,
    userDeleteCohortsBtnEl,
    phenoAdvancedOptionsEl,
    phenoSimilarityMetricEl,
    phenoRenderHeatmapEl,
    phenoRenderMdsEl,
    phenoRenderGraphEl,
    queryLatestDetailsEl,
  } = refs;
  const {
    effectiveQueryGranularityCeiling,
    renderQueryExecutionMode,
    setActiveTab,
    setDashboardSubtab,
    updatePhenoGraphOptions,
    refreshLmStatus,
    refreshUserDataAfterDelete,
  } = callbacks;

  function setStatus(message, kind = "") {
    if (!userSettingsStatusEl) return;
    userSettingsStatusEl.className = kind ? `section-note ${kind}` : "section-note";
    userSettingsStatusEl.textContent = message;
  }

  userSettingsPanelEl.addEventListener("click", event => {
    const button = event.target.closest("[data-settings-section]");
    if (!button) return;
    const section = button.dataset.settingsSection;
    userSettingsPanelEl.querySelectorAll("[data-settings-page]").forEach(page => {
      page.hidden = page.dataset.settingsPage !== section;
    });
    userSettingsPanelEl.querySelectorAll("[data-settings-section]").forEach(item => {
      if (item === button) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    userSettingsPanelEl.querySelector(".user-settings-content").scrollTop = 0;
  });
  function updateDirtyStatus() {
    const dirty = JSON.stringify(formSettings()) !== JSON.stringify(normalizeUserSettings(state.userSettings));
    document.getElementById("userSettingsDirty").textContent = dirty ? "Unsaved changes" : "";
  }
  userSettingsPanelEl.addEventListener("input", updateDirtyStatus);
  userSettingsPanelEl.addEventListener("change", updateDirtyStatus);

  function setPanelOpen(open) {
    if (!userSettingsPanelEl) return;
    userSettingsPanelEl.classList.toggle("is-hidden", !open);
    if (open) {
      renderAuthSummary();
    }
  }

  function authProviderLabel(authState) {
    const mode = String(authState && authState.mode || (authState && authState.enabled ? "local" : "none"));
    const provider = String(authState && authState.provider || mode || "none");
    const user = authState && authState.user ? authState.user : {};
    const loginMethod = String(user.login_method || "").trim().toLowerCase();
    if (loginMethod === "local") return mode === "oidc" ? "Local password (fallback)" : "Local password";
    if (loginMethod === "oidc") return `${provider} / OIDC`;
    if (mode === "oidc") return `${provider} / OIDC`;
    if (mode === "local") return "Local password";
    return "Development fallback";
  }

  function renderAuthSummary() {
    if (!userSettingsAuthSummaryEl) return;
    const authState = state.authState || {};
    const user = authState.user || {};
    const groups = Array.isArray(user.groups) && user.groups.length ? user.groups.join(", ") : "none";
    const signedIn = authState.authenticated && user.username;
    const rows = [
      ["Signed in as", signedIn ? `${user.display_name || user.username} (${user.username})` : "Not signed in"],
      ["Provider", authProviderLabel(authState)],
      ["Local password fallback", authState.localLoginEnabled ? "enabled" : "disabled"],
      ["Password reset", authState.passwordResetEnabled ? "SMTP configured" : "contact administrator"],
      ["Email", user.email || "not set"],
      ["Role", user.role || "user"],
      ["Groups", groups],
    ];
    userSettingsAuthSummaryEl.innerHTML = `
      <strong>Authentication</strong>
      <div class="user-settings-auth-grid">
        ${rows.map(([label, value]) => `
          <div class="user-settings-auth-label">${label}</div>
          <div class="user-settings-auth-value">${String(value).replace(/</g, "&lt;")}</div>
        `).join("")}
      </div>
      <div class="section-note">Dataset access is managed by COHORTome roles and groups.</div>
    `;
  }

  function renderUserSettingsForm() {
    const settings = normalizeUserSettings(state.userSettings);
    renderLlmProviderOptions(settings.llm_provider_id);
    if (settingsAppearanceEl) settingsAppearanceEl.value = settings.appearance;
    for (const key of ["plot_palette", "heatmap_palette", "diverging_palette"]) {
      document.getElementById(`settings_${key}`).value = settings[key];
      window.CohortomeTheme.palettePreview(key, settings[key]);
      document.getElementById(`settings_${key}`).onchange = event => window.CohortomeTheme.palettePreview(key, event.target.value);
    }
    if (settingsLandingTabModeEl) settingsLandingTabModeEl.value = settings.landing_tab_mode;
    if (settingsLandingTabEl) settingsLandingTabEl.value = settings.landing_tab;
    if (settingsQueryDisclosureEl) settingsQueryDisclosureEl.value = settings.query_disclosure_default;
    if (settingsQueryDefaultModeEl) settingsQueryDefaultModeEl.value = settings.query_default_mode;
    if (settingsRunRetentionEl) settingsRunRetentionEl.value = String(settings.run_history_retention_days);
    if (settingsAnalysisAutoOpenJobsEl) settingsAnalysisAutoOpenJobsEl.checked = settings.analysis_auto_open_jobs;
    document.getElementById("settingsJobNotifications").checked = settings.job_notifications;
    if (settingsLatestQueryDetailsEl) settingsLatestQueryDetailsEl.checked = settings.latest_query_details;
    if (settingsPhenoDefaultMetricEl) settingsPhenoDefaultMetricEl.value = settings.pheno_default_metric;
    if (settingsLlmProviderEl) settingsLlmProviderEl.value = settings.llm_provider_id;
    if (settingsPhenoAdvancedOpenEl) settingsPhenoAdvancedOpenEl.checked = settings.pheno_advanced_open;
    if (settingsPhenoRenderHeatmapEl) settingsPhenoRenderHeatmapEl.checked = settings.pheno_render_heatmap;
    if (settingsPhenoRenderMdsEl) settingsPhenoRenderMdsEl.checked = settings.pheno_render_mds;
    if (settingsPhenoRenderGraphEl) settingsPhenoRenderGraphEl.checked = settings.pheno_render_graph;
    if (settingsDashboardAssaysOpenEl) settingsDashboardAssaysOpenEl.checked = settings.dashboard_assays_open;
    if (settingsDatasetCompactViewEl) settingsDatasetCompactViewEl.checked = settings.dataset_compact_view;
    renderAuthSummary();
    updateDirtyStatus();
  }

  function renderLlmProviderOptions(selectedProviderId) {
    if (!settingsLlmProviderEl) return;
    const providers = Array.isArray(state.lmStatus && state.lmStatus.providers) ? state.lmStatus.providers : [];
    const options = providers.length ? providers : [{ id: "system-default", label: "System default", model: "", enabled: true }];
    settingsLlmProviderEl.innerHTML = options.map((provider) => {
      const id = String(provider.id || "");
      const label = String(provider.label || id || "Provider");
      const model = String(provider.model || "").trim();
      const enabled = provider.enabled !== false;
      const dataBoundary = String(provider.data_boundary || "external").trim().toLowerCase() === "local" ? "local" : "external";
      const text = `${label} (${dataBoundary})${model ? ` - ${model}` : ""}${enabled ? "" : " (disabled)"}`;
      return `<option value="${id.replace(/"/g, "&quot;")}"${id === selectedProviderId ? " selected" : ""}>${text.replace(/</g, "&lt;")}</option>`;
    }).join("");
    if (selectedProviderId && !options.some((provider) => String(provider.id || "") === selectedProviderId)) {
      settingsLlmProviderEl.insertAdjacentHTML("beforeend", `<option value="${selectedProviderId.replace(/"/g, "&quot;")}" selected>${selectedProviderId} (unavailable)</option>`);
    }
  }

  function formSettings() {
    return normalizeUserSettings({
      plot_palette: document.getElementById("settings_plot_palette").value,
      heatmap_palette: document.getElementById("settings_heatmap_palette").value,
      diverging_palette: document.getElementById("settings_diverging_palette").value,
      landing_tab_mode: settingsLandingTabModeEl ? settingsLandingTabModeEl.value : DEFAULT_USER_SETTINGS.landing_tab_mode,
      appearance: settingsAppearanceEl ? settingsAppearanceEl.value : "light",
      landing_tab: settingsLandingTabEl ? settingsLandingTabEl.value : DEFAULT_USER_SETTINGS.landing_tab,
      query_disclosure_default: settingsQueryDisclosureEl ? settingsQueryDisclosureEl.value : DEFAULT_USER_SETTINGS.query_disclosure_default,
      query_default_mode: settingsQueryDefaultModeEl ? settingsQueryDefaultModeEl.value : DEFAULT_USER_SETTINGS.query_default_mode,
      run_history_retention_days: settingsRunRetentionEl ? Number(settingsRunRetentionEl.value) : DEFAULT_USER_SETTINGS.run_history_retention_days,
      analysis_auto_open_jobs: settingsAnalysisAutoOpenJobsEl ? settingsAnalysisAutoOpenJobsEl.checked : DEFAULT_USER_SETTINGS.analysis_auto_open_jobs,
      job_notifications: document.getElementById("settingsJobNotifications").checked,
      latest_query_details: settingsLatestQueryDetailsEl ? settingsLatestQueryDetailsEl.checked : DEFAULT_USER_SETTINGS.latest_query_details,
      pheno_default_metric: settingsPhenoDefaultMetricEl ? settingsPhenoDefaultMetricEl.value : DEFAULT_USER_SETTINGS.pheno_default_metric,
      llm_provider_id: settingsLlmProviderEl ? settingsLlmProviderEl.value : DEFAULT_USER_SETTINGS.llm_provider_id,
      pheno_advanced_open: settingsPhenoAdvancedOpenEl ? settingsPhenoAdvancedOpenEl.checked : DEFAULT_USER_SETTINGS.pheno_advanced_open,
      pheno_render_heatmap: settingsPhenoRenderHeatmapEl ? settingsPhenoRenderHeatmapEl.checked : DEFAULT_USER_SETTINGS.pheno_render_heatmap,
      pheno_render_mds: settingsPhenoRenderMdsEl ? settingsPhenoRenderMdsEl.checked : DEFAULT_USER_SETTINGS.pheno_render_mds,
      pheno_render_graph: settingsPhenoRenderGraphEl ? settingsPhenoRenderGraphEl.checked : DEFAULT_USER_SETTINGS.pheno_render_graph,
      dashboard_assays_open: settingsDashboardAssaysOpenEl ? settingsDashboardAssaysOpenEl.checked : DEFAULT_USER_SETTINGS.dashboard_assays_open,
      dataset_compact_view: settingsDatasetCompactViewEl ? settingsDatasetCompactViewEl.checked : DEFAULT_USER_SETTINGS.dataset_compact_view,
    });
  }

  function applyUserSettings(options = {}) {
    const settings = normalizeUserSettings(state.userSettings);
    state.userSettings = settings;
    window.CohortomeTheme.apply(settings.appearance);
    window.CohortomeTheme.applyPalettes(settings);
    document.body.classList.toggle("user-setting-dataset-compact", settings.dataset_compact_view);
    if (queryLatestDetailsEl) {
      queryLatestDetailsEl.classList.toggle("is-hidden", !settings.latest_query_details);
      if (!settings.latest_query_details) queryLatestDetailsEl.open = false;
    }

    state.queryExecutionMode = settings.query_default_mode;
    if (phenoAdvancedOptionsEl) {
      phenoAdvancedOptionsEl.open = settings.pheno_advanced_open;
    }
    if (phenoSimilarityMetricEl) phenoSimilarityMetricEl.value = settings.pheno_default_metric;
    if (phenoRenderHeatmapEl) phenoRenderHeatmapEl.checked = settings.pheno_render_heatmap;
    if (phenoRenderMdsEl) phenoRenderMdsEl.checked = settings.pheno_render_mds;
    if (phenoRenderGraphEl) phenoRenderGraphEl.checked = settings.pheno_render_graph;
    updatePhenoGraphOptions();

    const ceiling = effectiveQueryGranularityCeiling();
    state.queryGranularityMode = settings.query_disclosure_default === "summary" || ceiling !== "detailed"
      ? "summary"
      : "detailed";
    if (state.queryGranularityMode !== "detailed") {
      state.queryFollowMemoryEnabled = false;
    }
    renderQueryExecutionMode();

    if (options.applyNavigation !== false && settings.landing_tab_mode === "fixed") {
      setDashboardSubtab(settings.dashboard_assays_open ? "assays" : "clinical");
      setActiveTab(settings.landing_tab);
    }
    renderUserSettingsForm();
  }

  async function loadUserSettings(options = {}) {
    try {
      const response = await fetch("/user-settings");
      if (!response.ok) {
        throw new Error("Unable to load user settings.");
      }
      state.userSettings = normalizeUserSettings(await response.json());
      applyUserSettings(options);
      setStatus("Preferences loaded.");
    } catch (error) {
      state.userSettings = normalizeUserSettings(DEFAULT_USER_SETTINGS);
      applyUserSettings(options);
      setStatus(error && error.message ? error.message : "Unable to load user settings.", "is-warning");
    }
  }

  async function saveUserSettings(settings = formSettings()) {
    const originalLabel = userSettingsSaveBtnEl ? userSettingsSaveBtnEl.textContent : "";
    if (userSettingsSaveBtnEl) {
      userSettingsSaveBtnEl.disabled = true;
      userSettingsSaveBtnEl.textContent = "Saving...";
    }
    setStatus("Saving preferences...");
    try {
      const response = await fetch("/user-settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Unable to save user settings.");
      }
      state.userSettings = normalizeUserSettings(await response.json());
      applyUserSettings();
      if (typeof refreshLmStatus === "function") {
        await refreshLmStatus();
      }
      setStatus("Preferences saved.");
      if (userSettingsSaveBtnEl) {
        userSettingsSaveBtnEl.textContent = "Saved";
        window.setTimeout(() => {
          userSettingsSaveBtnEl.textContent = originalLabel || "Save";
          userSettingsSaveBtnEl.disabled = false;
        }, 1400);
      }
    } catch (error) {
      if (userSettingsSaveBtnEl) {
        userSettingsSaveBtnEl.textContent = originalLabel || "Save";
        userSettingsSaveBtnEl.disabled = false;
      }
      throw error;
    }
  }

  async function resetUserSettings() {
    if (userSettingsResetBtnEl) userSettingsResetBtnEl.disabled = true;
    try {
      await saveUserSettings(DEFAULT_USER_SETTINGS);
    } finally {
      if (userSettingsResetBtnEl) userSettingsResetBtnEl.disabled = false;
    }
  }

  async function deleteUserData(kind) {
    const config = {
      chats: {
        url: "/user-data/analysis-sessions",
        confirmText: "Delete all saved analysis chats without linked generated runs? Chats with generated runs must be deleted from Analysis.",
        runningText: "Deleting analysis chats...",
        doneText: (payload) => `Deleted ${payload.deleted_count || 0} saved analysis chat${payload.deleted_count === 1 ? "" : "s"} and cleared the local chat list.`,
        button: userDeleteChatsBtnEl,
      },
      jobs: {
        url: "/run-history",
        confirmText: "Delete all completed, failed, and cancelled generated runs plus artifacts? Active runs will be kept.",
        runningText: "Deleting generated runs...",
        doneText: (payload) => {
          const skipped = payload.skipped_active_count ? ` ${payload.skipped_active_count} active run${payload.skipped_active_count === 1 ? "" : "s"} kept.` : "";
          return `Deleted ${payload.deleted_count || 0} generated run${payload.deleted_count === 1 ? "" : "s"}.${skipped}`;
        },
        button: userDeleteJobsBtnEl,
      },
      cohorts: {
        url: "/user-data/saved-cohorts",
        confirmText: "Delete all saved cohorts? Cohorts referenced by analysis chats will block this action.",
        runningText: "Deleting saved cohorts...",
        doneText: (payload) => `Deleted ${payload.deleted_count || 0} saved cohort${payload.deleted_count === 1 ? "" : "s"}.`,
        button: userDeleteCohortsBtnEl,
      },
    }[kind];
    if (!config) return;
    if (!window.confirm(config.confirmText)) return;
    if (config.button) config.button.disabled = true;
    setStatus(config.runningText);
    try {
      const response = await fetch(config.url, { method: "DELETE" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to delete saved data.");
      }
      if (typeof refreshUserDataAfterDelete === "function") {
        await refreshUserDataAfterDelete(kind);
      }
      setStatus(config.doneText(payload));
    } catch (error) {
      setStatus(error && error.message ? error.message : "Unable to delete saved data.", "is-warning");
    } finally {
      if (config.button) config.button.disabled = false;
    }
  }

  return {
    setPanelOpen,
    renderUserSettingsForm,
    renderAuthSummary,
    applyUserSettings,
    loadUserSettings,
    saveUserSettings,
    resetUserSettings,
    deleteUserData,
  };
}
