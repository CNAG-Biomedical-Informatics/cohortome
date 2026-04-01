export function createSavedCohortsUi(ctx) {
  const { refs, helpers, callbacks, state } = ctx;
  const {
    savedCohortsEl,
    phenoSavedCohortsEl,
    phenoSavedCohortsSelectionEl,
    phenoSelectedPatientIdsEl,
    phenoSelectedPatientIdsSummaryEl,
    analysisSelectedPatientIdsEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
    analysisSelectedSavedCohortSelectionEl,
    analysisCompareSavedCohortSelectionEl,
    analysisStatusEl,
    phenoStatusEl,
    dataDirEl,
  } = refs;
  const { escapeHtml } = helpers;
  const {
    setActiveTab,
    renderAnalysisScopeSummary,
    renderAnalysisCompareMode,
    renderAnalysisCompareScopeSummary,
    renderSelectedPatientIdsSummary,
    renderGlobalContext,
  } = callbacks;

  function renderSavedCohortsInto(container, mode) {
    if (!container) return;
    if (!state.savedCohorts.length) {
      container.innerHTML = '<div class="empty">No saved cohorts yet.</div>';
      return;
    }
    const primaryActionLabel = mode === "pheno" ? "Use in Pheno-Ranker" : "Use as Cohort A";
    const primaryAction = mode === "pheno" ? "load-pheno" : "load-analysis";
    container.innerHTML = `<div class="saved-cohort-list">${
      state.savedCohorts.map((item) => {
        const sampleIds = Array.isArray(item.sample_ids) && item.sample_ids.length
          ? item.sample_ids
          : (Array.isArray(item.patient_ids) ? item.patient_ids : []);
        const patientIds = Array.isArray(item.patient_ids) ? item.patient_ids : [];
        const preview = sampleIds.slice(0, 4).join(", ");
        const suffix = sampleIds.length > 4 ? ` ... (+${sampleIds.length - 4} more)` : "";
        const source = item.source && item.source.kind ? item.source.kind : "manual";
        return `
          <div class="saved-cohort-card">
            <strong>${escapeHtml(item.name || "Unnamed cohort")}</strong>
            <small>${escapeHtml(String(patientIds.length || item.patient_count || 0))} patients • ${escapeHtml(String(sampleIds.length || item.sample_count || 0))} samples • source: ${escapeHtml(source)}</small>
            <small>${escapeHtml(preview)}${escapeHtml(suffix)}</small>
            <div class="saved-cohort-actions">
              <button type="button" class="query-chip action" data-saved-cohort-action="${primaryAction}" data-saved-cohort-id="${escapeHtml(item.id)}">${primaryActionLabel}</button>
              ${mode === "analysis" ? `<button type="button" class="query-chip action" data-saved-cohort-action="load-analysis-b" data-saved-cohort-id="${escapeHtml(item.id)}">Use as Cohort B</button>` : ""}
              <button type="button" class="query-chip" data-saved-cohort-action="copy" data-saved-cohort-id="${escapeHtml(item.id)}">Copy IDs</button>
              <button type="button" class="query-chip" data-saved-cohort-action="delete" data-saved-cohort-id="${escapeHtml(item.id)}">Delete</button>
            </div>
          </div>
        `;
      }).join("")
    }</div>`;
  }

  function renderPhenoSavedCohortsSelection() {
    if (!phenoSavedCohortsSelectionEl) return;
    const selectedItems = state.phenoSelectedSavedCohortIds
      .map((cohortId) => state.savedCohorts.find((entry) => entry.id === cohortId))
      .filter(Boolean);
    if (!selectedItems.length) {
      phenoSavedCohortsSelectionEl.textContent = "No saved cohorts attached as separate references.";
      phenoSelectedPatientIdsEl.disabled = false;
      renderSelectedPatientIdsSummary();
      renderGlobalContext();
      return;
    }
    phenoSavedCohortsSelectionEl.innerHTML = `
      <div class="saved-cohort-actions">
        <span class="query-chip badge">Separate references</span>
        ${selectedItems.map((item) => `<button type="button" class="query-chip query-chip-deterministic" data-pheno-selected-cohort-id="${escapeHtml(item.id)}">${escapeHtml(item.name || "Unnamed cohort")} ×</button>`).join("")}
      </div>
    `;
    phenoSelectedPatientIdsEl.disabled = true;
    phenoSelectedPatientIdsSummaryEl.textContent = "Scope is disabled while saved cohorts are attached as separate references.";
    renderGlobalContext();
  }

  function renderSavedCohorts() {
    renderSavedCohortsInto(savedCohortsEl, "analysis");
    renderSavedCohortsInto(phenoSavedCohortsEl, "pheno");
    renderPhenoSavedCohortsSelection();
  }

  function setSavedCohortStatus(message) {
    if (callbacks.currentTabName() === "pheno") {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = message;
      return;
    }
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = message;
  }

  async function loadSavedCohorts() {
    if (!savedCohortsEl && !phenoSavedCohortsEl) return;
    try {
      const dataDir = encodeURIComponent((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim());
      const response = await fetch(`/saved-cohorts?data_dir=${dataDir}`);
      if (!response.ok) {
        state.savedCohorts = [];
        renderSavedCohorts();
        return;
      }
      const payload = await response.json();
      state.savedCohorts = Array.isArray(payload.cohorts) ? payload.cohorts : [];
      renderSavedCohorts();
    } catch (_error) {
      state.savedCohorts = [];
      renderSavedCohorts();
    }
  }

  async function saveLatestQueryAsCohort() {
    if (!state.latestQueryPatientIds.length) return;
    const defaultName = state.latestQueryPrompt
      ? state.latestQueryPrompt.slice(0, 80)
      : `Saved cohort ${new Date().toLocaleString()}`;
    const name = window.prompt("Cohort name", defaultName);
    if (name === null) return;
    try {
      const response = await fetch("/saved-cohorts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
          sample_ids: state.latestQueryRecordIds,
          patient_ids: state.latestQueryPatientIds,
          id_type: state.latestQueryRecordIds.length ? "sample" : state.latestQueryIdType,
          source_kind: "query",
          source_prompt: state.latestQueryPrompt,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(String(payload.detail || "Unable to save cohort."));
      }
      await loadSavedCohorts();
      callbacks.queryStatusEl().className = "query-status";
      callbacks.queryStatusEl().textContent = `Saved cohort "${(name || defaultName).trim()}".`;
    } catch (error) {
      callbacks.queryStatusEl().className = "query-status";
      callbacks.queryStatusEl().textContent = error && error.message ? error.message : "Unable to save cohort.";
    }
  }

  async function deleteSavedCohortById(cohortId) {
    try {
      const response = await fetch(`/saved-cohorts/${encodeURIComponent(cohortId)}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Unable to delete saved cohort.");
      await loadSavedCohorts();
      setSavedCohortStatus("Deleted saved cohort.");
    } catch (_error) {
      setSavedCohortStatus("Unable to delete saved cohort.");
    }
  }

  async function copySavedCohortIds(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    const ids = Array.isArray(item && item.sample_ids) && item.sample_ids.length
      ? item.sample_ids
      : (Array.isArray(item && item.patient_ids) ? item.patient_ids : []);
    if (!item || !ids.length) return;
    try {
      await navigator.clipboard.writeText(ids.join(","));
      setSavedCohortStatus(`Copied ${ids.length} IDs from ${item.name}.`);
    } catch (_error) {
      setSavedCohortStatus("Unable to copy saved cohort IDs.");
    }
  }

  function useSavedCohortInAnalysis(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    if (!item || (!Array.isArray(item.sample_ids) && !Array.isArray(item.patient_ids))) return;
    state.analysisSelectedSavedCohortId = cohortId;
    analysisSelectedPatientIdsEl.value = "";
    renderAnalysisScopeSummary();
    setActiveTab("analysis");
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = analysisCompareModeEl && analysisCompareModeEl.checked
      ? `Loaded saved cohort "${item.name}" into Cohort A.`
      : `Loaded saved cohort "${item.name}" into the analysis scope.`;
  }

  function useSavedCohortInAnalysisCompare(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    if (!item || (!Array.isArray(item.sample_ids) && !Array.isArray(item.patient_ids))) return;
    state.analysisCompareSavedCohortId = cohortId;
    if (analysisCompareModeEl) analysisCompareModeEl.checked = true;
    renderAnalysisCompareMode();
    analysisCompareSelectedPatientIdsEl.value = "";
    renderAnalysisCompareScopeSummary();
    setActiveTab("analysis");
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = `Loaded saved cohort "${item.name}" into Cohort B.`;
  }

  function useSavedCohortInPheno(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    if (!item || (!Array.isArray(item.sample_ids) && !Array.isArray(item.patient_ids))) return;
    if (!state.phenoSelectedSavedCohortIds.includes(cohortId)) {
      state.phenoSelectedSavedCohortIds = state.phenoSelectedSavedCohortIds.concat([cohortId]);
    }
    renderPhenoSavedCohortsSelection();
    setActiveTab("pheno");
    phenoStatusEl.className = "pheno-status";
    phenoStatusEl.textContent = `Attached saved cohort "${item.name}" as a separate Pheno-Ranker reference.`;
  }

  function removeSavedCohortFromPheno(cohortId) {
    state.phenoSelectedSavedCohortIds = state.phenoSelectedSavedCohortIds.filter((item) => item !== cohortId);
    renderPhenoSavedCohortsSelection();
    phenoStatusEl.className = "pheno-status";
    phenoStatusEl.textContent = "Removed saved cohort from separate Pheno-Ranker references.";
  }

  function clearSavedCohortFromAnalysis(side) {
    if (side === "b") {
      state.analysisCompareSavedCohortId = "";
      renderAnalysisCompareScopeSummary();
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = analysisCompareModeEl && analysisCompareModeEl.checked
        ? "Cohort B cleared. Select a saved cohort to compare."
        : "Cohort B reverted to manual scope.";
      return;
    }
    state.analysisSelectedSavedCohortId = "";
    renderAnalysisScopeSummary();
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = analysisCompareModeEl && analysisCompareModeEl.checked
      ? "Cohort A cleared. Select a saved cohort to compare."
      : "Cohort A reverted to manual scope.";
  }

  function handleSavedCohortAction(button) {
    const cohortId = button.dataset.savedCohortId;
    if (!cohortId) return;
    if (button.dataset.savedCohortAction === "load-analysis") return void useSavedCohortInAnalysis(cohortId);
    if (button.dataset.savedCohortAction === "load-analysis-b") return void useSavedCohortInAnalysisCompare(cohortId);
    if (button.dataset.savedCohortAction === "load-pheno") return void useSavedCohortInPheno(cohortId);
    if (button.dataset.savedCohortAction === "copy") return void copySavedCohortIds(cohortId);
    if (button.dataset.savedCohortAction === "delete") return void deleteSavedCohortById(cohortId);
  }

  return {
    renderPhenoSavedCohortsSelection,
    renderSavedCohorts,
    loadSavedCohorts,
    saveLatestQueryAsCohort,
    removeSavedCohortFromPheno,
    handleSavedCohortAction,
    clearSavedCohortFromAnalysis,
  };
}
