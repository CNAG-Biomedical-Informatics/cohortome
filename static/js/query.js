import { downloadFile, downloadStatus, activityState } from "./shared.js";
import {createQueryThreadView, createQueryActionsView, createReplyView, createQueryShortcutsView} from './react/ui.js';
import { openClinicalSummary } from './clinical_summary.js';

export function createQueryUi(ctx) {
  const { refs, helpers, callbacks, state } = ctx;
  const {
    queryReplyEl,
    queryStatusEl,
    queryReasonEl,
    queryActionsEl,
    queryFollowupsEl,
    queryDataEl,
    queryDetailsEl,
    queryThreadEl,
    questionEl,
    askBtnEl,
    queryTabEl,
    queryExamplesEl,
    queryStarterPanelEl,
    queryStarterTopHostEl,
    queryStarterHostEl,
    queryComposerExamplesBtnEl,
    queryDiseaseTopChipsEl,
    queryDiseaseStatusEl,
    queryContextWorkspaceBtnEl,
    queryContextGeneralBtnEl,
    queryComposerTitleEl,
    queryThreadModeLabelEl,
  } = refs;
  const { fallbackCopyText } = helpers;
  const {
    renderQueryExecutionMode,
    startQueryProgressUpdates,
    stopQueryProgressUpdates,
    nextFrame,
    saveLatestQueryAsCohort,
    sendPatientIdsToPhenoRanker,
    sendPatientIdsToAnalysis,
    sendPromptToAnalysis,
    currentPatientsProvider,
    phenoRankerPatientIdsProvider,
    setLatestQueryState,
    setLatestScopedContext,
  } = callbacks;
  const QUERY_RESULT_PAGE_SIZE = 50;
  const threadView = queryThreadEl ? createQueryThreadView(queryThreadEl) : null;
  const actionsView = queryActionsEl ? createQueryActionsView(queryActionsEl) : null;
  const replyView=createReplyView(queryReplyEl);
  const reasonView=createReplyView(queryReasonEl);
  const diseaseShortcutsView=createQueryShortcutsView(queryDiseaseTopChipsEl);
  let diseaseOptions = [];
  let queryPromptLibraryOpen = true;

  function isGeneralQuestionMode() {
    return state.queryContextMode === "general";
  }

  function historyForContext(mode) {
    return (Array.isArray(state.queryHistory) ? state.queryHistory : [])
      .filter((turn) => mode === "general" ? turn.context_mode === "general" : turn.context_mode !== "general")
      .slice(-6)
      .map((turn) => ({ role: turn.role, content: turn.content }));
  }

  function queryResultPage(payload) {
    const data = payload && payload.data && typeof payload.data === "object" ? payload.data : {};
    const page = data.result_page && typeof data.result_page === "object" ? data.result_page : {};
    const resultHandle = String(page.result_handle || data.result_handle || "").trim();
    const patientIds = Array.isArray(page.patient_ids)
      ? page.patient_ids.slice(0, QUERY_RESULT_PAGE_SIZE)
      : Array.isArray(data.patient_ids)
        ? data.patient_ids.slice(0, QUERY_RESULT_PAGE_SIZE)
        : [];
    const sampleIds = Array.isArray(page.sample_ids)
      ? page.sample_ids.slice(0, QUERY_RESULT_PAGE_SIZE)
      : Array.isArray(data.sample_ids)
        ? data.sample_ids.slice(0, QUERY_RESULT_PAGE_SIZE)
        : [];
    const rows = Array.isArray(page.rows)
      ? page.rows.slice(0, QUERY_RESULT_PAGE_SIZE)
      : Array.isArray(data.patients)
        ? data.patients.slice(0, QUERY_RESULT_PAGE_SIZE)
        : [];
    const visibleCount = Math.max(rows.length, patientIds.length, sampleIds.length);
    const totalCount = Math.max(0, Number(page.total_count ?? data.total_count ?? data.patient_count ?? data.sample_count ?? visibleCount));
    const returnedCount = Math.min(
      QUERY_RESULT_PAGE_SIZE,
      Math.max(0, Number(page.returned_count ?? data.returned_count ?? visibleCount)),
    );
    return {
      resultHandle,
      totalCount,
      returnedCount,
      pageSize: Math.min(QUERY_RESULT_PAGE_SIZE, Math.max(1, Number(page.page_size ?? data.page_size ?? QUERY_RESULT_PAGE_SIZE))),
      hasMore: Boolean(page.has_more ?? data.has_more),
      nextCursor: String(page.next_cursor || data.next_cursor || "").trim(),
      expiresAt: String(page.expires_at || data.expires_at || "").trim(),
      patientIds,
      sampleIds,
      rows,
    };
  }

  function boundQueryPayload(payload) {
    if (!payload || typeof payload !== "object") return payload;
    const data = payload.data && typeof payload.data === "object" ? payload.data : {};
    const page = queryResultPage(payload);
    if (Array.isArray(data.patient_ids)) data.patient_ids = data.patient_ids.slice(0, QUERY_RESULT_PAGE_SIZE);
    if (Array.isArray(data.sample_ids)) data.sample_ids = data.sample_ids.slice(0, QUERY_RESULT_PAGE_SIZE);
    if (Array.isArray(data.patients)) data.patients = data.patients.slice(0, QUERY_RESULT_PAGE_SIZE);
    if (data.result_page && typeof data.result_page === "object") {
      data.result_page = {
        ...data.result_page,
        patient_ids: page.patientIds,
        sample_ids: page.sampleIds,
        rows: page.rows,
      };
    }
    const context = payload.action_context && typeof payload.action_context === "object" ? payload.action_context : {};
    if (page.resultHandle) {
      payload.action_context = {
        ...context,
        result_handle: page.resultHandle,
        patient_ids: [],
        record_ids: [],
      };
    } else {
      if (Array.isArray(context.patient_ids)) context.patient_ids = context.patient_ids.slice(0, QUERY_RESULT_PAGE_SIZE);
      if (Array.isArray(context.record_ids)) context.record_ids = context.record_ids.slice(0, QUERY_RESULT_PAGE_SIZE);
      payload.action_context = context;
    }
    payload.data = data;
    if (page.resultHandle) payload.reply = queryDisplayReply(payload);
    return payload;
  }

  function compactQueryHistoryReply(payload) {
    if (!payload || typeof payload !== "object") return "Query completed.";
    if (payload.intent === "general_llm") return String(payload.reply || "").trim();
    const page = queryResultPage(payload);
    const count = page.totalCount || Number(payload.data && (payload.data.patient_count ?? payload.data.sample_count) || 0);
    if (count || page.resultHandle) {
      const context = payload.action_context && typeof payload.action_context === "object" ? payload.action_context : {};
      const sampleLevel = String(context.id_type || "patient") === "sample";
      const unit = sampleLevel ? (count === 1 ? "sample" : "samples") : (count === 1 ? "patient" : "patients");
      return `Query result: ${count} ${unit} matched (${String(payload.intent || "workspace_query")}).`;
    }
    const reply = String(payload.reply || "Query completed.").trim();
    return reply.length > 360 ? `${reply.slice(0, 357)}...` : reply;
  }

  function queryDisplayReply(payload) {
    const page = queryResultPage(payload);
    const context = payload.action_context && typeof payload.action_context === "object" ? payload.action_context : {};
    const sampleLevel = String(context.id_type || "patient") === "sample";
    if (!page.resultHandle) {
      const inventoryIntent = payload && (payload.intent === "patient_inventory" || payload.intent === "sample_inventory");
      const hasStructuredIds = page.patientIds.length > 0 || page.sampleIds.length > 0 || page.rows.length > 0;
      if (inventoryIntent && hasStructuredIds) {
        const count = page.totalCount || Math.max(page.patientIds.length, page.sampleIds.length, page.rows.length);
        const unit = sampleLevel ? (count === 1 ? "sample" : "samples") : (count === 1 ? "patient" : "patients");
        return `Found ${count} ${unit}. The bounded result is shown below.`;
      }
      return payload && payload.reply !== undefined ? payload.reply : payload;
    }
    const unit = sampleLevel
      ? (page.totalCount === 1 ? "sample matches" : "samples match")
      : (page.totalCount === 1 ? "patient matches" : "patients match");
    return `${page.totalCount} ${unit} this query. Browse the result below in bounded pages.`;
  }

  function queryDetailsData(data) {
    if (!data || typeof data !== "object") return {};
    const safe = { ...data };
    delete safe.patient_ids;
    delete safe.sample_ids;
    delete safe.patients;
    if (safe.result_page && typeof safe.result_page === "object") {
      safe.result_page = { ...safe.result_page };
      delete safe.result_page.patient_ids;
      delete safe.result_page.sample_ids;
      delete safe.result_page.rows;
    }
    return safe;
  }

  function renderQueryContextMode() {
    const general = isGeneralQuestionMode();
    [[queryContextWorkspaceBtnEl, !general], [queryContextGeneralBtnEl, general]].forEach(([button, active]) => {
      if (!button) return;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (queryTabEl) queryTabEl.classList.toggle("query-tab-general-mode", general);
    if (queryComposerTitleEl) queryComposerTitleEl.textContent = hasQueryTurns() ? "Ask a follow-up" : general ? "Ask Model" : "Ask a question";
    if (queryThreadModeLabelEl) queryThreadModeLabelEl.textContent = general ? "General question" : "Workspace mode";
    if (questionEl) {
      questionEl.placeholder = general
        ? "Ask a general question without workspace context"
        : "Ask about the active workspace";
    }
    renderQueryStarterPrompts();
    renderQueryExecutionMode();
  }

  function setQueryContextMode(value) {
    if (state.queryInFlight) return;
    state.queryContextMode = value === "general" ? "general" : "workspace";
    if (isGeneralQuestionMode()) {
      state.queryExecutionMode = "auto";
      state.queryFollowMemoryEnabled = false;
      if (refs.queryDiseasePanelEl) refs.queryDiseasePanelEl.classList.add("is-hidden");
      if (refs.queryDiseaseBuilderBtnEl) refs.queryDiseaseBuilderBtnEl.classList.remove("is-active");
    }
    renderQueryContextMode();
    if (queryStatusEl) {
      queryStatusEl.className = "query-status is-hidden";
      queryStatusEl.textContent = "";
    }
    questionEl && questionEl.focus();
  }

  function hasQueryTurns() {
    return Array.isArray(state.queryTurns) && state.queryTurns.length > 0;
  }

  function renderQueryStarterPrompts() {
    if (!queryStarterPanelEl) {
      return;
    }
    const hasTurns = hasQueryTurns();
    const targetHost = hasTurns ? queryStarterHostEl : queryStarterTopHostEl;
    if (targetHost && queryStarterPanelEl.parentElement !== targetHost) {
      targetHost.appendChild(queryStarterPanelEl);
    }

    const visible = !isGeneralQuestionMode() && (!hasTurns || queryPromptLibraryOpen);
    queryStarterPanelEl.hidden = !visible;
    queryStarterPanelEl.classList.toggle("is-hidden", !visible);
    queryStarterPanelEl.classList.toggle("query-starter-panel-compact", hasTurns);

    if (queryStarterHostEl) {
      queryStarterHostEl.hidden = !hasTurns || !visible;
      queryStarterHostEl.classList.toggle("is-hidden", !hasTurns || !visible);
    }

    if (queryComposerExamplesBtnEl) {
      queryComposerExamplesBtnEl.hidden = !hasTurns || isGeneralQuestionMode();
      queryComposerExamplesBtnEl.classList.toggle("is-active", hasTurns && queryPromptLibraryOpen);
      queryComposerExamplesBtnEl.setAttribute("aria-expanded", hasTurns && queryPromptLibraryOpen ? "true" : "false");
      const labelEl = queryComposerExamplesBtnEl.querySelector("span:last-child");
      if (labelEl) {
        labelEl.textContent = queryPromptLibraryOpen ? "Hide prompts" : "Prompts";
      } else {
        queryComposerExamplesBtnEl.textContent = queryPromptLibraryOpen ? "Hide prompts" : "Prompts";
      }
    }
  }

  function setQueryPromptLibraryOpen(open, options = {}) {
    queryPromptLibraryOpen = Boolean(open);
    renderQueryStarterPrompts();
    if (options.scroll && queryPromptLibraryOpen && queryStarterPanelEl && !queryStarterPanelEl.hidden) {
      queryStarterPanelEl.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    }
  }

  function renderTopDiseaseChips() {
    if (!queryDiseaseTopChipsEl) return;
    const currentPrompt = String(questionEl && questionEl.value ? questionEl.value : "").toLowerCase();
    diseaseShortcutsView.render(diseaseOptions,currentPrompt);
  }

  async function loadDiseaseOptions() {
    if (!queryDiseaseTopChipsEl) return;
    try {
      const scopeId = String(refs.dataDirEl && refs.dataDirEl.dataset && refs.dataDirEl.dataset.scopeId ? refs.dataDirEl.dataset.scopeId : (refs.dataDirEl && refs.dataDirEl.value ? refs.dataDirEl.value.trim() : ""));
      const dataDir = encodeURIComponent(scopeId);
      const response = await fetch(`/cohorts/diseases?data_dir=${dataDir}`);
      if (!response.ok) throw new Error("Unable to load diseases.");
      const payload = await response.json();
      const diseases = Array.isArray(payload) ? payload : [];
      diseaseOptions = diseases;
      renderTopDiseaseChips();
      if (queryDiseaseStatusEl) {
        queryDiseaseStatusEl.textContent = diseases.length
          ? `Click a disease to preload a deterministic workspace query.`
          : "No diseases are available in the current dataset.";
      }
    } catch (_error) {
      diseaseOptions = [];
      renderTopDiseaseChips();
      if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = "Unable to load disease workspace shortcuts.";
    }
  }

  function preloadDiseaseCohort(disease) {
    const normalized = String(disease || "").trim();
    if (!normalized) return;
    state.queryContextMode = "workspace";
    questionEl.value = normalized === "Healthy Control"
      ? "Which subjects are Healthy Controls?"
      : `Which patients have ${disease}?`;
    state.queryExecutionMode = "auto";
    renderQueryExecutionMode();
    renderQueryContextMode();
    renderTopDiseaseChips();
    if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = `Prompt prepared for disease workspace ${normalized}. Press Ask to run.`;
    questionEl.focus();
  }

  function defaultQueryExecutionMode() {
    return state.userSettings && state.userSettings.query_default_mode === "planner_only" ? "planner_only" : "auto";
  }

  function queryReplyModel(payload,navigation={}) {
    const structured=payload && typeof payload==='object';
    return {text:structured ? queryDisplayReply(payload) : payload,
      table:structured ? {payload,page:queryResultPage(payload),patients:currentPatientsProvider() || [],navigation} : null};
  }

  function queryIntentPresentation(intent) {
    const value = String(intent || "unknown");
    const labels = {
      semantic_cohort_query: { label: "Workspace query", title: "A workspace-style query result returned by the app." },
      medication_cohort: { label: "Medication workspace query", title: "Deterministic workspace lookup based on treatment labels in the dataset." },
      disease_cohort: { label: "Disease workspace query", title: "Deterministic workspace lookup based on disease labels in the dataset." },
      explicit_patient_id_cohort: { label: "Selected patient cohort", title: "Deterministic cohort built directly from explicit patient IDs present in the workspace." },
      patient_filter_cohort: { label: "Patient filter query", title: "Deterministic workspace filtering across multiple include or exclude conditions." },
      patient_transition_cohort: { label: "Transition query", title: "Deterministic query over patients who changed from one term to another over time." },
      patient_started_after_cohort: { label: "Started-after query", title: "Deterministic temporal query over patients who started one term after another." },
      patient_temporal_order_cohort: { label: "Temporal order query", title: "Deterministic temporal query over the order of events in patient timelines." },
      patient_inventory: { label: "Patient inventory", title: "Deterministic listing of patients in the current cohort." },
      external_assay_inventory: { label: "Assay feature inventory", title: "A bounded feature inventory read from an approved external assay." },
      external_assay_summary: { label: "Assay summary", title: "Descriptive aggregate statistics computed locally from an approved external assay." },
      external_assay_comparison: { label: "Assay comparison", title: "A descriptive two-cohort comparison computed locally from an approved external assay." },
      general_llm: { label: "General LLM answer", title: "The selected model answered without receiving workspace or dataset context." },
      llm_fallback: { label: "LLM fallback answer", title: "LM Studio answered directly from the provided context because no deterministic route or semantic plan was used." },
      llm_unavailable: { label: "LLM unavailable", title: "LM Studio fallback is enabled, but no loaded model was available." },
      llm_error: { label: "LLM error", title: "LM Studio fallback was attempted but did not return a usable answer." },
      unsupported: { label: "Unsupported query", title: "The app could not map this prompt to a supported deterministic or LM-planned query path." },
      needs_clarification: { label: "Needs clarification", title: "The prompt is too vague to answer reliably, so the app is asking for a more specific query." },
    };
    return labels[value] || {
      label: value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()),
      title: `Internal query intent: ${value}`,
    };
  }

  function queryBadge(label, title, iconKind = '') {
    return {label, title, iconKind};
  }

  function formatAiProviderGranularity(value) {
    const label = String(value || "").replace(/_/g, " ");
    return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : "";
  }

  function getQueryProvenanceChips(payload) {
    const data = payload && payload.data ? payload.data : {};
    const intentInfo = queryIntentPresentation(payload && payload.intent ? payload.intent : "unknown");
    const plannedByLmStudio = data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio";
    const answeredByLmStudio = data.provider === "lm_studio";
    const aiProviderConsulted = plannedByLmStudio || answeredByLmStudio;
    const chips = [queryBadge(intentInfo.label, intentInfo.title, "summary")];
    if (payload && payload.intent === "general_llm") {
      chips.push(queryBadge(
        "No workspace context",
        "Only this prompt and recent General-question turns were sent to the selected model. No workspace or dataset context was supplied.",
        "no_context",
      ));
      if (data.model) chips.push(queryBadge(data.model, "Model used for this general answer.", "llm"));
      return chips;
    }
    const datasetNames = Array.isArray(data.dataset_names)
      ? data.dataset_names.map((item) => String(item || "").trim()).filter(Boolean)
      : String(data.dataset_name || "").trim()
        ? [String(data.dataset_name).trim()]
        : [];
    if (datasetNames.length) {
      chips.push(queryBadge(
        `Dataset: ${datasetNames.join(", ")}`,
        `This answer was computed from ${datasetNames.join(", ")}.`,
        "summary",
      ));
    }
    if (data.granularity_applied) {
      const requested = data.granularity_requested && data.granularity_requested !== data.granularity_applied
        ? ` Requested: ${data.granularity_requested}.`
        : "";
      chips.push(queryBadge(
        `Response detail: ${formatAiProviderGranularity(data.granularity_applied)}`,
        `Detail available in the COHORTome response: ${data.granularity_applied}. This is separate from the context sent to a model.${requested}`.trim(),
        "response",
      ));
    }
    if (aiProviderConsulted && data.ai_provider_context_granularity && data.ai_provider_access) {
      let title = "";
      if (data.ai_provider_access === "blocked") {
        title = "AI providers are blocked for this dataset or workspace.";
      } else if (data.ai_provider_access === "safe_summary") {
        title = "AI providers may be used, but they only receive provider-safe structural summary context.";
      } else {
        title = `AI providers may receive up to detailed context and currently receive ${formatAiProviderGranularity(data.ai_provider_context_granularity)} context.`;
      }
      chips.push(queryBadge(
        `Model context: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}`,
        title,
        "provider",
      ));
    }
    if (plannedByLmStudio) {
      chips.push(queryBadge("LLM-planned", "LM Studio translated the prompt into a constrained internal cohort plan.", "planner"));
      chips.push(queryBadge("Deterministic execution", "The app executed the planned query against local cohort data without using the model to produce the result.", "deterministic"));
      if (data.planner.model) chips.push(queryBadge(data.planner.model, "LM Studio model used for semantic query planning.", "llm"));
      return chips;
    }
    let resultLabel = "Deterministic";
    let resultTitle = "The app answered using deterministic dataset logic.";
    if (answeredByLmStudio) {
      resultLabel = "LLM answer";
      resultTitle = "LM Studio answered directly from the provided context.";
    } else if (data.source === "policy") {
      resultLabel = "AI blocked";
      resultTitle = "This Query prompt required an AI provider, but provider access is blocked by workspace policy.";
    } else if (data.source === "provider_unavailable") {
      resultLabel = "AI unavailable";
      resultTitle = "This Query prompt required an AI provider, but no provider reply was available.";
    }
    const resultIcon = answeredByLmStudio
      ? "llm"
      : data.source === "policy"
        ? "blocked"
        : data.source === "provider_unavailable"
          ? "unavailable"
          : "deterministic";
    chips.push(queryBadge(resultLabel, resultTitle, resultIcon));
    if (answeredByLmStudio && data.model) chips.push(queryBadge(data.model, "LM Studio model used for this answer.", "llm"));
    return chips;
  }

  function describeQueryProvenance(payload) {
    const data = payload && payload.data ? payload.data : {};
    if (payload && payload.intent === "general_llm") {
      return "The selected model answered from general knowledge. No workspace or dataset context was supplied.";
    }
    if (data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio") {
      const model = data.planner.model ? ` using ${data.planner.model}` : "";
      const providerContext = data.ai_provider_context_granularity
        ? ` AI provider context: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}.`
        : "";
      return `LM Studio semantic planner${model} translated the request into an internal cohort plan, and the result was executed with deterministic dataset logic.${providerContext}`;
    }
    if (data.provider === "lm_studio") {
      const providerContext = data.ai_provider_context_granularity
        ? ` AI provider context: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}.`
        : "";
      return `Provider: LM Studio fallback.${providerContext}`;
    }
    return `Provider: ${data.provider === "lm_studio" ? "LM Studio fallback" : "deterministic dataset logic"}.`;
  }

  function resetQueryWorkspace() {
    callbacks.detachQueryChat?.();
    state.queryScopeMetadata = null;
    state.queryHistory = [];
    state.queryTurns = [];
    queryPromptLibraryOpen = true;
    state.queryContextMode = "workspace";
    state.queryExecutionMode = defaultQueryExecutionMode();
    state.queryFollowMemoryEnabled = false;
    if (questionEl) questionEl.value = "";
    renderTopDiseaseChips();
    if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = "Click a disease to preload a deterministic workspace query.";
    setLatestQueryState({ ids: [], recordIds: [], resultHandle: "", totalCount: 0, prompt: "", analysisPrompt: "", idType: "patient" });
    setLatestScopedContext({ patientIds: [], recordIds: [], resultHandle: "", totalCount: 0, idType: "patient", sourceTab: "", prompt: "" });
    replyView.render({empty:'Ask about medications, diseases, or a patient timeline.'});
    reasonView.render({empty:'Run a query to see how the answer was produced.'});
    actionsView?.render(null);
    queryFollowupsEl.replaceChildren();
    queryDataEl.textContent = "";
    queryDetailsEl.open = false;
    if (queryStatusEl) {
      queryStatusEl.className = "query-status is-hidden";
      queryStatusEl.textContent = "";
    }
    renderQueryExecutionMode();
    renderQueryContextMode();
    renderQueryStarterPrompts();
    renderQueryThread();
  }

  function renderQueryThread() {
    renderQueryStarterPrompts();
    if (queryComposerTitleEl) queryComposerTitleEl.textContent = hasQueryTurns() ? "Ask a follow-up" : isGeneralQuestionMode() ? "Ask Model" : "Ask a question";
    if (!queryThreadEl) return;
    if (queryTabEl) queryTabEl.classList.toggle("query-tab-empty", !state.queryTurns.length);
    let latestAssistantIndex = -1;
    for (let i=state.queryTurns.length-1;i>=0;i--) {
      if (state.queryTurns[i]?.role==="assistant" && !state.queryTurns[i].pending) {latestAssistantIndex=i;break;}
    }
    const turns = state.queryTurns.map((turn,index)=>{
      if (turn.role==="user") return {role:turn.role,prompt:turn.prompt};
      const payload=turn.payload || {}, data=payload.data || {};
      const latest=index===latestAssistantIndex;
      const sourcePrompt=index>0 && state.queryTurns[index-1].role==="user" ? state.queryTurns[index-1].prompt || "" : "";
      return {
        role:turn.role, pending:turn.pending, latest,
        tone:turn.pending ? "query-thread-turn-pending" : data.source==="error" ? "query-thread-turn-error" : "query-thread-turn-assistant",
        label:turn.pending ? "Running" : data.source==="error" ? "Query not completed" : turn.contextMode==="general" ? "Answer" : "Result",
        reply:turn.pending ? activityState(turn.pendingLabel || "Running query",turn.pendingDetail || "Working through the query and preparing cohort-aware results.") : queryReplyModel(payload,turn.resultNavigation || {}),
        actions:!turn.pending && !turn.restored && latest ? queryActionsModel(payload,sourcePrompt) : "",
        provenance:!turn.pending ? getQueryProvenanceChips(payload) : [],
        followups:data.follow_up_suggestions, followupMetadata:data.follow_up_suggestion_metadata,
      };
    });
    threadView.render(turns,isGeneralQuestionMode());
  }

  function scrollQueryTurnIntoView(turnIndex) {
    if (!queryThreadEl) return;
    const index = Number(turnIndex);
    const target = Number.isInteger(index)
      ? queryThreadEl.querySelector(`[data-query-turn-index="${index}"]`)
      : queryThreadEl.lastElementChild;
    if (!target || typeof target.scrollIntoView !== "function") return;
    window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    });
  }

  function renderQueryReason(payload) {
    const data = payload.data || {};
    const reasons = [];
    reasons.push(`Intent: ${payload.intent || "unknown"}.`);
    reasons.push(describeQueryProvenance(payload));
    if (data.context && data.context.dataset_overview) {
      const totals = data.context.dataset_overview;
      reasons.push(`Context included cohort totals for ${totals.patients} patients and ${totals.visits} visits.`);
    } else if (typeof data.patient_count === "number") {
      reasons.push(`Matched patient count: ${data.patient_count}.`);
    } else if (Array.isArray(data.medications)) {
      reasons.push(`Medication inventory size shown: ${data.medications.length}.`);
    } else if (Array.isArray(data.diseases)) {
      reasons.push(`Disease inventory size shown: ${data.diseases.length}.`);
    }
    if (payload.intent === "needs_clarification") reasons.push("The prompt was too vague, so the UI is suggesting more specific follow-up questions.");
    if (payload.intent === "unsupported") reasons.push("The deterministic router did not recognize the query pattern, and no fallback answer was produced.");
    reasonView.render({text:reasons.join('\n')});
  }

  function renderFollowupButtons(items) {
    queryFollowupsEl.replaceChildren();
  }



  function queryActionContext(payload) {
    const context = payload && payload.action_context && typeof payload.action_context === "object"
      ? payload.action_context
      : {};
    const patientIds = Array.isArray(context.patient_ids) ? context.patient_ids.filter(Boolean) : [];
    const recordIds = Array.isArray(context.record_ids) ? context.record_ids.filter(Boolean) : [];
    const page = queryResultPage(payload);
    const resultHandle = String(context.result_handle || page.resultHandle || "").trim();
    return {
      patientIds: resultHandle ? [] : patientIds.slice(0, QUERY_RESULT_PAGE_SIZE),
      recordIds: resultHandle ? [] : recordIds.slice(0, QUERY_RESULT_PAGE_SIZE),
      resultHandle,
      totalCount: page.totalCount || Math.max(patientIds.length, recordIds.length),
      idType: context.id_type || (recordIds.length ? "sample" : "patient"),
      analysisPrompt: typeof context.analysis_prompt === "string" ? context.analysis_prompt : "",
    };
  }

  function queryActionsModel(payload, sourcePrompt = "") {
    if (payload && payload.intent === "general_llm") return "";
    if (payload && payload.data && payload.data.result_handle_unavailable === true) return "";
    const submittedPrompt = String(sourcePrompt || "").trim();
    const actionContext = queryActionContext(payload);
    const patientIds = actionContext.patientIds;
    const recordIds = actionContext.recordIds;
    const resultHandle = actionContext.resultHandle;
    const availableActions = payload && payload.data && payload.data.available_actions && typeof payload.data.available_actions === "object"
      ? payload.data.available_actions
      : {};
    setLatestQueryState({
      ids: patientIds,
      recordIds,
      resultHandle,
      totalCount: actionContext.totalCount,
      prompt: submittedPrompt,
      analysisPrompt: actionContext.analysisPrompt,
      idType: actionContext.idType,
    });
    if (patientIds.length || recordIds.length || resultHandle) {
      setLatestScopedContext({
        patientIds,
        recordIds,
        resultHandle,
        totalCount: actionContext.totalCount,
        idType: actionContext.idType,
        sourceTab: "query",
        prompt: submittedPrompt,
      });
      renderQueryExecutionMode();
    }
    if (!Object.values(availableActions).some(Boolean)) return "";
    const phenoRankerPatientIds = phenoRankerPatientIdsProvider();
    const compatibleIds = phenoRankerPatientIds.length ? patientIds.filter((patientId) => phenoRankerPatientIds.includes(patientId)) : [];
    const allCompatible = patientIds.length > 0 && compatibleIds.length === patientIds.length;
    const canUsePheno = availableActions.use_in_pheno_ranker && (resultHandle || recordIds.length > 0 || allCompatible);
    const canCopyIds = !resultHandle && availableActions.copy_patient_ids && patientIds.length > 0;
    const incompatiblePheno = !resultHandle && availableActions.use_in_pheno_ranker && !recordIds.length && phenoRankerPatientIds.length && !allCompatible;
    const canSummarize = Boolean(resultHandle || patientIds.length);
    const moreActions = canSummarize || canCopyIds || canUsePheno || incompatiblePheno;
    return {openAnalysis:!!availableActions.open_in_analysis, saveCohort:!!availableActions.save_cohort,
      canSummarize:!!canSummarize, canCopyIds:!!canCopyIds, canUsePheno:!!canUsePheno,
      incompatiblePheno:!!incompatiblePheno, moreActions:!!moreActions, resultHandle};
  }

  function renderQueryActions(payload, sourcePrompt = "") {
    actionsView?.render(queryActionsModel(payload,sourcePrompt));
  }

  function flashQueryActionFeedback(button, label) {
    if (!button) return;
    const textEl = button.querySelector(".query-action-label");
    const target = textEl || button;
    const previous = textEl ? textEl.textContent : button.textContent;
    target.textContent = label;
    window.setTimeout(() => {
      target.textContent = previous;
    }, 1400);
  }

  async function copyPatientIdsFromQuery(idsOverride, triggerButton) {
    const ids = Array.isArray(idsOverride) && idsOverride.length ? idsOverride : state.latestQueryPatientIds;
    if (!ids.length) {
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "No patient IDs are available to copy from this answer.";
      flashQueryActionFeedback(triggerButton, "No IDs");
      return;
    }
    const payload = ids.join(",");
    try {
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(payload);
        copied = true;
      } else {
        copied = fallbackCopyText(payload);
      }
      if (!copied) throw new Error("copy_failed");
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = `Copied ${ids.length} patient IDs.`;
      flashQueryActionFeedback(triggerButton, "Copied");
    } catch (_error) {
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "Unable to copy patient IDs from the browser.";
      flashQueryActionFeedback(triggerButton, "Unavailable");
    }
  }

  async function askQuery() {
    if (state.queryInFlight) return;
    const continuationIssue = callbacks.queryContinuationIssue?.();
    if (continuationIssue || state.queryTurns.length >= 200) {
      queryStatusEl.className = 'query-status';
      queryStatusEl.textContent = continuationIssue || 'This chat has reached 100 questions. Start a new Query chat to continue.';
      return;
    }
    const question = questionEl.value.trim();
    const queryMode = state.queryExecutionMode;
    const granularityMode = state.queryGranularityMode;
    const generalQuestion = isGeneralQuestionMode();
    if (!question) {
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "Enter a question first.";
      return;
    }
    const queryDatasetId = refs.dataDirEl.dataset && refs.dataDirEl.dataset.scopeId
      ? String(refs.dataDirEl.dataset.scopeId).trim()
      : String(refs.dataDirEl.value || "").trim();
    if (!generalQuestion && !queryDatasetId) {
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "Select and apply a dataset before running Query.";
      return;
    }
    if ((generalQuestion || queryMode === "planner_only") && (!state.lmStatus || state.lmStatus.available !== true)) {
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = generalQuestion
        ? "General questions require an available model provider."
        : "LLM planner unavailable. Start an LLM model or switch Query mode back to Auto.";
      renderQueryExecutionMode();
      return;
    }
    const submittedScope = !generalQuestion && state.queryFollowMemoryEnabled && state.latestScopedContext
      ? {
        patientIds: Array.isArray(state.latestScopedContext.patientIds) ? state.latestScopedContext.patientIds.slice(0, QUERY_RESULT_PAGE_SIZE) : [],
        recordIds: Array.isArray(state.latestScopedContext.recordIds) ? state.latestScopedContext.recordIds.slice(0, QUERY_RESULT_PAGE_SIZE) : [],
        resultHandle: String(state.latestScopedContext.resultHandle || "").trim(),
        idType: String(state.latestScopedContext.idType || "patient"),
      }
      : { patientIds: [], recordIds: [], resultHandle: "", idType: "patient" };
    const workspaceRevision = state.workspaceRevision;
    const requestIsStale = () => workspaceRevision !== state.workspaceRevision;
    state.queryInFlight = true;
    askBtnEl.disabled = true;
    const chatSaved = await callbacks.saveQueryChat?.();
    if (requestIsStale()) return;
    if (chatSaved === false) {
      state.queryInFlight = false;
      askBtnEl.disabled = false;
      queryStatusEl.className = 'query-status';
      queryStatusEl.textContent = 'Unable to save this chat. Check the message in Chats before retrying.';
      return;
    }
    queryStatusEl.className = "query-status loading";
    queryStatusEl.textContent = generalQuestion ? "Waiting for the model..." : "Running query. Waiting for response...";
    replyView.render({text:generalQuestion ? '**Asking the model...**\nPlease wait.' : '**Running query...**\nPlease wait.'});
    reasonView.render({text:'Waiting for the response and its supporting context.'});
    actionsView?.render(null);
    queryFollowupsEl.replaceChildren();
    queryPromptLibraryOpen = false;
    state.queryTurns.push({ role: "user", prompt: question, contextMode: generalQuestion ? "general" : "workspace" });
    state.queryTurns.push({
      role: "assistant",
      pending: true,
      contextMode: generalQuestion ? "general" : "workspace",
      pendingLabel: generalQuestion ? "Asking model" : "Parsing request",
      pendingDetail: generalQuestion
        ? "Waiting for a general answer without workspace context."
        : "Interpreting the cohort question and selecting the right query path.",
      payload: { reply: "Running query..." },
    });
    questionEl.value = "";
    renderTopDiseaseChips();
    renderQueryThread();
    scrollQueryTurnIntoView(state.queryTurns.length - 1);
    startQueryProgressUpdates();
    await nextFrame();
    if (requestIsStale()) return;
    try {
      const response = await fetch(generalQuestion ? "/llm/general" : "/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(generalQuestion
          ? { prompt: question, history: historyForContext("general") }
          : {
            q: question,
            dataset_id: queryDatasetId,
            query_mode: queryMode,
            granularity_mode: granularityMode,
            history: historyForContext("workspace"),
            scoped_patient_ids: !submittedScope.resultHandle
              ? submittedScope.patientIds
              : [],
            scoped_record_ids: !submittedScope.resultHandle
              ? submittedScope.recordIds
              : [],
            scoped_result_handle: submittedScope.resultHandle,
            scoped_id_type: submittedScope.idType,
            scope_metadata: state.queryScopeMetadata || {},
          }),
      });
      if (!response.ok) {
        const error = await response.json();
        if (requestIsStale()) return;
        const terminalScopedResult = !generalQuestion
          && Boolean(submittedScope.resultHandle)
          && (response.status === 404 || response.status === 410);
        if (terminalScopedResult) {
          const message = terminalQueryResultMessage(response.status);
          invalidateQueryResultHandle(submittedScope.resultHandle, message);
          error.detail = message;
        }
        replyView.render({text:error.detail});
        reasonView.render({text:'The request reached the API but returned an error response.'});
        queryDataEl.textContent = "";
        queryDetailsEl.open = false;
        actionsView?.render(null);
        state.queryTurns[state.queryTurns.length - 1] = {
          role: "assistant",
          contextMode: generalQuestion ? "general" : "workspace",
          payload: { intent: "query_error", reply: String(error.detail || "Query failed."), data: { source: "error", provider: "deterministic" } },
      };
      renderQueryThread();
      scrollQueryTurnIntoView(state.queryTurns.length - 1);
      queryStatusEl.className = "query-status";
        queryStatusEl.textContent = "Query failed.";
        return;
      }
      const payload = boundQueryPayload(await response.json());
      if (requestIsStale()) return;
      stopQueryProgressUpdates();
      state.queryTurns[state.queryTurns.length - 1] = {
        role: "assistant",
        payload,
        contextMode: generalQuestion ? "general" : "workspace",
        resultNavigation: { cursor: "", start: 0, previous: [], loading: false, error: "" },
      };
      renderQueryThread();
      scrollQueryTurnIntoView(state.queryTurns.length - 1);
      replyView.render(queryReplyModel(payload));
      renderQueryReason(payload);
      renderQueryActions(payload, question);
      renderFollowupButtons(payload.data && payload.data.follow_up_suggestions);
      queryDataEl.textContent = JSON.stringify(queryDetailsData(payload.data), null, 2);
      queryDetailsEl.open = false;
      const contextMode = generalQuestion ? "general" : "workspace";
      state.queryHistory.push({ role: "user", content: question, context_mode: contextMode });
      state.queryHistory.push({ role: "assistant", content: compactQueryHistoryReply(payload), context_mode: contextMode });
      state.queryHistory = state.queryHistory.slice(-16);
      state.queryExecutionMode = defaultQueryExecutionMode();
      renderQueryExecutionMode();
      queryStatusEl.className = "query-status is-hidden";
      queryStatusEl.textContent = "";
    } catch (error) {
      if (requestIsStale()) return;
      stopQueryProgressUpdates();
      replyView.render({text:error?.message || 'Request failed.'});
      reasonView.render({text:'The request failed before a valid response payload reached the UI.'});
      queryDataEl.textContent = "";
      queryDetailsEl.open = false;
      actionsView?.render(null);
      setLatestQueryState({ ids: [] });
      state.queryTurns[state.queryTurns.length - 1] = {
        role: "assistant",
        contextMode: generalQuestion ? "general" : "workspace",
        payload: { intent: "query_error", reply: error && error.message ? error.message : "Request failed.", data: { source: "error", provider: "deterministic" } },
      };
      renderQueryThread();
      scrollQueryTurnIntoView(state.queryTurns.length - 1);
      state.queryExecutionMode = defaultQueryExecutionMode();
      renderQueryExecutionMode();
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "Network error.";
    } finally {
      if (requestIsStale()) return;
      await callbacks.saveQueryChat?.();
      stopQueryProgressUpdates();
      state.queryInFlight = false;
      askBtnEl.disabled = false;
      if (queryTabEl.classList.contains('active')) questionEl.focus();
    }
  }

  function handleQueryExamplesClick(event) {
    const diseaseChip = event.target.closest("[data-query-disease-chip]");
    if (diseaseChip && queryDiseaseTopChipsEl && queryDiseaseTopChipsEl.contains(diseaseChip)) {
      preloadDiseaseCohort(diseaseChip.dataset.queryDiseaseChip || "");
      return;
    }
    const analysisButton = event.target.closest("[data-analysis-prompt]");
    if (analysisButton && queryExamplesEl.contains(analysisButton)) {
      if (state.latestQueryPatientIds.length || state.latestQueryResultHandle) {
        sendPatientIdsToAnalysis();
      }
      sendPromptToAnalysis(analysisButton.dataset.analysisPrompt, {
        llmOnly: analysisButton.dataset.analysisLlmOnly === "true",
      });
      if (hasQueryTurns()) {
        setQueryPromptLibraryOpen(false);
      }
      return;
    }
    const button = event.target.closest("[data-prompt]");
    if (!button || !queryExamplesEl.contains(button)) return;
    questionEl.value = button.dataset.prompt;
    state.queryExecutionMode = defaultQueryExecutionMode();
    renderQueryExecutionMode();
    if (hasQueryTurns()) {
      setQueryPromptLibraryOpen(false);
    }
    questionEl.focus();
  }

  function handleQueryFollowupsClick(event) {
    const button = event.target.closest("[data-prompt]");
    if (!button || !queryFollowupsEl.contains(button)) return;
    questionEl.value = button.dataset.prompt;
    state.queryExecutionMode = button.dataset.queryFollowupMode === "planner_only" ? "planner_only" : "deterministic_only";
    renderQueryExecutionMode();
    questionEl.focus();
  }

  function replaceQueryResultPage(payload, responsePage) {
    const data = payload && payload.data && typeof payload.data === "object" ? payload.data : {};
    const nextPayload = { ...payload, data };
    data.result_handle = String(responsePage && responsePage.result_handle || data.result_handle || "").trim();
    data.result_page = responsePage && typeof responsePage === "object" ? { ...responsePage } : {};
    data.patient_ids = Array.isArray(data.result_page.patient_ids) ? data.result_page.patient_ids : [];
    data.sample_ids = Array.isArray(data.result_page.sample_ids) ? data.result_page.sample_ids : [];
    data.patients = Array.isArray(data.result_page.rows) ? data.result_page.rows : [];
    return boundQueryPayload(nextPayload);
  }

  function terminalQueryResultMessage(status) {
    return Number(status) === 410
      ? "This Query result has expired. Run the query again to recreate it."
      : "This Query result is no longer available. Run the query again to recreate it.";
  }

  function payloadWithoutQueryResultHandle(payload, handle) {
    if (!payload || typeof payload !== "object") return payload;
    const current = queryResultPage(payload);
    if (!handle || current.resultHandle !== handle) return payload;
    const data = payload.data && typeof payload.data === "object" ? { ...payload.data } : {};
    const resultPage = data.result_page && typeof data.result_page === "object"
      ? { ...data.result_page, result_handle: "", has_more: false, next_cursor: "" }
      : {};
    const availableActions = data.available_actions && typeof data.available_actions === "object"
      ? data.available_actions
      : {};
    data.result_handle = "";
    data.result_handle_unavailable = true;
    data.result_page = resultPage;
    data.available_actions = Object.fromEntries(
      Object.keys(availableActions).map((key) => [key, false]),
    );
    const actionContext = payload.action_context && typeof payload.action_context === "object"
      ? payload.action_context
      : {};
    return {
      ...payload,
      data,
      action_context: {
        ...actionContext,
        result_handle: "",
        patient_ids: [],
        record_ids: [],
      },
    };
  }

  function invalidateQueryResultHandle(handle, message) {
    const normalizedHandle = String(handle || "").trim();
    if (!normalizedHandle) return;
    state.queryTurns.forEach((turn) => {
      if (!turn || !turn.payload || queryResultPage(turn.payload).resultHandle !== normalizedHandle) return;
      turn.payload = payloadWithoutQueryResultHandle(turn.payload, normalizedHandle);
      turn.resultNavigation = {
        ...(turn.resultNavigation && typeof turn.resultNavigation === "object" ? turn.resultNavigation : {}),
        loading: false,
        error: String(message || terminalQueryResultMessage(404)),
        terminal: true,
      };
    });
    if (String(state.latestQueryResultHandle || "").trim() === normalizedHandle) {
      setLatestQueryState({
        ids: [],
        recordIds: [],
        resultHandle: "",
        totalCount: 0,
        prompt: "",
        analysisPrompt: "",
        idType: "patient",
      });
    }
    if (state.latestScopedContext && String(state.latestScopedContext.resultHandle || "").trim() === normalizedHandle) {
      setLatestScopedContext({
        patientIds: [],
        recordIds: [],
        resultHandle: "",
        totalCount: 0,
        idType: "patient",
        sourceTab: "",
        prompt: "",
      });
      state.latestScopedContext.sourceTab = "";
      state.latestScopedContext.prompt = "";
      state.queryFollowMemoryEnabled = false;
      renderQueryExecutionMode();
    }
  }

  async function loadQueryResultPage(turnIndex, direction, requestedSort = "") {
    const index = Number(turnIndex);
    const turn = Number.isInteger(index) ? state.queryTurns[index] : null;
    if (!turn || !turn.payload || turn.pending) return;
    const currentPage = queryResultPage(turn.payload);
    if (!currentPage.resultHandle) return;
    const currentNavigation = turn.resultNavigation && typeof turn.resultNavigation === "object"
      ? turn.resultNavigation
      : { cursor: "", start: 0, previous: [], loading: false, error: "" };
    if (currentNavigation.loading) return;
    let sortBy = String(currentNavigation.sortBy || "");
    let sortDirection = String(currentNavigation.sortDirection || "asc");
    const previous = Array.isArray(currentNavigation.previous) ? currentNavigation.previous.slice() : [];
    let targetCursor = "";
    let targetStart = 0;
    let nextPrevious = previous;
    if (direction === "sort") {
      sortDirection = sortBy === requestedSort && sortDirection === "asc" ? "desc" : "asc";
      sortBy = requestedSort;
      nextPrevious = [];
    } else if (direction === "next") {
      if (!currentPage.hasMore || !currentPage.nextCursor) return;
      targetCursor = currentPage.nextCursor;
      targetStart = Math.max(0, Number(currentNavigation.start || 0)) + currentPage.returnedCount;
      nextPrevious = previous.concat([{
        cursor: String(currentNavigation.cursor || ""),
        start: Math.max(0, Number(currentNavigation.start || 0)),
      }]);
    } else if (direction === "previous") {
      const target = previous[previous.length - 1];
      if (!target) return;
      targetCursor = String(target.cursor || "");
      targetStart = Math.max(0, Number(target.start || 0));
      nextPrevious = previous.slice(0, -1);
    } else {
      return;
    }

    turn.resultNavigation = { ...currentNavigation, loading: true, error: "" };
    renderQueryThread();
    try {
      const parameters = new URLSearchParams({ limit: String(QUERY_RESULT_PAGE_SIZE) });
      if (sortBy) {
        parameters.set("sort_by", sortBy);
        parameters.set("sort_direction", sortDirection);
      }
      if (targetCursor) parameters.set("cursor", targetCursor);
      const response = await fetch(
        `/query-results/${encodeURIComponent(currentPage.resultHandle)}?${parameters.toString()}`,
        { cache: "no-store" },
      );
      if (state.queryTurns[index] !== turn || queryResultPage(turn.payload).resultHandle !== currentPage.resultHandle) return;
      if (!response.ok) {
        const terminalResponse = response.status === 404 || response.status === 410;
        let message = terminalResponse
          ? terminalQueryResultMessage(response.status)
          : "Unable to load this result page.";
        try {
          const error = await response.json();
          if (!terminalResponse && error && error.detail) message = String(error.detail);
        } catch (_error) {
          // Keep the safe status-based message.
        }
        if (terminalResponse) {
          invalidateQueryResultHandle(currentPage.resultHandle, message);
          renderQueryThread();
          if (index === state.queryTurns.length - 1) {
            replyView.render(queryReplyModel(turn.payload, turn.resultNavigation || {}));
            queryDataEl.textContent = JSON.stringify(queryDetailsData(turn.payload.data), null, 2);
          }
          return;
        }
        throw new Error(message);
      }
      const responsePage = await response.json();
      if (String(responsePage.result_handle || "").trim() !== currentPage.resultHandle) {
        throw new Error("The result page did not match this Query result.");
      }
      turn.payload = replaceQueryResultPage(turn.payload, responsePage);
      turn.resultNavigation = {
        cursor: targetCursor,
        sortBy, sortDirection,
        start: targetStart,
        previous: nextPrevious,
        loading: false,
        error: "",
      };
      renderQueryThread();
      if (index === state.queryTurns.length - 1) {
        replyView.render(queryReplyModel(turn.payload, turn.resultNavigation));
        queryDataEl.textContent = JSON.stringify(queryDetailsData(turn.payload.data), null, 2);
      }
      const renderedTurn = queryThreadEl && queryThreadEl.querySelector(`[data-query-turn-index="${index}"]`);
      if (renderedTurn && typeof renderedTurn.scrollIntoView === "function") {
        renderedTurn.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      turn.resultNavigation = {
        ...currentNavigation,
        loading: false,
        error: error && error.message ? error.message : "Unable to load this result page.",
      };
      renderQueryThread();
    }
  }

  function handleDocumentClick(event) {
    document.querySelectorAll('.query-inline-actions[open]').forEach(menu => {
      if (!menu.contains(event.target) || event.target.closest('[data-query-action]')) menu.open = false;
    });
    const sortButton = event.target.closest("[data-query-sort]");
    if (sortButton && queryTabEl?.contains(sortButton)) {
      const turnElement = sortButton.closest("[data-query-turn-index]");
      const index = turnElement ? turnElement.dataset.queryTurnIndex : state.queryTurns.length - 1;
      void loadQueryResultPage(index, "sort", sortButton.dataset.querySort);
      return;
    }
    const exportButton = event.target.closest("[data-query-export]");
    if (exportButton && queryTabEl?.contains(exportButton)) {
      const format = exportButton.dataset.queryExport;
      const handle = exportButton.dataset.queryExportHandle;
      const parameters = new URLSearchParams({ format });
      if (exportButton.dataset.queryExportSort) {
        parameters.set("sort_by", exportButton.dataset.queryExportSort);
        parameters.set("sort_direction", exportButton.dataset.queryExportDirection);
      }
      exportButton.disabled = true;
      queryStatusEl.textContent = "Preparing download…";
      void downloadFile(`/query-results/${encodeURIComponent(handle)}/export?${parameters.toString()}`,
        format === "json" ? "query-result-metadata.json" : `query-result.${format}`)
        .then(result => { queryStatusEl.textContent = downloadStatus(result); })
        .catch((error) => { queryStatusEl.textContent = error.message; })
        .finally(() => { exportButton.disabled = false; });
      return;
    }
    const diseaseChip = event.target.closest("[data-query-disease-chip]");
    if (diseaseChip && queryDiseaseTopChipsEl && queryDiseaseTopChipsEl.contains(diseaseChip)) {
      preloadDiseaseCohort(diseaseChip.dataset.queryDiseaseChip || "");
      return;
    }
    const pageButton = event.target.closest("[data-query-page-action]");
    if (pageButton && queryThreadEl && queryThreadEl.contains(pageButton)) {
      const turnElement = pageButton.closest("[data-query-turn-index]");
      const turnIndex = turnElement ? turnElement.dataset.queryTurnIndex : "";
      void loadQueryResultPage(turnIndex, pageButton.dataset.queryPageAction || "");
      return;
    }
    const queryActionButton = event.target.closest("[data-query-action]");
    if (queryActionButton && queryTabEl && queryTabEl.contains(queryActionButton)) {
      if (queryActionButton.dataset.queryAction === 'clinical-summary') {
        const turn = queryActionButton.closest('[data-query-turn-index]');
        const payload = state.queryTurns[Number(turn?.dataset.queryTurnIndex)]?.payload;
        if (!payload) return;
        const selection = queryActionContext(payload);
        openClinicalSummary(selection.resultHandle
          ? {result_handle:selection.resultHandle, label:'Query selection'}
          : {patient_ids:selection.patientIds, label:'Query selection'});
        return;
      }
      if (queryActionButton.dataset.queryAction === "use-pheno") {
        sendPatientIdsToPhenoRanker();
        return;
      }
      if (queryActionButton.dataset.queryAction === "use-analysis") {
        sendPatientIdsToAnalysis();
        return;
      }
      if (queryActionButton.dataset.queryAction === "copy-ids") {
        copyPatientIdsFromQuery(state.latestQueryPatientIds, queryActionButton);
        return;
      }
      if (queryActionButton.dataset.queryAction === "save-cohort") {
        saveLatestQueryAsCohort();
        return;
      }
    }
    const queryPromptButton = event.target.closest("[data-prompt]");
    if (queryPromptButton && queryThreadEl && queryThreadEl.contains(queryPromptButton)) {
      questionEl.value = queryPromptButton.dataset.prompt;
      state.queryExecutionMode = queryPromptButton.dataset.queryFollowupMode === "planner_only" ? "planner_only" : "deterministic_only";
      renderQueryExecutionMode();
      questionEl.focus();
    }
  }

  return {
    markRestoredChat() {
      for (const turn of state.queryTurns) {
        if (turn.role !== 'assistant') continue;
        turn.restored = true;
        const handle = queryResultPage(turn.payload).resultHandle;
        turn.payload = payloadWithoutQueryResultHandle(turn.payload, handle);
      }
      renderQueryThread();
    },
    queryReplyModel,
    renderQueryReason,
    renderQueryActions,
    renderQueryExecutionMode,
    renderQueryStarterPrompts,
    resetQueryWorkspace,
    renderQueryThread,
    askQuery,
    loadDiseaseOptions,
    preloadDiseaseCohort,
    handleQueryExamplesClick,
    handleQueryFollowupsClick,
    handleDocumentClick,
    renderQueryContextMode,
    togglePromptLibrary() {
      setQueryPromptLibraryOpen(!queryPromptLibraryOpen, { scroll: true });
    },
    setExecutionMode(value) {
      state.queryExecutionMode = value;
    },
    setContextMode: setQueryContextMode,
  };
}
