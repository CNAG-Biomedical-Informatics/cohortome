export function createDatasetsUi(ctx) {
  const { refs, state, helpers, callbacks } = ctx;
  const {
    dataDirEl,
    datasetPickerShellEl,
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
    loadMolecularDatasets,
    loadPhenoRankerPatientIds,
    renderPhenoTabAvailability,
    currentTabName,
    setActiveTab,
    renderQueryExecutionMode,
    loadAuthUsers,
    updateLoadButtonAvailability,
  } = callbacks;

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
    const actionLabel = canManageDataset()
      ? "Prepare or rebuild it in Data Admin."
      : "Ask an admin to prepare it in Data Admin.";
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
    const blockedByAuth = typeof isWorkspaceAccessible === "function" && !isWorkspaceAccessible();
    const storeBlocker = pendingWorkspaceStoreBlocker();
    refs.loadBtnEl.classList.toggle("is-loading", Boolean(state.loadInFlight));
    refs.loadBtnEl.classList.toggle("has-pending-change", Boolean(hasPendingChange && !state.loadInFlight));
    refs.loadBtnEl.disabled = Boolean(state.loadInFlight || blockedByAuth || storeBlocker);
    refs.loadBtnEl.title = storeBlocker ? storeBlocker.message : "";
    if (datasetPickerShellEl) {
      datasetPickerShellEl.classList.toggle("is-loading", Boolean(state.loadInFlight));
    }
    if (refs.loadBtnLabelEl) {
      refs.loadBtnLabelEl.textContent = state.loadInFlight
        ? "Applying..."
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
    if (effectiveProviderAccess === "blocked") {
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
    return state.pendingDatasetIds.length ? state.pendingDatasetIds.slice() : state.currentDatasetIds.slice();
  }

  function startupDefaultDatasetIds() {
    if (!state.availableDatasets.length) {
      return [];
    }
    const explicitDefault = state.availableDatasets.find((item) => String(item.dataset_id || "") === "default");
    if (explicitDefault) {
      return [String(explicitDefault.dataset_id || "default")];
    }
    const firstDataset = state.availableDatasets[0];
    return firstDataset && firstDataset.dataset_id
      ? [String(firstDataset.dataset_id)]
      : [];
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
    if (!selectedIds.size && state.availableDatasets[0]) {
      dataDirEl.options[0].selected = true;
    }
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
      const allowedGroups = Array.isArray(dataset.allowed_groups) ? dataset.allowed_groups : [];
      const allowedUsers = Array.isArray(dataset.allowed_users) ? dataset.allowed_users : [];
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
            <div class="dataset-picker-meta">
              <span class="dataset-picker-tag">${escapeHtml(datasetId)}</span>
              <span class="dataset-picker-tag">${escapeHtml(visibility.replaceAll("_", " "))}</span>
              ${allowedGroups.length ? `<span class="dataset-picker-tag">groups: ${escapeHtml(allowedGroups.join(", "))}</span>` : ""}
              ${allowedUsers.length ? `<span class="dataset-picker-tag">users: ${escapeHtml(allowedUsers.join(", "))}</span>` : ""}
            </div>
            ${description ? `<div class="dataset-picker-description">${escapeHtml(description)}</div>` : ""}
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
    datasetAdminListEl.innerHTML = state.availableDatasets.map((dataset) => {
      const datasetId = String(dataset.dataset_id || "");
      const visibility = String(dataset.visibility || "all_authenticated");
      const providerDetailedAllowed = visibility === "all_authenticated";
      const description = String(dataset.description || "").trim();
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
        <div class="dataset-picker-card">
          <div>
            <div class="dataset-picker-title">
              <span>${escapeHtml(dataset.name || datasetId || "Unnamed dataset")}</span>
            </div>
            <div class="dataset-picker-meta">
              <span class="dataset-picker-tag">${escapeHtml(datasetId)}</span>
              <span class="dataset-picker-tag">${escapeHtml(visibility.replaceAll("_", " "))}</span>
              ${allowedGroups.length ? `<span class="dataset-picker-tag">groups: ${escapeHtml(allowedGroups.join(", "))}</span>` : ""}
              ${allowedUsers.length ? `<span class="dataset-picker-tag">users: ${escapeHtml(allowedUsers.join(", "))}</span>` : ""}
            </div>
            ${description ? `<div class="dataset-picker-description">${escapeHtml(description)}</div>` : ""}
            <div class="dataset-picker-access">
              <div class="dataset-policy-section">
                <div class="dataset-policy-heading">Internal</div>
                <div class="section-note">Controls who can use this dataset inside Patient Navigator and how much Query detail is allowed in-app.</div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-visibility-${escapeHtml(datasetId)}">Visibility</label>
                  <select id="dataset-visibility-${escapeHtml(datasetId)}" data-dataset-visibility="${escapeHtml(datasetId)}">
                    <option value="all_authenticated" ${visibility === "all_authenticated" ? "selected" : ""}>All authenticated</option>
                    <option value="restricted" ${visibility === "restricted" ? "selected" : ""}>Restricted</option>
                    <option value="admin_only" ${visibility === "admin_only" ? "selected" : ""}>Admin only</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-groups-${escapeHtml(datasetId)}">Allowed groups</label>
                  <input id="dataset-groups-${escapeHtml(datasetId)}" data-dataset-groups="${escapeHtml(datasetId)}" value="${escapeHtml(allowedGroups.join(", "))}" placeholder="e.g. cnag, ibd-team">
                </div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-users-${escapeHtml(datasetId)}">Allowed users</label>
                  <input id="dataset-users-${escapeHtml(datasetId)}" data-dataset-users="${escapeHtml(datasetId)}" value="${escapeHtml(allowedUsers.join(", "))}" placeholder="e.g. mrueda, alice">
                </div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-query-granularity-${escapeHtml(datasetId)}">Query detail in app</label>
                  <select id="dataset-query-granularity-${escapeHtml(datasetId)}" data-dataset-query-granularity="${escapeHtml(datasetId)}">
                    <option value="summary" ${normalizeDatasetQueryGranularityCeiling(dataset.query_granularity_ceiling) === "summary" ? "selected" : ""}>Summary only</option>
                    <option value="detailed" ${normalizeDatasetQueryGranularityCeiling(dataset.query_granularity_ceiling) === "detailed" ? "selected" : ""}>Detailed allowed</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row">
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
                <div class="section-note">Controls what Patient Navigator may send to the currently configured AI provider. LM Studio is the active provider today.</div>
                <div class="dataset-picker-access-row">
                  <label for="dataset-ai-provider-access-${escapeHtml(datasetId)}">LM Studio</label>
                  <select id="dataset-ai-provider-access-${escapeHtml(datasetId)}" data-dataset-ai-provider-access="${escapeHtml(datasetId)}">
                    <option value="detailed_allowed" ${["detailed_allowed", "use_thread_mode"].includes(String(dataset.ai_provider_access || "detailed_allowed")) ? "selected" : ""} ${providerDetailedAllowed ? "" : "disabled"}>Detailed allowed</option>
                    <option value="safe_summary" ${["safe_summary", "restricted", "summary_only"].includes(String(dataset.ai_provider_access || "")) ? "selected" : ""}>Safe summary</option>
                    <option value="blocked" ${String(dataset.ai_provider_access || "") === "blocked" ? "selected" : ""}>Blocked</option>
                  </select>
                </div>
                <div class="dataset-picker-access-row">
                  <label>Current behavior</label>
                  <div class="dataset-policy-placeholder">${
                    normalizeAiProviderAccess(String(dataset.ai_provider_access || "detailed_allowed")) === "blocked"
                      ? "LM Studio is disabled for this dataset."
                      : !providerDetailedAllowed
                        ? "Restricted and admin-only datasets are capped at Safe summary for AI providers."
                        : normalizeAiProviderAccess(String(dataset.ai_provider_access || "detailed_allowed")) === "safe_summary"
                          ? "LM Studio may be used, but only with provider-safe structural summary context."
                          : "LM Studio may receive detailed context when the current in-app result allows it."
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
        </div>
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
    const groupsEl = datasetAdminListEl.querySelector(`[data-dataset-groups="${CSS.escape(datasetId)}"]`);
    const usersEl = datasetAdminListEl.querySelector(`[data-dataset-users="${CSS.escape(datasetId)}"]`);
    const queryGranularityEl = datasetAdminListEl.querySelector(`[data-dataset-query-granularity="${CSS.escape(datasetId)}"]`);
    const aiProviderAccessEl = datasetAdminListEl.querySelector(`[data-dataset-ai-provider-access="${CSS.escape(datasetId)}"]`);
    if (!visibilityEl || !groupsEl || !usersEl || !queryGranularityEl || !aiProviderAccessEl) {
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
    const normalizedVisibility = String(visibilityEl.value || "all_authenticated").trim().toLowerCase();
    const requestedAiProviderAccess = String(aiProviderAccessEl.value || "detailed_allowed").trim();
    const effectiveProviderAccess = (normalizedVisibility === "restricted" || normalizedVisibility === "admin_only")
      ? (requestedAiProviderAccess === "blocked" ? "blocked" : "safe_summary")
      : requestedAiProviderAccess;
    loadStatusEl.className = "load-status loading";
    loadStatusEl.textContent = `Saving access for ${datasetId}...`;
    setDatasetAdminFeedback(datasetId, "Saving settings...", "success", 0);
    try {
      const response = await fetch(`/datasets/${encodeURIComponent(datasetId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          visibility: visibilityEl.value,
          allowed_groups: allowedGroups,
          allowed_users: allowedUsers,
          query_granularity_ceiling: queryGranularityEl.value,
          ai_provider_access: effectiveProviderAccess,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Unable to save dataset access.");
      }
      await loadDatasets();
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
      await loadDatasets();
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

  async function loadDatasets() {
    if (!dataDirEl) {
      return;
    }
    try {
      const response = await fetch("/datasets");
      if (!response.ok) {
        throw new Error("Unable to load datasets.");
      }
      const payload = await response.json();
      state.availableDatasets = Array.isArray(payload.datasets) ? payload.datasets : [];
      state.currentDatasetIds = Array.isArray(payload.current_dataset_ids) ? payload.current_dataset_ids : [];
      state.pendingDatasetIds = state.currentDatasetIds.slice();
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

  function prepareStartupWorkspaceSelection() {
    const startupIds = startupDefaultDatasetIds();
    state.currentDatasetIds = [];
    state.currentDatasetScopeId = "";
    state.pendingDatasetIds = startupIds.slice();
    renderDatasetSelect();
    if (dataDirEl) {
      dataDirEl.dataset.scopeId = "";
    }
    renderDatasetScopeSummary();
    renderAnalysisDatasetScope();
    renderLoadButtonState();
    updateLoadButtonAvailability();
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
    startupDefaultDatasetIds,
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
    prepareStartupWorkspaceSelection,
  };
}
