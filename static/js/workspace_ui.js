export function createWorkspaceUi(ctx) {
  const { refs, state, helpers, callbacks } = ctx;
  const {
    contextDataDirEl,
    contextCohortEl,
    contextLmModelEl,
    contextScopeEl,
    contextAuthEl,
    lmStatusEl,
    phenoLmStatusEl,
    analysisLmStatusEl,
    patientsEl,
    dashboardEl,
    dashboardTimelineEl,
    detailEl,
    loadStatusEl,
    patientSearchEl,
    dataDirEl,
    analysisSelectedPatientIdsEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
    phenoSelectedPatientIdsEl,
  } = refs;
  const { formatNumber } = helpers;
  const {
    currentTabName,
    currentDatasetRecord,
    datasetScopeLabel,
    pendingDatasetSelectionIds,
    currentDatasetSelectionKey,
    renderDatasetPicker,
    renderDatasetAdminList,
    renderDatasetScopeSummary,
    renderLoadButtonState,
    syncQueryGranularityWithWorkspacePolicy,
    loadAnalysisCatalog,
    loadSavedCohorts,
    loadQueryDiseaseOptions,
    loadAssayDatasets,
    loadPhenoRankerPatientIds,
    renderAnalysisCatalog,
    renderPatientList,
    renderDetail,
    renderDashboard,
    isWorkspaceAccessible,
    updateLoadButtonAvailability,
    applyUserSettings,
    clearDatasetScopedContent,
  } = callbacks;

  function nextFrame() {
    return new Promise((resolve) => {
      window.requestAnimationFrame(() => resolve());
    });
  }

  function getCurrentScopeIds() {
    return String(phenoSelectedPatientIdsEl && phenoSelectedPatientIdsEl.value ? phenoSelectedPatientIdsEl.value : "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function summarizeScopeForTab(tabName) {
    const selectedAnalysisCohortA = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
      : null;
    const selectedAnalysisCohortB = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
      : null;
    if (tabName === "pheno") {
      const ids = getCurrentScopeIds();
      if (!ids.length && !state.phenoSelectedSavedCohortIds.length) {
        return "Full workspace";
      }
      if (state.phenoSelectedSavedCohortIds.length) {
        return `${state.phenoSelectedSavedCohortIds.length} saved cohort${state.phenoSelectedSavedCohortIds.length === 1 ? "" : "s"}`;
      }
      return `${ids.length} IDs in Pheno scope`;
    }
    if (tabName === "analysis") {
      const ids = selectedAnalysisCohortA && Array.isArray(selectedAnalysisCohortA.sample_ids)
        ? selectedAnalysisCohortA.sample_ids.map((item) => String(item).trim()).filter(Boolean)
        : String(analysisSelectedPatientIdsEl && analysisSelectedPatientIdsEl.value ? analysisSelectedPatientIdsEl.value : "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      const compareIds = selectedAnalysisCohortB && Array.isArray(selectedAnalysisCohortB.sample_ids)
        ? selectedAnalysisCohortB.sample_ids.map((item) => String(item).trim()).filter(Boolean)
        : String((analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value) || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      if (analysisCompareModeEl && analysisCompareModeEl.checked) {
        const labelA = ids.length ? `${ids.length} in A` : "saved cohort A not set";
        const labelB = compareIds.length ? `${compareIds.length} in B` : "saved cohort B not set";
        return `${labelA} vs ${labelB}`;
      }
      if (!ids.length) {
        return "Full workspace";
      }
      return `${ids.length} IDs in Analysis scope`;
    }
    if (tabName === "dashboard" && (state.currentDashboardSubtab === "assays" || state.currentDashboardSubtab === "multimodal")) {
      const ids = selectedAnalysisCohortA && Array.isArray(selectedAnalysisCohortA.sample_ids)
        ? selectedAnalysisCohortA.sample_ids.map((item) => String(item).trim()).filter(Boolean)
        : String(analysisSelectedPatientIdsEl && analysisSelectedPatientIdsEl.value ? analysisSelectedPatientIdsEl.value : "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      const compareIds = selectedAnalysisCohortB && Array.isArray(selectedAnalysisCohortB.sample_ids)
        ? selectedAnalysisCohortB.sample_ids.map((item) => String(item).trim()).filter(Boolean)
        : String((analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value) || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      if (analysisCompareModeEl && analysisCompareModeEl.checked) {
        const labelA = ids.length ? `${ids.length} in A` : "saved cohort A not set";
        const labelB = compareIds.length ? `${compareIds.length} in B` : "saved cohort B not set";
        return `${labelA} vs ${labelB}`;
      }
      if (!ids.length) {
        return "Full workspace";
      }
      return `${ids.length} IDs in ${state.currentDashboardSubtab === "multimodal" ? "Multimodal" : "Assay"} scope`;
    }
    return "Full workspace";
  }

  function renderGlobalContext() {
    if (!contextDataDirEl || !contextCohortEl || !contextLmModelEl || !contextScopeEl) {
      return;
    }
    const dataset = currentDatasetRecord();
    contextDataDirEl.textContent = dataset
      ? String(dataset.name || dataset.dataset_id || "Dataset")
      : (state.currentDatasetIds.length > 1
        ? datasetScopeLabel()
        : (currentDatasetSelectionKey() || "Not configured"));

    const activeRepresentations = (Array.isArray(state.availableDatasets) ? state.availableDatasets : [])
      .filter((item) => (Array.isArray(state.currentDatasetIds) ? state.currentDatasetIds : []).includes(String(item && item.dataset_id ? item.dataset_id : "")))
      .map((item) => String(item && item.clinical_representation ? item.clinical_representation : "unspecified").trim().toLowerCase());
    const representation = state.dashboardSummaryState && state.dashboardSummaryState.clinical_representation
      ? String(state.dashboardSummaryState.clinical_representation).trim().toLowerCase()
      : (activeRepresentations.length && activeRepresentations.every((item) => item === activeRepresentations[0]) ? activeRepresentations[0] : "mixed");
    const recordLabel = representation === "snapshot" ? "timepoints" : representation === "person" ? "person records" : "clinical records";
    if (state.dashboardSummaryState && state.dashboardSummaryState.totals) {
      const totals = state.dashboardSummaryState.totals;
      contextCohortEl.textContent = `${formatNumber(totals.patients || 0)} patients, ${formatNumber(totals.clinical_records ?? totals.visits ?? 0)} ${recordLabel}`;
    } else if (state.currentPatients.length) {
      const totalRecords = state.currentPatients.reduce((sum, patient) => sum + Number(patient.clinical_record_count ?? patient.visit_count ?? 0), 0);
      contextCohortEl.textContent = `${formatNumber(state.currentPatients.length)} patients, ${formatNumber(totalRecords)} ${recordLabel}`;
    } else if (state.loadInFlight) {
      contextCohortEl.textContent = "Loading...";
    } else {
      contextCohortEl.textContent = "No cohort loaded";
    }

    if (!contextLmModelEl.textContent.trim()) {
      contextLmModelEl.textContent = "Checking...";
    }
    contextScopeEl.textContent = summarizeScopeForTab(currentTabName());
    if (contextAuthEl) {
      if (!state.authState.enabled) {
        contextAuthEl.textContent = "Local user";
      } else if (state.authState.authenticated && state.authState.user) {
        contextAuthEl.textContent = `${state.authState.user.display_name || state.authState.user.username} (${state.authState.user.role || "user"})`;
      } else {
        contextAuthEl.textContent = "Signed out";
      }
    }
  }

  async function loadLmStatus() {
    if (!lmStatusEl || !phenoLmStatusEl || !analysisLmStatusEl) {
      return;
    }
    const setContextLmStatus = (label, statusClass, title) => {
      if (!contextLmModelEl) return;
      const pill = contextLmModelEl.closest(".context-pill");
      if (pill) {
        pill.classList.remove("is-ready", "is-warning", "is-muted");
        if (statusClass) pill.classList.add(statusClass);
      }
      contextLmModelEl.textContent = label;
      contextLmModelEl.title = title || label;
    };
    try {
      const response = await fetch("/lm-status");
      if (!response.ok) {
        throw new Error("Unable to load LM status.");
      }
      const payload = await response.json();
      state.lmStatus = payload;
      const provider = payload.provider && typeof payload.provider === "object" ? payload.provider : {};
      const providerLabel = String(provider.label || "LLM").trim();
      const text = !payload.enabled
        ? `${providerLabel}: disabled`
        : (payload.available
          ? `${providerLabel}: ${payload.model || "model loaded"}`
          : (payload.status === "no_model" ? `${providerLabel}: no model loaded` : `${providerLabel}: unavailable`));
      lmStatusEl.textContent = text;
      phenoLmStatusEl.textContent = text;
      analysisLmStatusEl.textContent = text;
      const title = payload.detail || payload.base_url || text;
      if (!payload.enabled) {
        setContextLmStatus("Disabled", "is-muted", title);
      } else if (payload.available) {
        setContextLmStatus(`${providerLabel}: ${payload.model || "model"}`, "is-ready", title);
      } else if (payload.status === "no_model") {
        setContextLmStatus("No model loaded", "is-warning", title);
      } else {
        setContextLmStatus("Unavailable", "is-warning", title);
      }
    } catch (_error) {
      const text = "LLM model: unavailable";
      state.lmStatus = { enabled: true, available: false, status: "unavailable", detail: "Unable to load LM status." };
      lmStatusEl.textContent = text;
      phenoLmStatusEl.textContent = text;
      analysisLmStatusEl.textContent = text;
      setContextLmStatus("Unavailable", "is-warning", "Unable to load LM status.");
    }
    if (typeof renderAnalysisCatalog === "function") {
      renderAnalysisCatalog();
    }
    renderGlobalContext();
  }

  function filterPatients(query) {
    const value = String(query || "").trim().toLowerCase();
    if (!value) return state.currentPatients;
    return state.currentPatients.filter((patient) => {
      const clarid = patient && patient.clarid && typeof patient.clarid === "object" ? patient.clarid : {};
      return [patient && patient.patient_id, clarid.human_id, clarid.stub_id]
        .some((candidate) => String(candidate || "").toLowerCase().includes(value));
    });
  }

  async function persistDatasetSelection(datasetIds) {
    const response = await fetch("/datasets/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_ids: datasetIds }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Unable to apply workspace selection.");
    }
    return payload;
  }

  async function loadPatients(options = {}) {
    const { respectAdminGate = true, targetDatasetIds = null } = options;
    if (state.loadInFlight) {
      return;
    }
    if (respectAdminGate && !isWorkspaceAccessible()) {
      updateLoadButtonAvailability();
      return;
    }
    state.loadInFlight = true;
    if (loadStatusEl) {
      delete loadStatusEl.dataset.datasetStoreBlocker;
    }
    renderGlobalContext();
    renderLoadButtonState();
    updateLoadButtonAvailability();
    if (loadStatusEl) {
      loadStatusEl.className = "load-status loading";
      loadStatusEl.textContent = "Applying workspace selection...";
    }
    await nextFrame();

    try {
      const serverSelectionAlreadyPersisted = Array.isArray(targetDatasetIds);
      const requestedIds = serverSelectionAlreadyPersisted
        ? targetDatasetIds.map((item) => String(item || "").trim()).filter(Boolean)
        : pendingDatasetSelectionIds();
      const selectedIds = Array.from(new Set(requestedIds));
      const targetScopeId = currentDatasetSelectionKey(selectedIds);
      const hadActiveWorkspace = Boolean(state.currentDatasetIds.length);
      let prefetchedAssayPayload = null;

      if (!selectedIds.length) {
        if (!serverSelectionAlreadyPersisted) {
          await persistDatasetSelection([]);
        }
        state.currentDatasetIds = [];
        state.pendingDatasetIds = [];
        state.currentDatasetScopeId = "";
        if (dataDirEl) {
          dataDirEl.dataset.scopeId = "";
        }
        clearDatasetScopedContent({ clearSelection: false, nextScopeId: "" });
        renderDatasetPicker();
        renderDatasetAdminList();
        renderDatasetScopeSummary();
        renderLoadButtonState();
        syncQueryGranularityWithWorkspacePolicy();
        if (loadStatusEl) {
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = hadActiveWorkspace ? "Workspace unloaded." : "No dataset selected.";
        }
        renderGlobalContext();
        return;
      }

      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Checking the selected workspace before switching...";
      }
      await nextFrame();

      const patientResponse = await fetch(`/patients?dataset_id=${encodeURIComponent(targetScopeId)}`);
      if (!patientResponse.ok) {
        const error = await patientResponse.json().catch(() => ({}));
        throw new Error(error.detail || "Unable to load patients.");
      }

      const patients = await patientResponse.json();
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Preparing transcriptomics assays for the selected workspace...";
      }
      await nextFrame();
      const assayResponse = await fetch(`/assays?data_dir=${encodeURIComponent(targetScopeId)}`);
      if (!assayResponse.ok) {
        const error = await assayResponse.json().catch(() => ({}));
        throw new Error(error.detail || "Unable to load assays.");
      }
      prefetchedAssayPayload = await assayResponse.json();

      let committedIds = selectedIds.slice();
      let committedScopeId = targetScopeId;
      if (!serverSelectionAlreadyPersisted) {
        const selectionPayload = await persistDatasetSelection(selectedIds);
        committedIds = Array.isArray(selectionPayload.current_dataset_ids)
          ? selectionPayload.current_dataset_ids.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
        committedScopeId = String(selectionPayload.current_dataset_scope_id || currentDatasetSelectionKey(committedIds)).trim();
        const requestedSet = new Set(selectedIds);
        if (committedIds.length !== requestedSet.size || committedIds.some((item) => !requestedSet.has(item))) {
          throw new Error("The server did not persist the requested workspace selection.");
        }
      }
      state.currentDatasetIds = committedIds.slice();
      state.pendingDatasetIds = committedIds.slice();
      state.currentDatasetScopeId = committedScopeId;
      if (dataDirEl) {
        dataDirEl.dataset.scopeId = committedScopeId;
      }
      clearDatasetScopedContent({ clearSelection: false, nextScopeId: committedScopeId });
      const workspaceRevision = state.workspaceRevision;
      state.currentPatients = Array.isArray(patients) ? patients : [];
      state.selectedPatientId = null;
      renderDatasetPicker();
      renderDatasetAdminList();
      renderDatasetScopeSummary();
      renderGlobalContext();
      renderLoadButtonState();
      syncQueryGranularityWithWorkspacePolicy();
      if (typeof applyUserSettings === "function") {
        applyUserSettings({ applyNavigation: false });
      }
      if (state.currentPatients.length) {
        renderPatientList(filterPatients(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : ""));
        if (detailEl) {
          detailEl.innerHTML = '<div class="empty">Select a patient to inspect the patient workspace.</div>';
        }
      } else {
        if (patientsEl) patientsEl.innerHTML = '<div class="empty">No patient records found in the selected workspace.</div>';
        if (detailEl) detailEl.innerHTML = '<div class="empty">No patient workspace to display.</div>';
      }
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Refreshing catalog, cohorts, and query helpers...";
      }
      await loadAnalysisCatalog();
      await loadSavedCohorts();
      await loadQueryDiseaseOptions();
      if (workspaceRevision !== state.workspaceRevision || state.currentDatasetScopeId !== committedScopeId) return;
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Indexing transcriptomics assays for the selected workspace...";
      }
      await nextFrame();
      await loadAssayDatasets({ scopeId: committedScopeId, prefetched: prefetchedAssayPayload });
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Loading Pheno-Ranker scope IDs and patient roster...";
      }
      await loadPhenoRankerPatientIds();
      if (workspaceRevision !== state.workspaceRevision || state.currentDatasetScopeId !== committedScopeId) return;
      if (!state.currentPatients.length) {
        if (dashboardEl) {
          dashboardEl.innerHTML = '<div class="empty">No dashboard to display.</div>';
        }
        if (dashboardTimelineEl) {
          dashboardTimelineEl.innerHTML = '<div class="empty">No timeline to display.</div>';
        }
        state.dashboardSummaryState = null;
        if (loadStatusEl) {
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = "No patients found.";
        }
        renderGlobalContext();
        return;
      }

      if (loadStatusEl) {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = `Loaded ${state.currentPatients.length} patients. Workspace: ${datasetScopeLabel()}.`;
      }
      renderGlobalContext();

      if (dashboardEl) {
        dashboardEl.innerHTML = '<div class="empty">Loading dashboard...</div>';
      }
      if (dashboardTimelineEl) {
        dashboardTimelineEl.innerHTML = '<div class="empty">Loading timeline...</div>';
      }
      window.setTimeout(() => {
        fetch(`/dashboard?dataset_id=${encodeURIComponent(committedScopeId)}`)
          .then(async (response) => {
            if (workspaceRevision !== state.workspaceRevision || state.currentDatasetScopeId !== committedScopeId) return;
            if (!response.ok) {
              if (dashboardEl) {
                dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
              }
              if (dashboardTimelineEl) {
                dashboardTimelineEl.innerHTML = '<div class="empty">Timeline unavailable.</div>';
              }
              state.dashboardSummaryState = null;
              renderGlobalContext();
              return;
            }
            const payload = await response.json();
            if (workspaceRevision !== state.workspaceRevision || state.currentDatasetScopeId !== committedScopeId) return;
            state.dashboardSummaryState = payload;
            renderDashboard(state.dashboardSummaryState);
            renderGlobalContext();
          })
          .catch(() => {
            if (workspaceRevision !== state.workspaceRevision || state.currentDatasetScopeId !== committedScopeId) return;
            if (dashboardEl) {
              dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
            }
            if (dashboardTimelineEl) {
              dashboardTimelineEl.innerHTML = '<div class="empty">Timeline unavailable.</div>';
            }
            state.dashboardSummaryState = null;
            renderGlobalContext();
          });
      }, 0);
    } catch (error) {
      if (!state.currentDatasetIds.length) {
        if (patientsEl) {
          patientsEl.innerHTML = '<div class="empty">Unable to load patients.</div>';
        }
        if (detailEl) {
          detailEl.innerHTML = '<div class="empty">Patient workspace unavailable.</div>';
        }
        if (dashboardEl) {
          dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
        }
        if (dashboardTimelineEl) {
          dashboardTimelineEl.innerHTML = '<div class="empty">Timeline unavailable.</div>';
        }
        state.dashboardSummaryState = null;
      }
      if (loadStatusEl) {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = error && error.message ? error.message : "Load failed.";
      }
      renderGlobalContext();
    } finally {
      state.loadInFlight = false;
      renderLoadButtonState();
      updateLoadButtonAvailability();
    }
  }

  async function loadPatient(patientId) {
    const scopeId = currentDatasetSelectionKey();
    state.selectedPatientId = patientId;
    const datasetId = encodeURIComponent(scopeId);
    const response = await fetch(`/patients/${encodeURIComponent(patientId)}/workspace?dataset_id=${datasetId}`);
    if (scopeId !== currentDatasetSelectionKey()) return;
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      if (detailEl) {
        detailEl.innerHTML = `<div class="empty">${error.detail || "Unable to load patient."}</div>`;
      }
      return;
    }
    const patient = await response.json();
    if (scopeId !== currentDatasetSelectionKey()) return;
    renderDetail(patient);
    renderPatientList(filterPatients(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : ""));
    if (state.dashboardSummaryState) {
      renderDashboard(state.dashboardSummaryState);
    }
  }

  return {
    nextFrame,
    getCurrentScopeIds,
    summarizeScopeForTab,
    renderGlobalContext,
    loadLmStatus,
    filterPatients,
    loadPatients,
    loadPatient,
  };
}
