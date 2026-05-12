const DEFAULT_USER_SETTINGS = {
  version: 1,
  landing_tab: "dashboard",
  query_disclosure_default: "detailed",
  analysis_auto_open_jobs: true,
  pheno_default_metric: "",
  pheno_advanced_open: false,
  dashboard_molecular_open: false,
  dataset_compact_view: false,
};

const ALLOWED_TABS = new Set(["dashboard", "datasets", "query", "analysis", "pheno"]);
const ALLOWED_DISCLOSURE = new Set(["summary", "detailed"]);
const ALLOWED_PHENO_METRICS = new Set(["", "hamming", "jaccard"]);

function normalizeChoice(value, allowed, fallback) {
  const normalized = String(value || "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function normalizeUserSettings(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  return {
    version: 1,
    landing_tab: normalizeChoice(source.landing_tab, ALLOWED_TABS, DEFAULT_USER_SETTINGS.landing_tab),
    query_disclosure_default: normalizeChoice(source.query_disclosure_default, ALLOWED_DISCLOSURE, DEFAULT_USER_SETTINGS.query_disclosure_default),
    analysis_auto_open_jobs: source.analysis_auto_open_jobs !== false,
    pheno_default_metric: normalizeChoice(source.pheno_default_metric, ALLOWED_PHENO_METRICS, DEFAULT_USER_SETTINGS.pheno_default_metric),
    pheno_advanced_open: Boolean(source.pheno_advanced_open),
    dashboard_molecular_open: Boolean(source.dashboard_molecular_open),
    dataset_compact_view: Boolean(source.dataset_compact_view),
  };
}

export function createUserSettingsUi(ctx) {
  const { refs, state, callbacks } = ctx;
  const {
    userSettingsBtnEl,
    userSettingsPanelEl,
    userSettingsStatusEl,
    settingsLandingTabEl,
    settingsQueryDisclosureEl,
    settingsAnalysisAutoOpenJobsEl,
    settingsPhenoDefaultMetricEl,
    settingsPhenoAdvancedOpenEl,
    settingsDashboardMolecularOpenEl,
    settingsDatasetCompactViewEl,
    phenoAdvancedOptionsEl,
    phenoSimilarityMetricEl,
  } = refs;
  const {
    effectiveQueryGranularityCeiling,
    renderQueryExecutionMode,
    setActiveTab,
    setDashboardSubtab,
    updatePhenoGraphOptions,
  } = callbacks;

  function setStatus(message, kind = "") {
    if (!userSettingsStatusEl) return;
    userSettingsStatusEl.className = kind ? `section-note ${kind}` : "section-note";
    userSettingsStatusEl.textContent = message;
  }

  function setPanelOpen(open) {
    if (!userSettingsPanelEl) return;
    if (open && userSettingsBtnEl) {
      const rect = userSettingsBtnEl.getBoundingClientRect();
      const panelWidth = Math.min(420, Math.max(280, window.innerWidth - 32));
      const left = Math.min(Math.max(16, rect.right - panelWidth), window.innerWidth - panelWidth - 16);
      userSettingsPanelEl.style.setProperty("--settings-panel-top", `${Math.round(rect.bottom + 10)}px`);
      userSettingsPanelEl.style.setProperty("--settings-panel-left", `${Math.round(left)}px`);
      userSettingsPanelEl.style.setProperty("--settings-panel-width", `${Math.round(panelWidth)}px`);
    }
    userSettingsPanelEl.classList.toggle("is-hidden", !open);
  }

  function renderUserSettingsForm() {
    const settings = normalizeUserSettings(state.userSettings);
    if (settingsLandingTabEl) settingsLandingTabEl.value = settings.landing_tab;
    if (settingsQueryDisclosureEl) settingsQueryDisclosureEl.value = settings.query_disclosure_default;
    if (settingsAnalysisAutoOpenJobsEl) settingsAnalysisAutoOpenJobsEl.checked = settings.analysis_auto_open_jobs;
    if (settingsPhenoDefaultMetricEl) settingsPhenoDefaultMetricEl.value = settings.pheno_default_metric;
    if (settingsPhenoAdvancedOpenEl) settingsPhenoAdvancedOpenEl.checked = settings.pheno_advanced_open;
    if (settingsDashboardMolecularOpenEl) settingsDashboardMolecularOpenEl.checked = settings.dashboard_molecular_open;
    if (settingsDatasetCompactViewEl) settingsDatasetCompactViewEl.checked = settings.dataset_compact_view;
  }

  function formSettings() {
    return normalizeUserSettings({
      landing_tab: settingsLandingTabEl ? settingsLandingTabEl.value : DEFAULT_USER_SETTINGS.landing_tab,
      query_disclosure_default: settingsQueryDisclosureEl ? settingsQueryDisclosureEl.value : DEFAULT_USER_SETTINGS.query_disclosure_default,
      analysis_auto_open_jobs: settingsAnalysisAutoOpenJobsEl ? settingsAnalysisAutoOpenJobsEl.checked : DEFAULT_USER_SETTINGS.analysis_auto_open_jobs,
      pheno_default_metric: settingsPhenoDefaultMetricEl ? settingsPhenoDefaultMetricEl.value : DEFAULT_USER_SETTINGS.pheno_default_metric,
      pheno_advanced_open: settingsPhenoAdvancedOpenEl ? settingsPhenoAdvancedOpenEl.checked : DEFAULT_USER_SETTINGS.pheno_advanced_open,
      dashboard_molecular_open: settingsDashboardMolecularOpenEl ? settingsDashboardMolecularOpenEl.checked : DEFAULT_USER_SETTINGS.dashboard_molecular_open,
      dataset_compact_view: settingsDatasetCompactViewEl ? settingsDatasetCompactViewEl.checked : DEFAULT_USER_SETTINGS.dataset_compact_view,
    });
  }

  function applyUserSettings(options = {}) {
    const settings = normalizeUserSettings(state.userSettings);
    state.userSettings = settings;
    document.body.classList.toggle("user-setting-dataset-compact", settings.dataset_compact_view);

    if (phenoAdvancedOptionsEl) {
      phenoAdvancedOptionsEl.open = settings.pheno_advanced_open;
    }
    if (phenoSimilarityMetricEl) {
      phenoSimilarityMetricEl.value = settings.pheno_default_metric;
      updatePhenoGraphOptions();
    }

    const ceiling = effectiveQueryGranularityCeiling();
    state.queryGranularityMode = settings.query_disclosure_default === "summary" || ceiling !== "detailed"
      ? "summary"
      : "detailed";
    if (state.queryGranularityMode !== "detailed") {
      state.queryFollowMemoryEnabled = false;
    }
    renderQueryExecutionMode();

    if (options.applyNavigation !== false) {
      setDashboardSubtab(settings.dashboard_molecular_open ? "molecular" : "clinical");
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
    setStatus("Saving preferences...");
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
    setStatus("Preferences saved.");
  }

  async function resetUserSettings() {
    await saveUserSettings(DEFAULT_USER_SETTINGS);
  }

  return {
    setPanelOpen,
    renderUserSettingsForm,
    applyUserSettings,
    loadUserSettings,
    saveUserSettings,
    resetUserSettings,
  };
}
