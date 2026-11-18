import {createClinicalCharts} from './charts/clinical.js';
import {openImagingDialog} from './react/ui.js';
import {renderPatientRoster,renderPatientDetail} from './react/ui.js';
import {renderReadinessView,renderMatrixView} from './react/ui.js';
import {renderNotice, renderOptions, renderScopeSource, renderAssayChoices, renderAssociationExamples, renderExpressionPreview} from './react/ui.js';
import { formatAssayModality, formatAssayDataType } from "./assay_labels.js";
import { fallbackCopyText } from "./shared.js";
import { createTimelineUi } from "./timeline.js";
import { createMultimodalCoverage } from './multimodal_coverage.js';
import { createVariantBrowser } from './variant_browser.js';
import { displayIdentity, decodeIdentity, identityKey } from './identities.js';
import { clinicalSexColor, clinicalSexCounts, clinicalMeasurements } from './clinical_chart_data.js';
import { createClinicalDashboardView, createAssayOverviewView, createAssayTabsView, createImagingStudiesView, createImagingHealthView, createAssayCardsView } from './react/ui.js';

export function createDashboardUi(ctx) {
  const { refs, helpers, callbacks, state, constants } = ctx;
  const {
    patientsEl,
    patientSearchEl,
    dashboardEl,
    detailEl,
    dataDirEl,
    assayDashboardStatusEl,
    assayDashboardOverviewEl,
    assayModalityTabsEl,
    assayDashboardCardsEl,
    multimodalReadinessPanelEl,
    multimodalReadinessStatusEl,
    multimodalReadinessContentEl,
    multimodalMatrixPanelEl,
    multimodalMatrixStatusEl,
    multimodalMatrixContentEl,
    dicomDashboardPanelEl,
    dicomDashboardHealthEl,
    dicomDashboardStatusEl,
    dicomDashboardStudiesEl,
    transcriptomicsQuickExpressionPanelEl,
    analysisAssayDatasetListEl,
    analysisCatalogAssayDatasetListEl,
    analysisAssayGeneEl,
    analysisAssayGenesEl,
    analysisAssayStatusEl,
    analysisCatalogAssayStatusEl,
    analysisAssayResultEl,
    analysisSelectedPatientIdsEl,
    analysisSelectedPatientIdsSummaryEl,
    analysisSelectedSavedCohortSelectionEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
    analysisCompareSelectedPatientIdsSummaryEl,
    analysisCompareSavedCohortSelectionEl,
  } = refs;
  const { escapeHtml, formatNumber } = helpers;
  const clinicalView = createClinicalDashboardView(dashboardEl);
  const assayOverviewView = createAssayOverviewView(assayDashboardOverviewEl);
  const assayTabsView = createAssayTabsView(assayModalityTabsEl);
  const imagingStudiesView = createImagingStudiesView(dicomDashboardStudiesEl);
  const imagingHealthView = createImagingHealthView(dicomDashboardHealthEl);
  const assayCardsView = createAssayCardsView(assayDashboardCardsEl);
  const imagingCardsView = createAssayCardsView(document.getElementById('imagingDashboardCards'));
  const {
    renderGlobalContext,
    syncCurrentAnalysisSessionFromUi,
    isMultiDatasetWorkspace,
    sendPatientIdsToAnalysis,
    saveIdsAsCohort,
    sendPromptToAnalysis,
    renderAnalysisCatalog,
    renderAnalysisCatalogAssayPanel,
  } = callbacks;
  const { MAX_VISIBLE_PATIENTS } = constants;
  const appliedScope = () => state.activePatientScope?.workspace === state.currentDatasetScopeId
    ? state.activePatientScope : null;
  const dashboardAssays = datasets => appliedScope() ? (appliedScope().assays || []) : (datasets || []);
  let scopeSnapshot = null, patientScopeKeys = new Set();
  const scopeHasPatient = (patientId, datasetId) => {
    const scope = appliedScope();
    if (!scope) return true;
    if (scopeSnapshot !== scope) {
      scopeSnapshot = scope;
      patientScopeKeys = new Set((scope.selection.members || []).map(member => JSON.stringify([member.dataset_id, member.patient_id])));
    }
    const identity = decodeIdentity(patientId);
    const dataset = identity?.datasetId || datasetId || (state.currentDatasetIds.length === 1 ? state.currentDatasetIds[0] : '');
    const id = identity?.sourceId || patientId;
    return patientScopeKeys.has(JSON.stringify([dataset, id]));
  };
  const multimodalCoverage = createMultimodalCoverage({state, escapeHtml, saveIdsAsCohort, renderGlobalContext});
  let variantPanelItems = [];
  const variantBrowser = createVariantBrowser({state, escapeHtml, saveIdsAsCohort, onPanels: panels => {
    variantPanelItems = panels.map(panel => ({...panel, variant_panel: true,
      modality: ['dna_sequencing', 'genotyping_array'].includes(panel.provenance?.technology) ? panel.provenance.technology : 'genotyping',
      feature_count: panel.variants, sample_count: panel.samples}));
    renderAssayDashboardCards(state.assayDatasetsState || []);
  }});
  const {dashboardPlotLayout, mountPlot, renderMeasurementDistributions, renderDashboardCharts} = createClinicalCharts({clinicalSexCounts, clinicalSexColor, formatNumber, clinicalRepresentation});
  const { renderDashboardTimeline, resetTimelineView, resetInspectorView } = createTimelineUi({
    state, refs,
    helpers: { escapeHtml, dashboardPlotLayout, mountPlot },
  });
  window.addEventListener('cohortome:scope-applied', () => {
    // Keep the workspace inventories used by captured Analysis chats intact.
    // Scope changes affect the displayed dashboards, not those stored inputs.
    variantPanelItems = [];
    renderDashboard(state.dashboardSummaryState || state.dashboardSummary || {});
    renderAssayDashboardCards(state.assayDatasetsState || []);
    renderDicomStudies(state.dicomStatus || {});
    renderMultimodalMatrixVisibility();
    void variantBrowser.load(state.currentDatasetScopeId);
  });

  function isCurrentWorkspaceScope(scopeId) {
    const normalized = String(scopeId || "").trim();
    return Boolean(normalized && normalized === String(state.currentDatasetScopeId || "").trim());
  }

  function clinicalRepresentation(payload = null) {
    const direct = String(payload && payload.clinical_representation ? payload.clinical_representation : "").trim().toLowerCase();
    if (direct) return direct;
    const activeIds = new Set(Array.isArray(state.currentDatasetIds) ? state.currentDatasetIds : []);
    const values = (Array.isArray(state.availableDatasets) ? state.availableDatasets : [])
      .filter((item) => activeIds.has(String(item && item.dataset_id ? item.dataset_id : "")))
      .map((item) => String(item && item.clinical_representation ? item.clinical_representation : "unspecified").trim().toLowerCase());
    return values.length && values.every((value) => value === values[0]) ? values[0] : "mixed";
  }

  function clinicalRecordLabel(payload, count, capitalize = false) {
    const representation = clinicalRepresentation(payload);
    const singular = representation === "snapshot" ? "timepoint" : representation === "person" ? "person record" : "clinical record";
    const label = Number(count) === 1 ? singular : `${singular}s`;
    return capitalize ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : label;
  }





  function currentRosterPatients() {
    const query = String(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : "").trim().toLowerCase();
    const patients = Array.isArray(state.currentPatients) ? state.currentPatients : [];
    if (!query) return patients;
    return patients.filter((patient) => patientMatchesIdentityQuery(patient, query));
  }

  function normalizedClarid(patient) {
    const value = patient && patient.clarid && typeof patient.clarid === "object" ? patient.clarid : null;
    if (!value || !String(value.human_id || "").trim() || !String(value.stub_id || "").trim()) return null;
    return value;
  }

  function patientMatchesIdentityQuery(patient, rawQuery) {
    const query = String(rawQuery || "").trim().toLowerCase();
    if (!query) return true;
    const clarid = normalizedClarid(patient);
    return [
      patient && patient.patient_id,
      clarid && clarid.human_id,
      clarid && clarid.stub_id,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  }

  function claridDecodedSummary(clarid) {
    if (!clarid) return "";
    const condition = clarid.condition_name
      ? `${clarid.condition_name} (${clarid.condition})` : clarid.condition;
    return [clarid.study, clarid.type, condition, clarid.sex, clarid.age_group]
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .join(" · ");
  }

  function claridSearchFeedback(items) {
    const query = String(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : "").trim().toLowerCase();
    if (!query) return "";
    const match = items.find((patient) => {
      const clarid = normalizedClarid(patient);
      return clarid && [clarid.human_id, clarid.stub_id].some((value) => String(value || "").toLowerCase() === query);
    });
    if (!match) return "";
    const clarid = normalizedClarid(match);
    return {summary:claridDecodedSummary(clarid),patientId:match.patient_id};
  }




  function renderPatientList(items) {
    renderPatientRoster(patientsEl,{total:items.length,limit:MAX_VISIBLE_PATIENTS,
      compact:state.currentDashboardSubtab==="timeline", feedback:claridSearchFeedback(items),
      items:items.slice(0,MAX_VISIBLE_PATIENTS).map(patient=>{
        const count=Number(patient.clinical_record_count ?? patient.visit_count ?? 0);
        return {...patient,clarid:normalizedClarid(patient),active:state.selectedPatientId===patient.patient_id,
          recordText:`${count} ${clinicalRecordLabel(patient,count)}`,
          datasetLabel:isMultiDatasetWorkspace() ? (patient.dataset_names || []).join(", ") : ""};
      })});
  }

  function renderDetail(patient) {
    resetInspectorView();
    const datasetNames = Array.isArray(patient.patient_context && patient.patient_context.dataset_names)
      ? patient.patient_context.dataset_names
      : (Array.isArray(patient.dataset_names) ? patient.dataset_names : []);
    const previewPayload = {
      patient_id: patient.patient_id,
      summary: patient.summary,
      patient_context: patient.patient_context,
      evidence: patient.evidence,
      key_fragments: (patient.key_fragments || []).slice(0, 12).map((fragment) => ({
        category: fragment.category,
        label: fragment.label,
        visit_id: fragment.visit_id,
        event_type: fragment.event_type,
        event_date: fragment.event_date,
        source_file: fragment.source_file,
        record_index: fragment.record_index,
        path: fragment.path,
      })),
      visits: (patient.visits || []).slice(0, 8).map((visit) => ({
        visit_id: visit.visit_id,
        event_type: visit.event_type,
        event_date: visit.event_date,
        diagnosis: visit.diagnosis,
        evidence: visit.evidence,
        key_fragments: (visit.key_fragments || []).slice(0, 6).map((fragment) => ({
          category: fragment.category,
          label: fragment.label,
          path: fragment.path,
        })),
      })),
    };
    renderPatientDetail(detailEl,{patient,preview:previewPayload,clarid:normalizedClarid(patient),
      person:clinicalRepresentation(patient)==="person",datasetLabel:isMultiDatasetWorkspace() ? datasetNames.join(", ") : ""});
  }

  function renderDashboard(summary = {}) {
    state.dashboardSummary = summary;
    const workspaceSummary = summary;
    const scope = appliedScope();
    const selection = scope ? {status:'ready', data:scope.summary,
      label:scope.selection.source?.prompt || 'Applied patient scope'} : null;
    if (selection?.status === 'ready') summary = selection.data || {};
    const datasets = summary.characteristics || [];
    const viewedDataset = datasets.find(item => item.dataset_id === state.dashboardClinicalDataset);
    if (!viewedDataset) state.dashboardClinicalDataset = '';
    if (viewedDataset?.chart_summary) summary = {...summary, ...viewedDataset.chart_summary};
    const tableMode = state.dashboardClinicalMode === 'table';
    const expanded = Boolean(state.dashboardClinicalExpanded);
    const totals = summary && summary.totals ? summary.totals : {};
    const representation = clinicalRepresentation(summary);
    const timelineButton = document.getElementById("dashboardTimelineBtn");
    if (timelineButton) {
      timelineButton.hidden = false;
      timelineButton.setAttribute("aria-hidden", "false");
    }
    const recordCount = Number(totals.clinical_records ?? totals.visits ?? summary.visits ?? 0);
    const viewedDatasets = viewedDataset ? [viewedDataset] : datasets;
    const measurementFields = clinicalMeasurements(viewedDatasets);
    const measurement = measurementFields.find(field => field.id === state.dashboardClinicalMeasurement) || measurementFields[0];
    if (measurement) state.dashboardClinicalMeasurement = measurement.id;
    clinicalView.render({
      totals, patients:totals.patients ?? summary.patients ?? 0, records:recordCount,
      representation, scoped:selection?.status === 'ready', workspacePatients:summary.workspace_patient_count,
      datasets, datasetId:state.dashboardClinicalDataset, tableMode, expanded, formatNumber,
      viewedDatasets, measurementFields, measurement, sexEntries:clinicalSexCounts(summary.sex_counts || {}),
      drawMeasurements:() => renderMeasurementDistributions(viewedDatasets, measurement),
      actions:{
        expand:() => { state.dashboardClinicalExpanded = !state.dashboardClinicalExpanded; renderDashboard(workspaceSummary); },
        mode:value => { state.dashboardClinicalMode = value; renderDashboard(workspaceSummary); },
        dataset:value => { state.dashboardClinicalDataset = value; renderDashboard(workspaceSummary); },
        measurement:value => { state.dashboardClinicalMeasurement = value; renderDashboard(workspaceSummary); },
      },
      draw:() => {
        if (!tableMode && (!selection || selection.status === 'ready')) {
          renderDashboardCharts(summary);
        }
      },
    });
    if (state.currentDashboardSubtab === "timeline") {
      renderDashboardTimeline(workspaceSummary);
    }
  }

  function renderAnalysisScopeSummary() {
    const selectedCohort = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
      : null;
    const metadata = !selectedCohort && state.analysisScopeMetadata && typeof state.analysisScopeMetadata === "object"
      ? state.analysisScopeMetadata
      : {};
    const queryResultHandle = String(metadata.query_result_handle || "").trim();
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    analysisSelectedPatientIdsEl.disabled = compareMode || Boolean(selectedCohort) || Boolean(queryResultHandle);
    const selectedCohortUsesSampleIds = Boolean(
      selectedCohort
      && Array.isArray(selectedCohort.sample_ids)
      && selectedCohort.sample_ids.length
    );
    const ids = selectedCohort && Array.isArray(selectedCohort.sample_ids) && selectedCohort.sample_ids.length
      ? selectedCohort.sample_ids.map((item) => String(item).trim()).filter(Boolean)
      : selectedCohort && Array.isArray(selectedCohort.patient_ids)
      ? selectedCohort.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String(analysisSelectedPatientIdsEl.value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const countLabel = selectedCohort
      ? `${selectedCohort.patient_count ?? (selectedCohort.patient_ids || []).length} patients / ${selectedCohort.sample_count ?? 0} samples`
      : metadata && (metadata.patient_count || metadata.sample_count)
        ? `${metadata.patient_count ?? 0} patients / ${metadata.sample_count ?? 0} samples`
      : `${ids.length} ${ids.length === 1 ? "ID" : "IDs"}`;
    const metadataSource = metadata && metadata.source && metadata.source.kind
      ? String(metadata.source.kind).replace(/_/g, " ")
      : "";
    analysisSelectedPatientIdsSummaryEl.textContent = compareMode
      ? (selectedCohort
        ? `Cohort A: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
        : ids.length
          ? `Cohort A: ${countLabel} in scope${metadataSource ? ` from ${metadataSource}` : ""}.`
        : "Cohort A: select a saved cohort from Saved Cohorts to compare.")
      : (selectedCohort
        ? `Scope: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
        : queryResultHandle
          ? `Scope: ${metadata.id_type === "sample" ? metadata.sample_count || 0 : metadata.patient_count || 0} ${metadata.id_type === "sample" ? "samples" : "patients"} from the Query result; identifiers remain server-side.`
        : ids.length
          ? `Scope: ${countLabel} in scope${metadataSource ? ` from ${metadataSource}` : ""}.`
          : "Scope: full workspace.");
    if (analysisSelectedSavedCohortSelectionEl) {
      if (selectedCohort) {
        analysisSelectedSavedCohortSelectionEl.classList.remove("is-hidden");
        renderScopeSource(analysisSelectedSavedCohortSelectionEl, "a", selectedCohort);
      } else {
        analysisSelectedSavedCohortSelectionEl.classList.add("is-hidden");
        renderScopeSource(analysisSelectedSavedCohortSelectionEl, "a", null);
      }
    }
    renderAssayDatasetSelector();
    renderAssayDashboardCards(state.assayDatasetsState);
    if (typeof renderAnalysisCatalog === "function") {
      renderAnalysisCatalog();
    }
    renderGlobalContext();
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  function renderAnalysisCompareScopeSummary() {
    if (!analysisCompareSelectedPatientIdsSummaryEl) return;
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    analysisCompareSelectedPatientIdsSummaryEl.classList.toggle("is-hidden", !compareMode);
    if (analysisCompareSavedCohortSelectionEl) {
      analysisCompareSavedCohortSelectionEl.classList.toggle("is-hidden", !compareMode);
      if (!compareMode) {
        renderScopeSource(analysisCompareSavedCohortSelectionEl, "b", null);
      }
    }
    if (!compareMode) {
      renderAssayDatasetSelector();
      renderAssayDashboardCards(state.assayDatasetsState);
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
      renderGlobalContext();
      syncCurrentAnalysisSessionFromUi({ render: true });
      return;
    }
    const selectedCohort = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
      : null;
    const metadata = !selectedCohort && state.analysisCompareScopeMetadata && typeof state.analysisCompareScopeMetadata === "object"
      ? state.analysisCompareScopeMetadata
      : {};
    if (analysisCompareSelectedPatientIdsEl) {
      analysisCompareSelectedPatientIdsEl.disabled = true;
    }
    const selectedCohortUsesSampleIds = Boolean(
      selectedCohort
      && Array.isArray(selectedCohort.sample_ids)
      && selectedCohort.sample_ids.length
    );
    const ids = selectedCohort && Array.isArray(selectedCohort.sample_ids) && selectedCohort.sample_ids.length
      ? selectedCohort.sample_ids.map((item) => String(item).trim()).filter(Boolean)
      : selectedCohort && Array.isArray(selectedCohort.patient_ids)
      ? selectedCohort.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String((analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value) || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const countLabel = selectedCohort
      ? `${selectedCohort.patient_count ?? (selectedCohort.patient_ids || []).length} patients / ${selectedCohort.sample_count ?? 0} samples`
      : metadata && (metadata.patient_count || metadata.sample_count)
        ? `${metadata.patient_count ?? 0} patients / ${metadata.sample_count ?? 0} samples`
      : `${ids.length} IDs`;
    const metadataSource = metadata && metadata.source && metadata.source.kind
      ? String(metadata.source.kind).replace(/_/g, " ")
      : "";
    analysisCompareSelectedPatientIdsSummaryEl.textContent = selectedCohort
      ? `Cohort B: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
      : ids.length
        ? `Cohort B: ${countLabel} in scope${metadataSource ? ` from ${metadataSource}` : ""}.`
      : "Cohort B: select a saved cohort from Saved Cohorts to compare.";
    if (analysisCompareSavedCohortSelectionEl) {
      if (selectedCohort) {
        renderScopeSource(analysisCompareSavedCohortSelectionEl, "b", selectedCohort);
      } else {
        renderScopeSource(analysisCompareSavedCohortSelectionEl, "b", null);
      }
    }
    renderAssayDatasetSelector();
    renderAssayDashboardCards(state.assayDatasetsState);
    if (typeof renderAnalysisCatalog === "function") {
      renderAnalysisCatalog();
    }
    renderGlobalContext();
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  function renderAssayExpressionResult(payload) {
    if (!analysisAssayResultEl) return;
    const payloads = payload ? (Array.isArray(payload) ? payload : [payload]) : [];
    analysisAssayResultEl.className = payloads.length ? "assay-result" : "assay-result empty";
    renderExpressionPreview(analysisAssayResultEl, payloads);
  }

  function selectedAssayDatasetNames() {
    const knownNames = new Set(
      state.assayDatasetsState.map((dataset) => String(dataset && dataset.dataset_name ? dataset.dataset_name : "").trim()).filter(Boolean)
    );
    return state.selectedAssayDatasets.filter((datasetName) => knownNames.has(datasetName));
  }

  function selectedTranscriptomicsAssayDatasetNames() {
    const transcriptomicsNames = new Set(
      state.assayDatasetsState
        .filter((dataset) => isQuickExpressionDataset(dataset))
        .map((dataset) => dataset.dataset_name)
    );
    return selectedAssayDatasetNames().filter((datasetName) => transcriptomicsNames.has(datasetName));
  }

  function currentAnalysisCatalogItem() {
    return Array.isArray(state.analysisCatalogItems)
      ? state.analysisCatalogItems.find((item) => String(item && item.id ? item.id : "") === String(state.analysisSelectedCatalogItemId || ""))
      : null;
  }

  function requiresSingleSelectedAssayDataset(item) {
    const itemId = String(item && item.id ? item.id : "").trim();
    return itemId === "transcriptomics-deseq2-differential-expression"
      || itemId === "transcriptomics-limma-voom-differential-expression"
      || itemId === "transcriptomics-hallmark-pathway-enrichment"
      || itemId === "transcriptomics-signature-workflow"
      || itemId === "methylation-qc-pca"
      || itemId === "methylation-limma-differential-methylation"
      || itemId === "flow-cytometry-wilcoxon-cohort-comparison"
      || itemId === "serology-wilcoxon-cohort-comparison";
  }

  function normalizedAssayDataType(dataset) {
    const explicit = String(dataset && dataset.data_type ? dataset.data_type : "").trim();
    if (explicit) return explicit;
    const modality = String(dataset && dataset.modality ? dataset.modality : "").trim();
    if (modality.endsWith("_raw_counts")) return "raw_counts";
    if (modality.endsWith("_relative_abundance")) return "relative_abundance";
    if (modality.endsWith("_protein_abundance")) return "protein_abundance";
    if (modality.endsWith("_cell_population_abundance")) return "cell_population_abundance";
    if (modality.endsWith("_quantitative_measurement")) return "quantitative_measurement";
    return "";
  }

  function isQuickExpressionDataset(dataset) {
    return normalizedAssayModality(dataset && dataset.modality) === "transcriptomics"
      && normalizedAssayDataType(dataset) === "raw_counts"
      && dataset.supports_expression_summary !== false;
  }

  function assayMatchesCatalogRequirement(dataset, item) {
    if (!item || !item.requires_assays) return true;
    const requiredModalities = Array.isArray(item.required_modalities)
      ? item.required_modalities.map((value) => normalizedAssayModality(value)).filter(Boolean)
      : [];
    const requiredDataTypes = Array.isArray(item.required_data_types)
      ? item.required_data_types.map((value) => String(value || "").trim()).filter(Boolean)
      : [];
    const modality = normalizedAssayModality(dataset && dataset.modality);
    const dataType = normalizedAssayDataType(dataset);
    if (requiredModalities.length && !requiredModalities.includes(modality)) return false;
    if (requiredDataTypes.length && !requiredDataTypes.includes(dataType)) return false;
    return true;
  }

  function groupAssaysByModality(datasets) {
    const groups = new Map();
    (Array.isArray(datasets) ? datasets : []).forEach((dataset) => {
      const key = normalizedAssayModality(dataset && dataset.modality);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(dataset);
    });
    return Array.from(groups.entries()).sort((left, right) => formatAssayModality(left[0]).localeCompare(formatAssayModality(right[0])));
  }

  function contextualAssayDatasets() {
    const item = currentAnalysisCatalogItem();
    if (!item || !item.requires_assays) {
      return [];
    }
    const compareRequired = Boolean(item.default_compare_mode);
    const minimumOverlap = Math.max(1, Number(item.minimum_samples_per_cohort || 1));
    const compatibleDatasets = state.assayDatasetsState.filter((dataset) => {
      if (!assayMatchesCatalogRequirement(dataset, item)) {
        return false;
      }
      const patientIds = Array.isArray(dataset && dataset.patient_ids) ? dataset.patient_ids : [];
      if (!patientIds.length) {
        return true;
      }
      const overlap = currentAssayScopeOverlap(patientIds);
      if (compareRequired) {
        return overlap.overlapA >= minimumOverlap && overlap.overlapB >= minimumOverlap;
      }
      if (overlap.scopeASize || overlap.scopeBSize) {
        return overlap.overlapA > 0 || overlap.overlapB > 0;
      }
      return true;
    });
    const compatibleNames = new Set(compatibleDatasets.map((dataset) => dataset.dataset_name));
    // An empty loading inventory is not evidence that a saved assay disappeared.
    if (!state.assayDatasetsScopeId) return compatibleDatasets;
    const filteredSelected = state.selectedAssayDatasets.filter((name) => compatibleNames.has(name));
    if (filteredSelected.length !== state.selectedAssayDatasets.length) {
      state.selectedAssayDatasets = filteredSelected;
    }
    if (
      requiresSingleSelectedAssayDataset(item)
      && compatibleDatasets.length === 1
      && (
        state.selectedAssayDatasets.length !== 1
        || state.selectedAssayDatasets[0] !== compatibleDatasets[0].dataset_name
      )
    ) {
      state.selectedAssayDatasets = [compatibleDatasets[0].dataset_name];
    }
    return compatibleDatasets;
  }

  function renderAssayDatasetSelector() {
    const item = currentAnalysisCatalogItem();
    const contextRequiresAssay = Boolean(item && item.requires_assays);
    const mainListEl = analysisAssayDatasetListEl;
    const contextualListEl = analysisCatalogAssayDatasetListEl;
    if (!mainListEl && !contextualListEl) return;
    if (!state.assayDatasetsState.length) {
      renderNotice(mainListEl, "No assay loaded");
      renderNotice(contextualListEl, "No assay loaded");
      return;
    }
    const selected = new Set(state.selectedAssayDatasets);
    const groupsFor = (datasets, includeOverlap=false) => groupAssaysByModality(datasets).map(([modality, items]) => ({
      label:formatAssayModality(modality), items:items.map(dataset => {
        const overlap=currentAssayScopeOverlap(dataset.patient_ids), panel=dataset.feature_panel;
        const panelMeta=panel ? ` • Panel v${panel.panel_version || ""}${panel.independent_of_target_cohort ? " • independently selected" : ""}` : "";
        const base=`${dataset.sample_count || 0} samples, ${Number(dataset.feature_count || dataset.gene_count || 0)} ${dataset.feature_label || "features"} • ${formatAssayDataType(normalizedAssayDataType(dataset) || dataset.data_type)}${panelMeta}`;
        return {value:dataset.dataset_name,label:dataset.label || dataset.dataset_name,checked:selected.has(dataset.dataset_name),
          description:base+(includeOverlap ? ` • A overlap ${overlap.overlapA}${analysisCompareModeEl?.checked ? ` • B overlap ${overlap.overlapB}` : ""}` : "")};
      })
    }));
    renderAssayChoices(mainListEl,groupsFor(state.assayDatasetsState.filter(isQuickExpressionDataset)),"No raw-count transcriptomics assays available");
    renderAssayChoices(contextualListEl,contextRequiresAssay ? groupsFor(contextualAssayDatasets(),true) : [],
      contextRequiresAssay ? "No compatible assays are available in this workspace." : "Choose an assay analysis to select a compatible assay.");
  }

  function syncSelectedAssayDatasets() {
    const available = new Set(state.assayDatasetsState.map((item) => item.dataset_name));
    state.selectedAssayDatasets = state.selectedAssayDatasets.filter((item) => available.has(item));
    renderAssayDatasetSelector();
  }

  function clearAssayWorkspaceSelection() {
    state.selectedAssayDatasets = [];
    if (analysisAssayGeneEl) {
      analysisAssayGeneEl.value = "";
    }
    renderAssayExpressionResult(null);
  }

  function clearDatasetWorkspaceViews(options = {}) {
    const signedOut = options.signedOut === true;
    const workspaceMessage = signedOut ? "Sign in to access shared assays." : "No workspace loaded.";
    state.assayDatasetsState = [];
    state.assayDatasetsScopeId = "";
    state.assayDashboardModalityFilter = "all";
    state.multimodalReadinessState = null;
    state.multimodalMatrixState = null;
    state.dicomStudiesState = [];
    state.dicomStatus = null;
    state.dashboardSummary = null;
    clearAssayWorkspaceSelection();
    if (analysisAssayGenesEl) renderOptions(analysisAssayGenesEl);
    renderAssayDatasetSelector();
    renderAssayDashboardCards([]);
    if (analysisAssayStatusEl) {
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = workspaceMessage;
    }
    if (analysisCatalogAssayStatusEl) {
      analysisCatalogAssayStatusEl.textContent = workspaceMessage;
    }
    if (assayDashboardStatusEl) {
      assayDashboardStatusEl.className = "query-status";
      assayDashboardStatusEl.textContent = workspaceMessage;
    }
    if (dicomDashboardHealthEl) {
      imagingHealthView.render({message:signedOut ? 'Sign in to inspect DICOM viewer status.' : 'Load a workspace to inspect DICOM viewer status.'});
    }
    if (dicomDashboardStatusEl) {
      dicomDashboardStatusEl.className = "dashboard-count";
      dicomDashboardStatusEl.textContent = signedOut ? "Sign in to access DICOM studies." : "No workspace loaded.";
    }
    if (dicomDashboardStudiesEl) {
      imagingStudiesView.render({empty:'No DICOM studies loaded.'});
    }
    if (multimodalReadinessStatusEl) {
      multimodalReadinessStatusEl.hidden = false;
      document.getElementById('multimodalReadinessSummary').textContent = '';
      multimodalReadinessStatusEl.className = "query-status";
      multimodalReadinessStatusEl.textContent = workspaceMessage;
    }
    if (multimodalReadinessContentEl) {
      multimodalCoverage.reset();
      renderNotice(multimodalReadinessContentEl,"Load a workspace to review multimodal readiness.");
    }
    if (multimodalMatrixStatusEl) {
      multimodalMatrixStatusEl.className = "query-status";
      multimodalMatrixStatusEl.textContent = workspaceMessage;
    }
    if (multimodalMatrixContentEl) {
      renderNotice(multimodalMatrixContentEl,"Load a workspace to build a multimodal feature matrix.");
    }
    if (typeof renderAnalysisCatalogAssayPanel === "function") renderAnalysisCatalogAssayPanel();
    if (typeof renderAnalysisCatalog === "function") renderAnalysisCatalog();
  }

  function assayDatasetOverlap(datasetName) {
    const normalizedName = String(datasetName || "").trim();
    if (!normalizedName) return null;
    const dataset = state.assayDatasetsState.find((item) => String(item && item.dataset_name ? item.dataset_name : "").trim() === normalizedName);
    if (!dataset) return null;
    return currentAssayScopeOverlap(dataset.patient_ids);
  }

  function currentAssayScopeOverlap(patientIds) {
    const qualifyPatient = value => {
      const id = String(value).trim();
      return decodeIdentity(id) || state.currentDatasetIds.length !== 1 ? id : identityKey(state.currentDatasetIds[0], 'patient', id);
    };
    const datasetPatientIds = new Set((Array.isArray(patientIds) ? patientIds : []).map(qualifyPatient));
    const selectedCohortA = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
      : null;
    const selectedCohortB = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
      : null;
    const scopeA = selectedCohortA && Array.isArray(selectedCohortA.patient_ids)
      ? selectedCohortA.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String(analysisSelectedPatientIdsEl && analysisSelectedPatientIdsEl.value ? analysisSelectedPatientIdsEl.value : "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const scopeB = selectedCohortB && Array.isArray(selectedCohortB.patient_ids)
      ? selectedCohortB.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String(analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value ? analysisCompareSelectedPatientIdsEl.value : "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const overlapA = scopeA.filter((item) => datasetPatientIds.has(qualifyPatient(item))).length;
    const overlapB = scopeB.filter((item) => datasetPatientIds.has(qualifyPatient(item))).length;
    return { overlapA, overlapB, scopeASize: scopeA.length, scopeBSize: scopeB.length };
  }

  function renderDicomHealth(payload) {
    if (!dicomDashboardHealthEl) return;
    const source = payload && typeof payload === 'object' ? payload : {};
    state.dicomStatus = {...(state.dicomStatus || {}), ...source};
    imagingHealthView.render({source, studies:state.dicomStudiesState || []});
    renderAssayDashboardOverview(state.assayDatasetsState || []);
  }

  function renderDicomHealthError(message) {
    if (!dicomDashboardHealthEl) return;
    imagingHealthView.render({message:message || 'Unable to load DICOM viewer status.'});
  }

  function renderDicomStudies(payload) {
    if (!dicomDashboardStatusEl || !dicomDashboardStudiesEl) return;
    const source = payload && typeof payload === "object" ? payload : {};
    const enabled = Boolean(source.enabled);
    const allStudies = Array.isArray(source.studies) ? source.studies : [];
    const studies = allStudies.filter(study => scopeHasPatient(study.patient_id, study.source_dataset_id));
    state.dicomStatus = { ...(state.dicomStatus || {}), ...source };
    state.dicomStudiesState = allStudies;
    dicomDashboardStatusEl.className = "dashboard-count";
    if (!studies.length) {
      dicomDashboardStatusEl.textContent = appliedScope() ? 'No imaging studies in the applied scope.' : 'No imaging studies listed in this workspace.';
      imagingStudiesView.render({empty:appliedScope() ? 'No linked DICOM studies for these patients.' : 'No DICOM studies configured.'});
      renderAssayDashboardOverview(state.assayDatasetsState || []);
      return;
    }
    const patients = new Set(studies.filter(study => study.patient_id).map(study => {
      const identity = decodeIdentity(study.patient_id);
      return JSON.stringify([identity?.datasetId || study.source_dataset_id || '', identity?.sourceId || study.patient_id]);
    }));
    const unlinked = studies.filter(study => !study.patient_id).length;
    dicomDashboardStatusEl.textContent = `${patients.size} ${unlinked ? 'linked ' : ''}${patients.size === 1 ? 'patient' : 'patients'} · ${studies.length} imaging ${studies.length === 1 ? 'study' : 'studies'}${unlinked ? ` · ${unlinked} without patient linkage` : ''}`;
    const patientLabel = study => {
      if (!study.patient_id) return 'Not linked';
      if (decodeIdentity(study.patient_id)) return displayIdentity(study.patient_id);
      return study.source_dataset_id ? `${study.source_dataset_id} · ${study.patient_id}` : String(study.patient_id);
    };
    const patientLabels = [...new Set(studies.map(patientLabel))].sort((a,b) => a.localeCompare(b, undefined, {numeric:true}));
    imagingStudiesView.render({studies, enabled, patientLabels, patientLabel, openViewer:openImagingViewer});
    renderAssayDashboardOverview(state.assayDatasetsState || []);
  }

  function openImagingViewer(value, button) {
    let url;
    try { url = new URL(value, window.location.origin); } catch (_) { return; }
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/local-viewer/open/')) return;
    openImagingDialog(url.href,button);
  }

  async function loadDicomStudies(options = {}) {
    if (!dicomDashboardStatusEl || !dicomDashboardStudiesEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const dataDir = encodeURIComponent(scopeId);
    dicomDashboardStatusEl.className = "dashboard-count loading";
    dicomDashboardStatusEl.textContent = "Checking DICOM studies...";
    if (dicomDashboardHealthEl) {
      imagingHealthView.render({message:'Checking DICOM viewer status...'});
    }
    const [studiesResult, statusResult] = await Promise.allSettled([
      fetch(`/dicom/studies?data_dir=${dataDir}`),
      fetch(`/dicom/status?data_dir=${dataDir}`),
    ]);
    if (!isCurrentWorkspaceScope(scopeId)) return;
    if (studiesResult.status === "fulfilled" && studiesResult.value.ok) {
      renderDicomStudies(await studiesResult.value.json());
    } else {
      const error = studiesResult.status === "rejected" ? studiesResult.reason : null;
      state.dicomStudiesState = [];
      dicomDashboardStatusEl.className = "dashboard-count";
      dicomDashboardStatusEl.textContent = error && error.message ? error.message : "Unable to load DICOM studies.";
      imagingStudiesView.render({empty:'No DICOM studies configured.'});
    }
    if (statusResult.status === "fulfilled" && statusResult.value.ok) {
      renderDicomHealth(await statusResult.value.json());
    } else {
      const error = statusResult.status === "rejected" ? statusResult.reason : null;
      renderDicomHealthError(error && error.message ? error.message : "Unable to load DICOM viewer status.");
    }
  }

  function normalizedAssayModality(value) {
    const normalized = String(value || "assay").trim() || "assay";
    if (normalized.startsWith("transcriptomics")) return "transcriptomics";
    if (normalized.startsWith("proteomics")) return "proteomics";
    if (normalized.startsWith("olink")) return "olink";
    if (normalized.startsWith("flow_cytometry") || normalized.startsWith("immune_cell")) return "flow_cytometry";
    if (normalized.startsWith("serology")) return "serology";
    if (normalized === "genotyping_array") return normalized;
    if (normalized.startsWith("genotyping") || normalized.startsWith("variant")) return "genotyping";
    if (normalized.startsWith("imaging") || normalized === "dicom") return "imaging";
    return normalized;
  }

  function assayModalityCounts(datasets) {
    const counts = new Map();
    (Array.isArray(datasets) ? datasets : []).forEach((dataset) => {
      const modality = normalizedAssayModality(dataset && dataset.modality);
      counts.set(modality, (counts.get(modality) || 0) + 1);
    });
    return counts;
  }

  function assayModalityTabs(datasets) {
    datasets = (datasets || []).filter((item) => normalizedAssayModality(item.modality) !== "imaging");
    const counts = assayModalityCounts(datasets);
    return [
      { key: "all", label: "All", count: Array.isArray(datasets) ? datasets.length : 0 },
      ...Array.from(counts.entries())
        .sort((left, right) => formatAssayModality(left[0]).localeCompare(formatAssayModality(right[0])))
        .map(([key, count]) => ({ key, label: formatAssayModality(key), count })),
    ];
  }

  function selectedAssayModalityFilter() {
    const value = String(state.assayDashboardModalityFilter || "all").trim() || "all";
    const tabs = assayModalityTabs([...dashboardAssays(state.assayDatasetsState), ...variantPanelItems]);
    return tabs.some((tab) => tab.key === value) ? value : "all";
  }

  function renderAssayDashboardOverview(datasets) {
    if (!assayDashboardOverviewEl) return;
    const items = [...dashboardAssays(datasets).filter(item => !item.variant_panel), ...variantPanelItems]
      .filter((item) => normalizedAssayModality(item.modality) !== "imaging");
    if (!items.length) {
      assayOverviewView.render({empty:appliedScope() ? 'No linked assays in the applied patient scope.' : 'Load assays to review modality coverage.'});
      return;
    }
    const patientIds = new Set();
    const sampleIds = new Set();
    let featureTotal = 0;
    items.forEach((item) => {
      (Array.isArray(item.patient_ids) ? item.patient_ids : []).forEach((id) => patientIds.add(String(id || "").trim()));
      (Array.isArray(item.sample_ids) ? item.sample_ids : []).forEach((id) => sampleIds.add(String(id || "").trim()));
      featureTotal += Number(item.feature_count || item.gene_count || 0);
    });
    const modalities = Array.from(assayModalityCounts(items).keys()).sort((left, right) => formatAssayModality(left).localeCompare(formatAssayModality(right)));
    const coverage = modalities.map(modality => {
      const assays = items.filter(item => normalizedAssayModality(item.modality) === modality);
      const known = assays.every(item => Array.isArray(item.patient_ids));
      const patients = new Set(assays.flatMap(item => item.patient_ids || []).map(String).filter(id => id.trim()));
      return { modality, count: known ? patients.size : null };
    });
    const totalKnown = items.every(item => Array.isArray(item.patient_ids));
    const featureCountsKnown = items.every(item => (item.feature_count ?? item.gene_count) != null);
    const totalPatients = [...patientIds].filter(Boolean).length;
    const denominator = totalKnown ? totalPatients : Math.max(1, ...coverage.map(item => item.count || 0));
    assayOverviewView.render({assays:items.length, samples:sampleIds.size, patients:patientIds.size,
      scoped:!!appliedScope(), featureCountsKnown, featureTotal, totalKnown, totalPatients,
      denominator, coverage, formatNumber, formatModality:formatAssayModality});
  }

  function renderAssayModalityTabs(datasets) {
    if (!assayModalityTabsEl) return;
    const tabs = assayModalityTabs(datasets);
    const selected = selectedAssayModalityFilter();
    assayTabsView.render(tabs, selected);
  }

  function renderDicomPanelVisibility() {
    if (!dicomDashboardPanelEl) return;
    dicomDashboardPanelEl.classList.remove("is-hidden");
    dicomDashboardPanelEl.setAttribute("aria-hidden", "false");
  }

  function renderTranscriptomicsQuickExpressionVisibility() {
    if (!transcriptomicsQuickExpressionPanelEl) return;
    const visible = !appliedScope() && selectedAssayModalityFilter() === "transcriptomics"
      && state.assayDatasetsState.some((dataset) => isQuickExpressionDataset(dataset));
    transcriptomicsQuickExpressionPanelEl.classList.toggle("is-hidden", !visible);
    transcriptomicsQuickExpressionPanelEl.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function renderMultimodalReadinessVisibility() {
    if (!multimodalReadinessPanelEl) return;
    multimodalReadinessPanelEl.classList.remove("is-hidden");
    multimodalReadinessPanelEl.setAttribute("aria-hidden", "false");
  }

  function renderMultimodalMatrixVisibility() {
    if (!multimodalMatrixPanelEl) return;
    const hidden = Boolean(appliedScope());
    multimodalMatrixPanelEl.classList.toggle('is-hidden', hidden);
    multimodalMatrixPanelEl.setAttribute('aria-hidden', String(hidden));
  }

  function renderMultimodalReadiness(payload) {
    if (!multimodalReadinessStatusEl || !multimodalReadinessContentEl) return;
    multimodalCoverage.reset();
    const source = payload && typeof payload === "object" ? payload : {};
    const modalities = Array.isArray(source.modalities) ? source.modalities : [];
    const issues = Array.isArray(source.issues) ? source.issues : [];
    state.multimodalReadinessState = source;
    multimodalReadinessStatusEl.className = issues.some((item) => item && item.severity === "error") ? "query-status error" : "query-status";
    multimodalReadinessStatusEl.hidden = modalities.length > 0;
    multimodalReadinessStatusEl.textContent = modalities.length ? '' : 'No multimodal readiness data available.';
    document.getElementById('multimodalReadinessSummary').textContent = modalities.length
      ? `${modalities.length} data types checked across the workspace.` : '';
    renderReadinessView(multimodalReadinessContentEl,{modalities,issues});
    void multimodalCoverage.load(multimodalReadinessContentEl.querySelector('.multimodal-coverage'), state.currentDatasetScopeId);
    renderMultimodalReadinessVisibility();
  }

  function renderMultimodalReadinessError(message) {
    if (!multimodalReadinessStatusEl || !multimodalReadinessContentEl) return;
    multimodalCoverage.reset();
    state.multimodalReadinessState = null;
    multimodalReadinessStatusEl.className = "query-status";
    multimodalReadinessStatusEl.hidden = false;
    document.getElementById('multimodalReadinessSummary').textContent = '';
    multimodalReadinessStatusEl.textContent = message || "Unable to load multimodal readiness.";
    renderNotice(multimodalReadinessContentEl,"Multimodal readiness is unavailable for this workspace.");
    renderMultimodalReadinessVisibility();
  }

  function renderMultimodalMatrix(payload) {
    if (!multimodalMatrixStatusEl || !multimodalMatrixContentEl) return;
    const source = payload && typeof payload === "object" ? payload : {};
    const metadata = source.metadata && typeof source.metadata === "object" ? source.metadata : {};
    state.multimodalMatrixState = source;
    multimodalMatrixStatusEl.className = "query-status";
    multimodalMatrixStatusEl.textContent = Number(metadata.row_count || 0)
      ? `${metadata.row_count || 0} records checked · ${(source.missingness || []).length} preview fields`
      : "No matrix rows available.";
    renderMatrixView(multimodalMatrixContentEl,source);
    renderMultimodalMatrixVisibility();
  }

  function renderMultimodalMatrixError(message) {
    if (!multimodalMatrixStatusEl || !multimodalMatrixContentEl) return;
    state.multimodalMatrixState = null;
    multimodalMatrixStatusEl.className = "query-status";
    multimodalMatrixStatusEl.textContent = message || "Unable to build multimodal feature matrix.";
    renderNotice(multimodalMatrixContentEl,"Multimodal feature matrix is unavailable for this workspace.");
    renderMultimodalMatrixVisibility();
  }


  function assayCardsModel(items, extra = {}) {
    return {...extra, entries:items.map(item => ({item, modality:normalizedAssayModality(item.modality),
      dataType:normalizedAssayDataType(item) || item.data_type,
      valueKind:String(item.value_kind || normalizedAssayDataType(item) || item.data_type || 'feature_matrix').trim(),
      overlap:appliedScope() ? null : currentAssayScopeOverlap(item.patient_ids)})),
      formatModality:formatAssayModality, formatDataType:formatAssayDataType, number:formatNumber,
      compare:!!analysisCompareModeEl?.checked,
      openVariant:(dataset, button) => void variantBrowser.open(dataset, button)};
  }
  function filteredAssayDatasets(datasets) {
    const selected = selectedAssayModalityFilter();
    const items = Array.isArray(datasets) ? datasets : [];
    if (selected === "all") return items;
    return items.filter((item) => normalizedAssayModality(item && item.modality) === selected);
  }

  function renderAssayDashboardCards(datasets) {
    if (!assayDashboardCardsEl) return;
    const allItems = Array.isArray(datasets) ? datasets : [];
    for (const axis of ["X", "Y"]) {
      const select = document.getElementById(`associationAssay${axis}`);
      if (!select) continue;
      const previous = select.value;
      renderOptions(select,[{value:"",label:"Choose a matrix"},...allItems.map(item=>({value:item.dataset_name,label:`${formatAssayModality(item.modality)} · ${item.label || item.dataset_name}`}))]);
      if (allItems.some(item => item.dataset_name === previous)) select.value = previous;
      const feature = document.getElementById(`associationFeature${axis}`);
      const search = document.getElementById(`associationSearch${axis}`);
      const status = document.getElementById(`associationFeatureStatus${axis}`);
      const description = document.getElementById(`associationDescription${axis}`);
      let annotations = {};
      feature.onchange = () => {
        const annotation = annotations[feature.value] || {};
        description.textContent = feature.value ? [
          annotation.description || annotation.gene_name || "No description supplied for this feature.",
          annotation.unit ? `Units: ${annotation.unit}.` : "Units not supplied.",
        ].join(" ") : "";
      };
      // Invalidates responses from previous renders as well as rapid searches.
      const resetFeatures = (label) => {
        feature._request = {};
        renderOptions(feature,[{value:"",label}]);
        feature.disabled = true;
        status.textContent = "";
        description.textContent = "";
        annotations = {};
      };
      let searchTimer;
      const loadFeatures = async () => {
        if (!select.value) return;
        resetFeatures("Loading features…");
        const request = feature._request;
        const assay = select.value;
        const scope = state.currentDatasetScopeId;
        const isCurrent = () => feature._request === request && select.value === assay && state.currentDatasetScopeId === scope;
        try {
          const response = await fetch(`/assays/features?data_dir=${encodeURIComponent(scope)}&assay_id=${encodeURIComponent(assay)}&q=${encodeURIComponent(search.value.trim())}&limit=50`);
          if (!response.ok) throw new Error("Feature lookup failed");
          const payload = await response.json();
          if (!isCurrent()) return;
          const ids = payload.genes || [];
          annotations = payload.annotations || {};
          renderOptions(feature,[{value:"",label:ids.length ? "Choose a feature" : "No matching features"},...ids.map(id=>{
            const annotation=annotations[id] || {}, label=annotation.label || annotation.gene_symbol || annotation.gene_name;
            return {value:id,label:label ? `${label} · ${id}` : `${id} · Name not supplied`};
          })]);
          feature.disabled = !ids.length;
          status.textContent = ids.length >= 50 ? "Showing up to 50 matches. Search to narrow the list." : `${ids.length} available feature${ids.length === 1 ? "" : "s"}${search.value.trim() ? " matching your search" : ""}.`;
          return true;
        } catch (_) {
          if (!isCurrent()) return;
          resetFeatures("Features unavailable");
          status.textContent = "Could not load features. Edit the search or reselect the matrix to retry.";
        }
      };
      select.onchange = () => {
        clearTimeout(searchTimer);
        search.value = "";
        search.disabled = !select.value;
        resetFeatures("Choose a matrix first");
        return loadFeatures();
      };
      search.oninput = () => {
        clearTimeout(searchTimer);
        resetFeatures("Searching features…");
        const request = feature._request;
        searchTimer = setTimeout(() => {
          if (feature._request === request) void loadFeatures();
        }, 250);
      };
      select.onchange();
    }
    const examples = document.getElementById("associationExamples");
    if (examples) {
      const flow = "synthetic_autoimmune_flow_cytometry";
      const serology = "synthetic_autoimmune_serology";
      examples.hidden = ![flow, serology].every(id => allItems.some(item => item.dataset_name === id));
      renderAssociationExamples(examples,!examples.hidden);
      examples.querySelectorAll("button").forEach(button => {
        button.onclick = async () => {
          await Promise.all([['X', flow, button.dataset.exampleX], ['Y', serology, button.dataset.exampleY]].map(async ([axis, assay, id]) => {
            const matrix = document.getElementById(`associationAssay${axis}`);
            matrix.value = assay;
            const loaded = await matrix.onchange();
            const feature = document.getElementById(`associationFeature${axis}`);
            if (loaded && matrix.value === assay && Array.from(feature.options).some(option => option.value === id)) {
              feature.value = id;
              feature.onchange();
            }
          }));
        };
      });
    }
    const associationBtn = document.getElementById("associationOpenBtn");
    if (associationBtn) {
      associationBtn.disabled = allItems.length < 2;
      associationBtn.onclick = () => {
        const parameters = {};
        for (const axis of ["X", "Y"]) {
          parameters[`assay_${axis.toLowerCase()}`] = document.getElementById(`associationAssay${axis}`).value;
          parameters[`feature_${axis.toLowerCase()}`] = document.getElementById(`associationFeature${axis}`).value.trim();
        }
        if (Object.values(parameters).some(value => !value)) {
          document.getElementById("associationStatus").textContent = "Choose both matrices and select a feature from each dropdown.";
          return;
        }
        sendPromptToAnalysis(`Compare measurements: ${JSON.stringify(parameters)}`);
        document.getElementById("associationStatus").textContent = "Comparison prompt ready. Review the question and cohort scope, keep A/B comparison off, then select Run analysis.";
      };
    }
    const displayedItems = dashboardAssays(allItems);
    const imagingItems = displayedItems.filter((item) => normalizedAssayModality(item.modality) === "imaging");
    imagingCardsView.render(imagingItems.length ? assayCardsModel(imagingItems, {imaging:true})
      : {empty:'No derived imaging measurements in this workspace. DICOM studies, when available, are listed above.'});
    const items = [...displayedItems, ...variantPanelItems].filter((item) => normalizedAssayModality(item.modality) !== "imaging");
    renderAssayDashboardOverview(items);
    renderAssayModalityTabs(items);
    renderDicomPanelVisibility();
    renderTranscriptomicsQuickExpressionVisibility();
    renderMultimodalReadinessVisibility();
    renderMultimodalMatrixVisibility();
    if (!items.length) {
      assayCardsView.render({empty:'No assay data to display. Check the workspace selection and assay availability in Datasets.'});
      return;
    }
    const selected = selectedAssayModalityFilter();
    const visibleItems = filteredAssayDatasets(items);
    if (!visibleItems.length) {
      assayCardsView.render({empty:'No assays match the selected modality. Choose another modality filter to see the available assays.'});
      return;
    }
    assayCardsView.render(assayCardsModel(visibleItems, {title:selected === 'all' ? 'All assays' : formatAssayModality(selected)}));
  }

  function handleAssayModalityFilter(value) {
    state.assayDashboardModalityFilter = String(value || "all").trim() || "all";
    renderAssayDashboardCards(state.assayDatasetsState || []);
  }

  async function loadMultimodalReadiness(options = {}) {
    if (!multimodalReadinessStatusEl || !multimodalReadinessContentEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const dataDir = encodeURIComponent(scopeId);
    multimodalReadinessStatusEl.className = "query-status loading";
    multimodalReadinessStatusEl.hidden = false;
    document.getElementById('multimodalReadinessSummary').textContent = '';
    multimodalReadinessStatusEl.textContent = "Checking multimodal readiness...";
    multimodalCoverage.reset();
    renderNotice(multimodalReadinessContentEl,"Checking modality overlap and linkage...");
    try {
      const response = await fetch(`/assays/readiness?data_dir=${dataDir}`);
      if (!response.ok) throw new Error("Unable to load multimodal readiness.");
      const payload = await response.json();
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalReadiness(payload);
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalReadinessError(error && error.message ? error.message : "Unable to load multimodal readiness.");
    }
  }

  async function loadMultimodalMatrix(options = {}) {
    if (!multimodalMatrixStatusEl || !multimodalMatrixContentEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const dataDir = encodeURIComponent(scopeId);
    multimodalMatrixStatusEl.className = "query-status loading";
    multimodalMatrixStatusEl.textContent = "Building multimodal feature matrix...";
    renderNotice(multimodalMatrixContentEl,"Joining clinical, assay, and imaging metadata...");
    try {
      const response = await fetch(`/assays/matrix?data_dir=${dataDir}&max_features_per_dataset=3&max_rows=12`);
      if (!response.ok) throw new Error("Unable to build multimodal feature matrix.");
      const payload = await response.json();
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalMatrix(payload);
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalMatrixError(error && error.message ? error.message : "Unable to build multimodal feature matrix.");
    }
  }

  async function loadAssayFeatureSuggestions() {
    if (!analysisAssayGenesEl) return;
    const datasetNames = selectedTranscriptomicsAssayDatasetNames();
    if (!datasetNames.length) {
      renderOptions(analysisAssayGenesEl);
      return;
    }
    const query = encodeURIComponent(String(analysisAssayGeneEl && analysisAssayGeneEl.value ? analysisAssayGeneEl.value.trim() : ""));
    const scopeId = String((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()).trim();
    const dataDir = encodeURIComponent(scopeId);
    try {
      const payloads = await Promise.all(datasetNames.map(async (datasetName) => {
        const dataset = encodeURIComponent(datasetName);
        const response = await fetch(`/assays/features?data_dir=${dataDir}&assay_id=${dataset}&q=${query}&limit=50`);
        if (!response.ok) throw new Error("Unable to load assay features.");
        return response.json();
      }));
      const genes = Array.from(new Set(payloads.flatMap((payload) => Array.isArray(payload.genes) ? payload.genes : []))).sort();
      const annotations = payloads.reduce((acc, payload) => {
        const current = payload && payload.annotations && typeof payload.annotations === "object" ? payload.annotations : {};
        return { ...acc, ...current };
      }, {});
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderOptions(analysisAssayGenesEl, genes.map(geneId => {
        const annotation=annotations[geneId] || {}, symbol=String(annotation.gene_symbol || "").trim();
        return {value:geneId,labelAttribute:symbol ? `${symbol} · ${geneId}` : geneId,
          title:[geneId,symbol,String(annotation.gene_name || "").trim()].filter(Boolean).join(" • ")};
      }));
    } catch (_error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderOptions(analysisAssayGenesEl);
    }
  }

  async function loadAssayDatasets(options = {}) {
    if (!analysisAssayStatusEl || !assayDashboardStatusEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const previousScopeId = String(state.assayDatasetsScopeId || "").trim();
    const scopeChanged = previousScopeId !== scopeId;
    state.assayDatasetsScopeId = scopeId;
    void variantBrowser.load(scopeId);
    if (scopeChanged) {
      clearAssayWorkspaceSelection();
    }
    const dataDir = encodeURIComponent(scopeId);
    void loadDicomStudies({ scopeId });
    void loadMultimodalReadiness({ scopeId });
    void loadMultimodalMatrix({ scopeId });
    analysisAssayStatusEl.className = "query-status loading";
    analysisAssayStatusEl.textContent = "Checking transcriptomics assays...";
    if (analysisCatalogAssayStatusEl) {
      analysisCatalogAssayStatusEl.textContent = "Checking assays...";
    }
    assayDashboardStatusEl.className = "query-status loading";
    assayDashboardStatusEl.textContent = "Checking assays...";
    try {
      const payload = options.prefetched && typeof options.prefetched === "object"
        ? options.prefetched
        : await (async () => {
          const response = await fetch(`/assays?data_dir=${dataDir}`);
          if (!response.ok) throw new Error("Unable to load assay datasets.");
          return response.json();
        })();
      if (!isCurrentWorkspaceScope(scopeId)) return;
      const datasets = Array.isArray(payload.datasets) ? payload.datasets : [];
      state.assayDatasetsState = datasets;
      syncSelectedAssayDatasets();
      renderAssayDashboardCards(state.assayDatasetsState);
      if (typeof renderAnalysisCatalogAssayPanel === "function") {
        renderAnalysisCatalogAssayPanel();
      }
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
      if (!datasets.length) {
        analysisAssayStatusEl.className = "query-status";
        analysisAssayStatusEl.textContent = "No raw-count transcriptomics assays are currently available for quick expression checks.";
        if (analysisCatalogAssayStatusEl) {
          analysisCatalogAssayStatusEl.textContent = "No compatible assay datasets are currently available in this workspace.";
        }
        assayDashboardStatusEl.className = "query-status";
        assayDashboardStatusEl.textContent = "Assay inventory loaded.";
        renderAssayExpressionResult(null);
        return;
      }
      analysisAssayStatusEl.className = "query-status";
      const transcriptomicsCount = datasets.filter((dataset) => isQuickExpressionDataset(dataset)).length;
      analysisAssayStatusEl.textContent = transcriptomicsCount
        ? `Loaded ${transcriptomicsCount} raw-count transcriptomics assay${transcriptomicsCount === 1 ? "" : "s"} for quick expression checks.`
        : "No raw-count transcriptomics assays are currently available for quick expression checks.";
      if (analysisCatalogAssayStatusEl) {
        analysisCatalogAssayStatusEl.textContent = datasets.length === 1
          ? `1 assay dataset available for Analysis.`
          : `${datasets.length} assays available. Some assay tools require exactly one selected assay.`;
      }
      assayDashboardStatusEl.className = "query-status";
      assayDashboardStatusEl.textContent = "Assay inventory loaded.";
      await loadAssayFeatureSuggestions();
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = error && error.message ? error.message : "Unable to load transcriptomics assays.";
      if (analysisCatalogAssayStatusEl) {
        analysisCatalogAssayStatusEl.textContent = error && error.message ? error.message : "Unable to load assay datasets.";
      }
      assayDashboardStatusEl.className = "query-status";
      assayDashboardStatusEl.textContent = error && error.message ? error.message : "Unable to load assay datasets.";
      state.assayDatasetsState = [];
      clearAssayWorkspaceSelection();
      renderAssayDatasetSelector();
      renderAssayDashboardCards(state.assayDatasetsState);
      if (assayDashboardCardsEl) {
        assayCardsView.render({error:{title:'Assays unavailable', message:'Assay information could not be loaded. This does not mean the workspace has no assays. Apply workspace again in Datasets to retry.'}});
      }
      imagingCardsView.render({error:{title:'Imaging measurements unavailable', message:'The measurement inventory could not be loaded. Apply workspace again in Datasets to retry.'}});
      if (typeof renderAnalysisCatalogAssayPanel === "function") {
        renderAnalysisCatalogAssayPanel();
      }
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
    }
  }

  async function runAssayExpressionAnalysis() {
    if (!analysisAssayGeneEl || !analysisAssayStatusEl) return;
    const datasetNames = selectedTranscriptomicsAssayDatasetNames();
    const geneId = String(analysisAssayGeneEl.value || "").trim();
    if (!datasetNames.length || !geneId) {
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = "Choose at least one raw-count transcriptomics assay and a gene ID first.";
      return;
    }
    analysisAssayStatusEl.className = "query-status loading";
    analysisAssayStatusEl.textContent = "Fetching transcriptomics expression summary...";
    const scopeId = String((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()).trim();
    try {
      const selectedCohortA = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
        : null;
      const selectedCohortB = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
        : null;
      const payloads = await Promise.all(datasetNames.map(async (datasetName) => {
        const response = await fetch("/assays/expression", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
            assay_id: datasetName,
            gene_id: geneId,
            selected_patient_ids: selectedCohortA && Array.isArray(selectedCohortA.patient_ids)
              ? selectedCohortA.patient_ids.join(",")
              : analysisSelectedPatientIdsEl.value.trim(),
            compare_selected_patient_ids: analysisCompareModeEl && analysisCompareModeEl.checked
              ? (selectedCohortB && Array.isArray(selectedCohortB.patient_ids)
                ? selectedCohortB.patient_ids.join(",")
                : analysisCompareSelectedPatientIdsEl.value.trim())
              : "",
          }),
        });
        if (!response.ok) throw new Error("Unable to fetch transcriptomics expression.");
        return response.json();
      }));
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderAssayExpressionResult(payloads);
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = `Expression summary ready for ${geneId} across ${datasetNames.length} assay${datasetNames.length === 1 ? "" : "s"}.`;
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderAssayExpressionResult(null);
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = error && error.message ? error.message : "Unable to fetch transcriptomics expression.";
    }
  }

  function handleAssayDatasetSelectionChange(sourceEl = null, changedInput = null) {
    const listEl = sourceEl || analysisAssayDatasetListEl || analysisCatalogAssayDatasetListEl;
    if (!listEl) return;
    let selected = Array.from(listEl.querySelectorAll('input[type="checkbox"]:checked'))
      .map((item) => item.value)
      .filter(Boolean);
    const item = currentAnalysisCatalogItem();
    if (requiresSingleSelectedAssayDataset(item) && selected.length > 1) {
      const changedValue = changedInput && changedInput.checked ? String(changedInput.value || "").trim() : "";
      selected = changedValue ? [changedValue] : selected.slice(-1);
    }
    state.selectedAssayDatasets = selected;
    renderAssayDatasetSelector();
    syncCurrentAnalysisSessionFromUi({render: false});
    void loadAssayFeatureSuggestions();
  }

  function handleAssayFeatureInput() {
    void loadAssayFeatureSuggestions();
  }

  function closeClaridPopovers(except = null) {
    document.querySelectorAll(".clarid-identity.is-open").forEach((identity) => {
      if (identity === except) return;
      identity.classList.remove("is-open");
      const popover = identity.querySelector('.clarid-popover[popover]');
      if (popover?.matches(':popover-open')) popover.hidePopover();
      const toggle = identity.querySelector("[data-clarid-toggle]");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    });
  }

  async function handleClaridAction(event) {
    const copyButton = event.target.closest("[data-clarid-copy]");
    const toggle = event.target.closest("[data-clarid-toggle]");
    if (!copyButton && !toggle) return false;
    event.preventDefault();
    event.stopPropagation();
    if (toggle) {
      const identity = toggle.closest(".clarid-identity");
      const nextOpen = identity && !identity.classList.contains("is-open");
      closeClaridPopovers(nextOpen ? identity : null);
      const popover = identity?.querySelector('.clarid-popover');
      const floating = identity?.closest('.query-result-table, .patient-inventory') && popover?.showPopover;
      // Set floating layout before opening, so it never expands the table row.
      if (floating) popover.setAttribute('popover', 'manual');
      if (identity) identity.classList.toggle("is-open", Boolean(nextOpen));
      toggle.setAttribute("aria-expanded", nextOpen ? "true" : "false");
      if (nextOpen && floating) {
        // The top layer avoids both table reflow and clipping by its scroll box.
        popover.style.left = '12px';
        popover.style.top = '12px';
        popover.showPopover();
        const anchor = toggle.getBoundingClientRect();
        const bounds = popover.getBoundingClientRect();
        popover.style.left = `${Math.max(12, Math.min(anchor.left, window.innerWidth - bounds.width - 12))}px`;
        const below = anchor.bottom + 7;
        popover.style.top = `${Math.max(12, below + bounds.height <= window.innerHeight - 12
          ? below : anchor.top - bounds.height - 7)}px`;
      }
      return true;
    }
    const value = String(copyButton.dataset.claridCopy || "");
    let copied = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        copied = true;
      } else {
        copied = fallbackCopyText(value);
      }
    } catch (_error) {
      copied = false;
    }
    const original = copyButton.textContent;
    copyButton.textContent = copied ? "Copied" : "Unavailable";
    window.setTimeout(() => { copyButton.textContent = original; }, 1400);
    return true;
  }

  return {
    renderPatientList,
    renderDetail,
    renderDashboard,
    renderDashboardTimeline,
    resetDashboardViews:() => { clinicalView.reset(); resetTimelineView(); resetInspectorView(); },
    resetPatientInspectorView:resetInspectorView,
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
    renderAssayDatasetSelector,
    renderAssayExpressionResult,
    renderAssayDashboardCards,
    handleAssayModalityFilter,
    renderDicomStudies,
    clearDatasetWorkspaceViews,
    loadDicomStudies,
    loadAssayDatasets,
    runAssayExpressionAnalysis,
    handleAssayDatasetSelectionChange,
    handleAssayFeatureInput,
    assayDatasetOverlap,
    handleClaridAction,
    closeClaridPopovers,
  };
}
