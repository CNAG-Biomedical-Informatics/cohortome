import {renderOptions,renderLoadIcon} from './react/ui.js';
import { modalityIcon } from './modalities.js';
import {createDatasetPickerView, createDatasetsAdminView, openDatasetConfirmation} from './react/ui.js';
import { createResourceInstaller } from './resource_install.js';
import { createDatasetBulkAi } from './dataset_bulk_ai.js';
import { openDicomFolderDialog } from './dicom_folder.js';
import { openDatasetAbout } from './dataset_about.js';

export function createDatasetsUi(ctx) {
  const desktop = document.documentElement.dataset.deployment === "desktop";
  const bundledDesktopDatasetIds = new Set(["default", "synthetic-cross-sectional-demo"]);
  const accessLabel = (visibility) => desktop ? "Available in this desktop workspace"
    : ({ all_authenticated: "All authenticated users", restricted: "Restricted", admin_only: "Admin only" }[visibility] || visibility);
  const { refs, state, helpers, callbacks } = ctx;
  const {
    dataDirEl,
    datasetPickerShellEl,
    datasetPickerLegendEl,
    datasetPickerEl,
    loadStatusEl,
    datasetScopeSummaryEl,
    analysisDatasetScopeEl,
    datasetAdminListEl,
  } = refs;
  const { escapeHtml } = helpers;
  const pickerView = datasetPickerEl ? createDatasetPickerView(datasetPickerEl, datasetPickerLegendEl, (id, checked) => {
    const selected = new Set(pendingDatasetSelectionIds());
    if (checked) selected.add(id); else selected.delete(id);
    syncDatasetSelectionFromPicker([...selected]);
  }) : null;
  for (const container of [datasetPickerEl, datasetAdminListEl]) {
    container?.addEventListener('click', event => {
      const button = event.target.closest('[data-dataset-about]');
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      openDatasetAbout(button.dataset.datasetAbout);
    });
  }
  const {
    canManageDataset,
    isWorkspaceAccessible,
    renderGlobalContext,
    prepareAnalysisSessionForDataDir,
    resetQueryWorkspace,
    loadAnalysisCatalog,
    loadSavedCohorts,
    loadQueryDiseaseOptions,
    loadAssayDatasets,
    loadPhenoRankerPatientIds,
    renderPhenoTabAvailability,
    currentTabName,
    setActiveTab,
    renderQueryExecutionMode,
    loadAuthUsers,
    updateLoadButtonAvailability,
  } = callbacks;
  const resourceInstaller = createResourceInstaller({
    escapeHtml,
    refresh: () => loadDatasets({ preservePendingSelection: true }),
    select: (id) => {
      if (!state.pendingDatasetIds.includes(id)) state.pendingDatasetIds.push(id);
      renderDatasetSelect();
      renderDatasetScopeSummary();
      renderLoadButtonState();
      document.getElementById("userSettingsCloseBtn")?.click();
      setActiveTab("datasets");
    },
  });

  const datasetTraitDefinitions = {
    private: {
      label: "Private data",
      legendLabel: "Private",
      svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M8 10V7a4 4 0 1 1 8 0v3"></path><rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M12 14v2"></path></svg>',
    },
    cross_sectional: {
      label: "Cross-sectional study design",
      legendLabel: "Cross-sectional",
      svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M3 12h6m6 0h6M12 3v5m0 8v5"/><circle cx="12" cy="12" r="3"/></svg>',
    },
    longitudinal: {
      label: "Longitudinal study design",
      legendLabel: "Longitudinal",
      svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M6 12h4m4 0h4"/><circle cx="4" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="20" cy="12" r="2"/></svg>',
    },
    clinical: {
      label: "Clinical data",
      legendLabel: "Clinical",
      svg: modalityIcon('clinical', ''),
    },
    assay: {
      label: "Assay data",
      legendLabel: "Assay data",
      svg: modalityIcon('assay', ''),
    },
  };
  datasetTraitDefinitions.imaging = {
    label: "Imaging data", legendLabel: "Imaging",
    svg: modalityIcon('imaging', ''),
  };
  const datasetTraitOrder = ["private", "cross_sectional", "longitudinal", "clinical", "assay", "imaging"];

  function normalizedDatasetStoreStatus(dataset) {
    const storeStatus = dataset && typeof dataset.query_store_status === "object" && dataset.query_store_status
      ? dataset.query_store_status
      : { status: "not_built", ready: false };
    const storeState = String(storeStatus.status || "not_built").trim().toLowerCase();
    return {
      ready: Boolean(storeStatus.ready),
      status: storeState,
      detail: String(storeStatus.last_error || "").trim(),
    };
  }

  function datasetTraitKeys(dataset) {
    const keys = [];
    if (normalizeDataClassification(dataset && dataset.data_classification) === "private") {
      keys.push("private");
    }
    const design = dataset?.study_design;
    if (design === "cross_sectional") {
      keys.push("cross_sectional");
    } else if (design === "longitudinal") {
      keys.push("longitudinal");
    }
    if (Number(dataset && dataset.clinical_record_count ? dataset.clinical_record_count : 0) > 0) {
      keys.push("clinical");
    }
    if (Number(dataset?.laboratory_assay_file_count ?? dataset?.assay_file_count ?? 0) > 0) {
      keys.push("assay");
    }
    if (dataset?.has_imaging) keys.push("imaging");
    return keys;
  }


  function pendingWorkspaceStoreBlocker() {
    const pendingRecords = pendingDatasetRecords();
    if (!pendingRecords.length) {
      return null;
    }
    const blockedRecord = pendingRecords.find((dataset) => {
      const status = normalizedDatasetStoreStatus(dataset);
      const prepareOnUse = desktop
        && bundledDesktopDatasetIds.has(String(dataset.dataset_id || ""))
        && status.status !== "building";
      return !status.ready && !prepareOnUse;
    });
    if (!blockedRecord) {
      return null;
    }
    const storeStatus = normalizedDatasetStoreStatus(blockedRecord);
    const datasetLabel = String(blockedRecord.name || blockedRecord.dataset_id || "Dataset").trim();
    const actionLabel = storeStatus.status === "building"
      ? "Wait for the build to finish, then refresh the dataset list."
      : canManageDataset()
      ? "Rebuild it in Admin > Data."
      : "Ask an admin to rebuild it in Admin > Data.";
    const statusText = ({
      stale: "stale",
      failed: "failed",
      building: "still being built",
      not_built: "not built",
    }[storeStatus.status] || "not ready");
    const detail = storeStatus.detail ? ` ${storeStatus.detail}` : "";
    return {
      datasetId: String(blockedRecord.dataset_id || "").trim(),
      datasetLabel,
      status: storeStatus.status,
      message: `Cannot apply workspace: query store for "${datasetLabel}" is ${statusText}. ${actionLabel}${detail}`,
    };
  }

  function renderLoadButtonState() {
    if (!refs.loadBtnEl) {
      return;
    }
    const activeIds = state.currentDatasetIds.slice();
    const pendingIds = pendingDatasetSelectionIds();
    const hasPendingChange = activeIds.length !== pendingIds.length
      || activeIds.some((item, index) => item !== pendingIds[index]);
    const isUnloading = activeIds.length > 0 && pendingIds.length === 0;
    const hasNoWorkspaceSelection = activeIds.length === 0 && pendingIds.length === 0;
    const blockedByAuth = typeof isWorkspaceAccessible === "function" && !isWorkspaceAccessible();
    const storeBlocker = pendingWorkspaceStoreBlocker();
    refs.loadBtnEl.classList.toggle("is-loading", Boolean(state.loadInFlight));
    refs.loadBtnEl.classList.toggle("has-pending-change", Boolean(hasPendingChange && !state.loadInFlight));
    refs.loadBtnEl.disabled = Boolean(state.loadInFlight || blockedByAuth || storeBlocker || hasNoWorkspaceSelection);
    refs.loadBtnEl.title = storeBlocker
      ? storeBlocker.message
      : hasNoWorkspaceSelection
        ? "Select at least one dataset to create a workspace."
        : "";
    if (loadStatusEl && !state.loadInFlight) {
      if (storeBlocker) {
        loadStatusEl.className = "load-status warning";
        loadStatusEl.textContent = storeBlocker.message;
        loadStatusEl.dataset.datasetStoreBlocker = "true";
      } else if (loadStatusEl.dataset.datasetStoreBlocker === "true") {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = hasPendingChange
          ? "Workspace selection is ready. Click Apply workspace to switch."
          : activeIds.length
            ? "Active workspace is ready."
            : "Select at least one dataset, then click Apply workspace.";
        if (!hasPendingChange) {
          delete loadStatusEl.dataset.datasetStoreBlocker;
        }
      }
    }
    if (datasetPickerShellEl) {
      datasetPickerShellEl.classList.toggle("is-loading", Boolean(state.loadInFlight));
    }
    if (refs.loadBtnLabelEl) {
      refs.loadBtnLabelEl.textContent = state.loadInFlight
        ? "Applying..."
        : isUnloading
          ? "Unload workspace"
          : hasPendingChange
          ? "Apply workspace"
          : "Reload workspace";
    }
    if (refs.loadBtnIconEl) {
      renderLoadIcon(refs.loadBtnIconEl,state.loadInFlight);
    }
  }

  function selectedDatasetIdsFromUi() {
    if (!dataDirEl) {
      return [];
    }
    return Array.from(dataDirEl.selectedOptions || [])
      .map((option) => String(option.value || "").trim())
      .filter(Boolean);
  }

  function currentDatasetId() {
    return state.currentDatasetIds.length === 1 ? state.currentDatasetIds[0] : "";
  }

  function currentDatasetSelectionKey(datasetIds = state.currentDatasetIds) {
    const selected = Array.isArray(datasetIds) ? datasetIds.slice() : [];
    if (!selected.length) {
      return "";
    }
    if (selected.length === 1) {
      return selected[0];
    }
    return `scope--${selected.slice().sort().join("--")}`;
  }

  function currentDatasetRecord() {
    if (state.currentDatasetIds.length !== 1) {
      return null;
    }
    return state.availableDatasets.find((item) => String(item.dataset_id || "") === state.currentDatasetIds[0]) || null;
  }

  function normalizeDatasetQueryGranularityCeiling(value) {
    return String(value || "").trim().toLowerCase() === "detailed" ? "detailed" : "summary";
  }

  function effectiveQueryGranularityCeiling(datasetIds = state.currentDatasetIds) {
    const selected = new Set((Array.isArray(datasetIds) ? datasetIds : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean));
    if (!selected.size) {
      return "summary";
    }
    const records = state.availableDatasets.filter((item) => selected.has(String(item.dataset_id || "")));
    if (!records.length) {
      return "summary";
    }
    return records.every((item) => normalizeDatasetQueryGranularityCeiling(item.query_granularity_ceiling) === "detailed")
      ? "detailed"
      : "summary";
  }

  function normalizeAiProviderAccess(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (["summary_only", "restricted", "safe_summary"].includes(normalized)) {
      return "safe_summary";
    }
    if (["use_thread_mode", "detailed_allowed", "detailed"].includes(normalized)) {
      return "detailed_allowed";
    }
    return ["detailed_allowed", "safe_summary", "blocked"].includes(normalized) ? normalized : "detailed_allowed";
  }

  function normalizeDataClassification(value) {
    return String(value || "").trim().toLowerCase() === "public" ? "public" : "private";
  }

  function selectedProviderDataBoundary() {
    const provider = state.lmStatus && typeof state.lmStatus.provider === "object" ? state.lmStatus.provider : {};
    return String(provider.data_boundary || "").trim().toLowerCase() === "local" ? "local" : "external";
  }

  function effectiveAiProviderAccess(datasetIds = state.currentDatasetIds) {
    const selected = new Set((Array.isArray(datasetIds) ? datasetIds : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean));
    if (!selected.size) {
      return "detailed_allowed";
    }
    const records = state.availableDatasets.filter((item) => selected.has(String(item.dataset_id || "")));
    if (!records.length) {
      return "detailed_allowed";
    }
    if (selectedProviderDataBoundary() !== "local" && records.some((item) => normalizeDataClassification(item.data_classification) === "private")) {
      return "blocked";
    }
    if (records.some((item) => normalizeAiProviderAccess(item.ai_provider_access) === "blocked")) {
      return "blocked";
    }
    if (records.some((item) => normalizeAiProviderAccess(item.ai_provider_access) === "safe_summary")) {
      return "safe_summary";
    }
    return "detailed_allowed";
  }

  function queryWorkspacePolicyExplanation() {
    const records = selectedDatasetRecords();
    if (!records.length) {
      return null;
    }
    const effectiveProviderAccess = effectiveAiProviderAccess();
    const effectiveDisclosure = effectiveQueryGranularityCeiling();
    const blockedCount = records.filter((item) => normalizeAiProviderAccess(item.ai_provider_access) === "blocked").length;
    const safeSummaryCount = records.filter((item) => normalizeAiProviderAccess(item.ai_provider_access) === "safe_summary").length;
    const privateDatasetCount = records.filter((item) => normalizeDataClassification(item.data_classification) === "private").length;
    if (effectiveProviderAccess === "blocked") {
      if (privateDatasetCount > 0 && selectedProviderDataBoundary() !== "local") {
        return `AI provider policy: Blocked. The selected external provider cannot receive context from ${privateDatasetCount} private dataset${privateDatasetCount === 1 ? "" : "s"}.`;
      }
      return blockedCount > 0
        ? `AI provider policy: Blocked. ${blockedCount} selected dataset${blockedCount === 1 ? "" : "s"} require this stricter policy.`
        : "AI provider policy: Blocked.";
    }
    if (effectiveProviderAccess === "safe_summary") {
      return safeSummaryCount > 0
        ? `AI provider policy: Safe summary. ${safeSummaryCount} selected dataset${safeSummaryCount === 1 ? "" : "s"} require provider-safe summary access.`
        : "AI provider policy: Safe summary.";
    }
    if (records.length > 1 && effectiveDisclosure !== "detailed") {
      const summaryCount = records.filter((item) => normalizeDatasetQueryGranularityCeiling(item.query_granularity_ceiling) === "summary").length;
      return `Query detail policy: Summary only. ${summaryCount} selected dataset${summaryCount === 1 ? "" : "s"} require the stricter in-app disclosure mode.`;
    }
    if (records.length > 1) {
      return "Mixed workspace: the strictest selected dataset policy is applied automatically.";
    }
    return null;
  }

  function syncQueryGranularityWithWorkspacePolicy(options = {}) {
    const { announce = false } = options;
    const nextMode = effectiveQueryGranularityCeiling();
    const changed = state.queryGranularityMode !== nextMode;
    state.queryGranularityMode = nextMode;
    if (state.queryGranularityMode !== "detailed") {
      state.queryFollowMemoryEnabled = false;
    }
    if (changed && (state.queryTurns.length || state.queryHistory.length)) {
      resetQueryWorkspace();
      if (announce && refs.queryStatusEl) {
        refs.queryStatusEl.className = "query-status";
        refs.queryStatusEl.textContent = `Query thread reset. Workspace mode is now ${nextMode === "detailed" ? "Detailed" : "Summary"}.`;
      }
    }
    renderPhenoTabAvailability();
    if (nextMode !== "detailed" && currentTabName() === "pheno") {
      setActiveTab("query");
      if (loadStatusEl) {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = "Pheno-Ranker was closed because this workspace is now Summary-only.";
      }
    }
    renderQueryExecutionMode();
  }

  function pendingDatasetSelectionIds() {
    return state.pendingDatasetIds.slice();
  }

  function selectedDatasetRecords() {
    const selected = new Set(state.currentDatasetIds);
    return state.availableDatasets.filter((item) => selected.has(String(item.dataset_id || "")));
  }

  function pendingDatasetRecords() {
    const selected = new Set(pendingDatasetSelectionIds());
    return state.availableDatasets.filter((item) => selected.has(String(item.dataset_id || "")));
  }

  function datasetScopeLabel() {
    const records = selectedDatasetRecords();
    if (!records.length) {
      return "No dataset selected";
    }
    const names = records
      .map((item) => String(item.name || item.dataset_id || "Dataset").trim())
      .filter(Boolean);
    if (names.length <= 2) {
      return names.join(" + ");
    }
    return `${names[0]}, ${names[1]} + ${names.length - 2} more`;
  }

  function pendingDatasetScopeLabel() {
    const records = pendingDatasetRecords();
    if (!records.length) {
      return "No dataset selected";
    }
    const names = records
      .map((item) => String(item.name || item.dataset_id || "Dataset").trim())
      .filter(Boolean);
    if (names.length <= 2) {
      return names.join(" + ");
    }
    return `${names[0]}, ${names[1]} + ${names.length - 2} more`;
  }

  function datasetLabelsForIds(ids) {
    const selected = new Set((Array.isArray(ids) ? ids : []).map((item) => String(item || "").trim()).filter(Boolean));
    return state.availableDatasets
      .filter((item) => selected.has(String(item.dataset_id || "")))
      .map((item) => String(item.name || item.dataset_id || "Dataset").trim())
      .filter(Boolean);
  }

  function effectiveDatasetUserLabels(dataset) {
    const users = Array.isArray(state.availableAuthUsers) ? state.availableAuthUsers : [];
    if (!users.length) {
      return [];
    }
    const visibility = String(dataset && dataset.visibility || "all_authenticated");
    const allowedUsers = new Set((Array.isArray(dataset && dataset.allowed_users) ? dataset.allowed_users : [])
      .map((item) => String(item || "").trim().toLowerCase())
      .filter(Boolean));
    const allowedGroups = new Set((Array.isArray(dataset && dataset.allowed_groups) ? dataset.allowed_groups : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean));
    return users
      .filter((user) => {
        const username = String(user && user.username || "").trim().toLowerCase();
        const role = String(user && user.role || "user").trim().toLowerCase();
        const enabled = Boolean(user && user.enabled !== false);
        const groups = new Set((Array.isArray(user && user.groups) ? user.groups : [])
          .map((item) => String(item || "").trim())
          .filter(Boolean));
        if (!enabled) {
          return false;
        }
        if (role === "admin") {
          return true;
        }
        if (visibility === "all_authenticated") {
          return true;
        }
        if (visibility === "admin_only") {
          return false;
        }
        if (allowedUsers.has(username)) {
          return true;
        }
        for (const group of groups) {
          if (allowedGroups.has(group)) {
            return true;
          }
        }
        return false;
      })
      .map((user) => String(user.display_name || user.username || "").trim())
      .filter(Boolean);
  }

  function renderAnalysisDatasetScope() {
    if (!analysisDatasetScopeEl) {
      return;
    }
    const labels = datasetLabelsForIds(state.currentDatasetIds);
    analysisDatasetScopeEl.textContent = labels.length > 1
      ? `Workspace datasets: ${labels.join(", ")}.`
      : labels.length
        ? `Workspace dataset: ${labels[0]}.`
        : "Workspace dataset: none selected.";
  }

  function renderDatasetScopeSummary() {
    if (!datasetScopeSummaryEl) {
      return;
    }
    const records = selectedDatasetRecords();
    if (!records.length) {
    const pendingLabel = pendingDatasetScopeLabel();
    const hasPendingSelection = pendingDatasetSelectionIds().length > 0;
    const storeBlocker = pendingWorkspaceStoreBlocker();
    datasetScopeSummaryEl.textContent = hasPendingSelection
        ? `Active workspace: no dataset selected. Pending workspace: ${pendingLabel}.${storeBlocker ? ` ${storeBlocker.message}` : " Click Apply workspace to switch."}`
        : "Active workspace: no dataset selected.";
      return;
    }
    const selectedCount = records.length;
    const authorizedCount = state.availableDatasets.length;
    const noun = selectedCount === 1 ? "dataset" : "datasets";
    const activeIds = state.currentDatasetIds.slice();
    const pendingIds = pendingDatasetSelectionIds();
    const sameSelection = activeIds.length === pendingIds.length && activeIds.every((item, index) => item === pendingIds[index]);
    const base = `Active workspace: ${datasetScopeLabel()} (${selectedCount} ${noun}${authorizedCount ? `, ${authorizedCount} authorized` : ""}).`;
    const storeBlocker = pendingWorkspaceStoreBlocker();
    datasetScopeSummaryEl.textContent = sameSelection
      ? base
      : `${base} Pending workspace: ${pendingDatasetScopeLabel()}.${storeBlocker ? ` ${storeBlocker.message}` : " Click Apply workspace to switch."}`;
  }

  function renderDatasetSelect() {
    if (!dataDirEl) {
      return;
    }
    const selectedIds = new Set(pendingDatasetSelectionIds());
    renderOptions(dataDirEl,state.availableDatasets.length ? state.availableDatasets.map(dataset=>({
      value:String(dataset.dataset_id || ""),label:String(dataset.name || dataset.dataset_id || "Unnamed dataset")
    })) : [{value:"",label:"No dataset available"}]);
    for(const option of dataDirEl.options) option.selected=selectedIds.has(option.value);
    if(!state.availableDatasets.length) return;
    dataDirEl.dataset.scopeId = currentDatasetSelectionKey();
    renderDatasetPicker();
    renderDatasetAdminList();
    renderDatasetScopeSummary();
  }

  function renderDatasetPicker() {
    if (!pickerView) return;
    const selectedIds = new Set(pendingDatasetSelectionIds());
    const activeIds = new Set(state.currentDatasetIds);
    const present = new Set();
    const trait = key => ({key, ...datasetTraitDefinitions[key]});
    const datasets = state.availableDatasets.map(dataset => {
      const id = String(dataset.dataset_id || "");
      const keys = datasetTraitKeys(dataset);
      keys.forEach(key => present.add(key));
      return {
        id, name: dataset.name || id || "Unnamed dataset",
        checked: selectedIds.has(id), active: activeIds.has(id),
        description: String(dataset.description || "").trim(),
        tags: Array.isArray(dataset.content_tags) ? dataset.content_tags.map(item => String(item || "").trim()).filter(Boolean) : [],
        groups: Array.isArray(dataset.allowed_groups) ? dataset.allowed_groups : [],
        users: Array.isArray(dataset.allowed_users) ? dataset.allowed_users : [],
        traits: keys.map(trait), store: normalizedDatasetStoreStatus(dataset),
        access: accessLabel(String(dataset.visibility || "all_authenticated")),
      };
    });
    pickerView.render({datasets, desktop, legend: datasetTraitOrder.filter(key => present.has(key)).map(trait)});
  }

  const adminView = datasetAdminListEl ? createDatasetsAdminView(datasetAdminListEl, id => {
    const dataset = state.availableDatasets.find(item => item.dataset_id === id);
    if (dataset && canManageDataset()) openDicomFolderDialog([{id, name: dataset.name || id}], escapeHtml);
  }) : null;
  const bulkAiUi = createDatasetBulkAi({reload: loadDatasets,
    canManage: canManageDataset, onChange: renderDatasetAdminList});
  function renderDatasetAdminList() {
    if (!adminView) return;
    if (!canManageDataset() || !state.availableDatasets.length) {
      adminView.render({message: !canManageDataset()
        ? "Dataset administration is only visible to administrators."
        : "No dataset administration entries available."});
      return;
    }
    const datasets = state.availableDatasets.map(dataset => {
      const datasetId = String(dataset.dataset_id || "");
      const visibility = String(dataset.visibility || "all_authenticated");
      const dataClassification = normalizeDataClassification(dataset.data_classification);
      const description = String(dataset.description || "").trim();
      const contentTags = Array.isArray(dataset.content_tags) ? dataset.content_tags.map((item) => String(item || "").trim()).filter(Boolean) : [];
      const allowedGroups = Array.isArray(dataset.allowed_groups) ? dataset.allowed_groups : [];
      const allowedUsers = Array.isArray(dataset.allowed_users) ? dataset.allowed_users : [];
      const effectiveUsers = effectiveDatasetUserLabels(dataset);
      const feedback = state.datasetAdminFeedback[datasetId];
      const storeStatus = dataset && typeof dataset.query_store_status === "object" && dataset.query_store_status
        ? dataset.query_store_status
        : { status: "not_built", ready: false };
      const storeState = String(storeStatus.status || "not_built").trim().toLowerCase();
      const storeReady = Boolean(storeStatus.ready);
      const storeLabel = storeReady
        ? "Ready"
        : ({
          building: "Building",
          stale: "Stale",
          failed: "Failed",
          not_built: "Not built",
        }[storeState] || "Not built");
      const storeBuilding = storeState === "building";
      const storeButtonLabel = storeBuilding
        ? "Building query store…"
        : storeState === "failed"
          ? "Retry build"
          : storeReady || storeState === "stale"
            ? "Rebuild query store"
            : "Build query store";
      const storeDetail = String(storeStatus.last_error || "").trim()
        || (storeStatus.last_built_at ? `Last built: ${storeStatus.last_built_at}` : "The query store has not been built yet.");

      const aiAccess = normalizeAiProviderAccess(String(dataset.ai_provider_access || "detailed_allowed"));
      const behavior = aiAccess === "blocked" ? "No AI provider receives dataset context."
        : dataClassification === "private"
          ? aiAccess === "safe_summary"
            ? "Local providers may receive a safe structural summary. External providers are blocked."
            : "Local providers may receive detailed context. External providers are blocked."
          : aiAccess === "safe_summary"
            ? "Approved providers may receive only a safe structural summary."
            : "Approved providers may receive detailed context when the in-app result allows it.";
      return {dataset, datasetId, visibility, dataClassification, description, contentTags,
        allowedGroups, allowedUsers, effectiveUsers, feedback, storeState, storeReady,
        storeLabel, storeBuilding, storeButtonLabel, storeDetail, aiAccess, behavior,
        name: dataset.name || datasetId || "Unnamed dataset", access: accessLabel(visibility),
        granularity: normalizeDatasetQueryGranularityCeiling(dataset.query_granularity_ceiling),
        bundled: bundledDesktopDatasetIds.has(datasetId)};
    });
    adminView.render({datasets, desktop, bulk: bulkAiUi.snapshot(state.availableDatasets)});
  }

  function setDatasetAdminFeedback(datasetId, text, tone = "success", autoClearMs = 2600) {
    const key = String(datasetId || "").trim();
    if (!key) {
      return;
    }
    state.datasetAdminFeedback = {
      ...state.datasetAdminFeedback,
      [key]: { text: String(text || ""), tone },
    };
    renderDatasetAdminList();
    if (state.datasetAdminFeedbackTimers[key]) {
      window.clearTimeout(state.datasetAdminFeedbackTimers[key]);
    }
    if (autoClearMs > 0) {
      state.datasetAdminFeedbackTimers[key] = window.setTimeout(() => {
        delete state.datasetAdminFeedback[key];
        delete state.datasetAdminFeedbackTimers[key];
        renderDatasetAdminList();
      }, autoClearMs);
    }
  }

  async function saveDatasetAccess(datasetId) {
    if (!datasetAdminListEl || !canManageDataset()) {
      return;
    }
    const visibilityEl = datasetAdminListEl.querySelector(`[data-dataset-visibility="${CSS.escape(datasetId)}"]`);
    const dataClassificationEl = datasetAdminListEl.querySelector(`[data-dataset-classification="${CSS.escape(datasetId)}"]`);
    const groupsEl = datasetAdminListEl.querySelector(`[data-dataset-groups="${CSS.escape(datasetId)}"]`);
    const usersEl = datasetAdminListEl.querySelector(`[data-dataset-users="${CSS.escape(datasetId)}"]`);
    const queryGranularityEl = datasetAdminListEl.querySelector(`[data-dataset-query-granularity="${CSS.escape(datasetId)}"]`);
    const aiProviderAccessEl = datasetAdminListEl.querySelector(`[data-dataset-ai-provider-access="${CSS.escape(datasetId)}"]`);
    if (!visibilityEl || !dataClassificationEl || !groupsEl || !usersEl || !queryGranularityEl || !aiProviderAccessEl) {
      return;
    }
    const allowedGroups = String(groupsEl.value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const allowedUsers = String(usersEl.value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const requestedAiProviderAccess = String(aiProviderAccessEl.value || "detailed_allowed").trim();
    loadStatusEl.className = "load-status loading";
    loadStatusEl.textContent = `Saving access for ${datasetId}...`;
    setDatasetAdminFeedback(datasetId, "Saving settings...", "success", 0);
    try {
      const response = await fetch(`/datasets/${encodeURIComponent(datasetId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...(!desktop ? { visibility: visibilityEl.value, allowed_groups: allowedGroups, allowed_users: allowedUsers } : {}),
          data_classification: dataClassificationEl.value,
          query_granularity_ceiling: queryGranularityEl.value,
          ai_provider_access: requestedAiProviderAccess,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Unable to save dataset access.");
      }
      await loadDatasets({ preservePendingSelection: true });
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = `Updated settings for ${datasetId}.`;
      setDatasetAdminFeedback(datasetId, "Settings saved.", "success");
    } catch (error) {
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = error && error.message ? error.message : "Unable to save dataset access.";
      setDatasetAdminFeedback(
        datasetId,
        error && error.message ? error.message : "Unable to save dataset settings.",
        "error",
        4200,
      );
    }
  }

  function removeDataset(datasetId) {
    if (!canManageDataset()) return;
    if (bundledDesktopDatasetIds.has(datasetId)) return;
    const dataset = state.availableDatasets.find(item => item.dataset_id === datasetId);
    if (!dataset) return;
    openDatasetConfirmation({kind:'remove', datasets:[dataset], onReload:()=>window.location.reload(),
      onApply:async ({confirmation,remove_files})=>{
        if (!canManageDataset() || bundledDesktopDatasetIds.has(datasetId)) throw new Error("This dataset cannot be removed.");
        const response=await fetch(`/resources/datasets/${encodeURIComponent(datasetId)}/remove`, {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({confirmation,remove_files}),
        });
        const payload=await response.json();
        if (!response.ok) throw new Error(payload.detail || "Unable to remove dataset.");
        return {status:payload.message,complete:true};
      }});
  }

  async function prepareDatasetStore(datasetId) {
    if (!datasetId || !canManageDataset()) {
      return;
    }
    loadStatusEl.className = "load-status loading";
    loadStatusEl.textContent = `Building query store for ${datasetId}...`;
    setDatasetAdminFeedback(datasetId, "Building query store...", "success", 0);
    try {
      const response = await fetch(`/datasets/${encodeURIComponent(datasetId)}/prepare-store`, {
        method: "POST",
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Unable to build query store.");
      }
      await loadDatasets({ preservePendingSelection: true });
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = `Query store rebuilt for ${datasetId}.`;
      setDatasetAdminFeedback(datasetId, "Query store rebuilt.", "success");
    } catch (error) {
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = error && error.message ? error.message : "Unable to build query store.";
      setDatasetAdminFeedback(
        datasetId,
        error && error.message ? error.message : "Unable to build query store.",
        "error",
        4200,
      );
    }
  }

  function syncDatasetSelectionFromPicker(selection) {
    if (!dataDirEl || !datasetPickerEl) {
      return;
    }
    const selected = selection || Array.from(datasetPickerEl.querySelectorAll("[data-dataset-checkbox]:checked"))
      .map((input) => String(input.getAttribute("data-dataset-checkbox") || "").trim())
      .filter(Boolean);
    Array.from(dataDirEl.options).forEach((option) => {
      option.selected = selected.includes(String(option.value || "").trim());
    });
    state.pendingDatasetIds = selected;
    renderDatasetPicker();
    renderDatasetAdminList();
    renderDatasetScopeSummary();
    renderLoadButtonState();
    updateLoadButtonAvailability();
  }

  async function loadDatasets(options = {}) {
    resourceInstaller.setAllowed(canManageDataset());
    if (!dataDirEl) {
      return;
    }
    const pendingBeforeRefresh = options.preservePendingSelection === true
      ? state.pendingDatasetIds.slice()
      : [];
    try {
      const response = await fetch("/datasets");
      if (!response.ok) {
        throw new Error("Unable to load datasets.");
      }
      const payload = await response.json();
      state.availableDatasets = Array.isArray(payload.datasets) ? payload.datasets : [];
      state.currentDatasetIds = Array.isArray(payload.current_dataset_ids) ? payload.current_dataset_ids : [];
      const availableIds = new Set(state.availableDatasets.map((item) => String(item.dataset_id || "")));
      state.pendingDatasetIds = options.preservePendingSelection === true
        ? pendingBeforeRefresh.filter((item) => availableIds.has(item))
        : state.currentDatasetIds.slice();
      state.currentDatasetScopeId = String(payload.current_dataset_scope_id || "");
      renderDatasetSelect();
      if (dataDirEl) {
        dataDirEl.dataset.scopeId = state.currentDatasetScopeId;
      }
      renderDatasetScopeSummary();
      renderAnalysisDatasetScope();
      syncQueryGranularityWithWorkspacePolicy();
      renderLoadButtonState();
      updateLoadButtonAvailability();
      if (canManageDataset()) {
        void loadAuthUsers();
      }
    } catch (_error) {
      state.availableDatasets = [];
      state.currentDatasetIds = [];
      state.pendingDatasetIds = [];
      state.currentDatasetScopeId = "";
      renderDatasetSelect();
      if (dataDirEl) {
        dataDirEl.dataset.scopeId = "";
      }
      renderDatasetScopeSummary();
      renderAnalysisDatasetScope();
      syncQueryGranularityWithWorkspacePolicy();
      renderLoadButtonState();
      updateLoadButtonAvailability();
    }
  }

  return {
    resourceInstaller,
    renderLoadButtonState,
    selectedDatasetIdsFromUi,
    currentDatasetId,
    currentDatasetSelectionKey,
    currentDatasetRecord,
    normalizeDatasetQueryGranularityCeiling,
    effectiveQueryGranularityCeiling,
    normalizeAiProviderAccess,
    effectiveAiProviderAccess,
    queryWorkspacePolicyExplanation,
    syncQueryGranularityWithWorkspacePolicy,
    pendingDatasetSelectionIds,
    selectedDatasetRecords,
    pendingDatasetRecords,
    datasetScopeLabel,
    pendingDatasetScopeLabel,
    datasetLabelsForIds,
    effectiveDatasetUserLabels,
    renderAnalysisDatasetScope,
    renderDatasetScopeSummary,
    pendingWorkspaceStoreBlocker,
    renderDatasetSelect,
    renderDatasetPicker,
    renderDatasetAdminList,
    setDatasetAdminFeedback,
    saveDatasetAccess,
    prepareDatasetStore,
    removeDataset,
    syncDatasetSelectionFromPicker,
    loadDatasets,
  };
}
