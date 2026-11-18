import {createPhenoOrdinationChart} from './charts/pheno-ordination.js';
import {createPhenoHeatmapChart} from './charts/pheno-heatmap.js';
import {createPhenoNetworkChart} from './charts/pheno-network.js';
import {renderOptions,renderNotice,renderPhenoReadinessView,renderPhenoFiles,renderPhenoLegend,renderPhenoRunning} from './react/ui.js';
import {activityState} from './shared.js';
import {createProvenanceView,createPlanPreviewView, createPhenoResultView, createPhenoAlignmentView, createPhenoExplanationView, createPhenoPlanningView, createPhenoFollowupsView} from './react/ui.js';
import { displayIdentity } from "./identities.js";
import { createPhenoPatientPicker } from './pheno_patient_picker.js';

export const PHENO_HEATMAP_MAX_RECORDS = 1000;

export function phenoHeatmapRecordCount(text) {
  const lines = String(text).split(/\r?\n/).filter(line => line.trim());
  if (!lines.length) return 0;
  return Math.max(lines.length - 1, lines[0].split('\t').length - 1);
}

export function createPhenoUi(ctx) {
  const {
    refs,
    constants,
    helpers,
    callbacks,
  } = ctx;

  const {
    dataDirEl,
    phenoActionEl,
    phenoModeEl,
    phenoPromptEl,
    phenoPlanBtnEl,
    phenoPlanRunBtnEl,
    phenoPlanStatusEl,
    phenoPlanMetaEl,
    phenoPlanDetailsEl,
    phenoPlanEl,
    phenoPlanReasoningEl,
    phenoPlanFollowupsEl,
    phenoReferenceFilesSummaryEl,
    phenoBackgroundJobBannerEl,
    phenoSetupDetailsEl,
    phenoPatientFieldEl,
    phenoPatientIdEl,
    phenoSelectedPatientIdsEl,
    phenoSelectedPatientIdsSummaryEl,
    phenoIncludeTermsEl,
    phenoExcludeTermsEl,
    phenoSimilarityMetricEl,
    phenoSortByEl,
    phenoMaxOutFieldEl,
    phenoMaxOutEl,
    phenoAlignChecksEl,
    phenoAlignEl,
    phenoRenderHeatmapEl,
    phenoRenderMdsEl,
    phenoRenderGraphEl,
    phenoGraphOptionsEl,
    phenoGraphMinWeightEl,
    phenoGraphMaxWeightEl,
    phenoPlotChecksEl,
    phenoRunBtnEl,
    phenoExplainBtnEl,
    phenoExplainLlmBtnEl,
    phenoAnalysisBtnEl,
    phenoCopyIdsBtnEl,
    phenoStatusEl,
    phenoExplainCardEl,
    phenoAlignmentCardEl,
    phenoExplainDetailEl,
    phenoCommandEl,
    phenoFilesEl,
    phenoResultEmptyStateEl,
    phenoResultWorkspaceEl,
    phenoOutputDetailsEl,
    phenoOutputPreviewEl,
    phenoAlignmentDetailEl,
    phenoLogsEl,
    phenoPreviewsEl,
    analysisSelectedPatientIdsEl,
    analysisPromptEl,
    analysisStatusEl,
  } = refs;

  const filesView=createPhenoResultView(phenoFilesEl);
  const metaView=createProvenanceView(phenoPlanMetaEl);
  const planPreviewView=createPlanPreviewView(phenoPlanEl);
  const planningView=createPhenoPlanningView(phenoPlanReasoningEl);
  const planFollowupsView=createPhenoFollowupsView(phenoPlanFollowupsEl);
  const explanationView=createPhenoExplanationView(phenoExplainDetailEl);
  const alignmentView=createPhenoAlignmentView(phenoAlignmentDetailEl,getPhenoBucketStyle,normalizePhenoBucketName);
  const outputView=createPhenoResultView(phenoOutputPreviewEl);
  const previewsView=createPhenoResultView(phenoPreviewsEl);
  const { PHENO_BUCKET_STYLES, PHENO_COHORT_COLORS } = constants;
  const { escapeHtml, fallbackCopyText, nextFrame } = helpers;
  const {
    setActiveTab,
    renderGlobalContext,
    renderAnalysisScopeSummary,
    syncCurrentAnalysisSessionFromUi,
    startPhenoPlanProgressUpdates,
    stopPhenoPlanProgressUpdates,
    startPhenoRunProgressUpdates,
    stopPhenoRunProgressUpdates,
    handlePhenoJobSubmission,
    handlePhenoJobCompletion,
    saveIdsAsCohort,
    setAnalysisScopeMetadataFromSelection,
    getSelectedSavedCohortIds,
    setSelectedSavedCohortIds,
    getCurrentScopeIds,
    onPatientIdsLoaded,
    onReferenceFilesLoaded,
  } = callbacks;

  const state = {
    inFlight: false,
    planInFlight: false,
    explainInFlight: false,
    explainLlmInFlight: false,
    tableState: null,
    runState: null,
    selectedAlignmentKey: "",
    selectedMdsRecordIds: [],
    selectedUmapRecordIds: [],
    projectionPatientIds: new Map(),
    selectedHeatmapRecordIds: [],
    selectedGraphRecordIds: [],
    manualOverrides: false,
    plannedPrompt: '',
    isApplyingPlan: false,
    rankerPatientIds: [],
    rankerRecordIds: [],
    referenceFiles: [],
    workspaceVersion: 0,
  };

  const patientPicker = createPhenoPatientPicker(phenoPatientIdEl, document.getElementById('phenoPatientChoices'));

  const {renderInteractivePhenoMdsPlot} = createPhenoOrdinationChart({parseTsvLines, getPhenoMdsCohortInfo, renderPhenoCohortLegend, state, normalizePhenoSelectedRecordId, displayIdentity, normalizePhenoSelectedRecordIds, escapeHtml});
  const {renderInteractivePhenoHeatmap} = createPhenoHeatmapChart({phenoHeatmapRecordCount, PHENO_HEATMAP_MAX_RECORDS, parseTsvLines, getEffectivePhenoCohortMetric, escapeHtml, displayIdentity});
  const {renderInteractivePhenoGraph} = createPhenoNetworkChart({renderPhenoCohortLegend, getEffectivePhenoCohortMetric, getPhenoMdsCohortInfo, displayIdentity, state, normalizePhenoSelectedRecordIds, escapeHtml});
  function currentActivePhenoBackgroundJob() {
    return Array.isArray(state.recentJobs)
      ? state.recentJobs.find((item) => item && item.feature === "pheno" && ["queued", "running"].includes(String(item.status || "").trim()))
      : null;
  }

  function currentCompletedPhenoJobForWorkspace() {
    const workspaceId = String((dataDirEl && dataDirEl.dataset && dataDirEl.dataset.scopeId) || (dataDirEl && dataDirEl.value) || "").trim();
    if (!workspaceId || !Array.isArray(state.recentJobs)) {
      return null;
    }
    return state.recentJobs.find((item) => {
      if (!item || item.feature !== "pheno") return false;
      if (String(item.status || "").trim() !== "completed") return false;
      return String(item.dataset_id || "").trim() === workspaceId;
    }) || null;
  }

  function renderPhenoBackgroundJobBanner() {
    if (!phenoBackgroundJobBannerEl) {
      return;
    }
    const active = currentActivePhenoBackgroundJob();
    if (active || state.inFlight) {
      const queued = active?.status === "queued";
      const label = String(active?.job_code || active?.job_id || "").trim();
      phenoBackgroundJobBannerEl.classList.remove("is-hidden");
      phenoBackgroundJobBannerEl.dataset.stage = queued ? "queued" : "running";
      renderPhenoRunning(phenoBackgroundJobBannerEl,{queued,label,active:Boolean(active)});
      return;
    }
    const completed = currentCompletedPhenoJobForWorkspace();
    if (completed) {
      const label = String(completed.job_code || completed.job_id || "").trim();
      phenoBackgroundJobBannerEl.classList.remove("is-hidden");
      phenoBackgroundJobBannerEl.dataset.stage = "completed";
      renderNotice(phenoBackgroundJobBannerEl, label
        ? `Background Pheno-Ranker run completed: ${label}.`
        : "A background Pheno-Ranker run completed.");
      return;
    }
    phenoBackgroundJobBannerEl.classList.add("is-hidden");
    renderNotice(phenoBackgroundJobBannerEl, "");
  }
  phenoBackgroundJobBannerEl?.addEventListener("click", event => {
    if (event.target.closest("[data-pheno-view-job]")) callbacks.openPhenoJobs?.();
  });

  function seedQueuedPhenoBackgroundJob(payload) {
    const source = payload && typeof payload === "object" ? payload : {};
    const data = source && typeof source.data === "object" ? source.data : {};
    const jobId = String(data.job_id || source.job_id || "").trim();
    if (!jobId) {
      return;
    }
    const workspaceId = String(
      source.dataset_id
      || ((dataDirEl && dataDirEl.dataset && dataDirEl.dataset.scopeId) || (dataDirEl && dataDirEl.value) || "")
    ).trim();
    const seededJob = {
      job_id: jobId,
      job_code: String(data.job_code || source.job_code || "").trim(),
      status: String(data.job_status || source.status || "queued").trim() || "queued",
      feature: "pheno",
      name: "Pheno-Ranker cohort run",
      prompt: phenoPromptEl && phenoPromptEl.value ? phenoPromptEl.value.trim() : "",
      dataset_id: workspaceId,
      result_available: false,
      submitted_at: new Date().toISOString(),
      reply_preview: String(source.reply || "").trim(),
    };
    state.recentJobs = [
      seededJob,
      ...(Array.isArray(state.recentJobs) ? state.recentJobs : []).filter((item) => {
        const itemId = String(item && item.job_id ? item.job_id : "").trim();
        if (itemId && itemId === jobId) {
          return false;
        }
        return !(item && item.feature === "pheno" && ["queued", "running"].includes(String(item.status || "").trim()));
      }),
    ];
  }

  function renderProvenanceBadge(label,title='',iconKind='') { return {label,title,iconKind}; }

  function updatePhenoMode() {
    const patientMode = phenoModeEl.value === "patient";
    document.querySelectorAll('[data-pheno-mode]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.phenoMode === phenoModeEl.value));
    });
    const extractMode = phenoActionEl.value === "extract";
    const cohortMode = !patientMode && !extractMode;
    phenoPatientFieldEl.classList.toggle("is-hidden", !patientMode || extractMode);
    phenoMaxOutFieldEl.classList.toggle("is-hidden", !patientMode || extractMode);
    phenoAlignChecksEl.classList.toggle("is-hidden", !patientMode || extractMode);
    phenoPlotChecksEl.classList.toggle("is-hidden", patientMode || extractMode);
    updatePhenoGraphOptions();
    if (cohortMode && phenoRenderMdsEl) {
      phenoRenderMdsEl.checked = true;
    }
  }

  document.querySelectorAll('[data-pheno-mode]').forEach(button => {
    button.addEventListener('click', () => {
      phenoModeEl.value = button.dataset.phenoMode;
      phenoActionEl.value = 'compare';
      phenoModeEl.dispatchEvent(new Event('change', { bubbles: true }));
      phenoModeEl.dispatchEvent(new Event('input', { bubbles: true }));
      if (phenoModeEl.value === 'patient') phenoPatientIdEl.focus();
    });
  });

  function updatePhenoGraphOptions() {
    if (!phenoGraphOptionsEl) {
      return;
    }
    const show = Boolean(phenoModeEl.value === "cohort" && phenoActionEl.value !== "extract" && phenoRenderGraphEl && phenoRenderGraphEl.checked);
    phenoGraphOptionsEl.classList.toggle("is-hidden", !show);
    const metric = normalizePhenoMetricValue(phenoSimilarityMetricEl && phenoSimilarityMetricEl.value ? phenoSimilarityMetricEl.value : "");
    if (phenoGraphMinWeightEl) {
      phenoGraphMinWeightEl.placeholder = metric === "jaccard" ? "e.g. 0.25" : "optional";
      phenoGraphMinWeightEl.title = metric === "jaccard"
        ? "For Jaccard graphs, minimum weight keeps edges at or above this similarity."
        : "Optional lower bound passed to Pheno-Ranker.";
    }
    if (phenoGraphMaxWeightEl) {
      phenoGraphMaxWeightEl.placeholder = metric === "hamming" ? "e.g. 2" : "optional";
      phenoGraphMaxWeightEl.title = metric === "hamming"
        ? "For Hamming graphs, maximum weight keeps edges at or below this distance."
        : "Optional upper bound passed to Pheno-Ranker.";
    }
  }

  function normalizePhenoMetricValue(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return ["hamming", "jaccard"].includes(normalized) ? normalized : "";
  }

  function parseOptionalNumberInput(inputEl) {
    if (!inputEl) {
      return null;
    }
    const value = String(inputEl.value || "").trim();
    if (!value) {
      return null;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function hasPhenoGraphCutoffInput() {
    return Boolean(
      (phenoGraphMinWeightEl && String(phenoGraphMinWeightEl.value || "").trim())
      || (phenoGraphMaxWeightEl && String(phenoGraphMaxWeightEl.value || "").trim())
    );
  }

  function renderPhenoPlanReasoning(items,plan=null) {
    planningView.render({lines:Array.isArray(items) ? items.filter(Boolean) : [],plan});
  }

  function renderPlanningProgress() {
    planningView.render({activity:activityState("Planner reasoning", "Waiting for the interpreted plan and supporting rationale.")});
  }

  function renderPhenoPlanFollowUps(source=null) {
    const payload=source && typeof source==='object' ? source : {};
    const suggestions=Array.isArray(payload.follow_up_suggestions) ? [...new Set(payload.follow_up_suggestions.map(item=>String(item || '').trim()).filter(Boolean))].slice(0,4) : [];
    const data=payload.data || {}, planner=data.planner || {};
    const llmPlanned=['llm','lm_studio'].includes(String(payload.source || '').trim().toLowerCase()) || String(data.source || '').trim().toLowerCase()==='llm' || String(planner.provider || '').trim().toLowerCase()==='lm_studio';
    planFollowupsView.render({suggestions,llmPlanned});
  }

  function handlePhenoPlanFollowUpsClick(event) {
    const button = event.target.closest("[data-pheno-followup-prompt]");
    if (!button || !phenoPlanFollowupsEl || !phenoPlanFollowupsEl.contains(button)) {
      return;
    }
    const prompt = String(button.dataset.phenoFollowupPrompt || "").trim();
    if (!prompt) {
      return;
    }
    const mode = String(button.dataset.followupExecutionMode || "deterministic");
    phenoPromptEl.value = prompt;
    handlePhenoPromptEdited();
    if (phenoPlanStatusEl && phenoPlanStatusEl.dataset.backgroundBlocked !== "true") {
      phenoPlanStatusEl.textContent = mode === "llm_planned"
        ? "LLM-planned follow-up prepared. Preview or run it to confirm the actual planning path."
        : "Deterministic follow-up prepared. Preview the plan or run it when ready.";
    }
    phenoPromptEl.focus();
  }

  function getPhenoPlanBlockingIssues(plan) {
    const normalized = plan || {};
    const action = String(normalized.action || "compare");
    const mode = String(normalized.mode || "cohort");
    const patientId = String(normalized.patient_id || "").trim();
    const invalidPatientId = String(normalized.invalid_patient_id || "").trim();
    const scopeIds = typeof normalized.selected_patient_ids === "string"
      ? normalized.selected_patient_ids.split(",").map((item) => item.trim()).filter(Boolean)
      : (Array.isArray(normalized.selected_patient_ids) ? normalized.selected_patient_ids.map((item) => String(item || "").trim()).filter(Boolean) : []);
    const issues = [];

    if (action === "extract" && !scopeIds.length && !normalized.query_result_handle) {
      issues.push("Extraction needs a non-empty Scope before it can run.");
    }

    if (mode === "patient") {
      if (normalized.query_result_handle) {
        issues.push('Use Cohort mode for this Query selection, or replace it with manual IDs.');
      }
      if (invalidPatientId) {
        issues.push(`Patient ID ${invalidPatientId} does not exist in the current Pheno-Ranker reference dataset.`);
      }
      if (!patientId && scopeIds.length !== 1) {
        issues.push("Choose a patient or visit in the Patient ID field to find its closest matches.");
      }
      const availableIds = [...state.rankerRecordIds, ...state.rankerPatientIds];
      if (patientId && availableIds.length && !availableIds.includes(patientId) && !invalidPatientId) {
        issues.push('Choose a patient or visit from the available suggestions. This ID is not in the loaded reference data.');
      }
      if (!patientId && scopeIds.length === 1) {
        issues.push(`Patient mode will use ${scopeIds[0]} as the target patient.`);
      }
      if (scopeIds.length > 1) {
        issues.push("Patient mode cannot run with multiple IDs in Scope.");
      }
    }

    return issues;
  }

  function renderPhenoPlanState(plan, reasoning) {
    const issues = getPhenoPlanBlockingIssues(plan);
    phenoPlanStatusEl.classList.remove("warning");
    phenoPlanEl.classList.remove("is-blocking");
    phenoPlanReasoningEl.classList.remove("is-blocking");

    if (!issues.length) {
      return;
    }

    phenoPlanStatusEl.classList.add("warning");
    phenoPlanEl.classList.add("is-blocking");
    phenoPlanReasoningEl.classList.add("is-blocking");

    planningView.warn({title:"Planner output is not runnable yet.",issues},!(Array.isArray(reasoning) && reasoning.length));
  }

  function renderPhenoPlanMeta(source) {
    const data = source && typeof source === "object" ? (source.data || {}) : {};
    const rawSource = source && typeof source === "object" ? String(source.source || "") : String(source || "");
    const planner = data.planner && typeof data.planner === "object" ? data.planner : null;
    const aiProviderConsulted = (
      (data.execution === "planning" && planner && planner.provider === "lm_studio")
      || data.provider === "lm_studio"
      || rawSource === "lm_studio"
    );
    if (!rawSource && !planner) {
      metaView.render([]);
      return;
    }
    const chips = [];
    const formatAiProviderGranularity = (value) => {
      const label = String(value || "").replace(/_/g, " ");
      return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : "";
    };
    if (aiProviderConsulted && data.ai_provider_context_granularity && data.ai_provider_access) {
      let title = "";
      if (data.ai_provider_access === "blocked") {
        title = "AI providers are blocked for this dataset or workspace.";
      } else if (data.ai_provider_access === "safe_summary") {
        title = "AI providers may be used, but they only receive provider-safe structural summary context.";
      } else {
        title = `AI providers may receive up to detailed context and currently receive ${formatAiProviderGranularity(data.ai_provider_context_granularity)} context for Pheno-Ranker planning.`;
      }
      chips.push(renderProvenanceBadge(`Model context: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}`, title, "provider"));
    }
    if (planner && planner.provider === "lm_studio") {
      chips.push(renderProvenanceBadge("LLM-planned", "LM Studio translated the prompt into a Pheno-Ranker execution plan.", "planner"));
      if (planner.model) {
        chips.push(renderProvenanceBadge(String(planner.model), "LM Studio model used for Pheno-Ranker planning.", "llm"));
      }
    } else {
      const isLm = rawSource === "lm_studio";
      const label = isLm ? "LLM-planned" : "Deterministic";
      const title = isLm
        ? "LM Studio translated the prompt into a Pheno-Ranker execution plan."
        : "The app derived the Pheno-Ranker plan using deterministic prompt parsing.";
      chips.push(renderProvenanceBadge(label, title, isLm ? "planner" : "deterministic"));
    }
    metaView.render(chips);
  }

  function setPhenoResultWorkspaceVisible(visible) {
    if (phenoResultEmptyStateEl) {
      phenoResultEmptyStateEl.classList.toggle("is-hidden", Boolean(visible));
    }
    if (phenoResultWorkspaceEl) {
      phenoResultWorkspaceEl.classList.toggle("is-hidden", !visible);
    }
  }

  function updatePhenoExplainActions() {
    const isPatientMode = Boolean(state.runState && state.runState.jobId && state.runState.mode === "patient");
    const canExplain = isPatientMode;
    if (phenoExplainCardEl) {
      phenoExplainCardEl.classList.toggle("is-hidden", !canExplain);
    }
    if (phenoAlignmentCardEl) {
      phenoAlignmentCardEl.classList.toggle("is-hidden", !isPatientMode);
    }
    if (phenoExplainBtnEl) {
      phenoExplainBtnEl.disabled = !canExplain || state.explainInFlight || state.explainLlmInFlight;
      phenoExplainBtnEl.title = canExplain ? "" : "Available after a patient-mode run.";
    }
    if (phenoExplainLlmBtnEl) {
      phenoExplainLlmBtnEl.disabled = !canExplain || state.explainInFlight || state.explainLlmInFlight;
      phenoExplainLlmBtnEl.title = canExplain ? "" : "Available after a patient-mode run.";
    }
  }

  function currentPhenoSettingsPlan() {
    const selectedSavedCohortIds = typeof getSelectedSavedCohortIds === "function" ? getSelectedSavedCohortIds() : [];
    const graphMinWeight = parseOptionalNumberInput(phenoGraphMinWeightEl);
    const graphMaxWeight = parseOptionalNumberInput(phenoGraphMaxWeightEl);
    const plan = {
      action: phenoActionEl ? phenoActionEl.value : "compare",
      mode: phenoModeEl ? phenoModeEl.value : "cohort",
      patient_id: patientPicker.get(),
      selected_patient_ids: selectedSavedCohortIds.length ? "" : (phenoSelectedPatientIdsEl ? phenoSelectedPatientIdsEl.value.trim() : ""),
      selected_saved_cohort_ids: selectedSavedCohortIds,
      query_result_handle: selectedSavedCohortIds.length ? '' : ctx.state?.phenoQuerySelection?.handle || '',
      query_selection: selectedSavedCohortIds.length ? null : ctx.state?.phenoQuerySelection || null,
      include_terms: parsePhenoTermsInput(phenoIncludeTermsEl ? phenoIncludeTermsEl.value : ""),
      exclude_terms: parsePhenoTermsInput(phenoExcludeTermsEl ? phenoExcludeTermsEl.value : ""),
      similarity_metric_cohort: phenoSimilarityMetricEl ? phenoSimilarityMetricEl.value : "",
      sort_by: phenoSortByEl ? phenoSortByEl.value : "",
      max_out: Number(phenoMaxOutEl && phenoMaxOutEl.value ? phenoMaxOutEl.value : 10),
      align: Boolean(phenoAlignEl && phenoAlignEl.checked),
      render_heatmap: Boolean(phenoRenderHeatmapEl && phenoRenderHeatmapEl.checked),
      render_mds: Boolean(phenoRenderMdsEl && phenoRenderMdsEl.checked),
      render_graph: Boolean(phenoRenderGraphEl && phenoRenderGraphEl.checked),
    };
    if (graphMinWeight !== null) {
      plan.graph_min_weight = graphMinWeight;
    }
    if (graphMaxWeight !== null) {
      plan.graph_max_weight = graphMaxWeight;
    }
    return plan;
  }

  function describePhenoPlanAsPrompt(plan) {
    const normalized = plan && typeof plan === "object" ? plan : {};
    const action = String(normalized.action || "compare");
    const mode = String(normalized.mode || "cohort");
    const parts = [];
    if (action === "extract") {
      const scope = String(normalized.selected_patient_ids || "").trim();
      parts.push(scope ? `Extract Pheno-Ranker records for ${scope}.` : "Extract the selected Pheno-Ranker records.");
    } else if (mode === "patient") {
      const target = String(normalized.patient_id || "").trim();
      parts.push(target ? `Compare patient ${target} to the active workspace.` : "Compare one patient to the active workspace.");
    } else {
      parts.push("Compare the active Pheno-Ranker cohort.");
    }
    const includeTerms = Array.isArray(normalized.include_terms) ? normalized.include_terms.filter(Boolean) : [];
    const excludeTerms = Array.isArray(normalized.exclude_terms) ? normalized.exclude_terms.filter(Boolean) : [];
    if (includeTerms.length) {
      parts.push(`Include ${includeTerms.join(", ")}.`);
    }
    if (excludeTerms.length) {
      parts.push(`Exclude ${excludeTerms.join(", ")}.`);
    }
    const metric = String(normalized.similarity_metric_cohort || "").trim();
    if (mode === "cohort" && metric) {
      parts.push(`Use ${metric} cohort similarity.`);
    }
    const outputs = [];
    if (normalized.render_heatmap) outputs.push("heatmap");
    if (normalized.render_mds) outputs.push("MDS");
    if (normalized.render_graph) outputs.push("graph");
    if (outputs.length) {
      parts.push(`Render ${outputs.join(", ")}.`);
    }
    if (normalized.graph_min_weight !== undefined) {
      parts.push(`Graph min edge weight ${normalized.graph_min_weight}.`);
    }
    if (normalized.graph_max_weight !== undefined) {
      parts.push(`Graph max edge weight ${normalized.graph_max_weight}.`);
    }
    return parts.join(" ");
  }

  function syncPromptToCurrentPhenoPlan(plan) {
    if (!phenoPromptEl) {
      return;
    }
    const description = describePhenoPlanAsPrompt(plan);
    if (description) {
      phenoPromptEl.value = description;
      updatePhenoRunAvailability();
    }
  }

  function renderPhenoManualSettingsPreview(statusText = "") {
    if (!phenoPlanEl || !phenoPlanReasoningEl || !phenoPlanStatusEl) {
      return null;
    }
    const plan = currentPhenoSettingsPlan();
    syncPromptToCurrentPhenoPlan(plan);
    phenoPlanEl.classList.remove("is-blocking");
    phenoPlanReasoningEl.classList.remove("is-blocking");
    planPreviewView.render({text:JSON.stringify(compactPhenoPlan(plan), null, 2)});
    renderPhenoPlanReasoning(
      ["These settings were edited after the last preview. Run Pheno-Ranker will use this current form state."],
      plan,
    );
    if (phenoPlanStatusEl.dataset.backgroundBlocked !== "true") {
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = statusText || getPhenoPlanBlockingIssues(plan).join(' ') || "Ready to run with the selected settings.";
    }
    renderPhenoPlanMeta("");
    renderPhenoPlanFollowUps();
    return {
      source: "manual",
      reasoning: ["Using current form settings."],
      plan,
    };
  }

  function markPhenoManualOverride() {
    if (state.isApplyingPlan) {
      return;
    }
    state.manualOverrides = true;
    renderPhenoManualSettingsPreview();
  }

  function setPhenoManualOverrides(nextValue) {
    state.manualOverrides = Boolean(nextValue);
  }

  function handlePhenoPromptEdited() {
    state.manualOverrides = false;
    state.plannedPrompt = '';
    if (phenoPlanEl) {
      phenoPlanEl.classList.remove("is-blocking");
      planPreviewView.render({text:"Prompt changed. Preview plan to see the interpreted settings."});
    }
    if (phenoPlanReasoningEl) {
      phenoPlanReasoningEl.classList.remove("is-blocking");
      renderPhenoPlanReasoning(["The prompt was edited after the last preview. The next preview or run will re-interpret this prompt."], null);
    }
    if (phenoPlanStatusEl && phenoPlanStatusEl.dataset.backgroundBlocked !== "true") {
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = "Prompt changed. Preview plan or run Pheno-Ranker to interpret the new prompt.";
    }
    renderPhenoPlanMeta("");
    renderPhenoPlanFollowUps();
    updatePhenoRunAvailability();
  }

  function getPhenoTopMatchRecordIds(limit = 10) {
    if (!state.tableState || state.tableState.sourceName !== "rank.txt") {
      return [];
    }
    const rows = Array.isArray(state.tableState.rows) ? state.tableState.rows : [];
    const index = Number.isInteger(state.tableState.referenceColumnIndex) ? state.tableState.referenceColumnIndex : -1;
    if (index < 0) {
      return [];
    }
    const ids = [];
    for (const row of rows) {
      const recordId = String((Array.isArray(row) ? row[index] : "") || "").trim();
      if (!recordId || ids.includes(recordId)) {
        continue;
      }
      ids.push(recordId);
      if (ids.length >= limit) {
        break;
      }
    }
    return ids;
  }

  function collapsePhenoRecordIdsToPatientIds(recordIds) {
    const patientIds = [];
    for (const value of Array.isArray(recordIds) ? recordIds : []) {
      const recordId = String(value || "").trim();
      if (!recordId) {
        continue;
      }
      const patientId = state.projectionPatientIds.get(recordId)
        || (recordId.includes(":") ? recordId.split(":")[0] : recordId);
      if (patientId && !patientIds.includes(patientId)) {
        patientIds.push(patientId);
      }
    }
    return patientIds;
  }

  function updatePhenoResultActions() {
    const hasMatches = Boolean(getPhenoTopMatchRecordIds().length && state.runState && state.runState.mode === "patient");
    if (phenoAnalysisBtnEl) {
      phenoAnalysisBtnEl.disabled = !hasMatches;
      phenoAnalysisBtnEl.title = hasMatches ? "" : "Available after a patient-mode rank.txt result is loaded.";
    }
    if (phenoCopyIdsBtnEl) {
      phenoCopyIdsBtnEl.disabled = !hasMatches;
      phenoCopyIdsBtnEl.title = hasMatches ? "" : "Available after a patient-mode rank.txt result is loaded.";
    }
  }


  function updatePhenoRunAvailability() {
    if (!phenoRunBtnEl || !phenoPromptEl) {
      return;
    }
    renderPhenoBackgroundJobBanner();
    const hasPrompt = Boolean(phenoPromptEl.value.trim());
    const activeBackgroundJob = currentActivePhenoBackgroundJob();
    const activeLabel = activeBackgroundJob ? String(activeBackgroundJob.job_code || activeBackgroundJob.job_id || "").trim() : "";
    const plan = currentPhenoSettingsPlan();
    const issues = getPhenoPlanBlockingIssues(plan);
    const formBlocked = issues.length > 0;
    const shouldDisable = state.inFlight || state.planInFlight || ((!hasPrompt || state.manualOverrides) && formBlocked) || Boolean(activeBackgroundJob);
    phenoRunBtnEl.disabled = shouldDisable;
    const runLabel = phenoRunBtnEl.querySelector("span:last-child");
    if (runLabel) runLabel.textContent = activeBackgroundJob
      ? (activeBackgroundJob.status === "queued" ? "Queued…" : "Running…")
      : state.inFlight ? "Running…" : state.planInFlight ? "Interpreting…" : "Run Pheno-Ranker";
    phenoRunBtnEl.setAttribute("aria-busy", String(Boolean(state.inFlight || activeBackgroundJob)));
    phenoRunBtnEl.classList.toggle("is-background-blocked", Boolean(activeBackgroundJob));
    phenoRunBtnEl.title = activeBackgroundJob
      ? "A background Pheno-Ranker run is already in progress."
      : (formBlocked ? issues.join(' ') : 'Run with the selected settings.');
    renderPhenoReadiness(plan, issues, activeBackgroundJob);
    if (phenoPlanRunBtnEl) {
      phenoPlanRunBtnEl.disabled = Boolean(activeBackgroundJob) || state.planInFlight || state.inFlight;
      phenoPlanRunBtnEl.classList.toggle("is-background-blocked", Boolean(activeBackgroundJob));
      phenoPlanRunBtnEl.title = activeBackgroundJob ? "A background Pheno-Ranker run is already in progress." : "";
    }
    if (phenoPlanStatusEl) {
      if (activeBackgroundJob) {
        phenoPlanStatusEl.className = "pheno-status warning";
        phenoPlanStatusEl.dataset.backgroundBlocked = "true";
        phenoPlanStatusEl.textContent = activeLabel
          ? `Background Pheno-Ranker run ${activeLabel} is in progress. New runs are locked until it finishes.`
          : "A background Pheno-Ranker run is in progress. New runs are locked until it finishes.";
      } else if (phenoPlanStatusEl.dataset.backgroundBlocked === "true") {
        delete phenoPlanStatusEl.dataset.backgroundBlocked;
        phenoPlanStatusEl.className = "pheno-status";
        phenoPlanStatusEl.textContent = hasPrompt
          ? "Preview the interpreted plan or run Pheno-Ranker for the current scope."
          : "Describe a run in natural language. The run applies to the current scope shown above.";
      }
    }
  }

  function renderPhenoReadiness(plan, issues, activeJob) {
    const el = document.getElementById('phenoReadiness');
    if (!el) return;
    const prompt = phenoPromptEl.value.trim();
    const needsPlan = prompt && !state.manualOverrides && prompt !== state.plannedPrompt;
    const workspace = String(dataDirEl.dataset.scopeId || dataDirEl.value || '').trim();
    const hasReferences = state.rankerRecordIds.length > 0 || state.rankerPatientIds.length > 0;
    const title = state.inFlight ? 'Running…' : state.planInFlight ? 'Interpreting request…'
      : activeJob ? 'Background run in progress' : !workspace ? 'Load a workspace'
      : !hasReferences ? 'Reference records are not available yet'
      : needsPlan ? 'Request will be interpreted before running' : issues.length ? issues[0] : 'Ready to run';
    const cohorts = plan.selected_saved_cohort_ids || [];
    const scopeIds = String(plan.selected_patient_ids || '').split(',').filter(Boolean);
    const reference = cohorts.length ? `${cohorts.length} saved cohort${cohorts.length === 1 ? '' : 's'}`
      : plan.query_selection?.handle ? `${plan.query_selection.count} ${plan.query_selection.idType === 'sample' ? 'samples' : 'patients'} from Query`
      : plan.mode !== 'patient' && scopeIds.length ? `${scopeIds.length} selected IDs` : 'Full workspace';
    const parts = [plan.action === 'extract' ? 'Extract records' : plan.mode === 'patient' ? 'Patient ranking' : 'Cohort comparison'];
    if (plan.mode === 'patient') parts.push(`Target: ${plan.patient_id || scopeIds[0] || 'not selected'}`);
    parts.push(`${plan.mode === 'patient' ? 'Reference' : 'Data'}: ${reference}`);
    parts.push(`Terms: ${plan.include_terms.length ? plan.include_terms.join(', ') : 'all supported terms'}`);
    if (plan.exclude_terms.length) parts.push(`Excluded: ${plan.exclude_terms.join(', ')}`);
    el.classList.toggle('is-ready', Boolean(workspace && hasReferences && !needsPlan && !issues.length && !activeJob && !state.inFlight && !state.planInFlight));
    renderPhenoReadinessView(el,title,parts);
  }

  function getPhenoPlotSelection(kind) {
    if (kind === "umap") return state.selectedUmapRecordIds;
    if (kind === "heatmap") {
      return state.selectedHeatmapRecordIds;
    }
    if (kind === "graph") {
      return state.selectedGraphRecordIds;
    }
    return state.selectedMdsRecordIds;
  }

  function normalizePhenoSelectedRecordId(recordId) {
    const rawId = String(recordId || "").trim();
    if (!rawId) {
      return "";
    }
    const match = rawId.match(/^C\d+_(.+)$/);
    return match ? match[1].trim() : rawId;
  }

  function normalizePhenoSelectedRecordIds(recordIds) {
    return (Array.isArray(recordIds) ? recordIds : [])
      .map((recordId) => normalizePhenoSelectedRecordId(recordId))
      .filter((value, index, all) => value && all.indexOf(value) === index);
  }

  function resetPhenoRunWorkspace() {
    state.runState = null;
    state.selectedAlignmentKey = "";
    state.selectedMdsRecordIds = [];
    state.selectedUmapRecordIds = [];
    state.projectionPatientIds.clear();
    state.selectedHeatmapRecordIds = [];
    state.selectedGraphRecordIds = [];
    state.tableState = null;
    state.explainInFlight = false;
    state.explainLlmInFlight = false;
    updatePhenoExplainActions();
    updatePhenoResultActions();
    setPhenoResultWorkspaceVisible(false);
    phenoCommandEl.textContent = "No run yet.";
    filesView.render({message:"No output files yet."});
    outputView.render({message:"No output preview yet."});
    renderPhenoAlignmentPlaceholder("Run patient mode, then click one row in rank.txt to inspect matched variables for that pair.");
    renderPhenoExplainPlaceholder("Run patient mode, then click Explain results to summarize the top matches from rank.txt.");
    phenoLogsEl.textContent = "No logs yet.";
    previewsView.render({message:"No interactive plots available yet."});
    renderPhenoBackgroundJobBanner();
  }

  function clearDatasetWorkspace() {
    ctx.state.phenoQuerySelection = null;
    state.plannedPrompt = '';
    state.workspaceVersion += 1;
    state.inFlight = false;
    state.planInFlight = false;
    state.explainInFlight = false;
    state.explainLlmInFlight = false;
    state.rankerPatientIds = [];
    state.rankerRecordIds = [];
    state.referenceFiles = [];
    state.manualOverrides = false;
    stopPhenoPlanProgressUpdates();
    stopPhenoRunProgressUpdates();
    onPatientIdsLoaded([]);
    onReferenceFilesLoaded([]);
    patientPicker.reset();
    const choices = document.getElementById('phenoPatientChoices');
    renderOptions(choices);
    if (phenoSelectedPatientIdsEl) phenoSelectedPatientIdsEl.value = "";
    if (phenoReferenceFilesSummaryEl) {
      renderPhenoFiles(phenoReferenceFilesSummaryEl, [], "None");
    }
    if (phenoPlanStatusEl) {
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = "Load a workspace before planning a Pheno-Ranker run.";
    }
    if (phenoPlanMetaEl) metaView.render([]);
    planPreviewView.render({text:'No plan yet.'});
    renderPhenoPlanReasoning([]);
    renderPhenoPlanFollowUps();
    if (phenoStatusEl) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "No workspace loaded.";
    }
    resetPhenoRunWorkspace();
    renderSelectedPatientIdsSummary();
    updatePhenoRunAvailability();
  }

  function renderPhenoNoPlanState(reasoning) {
    phenoPlanStatusEl.className = "pheno-status warning";
    phenoPlanStatusEl.textContent = "Planner did not find a runnable Pheno-Ranker request yet.";
    phenoPlanEl.classList.add("is-blocking");
    phenoPlanReasoningEl.classList.add("is-blocking");
    planPreviewView.render({text:"No actionable plan."});
    renderPhenoPlanReasoning(reasoning || [], null);
    planningView.warn({title:"No runnable plan yet.",detail:"Describe a comparison or extraction request instead of a greeting or generic note."});
  }

  function compactPhenoPlan(plan) {
    const compact = {};
    for (const [key, value] of Object.entries(plan || {})) {
      if (Array.isArray(value) && !value.length) {
        continue;
      }
      if (value === "" || value === null || value === undefined) {
        continue;
      }
      compact[key] = value;
    }
    return compact;
  }

  function parsePhenoTermsInput(value) {
    return String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function renderSelectedPatientIdsSummary() {
    const selection = ctx.state?.phenoQuerySelection;
    if (selection?.handle && !getSelectedSavedCohortIds().length) {
      phenoSelectedPatientIdsSummaryEl.textContent = `Scope: ${selection.count} ${selection.idType === 'sample' ? 'samples' : 'patients'} from Query; identifiers remain server-side. Enter manual IDs to replace this selection.`;
      renderGlobalContext();
      return;
    }
    const ids = getCurrentScopeIds();
    if (!ids.length) {
      phenoSelectedPatientIdsSummaryEl.textContent = "Scope: full workspace.";
      renderGlobalContext();
      return;
    }
    const preview = ids.slice(0, 8).join(", ");
    const suffix = ids.length > 8 ? ` ... (+${ids.length - 8} more)` : "";
    const invalidIds = state.rankerPatientIds.length
      ? ids.filter((patientId) => !state.rankerPatientIds.includes(patientId))
      : [];
    if (invalidIds.length) {
      phenoSelectedPatientIdsSummaryEl.textContent = `Scope: ${ids.length} IDs entered. Some are patient-level IDs, but Pheno-Ranker needs the original record IDs or timepoints for this reference: ${invalidIds.join(", ")}.`;
      renderGlobalContext();
      return;
    }
    phenoSelectedPatientIdsSummaryEl.textContent = `Scope: ${ids.length} selected samples. ${preview}${suffix}`;
    renderGlobalContext();
  }

  function applyPhenoPlan(plan) {
    state.isApplyingPlan = true;
    const normalized = plan || {};
    phenoActionEl.value = normalized.action || "compare";
    phenoModeEl.value = normalized.mode || "cohort";
    const scopeIdsBeforePlan = getCurrentScopeIds();
    patientPicker.set(normalized.patient_id || "");
    if (!ctx.state?.phenoQuerySelection?.handle && typeof normalized.selected_patient_ids === "string" && normalized.selected_patient_ids.trim()) {
      phenoSelectedPatientIdsEl.value = normalized.selected_patient_ids;
    }
    const scopeIdsAfterPlan = getCurrentScopeIds();
    if (phenoModeEl.value === "patient" && !phenoPatientIdEl.value.trim() && scopeIdsAfterPlan.length === 1) {
      patientPicker.set(scopeIdsAfterPlan[0]);
    } else if (
      phenoModeEl.value === "patient"
      && !phenoPatientIdEl.value.trim()
      && !scopeIdsAfterPlan.length
      && scopeIdsBeforePlan.length === 1
    ) {
      patientPicker.set(scopeIdsBeforePlan[0]);
    }
    renderSelectedPatientIdsSummary();
    phenoIncludeTermsEl.value = Array.isArray(normalized.include_terms) ? normalized.include_terms.join(",") : (normalized.include_terms || "");
    phenoExcludeTermsEl.value = Array.isArray(normalized.exclude_terms) ? normalized.exclude_terms.join(",") : (normalized.exclude_terms || "");
    phenoSimilarityMetricEl.value = normalized.similarity_metric_cohort || "";
    phenoSortByEl.value = normalized.sort_by || "";
    phenoMaxOutEl.value = Number(normalized.max_out || 10);
    phenoAlignEl.checked = Boolean(normalized.align);
    phenoRenderHeatmapEl.checked = Boolean(normalized.render_heatmap);
    phenoRenderMdsEl.checked = Boolean(normalized.render_mds);
    if (phenoRenderGraphEl) {
      phenoRenderGraphEl.checked = Boolean(normalized.render_graph);
    }
    if (phenoGraphMinWeightEl && Object.prototype.hasOwnProperty.call(normalized, "graph_min_weight")) {
      phenoGraphMinWeightEl.value = normalized.graph_min_weight === undefined || normalized.graph_min_weight === null ? "" : String(normalized.graph_min_weight);
    }
    if (phenoGraphMaxWeightEl && Object.prototype.hasOwnProperty.call(normalized, "graph_max_weight")) {
      phenoGraphMaxWeightEl.value = normalized.graph_max_weight === undefined || normalized.graph_max_weight === null ? "" : String(normalized.graph_max_weight);
    }
    updatePhenoMode();
    state.isApplyingPlan = false;
    state.manualOverrides = false;
  }

  async function requestPhenoPlan(revealPlan = true) {
    if (revealPlan) document.getElementById('phenoTechnicalDetails').open = true;
    if (callbacks.phenoChatIssue?.()) { phenoStatusEl.textContent = callbacks.phenoChatIssue(); return null; }
    if (state.planInFlight) {
      return null;
    }
    const text = phenoPromptEl.value.trim();
    if (state.manualOverrides || !text) {
      if (revealPlan && phenoPlanDetailsEl) {
        phenoPlanDetailsEl.open = true;
        phenoPlanDetailsEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return renderPhenoManualSettingsPreview("Previewing current form settings. Run Pheno-Ranker will use these values.");
    }

    const workspaceVersion = state.workspaceVersion;
    state.planInFlight = true;
    updatePhenoRunAvailability();
    phenoPlanBtnEl.disabled = true;
    phenoPlanRunBtnEl.disabled = true;
    if (revealPlan && phenoPlanDetailsEl) {
      phenoPlanDetailsEl.open = true;
      phenoPlanDetailsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    phenoPlanStatusEl.className = "pheno-status loading";
    phenoPlanStatusEl.textContent = "Interpreting request...";
    renderPhenoPlanMeta("");
    renderPhenoPlanFollowUps();
    planPreviewView.render({activity:activityState("Interpreting request", "Reading the natural-language request and extracting a runnable plan.")});
    renderPlanningProgress();
    startPhenoPlanProgressUpdates();
    await nextFrame();
    if (workspaceVersion !== state.workspaceVersion) return null;

    try {
      const response = await fetch("/pheno-ranker/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
          selected_patient_ids: phenoSelectedPatientIdsEl.value.trim(),
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        if (workspaceVersion !== state.workspaceVersion) return null;
        const detail = error.detail && typeof error.detail === "object" ? JSON.stringify(error.detail, null, 2) : String(error.detail || "Planner request failed.");
        stopPhenoPlanProgressUpdates();
        phenoPlanStatusEl.className = "pheno-status";
        phenoPlanStatusEl.textContent = "Planner failed.";
        document.getElementById('phenoTechnicalDetails').open = true;
        renderPhenoPlanMeta("");
        planPreviewView.render({text:detail});
        renderPhenoPlanReasoning([], null);
        renderPhenoPlanFollowUps();
        return null;
      }
      const payload = await response.json();
      if (workspaceVersion !== state.workspaceVersion) return null;
      stopPhenoPlanProgressUpdates();
      renderPhenoPlanMeta(payload);
      renderPhenoPlanFollowUps(payload);
      if (!payload.plan || typeof payload.plan !== "object") {
        document.getElementById('phenoTechnicalDetails').open = true;
        renderPhenoNoPlanState(payload.reasoning || []);
        return payload;
      }
      applyPhenoPlan(payload.plan || {});
      state.plannedPrompt = text;
      planPreviewView.render({text:JSON.stringify(compactPhenoPlan(payload.plan || {}), null, 2)});
      renderPhenoPlanReasoning(payload.reasoning || [], payload.plan || {});
      const blockingIssues = getPhenoPlanBlockingIssues(payload.plan || {});
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = blockingIssues.length
        ? blockingIssues.join(" ")
        : "Planner ready. Review the interpreted plan for the current scope, then run it.";
      renderPhenoPlanState(payload.plan || {}, payload.reasoning || []);
      if (blockingIssues.length && payload.plan.mode === "patient") {
        phenoPatientIdEl.focus();
        phenoPatientIdEl.scrollIntoView({ block: "center", behavior: "smooth" });
      }
      return payload;
    } catch (error) {
      if (workspaceVersion !== state.workspaceVersion) return null;
      stopPhenoPlanProgressUpdates();
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = "Planner request failed.";
      document.getElementById('phenoTechnicalDetails').open = true;
      renderPhenoPlanMeta("");
      planPreviewView.render({text:error && error.message ? error.message : "Unexpected planner failure."});
      renderPhenoPlanReasoning([], null);
      renderPhenoPlanFollowUps();
      return null;
    } finally {
      stopPhenoPlanProgressUpdates();
      state.planInFlight = false;
      phenoPlanBtnEl.disabled = false;
      phenoPlanRunBtnEl.disabled = false;
      updatePhenoRunAvailability();
    }
  }

  async function planPhenoRanker() {
    await requestPhenoPlan(true);
  }

  async function planAndRunPhenoRanker() {
    const payload = await requestPhenoPlan(true);
    if (!payload || !payload.plan) {
      return;
    }
    if (getPhenoPlanBlockingIssues(payload.plan || {}).length) {
      return;
    }
    await runPhenoRanker(false);
  }

  function renderPhenoResultFiles(files) {
    filesView.render({kind:'files',files:Array.isArray(files) ? files : []});
  }

  function parseTsvLines(text) {
    const lines = String(text || "").split("\r\n").join("\n").split("\n").filter((line) => line.trim() && line.includes("\t"));
    if (!lines.length) {
      return null;
    }
    const header = lines[0].split("\t").map((cell) => cell.trim());
    if (header.length < 2) {
      return null;
    }
    const bodyRows = lines.slice(1)
      .map((line) => line.split("\t").map((cell) => cell.trim()))
      .filter((cells) => cells.length === header.length);
    if (!bodyRows.length) {
      return null;
    }
    return [header].concat(bodyRows);
  }

  function normalizePhenoBucketName(bucket) {
    const value = String(bucket || "").trim();
    if (!value) {
      return "Other";
    }
    if (value === "phenotypicFeatures") {
      return "Phenotypic Features";
    }
    if (value === "identifier") {
      return "Identifier";
    }
    if (value === "sex") {
      return "Sex";
    }
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function getPhenoBucketStyle(bucket) {
    return PHENO_BUCKET_STYLES[bucket] || PHENO_BUCKET_STYLES.other;
  }

  function formatPhenoReferenceLabel(filePath) {
    const raw = String(filePath || "").trim().split("/").pop() || "";
    if (!raw) {
      return "";
    }
    let value = raw.replace(/\.(json|tsv|txt|csv)$/i, "");
    value = value.replace(/^reference\.saved\.\d+\./i, "");
    value = value.replace(/^reference\.selected$/i, "selected scope");
    value = value.replace(/^default__|^private-dataset__/i, "");
    value = value.replace(/[_-]+/g, " ").trim();
    if (!value) {
      return "";
    }
    return value.replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function getPhenoReferenceLabelByCohortNumber(cohortNumber) {
    const index = Math.max(Number(cohortNumber || 0), 1) - 1;
    const files = Array.isArray(state.referenceFiles) ? state.referenceFiles : [];
    return formatPhenoReferenceLabel(files[index] || "");
  }

  function getPhenoMdsCohortInfo(recordId) {
    const rawId = String(recordId || "").trim();
    const match = rawId.match(/^(C(\d+))_(.+)$/);
    if (!match) {
      return {
        key: "unscoped",
        label: "Unscoped",
        displayId: rawId,
        color: "#2563eb",
      };
    }
    const cohortNumber = Number(match[2]);
    const color = PHENO_COHORT_COLORS[(Math.max(cohortNumber, 1) - 1) % PHENO_COHORT_COLORS.length];
    const inferredName = getPhenoReferenceLabelByCohortNumber(cohortNumber);
    return {
      key: match[1],
      label: inferredName ? `C${match[2]} (${inferredName})` : `C${match[2]}`,
      displayId: match[3],
      color,
    };
  }

  function renderPhenoCohortLegend(containerId, recordIds) {
    const container = document.getElementById(containerId);
    if (!container) {
      return;
    }
    const cohortItems = [];
    for (const recordId of Array.isArray(recordIds) ? recordIds : []) {
      const cohort = getPhenoMdsCohortInfo(recordId);
      if (cohort.key === "unscoped") {
        continue;
      }
      if (!cohortItems.some((item) => item.key === cohort.key)) {
        cohortItems.push(cohort);
      }
    }
    if (!cohortItems.length) {
      renderPhenoLegend(container, []);
      container.classList.add("is-hidden");
      return;
    }
    container.classList.remove("is-hidden");
    renderPhenoLegend(container,cohortItems);
  }

  function renderPhenoAlignmentPlaceholder(message) {
    alignmentView.render({message});
  }

  function renderPhenoExplainPlaceholder(message) {
    explanationView.render({message});
  }

  function getEffectivePhenoCohortMetric() {
    if (!state.runState || state.runState.mode !== "cohort") {
      return "hamming";
    }
    const raw = String(state.runState.similarityMetricCohort || "").trim().toLowerCase();
    return raw === "jaccard" ? "jaccard" : "hamming";
  }

  function hasPhenoAlignmentFiles(files) {
    return Array.isArray(files) && files.some((file) => file.name === "alignment.target.csv");
  }

  function renderPhenoAlignmentDetail(payload) {
    alignmentView.render({payload});
  }

  function renderPhenoExplainDetail(payload) {
    callbacks.onPhenoChatExplanation?.({...payload, chat_run_job_id:state.runState?.jobId});
    explanationView.render(phenoExplanationModel(payload));
  }

  function phenoExplanationModel(payload) {
    const matches = Array.isArray(payload.matches) ? payload.matches : [];
    if (!matches.length) {
      return {message:'No explanation could be generated for this run.'};
    }
    const targetId = payload.target_id || "unknown";
    const topN = String(payload.top_n || matches.length);
    const data = payload && payload.data ? payload.data : {};
    const isLlm = data.source === "llm" || payload.source === "lm_studio";
    const badges = [];
    const formatAiProviderGranularity = (value) => {
      const label = String(value || "").replace(/_/g, " ");
      return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : "";
    };
    if (isLlm && data.ai_provider_context_granularity && data.ai_provider_access) {
      let title = "";
      if (data.ai_provider_access === "blocked") {
        title = "AI providers are blocked for this dataset or workspace.";
      } else if (data.ai_provider_access === "safe_summary") {
        title = "AI providers may be used, but they only receive provider-safe structural summary context.";
      } else {
        title = `AI providers may receive up to detailed context and currently receive ${formatAiProviderGranularity(data.ai_provider_context_granularity)} context for this Pheno-Ranker explanation.`;
      }
      badges.push(renderProvenanceBadge(`Model context: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}`, title, "provider"));
    }
    const resultIcon = isLlm
      ? "llm"
      : data.source === "policy"
        ? "blocked"
        : data.source === "provider_unavailable"
          ? "unavailable"
          : "deterministic";
    badges.push(renderProvenanceBadge(
      isLlm ? "LLM answer" : "Deterministic",
      isLlm
        ? "LM Studio generated the narrative explanation from the provided Pheno-Ranker evidence."
        : "The app explained these Pheno-Ranker results deterministically from local artifacts.",
      resultIcon,
    ));
    if (data.model) {
      badges.push(renderProvenanceBadge(String(data.model), "LM Studio model used for this Pheno-Ranker explanation.", "llm"));
    }
    const prepareItems = items => (Array.isArray(items) ? items : []).map(item => ({
      label:item.label || '', style:getPhenoBucketStyle(item.bucket || 'other'),
    }));
    return {targetId,topN,isLlm,provenance:badges,reply:payload.llm_reply || "",
      matches:matches.map(match => ({
        reference_id:match.reference_id,
        metrics:Object.entries(match.metrics || {}).filter(([,value])=>value !== ""),
        highlights:Array.isArray(match.metric_highlights) ? match.metric_highlights : [],
        shared:prepareItems(match.alignment?.top_shared_items),
        referenceOnly:prepareItems(match.alignment?.top_reference_only_items),
        targetOnly:prepareItems(match.alignment?.top_target_only_items),
      })),
    };
  }

  async function explainPhenoResults() {
    if (!state.runState || !state.runState.jobId) {
      renderPhenoExplainPlaceholder("Run Pheno-Ranker first.");
      return;
    }
    if (state.runState.mode !== "patient") {
      renderPhenoExplainPlaceholder("Explain results currently supports patient-mode runs only.");
      return;
    }
    const workspaceVersion = state.workspaceVersion;
    state.explainInFlight = true;
    updatePhenoExplainActions();
    callbacks.onPhenoExplanationStatus?.({llm:false});
    explanationView.render({activity:activityState(
      "Explaining results",
      "Summarizing the top patient matches and alignment signals from rank.txt."
    )});
    try {
      const response = await fetch(`/pheno-ranker/explain/${encodeURIComponent(state.runState.jobId)}?top_n=3`);
      if (!response.ok) {
        const error = await response.json();
        if (workspaceVersion !== state.workspaceVersion) return;
        renderPhenoExplanationError(error.detail || "Unable to explain these results.");
        return;
      }
      const payload = await response.json();
      if (workspaceVersion !== state.workspaceVersion) return;
      renderPhenoExplainDetail(payload);
    } catch (error) {
      if (workspaceVersion !== state.workspaceVersion) return;
      renderPhenoExplanationError(error && error.message ? error.message : "Unable to explain these results.");
    } finally {
      state.explainInFlight = false;
      updatePhenoExplainActions();
    }
  }

  async function explainPhenoResultsWithLlm() {
    if (!state.runState || !state.runState.jobId) {
      renderPhenoExplainPlaceholder("Run Pheno-Ranker first.");
      return;
    }
    if (state.runState.mode !== "patient") {
      renderPhenoExplainPlaceholder("Explain with LLM currently supports patient-mode runs only.");
      return;
    }
    const workspaceVersion = state.workspaceVersion;
    state.explainLlmInFlight = true;
    updatePhenoExplainActions();
    callbacks.onPhenoExplanationStatus?.({llm:true});
    explanationView.render({activity:activityState(
      "Explaining with LLM",
      "Reviewing the top matches and drafting a clinician-friendly interpretation."
    )});
    try {
      const response = await fetch(`/pheno-ranker/explain-llm/${encodeURIComponent(state.runState.jobId)}?top_n=3`);
      if (!response.ok) {
        const error = await response.json();
        if (workspaceVersion !== state.workspaceVersion) return;
        renderPhenoExplanationError(error.detail || "Unable to explain these results with LM Studio.");
        return;
      }
      const payload = await response.json();
      if (workspaceVersion !== state.workspaceVersion) return;
      renderPhenoExplainDetail(payload);
    } catch (error) {
      if (workspaceVersion !== state.workspaceVersion) return;
      renderPhenoExplanationError(error && error.message ? error.message : "Unable to explain these results with LM Studio.");
    } finally {
      state.explainLlmInFlight = false;
      updatePhenoExplainActions();
    }
  }

  function renderPhenoExplanationError(message) {
    const text = typeof message === 'string' ? message : 'Unable to explain these results.';
    callbacks.onPhenoExplanationStatus?.({error:text});
    renderPhenoExplainPlaceholder(text);
  }

  async function loadPhenoAlignment(referenceId, targetId) {
    if (!state.runState || !state.runState.jobId || !state.runState.alignmentAvailable) {
      renderPhenoAlignmentPlaceholder("No alignment output is available for this run.");
      return;
    }
    const selectionKey = `${referenceId}::${targetId}`;
    const workspaceVersion = state.workspaceVersion;
    state.selectedAlignmentKey = selectionKey;
    renderSortablePhenoTable();
    renderPhenoAlignmentPlaceholder("Loading alignment details...");
    try {
      const response = await fetch(`/pheno-ranker/alignment/${encodeURIComponent(state.runState.jobId)}?reference_id=${encodeURIComponent(referenceId)}&target_id=${encodeURIComponent(targetId)}`);
      if (!response.ok) {
        const error = await response.json();
        if (workspaceVersion !== state.workspaceVersion) return;
        renderPhenoAlignmentPlaceholder(error.detail || "Alignment details are unavailable for this pair.");
        return;
      }
      const payload = await response.json();
      if (workspaceVersion !== state.workspaceVersion) return;
      renderPhenoAlignmentDetail(payload);
    } catch (error) {
      if (workspaceVersion !== state.workspaceVersion) return;
      renderPhenoAlignmentPlaceholder(error && error.message ? error.message : "Unable to load alignment details.");
    }
  }

  function inferPhenoColumnType(rows, columnIndex) {
    const values = rows.map((row) => row[columnIndex]).filter((value) => value !== "");
    if (!values.length) {
      return "text";
    }
    const numericValues = values.filter((value) => Number.isFinite(Number(value.replace(/,/g, ""))));
    return numericValues.length === values.length ? "number" : "text";
  }

  function comparePhenoCells(left, right, type, direction) {
    if (type === "number") {
      const leftValue = Number(String(left || "").replace(/,/g, ""));
      const rightValue = Number(String(right || "").replace(/,/g, ""));
      return direction === "asc" ? leftValue - rightValue : rightValue - leftValue;
    }
    const compared = String(left || "").localeCompare(String(right || ""), undefined, { numeric: true, sensitivity: "base" });
    return direction === "asc" ? compared : -compared;
  }

  function renderSortablePhenoTable() {
    if (!state.tableState || !Array.isArray(state.tableState.headers) || !Array.isArray(state.tableState.rows)) {
      outputView.render({message:"No output preview available."});
      return;
    }
    const { headers, rows, sortIndex, sortDirection, sourceName, interactive, referenceColumnIndex, targetColumnIndex } = state.tableState;
    const type = inferPhenoColumnType(rows, sortIndex);
    const sortedRows = rows.slice().sort((left, right) => comparePhenoCells(left[sortIndex], right[sortIndex], type, sortDirection));
    const note = interactive
      ? `${sourceName} loaded as TSV. Click a column header to sort. Click one result row to inspect matched variables for that pair.`
      : `${sourceName} loaded as TSV. Click a column header to sort.`;
    const rowKeys=new Map(state.tableState.rows.map((row,index)=>[row,index]));
    outputView.render({kind:'table',note,headers,sortIndex,sortDirection,interactive,
      rows:sortedRows.map(row=>{
        const referenceId=interactive && referenceColumnIndex>=0 ? row[referenceColumnIndex] : "";
        const targetId=interactive && targetColumnIndex>=0 ? row[targetColumnIndex] : "";
        return {row,key:rowKeys.get(row),referenceId,targetId,
          selected:interactive && state.selectedAlignmentKey===`${referenceId}::${targetId}`};
      })});
  }

  function setPhenoTable(rows, sourceName, options) {
    if (!Array.isArray(rows) || rows.length < 2) {
      state.tableState = null;
      updatePhenoResultActions();
      return;
    }
    const tableOptions = options || {};
    state.tableState = {
      headers: rows[0],
      rows: rows.slice(1),
      sortIndex: 0,
      sortDirection: "asc",
      sourceName,
      interactive: Boolean(tableOptions.interactive),
      referenceColumnIndex: Number.isInteger(tableOptions.referenceColumnIndex) ? tableOptions.referenceColumnIndex : -1,
      targetColumnIndex: Number.isInteger(tableOptions.targetColumnIndex) ? tableOptions.targetColumnIndex : -1,
    };
    renderSortablePhenoTable();
    updatePhenoResultActions();
  }

  async function copyPhenoMatchIds() {
    const recordIds = getPhenoTopMatchRecordIds();
    if (!recordIds.length) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "No matched IDs are available to copy from this run.";
      return;
    }
    try {
      const payload = recordIds.join(",");
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(payload);
        copied = true;
      } else {
        copied = fallbackCopyText(payload);
      }
      if (!copied) {
        throw new Error("copy_failed");
      }
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = `Copied ${recordIds.length} matched record IDs from Pheno-Ranker.`;
    } catch (_error) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "Unable to copy matched IDs from the browser.";
    }
  }

  function sendPhenoMatchesToAnalysis() {
    const recordIds = getPhenoTopMatchRecordIds();
    const patientIds = collapsePhenoRecordIdsToPatientIds(recordIds);
    if (!patientIds.length) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "No matched IDs are available to open in Analysis.";
      return;
    }
    analysisSelectedPatientIdsEl.value = patientIds.join(",");
    if (typeof setAnalysisScopeMetadataFromSelection === "function") {
      setAnalysisScopeMetadataFromSelection({
        sampleIds: recordIds,
        patientIds,
        idType: "sample",
        sourceKind: "pheno_ranker",
        sourcePrompt: "Top Pheno-Ranker matches",
      });
    }
    if (!analysisPromptEl.value.trim()) {
      analysisPromptEl.value = "Summarize the main clinical patterns in the top Pheno-Ranker matches and tell me what stands out.";
    }
    renderAnalysisScopeSummary();
    setActiveTab("analysis");
    syncCurrentAnalysisSessionFromUi({ render: true });
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = `Loaded ${patientIds.length} patient IDs from the top Pheno-Ranker matches into Analysis.`;
  }

  async function renderPhenoOutputPreview(files) {
    const items = Array.isArray(files) ? files : [];
    const preferred = items.find((file) => file.name === "rank.txt") || items.find((file) => file.name === "matrix.txt");
    if (!preferred) {
      state.tableState = null;
      updatePhenoResultActions();
      outputView.render({message:"No rank or matrix output file available for preview."});
      return;
    }
    try {
      const response = await fetch(preferred.url);
      if (!response.ok) {
        state.tableState = null;
        updatePhenoResultActions();
        outputView.render({message:"Unable to load output preview."});
        return;
      }
      const text = await response.text();
      if (preferred.name === "rank.txt") {
        const rows = parseTsvLines(text);
        if (rows && rows.length >= 2) {
          const header = rows[0];
          const referenceColumnIndex = header.indexOf("REFERENCE(ID)");
          const targetColumnIndex = header.indexOf("TARGET(ID)");
          setPhenoTable(rows, preferred.name, {
            interactive: hasPhenoAlignmentFiles(items) && referenceColumnIndex >= 0 && targetColumnIndex >= 0,
            referenceColumnIndex,
            targetColumnIndex,
          });
          return;
        }
      }
      state.tableState = null;
      updatePhenoResultActions();
      if (preferred.name === "matrix.txt") {
        const previewLines = text.split("\r\n").join("\n").split("\n").slice(0, 20).join("\n");
        outputView.render({kind:'text',text:previewLines,note:'Matrix preview is intentionally limited. Use the file link or the plot outputs for full cohort inspection.'});
        return;
      }
      outputView.render({kind:'text',text});
    } catch (error) {
      state.tableState = null;
      updatePhenoResultActions();
      outputView.render({message:error?.message || "Unable to load output preview."});
    }
  }

  async function renderPhenoPreviews(files, runOptions = {}) {
    const items = Array.isArray(files) ? files : [];
    const mdsPointsFile = items.find((file) => file.name === "mds_points.tsv");
    const umapPointsFile = items.find((file) => file.name === "umap_points.tsv");
    const matrixFile = items.find((file) => file.name === "matrix.txt");
    const graphFile = items.find((file) => file.name === "graph.json");
    state.selectedMdsRecordIds = [];
    state.selectedUmapRecordIds = [];
    state.projectionPatientIds.clear();
    state.selectedHeatmapRecordIds = [];
    state.selectedGraphRecordIds = [];
    if (!mdsPointsFile && !umapPointsFile && !matrixFile && !graphFile) {
      previewsView.render({message:"No interactive plot data were produced for this run. Expected matrix.txt, mds_points.tsv, and/or graph.json."});
      return;
    }
    previewsView.render({kind:'plots',kinds:[
      ...(matrixFile ? ['heatmap'] : []),...(mdsPointsFile ? ['mds'] : []),
      ...(umapPointsFile ? ['umap'] : []),...(graphFile ? ['graph'] : []),
    ]});
    if (umapPointsFile) void renderInteractivePhenoMdsPlot(umapPointsFile, 'UMAP');
    if (mdsPointsFile) {
      void renderInteractivePhenoMdsPlot(mdsPointsFile);
    }
    if (matrixFile) {
      void renderInteractivePhenoHeatmap(matrixFile);
    }
    if (graphFile) {
      void renderInteractivePhenoGraph(graphFile, runOptions);
    }
  }




  function flashPhenoActionFeedback(button, label) {
    if (!button) {
      return;
    }
    const original = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = original;
    button.textContent = label;
    window.setTimeout(() => {
      button.textContent = button.dataset.originalLabel || original;
    }, 1200);
  }

  async function copySelectedPhenoPlotIds(kind, triggerButton) {
    const selectedIds = normalizePhenoSelectedRecordIds(getPhenoPlotSelection(kind));
    if (!selectedIds.length) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = kind === "heatmap"
        ? "Select heatmap cells first."
        : (kind === "graph" ? "Select graph nodes first." : `Select cohort points in the ${kind === 'umap' ? 'UMAP' : 'MDS'} plot first.`);
      flashPhenoActionFeedback(triggerButton, "No IDs");
      return;
    }
    try {
      const payload = selectedIds.join(",");
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(payload);
        copied = true;
      } else {
        copied = fallbackCopyText(payload);
      }
      if (!copied) {
        throw new Error("copy_failed");
      }
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = kind === "heatmap"
        ? `Copied ${selectedIds.length} heatmap-selected IDs.`
        : (kind === "graph"
          ? `Copied ${selectedIds.length} selected graph node IDs.`
          : `Copied ${selectedIds.length} selected cohort record IDs from the ${kind === 'umap' ? 'UMAP' : 'MDS'} plot.`);
      flashPhenoActionFeedback(triggerButton, "Copied");
    } catch (_error) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "Unable to copy selected IDs from the browser.";
      flashPhenoActionFeedback(triggerButton, "Unavailable");
    }
  }

  function sendSelectedPhenoPlotIdsToAnalysis(kind) {
    const selectedIds = normalizePhenoSelectedRecordIds(getPhenoPlotSelection(kind));
    if (!selectedIds.length) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = kind === "heatmap"
        ? "Select heatmap cells first."
        : (kind === "graph" ? "Select graph nodes first." : `Select cohort points in the ${kind === 'umap' ? 'UMAP' : 'MDS'} plot first.`);
      return;
    }
    analysisSelectedPatientIdsEl.value = selectedIds.join(",");
    if (typeof setAnalysisScopeMetadataFromSelection === "function") {
      setAnalysisScopeMetadataFromSelection({
        sampleIds: selectedIds,
        patientIds: collapsePhenoRecordIdsToPatientIds(selectedIds),
        idType: "sample",
        sourceKind: `pheno_ranker_${kind}`,
        sourcePrompt: `Pheno-Ranker ${kind} selection (${selectedIds.length} samples)`,
      });
    }
    if (!analysisPromptEl.value.trim()) {
      analysisPromptEl.value = kind === "heatmap"
        ? "Summarize the main clinical patterns in the selected heatmap subgroup and tell me what stands out."
        : (kind === "graph"
          ? "Summarize the main clinical patterns in the selected graph subgroup and tell me what stands out."
          : `Summarize the main clinical patterns in the selected ${kind === 'umap' ? 'UMAP' : 'MDS'} subgroup and tell me what stands out.`);
    }
    renderAnalysisScopeSummary();
    setActiveTab("analysis");
    syncCurrentAnalysisSessionFromUi({ render: true });
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = kind === "heatmap"
      ? `Loaded ${selectedIds.length} sample IDs from the selected heatmap subgroup into Analysis.`
      : (kind === "graph"
        ? `Loaded ${selectedIds.length} sample IDs from the selected graph subgroup into Analysis.`
        : `Loaded ${selectedIds.length} sample IDs from the selected ${kind === 'umap' ? 'UMAP' : 'MDS'} subgroup into Analysis.`);
  }

  async function saveSelectedPhenoPlotIdsAsCohort(kind, triggerButton) {
    const selectedIds = normalizePhenoSelectedRecordIds(getPhenoPlotSelection(kind));
    if (!selectedIds.length) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = kind === "heatmap"
        ? "Select heatmap cells first."
        : (kind === "graph" ? "Select graph nodes first." : `Select cohort points in the ${kind === 'umap' ? 'UMAP' : 'MDS'} plot first.`);
      flashPhenoActionFeedback(triggerButton, "No IDs");
      return;
    }
    const patientIds = collapsePhenoRecordIdsToPatientIds(selectedIds);
    const saved = await saveIdsAsCohort({
      sampleIds: selectedIds,
      patientIds,
      sourceKind: "pheno_ranker_selection",
      sourcePrompt: kind === "heatmap"
        ? "Selected subgroup from Pheno-Ranker heatmap"
        : (kind === "graph" ? "Selected subgroup from Pheno-Ranker graph" : `Selected subgroup from Pheno-Ranker ${kind === 'umap' ? 'UMAP' : 'MDS'}`),
      statusTarget: "pheno",
    });
    if (saved) {
      flashPhenoActionFeedback(triggerButton, "Saved");
    }
  }

  function restorePhenoRunMetadata(jobPayload) {
    const payload = jobPayload && typeof jobPayload === "object" ? jobPayload : {};
    phenoPromptEl.value = String(payload.prompt || "").trim();
    phenoActionEl.value = String(payload.action || "compare").trim() || "compare";
    phenoModeEl.value = String(payload.mode || "cohort").trim() || "cohort";
    patientPicker.set(payload.patient_id);
    phenoSelectedPatientIdsEl.value = String(payload.selected_patient_ids || "").trim();
    ctx.state.phenoQuerySelection = payload.query_selection || null;
    phenoIncludeTermsEl.value = Array.isArray(payload.include_terms) ? payload.include_terms.join(",") : "";
    phenoExcludeTermsEl.value = Array.isArray(payload.exclude_terms) ? payload.exclude_terms.join(",") : "";
    phenoSimilarityMetricEl.value = String(payload.similarity_metric_cohort || "").trim();
    phenoSortByEl.value = String(payload.sort_by || "").trim();
    phenoMaxOutEl.value = Number(payload.max_out || 10);
    phenoAlignEl.checked = Boolean(payload.align);
    phenoRenderHeatmapEl.checked = Boolean(payload.render_heatmap);
    phenoRenderMdsEl.checked = Boolean(payload.render_mds);
    if (phenoRenderGraphEl) {
      phenoRenderGraphEl.checked = Boolean(payload.render_graph);
    }
    if (phenoGraphMinWeightEl) {
      phenoGraphMinWeightEl.value = payload.graph_min_weight === undefined || payload.graph_min_weight === null ? "" : String(payload.graph_min_weight);
    }
    if (phenoGraphMaxWeightEl) {
      phenoGraphMaxWeightEl.value = payload.graph_max_weight === undefined || payload.graph_max_weight === null ? "" : String(payload.graph_max_weight);
    }
    if (typeof setSelectedSavedCohortIds === "function") {
      setSelectedSavedCohortIds(Array.isArray(payload.selected_saved_cohort_ids) ? payload.selected_saved_cohort_ids : []);
    }
    updatePhenoMode();
    renderSelectedPatientIdsSummary();
    setPhenoManualOverrides(false);
  }

  async function applyPhenoRunPayload(payload, options = {}) {
    const source = payload && typeof payload === "object" ? payload : {};
    const statusPrefix = String(options.statusPrefix || "").trim();
    renderPhenoResultFiles(source.files);
    state.runState = {
      jobId: source.job_id,
      mode: source.mode,
      similarityMetricCohort: source.similarity_metric_cohort || "",
      alignmentAvailable: Boolean(source.mode === "patient" && hasPhenoAlignmentFiles(source.files)),
    };
    updatePhenoExplainActions();
    phenoOutputDetailsEl.open = source.mode === "patient";
    phenoStatusEl.className = "pheno-status";
    const completedLabel = statusPrefix || "Completed";
    phenoStatusEl.textContent = source.scope_expansion_note
      ? `${completedLabel} ${source.mode} run ${source.job_id}. ${source.scope_expansion_note}`
      : `${completedLabel} ${source.mode} run ${source.job_id}.`;
    phenoCommandEl.textContent = [
      source.command || "No command metadata.",
      source.cwd ? `\n# cwd: ${source.cwd}` : "",
    ].join("");
    phenoLogsEl.textContent = [source.stderr || "", ...(source.plots || []).map((item) => `${item.script}\nstdout:\n${item.stdout}\nstderr:\n${item.stderr}`)].filter(Boolean).join("\n\n") || "No diagnostic logs.";
    setPhenoResultWorkspaceVisible(true);
    await renderPhenoOutputPreview(source.files);
    await renderPhenoPreviews(source.files, source);
    const projectionErrors = (source.plots || []).filter(item => String(item.returncode) !== '0');
    if (projectionErrors.length) {
      previewsView.warning(projectionErrors.map(item => `${item.script}: ${item.stderr}`).join(' '));
    }
    if (source.mode === "patient" && state.runState.alignmentAvailable) {
      renderPhenoAlignmentPlaceholder("Click one row in rank.txt to inspect matched variables for that pair.");
    } else {
      renderPhenoAlignmentPlaceholder("Alignment details are available only for patient-mode runs.");
    }
    renderPhenoExplainPlaceholder("Use Explain results to summarize the top patient matches from rank.txt.");
    renderPhenoBackgroundJobBanner();
    if (!options.restoringChat) await callbacks.onPhenoChatResult?.(source);
  }

  async function loadCompletedPhenoJob(jobPayload, resultPayload = null) {
    const job = jobPayload && typeof jobPayload === "object" ? jobPayload : {};
    const result = resultPayload && typeof resultPayload === "object" ? resultPayload : null;
    if (!result) {
      throw new Error("This Pheno-Ranker job does not have a completed result yet.");
    }
    restorePhenoRunMetadata(job);
    setPhenoResultWorkspaceVisible(true);
    phenoStatusEl.className = "pheno-status loading";
    phenoStatusEl.textContent = "Loading completed Pheno-Ranker run...";
    phenoCommandEl.textContent = "Loading stored command and artifacts...";
    filesView.render({message:"Loading output files..."});
    outputView.render({kind:'activity',activity:activityState("Loading run", "Restoring the stored Pheno-Ranker result into this tab.")});
    renderPhenoAlignmentPlaceholder("Loading alignment details...");
    phenoLogsEl.textContent = "Loading stored logs...";
    previewsView.render({kind:'activity',activity:activityState("Loading plots", "Restoring interactive plots and output files from the completed background run.")});
    await applyPhenoRunPayload(result, { statusPrefix: "Loaded", restoringChat: true });
  }

  function scrollPhenoResultIntoView() {
    const activeBanner = (state.inFlight || currentActivePhenoBackgroundJob()) && phenoBackgroundJobBannerEl;
    const target = activeBanner || document.querySelector('.pheno-run-progress') || (phenoResultWorkspaceEl && !phenoResultWorkspaceEl.classList.contains("is-hidden")
      ? phenoResultWorkspaceEl
      : phenoStatusEl);
    if (!target || typeof target.scrollIntoView !== "function") return;
    window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function runPhenoRanker(usePromptPlanner = true) {
    if (state.chatPreparing) return;
    if (callbacks.phenoChatIssue?.()) { phenoStatusEl.textContent = callbacks.phenoChatIssue(); return; }
    if (!phenoPromptEl.value.trim()) {
      markPhenoManualOverride();
    }
    if (usePromptPlanner && phenoPromptEl.value.trim() && !state.manualOverrides && !hasPhenoGraphCutoffInput()) {
      const payload = await requestPhenoPlan(false);
      if (!payload || !payload.plan) {
        return;
      }
      if (getPhenoPlanBlockingIssues(payload.plan || {}).length) {
        return;
      }
      return runPhenoRanker(false);
    }
    if (state.inFlight) {
      return;
    }
    if (!phenoPromptEl.value.trim()) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "Describe a Pheno-Ranker request first.";
      updatePhenoRunAvailability();
      return;
    }
    const selectedSavedCohortIds = getSelectedSavedCohortIds();
    const scopeIds = selectedSavedCohortIds.length ? [] : getCurrentScopeIds();
    if (phenoModeEl.value === "patient") {
      if (!phenoPatientIdEl.value.trim() && scopeIds.length === 1) {
        patientPicker.set(scopeIds[0]);
      }
      if (scopeIds.length > 1) {
        phenoStatusEl.textContent = "Patient mode expects exactly one patient in scope, or one explicit Patient ID.";
        return;
      }
      if (!phenoPatientIdEl.value.trim()) {
        phenoStatusEl.textContent = "Enter a patient ID for patient mode, or set the scope to exactly one patient.";
        return;
      }
    }
    if (phenoActionEl.value === "extract" && !phenoSelectedPatientIdsEl.value.trim()) {
      phenoStatusEl.textContent = "Define a non-empty scope for extraction mode.";
      return;
    }
    if (state.rankerPatientIds.length || state.rankerRecordIds.length) {
      const validScopeIds = new Set([...(state.rankerPatientIds || []), ...(state.rankerRecordIds || [])]);
      const invalidScopeIds = scopeIds.filter((scopeId) => !validScopeIds.has(scopeId));
      if (invalidScopeIds.length) {
        phenoStatusEl.textContent = `Scope contains IDs not present in the current Pheno-Ranker reference: ${invalidScopeIds.join(", ")}.`;
        return;
      }
    }

    const workspaceVersion = state.workspaceVersion;
    state.chatPreparing = true;
    try {
      if (callbacks.beforePhenoChatRun && !await callbacks.beforePhenoChatRun()) return;
    } finally { state.chatPreparing = false; }
    if (workspaceVersion !== state.workspaceVersion) return;
    state.inFlight = true;
    updatePhenoRunAvailability();
    phenoStatusEl.className = "pheno-status loading";
    phenoStatusEl.textContent = "Running Pheno-Ranker...";
    setPhenoResultWorkspaceVisible(false);
    scrollPhenoResultIntoView();
    phenoCommandEl.textContent = "Preparing command...";
    filesView.render({message:"Waiting for Pheno-Ranker outputs."});
    state.runState = null;
    updatePhenoExplainActions();
    state.selectedAlignmentKey = "";
    state.tableState = null;
    phenoOutputDetailsEl.open = phenoModeEl.value === "patient";
    outputView.render({kind:'activity',activity:activityState("Preparing run", "Building the command and validating the selected scope.")});
    renderPhenoAlignmentPlaceholder("Waiting for alignment details.");
    phenoLogsEl.textContent = "Waiting for logs...";
    previewsView.render({kind:'activity',activity:activityState("Preparing plots", "Waiting for interactive cohort plots and result files from the active run.")});
    startPhenoRunProgressUpdates();
    await nextFrame();
    if (workspaceVersion !== state.workspaceVersion) return;

    try {
      const response = await fetch("/pheno-ranker/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: phenoPromptEl.value.trim(),
          action: phenoActionEl.value,
          mode: phenoModeEl.value,
          data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
          patient_id: patientPicker.get(),
          selected_patient_ids: selectedSavedCohortIds.length ? "" : phenoSelectedPatientIdsEl.value.trim(),
          scope_metadata: selectedSavedCohortIds.length ? {} : ctx.state?.phenoQuerySelection || {},
          selected_saved_cohort_ids: selectedSavedCohortIds,
          query_result_handle: selectedSavedCohortIds.length ? '' : ctx.state?.phenoQuerySelection?.handle || '',
          include_terms: parsePhenoTermsInput(phenoIncludeTermsEl.value),
          exclude_terms: parsePhenoTermsInput(phenoExcludeTermsEl.value),
          similarity_metric_cohort: phenoSimilarityMetricEl.value,
          sort_by: phenoSortByEl.value,
          max_out: Number(phenoMaxOutEl.value || 10),
          align: phenoAlignEl.checked,
          render_heatmap: phenoRenderHeatmapEl.checked,
          render_mds: phenoRenderMdsEl.checked,
          render_umap: ctx.state?.userSettings?.pheno_render_umap === true,
          render_graph: Boolean(phenoRenderGraphEl && phenoRenderGraphEl.checked),
          graph_min_weight: parseOptionalNumberInput(phenoGraphMinWeightEl),
          graph_max_weight: parseOptionalNumberInput(phenoGraphMaxWeightEl),
        }),
      });

      const payload = await response.json();
      if (workspaceVersion !== state.workspaceVersion) return;
      stopPhenoRunProgressUpdates();
      if (!response.ok) {
        const detailObject = payload && typeof payload.detail === "object" ? payload.detail : null;
        const detail = detailObject ? JSON.stringify(detailObject, null, 2) : String((payload && payload.detail) || "Pheno-Ranker failed.");
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = "Pheno-Ranker failed. See Logs for details.";
        scrollPhenoResultIntoView();
        phenoCommandEl.textContent = detailObject && detailObject.command ? detailObject.command : "Command failed before completion.";
        outputView.render({message:"No output preview available."});
        phenoLogsEl.textContent = detail;
        filesView.render({message:"No output files available."});
        previewsView.render({message:"No interactive plots available for this run."});
        await callbacks.onPhenoChatRunError?.({message:'Pheno-Ranker could not complete this run.', detail});
        return;
      }

      if (payload && payload.data && payload.data.execution === "queued") {
        await callbacks.onPhenoChatQueued?.(payload);
        seedQueuedPhenoBackgroundJob(payload);
        state.runState = null;
        updatePhenoExplainActions();
        setPhenoResultWorkspaceVisible(false);
        phenoCommandEl.textContent = "Queued as a background Pheno-Ranker run.";
        outputView.render({message:"Background run submitted. Open Queue to monitor progress and load the completed result."});
        phenoLogsEl.textContent = "Waiting for background run logs...";
        filesView.render({message:"No output files available until the background run completes."});
        previewsView.render({message:"Interactive plots will appear after the background run completes."});
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = payload.reply || "Background Pheno-Ranker run submitted.";
        updatePhenoRunAvailability();
        if (typeof handlePhenoJobSubmission === "function") {
          handlePhenoJobSubmission(payload);
        }
        renderPhenoBackgroundJobBanner();
        scrollPhenoResultIntoView();
        return;
      }

      await applyPhenoRunPayload(payload);
      if (typeof handlePhenoJobCompletion === "function") {
        handlePhenoJobCompletion(payload);
      }
      updatePhenoRunAvailability();
      scrollPhenoResultIntoView();
    } catch (error) {
      if (workspaceVersion !== state.workspaceVersion) return;
      stopPhenoRunProgressUpdates();
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "Network error while running Pheno-Ranker. See Logs for details.";
      outputView.render({message:"No output preview available."});
      filesView.render({message:"No output files available."});
      previewsView.render({message:"No interactive plots available for this run."});
      phenoLogsEl.textContent = error && error.message ? error.message : "Unexpected request failure.";
      await callbacks.onPhenoChatRunError?.({message:'Pheno-Ranker could not complete this run.', detail:phenoLogsEl.textContent});
      scrollPhenoResultIntoView();
    } finally {
      stopPhenoRunProgressUpdates();
      state.inFlight = false;
      updatePhenoRunAvailability();
      updatePhenoExplainActions();
    }
  }

  async function loadPhenoRankerPatientIds() {
    const workspaceVersion = state.workspaceVersion;
    const choices = document.getElementById('phenoPatientChoices');
    renderOptions(choices);
    try {
      const dataDir = encodeURIComponent((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim());
      const response = await fetch(`/pheno-ranker/patient-ids?data_dir=${dataDir}`);
      if (!response.ok) {
        if (workspaceVersion !== state.workspaceVersion) return;
        state.rankerPatientIds = [];
        state.rankerRecordIds = [];
        state.referenceFiles = [];
        renderPhenoFiles(phenoReferenceFilesSummaryEl, [], "Unavailable");
        onPatientIdsLoaded([]);
        onReferenceFilesLoaded([]);
        return;
      }
      const payload = await response.json();
      if (workspaceVersion !== state.workspaceVersion) return;
      state.rankerPatientIds = Array.isArray(payload.patient_ids) ? payload.patient_ids.filter(Boolean) : [];
      state.rankerRecordIds = Array.isArray(payload.record_ids) ? payload.record_ids.filter(Boolean) : [];
      if ((state.rankerRecordIds.length || state.rankerPatientIds.length)
          && phenoStatusEl.textContent === "No workspace loaded.") {
        phenoStatusEl.textContent = "";
      }
      patientPicker.load(state.rankerPatientIds, state.rankerRecordIds);
      state.referenceFiles = Array.isArray(payload.reference_files) ? payload.reference_files.filter(Boolean) : [];
      onPatientIdsLoaded(state.rankerPatientIds);
      onReferenceFilesLoaded(state.referenceFiles);
      if (!state.referenceFiles.length) {
        renderPhenoFiles(phenoReferenceFilesSummaryEl, [], "None");
      } else {
        const labels = state.referenceFiles.map((item) => item.split("/").pop());
        renderPhenoFiles(phenoReferenceFilesSummaryEl,labels);
      }
    } catch (_error) {
      if (workspaceVersion !== state.workspaceVersion) return;
      state.rankerPatientIds = [];
      state.rankerRecordIds = [];
      state.referenceFiles = [];
      renderPhenoFiles(phenoReferenceFilesSummaryEl, [], "Unavailable");
      onPatientIdsLoaded([]);
      onReferenceFilesLoaded([]);
    } finally {
      if (workspaceVersion === state.workspaceVersion) updatePhenoRunAvailability();
    }
  }

  function handleOutputPreviewClick(event) {
    const button = event.target.closest("[data-pheno-sort-index]");
    if (button && phenoOutputPreviewEl.contains(button) && state.tableState) {
      const nextIndex = Number(button.dataset.phenoSortIndex);
      if (!Number.isInteger(nextIndex)) {
        return;
      }
      if (state.tableState.sortIndex === nextIndex) {
        state.tableState.sortDirection = state.tableState.sortDirection === "asc" ? "desc" : "asc";
      } else {
        state.tableState.sortIndex = nextIndex;
        state.tableState.sortDirection = inferPhenoColumnType(state.tableState.rows, nextIndex) === "number" ? "desc" : "asc";
      }
      renderSortablePhenoTable();
      return;
    }
    const row = event.target.closest("[data-pheno-reference-id]");
    if (!row || !phenoOutputPreviewEl.contains(row) || !state.tableState || !state.tableState.interactive) {
      return;
    }
    loadPhenoAlignment(row.dataset.phenoReferenceId || "", row.dataset.phenoTargetId || "");
  }

  function handlePreviewsClick(event) {
    const button = event.target.closest("[data-pheno-plot-action]");
    if (!button || !phenoPreviewsEl.contains(button)) {
      return;
    }
    const kind = button.dataset.phenoPlotKind === "heatmap"
      ? "heatmap"
      : (button.dataset.phenoPlotKind === "graph" ? "graph" : (button.dataset.phenoPlotKind === "umap" ? "umap" : "mds"));
    if (button.dataset.phenoPlotAction === "copy") {
      void copySelectedPhenoPlotIds(kind, button);
      return;
    }
    if (button.dataset.phenoPlotAction === "save-cohort") {
      void saveSelectedPhenoPlotIdsAsCohort(kind, button);
      return;
    }
    if (button.dataset.phenoPlotAction === "analysis") {
      sendSelectedPhenoPlotIdsToAnalysis(kind);
    }
  }

  return {
    getPatientTargetId: () => patientPicker.get(),
    renderPlanningProgress,
    showPlanProgress: (label,detail) => planPreviewView.render({activity:activityState(label,detail)}),
    renderRunProgress(label,detail) {
      outputView.render({kind:'activity',activity:activityState(label,detail)});
      previewsView.render({kind:'activity',activity:activityState('Preparing plots','Waiting for interactive cohort plots and result files from the active run.')});
    },
    chatBusy: () => state.chatPreparing || state.inFlight || state.planInFlight || state.explainInFlight || state.explainLlmInFlight,
    restoreChatSetup: restorePhenoRunMetadata,
    restoreChatResult: payload => applyPhenoRunPayload(payload, {restoringChat:true, statusPrefix:'Saved'}),
    explanationModel: phenoExplanationModel,
    restoreChatExplanation: renderPhenoExplainDetail,
    updatePhenoMode,
    updatePhenoGraphOptions,
    renderSelectedPatientIdsSummary,
    loadPhenoRankerPatientIds,
    updatePhenoExplainActions,
    updatePhenoResultActions,
    updatePhenoRunAvailability,
    setPhenoResultWorkspaceVisible,
    resetPhenoRunWorkspace,
    clearDatasetWorkspace,
    planPhenoRanker,
    planAndRunPhenoRanker,
    runPhenoRanker,
    sendPhenoMatchesToAnalysis,
    copyPhenoMatchIds,
    explainPhenoResults,
    explainPhenoResultsWithLlm,
    loadPhenoAlignment,
    markPhenoManualOverride,
    setPhenoManualOverrides,
    handlePhenoPromptEdited,
    handlePhenoPlanFollowUpsClick,
    handleOutputPreviewClick,
    handlePreviewsClick,
    renderPhenoAlignmentPlaceholder,
    renderPhenoExplainPlaceholder,
    renderPhenoBackgroundJobBanner,
    loadCompletedPhenoJob,
  };
}
