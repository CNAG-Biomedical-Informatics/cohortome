import { downloadFile, downloadIcon, downloadStatus } from "./shared.js";
import { openMolecularExport } from './cohort_export.js';
import { createCohortLibrary } from './cohort_library.js';

function requestCohortName(defaultName, rename = false) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    dialog.className = 'chat-move-dialog';
    dialog.id = 'cohortNameDialog';
    dialog.setAttribute('aria-labelledby', 'cohortNameTitle');
    dialog.innerHTML = `<form>
      <h3 id="cohortNameTitle">${rename ? 'Rename cohort' : 'Save cohort'}</h3>
      <label for="cohortNameInput">Cohort name</label>
      <input id="cohortNameInput" type="text" required autocomplete="off">
      <div class="chat-move-actions">
        <button type="button" class="secondary-btn" data-cohort-name-cancel>Cancel</button>
        <button type="submit" class="primary-btn">${rename ? 'Rename' : 'Save cohort'}</button>
      </div>
    </form>`;
    const input = dialog.querySelector('input');
    input.value = defaultName;
    let result = null;
    dialog.querySelector('[data-cohort-name-cancel]').onclick = () => dialog.close();
    input.oninput = () => input.setCustomValidity('');
    dialog.querySelector('form').onsubmit = event => {
      event.preventDefault();
      if (!input.value.trim()) {
        input.setCustomValidity('Enter a cohort name.');
        input.reportValidity();
        return;
      }
      result = input.value.trim();
      dialog.close();
    };
    dialog.addEventListener('close', () => { dialog.remove(); resolve(result); }, { once: true });
    document.body.append(dialog);
    dialog.showModal();
    input.focus();
    input.select();
  });
}

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
    datasetLabelsForIds,
    currentDatasetIds,
    setAnalysisScopeMetadataFromSelection,
    clearAnalysisScopeMetadata,
    renderAnalysisCatalog,
  } = callbacks;
  let analysisNotice = "";
  let phenoNotice = "";
  const library = createCohortLibrary({escapeHtml, datasetLabels: datasetLabelsForIds,
    activeIds: currentDatasetIds, addRequiredDatasets: callbacks.addRequiredDatasets,
    reloadScope: async id => {
      await loadSavedCohorts();
      if (id && !state.savedCohorts.some(item => item.id === id)) {
        throw new Error('This cohort is no longer available in the workspace. Refresh its dataset access.');
      }
    }, onAction: handleSavedCohortAction});
  const findCohort = id => state.savedCohorts.find(item => item.id === id) || library.find(id);

  function noticeForMode(mode) {
    return mode === "pheno" ? phenoNotice : analysisNotice;
  }

  function setNoticeForMode(mode, message) {
    if (callbacks.currentTabName() === 'cohorts') library.say(message);
    if (mode === "pheno") {
      phenoNotice = String(message || "").trim();
    } else {
      analysisNotice = String(message || "").trim();
    }
  }

  function clearNoticeForMode(mode) {
    setNoticeForMode(mode, "");
  }

  function cohortIsActiveInCurrentUi(cohortId) {
    return state.analysisSelectedSavedCohortId === cohortId
      || state.analysisCompareSavedCohortId === cohortId
      || state.phenoSelectedSavedCohortIds.includes(cohortId);
  }

  function renderSavedCohortsInto(container, mode) {
    if (!container) return;
    const inlineNotice = noticeForMode(mode);
    if (!state.savedCohorts.length) {
      container.innerHTML = `${inlineNotice ? `<div class="saved-cohort-inline-status">${escapeHtml(inlineNotice)}</div>` : ""}<div class="empty">No saved cohorts yet.</div>`;
      return;
    }
    const primaryActionLabel = mode === "pheno" ? "Use in Pheno-Ranker" : "Use as Cohort A";
    const primaryAction = mode === "pheno" ? "load-pheno" : "load-analysis";
    container.innerHTML = `${inlineNotice ? `<div class="saved-cohort-inline-status">${escapeHtml(inlineNotice)}</div>` : ""}<div class="saved-cohort-list">${
      state.savedCohorts.map((item) => {
        const sampleIds = Array.isArray(item.sample_ids) && item.sample_ids.length
          ? item.sample_ids
          : (Array.isArray(item.patient_ids) ? item.patient_ids : []);
        const patientIds = Array.isArray(item.patient_ids) ? item.patient_ids : [];
        const datasetIds = Array.isArray(item.dataset_ids) && item.dataset_ids.length
          ? item.dataset_ids
          : (item.dataset_id ? [item.dataset_id] : []);
        const datasetLabels = datasetLabelsForIds(datasetIds);
        const memberLabels = item.members?.length ? item.members.map(m => `${m.sample_id || m.patient_id} · ${datasetLabelsForIds([m.dataset_id])[0] || m.dataset_id}`) : sampleIds;
        const preview = memberLabels.slice(0, 4).join(", ");
        const suffix = memberLabels.length > 4 ? ` ... (+${memberLabels.length - 4} more)` : "";
        const source = item.source && item.source.kind ? item.source.kind : "manual";
        const isActiveHere = cohortIsActiveInCurrentUi(item.id);
        return `
          <div class="saved-cohort-card">
            <strong>${escapeHtml(item.name || "Unnamed cohort")}</strong>
            <small>${escapeHtml(String(item.patient_count ?? patientIds.length))} patients • ${escapeHtml(String(item.sample_count ?? sampleIds.length))} samples • source: ${escapeHtml(source)}</small>
            ${datasetLabels.length ? `<small>${escapeHtml(datasetLabels.join(", "))}</small>` : ""}
            <small>${escapeHtml(preview)}${escapeHtml(suffix)}</small>
            <div class="saved-cohort-actions">
              <button type="button" class="query-chip action" data-saved-cohort-action="${primaryAction}" data-saved-cohort-id="${escapeHtml(item.id)}">${primaryActionLabel}</button>
              ${mode === "analysis" ? `<button type="button" class="query-chip action" data-saved-cohort-action="load-analysis-b" data-saved-cohort-id="${escapeHtml(item.id)}">Use as Cohort B</button>` : ""}
              <button type="button" class="query-chip" data-saved-cohort-action="copy" data-saved-cohort-id="${escapeHtml(item.id)}">Copy IDs</button>
              <button type="button" class="query-chip" data-saved-cohort-action="rename" data-saved-cohort-id="${escapeHtml(item.id)}">Rename</button>
              <button type="button" class="query-chip" data-saved-cohort-action="export-clinical" data-saved-cohort-id="${escapeHtml(item.id)}">${downloadIcon()}Export clinical data</button>
              <button type="button" class="query-chip" data-saved-cohort-action="export-molecular" data-saved-cohort-id="${escapeHtml(item.id)}">${downloadIcon()}Export molecular data</button>
              <button type="button" class="query-chip" data-saved-cohort-action="export" data-saved-cohort-id="${escapeHtml(item.id)}" title="Membership TSV and metadata JSON only; no clinical records or assay matrices">${downloadIcon()}Export membership</button>
              ${isActiveHere ? `<span class="query-chip badge" title="Detach this cohort from the current Analysis or Pheno state before deleting it here.">In use here</span>` : ""}
              <button type="button" class="query-chip danger-btn" data-saved-cohort-action="delete" data-saved-cohort-id="${escapeHtml(item.id)}"${isActiveHere ? ' disabled title="Detach this cohort from the current Analysis or Pheno state before deleting it here."' : ""}>Delete</button>
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
    library.render();
    renderSavedCohortsInto(savedCohortsEl, "analysis");
    renderSavedCohortsInto(phenoSavedCohortsEl, "pheno");
    renderPhenoSavedCohortsSelection();
  }

  function setSavedCohortStatus(message) {
    if (callbacks.currentTabName() === 'cohorts') { library.say(message); return; }
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
        if (callbacks.currentTabName() === 'cohorts') await library.load();
        return;
      }
      const payload = await response.json();
      state.savedCohorts = Array.isArray(payload.cohorts) ? payload.cohorts : [];
      renderSavedCohorts();
    } catch (_error) {
      state.savedCohorts = [];
      renderSavedCohorts();
    }
    if (callbacks.currentTabName() === 'cohorts') await library.load();
  }

  async function saveLatestQueryAsCohort() {
    const resultHandle = String(state.latestQueryResultHandle || "").trim();
    if (!state.latestQueryPatientIds.length && !resultHandle) return;
    const defaultName = state.latestQueryPrompt
      ? state.latestQueryPrompt.slice(0, 80)
      : `Saved cohort ${new Date().toLocaleString()}`;
    const name = await requestCohortName(defaultName);
    if (name === null) return;
    try {
      const response = await fetch("/saved-cohorts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
          dataset_ids: currentDatasetIds(),
          result_handle: resultHandle,
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

  async function saveIdsAsCohort(options = {}) {
    const sampleIds = Array.isArray(options.sampleIds) ? options.sampleIds.filter(Boolean) : [];
    const patientIds = Array.isArray(options.patientIds) ? options.patientIds.filter(Boolean) : [];
    const sourcePrompt = String(options.sourcePrompt || "").trim();
    const sourceKind = String(options.sourceKind || "manual").trim() || "manual";
    const statusTarget = options.statusTarget === "none" ? "none" : options.statusTarget === "pheno" ? "pheno" : "analysis";
    const defaultName = sourcePrompt
      ? sourcePrompt.slice(0, 80)
      : `Saved cohort ${new Date().toLocaleString()}`;
    const name = await requestCohortName(defaultName);
    if (name === null) return false;
    if (options.isCurrent && !options.isCurrent()) return false;
    try {
      const response = await fetch("/saved-cohorts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
          dataset_ids: currentDatasetIds(),
          sample_ids: sampleIds,
          patient_ids: patientIds,
          members: Array.isArray(options.members) ? options.members : undefined,
          id_type: sampleIds.length ? "sample" : "patient",
          source_kind: sourceKind,
          source_prompt: sourcePrompt,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(String(payload.detail || "Unable to save cohort."));
      }
      await loadSavedCohorts();
      const normalizedName = (name || defaultName).trim();
      if (statusTarget === "pheno") {
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = `Saved cohort "${normalizedName}".`;
      } else if (statusTarget === "analysis") {
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = `Saved cohort "${normalizedName}".`;
      }
      return true;
    } catch (error) {
      const message = error && error.message ? error.message : "Unable to save cohort.";
      if (statusTarget === "pheno") {
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = message;
      } else if (statusTarget === "analysis") {
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = message;
      }
      return false;
    }
  }

  async function renameSavedCohort(cohortId) {
    const item = findCohort(cohortId);
    if (!item) return;
    const name = await requestCohortName(item.name || "", true);
    if (name === null || name.trim() === item.name) return;
    const mode = callbacks.currentTabName() === "pheno" ? "pheno" : "analysis";
    try {
      if (!name.trim() || name.trim().length > 200) throw new Error("Cohort name must contain 1–200 characters.");
      const response = await fetch(`/saved-cohorts/${encodeURIComponent(cohortId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Unable to rename cohort.");
      Object.assign(item, payload);
      if (library.find(cohortId)) Object.assign(library.find(cohortId), payload);
      setNoticeForMode(mode, `Renamed cohort to "${payload.name}".`);
      renderAnalysisScopeSummary();
      renderAnalysisCompareScopeSummary();
    } catch (error) {
      setNoticeForMode(mode, error.message || "Unable to rename cohort.");
    }
    renderSavedCohorts();
  }

  async function deleteSavedCohortById(cohortId) {
    const targetMode = callbacks.currentTabName() === "pheno" ? "pheno" : "analysis";
    if (cohortIsActiveInCurrentUi(cohortId)) {
      const message = "Detach this cohort from the current Analysis or Pheno state before deleting it.";
      setNoticeForMode(targetMode, message);
      renderSavedCohorts();
      setSavedCohortStatus(message);
      return;
    }
    try {
      const response = await fetch(`/saved-cohorts/${encodeURIComponent(cohortId)}`, { method: "DELETE" });
      if (!response.ok) {
        let message = "Unable to delete saved cohort.";
        try {
          const payload = await response.json();
          message = String(payload.detail || payload.message || message);
        } catch (_error) {
        }
        throw new Error(message);
      }
      await loadSavedCohorts();
      clearNoticeForMode(targetMode);
      renderSavedCohorts();
      setSavedCohortStatus("Deleted saved cohort.");
    } catch (error) {
      const message = error && error.message ? error.message : "Unable to delete saved cohort.";
      setNoticeForMode(targetMode, message);
      renderSavedCohorts();
      setSavedCohortStatus(message);
    }
  }

  async function copySavedCohortIds(cohortId) {
    const item = findCohort(cohortId);
    const ids = Array.isArray(item && item.sample_ids) && item.sample_ids.length
      ? item.sample_ids
      : (Array.isArray(item && item.patient_ids) ? item.patient_ids : []);
    if (!item || !ids.length) return;
    try {
      await navigator.clipboard.writeText(item.members?.length
        ? ['dataset_id\tpatient_id\tsample_id', ...item.members.map(m => [m.dataset_id, m.patient_id, m.sample_id || ''].join('\t'))].join('\n')
        : ids.join(","));
      setSavedCohortStatus(`Copied ${ids.length} IDs from ${item.name}.`);
    } catch (_error) {
      setSavedCohortStatus("Unable to copy saved cohort IDs.");
    }
  }

  function useSavedCohortInAnalysis(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    if (!item || (!Array.isArray(item.sample_ids) && !Array.isArray(item.patient_ids))) return;
    clearNoticeForMode("analysis");
    state.analysisSelectedSavedCohortId = cohortId;
    if (typeof setAnalysisScopeMetadataFromSelection === "function") {
      setAnalysisScopeMetadataFromSelection({
        ...item,
        side: "a",
        sourceKind: item.source && item.source.kind ? item.source.kind : "saved_cohort",
        sourcePrompt: item.source && item.source.prompt ? item.source.prompt : `Saved cohort: ${item.name || cohortId}`,
      });
    }
    analysisSelectedPatientIdsEl.value = "";
    renderAnalysisScopeSummary();
    renderSavedCohorts();
    setActiveTab("analysis");
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = analysisCompareModeEl && analysisCompareModeEl.checked
      ? `Loaded saved cohort "${item.name}" into Cohort A.`
      : `Loaded saved cohort "${item.name}" into the analysis scope.`;
    if (typeof renderAnalysisCatalog === "function") renderAnalysisCatalog();
  }

  function useSavedCohortInAnalysisCompare(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    if (!item || (!Array.isArray(item.sample_ids) && !Array.isArray(item.patient_ids))) return;
    clearNoticeForMode("analysis");
    state.analysisCompareSavedCohortId = cohortId;
    if (typeof setAnalysisScopeMetadataFromSelection === "function") {
      setAnalysisScopeMetadataFromSelection({
        ...item,
        side: "b",
        sourceKind: item.source && item.source.kind ? item.source.kind : "saved_cohort",
        sourcePrompt: item.source && item.source.prompt ? item.source.prompt : `Saved cohort: ${item.name || cohortId}`,
      });
    }
    if (analysisCompareModeEl) analysisCompareModeEl.checked = true;
    renderAnalysisCompareMode();
    analysisCompareSelectedPatientIdsEl.value = "";
    renderAnalysisCompareScopeSummary();
    renderSavedCohorts();
    setActiveTab("analysis");
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = `Loaded saved cohort "${item.name}" into Cohort B.`;
    if (typeof renderAnalysisCatalog === "function") renderAnalysisCatalog();
  }

  function useSavedCohortInPheno(cohortId) {
    const item = state.savedCohorts.find((entry) => entry.id === cohortId);
    if (!item || (!Array.isArray(item.sample_ids) && !Array.isArray(item.patient_ids))) return;
    clearNoticeForMode("pheno");
    state.phenoQuerySelection = null;
    if (!state.phenoSelectedSavedCohortIds.includes(cohortId)) {
      state.phenoSelectedSavedCohortIds = state.phenoSelectedSavedCohortIds.concat([cohortId]);
    }
    renderPhenoSavedCohortsSelection();
    renderSavedCohorts();
    setActiveTab("pheno");
    phenoStatusEl.className = "pheno-status";
    phenoStatusEl.textContent = `Attached saved cohort "${item.name}" as a separate Pheno-Ranker reference.`;
  }

  function removeSavedCohortFromPheno(cohortId) {
    clearNoticeForMode("pheno");
    state.phenoSelectedSavedCohortIds = state.phenoSelectedSavedCohortIds.filter((item) => item !== cohortId);
    renderPhenoSavedCohortsSelection();
    renderSavedCohorts();
    phenoStatusEl.className = "pheno-status";
    phenoStatusEl.textContent = "Removed saved cohort from separate Pheno-Ranker references.";
  }

  function clearSavedCohortFromAnalysis(side) {
    if (side === "b") {
      clearNoticeForMode("analysis");
      state.analysisCompareSavedCohortId = "";
      if (typeof clearAnalysisScopeMetadata === "function") clearAnalysisScopeMetadata("b");
      renderAnalysisCompareScopeSummary();
      renderSavedCohorts();
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = analysisCompareModeEl && analysisCompareModeEl.checked
        ? "Cohort B cleared. Select a saved cohort to compare."
        : "Cohort B reverted to manual scope.";
      if (typeof renderAnalysisCatalog === "function") renderAnalysisCatalog();
      return;
    }
    clearNoticeForMode("analysis");
    state.analysisSelectedSavedCohortId = "";
    if (typeof clearAnalysisScopeMetadata === "function") clearAnalysisScopeMetadata("a");
    renderAnalysisScopeSummary();
    renderSavedCohorts();
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = analysisCompareModeEl && analysisCompareModeEl.checked
      ? "Cohort A cleared. Select a saved cohort to compare."
      : "Cohort A reverted to manual scope.";
    if (typeof renderAnalysisCatalog === "function") renderAnalysisCatalog();
  }

  function handleSavedCohortAction(button) {
    const cohortId = button.dataset.savedCohortId;
    if (!cohortId) return;
    if (button.dataset.savedCohortAction === 'export-molecular') return void openMolecularExport(cohortId, escapeHtml);
    if (button.dataset.savedCohortAction === "rename") return void renameSavedCohort(cohortId);
    if (["export", "export-clinical"].includes(button.dataset.savedCohortAction)) {
      const clinical = button.dataset.savedCohortAction === "export-clinical";
      const item = findCohort(cohortId);
      if (clinical && !window.confirm(`Export clinical BFF records for ${item?.patient_count ?? "the selected"} patients?\n\nIncludes all available visits from the cohort's source datasets, not only selected samples. Missing clinical records are listed in the manifest. Assay matrices and raw files are not included.\n\nMaximum: 100,000 records / 32 MiB. Handle this download as research data.`)) return;
      button.disabled = true;
      setSavedCohortStatus("Preparing cohort download…");
      void downloadFile(`/saved-cohorts/${encodeURIComponent(cohortId)}/export${clinical ? "?include=clinical" : ""}`, clinical ? "cohort-clinical-data.zip" : "saved-cohort.zip")
        .then(result => setSavedCohortStatus(downloadStatus(result)))
        .catch((error) => setSavedCohortStatus(error.message))
        .finally(() => { button.disabled = false; });
      return;
    }
    if (button.dataset.savedCohortAction === "load-analysis") return void useSavedCohortInAnalysis(cohortId);
    if (button.dataset.savedCohortAction === "load-analysis-b") return void useSavedCohortInAnalysisCompare(cohortId);
    if (button.dataset.savedCohortAction === "load-pheno") return void useSavedCohortInPheno(cohortId);
    if (button.dataset.savedCohortAction === "copy") return void copySavedCohortIds(cohortId);
    if (button.dataset.savedCohortAction === "delete") return void deleteSavedCohortById(cohortId);
  }

  return {
    loadLibrary: library.load,
    clearLibrary: library.clear,
    renderPhenoSavedCohortsSelection,
    renderSavedCohorts,
    loadSavedCohorts,
    saveLatestQueryAsCohort,
    saveIdsAsCohort,
    removeSavedCohortFromPheno,
    handleSavedCohortAction,
    clearSavedCohortFromAnalysis,
  };
}
