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
    phenoReferenceFilesSummaryEl,
    phenoBackgroundJobBannerEl,
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

  const { PHENO_BUCKET_STYLES, PHENO_COHORT_COLORS } = constants;
  const { escapeHtml, renderActivityCard, fallbackCopyText, renderQueryReply, nextFrame } = helpers;
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
    saveIdsAsCohort,
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
    selectedHeatmapRecordIds: [],
    selectedGraphRecordIds: [],
    manualOverrides: false,
    isApplyingPlan: false,
    rankerPatientIds: [],
    rankerRecordIds: [],
    referenceFiles: [],
  };

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
    if (active) {
      const label = String(active.job_code || active.job_id || "").trim();
      phenoBackgroundJobBannerEl.classList.remove("is-hidden");
      phenoBackgroundJobBannerEl.textContent = label
        ? `Background Pheno-Ranker run in progress: ${label}.`
        : "A background Pheno-Ranker run is in progress.";
      return;
    }
    const completed = currentCompletedPhenoJobForWorkspace();
    if (completed) {
      const label = String(completed.job_code || completed.job_id || "").trim();
      phenoBackgroundJobBannerEl.classList.remove("is-hidden");
      phenoBackgroundJobBannerEl.textContent = label
        ? `Background Pheno-Ranker run completed: ${label}.`
        : "A background Pheno-Ranker run completed.";
      return;
    }
    phenoBackgroundJobBannerEl.classList.add("is-hidden");
    phenoBackgroundJobBannerEl.textContent = "";
  }

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

  function provenanceIconSvg(kind) {
    const icons = {
      summary: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h8"></path><path d="M8 12h8"></path><path d="M8 18h5"></path><rect x="4" y="3" width="16" height="18" rx="2"></rect></svg>',
      provider: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 10V7a4 4 0 1 1 8 0v3"></path><rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M12 14v2"></path></svg>',
      planner: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v6"></path><path d="M9 6h6"></path><path d="M5 13a7 7 0 1 0 14 0"></path><path d="m9 13 2 2 4-4"></path></svg>',
      deterministic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"></path></svg>',
      llm: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9h8"></path><path d="M8 13h5"></path><path d="M6 4h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-4 4v-4H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path></svg>',
      blocked: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="m8.5 8.5 7 7"></path><path d="m15.5 8.5-7 7"></path></svg>',
      unavailable: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>',
    };
    return icons[kind] || icons.summary;
  }

  function renderProvenanceIcon(kind, cls = "provenance-inline-icon") {
    return `<span class="${cls}" aria-hidden="true">${provenanceIconSvg(kind)}</span>`;
  }

  function renderProvenanceBadge(label, title = "", iconKind = "") {
    return `<span class="query-chip badge provenance-badge"${title ? ` title="${escapeHtml(title)}"` : ""}>${iconKind ? `${renderProvenanceIcon(iconKind, "provenance-badge-icon")}` : ""}<span>${escapeHtml(label)}</span></span>`;
  }

  function updatePhenoMode() {
    const patientMode = phenoModeEl.value === "patient";
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

  function renderPhenoPlanReasoning(items, plan = null) {
    const lines = Array.isArray(items) ? items.filter(Boolean) : [];
    const normalized = plan && typeof plan === "object" ? plan : null;
    const chips = [];
    if (normalized) {
      const action = String(normalized.action || "compare");
      const mode = String(normalized.mode || "cohort");
      const patientId = String(normalized.patient_id || "").trim();
      const invalidPatientId = String(normalized.invalid_patient_id || "").trim();
      const scopeIds = typeof normalized.selected_patient_ids === "string"
        ? normalized.selected_patient_ids.split(",").map((item) => item.trim()).filter(Boolean)
        : (Array.isArray(normalized.selected_patient_ids) ? normalized.selected_patient_ids.map((item) => String(item || "").trim()).filter(Boolean) : []);
      chips.push(`<span class="pheno-plan-chip pheno-plan-chip-action">${escapeHtml(action === "extract" ? "Extract" : "Compare")}</span>`);
      chips.push(`<span class="pheno-plan-chip ${mode === "patient" ? "pheno-plan-chip-patient" : "pheno-plan-chip-cohort"}">${escapeHtml(mode === "patient" ? "Patient mode" : "Cohort mode")}</span>`);
      if (invalidPatientId) {
        chips.push(`<span class="pheno-plan-chip pheno-plan-chip-invalid">Invalid target: ${escapeHtml(invalidPatientId)}</span>`);
      } else if (patientId) {
        chips.push(`<span class="pheno-plan-chip pheno-plan-chip-target">Target: ${escapeHtml(patientId)}</span>`);
      }
      if (scopeIds.length) {
        chips.push(`<span class="pheno-plan-chip pheno-plan-chip-scope">Scope: ${escapeHtml(String(scopeIds.length))} ID${scopeIds.length === 1 ? "" : "s"}</span>`);
      }
    }
    if (!lines.length && !chips.length) {
      phenoPlanReasoningEl.innerHTML = '<div class="empty">No planner reasoning yet.</div>';
      return;
    }
    phenoPlanReasoningEl.innerHTML = `
      ${chips.length ? `<div class="pheno-plan-chip-row">${chips.join("")}</div>` : ""}
      ${lines.length ? `<ul class="mini-list">${lines.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<div class="empty">No planner reasoning yet.</div>'}
    `;
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

    if (action === "extract" && !scopeIds.length) {
      issues.push("Extraction needs a non-empty Scope before it can run.");
    }

    if (mode === "patient") {
      if (invalidPatientId) {
        issues.push(`Patient ID ${invalidPatientId} does not exist in the current Pheno-Ranker reference dataset.`);
      }
      if (!patientId && scopeIds.length !== 1) {
        issues.push("Patient mode needs exactly one target patient from Patient ID or Scope.");
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

    const warningHtml = `
      <div class="planner-warning">
        <strong>Planner output is not runnable yet.</strong>
        <ul class="mini-list">${issues.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
    `;

    if (Array.isArray(reasoning) && reasoning.length) {
      phenoPlanReasoningEl.innerHTML = `${warningHtml}${phenoPlanReasoningEl.innerHTML}`;
    } else {
      phenoPlanReasoningEl.innerHTML = warningHtml;
    }
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
      phenoPlanMetaEl.innerHTML = "";
      return;
    }
    const chips = [];
    const formatAiProviderGranularity = (value) => String(value || "").replace(/_/g, " ");
    if (aiProviderConsulted && data.ai_provider_context_granularity && data.ai_provider_access) {
      let title = "";
      if (data.ai_provider_access === "blocked") {
        title = "AI providers are blocked for this dataset or workspace.";
      } else if (data.ai_provider_access === "safe_summary") {
        title = "AI providers may be used, but they only receive provider-safe structural summary context.";
      } else {
        title = `AI providers may receive up to detailed context and currently receive ${formatAiProviderGranularity(data.ai_provider_context_granularity)} context for Pheno-Ranker planning.`;
      }
      chips.push(renderProvenanceBadge(`AI providers: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}`, title, "provider"));
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
    phenoPlanMetaEl.innerHTML = chips.join("");
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
      patient_id: phenoPatientIdEl ? phenoPatientIdEl.value.trim() : "",
      selected_patient_ids: selectedSavedCohortIds.length ? "" : (phenoSelectedPatientIdsEl ? phenoSelectedPatientIdsEl.value.trim() : ""),
      selected_saved_cohort_ids: selectedSavedCohortIds,
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
    phenoPlanEl.textContent = JSON.stringify(compactPhenoPlan(plan), null, 2);
    renderPhenoPlanReasoning(
      ["These settings were edited after the last preview. Run Pheno-Ranker will use this current form state."],
      plan,
    );
    if (phenoPlanStatusEl.dataset.backgroundBlocked !== "true") {
      phenoPlanStatusEl.className = "pheno-status warning";
      phenoPlanStatusEl.textContent = statusText || "Settings changed after preview. The panel now shows the current form settings.";
    }
    renderPhenoPlanMeta("");
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
    if (phenoPlanEl) {
      phenoPlanEl.classList.remove("is-blocking");
      phenoPlanEl.textContent = "Prompt changed. Preview plan to see the interpreted settings.";
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
      const patientId = recordId.includes(":") ? recordId.split(":")[0] : recordId;
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
    const shouldDisable = state.inFlight || state.planInFlight || !hasPrompt || Boolean(activeBackgroundJob);
    phenoRunBtnEl.disabled = shouldDisable;
    phenoRunBtnEl.classList.toggle("is-background-blocked", Boolean(activeBackgroundJob));
    phenoRunBtnEl.title = activeBackgroundJob
      ? "A background Pheno-Ranker run is already in progress."
      : (!hasPrompt ? "Describe a Pheno-Ranker request first." : "");
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

  function getPhenoPlotSelection(kind) {
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
    state.selectedHeatmapRecordIds = [];
    state.selectedGraphRecordIds = [];
    state.tableState = null;
    state.explainInFlight = false;
    state.explainLlmInFlight = false;
    updatePhenoExplainActions();
    updatePhenoResultActions();
    setPhenoResultWorkspaceVisible(false);
    phenoCommandEl.textContent = "No run yet.";
    phenoFilesEl.innerHTML = '<div class="empty">No output files yet.</div>';
    phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview yet.</div>';
    renderPhenoAlignmentPlaceholder("Run patient mode, then click one row in rank.txt to inspect matched variables for that pair.");
    renderPhenoExplainPlaceholder("Run patient mode, then click Explain results to summarize the top matches from rank.txt.");
    phenoLogsEl.textContent = "No logs yet.";
    phenoPreviewsEl.innerHTML = '<div class="empty">No interactive plots available yet.</div>';
    renderPhenoBackgroundJobBanner();
  }

  function renderPhenoNoPlanState(reasoning) {
    phenoPlanStatusEl.className = "pheno-status warning";
    phenoPlanStatusEl.textContent = "Planner did not find a runnable Pheno-Ranker request yet.";
    phenoPlanEl.classList.add("is-blocking");
    phenoPlanReasoningEl.classList.add("is-blocking");
    phenoPlanEl.textContent = "No actionable plan.";
    renderPhenoPlanReasoning(reasoning || [], null);
    phenoPlanReasoningEl.innerHTML = `
      <div class="planner-warning">
        <strong>No runnable plan yet.</strong>
        <div>Describe a comparison or extraction request instead of a greeting or generic note.</div>
      </div>
      ${phenoPlanReasoningEl.innerHTML}
    `;
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
    phenoPatientIdEl.value = normalized.patient_id || "";
    if (typeof normalized.selected_patient_ids === "string" && normalized.selected_patient_ids.trim()) {
      phenoSelectedPatientIdsEl.value = normalized.selected_patient_ids;
    }
    const scopeIdsAfterPlan = getCurrentScopeIds();
    if (phenoModeEl.value === "patient" && !phenoPatientIdEl.value.trim() && scopeIdsAfterPlan.length === 1) {
      phenoPatientIdEl.value = scopeIdsAfterPlan[0];
    } else if (
      phenoModeEl.value === "patient"
      && !phenoPatientIdEl.value.trim()
      && !scopeIdsAfterPlan.length
      && scopeIdsBeforePlan.length === 1
    ) {
      phenoPatientIdEl.value = scopeIdsBeforePlan[0];
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
    if (state.planInFlight) {
      return null;
    }
    const text = phenoPromptEl.value.trim();
    if (!text) {
      phenoPlanStatusEl.textContent = "Describe a Pheno-Ranker request first.";
      return null;
    }

    if (state.manualOverrides) {
      if (revealPlan && phenoPlanDetailsEl) {
        phenoPlanDetailsEl.open = true;
        phenoPlanDetailsEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return renderPhenoManualSettingsPreview("Previewing current form settings. Run Pheno-Ranker will use these values.");
    }

    state.planInFlight = true;
    resetPhenoRunWorkspace();
    phenoPlanBtnEl.disabled = true;
    phenoPlanRunBtnEl.disabled = true;
    if (revealPlan && phenoPlanDetailsEl) {
      phenoPlanDetailsEl.open = true;
      phenoPlanDetailsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    phenoPlanStatusEl.className = "pheno-status loading";
    phenoPlanStatusEl.textContent = "Interpreting request...";
    renderPhenoPlanMeta("");
    phenoPlanEl.innerHTML = renderActivityCard("Interpreting request", "Reading the natural-language request and extracting a runnable plan.");
    phenoPlanReasoningEl.innerHTML = renderActivityCard("Planner reasoning", "Waiting for the interpreted plan and supporting rationale.");
    startPhenoPlanProgressUpdates();
    await nextFrame();

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
        const detail = error.detail && typeof error.detail === "object" ? JSON.stringify(error.detail, null, 2) : String(error.detail || "Planner request failed.");
        stopPhenoPlanProgressUpdates();
        phenoPlanStatusEl.className = "pheno-status";
        phenoPlanStatusEl.textContent = "Planner failed.";
        renderPhenoPlanMeta("");
        phenoPlanEl.textContent = detail;
        renderPhenoPlanReasoning([], null);
        return null;
      }
      const payload = await response.json();
      stopPhenoPlanProgressUpdates();
      renderPhenoPlanMeta(payload);
      if (!payload.plan || typeof payload.plan !== "object") {
        renderPhenoNoPlanState(payload.reasoning || []);
        return payload;
      }
      applyPhenoPlan(payload.plan || {});
      phenoPlanEl.textContent = JSON.stringify(compactPhenoPlan(payload.plan || {}), null, 2);
      renderPhenoPlanReasoning(payload.reasoning || [], payload.plan || {});
      const blockingIssues = getPhenoPlanBlockingIssues(payload.plan || {});
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = blockingIssues.length
        ? "Planner found a blocking issue. Fix the highlighted fields before running."
        : "Planner ready. Review the interpreted plan for the current scope, then run it.";
      renderPhenoPlanState(payload.plan || {}, payload.reasoning || []);
      return payload;
    } catch (error) {
      stopPhenoPlanProgressUpdates();
      phenoPlanStatusEl.className = "pheno-status";
      phenoPlanStatusEl.textContent = "Planner request failed.";
      renderPhenoPlanMeta("");
      phenoPlanEl.textContent = error && error.message ? error.message : "Unexpected planner failure.";
      renderPhenoPlanReasoning([], null);
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

  function renderPhenoFiles(files) {
    if (!Array.isArray(files) || !files.length) {
      phenoFilesEl.innerHTML = '<div class="empty">No output files yet.</div>';
      return;
    }
    phenoFilesEl.innerHTML = `<ul class="pheno-file-list">${files.map((file) => `<li><a href="${file.url}" target="_blank" rel="noreferrer">${escapeHtml(file.name)}</a> (${file.size} bytes)</li>`).join("")}</ul>`;
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
      container.innerHTML = "";
      container.classList.add("is-hidden");
      return;
    }
    container.classList.remove("is-hidden");
    container.innerHTML = cohortItems.map((cohort) => `
      <span class="pheno-cohort-chip" style="--cohort-color:${cohort.color};">
        <span class="pheno-cohort-chip-swatch" aria-hidden="true"></span>
        ${escapeHtml(cohort.label)}
      </span>
    `).join("");
  }

  function renderPhenoAlignmentPlaceholder(message) {
    phenoAlignmentDetailEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
  }

  function renderPhenoExplainPlaceholder(message) {
    phenoExplainDetailEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
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

  function groupAlignmentItemsByBucket(items) {
    const groups = {};
    for (const item of Array.isArray(items) ? items : []) {
      const bucket = item.bucket || "other";
      if (!groups[bucket]) {
        groups[bucket] = [];
      }
      groups[bucket].push(item);
    }
    return Object.entries(groups).sort((left, right) => left[0].localeCompare(right[0]));
  }

  function renderAlignmentRows(entries) {
    return entries.map((entry) => {
      const bucket = entry.bucket || "other";
      const style = getPhenoBucketStyle(bucket);
      return `<tr>
        <td>
          <span class="alignment-bucket-pill" style="--bucket-bg:${style.bg};--bucket-ink:${style.ink};">
            <span class="alignment-swatch"></span>
            ${escapeHtml(normalizePhenoBucketName(bucket))}
          </span>
        </td>
        <td>
          <div class="alignment-label-cell">${escapeHtml(entry.label || "")}</div>
          <div class="alignment-path-cell">${escapeHtml(entry.json_path || "")}</div>
        </td>
      </tr>`;
    }).join("");
  }

  function renderAlignmentGroup(items, title) {
    const groups = groupAlignmentItemsByBucket(items);
    if (!groups.length) {
      return `<div class="empty">${escapeHtml(title)}: none.</div>`;
    }
    return `<div class="alignment-section">
      <h4>${escapeHtml(title)}</h4>
      <div class="alignment-group-table-wrap">
        <table class="alignment-group-table">
          <thead>
            <tr>
              <th>Term Type</th>
              <th>Matched Variable</th>
            </tr>
          </thead>
          <tbody>
            ${groups.map(([, entries]) => renderAlignmentRows(entries)).join("")}
          </tbody>
        </table>
      </div>
    </div>`;
  }

  function renderPhenoAlignmentDetail(payload) {
    const referenceId = payload.reference_id || "unknown";
    const targetId = payload.target_id || "unknown";
    const shared = Array.isArray(payload.shared) ? payload.shared : [];
    const referenceOnly = Array.isArray(payload.reference_only) ? payload.reference_only : [];
    const targetOnly = Array.isArray(payload.target_only) ? payload.target_only : [];
    phenoAlignmentDetailEl.innerHTML =
      `<div class="section-note">Reference <strong>${escapeHtml(referenceId)}</strong> compared to target <strong>${escapeHtml(targetId)}</strong>.</div>` +
      `<div class="alignment-summary">
        <span class="alignment-stat">Shared ${shared.length}</span>
        <span class="alignment-stat">Reference-only ${referenceOnly.length}</span>
        <span class="alignment-stat">Target-only ${targetOnly.length}</span>
      </div>` +
      renderAlignmentGroup(shared, "Matched Variables") +
      renderAlignmentGroup(referenceOnly, "Reference-Only Variables") +
      renderAlignmentGroup(targetOnly, "Target-Only Variables");
  }

  function renderPhenoExplainDetail(payload) {
    const matches = Array.isArray(payload.matches) ? payload.matches : [];
    if (!matches.length) {
      renderPhenoExplainPlaceholder("No explanation could be generated for this run.");
      return;
    }
    const targetId = payload.target_id || "unknown";
    const topN = String(payload.top_n || matches.length);
    const data = payload && payload.data ? payload.data : {};
    const isLlm = data.source === "llm" || payload.source === "lm_studio";
    const badges = [];
    const formatAiProviderGranularity = (value) => String(value || "").replace(/_/g, " ");
    if (isLlm && data.ai_provider_context_granularity && data.ai_provider_access) {
      let title = "";
      if (data.ai_provider_access === "blocked") {
        title = "AI providers are blocked for this dataset or workspace.";
      } else if (data.ai_provider_access === "safe_summary") {
        title = "AI providers may be used, but they only receive provider-safe structural summary context.";
      } else {
        title = `AI providers may receive up to detailed context and currently receive ${formatAiProviderGranularity(data.ai_provider_context_granularity)} context for this Pheno-Ranker explanation.`;
      }
      badges.push(renderProvenanceBadge(`AI providers: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}`, title, "provider"));
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
    const source = badges.join("");
    const llmReply = payload.llm_reply
      ? `<div class="query-section" style="margin-bottom:12px;"><h4>LLM answer</h4>${renderQueryReply(payload.llm_reply)}</div>`
      : "";
    const supportingMatchesHeading = isLlm
      ? `<div class="section-note" style="margin-bottom:12px;">Supporting evidence from the top ${escapeHtml(topN)} matches in <code>rank.txt</code>.</div>`
      : "";
    phenoExplainDetailEl.innerHTML =
      `<div class="pheno-explain-header">
        <div class="pheno-explain-title-row">
          <div class="pheno-explain-title-block">
            <strong>Target ${escapeHtml(targetId)}</strong>
            <span>${isLlm ? "Patient-level explanation with supporting match evidence" : `Top ${escapeHtml(topN)} matches from <code>rank.txt</code>`}</span>
          </div>
          <div class="pheno-explain-meta">${source}</div>
        </div>
      </div>` +
      llmReply +
      supportingMatchesHeading +
      `<div class="pheno-explain-match-grid">` +
      matches.map((match, index) => {
        const metrics = Object.entries(match.metrics || {})
          .filter(([, value]) => value !== "")
          .map(([key, value]) => `<span class="alignment-stat">${escapeHtml(key)} ${escapeHtml(String(value))}</span>`)
          .join("");
        const highlights = Array.isArray(match.metric_highlights) ? match.metric_highlights : [];
        const alignment = match.alignment || {};
        const shared = Array.isArray(alignment.top_shared_items) ? alignment.top_shared_items : [];
        const referenceOnly = Array.isArray(alignment.top_reference_only_items) ? alignment.top_reference_only_items : [];
        const targetOnly = Array.isArray(alignment.top_target_only_items) ? alignment.top_target_only_items : [];
        const renderLabelGroup = (title, items, toneClass) => {
          if (!items.length) {
            return "";
          }
          return `
            <div class="pheno-explain-group ${toneClass}">
              <div class="pheno-explain-group-title">${escapeHtml(title)}</div>
              <div class="pheno-explain-chip-wrap">
                ${items.map((item) => {
                  const bucket = item.bucket || "other";
                  const style = getPhenoBucketStyle(bucket);
                  return `<span class="alignment-bucket-pill pheno-explain-chip" style="--bucket-bg:${style.bg};--bucket-ink:${style.ink};">
                    <span class="alignment-swatch"></span>
                    ${escapeHtml(item.label || "")}
                  </span>`;
                }).join("")}
              </div>
            </div>
          `;
        };
        return `
          <div class="pheno-explain-match-card">
            <div class="pheno-explain-match-head">
              <div>
                <div class="pheno-explain-match-rank">Match ${index + 1}</div>
                <h4>${escapeHtml(match.reference_id || "Unknown match")}</h4>
              </div>
            </div>
            <div class="alignment-summary">${metrics || '<span class="alignment-stat">No numeric metrics detected</span>'}</div>
            ${highlights.length ? `<ul class="pheno-explain-highlight-list">${highlights.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>` : ""}
            <div class="pheno-explain-groups">
              ${renderLabelGroup("Shared variables", shared, "is-shared")}
              ${renderLabelGroup("Match-only variables", referenceOnly, "is-reference")}
              ${renderLabelGroup("Target-only variables", targetOnly, "is-target")}
            </div>
          </div>
        `;
      }).join("") +
      `</div>`;
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
    state.explainInFlight = true;
    updatePhenoExplainActions();
    phenoExplainDetailEl.innerHTML = renderActivityCard(
      "Explaining results",
      "Summarizing the top patient matches and alignment signals from rank.txt."
    );
    try {
      const response = await fetch(`/pheno-ranker/explain/${encodeURIComponent(state.runState.jobId)}?top_n=3`);
      if (!response.ok) {
        const error = await response.json();
        renderPhenoExplainPlaceholder(error.detail || "Unable to explain these results.");
        return;
      }
      const payload = await response.json();
      renderPhenoExplainDetail(payload);
    } catch (error) {
      renderPhenoExplainPlaceholder(error && error.message ? error.message : "Unable to explain these results.");
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
    state.explainLlmInFlight = true;
    updatePhenoExplainActions();
    phenoExplainDetailEl.innerHTML = renderActivityCard(
      "Explaining with LLM",
      "Reviewing the top matches and drafting a clinician-friendly interpretation."
    );
    try {
      const response = await fetch(`/pheno-ranker/explain-llm/${encodeURIComponent(state.runState.jobId)}?top_n=3`);
      if (!response.ok) {
        const error = await response.json();
        renderPhenoExplainPlaceholder(error.detail || "Unable to explain these results with LM Studio.");
        return;
      }
      const payload = await response.json();
      renderPhenoExplainDetail(payload);
    } catch (error) {
      renderPhenoExplainPlaceholder(error && error.message ? error.message : "Unable to explain these results with LM Studio.");
    } finally {
      state.explainLlmInFlight = false;
      updatePhenoExplainActions();
    }
  }

  async function loadPhenoAlignment(referenceId, targetId) {
    if (!state.runState || !state.runState.jobId || !state.runState.alignmentAvailable) {
      renderPhenoAlignmentPlaceholder("No alignment output is available for this run.");
      return;
    }
    const selectionKey = `${referenceId}::${targetId}`;
    state.selectedAlignmentKey = selectionKey;
    renderSortablePhenoTable();
    phenoAlignmentDetailEl.innerHTML = "<div class=\"empty\">Loading alignment details...</div>";
    try {
      const response = await fetch(`/pheno-ranker/alignment/${encodeURIComponent(state.runState.jobId)}?reference_id=${encodeURIComponent(referenceId)}&target_id=${encodeURIComponent(targetId)}`);
      if (!response.ok) {
        const error = await response.json();
        renderPhenoAlignmentPlaceholder(error.detail || "Alignment details are unavailable for this pair.");
        return;
      }
      const payload = await response.json();
      renderPhenoAlignmentDetail(payload);
    } catch (error) {
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
      phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
      return;
    }
    const { headers, rows, sortIndex, sortDirection, sourceName, interactive, referenceColumnIndex, targetColumnIndex } = state.tableState;
    const type = inferPhenoColumnType(rows, sortIndex);
    const sortedRows = rows.slice().sort((left, right) => comparePhenoCells(left[sortIndex], right[sortIndex], type, sortDirection));
    const note = interactive
      ? `${sourceName} loaded as TSV. Click a column header to sort. Click one result row to inspect matched variables for that pair.`
      : `${sourceName} loaded as TSV. Click a column header to sort.`;
    phenoOutputPreviewEl.innerHTML =
      `<div class="section-note">${escapeHtml(note)}</div>` +
      `<div class="pheno-output-table-wrap"><table class="pheno-output-table"><thead><tr>${
        headers.map((cell, index) => {
          const active = index === sortIndex;
          const arrow = active ? (sortDirection === "asc" ? " ▲" : " ▼") : "";
          return `<th><button type="button" class="pheno-sort-btn" data-pheno-sort-index="${index}" data-active="${active ? "true" : "false"}">${escapeHtml(cell)}${arrow}</button></th>`;
        }).join("")
      }</tr></thead><tbody>${
        sortedRows.map((row) => {
          const referenceId = interactive && referenceColumnIndex >= 0 ? row[referenceColumnIndex] : "";
          const targetId = interactive && targetColumnIndex >= 0 ? row[targetColumnIndex] : "";
          const selectionKey = `${referenceId}::${targetId}`;
          const isSelected = interactive && state.selectedAlignmentKey === selectionKey;
          const rowClass = interactive ? ` class="is-clickable${isSelected ? " is-selected" : ""}"` : "";
          const attrs = interactive
            ? ` data-pheno-reference-id="${escapeHtml(referenceId)}" data-pheno-target-id="${escapeHtml(targetId)}"`
            : "";
          return `<tr${rowClass}${attrs}>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`;
        }).join("")
      }</tbody></table></div>`;
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
      phenoOutputPreviewEl.innerHTML = '<div class="empty">No rank or matrix output file available for preview.</div>';
      return;
    }
    try {
      const response = await fetch(preferred.url);
      if (!response.ok) {
        state.tableState = null;
        updatePhenoResultActions();
        phenoOutputPreviewEl.innerHTML = '<div class="empty">Unable to load output preview.</div>';
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
        phenoOutputPreviewEl.innerHTML =
          '<div class="section-note">Matrix preview is intentionally limited. Use the file link or the plot outputs for full cohort inspection.</div>' +
          `<pre>${escapeHtml(previewLines)}</pre>`;
        return;
      }
      phenoOutputPreviewEl.innerHTML = `<pre>${escapeHtml(text)}</pre>`;
    } catch (error) {
      state.tableState = null;
      updatePhenoResultActions();
      phenoOutputPreviewEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : "Unable to load output preview.")}</div>`;
    }
  }

  async function renderPhenoPreviews(files, runOptions = {}) {
    const items = Array.isArray(files) ? files : [];
    const mdsPointsFile = items.find((file) => file.name === "mds_points.tsv");
    const matrixFile = items.find((file) => file.name === "matrix.txt");
    const graphFile = items.find((file) => file.name === "graph.json");
    state.selectedMdsRecordIds = [];
    state.selectedHeatmapRecordIds = [];
    state.selectedGraphRecordIds = [];
    if (!mdsPointsFile && !matrixFile && !graphFile) {
      phenoPreviewsEl.innerHTML = '<div class="empty">No interactive plot data were produced for this run. Expected matrix.txt, mds_points.tsv, and/or graph.json.</div>';
      return;
    }
    const interactiveCard = mdsPointsFile
      ? `<details class="pheno-preview-card pheno-preview-card-full pheno-preview-details" open><summary class="pheno-preview-summary"><strong>Interactive MDS</strong></summary><div class="pheno-preview-body"><div class="pheno-result-card-toolbar"><div class="pheno-actions pheno-actions-secondary"><button type="button" class="query-chip" data-pheno-plot-action="analysis" data-pheno-plot-kind="mds">Open selection in Analysis</button><button type="button" class="query-chip query-chip-deterministic" data-pheno-plot-action="save-cohort" data-pheno-plot-kind="mds">Save cohort</button><button type="button" class="query-chip" data-pheno-plot-action="copy" data-pheno-plot-kind="mds">Copy selected IDs</button></div></div><div id="phenoMdsCohortLegend" class="pheno-cohort-legend is-hidden"></div><div id="phenoMdsPlot" class="pheno-mds-plot"></div><div class="section-note" id="phenoMdsSelectionNote">Select points with box or lasso to reuse them in Analysis or save them as a cohort.</div></div></details>`
      : "";
    const heatmapCard = matrixFile
      ? `<details class="pheno-preview-card pheno-preview-card-full pheno-preview-details" open><summary class="pheno-preview-summary"><strong>Interactive Heatmap</strong></summary><div class="pheno-preview-body"><div id="phenoHeatmapPlot" class="pheno-mds-plot"></div><div class="section-note" id="phenoHeatmapSelectionNote">Use Plotly zoom, pan, and hover tools to inspect the cohort matrix.</div></div></details>`
      : "";
    const graphCard = graphFile
      ? `<details class="pheno-preview-card pheno-preview-card-full pheno-preview-details" open><summary class="pheno-preview-summary"><strong>Interactive Graph</strong></summary><div class="pheno-preview-body"><div class="pheno-result-card-toolbar"><div class="pheno-actions pheno-actions-secondary"><button type="button" class="query-chip" data-pheno-plot-action="analysis" data-pheno-plot-kind="graph">Open selection in Analysis</button><button type="button" class="query-chip query-chip-deterministic" data-pheno-plot-action="save-cohort" data-pheno-plot-kind="graph">Save cohort</button><button type="button" class="query-chip" data-pheno-plot-action="copy" data-pheno-plot-kind="graph">Copy selected IDs</button></div></div><div class="pheno-graph-controls"><label class="pheno-graph-threshold-label" for="phenoGraphThreshold"><span id="phenoGraphThresholdLabel">Displayed edges</span><input id="phenoGraphThreshold" type="range" min="0" max="0" step="1" value="0"></label><label class="pheno-graph-select-label" for="phenoGraphTopK"><span>Neighbors per node</span><select id="phenoGraphTopK"><option value="1">Top 1</option><option value="2">Top 2</option><option value="3">Top 3</option><option value="4">Top 4</option><option value="9999">All</option></select></label><label class="pheno-graph-select-label" for="phenoGraphEdgeLabels"><span>Edge values</span><select id="phenoGraphEdgeLabels"><option value="off">Off</option><option value="selected" selected>Selected</option><option value="visible">Visible</option></select></label><label class="pheno-graph-checkbox"><input id="phenoGraphLargestComponent" type="checkbox" checked> Largest component only</label><div id="phenoGraphThresholdMeta" class="section-note-inline">Loading graph filter…</div></div><div id="phenoGraphCohortLegend" class="pheno-cohort-legend is-hidden"></div><div id="phenoGraphPlot" class="pheno-mds-plot pheno-graph-plot"></div><div class="section-note" id="phenoGraphSelectionNote">Line width and opacity encode edge value. Click an edge to inspect it or switch Edge values to Visible.</div></div></details>`
      : "";
    phenoPreviewsEl.innerHTML = heatmapCard + interactiveCard + graphCard;
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

  async function renderInteractivePhenoMdsPlot(file) {
    const plotEl = document.getElementById("phenoMdsPlot");
    const noteEl = document.getElementById("phenoMdsSelectionNote");
    if (!plotEl) {
      return;
    }
    if (typeof window.Plotly === "undefined") {
      plotEl.innerHTML = '<div class="empty">Interactive Plotly view is unavailable in this browser.</div>';
      return;
    }
    try {
      const response = await fetch(file.url);
      if (!response.ok) {
        plotEl.innerHTML = '<div class="empty">Unable to load MDS coordinates.</div>';
        return;
      }
      const text = await response.text();
      const rows = parseTsvLines(text);
      if (!rows || rows.length < 2) {
        plotEl.innerHTML = '<div class="empty">No MDS coordinates were available for this run.</div>';
        return;
      }
      const header = rows[0];
      const recordIndex = header.indexOf("record_id");
      const patientIndex = header.indexOf("patient_id");
      const xIndex = header.indexOf("x");
      const yIndex = header.indexOf("y");
      if ([recordIndex, patientIndex, xIndex, yIndex].some((index) => index < 0)) {
        plotEl.innerHTML = '<div class="empty">MDS coordinate file is missing required columns.</div>';
        return;
      }
      const points = rows.slice(1).map((row) => ({
        record_id: String(row[recordIndex] || "").trim(),
        patient_id: String(row[patientIndex] || "").trim(),
        x: Number(row[xIndex]),
        y: Number(row[yIndex]),
      })).filter((item) => item.record_id && Number.isFinite(item.x) && Number.isFinite(item.y)).map((item) => ({
        ...item,
        cohort: getPhenoMdsCohortInfo(item.record_id),
      }));
      if (!points.length) {
        plotEl.innerHTML = '<div class="empty">No valid MDS coordinates were available for this run.</div>';
        return;
      }
      renderPhenoCohortLegend("phenoMdsCohortLegend", points.map((item) => item.record_id));
      const cohortGroups = new Map();
      points.forEach((item) => {
        if (!cohortGroups.has(item.cohort.key)) {
          cohortGroups.set(item.cohort.key, {
            label: item.cohort.label,
            color: item.cohort.color,
            points: [],
          });
        }
        cohortGroups.get(item.cohort.key).points.push(item);
      });
      const traces = Array.from(cohortGroups.values()).map((group) => ({
        type: "scattergl",
        mode: "markers+text",
        name: group.label,
        x: group.points.map((item) => item.x),
        y: group.points.map((item) => item.y),
        text: group.points.map((item) => item.record_id),
        customdata: group.points.map((item) => [item.record_id, item.patient_id, group.label]),
        textposition: "top center",
        textfont: {
          size: 12,
          color: "#0f172a",
        },
        hovertemplate: "<b>%{customdata[0]}</b><br>Patient %{customdata[1]}<br>%{customdata[2]}<br>x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
        marker: {
          size: 10,
          color: group.color,
          opacity: 0.88,
        },
        selected: {
          textfont: {
            color: "#991b1b",
            size: 13,
          },
          marker: {
            opacity: 1,
          },
        },
        unselected: {
          textfont: {
            color: "rgba(15, 23, 42, 0.28)",
          },
          marker: {
            opacity: 0.22,
          },
        },
      }));
      await window.Plotly.newPlot(plotEl, traces, {
        margin: { l: 40, r: 20, t: 10, b: 40 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(255,255,255,0.86)",
        dragmode: "lasso",
        showlegend: false,
        xaxis: { title: "MDS Coordinate 1", zeroline: false },
        yaxis: { title: "MDS Coordinate 2", zeroline: false },
      }, {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["select2d", "autoScale2d"],
      });
      const applySelectedPlotPoints = (selected) => {
        state.selectedMdsRecordIds = normalizePhenoSelectedRecordIds((Array.isArray(selected) ? selected : [])
          .map((point) => {
            if (Array.isArray(point.customdata) && point.customdata[0]) {
              return String(point.customdata[0]).trim();
            }
            if (typeof point.text === "string" && point.text.trim()) {
              return point.text.trim();
            }
            return "";
          }));
        if (noteEl) {
          noteEl.textContent = state.selectedMdsRecordIds.length
            ? `Selected ${state.selectedMdsRecordIds.length} MDS points.`
            : "Select points with box or lasso to reuse them in Analysis.";
        }
      };
      plotEl.on("plotly_selected", (event) => {
        applySelectedPlotPoints(Array.isArray(event && event.points) ? event.points : []);
      });
      plotEl.on("plotly_click", (event) => {
        applySelectedPlotPoints(Array.isArray(event && event.points) ? event.points : []);
      });
      plotEl.on("plotly_deselect", () => {
        state.selectedMdsRecordIds = [];
        if (noteEl) {
          noteEl.textContent = "Select points with box or lasso to reuse them in Analysis.";
        }
      });
    } catch (error) {
      plotEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : "Unable to render the MDS plot.")}</div>`;
    }
  }

  async function renderInteractivePhenoHeatmap(file) {
    const plotEl = document.getElementById("phenoHeatmapPlot");
    if (!plotEl) {
      return;
    }
    if (typeof window.Plotly === "undefined") {
      plotEl.innerHTML = '<div class="empty">Interactive Plotly heatmap is unavailable in this browser.</div>';
      return;
    }
    try {
      const response = await fetch(file.url);
      if (!response.ok) {
        plotEl.innerHTML = '<div class="empty">Unable to load the cohort matrix for the heatmap.</div>';
        return;
      }
      const text = await response.text();
      const rows = parseTsvLines(text);
      if (!rows || rows.length < 2) {
        plotEl.innerHTML = '<div class="empty">No matrix data were available for this heatmap.</div>';
        return;
      }
      const metric = getEffectivePhenoCohortMetric();
      const metricLabel = metric === "jaccard" ? "Jaccard similarity" : "Hamming dissimilarity";
      const header = rows[0];
      const xLabels = header.slice(1);
      const body = rows.slice(1);
      const yLabels = body.map((row) => row[0]);
      const zValues = body.map((row) => row.slice(1).map((value) => {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : null;
      }));
      await window.Plotly.newPlot(plotEl, [{
        type: "heatmap",
        x: xLabels,
        y: yLabels,
        z: zValues,
        colorscale: [
          [0.0, "#4575b4"],
          [0.5, "#ffffbf"],
          [1.0, "#d73027"],
        ],
        hoverongaps: false,
        hovertemplate: `<b>%{y}</b> vs <b>%{x}</b><br>${metricLabel} %{z:.4f}<extra></extra>`,
        colorbar: {
          title: metricLabel,
        },
      }], {
        margin: { l: 100, r: 20, t: 10, b: 90 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(255,255,255,0.86)",
        dragmode: "zoom",
        xaxis: {
          title: "Reference / comparison IDs",
          tickangle: -40,
          automargin: true,
        },
        yaxis: {
          title: "Reference / comparison IDs",
          autorange: "reversed",
          automargin: true,
        },
      }, {
        responsive: true,
        displaylogo: false,
      });
    } catch (error) {
      plotEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : "Unable to render the heatmap.")}</div>`;
    }
  }

  async function renderInteractivePhenoGraph(file, runOptions = {}) {
    const plotEl = document.getElementById("phenoGraphPlot");
    const noteEl = document.getElementById("phenoGraphSelectionNote");
    const thresholdEl = document.getElementById("phenoGraphThreshold");
    const thresholdLabelEl = document.getElementById("phenoGraphThresholdLabel");
    const thresholdMetaEl = document.getElementById("phenoGraphThresholdMeta");
    const topKEl = document.getElementById("phenoGraphTopK");
    const edgeLabelsEl = document.getElementById("phenoGraphEdgeLabels");
    const largestComponentEl = document.getElementById("phenoGraphLargestComponent");
    if (!plotEl) {
      return;
    }
    if (typeof window.cytoscape === "undefined") {
      plotEl.innerHTML = '<div class="empty">Interactive Cytoscape view is unavailable in this browser.</div>';
      return;
    }
    if (plotEl._cy && typeof plotEl._cy.destroy === "function") {
      plotEl._cy.destroy();
      plotEl._cy = null;
    }
    try {
      const response = await fetch(file.url);
      if (!response.ok) {
        plotEl.innerHTML = '<div class="empty">Unable to load the cohort graph.</div>';
        return;
      }
      const payload = await response.json();
      const elements = payload && typeof payload === "object" && payload.elements && typeof payload.elements === "object"
        ? payload.elements
        : {};
      const rawNodes = Array.isArray(elements.nodes) ? elements.nodes : [];
      const rawEdges = Array.isArray(elements.edges) ? elements.edges : [];
      if (!rawNodes.length) {
        plotEl.innerHTML = '<div class="empty">No graph nodes were produced for this run.</div>';
        return;
      }
      const nodeIds = rawNodes
        .map((node) => String(node && node.data && node.data.id ? node.data.id : "").trim())
        .filter(Boolean);
      renderPhenoCohortLegend("phenoGraphCohortLegend", nodeIds);
      const similarityMetric = getEffectivePhenoCohortMetric();
      const strongerIsHigher = similarityMetric !== "hamming";
      const metricLabel = strongerIsHigher ? "Jaccard similarity" : "Hamming dissimilarity";
      const defaultTopKNeighbors = nodeIds.length > 80 ? 1 : (nodeIds.length > 36 ? 2 : 3);
      const normalizedNodes = rawNodes.map((node) => {
        const id = String(node && node.data && node.data.id ? node.data.id : "").trim();
        const cohort = getPhenoMdsCohortInfo(id);
        return {
          data: {
            ...(node && node.data ? node.data : {}),
            id,
            label: id,
            cohort_label: cohort.label,
            cohort_color: cohort.color,
          },
        };
      });
      const graphMinWeight = Number(runOptions && runOptions.graph_min_weight !== undefined && runOptions.graph_min_weight !== null ? runOptions.graph_min_weight : NaN);
      const graphMaxWeight = Number(runOptions && runOptions.graph_max_weight !== undefined && runOptions.graph_max_weight !== null ? runOptions.graph_max_weight : NaN);
      const hasGraphMinWeight = Number.isFinite(graphMinWeight);
      const hasGraphMaxWeight = Number.isFinite(graphMaxWeight);
      const normalizedEdges = rawEdges.map((edge) => {
        const source = String(edge && edge.data && edge.data.source ? edge.data.source : "").trim();
        const target = String(edge && edge.data && edge.data.target ? edge.data.target : "").trim();
        const weightValue = Number(edge && edge.data && edge.data.weight ? edge.data.weight : NaN);
        const weight = Number.isFinite(weightValue) ? weightValue : 0;
        return {
          data: {
            ...(edge && edge.data ? edge.data : {}),
            source,
            target,
            weight,
          },
        };
      }).filter((edge) => {
        const weight = Number(edge && edge.data ? edge.data.weight : NaN);
        if (!Number.isFinite(weight)) {
          return false;
        }
        if (hasGraphMinWeight && weight < graphMinWeight) {
          return false;
        }
        if (hasGraphMaxWeight && weight > graphMaxWeight) {
          return false;
        }
        return true;
      });
      const edgeLookup = new Map();
      normalizedEdges.forEach((edge) => {
        const source = String(edge.data.source || "").trim();
        const target = String(edge.data.target || "").trim();
        if (!source || !target) {
          return;
        }
        const key = [source, target].sort().join("\u0000");
        edgeLookup.set(key, Number(edge.data.weight));
      });
      const uniqueSortedWeights = Array.from(new Set(normalizedEdges
        .map((edge) => Number(edge.data.weight))
        .filter((weight) => Number.isFinite(weight))))
        .sort((a, b) => strongerIsHigher ? b - a : a - b);
      const preferredEdgeBudget = Math.max(36, Math.min(140, Math.round(nodeIds.length * 1.5)));
      let defaultStrengthIndex = 0;
      if (uniqueSortedWeights.length) {
        if (strongerIsHigher) {
          defaultStrengthIndex = Math.max(0, Math.min(uniqueSortedWeights.length - 1, preferredEdgeBudget - 1));
        } else {
          const firstWeightAtOrAboveTwoIndex = uniqueSortedWeights.findIndex((weight) => weight >= 2);
          defaultStrengthIndex = firstWeightAtOrAboveTwoIndex <= 0
            ? 0
            : firstWeightAtOrAboveTwoIndex - 1;
          if (firstWeightAtOrAboveTwoIndex === -1) {
            defaultStrengthIndex = uniqueSortedWeights.length - 1;
          }
        }
      }
      const thresholdState = {
        cy: null,
        thresholdValue: uniqueSortedWeights[defaultStrengthIndex] ?? null,
      };

      const computeLargestComponentNodeIds = (nodes, edges) => {
        const adjacency = new Map();
        nodes.forEach((node) => {
          const id = String(node && node.data && node.data.id ? node.data.id : "").trim();
          if (id && !adjacency.has(id)) {
            adjacency.set(id, new Set());
          }
        });
        edges.forEach((edge) => {
          const source = String(edge && edge.data && edge.data.source ? edge.data.source : "").trim();
          const target = String(edge && edge.data && edge.data.target ? edge.data.target : "").trim();
          if (!source || !target) {
            return;
          }
          if (!adjacency.has(source)) {
            adjacency.set(source, new Set());
          }
          if (!adjacency.has(target)) {
            adjacency.set(target, new Set());
          }
          adjacency.get(source).add(target);
          adjacency.get(target).add(source);
        });
        const visited = new Set();
        let largest = [];
        adjacency.forEach((_neighbors, nodeId) => {
          if (visited.has(nodeId)) {
            return;
          }
          const queue = [nodeId];
          const component = [];
          visited.add(nodeId);
          while (queue.length) {
            const current = queue.shift();
            component.push(current);
            const neighbors = adjacency.get(current) || new Set();
            neighbors.forEach((neighbor) => {
              if (!visited.has(neighbor)) {
                visited.add(neighbor);
                queue.push(neighbor);
              }
            });
          }
          if (component.length > largest.length) {
            largest = component;
          }
        });
        return new Set(largest);
      };

      const qualifiesEdge = (edge, thresholdValue) => {
        const weight = Number(edge && edge.data ? edge.data.weight : NaN);
        if (!Number.isFinite(weight)) {
          return false;
        }
        if (thresholdValue === null || thresholdValue === undefined) {
          return true;
        }
        return strongerIsHigher ? weight >= thresholdValue : weight <= thresholdValue;
      };

      const buildEdgeVisual = (weight) => {
        const numericWeight = Number(weight);
        const finiteWeights = uniqueSortedWeights.filter((value) => Number.isFinite(Number(value))).map((value) => Number(value));
        const minWeight = finiteWeights.length ? Math.min(...finiteWeights) : numericWeight;
        const maxWeight = finiteWeights.length ? Math.max(...finiteWeights) : numericWeight;
        let normalizedStrength = 0.7;
        if (Number.isFinite(numericWeight) && Number.isFinite(minWeight) && Number.isFinite(maxWeight) && maxWeight !== minWeight) {
          normalizedStrength = strongerIsHigher
            ? (numericWeight - minWeight) / (maxWeight - minWeight)
            : (maxWeight - numericWeight) / (maxWeight - minWeight);
        }
        normalizedStrength = Math.max(0, Math.min(1, normalizedStrength));
        const perfectMatch = strongerIsHigher
          ? Math.abs(numericWeight - 1) < 0.000001
          : Math.abs(numericWeight) < 0.000001;
        return {
          width: 1 + (normalizedStrength * 8),
          opacity: 0.22 + (normalizedStrength * 0.72),
          color: perfectMatch ? "#020617" : "#94a3b8",
        };
      };
      const formatGraphWeight = (weight) => {
        const numericWeight = Number(weight);
        if (!Number.isFinite(numericWeight)) {
          return "n/a";
        }
        return strongerIsHigher ? numericWeight.toFixed(3) : String(Math.round(numericWeight));
      };
      const describeGraphEdge = (edge) => {
        const source = String(edge && edge.data ? edge.data("source") || "" : "").trim();
        const target = String(edge && edge.data ? edge.data("target") || "" : "").trim();
        const weight = Number(edge && edge.data ? edge.data("weight") : NaN);
        if (!source || !target || !Number.isFinite(weight)) {
          return "Selected edge has no available weight.";
        }
        return `Selected edge ${source} to ${target}. ${metricLabel} = ${formatGraphWeight(weight)}.`;
      };
      const currentEdgeLabelMode = () => {
        const mode = String(edgeLabelsEl && edgeLabelsEl.value ? edgeLabelsEl.value : "selected").trim().toLowerCase();
        return ["off", "selected", "visible"].includes(mode) ? mode : "selected";
      };
      const syncEdgeLabels = (cy) => {
        const mode = currentEdgeLabelMode();
        cy.edges().forEach((edge) => {
          const shouldShow = mode === "visible" || (mode === "selected" && edge.selected());
          edge.data("value_label", shouldShow ? formatGraphWeight(edge.data("weight")) : "");
        });
      };

      const syncSelectedNodes = (cy) => {
        const selectedNodes = cy.$("node:selected").toArray();
        const rawSelectedNodeIds = selectedNodes.map((node) => String(node.id() || "").trim()).filter(Boolean);
        state.selectedGraphRecordIds = normalizePhenoSelectedRecordIds(rawSelectedNodeIds);
        if (noteEl) {
          if (rawSelectedNodeIds.length === 2) {
            const [leftId, rightId] = rawSelectedNodeIds;
            const visibleEdge = selectedNodes[0].edgesWith(selectedNodes[1]).toArray()[0] || null;
            const visibleWeight = visibleEdge ? Number(visibleEdge.data("weight")) : NaN;
            const edgeKey = [leftId, rightId].sort().join("\u0000");
            const value = Number.isFinite(visibleWeight) ? visibleWeight : edgeLookup.get(edgeKey);
            if (Number.isFinite(value)) {
              noteEl.textContent = `Selected ${leftId} and ${rightId}. ${metricLabel} = ${Number(value).toFixed(3)}.`;
            } else {
              noteEl.textContent = `Selected ${leftId} and ${rightId}. No direct edge is currently available for this pair.`;
            }
          } else if (rawSelectedNodeIds.length) {
            noteEl.textContent = `Selected ${rawSelectedNodeIds.length} graph nodes.`;
          } else {
            noteEl.textContent = "Click an edge to inspect its value. Click or box-select graph nodes to reuse them in Analysis or save them as a cohort.";
          }
        }
      };

      const renderThresholdMeta = (edgeCount, thresholdValue) => {
        if (!thresholdLabelEl || !thresholdMetaEl) {
          return;
        }
        if (!Number.isFinite(thresholdValue)) {
          thresholdLabelEl.textContent = "Displayed edges";
          thresholdMetaEl.textContent = `${edgeCount} strongest edges shown.`;
          return;
        }
        const formatted = Number(thresholdValue).toFixed(3);
        if (strongerIsHigher) {
          thresholdLabelEl.textContent = "Minimum similarity";
          thresholdMetaEl.textContent = `${edgeCount} of ${normalizedEdges.length} edges shown at similarity >= ${formatted}.`;
        } else {
          thresholdLabelEl.textContent = "Maximum dissimilarity";
          thresholdMetaEl.textContent = `${edgeCount} of ${normalizedEdges.length} edges shown at dissimilarity <= ${formatted}.`;
        }
        const bounds = [];
        if (hasGraphMinWeight) {
          bounds.push(`min ${graphMinWeight.toFixed(3)}`);
        }
        if (hasGraphMaxWeight) {
          bounds.push(`max ${graphMaxWeight.toFixed(3)}`);
        }
        if (bounds.length) {
          thresholdMetaEl.textContent += ` Export cutoff: ${bounds.join(", ")}.`;
        }
      };

      const drawGraph = (thresholdValue) => {
        if (thresholdState.cy && typeof thresholdState.cy.destroy === "function") {
          thresholdState.cy.destroy();
        }
        const thresholdFilteredEdges = normalizedEdges.filter((edge) => qualifiesEdge(edge, thresholdValue));
        const incidentByNode = new Map();
        thresholdFilteredEdges.forEach((edge, index) => {
          const source = String(edge.data.source || "").trim();
          const target = String(edge.data.target || "").trim();
          if (!source || !target) {
            return;
          }
          if (!incidentByNode.has(source)) {
            incidentByNode.set(source, []);
          }
          if (!incidentByNode.has(target)) {
            incidentByNode.set(target, []);
          }
          incidentByNode.get(source).push({ edge, index });
          incidentByNode.get(target).push({ edge, index });
        });
        const currentTopK = Math.max(1, Number(topKEl && topKEl.value ? topKEl.value : defaultTopKNeighbors));
        const retainedEdgeIndexes = new Set();
        incidentByNode.forEach((items) => {
          items
            .slice()
            .sort((left, right) => {
              const leftWeight = Number(left.edge.data.weight);
              const rightWeight = Number(right.edge.data.weight);
              return strongerIsHigher ? rightWeight - leftWeight : leftWeight - rightWeight;
            })
            .slice(0, currentTopK)
            .forEach((item) => retainedEdgeIndexes.add(item.index));
        });
        let filteredEdges = thresholdFilteredEdges
          .filter((_edge, index) => retainedEdgeIndexes.has(index))
          .map((edge) => {
            const visual = buildEdgeVisual(edge.data.weight);
            return {
              data: {
                ...edge.data,
                width: visual.width,
                opacity: visual.opacity,
                color: visual.color,
                value_label: "",
              },
            };
          });
        const currentLargestComponentOnly = Boolean(largestComponentEl && largestComponentEl.checked);
        if (currentLargestComponentOnly && filteredEdges.length) {
          const largestNodeIds = computeLargestComponentNodeIds(normalizedNodes, filteredEdges);
          filteredEdges = filteredEdges.filter((edge) => {
            const source = String(edge.data.source || "").trim();
            const target = String(edge.data.target || "").trim();
            return largestNodeIds.has(source) && largestNodeIds.has(target);
          });
        }
        const visibleNodeIds = new Set();
        filteredEdges.forEach((edge) => {
          visibleNodeIds.add(String(edge.data.source || "").trim());
          visibleNodeIds.add(String(edge.data.target || "").trim());
        });
        const filteredNodes = visibleNodeIds.size
          ? normalizedNodes.filter((node) => visibleNodeIds.has(String(node.data.id || "").trim()))
          : normalizedNodes;
        const cy = window.cytoscape({
          container: plotEl,
          elements: [...filteredNodes, ...filteredEdges],
          layout: {
            name: "cose",
            animate: false,
            fit: true,
            padding: 28,
            nodeRepulsion: 5000,
            idealEdgeLength: 70,
            edgeElasticity: 80,
          },
          boxSelectionEnabled: true,
          selectionType: "additive",
          style: [
            {
              selector: "node",
              style: {
                "background-color": "data(cohort_color)",
                label: "data(label)",
                color: "#0f172a",
                "font-size": 10,
                "text-wrap": "wrap",
                "text-max-width": 96,
                "text-valign": "bottom",
                "text-halign": "center",
                "text-margin-y": 8,
                "border-width": 1.5,
                "border-color": "#ffffff",
                width: 18,
                height: 18,
              },
            },
            {
              selector: "edge",
              style: {
                width: "data(width)",
                "line-color": "data(color)",
                opacity: "data(opacity)",
                "curve-style": "bezier",
                label: "data(value_label)",
                color: "#0f172a",
                "font-size": 9,
                "text-background-color": "#ffffff",
                "text-background-opacity": 0.86,
                "text-background-padding": 2,
                "text-rotation": "autorotate",
                "text-margin-y": -4,
              },
            },
            {
              selector: "edge:selected",
              style: {
                "line-color": "#0f766e",
                opacity: 0.92,
                "overlay-color": "#99f6e4",
                "overlay-opacity": 0.18,
              },
            },
            {
              selector: ":selected",
              style: {
                "border-color": "#991b1b",
                "border-width": 3,
                "overlay-color": "#fca5a5",
                "overlay-opacity": 0.12,
              },
            },
          ],
        });
        thresholdState.cy = cy;
        plotEl._cy = cy;
        cy.on("select unselect", "node", () => syncSelectedNodes(cy));
        cy.on("tap", "edge", (event) => {
          const edge = event && event.target ? event.target : null;
          if (edge && typeof edge.select === "function") {
            cy.$("edge:selected").unselect();
            edge.select();
            syncEdgeLabels(cy);
          }
          if (noteEl) {
            noteEl.textContent = describeGraphEdge(edge);
          }
        });
        syncSelectedNodes(cy);
        syncEdgeLabels(cy);
        renderThresholdMeta(filteredEdges.length, thresholdValue);
        if (thresholdMetaEl) {
          const parts = [thresholdMetaEl.textContent];
          parts.push(currentTopK >= 9999 ? "Showing all neighbors per node." : `Top ${currentTopK} neighbors per node.`);
          if (currentLargestComponentOnly) {
            parts.push("Largest component only.");
          }
          thresholdMetaEl.textContent = parts.filter(Boolean).join(" ");
        }
      };

      if (thresholdEl && uniqueSortedWeights.length) {
        thresholdEl.min = "0";
        thresholdEl.max = String(uniqueSortedWeights.length - 1);
        thresholdEl.step = "1";
        thresholdEl.value = String(defaultStrengthIndex);
        thresholdEl.addEventListener("input", () => {
          const index = Math.max(0, Math.min(uniqueSortedWeights.length - 1, Number(thresholdEl.value || 0)));
          thresholdState.thresholdValue = uniqueSortedWeights[index];
          drawGraph(thresholdState.thresholdValue);
        });
      } else if (thresholdEl) {
        thresholdEl.disabled = true;
      }
      if (topKEl) {
        topKEl.value = String(defaultTopKNeighbors);
        topKEl.addEventListener("change", () => {
          drawGraph(thresholdState.thresholdValue);
        });
      }
      if (edgeLabelsEl) {
        edgeLabelsEl.value = "selected";
        edgeLabelsEl.addEventListener("change", () => {
          if (thresholdState.cy) {
            syncEdgeLabels(thresholdState.cy);
          }
        });
      }
      if (largestComponentEl) {
        largestComponentEl.checked = true;
        largestComponentEl.addEventListener("change", () => {
          drawGraph(thresholdState.thresholdValue);
        });
      }
      drawGraph(thresholdState.thresholdValue);
    } catch (error) {
      plotEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : "Unable to render the graph.")}</div>`;
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
        : (kind === "graph" ? "Select graph nodes first." : "Select cohort points in the MDS plot first.");
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
          : `Copied ${selectedIds.length} selected cohort record IDs from the MDS plot.`);
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
        : (kind === "graph" ? "Select graph nodes first." : "Select cohort points in the MDS plot first.");
      return;
    }
    analysisSelectedPatientIdsEl.value = selectedIds.join(",");
    if (!analysisPromptEl.value.trim()) {
      analysisPromptEl.value = kind === "heatmap"
        ? "Summarize the main clinical patterns in the selected heatmap subgroup and tell me what stands out."
        : (kind === "graph"
          ? "Summarize the main clinical patterns in the selected graph subgroup and tell me what stands out."
          : "Summarize the main clinical patterns in the selected MDS subgroup and tell me what stands out.");
    }
    renderAnalysisScopeSummary();
    setActiveTab("analysis");
    syncCurrentAnalysisSessionFromUi({ render: true });
    analysisStatusEl.className = "query-status";
    analysisStatusEl.textContent = kind === "heatmap"
      ? `Loaded ${selectedIds.length} sample IDs from the selected heatmap subgroup into Analysis.`
      : (kind === "graph"
        ? `Loaded ${selectedIds.length} sample IDs from the selected graph subgroup into Analysis.`
        : `Loaded ${selectedIds.length} sample IDs from the selected MDS subgroup into Analysis.`);
  }

  async function saveSelectedPhenoPlotIdsAsCohort(kind, triggerButton) {
    const selectedIds = normalizePhenoSelectedRecordIds(getPhenoPlotSelection(kind));
    if (!selectedIds.length) {
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = kind === "heatmap"
        ? "Select heatmap cells first."
        : (kind === "graph" ? "Select graph nodes first." : "Select cohort points in the MDS plot first.");
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
        : (kind === "graph" ? "Selected subgroup from Pheno-Ranker graph" : "Selected subgroup from Pheno-Ranker MDS"),
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
    phenoPatientIdEl.value = String(payload.patient_id || "").trim();
    phenoSelectedPatientIdsEl.value = String(payload.selected_patient_ids || "").trim();
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
    renderPhenoFiles(source.files);
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
    if (source.mode === "patient" && state.runState.alignmentAvailable) {
      renderPhenoAlignmentPlaceholder("Click one row in rank.txt to inspect matched variables for that pair.");
    } else {
      renderPhenoAlignmentPlaceholder("Alignment details are available only for patient-mode runs.");
    }
    renderPhenoExplainPlaceholder("Use Explain results to summarize the top patient matches from rank.txt.");
    renderPhenoBackgroundJobBanner();
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
    phenoFilesEl.innerHTML = '<div class="empty">Loading output files...</div>';
    phenoOutputPreviewEl.innerHTML = renderActivityCard("Loading run", "Restoring the stored Pheno-Ranker result into this tab.");
    renderPhenoAlignmentPlaceholder("Loading alignment details...");
    phenoLogsEl.textContent = "Loading stored logs...";
    phenoPreviewsEl.innerHTML = renderActivityCard("Loading plots", "Restoring interactive plots and output files from the completed background run.");
    await applyPhenoRunPayload(result, { statusPrefix: "Loaded" });
  }

  async function runPhenoRanker(usePromptPlanner = true) {
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
        phenoPatientIdEl.value = scopeIds[0];
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

    state.inFlight = true;
    updatePhenoRunAvailability();
    phenoStatusEl.className = "pheno-status loading";
    phenoStatusEl.textContent = "Running Pheno-Ranker...";
    setPhenoResultWorkspaceVisible(true);
    phenoCommandEl.textContent = "Preparing command...";
    phenoFilesEl.innerHTML = '<div class="empty">Waiting for Pheno-Ranker outputs.</div>';
    state.runState = null;
    updatePhenoExplainActions();
    state.selectedAlignmentKey = "";
    state.tableState = null;
    phenoOutputDetailsEl.open = phenoModeEl.value === "patient";
    phenoOutputPreviewEl.innerHTML = renderActivityCard("Preparing run", "Building the command and validating the selected scope.");
    renderPhenoAlignmentPlaceholder("Waiting for alignment details.");
    phenoLogsEl.textContent = "Waiting for logs...";
    phenoPreviewsEl.innerHTML = renderActivityCard("Preparing plots", "Waiting for interactive cohort plots and result files from the active run.");
    startPhenoRunProgressUpdates();
    await nextFrame();

    try {
      const response = await fetch("/pheno-ranker/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: phenoPromptEl.value.trim(),
          action: phenoActionEl.value,
          mode: phenoModeEl.value,
          data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
          patient_id: phenoPatientIdEl.value.trim(),
          selected_patient_ids: selectedSavedCohortIds.length ? "" : phenoSelectedPatientIdsEl.value.trim(),
          selected_saved_cohort_ids: selectedSavedCohortIds,
          include_terms: parsePhenoTermsInput(phenoIncludeTermsEl.value),
          exclude_terms: parsePhenoTermsInput(phenoExcludeTermsEl.value),
          similarity_metric_cohort: phenoSimilarityMetricEl.value,
          sort_by: phenoSortByEl.value,
          max_out: Number(phenoMaxOutEl.value || 10),
          align: phenoAlignEl.checked,
          render_heatmap: phenoRenderHeatmapEl.checked,
          render_mds: phenoRenderMdsEl.checked,
          render_graph: Boolean(phenoRenderGraphEl && phenoRenderGraphEl.checked),
          graph_min_weight: parseOptionalNumberInput(phenoGraphMinWeightEl),
          graph_max_weight: parseOptionalNumberInput(phenoGraphMaxWeightEl),
        }),
      });

      const payload = await response.json();
      stopPhenoRunProgressUpdates();
      if (!response.ok) {
        const detailObject = payload && typeof payload.detail === "object" ? payload.detail : null;
        const detail = detailObject ? JSON.stringify(detailObject, null, 2) : String((payload && payload.detail) || "Pheno-Ranker failed.");
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = "Pheno-Ranker failed. See Logs for details.";
        phenoCommandEl.textContent = detailObject && detailObject.command ? detailObject.command : "Command failed before completion.";
        phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
        phenoLogsEl.textContent = detail;
        phenoFilesEl.innerHTML = '<div class="empty">No output files available.</div>';
        phenoPreviewsEl.innerHTML = '<div class="empty">No interactive plots available for this run.</div>';
        return;
      }

      if (payload && payload.data && payload.data.execution === "queued") {
        seedQueuedPhenoBackgroundJob(payload);
        state.runState = null;
        updatePhenoExplainActions();
        setPhenoResultWorkspaceVisible(false);
        phenoCommandEl.textContent = "Queued as a background Pheno-Ranker run.";
        phenoOutputPreviewEl.innerHTML = '<div class="empty">Background run submitted. Open Jobs to monitor progress and load the completed result.</div>';
        phenoLogsEl.textContent = "Waiting for background run logs...";
        phenoFilesEl.innerHTML = '<div class="empty">No output files available until the background run completes.</div>';
        phenoPreviewsEl.innerHTML = '<div class="empty">Interactive plots will appear after the background run completes.</div>';
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = payload.reply || "Background Pheno-Ranker run submitted.";
        updatePhenoRunAvailability();
        if (typeof handlePhenoJobSubmission === "function") {
          handlePhenoJobSubmission(payload);
        }
        renderPhenoBackgroundJobBanner();
        return;
      }

      await applyPhenoRunPayload(payload);
    } catch (error) {
      stopPhenoRunProgressUpdates();
      phenoStatusEl.className = "pheno-status";
      phenoStatusEl.textContent = "Network error while running Pheno-Ranker. See Logs for details.";
      phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
      phenoFilesEl.innerHTML = '<div class="empty">No output files available.</div>';
      phenoPreviewsEl.innerHTML = '<div class="empty">No interactive plots available for this run.</div>';
      phenoLogsEl.textContent = error && error.message ? error.message : "Unexpected request failure.";
    } finally {
      stopPhenoRunProgressUpdates();
      state.inFlight = false;
      updatePhenoRunAvailability();
      updatePhenoExplainActions();
    }
  }

  async function loadPhenoRankerPatientIds() {
    try {
      const dataDir = encodeURIComponent((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim());
      const response = await fetch(`/pheno-ranker/patient-ids?data_dir=${dataDir}`);
      if (!response.ok) {
        state.rankerPatientIds = [];
        state.referenceFiles = [];
        phenoReferenceFilesSummaryEl.innerHTML = '<span class="query-chip badge">Active workspace files</span> <span class="section-note-inline">Unavailable</span>';
        onPatientIdsLoaded([]);
        onReferenceFilesLoaded([]);
        return;
      }
      const payload = await response.json();
      state.rankerPatientIds = Array.isArray(payload.patient_ids) ? payload.patient_ids.filter(Boolean) : [];
      state.rankerRecordIds = Array.isArray(payload.record_ids) ? payload.record_ids.filter(Boolean) : [];
      state.referenceFiles = Array.isArray(payload.reference_files) ? payload.reference_files.filter(Boolean) : [];
      onPatientIdsLoaded(state.rankerPatientIds);
      onReferenceFilesLoaded(state.referenceFiles);
      if (!state.referenceFiles.length) {
        phenoReferenceFilesSummaryEl.innerHTML = '<span class="query-chip badge">Active workspace files</span> <span class="section-note-inline">None</span>';
      } else {
        const labels = state.referenceFiles.map((item) => item.split("/").pop());
        phenoReferenceFilesSummaryEl.innerHTML = `
          <div class="file-label-row">
            <span class="query-chip badge">Active workspace files (${labels.length})</span>
            ${labels.map((label) => `<span class="query-chip query-chip-deterministic badge">${escapeHtml(label)}</span>`).join("")}
          </div>
        `;
      }
    } catch (_error) {
      state.rankerPatientIds = [];
      state.referenceFiles = [];
      phenoReferenceFilesSummaryEl.innerHTML = '<span class="query-chip badge">Active workspace files</span> <span class="section-note-inline">Unavailable</span>';
      onPatientIdsLoaded([]);
      onReferenceFilesLoaded([]);
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
      : (button.dataset.phenoPlotKind === "graph" ? "graph" : "mds");
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
    updatePhenoMode,
    updatePhenoGraphOptions,
    renderSelectedPatientIdsSummary,
    loadPhenoRankerPatientIds,
    updatePhenoExplainActions,
    updatePhenoResultActions,
    updatePhenoRunAvailability,
    setPhenoResultWorkspaceVisible,
    resetPhenoRunWorkspace,
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
    handleOutputPreviewClick,
    handlePreviewsClick,
    renderPhenoAlignmentPlaceholder,
    renderPhenoExplainPlaceholder,
    renderPhenoBackgroundJobBanner,
    loadCompletedPhenoJob,
  };
}
