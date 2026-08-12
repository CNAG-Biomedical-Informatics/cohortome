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
  const { escapeHtml, renderActivityCard, fallbackCopyText } = helpers;
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
    isMultiDatasetWorkspace,
    setLatestQueryState,
    setLatestScopedContext,
  } = callbacks;
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

  function renderQueryContextMode() {
    const general = isGeneralQuestionMode();
    [[queryContextWorkspaceBtnEl, !general], [queryContextGeneralBtnEl, general]].forEach(([button, active]) => {
      if (!button) return;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (queryTabEl) queryTabEl.classList.toggle("query-tab-general-mode", general);
    if (queryComposerTitleEl) queryComposerTitleEl.textContent = general ? "Ask Model" : "Continue Query";
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
    const targetHost = queryStarterTopHostEl;
    if (targetHost && queryStarterPanelEl.parentElement !== targetHost) {
      targetHost.appendChild(queryStarterPanelEl);
    }

    const visible = !isGeneralQuestionMode() && (!hasTurns || queryPromptLibraryOpen);
    queryStarterPanelEl.hidden = !visible;
    queryStarterPanelEl.classList.toggle("is-hidden", !visible);
    queryStarterPanelEl.classList.remove("query-starter-panel-compact");

    if (queryStarterHostEl) {
      queryStarterHostEl.hidden = true;
      queryStarterHostEl.classList.add("is-hidden");
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
      queryStarterPanelEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function renderTopDiseaseChips() {
    if (!queryDiseaseTopChipsEl) return;
    const currentPrompt = String(questionEl && questionEl.value ? questionEl.value : "").toLowerCase();
    const topDiseases = diseaseOptions.slice(0, 8);
    if (!topDiseases.length) {
      queryDiseaseTopChipsEl.innerHTML = "";
      return;
    }
    queryDiseaseTopChipsEl.innerHTML = topDiseases.map((item) => {
      const disease = String(item.disease || "").trim();
      const active = currentPrompt.includes(disease.toLowerCase()) ? " is-active-chip" : "";
      const count = Number(item.patient_count || 0);
      return `<button type="button" class="query-chip query-chip-deterministic${active}" data-query-disease-chip="${escapeHtml(disease)}">${escapeHtml(disease)} <span class="query-chip badge">${escapeHtml(String(count))}</span></button>`;
    }).join("");
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

  function renderInlineCode(value) {
    const parts = String(value).split("`");
    return parts.map((part, index) => {
      if (index % 2 === 1) {
        return `<code>${escapeHtml(part)}</code>`;
      }
      return escapeHtml(part)
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>");
    }).join("");
  }

  function renderQueryStructuredTable(payload) {
    const data = payload && payload.data ? payload.data : {};
    if (!data || typeof data !== "object") {
      return "";
    }
    if (Array.isArray(data.patients) && data.patients.length) {
      const currentPatients = Array.isArray(currentPatientsProvider()) ? currentPatientsProvider() : [];
      const provenanceByPatientId = new Map(currentPatients.map((item) => [
        String(item.patient_id || ""),
        Array.isArray(item.dataset_names) ? item.dataset_names : [],
      ]));
      const showDataset = isMultiDatasetWorkspace();
      const rows = data.patients.slice(0, 100).map((item) => `
        <tr>
          <td>${escapeHtml(String(item.patient_id || ""))}</td>
          ${showDataset ? `<td>${escapeHtml((provenanceByPatientId.get(String(item.patient_id || "")) || []).join(", ") || "n/a")}</td>` : ""}
          <td>${escapeHtml(String(item.sex || ""))}</td>
          <td>${escapeHtml(String(item.visit_count ?? ""))}</td>
          <td>${escapeHtml(String(item.medication_count ?? ""))}</td>
        </tr>
      `).join("");
      return `
        <div class="section-note">Matching patients (${data.patients.length}).</div>
        <table>
          <thead><tr><th>Patient</th>${showDataset ? "<th>Dataset</th>" : ""}<th>Sex</th><th>Visits</th><th>Medications</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }
    if (Array.isArray(data.medications) && data.medications.length) {
      const rows = data.medications.slice(0, 100).map((item) => `
        <tr>
          <td>${escapeHtml(String(item.medication || ""))}</td>
          <td>${escapeHtml(String(item.patient_count ?? ""))}</td>
        </tr>
      `).join("");
      return `
        <div class="section-note">Medication inventory (${data.medications.length}).</div>
        <table>
          <thead><tr><th>Medication</th><th>Patients</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }
    if (Array.isArray(data.diseases) && data.diseases.length) {
      const rows = data.diseases.slice(0, 100).map((item) => `
        <tr>
          <td>${escapeHtml(String(item.disease || ""))}</td>
          <td>${escapeHtml(String(item.patient_count ?? ""))}</td>
        </tr>
      `).join("");
      return `
        <div class="section-note">Disease inventory (${data.diseases.length}).</div>
        <table>
          <thead><tr><th>Disease</th><th>Patients</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }
    return "";
  }

  function renderQueryReply(payloadOrValue) {
    const value = typeof payloadOrValue === "object" && payloadOrValue ? payloadOrValue.reply : payloadOrValue;
    const lines = String(value || "").split("\r\n").join("\n").split("\n");
    const blocks = [];
    let paragraphLines = [];
    let listItems = [];
    let codeLines = [];
    let tableLines = [];
    let inCodeBlock = false;

    function flushParagraph() {
      if (!paragraphLines.length) return;
      blocks.push(`<p>${paragraphLines.map((line) => renderInlineCode(line)).join("<br>")}</p>`);
      paragraphLines = [];
    }
    function flushList() {
      if (!listItems.length) return;
      blocks.push(`<ul>${listItems.map((line) => `<li>${renderInlineCode(line)}</li>`).join("")}</ul>`);
      listItems = [];
    }
    function flushCodeBlock() {
      if (!codeLines.length) return;
      blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      codeLines = [];
    }
    function isTableLine(line) {
      return line.includes("|");
    }
    function isTableSeparatorLine(line) {
      const cells = line.split("|").map((cell) => cell.trim()).filter(Boolean);
      if (!cells.length) return false;
      return cells.every((cell) => cell.length >= 3 && cell.split("-").join("").split(":").join("") === "");
    }
    function splitTableCells(line) {
      let normalized = line.trim();
      if (normalized.startsWith("|")) normalized = normalized.slice(1);
      if (normalized.endsWith("|")) normalized = normalized.slice(0, -1);
      return normalized.split("|").map((cell) => renderInlineCode(cell.trim()));
    }
    function flushTable() {
      if (tableLines.length < 2) {
        if (tableLines.length) paragraphLines = paragraphLines.concat(tableLines);
        tableLines = [];
        return;
      }
      const headerLine = tableLines[0];
      const separatorLine = tableLines[1];
      if (!isTableSeparatorLine(separatorLine)) {
        paragraphLines = paragraphLines.concat(tableLines);
        tableLines = [];
        return;
      }
      const headers = splitTableCells(headerLine);
      const rows = tableLines.slice(2).map(splitTableCells);
      blocks.push(
        `<table><thead><tr>${headers.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>` +
        `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table>`
      );
      tableLines = [];
    }

    for (const rawLine of lines) {
      const trimmed = rawLine.trim();
      if (trimmed.startsWith("```")) {
        flushParagraph(); flushList(); flushTable();
        if (inCodeBlock) {
          flushCodeBlock();
          inCodeBlock = false;
        } else {
          inCodeBlock = true;
        }
        continue;
      }
      if (inCodeBlock) {
        codeLines.push(rawLine);
        continue;
      }
      if (!trimmed) {
        flushParagraph(); flushList(); flushTable();
        continue;
      }
      if (isTableLine(trimmed)) {
        flushParagraph(); flushList();
        tableLines.push(trimmed);
        continue;
      }
      flushTable();
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        flushParagraph();
        listItems.push(trimmed.slice(2));
        continue;
      }
      if (trimmed.startsWith("### ")) {
        flushParagraph(); flushList(); flushTable();
        blocks.push(`<h4>${renderInlineCode(trimmed.slice(4))}</h4>`);
        continue;
      }
      if (trimmed.startsWith("## ")) {
        flushParagraph(); flushList(); flushTable();
        blocks.push(`<h4>${renderInlineCode(trimmed.slice(3))}</h4>`);
        continue;
      }
      if (trimmed.startsWith("# ")) {
        flushParagraph(); flushList(); flushTable();
        blocks.push(`<h4>${renderInlineCode(trimmed.slice(2))}</h4>`);
        continue;
      }
      paragraphLines.push(trimmed);
    }
    flushParagraph();
    flushList();
    flushTable();
    if (inCodeBlock) flushCodeBlock();
    const textMarkup = blocks.join("") || "<p>No answer returned.</p>";
    const structured = typeof payloadOrValue === "object" && payloadOrValue ? renderQueryStructuredTable(payloadOrValue) : "";
    return structured ? `${textMarkup}${structured}` : textMarkup;
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

  function queryIconSvg(kind) {
    const icons = {
      summary: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h8"></path><path d="M8 12h8"></path><path d="M8 18h5"></path><rect x="4" y="3" width="16" height="18" rx="2"></rect></svg>',
      response: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path><circle cx="12" cy="12" r="2.5"></circle></svg>',
      provider: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 10V7a4 4 0 1 1 8 0v3"></path><rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M12 14v2"></path></svg>',
      planner: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v6"></path><path d="M9 6h6"></path><path d="M5 13a7 7 0 1 0 14 0"></path><path d="m9 13 2 2 4-4"></path></svg>',
      deterministic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"></path></svg>',
      llm: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9h8"></path><path d="M8 13h5"></path><path d="M6 4h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-4 4v-4H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"></path></svg>',
      blocked: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="m8.5 8.5 7 7"></path><path d="m15.5 8.5-7 7"></path></svg>',
      unavailable: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>',
      no_context: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="6" rx="7" ry="3"></ellipse><path d="M5 6v6c0 1.7 3.1 3 7 3 1.1 0 2.1-.1 3-.3"></path><path d="m5 4 14 16"></path></svg>',
    };
    return icons[kind] || icons.summary;
  }

  function renderQueryIcon(kind, cls = "provenance-inline-icon") {
    return `<span class="${cls}" aria-hidden="true">${queryIconSvg(kind)}</span>`;
  }

  function renderQueryBadge(label, title, iconKind = "") {
    const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
    return `<span class="query-chip badge provenance-badge"${safeTitle}>${iconKind ? `${renderQueryIcon(iconKind, "provenance-badge-icon")}` : ""}<span>${escapeHtml(label)}</span></span>`;
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
    const chips = [renderQueryBadge(intentInfo.label, intentInfo.title, "summary")];
    if (payload && payload.intent === "general_llm") {
      chips.push(renderQueryBadge(
        "No workspace context",
        "Only this prompt and recent General-question turns were sent to the selected model. No workspace or dataset context was supplied.",
        "no_context",
      ));
      if (data.model) chips.push(renderQueryBadge(data.model, "Model used for this general answer.", "llm"));
      return chips;
    }
    const datasetNames = Array.isArray(data.dataset_names)
      ? data.dataset_names.map((item) => String(item || "").trim()).filter(Boolean)
      : String(data.dataset_name || "").trim()
        ? [String(data.dataset_name).trim()]
        : [];
    if (datasetNames.length) {
      chips.push(renderQueryBadge(
        `Dataset: ${datasetNames.join(", ")}`,
        `This answer was computed from ${datasetNames.join(", ")}.`,
        "summary",
      ));
    }
    if (data.granularity_applied) {
      const requested = data.granularity_requested && data.granularity_requested !== data.granularity_applied
        ? ` Requested: ${data.granularity_requested}.`
        : "";
      chips.push(renderQueryBadge(
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
      chips.push(renderQueryBadge(
        `Model context: ${formatAiProviderGranularity(data.ai_provider_context_granularity)}`,
        title,
        "provider",
      ));
    }
    if (plannedByLmStudio) {
      chips.push(renderQueryBadge("LLM-planned", "LM Studio translated the prompt into a constrained internal cohort plan.", "planner"));
      chips.push(renderQueryBadge("Deterministic execution", "The app executed the planned query against local cohort data without using the model to produce the result.", "deterministic"));
      if (data.planner.model) chips.push(renderQueryBadge(data.planner.model, "LM Studio model used for semantic query planning.", "llm"));
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
    chips.push(renderQueryBadge(resultLabel, resultTitle, resultIcon));
    if (answeredByLmStudio && data.model) chips.push(renderQueryBadge(data.model, "LM Studio model used for this answer.", "llm"));
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
    state.queryHistory = [];
    state.queryTurns = [];
    queryPromptLibraryOpen = true;
    state.queryContextMode = "workspace";
    state.queryExecutionMode = defaultQueryExecutionMode();
    state.queryFollowMemoryEnabled = false;
    if (questionEl) questionEl.value = "";
    renderTopDiseaseChips();
    if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = "Click a disease to preload a deterministic workspace query.";
    setLatestQueryState({ ids: [], prompt: "", analysisPrompt: "", idType: "patient" });
    setLatestScopedContext({ patientIds: [], recordIds: [], idType: "patient", sourceTab: "", prompt: "" });
    queryReplyEl.innerHTML = '<div class="empty">Ask about medications, diseases, or a patient timeline.</div>';
    queryReasonEl.innerHTML = '<div class="empty">Run a query to see how the answer was produced.</div>';
    if (queryActionsEl) queryActionsEl.innerHTML = "";
    queryFollowupsEl.innerHTML = "";
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
    if (!queryThreadEl) return;
    if (queryTabEl) queryTabEl.classList.toggle("query-tab-empty", !state.queryTurns.length);
    if (!state.queryTurns.length) {
      queryThreadEl.innerHTML = isGeneralQuestionMode()
        ? '<div class="empty">Ask a general question. The model will not receive workspace context.</div>'
        : '<div class="empty">Ask a query to start a conversational thread. Follow-up questions will reuse recent query history.</div>';
      return;
    }
    const latestAssistantIndex = (() => {
      for (let index = state.queryTurns.length - 1; index >= 0; index -= 1) {
        if (state.queryTurns[index] && state.queryTurns[index].role === "assistant" && !state.queryTurns[index].pending) {
          return index;
        }
      }
      return -1;
    })();
    queryThreadEl.innerHTML = state.queryTurns.map((turn, index) => {
      if (turn.role === "user") {
        return `<article class="analysis-turn query-thread-turn query-thread-turn-user" data-query-turn-index="${index}"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${escapeHtml(turn.prompt || "")}</p></div></article>`;
      }
      const payload = turn.payload || {};
      const data = payload.data || {};
      const toneClass = turn.pending ? "query-thread-turn-pending" : data.source === "error" ? "query-thread-turn-error" : "query-thread-turn-assistant";
      const sourcePrompt = index > 0 && state.queryTurns[index - 1].role === "user"
        ? state.queryTurns[index - 1].prompt || ""
        : "";
      return `
        <article class="analysis-turn query-thread-turn ${toneClass}" data-query-turn-index="${index}">
          <div class="analysis-turn-label">${turn.pending ? "Running" : "Assistant"}</div>
          ${turn.pending ? "" : `<div class="query-thread-turn-meta">${getQueryProvenanceChips(payload).join("")}</div>`}
          <div class="analysis-turn-body">
            ${turn.pending ? renderActivityCard(turn.pendingLabel || "Running query", turn.pendingDetail || "Working through the query and preparing cohort-aware results.") : renderQueryReply(payload)}
            ${!turn.pending && index === latestAssistantIndex ? queryActionsMarkup(payload, sourcePrompt) : ""}
            ${!turn.pending && index === latestAssistantIndex ? renderFollowupButtonsMarkup(payload.data && payload.data.follow_up_suggestions) : ""}
          </div>
        </article>
      `;
    }).join("");
  }

  function scrollQueryTurnIntoView(turnIndex) {
    if (!queryThreadEl) return;
    const index = Number(turnIndex);
    const target = Number.isInteger(index)
      ? queryThreadEl.querySelector(`[data-query-turn-index="${index}"]`)
      : queryThreadEl.lastElementChild;
    if (!target || typeof target.scrollIntoView !== "function") return;
    window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
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
    queryReasonEl.innerHTML = `<p>${reasons.map(escapeHtml).join("<br>")}</p>`;
  }

  function renderFollowupButtons(items) {
    queryFollowupsEl.innerHTML = "";
  }

  function renderFollowupButtonsMarkup(items) {
    const followups = Array.isArray(items) ? items.slice(0, 4) : [];
    if (!followups.length) return "";
    return `<div class="query-followups" style="margin-top:12px;"><div class="query-followups-label">Suggested follow-up queries</div><div class="query-followups-list">${followups.map((item) => `<button type="button" class="query-chip" data-prompt="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("")}</div></div>`;
  }

  function queryActionContext(payload) {
    const context = payload && payload.action_context && typeof payload.action_context === "object"
      ? payload.action_context
      : {};
    const patientIds = Array.isArray(context.patient_ids) ? context.patient_ids.filter(Boolean) : [];
    const recordIds = Array.isArray(context.record_ids) ? context.record_ids.filter(Boolean) : [];
    return {
      patientIds,
      recordIds,
      idType: context.id_type || (recordIds.length ? "sample" : "patient"),
      analysisPrompt: typeof context.analysis_prompt === "string" ? context.analysis_prompt : "",
    };
  }

  function queryActionsMarkup(payload, sourcePrompt = "") {
    if (payload && payload.intent === "general_llm") return "";
    const submittedPrompt = String(sourcePrompt || "").trim();
    const actionContext = queryActionContext(payload);
    const patientIds = actionContext.patientIds;
    const recordIds = actionContext.recordIds;
    const availableActions = payload && payload.data && payload.data.available_actions && typeof payload.data.available_actions === "object"
      ? payload.data.available_actions
      : {};
    setLatestQueryState({
      ids: patientIds,
      recordIds,
      prompt: submittedPrompt,
      analysisPrompt: actionContext.analysisPrompt,
      idType: actionContext.idType,
    });
    if (patientIds.length || recordIds.length) {
      setLatestScopedContext({
        patientIds,
        recordIds,
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
    const canUsePheno = availableActions.use_in_pheno_ranker && (recordIds.length > 0 || allCompatible);
    const idsPayload = escapeHtml(patientIds.join(","));
    const scopeIds = recordIds.length ? recordIds : patientIds;
    const scopePayload = escapeHtml(scopeIds.join(","));
    return `
      <div class="query-actions query-actions-inline" style="margin-top:12px;">
        ${availableActions.open_in_analysis ? `<button type="button" class="query-chip action query-workflow-primary" data-query-action="use-analysis" data-query-patient-ids="${idsPayload}" data-query-scope-ids="${scopePayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 17 18 7"></path><path d="M9 7h9v9"></path><path d="M5 5h6"></path><path d="M5 11v8h8"></path></svg></span><span class="query-action-label">Open in Analysis</span></button>` : ""}
        ${availableActions.save_cohort ? `<button type="button" class="query-chip query-chip-deterministic query-workflow-secondary" data-query-action="save-cohort" data-query-patient-ids="${idsPayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v14H5z"></path><path d="M8 5v6h8V5"></path><path d="M9 19v-5h6v5"></path></svg></span><span class="query-action-label">Save cohort</span></button>` : ""}
        <details class="query-inline-actions">
          <summary><span class="query-inline-actions-more">More actions</span><span class="query-inline-actions-less">Less actions</span></summary>
          <div class="query-actions">
            ${availableActions.copy_patient_ids ? `<button type="button" class="query-chip query-chip-planner" data-query-action="copy-ids" data-query-patient-ids="${idsPayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M5 15V5a2 2 0 0 1 2-2h10"></path></svg></span><span class="query-action-label">Copy patient IDs</span></button>` : ""}
            ${canUsePheno ? `<button type="button" class="query-chip action" data-query-action="use-pheno" data-query-patient-ids="${idsPayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 17 18 7"></path><path d="M9 7h9v9"></path><path d="M5 5h6"></path><path d="M5 11v8h8"></path></svg></span><span class="query-action-label">Use IDs in Pheno-Ranker</span></button>` : ""}
            ${availableActions.use_in_pheno_ranker && !recordIds.length && phenoRankerPatientIds.length && !allCompatible ? '<span class="query-chip badge">This result is grouped at patient level. Pheno-Ranker needs the original record IDs or timepoints.</span>' : ""}
          </div>
        </details>
      </div>
    `;
  }

  function renderQueryActions(payload, sourcePrompt = "") {
    if (queryActionsEl) queryActionsEl.innerHTML = queryActionsMarkup(payload, sourcePrompt);
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
    const workspaceRevision = state.workspaceRevision;
    const requestIsStale = () => !generalQuestion && workspaceRevision !== state.workspaceRevision;
    state.queryInFlight = true;
    askBtnEl.disabled = true;
    queryStatusEl.className = "query-status loading";
    queryStatusEl.textContent = generalQuestion ? "Waiting for the model..." : "Running query. Waiting for response...";
    queryReplyEl.innerHTML = generalQuestion
      ? "<p><strong>Asking the model...</strong><br>Please wait.</p>"
      : "<p><strong>Running query...</strong><br>Please wait.</p>";
    queryReasonEl.innerHTML = "<p>Waiting for the response and its supporting context.</p>";
    if (queryActionsEl) queryActionsEl.innerHTML = "";
    queryFollowupsEl.innerHTML = "";
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
            scoped_patient_ids: state.queryFollowMemoryEnabled && state.latestScopedContext && Array.isArray(state.latestScopedContext.patientIds)
              ? state.latestScopedContext.patientIds
              : [],
            scoped_record_ids: state.queryFollowMemoryEnabled && state.latestScopedContext && Array.isArray(state.latestScopedContext.recordIds)
              ? state.latestScopedContext.recordIds
              : [],
            scoped_id_type: state.queryFollowMemoryEnabled && state.latestScopedContext && state.latestScopedContext.idType
              ? state.latestScopedContext.idType
              : "patient",
          }),
      });
      if (!response.ok) {
        const error = await response.json();
        if (requestIsStale()) return;
        queryReplyEl.innerHTML = `<p>${escapeHtml(error.detail)}</p>`;
        queryReasonEl.innerHTML = "<p>The request reached the API but returned an error response.</p>";
        queryDataEl.textContent = "";
        queryDetailsEl.open = false;
        if (queryActionsEl) queryActionsEl.innerHTML = "";
        state.queryTurns[state.queryTurns.length - 1] = {
          role: "assistant",
          payload: { intent: "query_error", reply: String(error.detail || "Query failed."), data: { source: "error", provider: "deterministic" } },
      };
      renderQueryThread();
      scrollQueryTurnIntoView(state.queryTurns.length - 1);
      queryStatusEl.className = "query-status";
        queryStatusEl.textContent = "Query failed.";
        return;
      }
      const payload = await response.json();
      if (requestIsStale()) return;
      stopQueryProgressUpdates();
      state.queryTurns[state.queryTurns.length - 1] = { role: "assistant", payload, contextMode: generalQuestion ? "general" : "workspace" };
      renderQueryThread();
      scrollQueryTurnIntoView(state.queryTurns.length - 1);
      queryReplyEl.innerHTML = renderQueryReply(payload);
      renderQueryReason(payload);
      renderQueryActions(payload, question);
      renderFollowupButtons(payload.data && payload.data.follow_up_suggestions);
      queryDataEl.textContent = JSON.stringify(payload.data, null, 2);
      queryDetailsEl.open = false;
      const contextMode = generalQuestion ? "general" : "workspace";
      state.queryHistory.push({ role: "user", content: question, context_mode: contextMode });
      state.queryHistory.push({ role: "assistant", content: payload.reply || "", context_mode: contextMode });
      state.queryHistory = state.queryHistory.slice(-16);
      state.queryExecutionMode = defaultQueryExecutionMode();
      renderQueryExecutionMode();
      queryStatusEl.className = "query-status is-hidden";
      queryStatusEl.textContent = "";
    } catch (error) {
      if (requestIsStale()) return;
      stopQueryProgressUpdates();
      queryReplyEl.innerHTML = `<p>${escapeHtml(error && error.message ? error.message : "Request failed.")}</p>`;
      queryReasonEl.innerHTML = "<p>The request failed before a valid response payload reached the UI.</p>";
      queryDataEl.textContent = "";
      queryDetailsEl.open = false;
      if (queryActionsEl) queryActionsEl.innerHTML = "";
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
      stopQueryProgressUpdates();
      state.queryInFlight = false;
      askBtnEl.disabled = false;
      questionEl.focus();
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
      if (state.latestQueryPatientIds.length) {
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
    state.queryExecutionMode = defaultQueryExecutionMode();
    renderQueryExecutionMode();
    questionEl.focus();
  }

  function handleDocumentClick(event) {
    const diseaseChip = event.target.closest("[data-query-disease-chip]");
    if (diseaseChip && queryDiseaseTopChipsEl && queryDiseaseTopChipsEl.contains(diseaseChip)) {
      preloadDiseaseCohort(diseaseChip.dataset.queryDiseaseChip || "");
      return;
    }
    const queryActionButton = event.target.closest("[data-query-action]");
    if (queryActionButton && queryTabEl && queryTabEl.contains(queryActionButton)) {
      const ids = String(queryActionButton.dataset.queryPatientIds || "").split(",").map((item) => item.trim()).filter(Boolean);
      if (queryActionButton.dataset.queryAction === "use-pheno") {
        sendPatientIdsToPhenoRanker();
        return;
      }
      if (queryActionButton.dataset.queryAction === "use-analysis") {
        const scopeIds = String(queryActionButton.dataset.queryScopeIds || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        setLatestQueryState({
          ids,
          recordIds: scopeIds.some((item) => item.includes(":")) ? scopeIds : [],
        });
        sendPatientIdsToAnalysis();
        return;
      }
      if (queryActionButton.dataset.queryAction === "copy-ids") {
        copyPatientIdsFromQuery(ids, queryActionButton);
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
      state.queryExecutionMode = defaultQueryExecutionMode();
      renderQueryExecutionMode();
      questionEl.focus();
    }
  }

  return {
    renderQueryReply,
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
