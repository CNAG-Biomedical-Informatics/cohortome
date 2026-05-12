const DEFAULT_USER_SETTINGS = {
  version: 1,
  landing_tab_mode: "fixed",
  landing_tab: "dashboard",
  query_disclosure_default: "detailed",
  query_default_mode: "auto",
  analysis_auto_open_jobs: true,
  pheno_default_metric: "",
  pheno_advanced_open: false,
  pheno_render_heatmap: true,
  pheno_render_mds: true,
  pheno_render_graph: true,
  dashboard_molecular_open: false,
  dataset_compact_view: false,
};

const ALLOWED_LANDING_TAB_MODES = new Set(["fixed", "last"]);
const ALLOWED_TABS = new Set(["dashboard", "datasets", "query", "analysis", "pheno"]);
const ALLOWED_DISCLOSURE = new Set(["summary", "detailed"]);
const ALLOWED_QUERY_MODES = new Set(["auto", "planner_only"]);
const ALLOWED_PHENO_METRICS = new Set(["", "hamming", "jaccard"]);

function normalizeChoice(value, allowed, fallback) {
  const normalized = String(value || "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function normalizeUserSettings(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  return {
    version: 1,
    landing_tab_mode: normalizeChoice(source.landing_tab_mode, ALLOWED_LANDING_TAB_MODES, DEFAULT_USER_SETTINGS.landing_tab_mode),
    landing_tab: normalizeChoice(source.landing_tab, ALLOWED_TABS, DEFAULT_USER_SETTINGS.landing_tab),
    query_disclosure_default: normalizeChoice(source.query_disclosure_default, ALLOWED_DISCLOSURE, DEFAULT_USER_SETTINGS.query_disclosure_default),
    query_default_mode: normalizeChoice(source.query_default_mode, ALLOWED_QUERY_MODES, DEFAULT_USER_SETTINGS.query_default_mode),
    analysis_auto_open_jobs: source.analysis_auto_open_jobs !== false,
    pheno_default_metric: normalizeChoice(source.pheno_default_metric, ALLOWED_PHENO_METRICS, DEFAULT_USER_SETTINGS.pheno_default_metric),
    pheno_advanced_open: Boolean(source.pheno_advanced_open),
    pheno_render_heatmap: source.pheno_render_heatmap !== false,
    pheno_render_mds: source.pheno_render_mds !== false,
    pheno_render_graph: source.pheno_render_graph !== false,
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
    userSettingsSaveBtnEl,
    userSettingsResetBtnEl,
    settingsLandingTabModeEl,
    settingsLandingTabEl,
    settingsQueryDisclosureEl,
    settingsQueryDefaultModeEl,
    settingsAnalysisAutoOpenJobsEl,
    settingsPhenoDefaultMetricEl,
    settingsPhenoAdvancedOpenEl,
    settingsPhenoRenderHeatmapEl,
    settingsPhenoRenderMdsEl,
    settingsPhenoRenderGraphEl,
    settingsDashboardMolecularOpenEl,
    settingsDatasetCompactViewEl,
    userDeleteChatsBtnEl,
    userDeleteJobsBtnEl,
    userDeleteCohortsBtnEl,
    phenoAdvancedOptionsEl,
    phenoSimilarityMetricEl,
    phenoRenderHeatmapEl,
    phenoRenderMdsEl,
    phenoRenderGraphEl,
  } = refs;
  const {
    effectiveQueryGranularityCeiling,
    renderQueryExecutionMode,
    setActiveTab,
    setDashboardSubtab,
    updatePhenoGraphOptions,
    refreshUserDataAfterDelete,
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
      const panelWidth = Math.min(560, Math.max(300, window.innerWidth - 32));
      const left = Math.min(Math.max(16, rect.right - panelWidth), window.innerWidth - panelWidth - 16);
      userSettingsPanelEl.style.setProperty("--settings-panel-top", `${Math.round(rect.bottom + 10)}px`);
      userSettingsPanelEl.style.setProperty("--settings-panel-left", `${Math.round(left)}px`);
      userSettingsPanelEl.style.setProperty("--settings-panel-width", `${Math.round(panelWidth)}px`);
    }
    userSettingsPanelEl.classList.toggle("is-hidden", !open);
  }

  function renderUserSettingsForm() {
    const settings = normalizeUserSettings(state.userSettings);
    if (settingsLandingTabModeEl) settingsLandingTabModeEl.value = settings.landing_tab_mode;
    if (settingsLandingTabEl) settingsLandingTabEl.value = settings.landing_tab;
    if (settingsQueryDisclosureEl) settingsQueryDisclosureEl.value = settings.query_disclosure_default;
    if (settingsQueryDefaultModeEl) settingsQueryDefaultModeEl.value = settings.query_default_mode;
    if (settingsAnalysisAutoOpenJobsEl) settingsAnalysisAutoOpenJobsEl.checked = settings.analysis_auto_open_jobs;
    if (settingsPhenoDefaultMetricEl) settingsPhenoDefaultMetricEl.value = settings.pheno_default_metric;
    if (settingsPhenoAdvancedOpenEl) settingsPhenoAdvancedOpenEl.checked = settings.pheno_advanced_open;
    if (settingsPhenoRenderHeatmapEl) settingsPhenoRenderHeatmapEl.checked = settings.pheno_render_heatmap;
    if (settingsPhenoRenderMdsEl) settingsPhenoRenderMdsEl.checked = settings.pheno_render_mds;
    if (settingsPhenoRenderGraphEl) settingsPhenoRenderGraphEl.checked = settings.pheno_render_graph;
    if (settingsDashboardMolecularOpenEl) settingsDashboardMolecularOpenEl.checked = settings.dashboard_molecular_open;
    if (settingsDatasetCompactViewEl) settingsDatasetCompactViewEl.checked = settings.dataset_compact_view;
  }

  function formSettings() {
    return normalizeUserSettings({
      landing_tab_mode: settingsLandingTabModeEl ? settingsLandingTabModeEl.value : DEFAULT_USER_SETTINGS.landing_tab_mode,
      landing_tab: settingsLandingTabEl ? settingsLandingTabEl.value : DEFAULT_USER_SETTINGS.landing_tab,
      query_disclosure_default: settingsQueryDisclosureEl ? settingsQueryDisclosureEl.value : DEFAULT_USER_SETTINGS.query_disclosure_default,
      query_default_mode: settingsQueryDefaultModeEl ? settingsQueryDefaultModeEl.value : DEFAULT_USER_SETTINGS.query_default_mode,
      analysis_auto_open_jobs: settingsAnalysisAutoOpenJobsEl ? settingsAnalysisAutoOpenJobsEl.checked : DEFAULT_USER_SETTINGS.analysis_auto_open_jobs,
      pheno_default_metric: settingsPhenoDefaultMetricEl ? settingsPhenoDefaultMetricEl.value : DEFAULT_USER_SETTINGS.pheno_default_metric,
      pheno_advanced_open: settingsPhenoAdvancedOpenEl ? settingsPhenoAdvancedOpenEl.checked : DEFAULT_USER_SETTINGS.pheno_advanced_open,
      pheno_render_heatmap: settingsPhenoRenderHeatmapEl ? settingsPhenoRenderHeatmapEl.checked : DEFAULT_USER_SETTINGS.pheno_render_heatmap,
      pheno_render_mds: settingsPhenoRenderMdsEl ? settingsPhenoRenderMdsEl.checked : DEFAULT_USER_SETTINGS.pheno_render_mds,
      pheno_render_graph: settingsPhenoRenderGraphEl ? settingsPhenoRenderGraphEl.checked : DEFAULT_USER_SETTINGS.pheno_render_graph,
      dashboard_molecular_open: settingsDashboardMolecularOpenEl ? settingsDashboardMolecularOpenEl.checked : DEFAULT_USER_SETTINGS.dashboard_molecular_open,
      dataset_compact_view: settingsDatasetCompactViewEl ? settingsDatasetCompactViewEl.checked : DEFAULT_USER_SETTINGS.dataset_compact_view,
    });
  }

  function applyUserSettings(options = {}) {
    const settings = normalizeUserSettings(state.userSettings);
    state.userSettings = settings;
    document.body.classList.toggle("user-setting-dataset-compact", settings.dataset_compact_view);

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
        confirmText: "Delete all saved analysis chats? Generated job artifacts are not deleted by this action.",
        runningText: "Deleting analysis chats...",
        doneText: (payload) => `Deleted ${payload.deleted_count || 0} saved analysis chat${payload.deleted_count === 1 ? "" : "s"} and cleared the local chat list.`,
        button: userDeleteChatsBtnEl,
      },
      jobs: {
        url: "/user-data/jobs",
        confirmText: "Delete all completed, failed, and cancelled jobs plus generated artifacts? Running jobs will be kept.",
        runningText: "Deleting completed jobs...",
        doneText: (payload) => {
          const skipped = payload.skipped_active_count ? ` ${payload.skipped_active_count} active job${payload.skipped_active_count === 1 ? "" : "s"} kept.` : "";
          return `Deleted ${payload.deleted_count || 0} completed job${payload.deleted_count === 1 ? "" : "s"}.${skipped}`;
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
    applyUserSettings,
    loadUserSettings,
    saveUserSettings,
    resetUserSettings,
    deleteUserData,
  };
}
