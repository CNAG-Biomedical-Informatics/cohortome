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
  const QUERY_RESULT_PAGE_SIZE = 50;
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

  function renderQueryStructuredTable(payload, navigation = {}) {
    const data = payload && payload.data ? payload.data : {};
    if (!data || typeof data !== "object") {
      return "";
    }
    const resultPage = queryResultPage(payload);
    const actionContext = payload && payload.action_context && typeof payload.action_context === "object"
      ? payload.action_context
      : {};
    const sampleLevel = String(actionContext.id_type || "patient") === "sample";
    const resultRows = resultPage.rows.length
      ? resultPage.rows
      : sampleLevel
        ? resultPage.sampleIds.map((sampleId) => ({ sample_id: sampleId }))
        : resultPage.patientIds.map((patientId) => ({ patient_id: patientId }));
    if (resultRows.length) {
      const currentPatients = Array.isArray(currentPatientsProvider()) ? currentPatientsProvider() : [];
      const provenanceByPatientId = new Map(currentPatients.map((item) => [
        String(item.patient_id || ""),
        Array.isArray(item.dataset_names) ? item.dataset_names : [],
      ]));
      const showDataset = isMultiDatasetWorkspace();
      const rows = resultRows.slice(0, QUERY_RESULT_PAGE_SIZE).map((item, index) => sampleLevel ? `
        <tr><td class="query-result-id-cell">${escapeHtml(String(item.sample_id || item.record_id || resultPage.sampleIds[index] || ""))}</td></tr>
      ` : `
        <tr>
          <td class="query-result-id-cell">${escapeHtml(String(item.patient_id || resultPage.patientIds[index] || ""))}</td>
          ${showDataset ? `<td>${escapeHtml((provenanceByPatientId.get(String(item.patient_id || "")) || []).join(", ") || "n/a")}</td>` : ""}
          <td>${escapeHtml(String(item.sex || ""))}</td>
          <td>${escapeHtml(String(item.visit_count ?? ""))}</td>
          <td>${escapeHtml(String(item.medication_count ?? ""))}</td>
        </tr>
      `).join("");
      const startOffset = Math.max(0, Number(navigation.start || 0));
      const pageCount = Math.max(resultRows.length, resultPage.returnedCount);
      const start = pageCount ? startOffset + 1 : 0;
      const end = Math.min(resultPage.totalCount || startOffset + pageCount, startOffset + pageCount);
      const total = resultPage.totalCount || end;
      const hasPrevious = Array.isArray(navigation.previous) && navigation.previous.length > 0;
      const navigationError = String(navigation.error || "").trim();
      const terminalResult = Boolean(navigation.terminal);
      const loading = Boolean(navigation.loading);
      const paging = resultPage.resultHandle || terminalResult ? `
        <div class="query-result-pagination" aria-live="polite">
          <span class="query-result-range">Showing ${escapeHtml(String(start))}–${escapeHtml(String(end))} of ${escapeHtml(String(total))}</span>
          <span class="query-result-boundary-note">${terminalResult ? "This bounded page remains visible, but the server-side result is no longer active." : "Only this page is kept in the browser."}</span>
          <span class="query-result-page-actions">
            ${resultPage.resultHandle && hasPrevious ? `<button type="button" class="query-chip query-chip-deterministic" data-query-page-action="previous" ${loading ? "disabled" : ""}>Previous</button>` : ""}
            ${resultPage.resultHandle && resultPage.hasMore && resultPage.nextCursor ? `<button type="button" class="query-chip query-chip-deterministic" data-query-page-action="next" ${loading ? "disabled" : ""}>${loading ? "Loading…" : "Load more"}</button>` : ""}
          </span>
        </div>
        ${navigationError ? `<div class="query-result-page-error" role="status">${escapeHtml(navigationError)}</div>` : ""}
      ` : `<div class="section-note">Matching ${sampleLevel ? "samples" : "patients"} (${escapeHtml(String(total))}).</div>`;
      return `
        ${paging}
        <div class="query-result-table-scroll">
        <table class="query-result-table">
          <thead>${sampleLevel
            ? "<tr><th>Sample</th></tr>"
            : `<tr><th>Patient</th>${showDataset ? "<th>Dataset</th>" : ""}<th>Sex</th><th>Visits</th><th>Medications</th></tr>`}</thead>
          <tbody>${rows}</tbody>
        </table>
        </div>
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

  function renderQueryReply(payloadOrValue, navigation = {}) {
    const value = typeof payloadOrValue === "object" && payloadOrValue ? queryDisplayReply(payloadOrValue) : payloadOrValue;
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
    const structured = typeof payloadOrValue === "object" && payloadOrValue ? renderQueryStructuredTable(payloadOrValue, navigation) : "";
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
    setLatestQueryState({ ids: [], recordIds: [], resultHandle: "", totalCount: 0, prompt: "", analysisPrompt: "", idType: "patient" });
    setLatestScopedContext({ patientIds: [], recordIds: [], resultHandle: "", totalCount: 0, idType: "patient", sourceTab: "", prompt: "" });
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
            ${turn.pending ? renderActivityCard(turn.pendingLabel || "Running query", turn.pendingDetail || "Working through the query and preparing cohort-aware results.") : renderQueryReply(payload, turn.resultNavigation || {})}
            ${!turn.pending && index === latestAssistantIndex ? queryActionsMarkup(payload, sourcePrompt) : ""}
            ${!turn.pending && index === latestAssistantIndex ? renderFollowupButtonsMarkup(data.follow_up_suggestions, data.follow_up_suggestion_metadata) : ""}
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

  function renderFollowupButtonsMarkup(items, metadataItems) {
    const followups = Array.isArray(items) ? items.slice(0, 4) : [];
    if (!followups.length) return "";
    const metadataByPrompt = new Map(
      (Array.isArray(metadataItems) ? metadataItems : [])
        .filter((item) => item && typeof item === "object" && String(item.prompt || "").trim())
        .map((item) => [String(item.prompt).trim(), item]),
    );
    const buttons = followups.map((item) => {
      const prompt = String(item || "").trim();
      const metadata = metadataByPrompt.get(prompt) || {};
      const deterministic = metadata.execution_kind === "deterministic" || metadata.execution_mode === "deterministic_only";
      const executionMode = deterministic ? "deterministic_only" : "planner_only";
      const cssClass = deterministic ? "query-chip-deterministic" : "query-chip-planner";
      const label = deterministic ? "Deterministic" : "LLM-planned";
      const title = deterministic
        ? "Runs with deterministic dataset logic; no LLM planning is requested."
        : "Uses the LLM semantic planner, then executes the resulting dataset query deterministically.";
      return `<button type="button" class="query-chip ${cssClass}" data-prompt="${escapeHtml(prompt)}" data-query-followup-mode="${executionMode}" title="${escapeHtml(title)}"><span>${escapeHtml(prompt)}</span><span class="followup-mode-label">${label}</span></button>`;
    }).join("");
    return `<div class="query-followups" style="margin-top:12px;"><div class="query-followups-label">Suggested follow-up queries</div><div class="query-followups-list">${buttons}</div></div>`;
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

  function queryActionsMarkup(payload, sourcePrompt = "") {
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
    const canUsePheno = !resultHandle && availableActions.use_in_pheno_ranker && (recordIds.length > 0 || allCompatible);
    const canCopyIds = !resultHandle && availableActions.copy_patient_ids && patientIds.length > 0;
    const incompatiblePheno = !resultHandle && availableActions.use_in_pheno_ranker && !recordIds.length && phenoRankerPatientIds.length && !allCompatible;
    const moreActions = canCopyIds || canUsePheno || incompatiblePheno;
    return `
      <div class="query-actions query-actions-inline" style="margin-top:12px;">
        ${availableActions.open_in_analysis ? `<button type="button" class="query-chip action query-workflow-primary" data-query-action="use-analysis"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 17 18 7"></path><path d="M9 7h9v9"></path><path d="M5 5h6"></path><path d="M5 11v8h8"></path></svg></span><span class="query-action-label">Open in Analysis</span></button>` : ""}
        ${availableActions.save_cohort ? `<button type="button" class="query-chip query-chip-deterministic query-workflow-secondary" data-query-action="save-cohort"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v14H5z"></path><path d="M8 5v6h8V5"></path><path d="M9 19v-5h6v5"></path></svg></span><span class="query-action-label">Save cohort</span></button>` : ""}
        ${moreActions ? `<details class="query-inline-actions">
          <summary><span class="query-inline-actions-more">More actions</span><span class="query-inline-actions-less">Less actions</span></summary>
          <div class="query-actions">
            ${canCopyIds ? `<button type="button" class="query-chip query-chip-planner" data-query-action="copy-ids"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M5 15V5a2 2 0 0 1 2-2h10"></path></svg></span><span class="query-action-label">Copy patient IDs</span></button>` : ""}
            ${canUsePheno ? `<button type="button" class="query-chip action" data-query-action="use-pheno"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 17 18 7"></path><path d="M9 7h9v9"></path><path d="M5 5h6"></path><path d="M5 11v8h8"></path></svg></span><span class="query-action-label">Use IDs in Pheno-Ranker</span></button>` : ""}
            ${incompatiblePheno ? '<span class="query-chip badge">This result is grouped at patient level. Pheno-Ranker needs the original record IDs or timepoints.</span>' : ""}
          </div>
        </details>` : (resultHandle && availableActions.save_cohort ? '<span class="section-note-inline">Save this result as a cohort before using it in Pheno-Ranker.</span>' : "")}
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
    const submittedScope = !generalQuestion && state.queryFollowMemoryEnabled && state.latestScopedContext
      ? {
        patientIds: Array.isArray(state.latestScopedContext.patientIds) ? state.latestScopedContext.patientIds.slice(0, QUERY_RESULT_PAGE_SIZE) : [],
        recordIds: Array.isArray(state.latestScopedContext.recordIds) ? state.latestScopedContext.recordIds.slice(0, QUERY_RESULT_PAGE_SIZE) : [],
        resultHandle: String(state.latestScopedContext.resultHandle || "").trim(),
        idType: String(state.latestScopedContext.idType || "patient"),
      }
      : { patientIds: [], recordIds: [], resultHandle: "", idType: "patient" };
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
    state.queryTurns = state.queryTurns.slice(-16);
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
      queryReplyEl.innerHTML = renderQueryReply(payload);
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

  async function loadQueryResultPage(turnIndex, direction) {
    const index = Number(turnIndex);
    const turn = Number.isInteger(index) ? state.queryTurns[index] : null;
    if (!turn || !turn.payload || turn.pending) return;
    const currentPage = queryResultPage(turn.payload);
    if (!currentPage.resultHandle) return;
    const currentNavigation = turn.resultNavigation && typeof turn.resultNavigation === "object"
      ? turn.resultNavigation
      : { cursor: "", start: 0, previous: [], loading: false, error: "" };
    const previous = Array.isArray(currentNavigation.previous) ? currentNavigation.previous.slice() : [];
    let targetCursor = "";
    let targetStart = 0;
    let nextPrevious = previous;
    if (direction === "next") {
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
      if (targetCursor) parameters.set("cursor", targetCursor);
      const response = await fetch(
        `/query-results/${encodeURIComponent(currentPage.resultHandle)}?${parameters.toString()}`,
        { cache: "no-store" },
      );
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
            queryReplyEl.innerHTML = renderQueryReply(turn.payload, turn.resultNavigation || {});
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
        start: targetStart,
        previous: nextPrevious,
        loading: false,
        error: "",
      };
      renderQueryThread();
      if (index === state.queryTurns.length - 1) {
        queryReplyEl.innerHTML = renderQueryReply(turn.payload, turn.resultNavigation);
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
