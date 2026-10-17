import { modalityIcon } from './modalities.js';

export function createDatasetsUi(ctx) {
  const desktop = document.documentElement.dataset.deployment === "desktop";
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

  const datasetTraitDefinitions = {
    private: {
      label: "Private data",
      legendLabel: "Private",
      svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M8 10V7a4 4 0 1 1 8 0v3"></path><rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M12 14v2"></path></svg>',
    },
    cross_sectional: {
      label: "Cross-sectional clinical records",
      legendLabel: "Cross-sectional",
      svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="8" r="3"></circle><path d="M6 20a6 6 0 0 1 12 0"></path></svg>',
    },
    longitudinal: {
      label: "Longitudinal clinical records",
      legendLabel: "Longitudinal",
      svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 18h16"></path><path d="m5 15 4-4 3 2 7-7"></path></svg>',
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
    const representation = String(dataset && dataset.clinical_representation ? dataset.clinical_representation : "").trim().toLowerCase();
    if (representation === "person") {
      keys.push("cross_sectional");
    } else if (representation === "snapshot") {
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

  function renderDatasetTraitIcon(key, decorative = false) {
    const definition = datasetTraitDefinitions[key];
    if (!definition) {
      return "";
    }
    const accessibility = decorative
      ? 'aria-hidden="true"'
      : `role="img" aria-label="${escapeHtml(definition.label)}" title="${escapeHtml(definition.label)}"`;
    return `<span class="dataset-trait-icon dataset-trait-icon-${escapeHtml(key)}" data-dataset-trait="${escapeHtml(key)}" ${accessibility}>${definition.svg}</span>`;
  }

  function renderDatasetTraitLegend(datasets) {
    if (!datasetPickerLegendEl) {
      return;
    }
    const present = new Set();
    (Array.isArray(datasets) ? datasets : []).forEach((dataset) => {
      datasetTraitKeys(dataset).forEach((key) => present.add(key));
    });
    const keys = datasetTraitOrder.filter((key) => present.has(key));
    datasetPickerLegendEl.classList.toggle("is-hidden", !keys.length);
    datasetPickerLegendEl.innerHTML = keys.length
      ? `<span class="dataset-trait-legend-title">Legend</span>${keys.map((key) => {
          const definition = datasetTraitDefinitions[key];
          return `<span class="dataset-trait-legend-item" data-dataset-trait-legend="${escapeHtml(key)}">${renderDatasetTraitIcon(key, true)}<span>${escapeHtml(definition.legendLabel)}</span></span>`;
        }).join("")}`
      : "";
  }

  function pendingWorkspaceStoreBlocker() {
    const pendingRecords = pendingDatasetRecords();
    if (!pendingRecords.length) {
      return null;
    }
    const blockedRecord = pendingRecords.find((dataset) => !normalizedDatasetStoreStatus(dataset).ready);
    if (!blockedRecord) {
      return null;
    }
    const storeStatus = normalizedDatasetStoreStatus(blockedRecord);
    const datasetLabel = String(blockedRecord.name || blockedRecord.dataset_id || "Dataset").trim();
    const actionLabel = storeStatus.status === "building"
      ? "Wait for preparation to finish, then refresh the dataset list."
      : canManageDataset()
      ? "Prepare or rebuild it in Admin > Data."
      : "Ask an admin to prepare it in Admin > Data.";
    const statusText = ({
      stale: "stale",
      failed: "failed",
      building: "still being prepared",
      not_built: "not prepared",
    }[storeStatus.status] || "not ready");
    const detail = storeStatus.detail ? ` ${storeStatus.detail}` : "";
    return {
      datasetId: String(blockedRecord.dataset_id || "").trim(),
      datasetLabel,
      status: storeStatus.status,
      message: `Cannot apply workspace: dataset store for "${datasetLabel}" is ${statusText}. ${actionLabel}${detail}`,
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
      refs.loadBtnIconEl.innerHTML = state.loadInFlight
        ? '<span class="button-spinner" aria-hidden="true"></span>'
        : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
             <path d="M12 3v12"></path>
             <path d="m7 10 5 5 5-5"></path>
             <path d="M5 21h14"></path>
           </svg>`;
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
    dataDirEl.innerHTML = "";
    if (!state.availableDatasets.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No dataset available";
      dataDirEl.appendChild(option);
      return;
    }
    state.availableDatasets.forEach((dataset) => {
      const option = document.createElement("option");
      option.value = String(dataset.dataset_id || "");
      option.textContent = String(dataset.name || dataset.dataset_id || "Unnamed dataset");
      if (selectedIds.has(option.value)) {
        option.selected = true;
      }
      dataDirEl.appendChild(option);
    });
    dataDirEl.dataset.scopeId = currentDatasetSelectionKey();
    renderDatasetPicker();
    renderDatasetAdminList();
    renderDatasetScopeSummary();
  }

  function renderDatasetPicker() {
    if (!datasetPickerEl) {
      return;
    }
    const selectedIds = new Set(pendingDatasetSelectionIds());
    const activeIds = new Set(state.currentDatasetIds);
    renderDatasetTraitLegend(state.availableDatasets);
    if (!state.availableDatasets.length) {
      datasetPickerEl.innerHTML = '<div class="empty">No dataset available.</div>';
      return;
    }
    datasetPickerEl.innerHTML = state.availableDatasets.map((dataset) => {
      const datasetId = String(dataset.dataset_id || "");
      const checked = selectedIds.has(datasetId);
      const active = activeIds.has(datasetId);
      const visibility = String(dataset.visibility || "all_authenticated");
      const description = String(dataset.description || "").trim();
      const contentTags = Array.isArray(dataset.content_tags) ? dataset.content_tags.map((item) => String(item || "").trim()).filter(Boolean) : [];
      const allowedGroups = Array.isArray(dataset.allowed_groups) ? dataset.allowed_groups : [];
      const allowedUsers = Array.isArray(dataset.allowed_users) ? dataset.allowed_users : [];
      const traitKeys = datasetTraitKeys(dataset);
      const storeStatus = normalizedDatasetStoreStatus(dataset);
      const stateBadges = [];
      if (active) {
        stateBadges.push('<span class="dataset-picker-state dataset-picker-state-active">Active</span>');
      }
      if (checked && !active) {
        stateBadges.push('<span class="dataset-picker-state dataset-picker-state-pending">Pending add</span>');
      }
      if (active && !checked) {
        stateBadges.push('<span class="dataset-picker-state dataset-picker-state-removal">Pending removal</span>');
      }
      if (checked && !storeStatus.ready) {
        stateBadges.push(`<span class="dataset-picker-state dataset-picker-state-removal">${escapeHtml(storeStatus.status.replaceAll("_", " "))}</span>`);
      }
      return `
        <label class="dataset-picker-card${checked ? " is-selected" : ""}${active ? " is-active" : ""}${checked && !active ? " is-pending-add" : ""}${active && !checked ? " is-pending-removal" : ""}" data-dataset-card="${escapeHtml(datasetId)}">
          <input type="checkbox" data-dataset-checkbox="${escapeHtml(datasetId)}" ${checked ? "checked" : ""}>
          <div>
            <div class="dataset-picker-title">
              <span>${escapeHtml(dataset.name || datasetId || "Unnamed dataset")}</span>
              ${stateBadges.join("")}
            </div>
            ${traitKeys.length ? `<div class="dataset-trait-icons">${traitKeys.map((key) => renderDatasetTraitIcon(key)).join("")}</div>` : ""}
            <div class="dataset-picker-meta">
              <span class="dataset-picker-tag">${escapeHtml(datasetId)}</span>
              <span class="dataset-picker-tag">${escapeHtml(accessLabel(visibility))}</span>
              ${contentTags.map((tag) => `<span class="dataset-picker-tag dataset-picker-tag-content">${escapeHtml(tag)}</span>`).join("")}
              ${!desktop && allowedGroups.length ? `<span class="dataset-picker-tag">groups: ${escapeHtml(allowedGroups.join(", "))}</span>` : ""}
              ${!desktop && allowedUsers.length ? `<span class="dataset-picker-tag">users: ${escapeHtml(allowedUsers.join(", "))}</span>` : ""}
            </div>
            ${description ? `<div class="dataset-picker-description" title="${escapeHtml(description)}">${escapeHtml(description)}</div>` : ""}
          </div>
        </label>
      `;
    }).join("");
  }

  function renderDatasetAdminList() {
    if (!datasetAdminListEl) {
      return;
    }
    if (!canManageDataset()) {
      datasetAdminListEl.innerHTML = '<div class="empty">Dataset administration is only visible to administrators.</div>';
      return;
    }
    if (!state.availableDatasets.length) {
      datasetAdminListEl.innerHTML = '<div class="empty">No dataset administration entries available.</div>';
      return;
    }
    const expandedDatasetIds = new Set(
      Array.from(datasetAdminListEl.querySelectorAll("[data-dataset-admin-card][open]"))
        .map((item) => String(item.getAttribute("data-dataset-admin-card") || "").trim())
        .filter(Boolean),
    );
    datasetAdminListEl.innerHTML = state.availableDatasets.map((dataset) => {
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
      const storeButtonLabel = storeReady ? "Rebuild store" : "Prepare store";
      const storeDetail = String(storeStatus.last_error || "").trim()
        || (storeStatus.last_built_at ? `Last built: ${storeStatus.last_built_at}` : "No prepared DuckDB store is available yet.");
      return `
        <details class="dataset-admin-card" data-dataset-admin-card="${escapeHtml(datasetId)}" ${expandedDatasetIds.has(datasetId) ? "open" : ""}>
          <summary class="dataset-admin-summary">
            <span class="dataset-admin-summary-main">
              <span class="dataset-picker-title">${escapeHtml(dataset.name || datasetId || "Unnamed dataset")}</span>
              <span class="dataset-picker-meta">
                <span class="dataset-picker-tag">${escapeHtml(datasetId)}</span>
                <span class="dataset-picker-tag">${escapeHtml(accessLabel(visibility))}</span>
                <span class="dataset-picker-tag">${escapeHtml(dataClassification)} data</span>
              </span>
            </span>
            <span class="dataset-picker-tag ${storeReady ? "dataset-picker-tag-ready" : storeState === "failed" ? "dataset-picker-tag-danger" : "dataset-picker-tag-warning"}">${escapeHtml(storeLabel)}</span>
          </summary>
          <div class="dataset-admin-body">
            <div class="dataset-picker-title">
              <span>${escapeHtml(dataset.name || datasetId || "Unnamed dataset")}</span>
            </div>
            <div class="dataset-picker-meta">
                <span class="dataset-picker-tag">${escapeHtml(datasetId)}</span>
                <span class="dataset-picker-tag">${escapeHtml(accessLabel(visibility))}</span>
                <span class="dataset-picker-tag">${escapeHtml(dataClassification)} data</span>
              ${contentTags.map((tag) => `<span class="dataset-picker-tag dataset-picker-tag-content">${escapeHtml(tag)}</span>`).join("")}
              ${!desktop && allowedGroups.length ? `<span class="dataset-picker-tag">groups: ${escapeHtml(allowedGroups.join(", "))}</span>` : ""}
              ${!desktop && allowedUsers.length ? `<span class="dataset-picker-tag">users: ${escapeHtml(allowedUsers.join(", "))}</span>` : ""}
            </div>
            ${description ? `<div class="dataset-picker-description">${escapeHtml(description)}</div>` : ""}
            <div class="dataset-picker-access">
              <div class="dataset-policy-section">
                <div class="dataset-policy-heading">${desktop ? "Data classification and detail" : "Access and classification"}</div>
                <div class="section-note">${desktop ? "This desktop workspace has one local owner. Classification and model policies still control how data may be shared." : "Visibility controls who can use the dataset inside COHORTome. Classification controls whether its data may be sent outside this deployment."}</div>
                <div class="dataset-picker-access-row${desktop ? " is-hidden" : ""}">
                  <label for="dataset-visibility-${escapeHtml(datasetId)}">Visibility</label>
                  <select id="dataset-visibility-${escapeHtml(datasetId)}" data-dataset-visibility="${escapeHtml(datasetId)}">
                    <option value="all_authenticated" ${visibility === "all_authenticated" ? "selected" : ""}>All authenticated users</option>
                    <option value="restricted" ${visibility === "restricted" ? "selected" : ""}>Restricted</option>
                    <option value="admin_only" ${visibility === "admin_only" ? "selected" : ""}>Admin only</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-classification-${escapeHtml(datasetId)}">Data classification</label>
                  <select id="dataset-classification-${escapeHtml(datasetId)}" data-dataset-classification="${escapeHtml(datasetId)}">
                    <option value="private" ${dataClassification === "private" ? "selected" : ""}>Private data</option>
                    <option value="public" ${dataClassification === "public" ? "selected" : ""}>Public data</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row${desktop ? " is-hidden" : ""}">
                  <label for="dataset-groups-${escapeHtml(datasetId)}">Allowed groups</label>
                  <input id="dataset-groups-${escapeHtml(datasetId)}" data-dataset-groups="${escapeHtml(datasetId)}" value="${escapeHtml(allowedGroups.join(", "))}" placeholder="e.g. cnag, ibd-team">
                </div>
                <div class="dataset-picker-access-row${desktop ? " is-hidden" : ""}">
                  <label for="dataset-users-${escapeHtml(datasetId)}">Allowed users</label>
                  <input id="dataset-users-${escapeHtml(datasetId)}" data-dataset-users="${escapeHtml(datasetId)}" value="${escapeHtml(allowedUsers.join(", "))}" placeholder="e.g. mrueda, alice">
                </div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-query-granularity-${escapeHtml(datasetId)}">In-app detail ceiling</label>
                  <select id="dataset-query-granularity-${escapeHtml(datasetId)}" data-dataset-query-granularity="${escapeHtml(datasetId)}">
                    <option value="summary" ${normalizeDatasetQueryGranularityCeiling(dataset.query_granularity_ceiling) === "summary" ? "selected" : ""}>Summary only</option>
                    <option value="detailed" ${normalizeDatasetQueryGranularityCeiling(dataset.query_granularity_ceiling) === "detailed" ? "selected" : ""}>Detailed allowed</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row${desktop ? " is-hidden" : ""}">
                  <label>Users with access</label>
                  <div class="identity-tags">
                    ${effectiveUsers.length
                      ? effectiveUsers.map((label) => `<span class="identity-tag">${escapeHtml(label)}</span>`).join("")
                      : '<span class="identity-tag">No currently configured local users match this policy</span>'}
                  </div>
                </div>
              </div>
              <div class="dataset-policy-section dataset-policy-section-muted">
                <div class="dataset-policy-heading">AI Providers</div>
                <div class="section-note">Sets the maximum context an eligible provider may receive. Private data is never sent to a provider marked external.</div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-ai-provider-access-${escapeHtml(datasetId)}">Provider context ceiling</label>
                  <select id="dataset-ai-provider-access-${escapeHtml(datasetId)}" data-dataset-ai-provider-access="${escapeHtml(datasetId)}">
                    <option value="detailed_allowed" ${["detailed_allowed", "use_thread_mode"].includes(String(dataset.ai_provider_access || "detailed_allowed")) ? "selected" : ""}>Detailed allowed</option>
                    <option value="safe_summary" ${["safe_summary", "restricted", "summary_only"].includes(String(dataset.ai_provider_access || "")) ? "selected" : ""}>Safe summary</option>
                    <option value="blocked" ${String(dataset.ai_provider_access || "") === "blocked" ? "selected" : ""}>Blocked</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row">
                  <label>Current behavior</label>
                  <div class="dataset-policy-placeholder">${
                    normalizeAiProviderAccess(String(dataset.ai_provider_access || "detailed_allowed")) === "blocked"
                      ? "No AI provider receives dataset context."
                      : dataClassification === "private"
                        ? normalizeAiProviderAccess(String(dataset.ai_provider_access || "detailed_allowed")) === "safe_summary"
                          ? "Local providers may receive a safe structural summary. External providers are blocked."
                          : "Local providers may receive detailed context. External providers are blocked."
                        : normalizeAiProviderAccess(String(dataset.ai_provider_access || "detailed_allowed")) === "safe_summary"
                          ? "Approved providers may receive only a safe structural summary."
                          : "Approved providers may receive detailed context when the in-app result allows it."
                  }</div>
                </div>
              </div>
              <div class="dataset-policy-section dataset-policy-section-muted">
                <div class="dataset-policy-heading">DuckDB Store</div>
                <div class="section-note">Prepared dataset-local DuckDB store used by workspace queries and merged dataset workspaces.</div>
                <div class="dataset-picker-access-row">
                  <label>Current status</label>
                  <div class="identity-tags">
                    <span class="identity-tag">${escapeHtml(storeLabel)}</span>
                  </div>
                </div>
                <div class="dataset-picker-access-row">
                  <label>Details</label>
                  <div class="dataset-policy-placeholder">${escapeHtml(storeDetail)}</div>
                </div>
              </div>
              <div class="dataset-picker-access-actions">
                <button type="button" class="query-chip action" data-dataset-save="${escapeHtml(datasetId)}">Save settings</button>
                <button type="button" class="query-chip action" data-dataset-prepare="${escapeHtml(datasetId)}">${escapeHtml(storeButtonLabel)}</button>
              </div>
              ${feedback && feedback.text ? `<div class="dataset-admin-feedback${feedback.tone === "error" ? " is-error" : ""}">${escapeHtml(feedback.text)}</div>` : ""}
            </div>
          </div>
        </details>
      `;
    }).join("");
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

  async function prepareDatasetStore(datasetId) {
    if (!datasetId || !canManageDataset()) {
      return;
    }
    loadStatusEl.className = "load-status loading";
    loadStatusEl.textContent = `Preparing DuckDB store for ${datasetId}...`;
    setDatasetAdminFeedback(datasetId, "Preparing DuckDB store...", "success", 0);
    try {
      const response = await fetch(`/datasets/${encodeURIComponent(datasetId)}/prepare-store`, {
        method: "POST",
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Unable to prepare dataset store.");
      }
      await loadDatasets({ preservePendingSelection: true });
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = `Prepared DuckDB store for ${datasetId}.`;
      setDatasetAdminFeedback(datasetId, "DuckDB store prepared.", "success");
    } catch (error) {
      loadStatusEl.className = "load-status";
      loadStatusEl.textContent = error && error.message ? error.message : "Unable to prepare dataset store.";
      setDatasetAdminFeedback(
        datasetId,
        error && error.message ? error.message : "Unable to prepare dataset store.",
        "error",
        4200,
      );
    }
  }

  function syncDatasetSelectionFromPicker() {
    if (!dataDirEl || !datasetPickerEl) {
      return;
    }
    const selected = Array.from(datasetPickerEl.querySelectorAll("[data-dataset-checkbox]:checked"))
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
    syncDatasetSelectionFromPicker,
    loadDatasets,
  };
}
