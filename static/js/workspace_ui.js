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
    prepareAnalysisSessionForDataDir,
    resetQueryWorkspace,
    syncQueryGranularityWithWorkspacePolicy,
    loadAnalysisCatalog,
    loadSavedCohorts,
    loadQueryDiseaseOptions,
    loadMolecularDatasets,
    loadPhenoRankerPatientIds,
    renderPatientList,
    renderDetail,
    renderDashboard,
    isWorkspaceAccessible,
    updateLoadButtonAvailability,
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
    if (tabName === "dashboard" && state.currentDashboardSubtab === "molecular") {
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
      return `${ids.length} IDs in Molecular scope`;
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

    if (state.dashboardSummaryState && state.dashboardSummaryState.totals) {
      const totals = state.dashboardSummaryState.totals;
      contextCohortEl.textContent = `${formatNumber(totals.patients || 0)} patients, ${formatNumber(totals.visits || 0)} timepoints`;
    } else if (state.currentPatients.length) {
      const totalVisits = state.currentPatients.reduce((sum, patient) => sum + Number(patient.visit_count || 0), 0);
      contextCohortEl.textContent = `${formatNumber(state.currentPatients.length)} patients, ${formatNumber(totalVisits)} timepoints`;
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
    try {
      const response = await fetch("/lm-status");
      if (!response.ok) {
        throw new Error("Unable to load LM status.");
      }
      const payload = await response.json();
      const text = payload.enabled
        ? (payload.model ? `LLM model: ${payload.model}` : "LLM: enabled, but no model is loaded")
        : "LLM: disabled";
      lmStatusEl.textContent = text;
      phenoLmStatusEl.textContent = text;
      analysisLmStatusEl.textContent = text;
      if (contextLmModelEl) {
        contextLmModelEl.textContent = payload.enabled
          ? (payload.model || "Enabled, no model loaded")
          : "Disabled";
      }
    } catch (_error) {
      const text = "LLM model: unavailable";
      lmStatusEl.textContent = text;
      phenoLmStatusEl.textContent = text;
      analysisLmStatusEl.textContent = text;
      if (contextLmModelEl) {
        contextLmModelEl.textContent = "Unavailable";
      }
    }
    renderGlobalContext();
  }

  function filterPatients(query) {
    const value = String(query || "").trim().toLowerCase();
    if (!value) return state.currentPatients;
    return state.currentPatients.filter((patient) => String(patient.patient_id || "").toLowerCase().includes(value));
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
    renderGlobalContext();
    renderLoadButtonState();
    updateLoadButtonAvailability();
    if (loadStatusEl) {
      loadStatusEl.className = "load-status loading";
      loadStatusEl.textContent = "Applying workspace selection...";
    }
    await nextFrame();

    try {
      const selectedIds = Array.isArray(targetDatasetIds)
        ? targetDatasetIds.map((item) => String(item || "").trim()).filter(Boolean)
        : pendingDatasetSelectionIds();
      const targetScopeId = currentDatasetSelectionKey(selectedIds);
      const hadActiveWorkspace = Boolean(state.currentDatasetIds.length);
      let prefetchedMolecularPayload = null;

      if (!selectedIds.length) {
        state.currentDatasetIds = [];
        state.pendingDatasetIds = [];
        state.currentDatasetScopeId = "";
        state.currentPatients = [];
        state.selectedPatientId = null;
        state.dashboardSummaryState = null;
        if (dataDirEl) {
          dataDirEl.dataset.scopeId = "";
        }
        renderDatasetPicker();
        renderDatasetAdminList();
        renderDatasetScopeSummary();
        renderLoadButtonState();
        prepareAnalysisSessionForDataDir("");
        resetQueryWorkspace();
        syncQueryGranularityWithWorkspacePolicy();
        if (patientsEl) {
          patientsEl.innerHTML = '<div class="empty">No dataset selected.</div>';
        }
        if (detailEl) {
          detailEl.innerHTML = '<div class="empty">Select a workspace to inspect the patient workspace.</div>';
        }
        if (dashboardEl) {
          dashboardEl.innerHTML = '<div class="empty">Select a workspace to inspect the dashboard.</div>';
        }
        if (loadStatusEl) {
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = "No dataset selected.";
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
        if (!hadActiveWorkspace) {
          if (patientsEl) {
            patientsEl.innerHTML = `<div class="empty">${error.detail || "Unable to load patients."}</div>`;
          }
          if (detailEl) {
            detailEl.innerHTML = '<div class="empty">Fix the data directory and try again.</div>';
          }
          if (dashboardEl) {
            dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
          }
          state.dashboardSummaryState = null;
        }
        if (loadStatusEl) {
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = error.detail || "Load failed.";
        }
        renderGlobalContext();
        return;
      }

      const patients = await patientResponse.json();
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Preparing molecular datasets for the selected workspace...";
      }
      await nextFrame();
      try {
        const molecularResponse = await fetch(`/molecular/datasets?data_dir=${encodeURIComponent(targetScopeId)}`);
        if (molecularResponse.ok) {
          prefetchedMolecularPayload = await molecularResponse.json();
        }
      } catch (_error) {
        prefetchedMolecularPayload = null;
      }

      await fetch("/datasets/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_ids: selectedIds }),
      });
      state.currentDatasetIds = selectedIds.slice();
      state.pendingDatasetIds = selectedIds.slice();
      state.currentDatasetScopeId = targetScopeId;
      if (dataDirEl) {
        dataDirEl.dataset.scopeId = targetScopeId;
      }
      renderDatasetPicker();
      renderDatasetAdminList();
      renderDatasetScopeSummary();
      renderGlobalContext();
      renderLoadButtonState();
      prepareAnalysisSessionForDataDir(targetScopeId);
      resetQueryWorkspace();
      syncQueryGranularityWithWorkspacePolicy();
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Refreshing catalog, cohorts, and query helpers...";
      }
      await loadAnalysisCatalog();
      await loadSavedCohorts();
      await loadQueryDiseaseOptions();
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Indexing molecular datasets for the selected workspace...";
      }
      await nextFrame();
      await loadMolecularDatasets({ scopeId: targetScopeId, prefetched: prefetchedMolecularPayload });
      if (loadStatusEl) {
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Loading Pheno-Ranker scope IDs and patient roster...";
      }
      await loadPhenoRankerPatientIds();
      state.currentPatients = Array.isArray(patients) ? patients : [];
      if (!state.currentPatients.length) {
        state.selectedPatientId = null;
        if (patientsEl) {
          patientsEl.innerHTML = '<div class="empty">No patient records found in the selected directory.</div>';
        }
        if (detailEl) {
          detailEl.innerHTML = '<div class="empty">No timeline to display.</div>';
        }
        if (dashboardEl) {
          dashboardEl.innerHTML = '<div class="empty">No dashboard to display.</div>';
        }
        state.dashboardSummaryState = null;
        if (loadStatusEl) {
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = "No patients found.";
        }
        renderGlobalContext();
        return;
      }

      renderPatientList(filterPatients(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : ""));
      state.selectedPatientId = null;
      if (detailEl) {
        detailEl.innerHTML = '<div class="empty">Select a patient to inspect the patient workspace.</div>';
      }
      if (loadStatusEl) {
        loadStatusEl.className = "load-status";
        loadStatusEl.textContent = `Loaded ${state.currentPatients.length} patients. Workspace: ${datasetScopeLabel()}.`;
      }
      renderGlobalContext();

      if (dashboardEl) {
        dashboardEl.innerHTML = '<div class="empty">Loading dashboard...</div>';
      }
      window.setTimeout(() => {
        fetch(`/dashboard?dataset_id=${encodeURIComponent(targetScopeId)}`)
          .then(async (response) => {
            if (!response.ok) {
              if (dashboardEl) {
                dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
              }
              state.dashboardSummaryState = null;
              renderGlobalContext();
              return;
            }
            state.dashboardSummaryState = await response.json();
            renderDashboard(state.dashboardSummaryState);
            renderGlobalContext();
          })
          .catch(() => {
            if (dashboardEl) {
              dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
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
    state.selectedPatientId = patientId;
    const datasetId = encodeURIComponent(currentDatasetSelectionKey());
    const response = await fetch(`/patients/${encodeURIComponent(patientId)}/navigator?dataset_id=${datasetId}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      if (detailEl) {
        detailEl.innerHTML = `<div class="empty">${error.detail || "Unable to load patient."}</div>`;
      }
      return;
    }
    const patient = await response.json();
    renderDetail(patient);
    renderPatientList(filterPatients(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : ""));
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
