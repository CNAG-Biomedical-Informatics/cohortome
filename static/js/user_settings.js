import {createAuthSummaryView,createSettingsPreferences,createSettingsNavigation,createExportSettingsView,createAboutSettingsView} from './react/ui.js';
import { fallbackCopyText } from "./shared.js";
import { createResourceStorage } from './resource_storage.js';
import { createLocalAgentsUi } from './local_agents.js';

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
  pheno_render_umap: false,
  pheno_render_graph: true,
  dashboard_assays_open: false,
  dataset_compact_view: false,
  llm_provider_id: "system-default",
};

const ALLOWED_LANDING_TAB_MODES = new Set(["fixed", "last"]);
const ALLOWED_TABS = new Set(["dashboard", "datasets", "cohorts", "query", "analysis", "pheno"]);
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
    pheno_render_umap: source.pheno_render_umap === true,
    pheno_render_graph: source.pheno_render_graph !== false,
    dashboard_assays_open: Boolean(source.dashboard_assays_open),
    dataset_compact_view: Boolean(source.dataset_compact_view),
    llm_provider_id: String(source.llm_provider_id || DEFAULT_USER_SETTINGS.llm_provider_id).trim() || DEFAULT_USER_SETTINGS.llm_provider_id,
  };
}

export function createUserSettingsUi(ctx) {
  const { refs, state, callbacks } = ctx;
  const exportPanel = document.getElementById("exportLimitsSettings");
  const resourceStorage = createResourceStorage();
  const localAgents = createLocalAgentsUi({state});
  const exportView=createExportSettingsView(exportPanel);
  let exportValues={}, exportStatus='', exportBusy=false;
  function renderExportLimits() {
    exportView.render({values:exportValues,status:exportStatus,busy:exportBusy,
      onChange:(key,value)=>{exportValues={...exportValues,[key]:value};renderExportLimits();},
      onSave:saveExportLimits,onDefaults:()=>{
        exportValues={source_mib:512,total_source_mib:1024,output_mib:256};
        exportStatus='Defaults selected. Save export limits to apply.';renderExportLimits();
      }});
  }
  async function loadExportLimits() {
    if (!exportPanel) return;
    exportPanel.hidden=true;
    try {
      const response=await fetch('/export-settings');
      if(response.status===401 || response.status===403)return;
      exportPanel.hidden=false;
      if(!response.ok)throw new Error('Export limits could not be loaded. Use defaults and save to recover.');
      exportValues=await response.json();exportStatus='';
    } catch(error){exportStatus=error.message;}
    finally {renderExportLimits();}
  }
  async function saveExportLimits() {
    if(exportBusy)return;
    if(![...exportPanel.querySelectorAll('input')].every(input=>input.reportValidity() && input.value!=='')) {
      exportStatus='Enter a whole number within each field’s limits.';renderExportLimits();return;
    }
    exportBusy=true;exportStatus='Saving…';renderExportLimits();
    try {
      const response=await fetch('/export-settings',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(Object.fromEntries(Object.entries(exportValues).map(([key,value])=>[key,Number(value)])))});
      const payload=await response.json();
      if(!response.ok)throw new Error(typeof payload.detail==='string' ? payload.detail : 'Check the limits. Combined source size must be at least the per-file size.');
      exportValues=payload;exportStatus='Export limits saved. New exports use these values; no restart needed.';
    } catch(error){exportStatus=error.message;}
    finally {exportBusy=false;renderExportLimits();}
  }
  renderExportLimits();
  const about = document.getElementById("settingsAbout");
  const aboutView=createAboutSettingsView(about);
  let report='Open to load versions.', copyStatus='';
  let aboutLoaded = false;
  let aboutLoading = false;
  function renderAbout() {
    aboutView.render({report,status:copyStatus,ready:aboutLoaded,onCopy:copyAbout});
  }
  renderAbout();
  async function loadAboutWhenOpen() {
    if (!about.open || aboutLoaded || aboutLoading) return;
    aboutLoading = true;
    report = "Detecting installed versions…";renderAbout();
    try {
      const response = await fetch("/about");
      if (!response.ok) throw new Error();
      const payload = await response.json();
      const rows = Object.entries(payload.components || {});
      for (const [label, version] of [["Plotly (browser)", window.Plotly?.version], ["Cytoscape (browser)", window.cytoscape?.version]]) {
        if (version) rows.push([label, version]);
      }
      report = rows.map(([name, version]) => `${name}: ${version}`).join("\n") + `\n\n${payload.note}`;
      aboutLoaded = true;
    } catch (_) {
      report = "Unable to load versions. Close and reopen About to retry.";
    } finally { aboutLoading = false;renderAbout(); }
  }
  async function copyAbout() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(report);
      } else {
        if (!fallbackCopyText(report)) throw new Error();
      }
      copyStatus = "Copied.";
    } catch (_) { copyStatus = "Select the report text and copy it manually."; }
    renderAbout();
  }
  const {
    userSettingsBtnEl,
    userSettingsPanelEl,
    userSettingsAuthSummaryEl,
    userSettingsStatusEl,
    userSettingsSaveBtnEl,
    userSettingsResetBtnEl,
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
  const authSummaryView=createAuthSummaryView(userSettingsAuthSummaryEl);
  const preferencesView=createSettingsPreferences(userSettingsPanelEl);
  let preferenceDraft=normalizeUserSettings(state.userSettings);
  const settingsNavigation=createSettingsNavigation(userSettingsPanelEl.querySelector('.user-settings-nav'));
  let selectedSection='general';
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

  function selectSettingsSection(section) {
    selectedSection=section;
    userSettingsPanelEl.querySelectorAll("[data-settings-page]").forEach(page => {
      page.hidden = page.dataset.settingsPage !== section;
    });
    settingsNavigation.render(selectedSection,selectSettingsSection);
    userSettingsPanelEl.querySelector(".user-settings-content").scrollTop = 0;
  }
  settingsNavigation.render(selectedSection,selectSettingsSection);
  function updateDirtyStatus() {
    const dirty = JSON.stringify(formSettings()) !== JSON.stringify(normalizeUserSettings(state.userSettings));
    document.getElementById("userSettingsDirty").textContent = dirty ? "Unsaved changes" : "";
  }

  function setPanelOpen(open) {
    if (!userSettingsPanelEl) return;
    userSettingsPanelEl.classList.toggle("is-hidden", !open);
    if (open) {
      const selected = userSettingsPanelEl.querySelector('[data-settings-section][aria-current="page"]');
      if (selected?.classList.contains("is-hidden")) {
        userSettingsPanelEl.querySelector('[data-settings-section="general"]').click();
      }
      renderAuthSummary();
      void loadExportLimits();
      void resourceStorage.load();
      void localAgents.load();
    } else {
      localAgents.hide();
    }
  }

  window.addEventListener('cohortome:review-agent-plans', () => {
    setPanelOpen(true);
    userSettingsPanelEl.querySelector('[data-settings-section="query"]').click();
    document.getElementById('localAgentsSettings').open = true;
    document.getElementById('localAgentsPlans').scrollIntoView({block:'nearest'});
  });

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
    authSummaryView.render(rows);
  }

  function renderPreferences() {
    const available=Array.isArray(state.lmStatus?.providers) ? state.lmStatus.providers : [];
    const providers=available.length ? available : [{id:'system-default',label:'System default',enabled:true}];
    preferencesView.render(preferenceDraft,providers,(key,value)=>{
      preferenceDraft={...preferenceDraft,[key]:value};
      renderPreferences();
      updateDirtyStatus();
    });
  }

  function renderUserSettingsForm() {
    preferenceDraft=normalizeUserSettings(state.userSettings);
    renderPreferences();
    renderAuthSummary();
    updateDirtyStatus();
  }

  function formSettings() {
    return normalizeUserSettings(preferenceDraft);
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
    loadAboutWhenOpen,
    updateDirtyStatus,
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
