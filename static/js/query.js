export function createQueryUi(ctx) {
  const { refs, helpers, callbacks, state } = ctx;
  const {
    queryReplyEl,
    queryStatusEl,
    queryMetaEl,
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
    queryDiseaseTopChipsEl,
    queryDiseaseStatusEl,
  } = refs;
  const { escapeHtml, renderActivityCard, fallbackCopyText } = helpers;
  const {
    renderQueryStarterPrompts,
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
  } = callbacks;
  let diseaseOptions = [];

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
      const dataDir = encodeURIComponent(String(refs.dataDirEl && refs.dataDirEl.value ? refs.dataDirEl.value.trim() : ""));
      const response = await fetch(`/cohorts/diseases?data_dir=${dataDir}`);
      if (!response.ok) throw new Error("Unable to load diseases.");
      const payload = await response.json();
      const diseases = Array.isArray(payload) ? payload : [];
      diseaseOptions = diseases;
      renderTopDiseaseChips();
      if (queryDiseaseStatusEl) {
        queryDiseaseStatusEl.textContent = diseases.length
          ? `Click a disease to preload a deterministic cohort query.`
          : "No diseases are available in the current dataset.";
      }
    } catch (_error) {
      diseaseOptions = [];
      renderTopDiseaseChips();
      if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = "Unable to load disease cohort shortcuts.";
    }
  }

  function preloadDiseaseCohort(disease) {
    const normalized = String(disease || "").trim();
    if (!normalized) return;
    questionEl.value = `Which patients have ${disease}?`;
    state.queryExecutionMode = "auto";
    renderQueryExecutionMode();
    renderTopDiseaseChips();
    if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = `Prompt prepared for disease cohort ${normalized}. Press Ask to run.`;
    questionEl.focus();
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
      const rows = data.patients.slice(0, 100).map((item) => `
        <tr>
          <td>${escapeHtml(String(item.patient_id || ""))}</td>
          <td>${escapeHtml(String(item.sex || ""))}</td>
          <td>${escapeHtml(String(item.visit_count ?? ""))}</td>
          <td>${escapeHtml(String(item.medication_count ?? ""))}</td>
        </tr>
      `).join("");
      return `
        <div class="section-note">Matching patients (${data.patients.length}).</div>
        <table>
          <thead><tr><th>Patient</th><th>Sex</th><th>Visits</th><th>Medications</th></tr></thead>
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
      semantic_cohort_query: { label: "Cohort query", title: "A cohort-style query result returned by the app." },
      medication_cohort: { label: "Medication cohort", title: "Deterministic cohort lookup based on treatment labels in the dataset." },
      disease_cohort: { label: "Disease cohort", title: "Deterministic cohort lookup based on disease labels in the dataset." },
      patient_filter_cohort: { label: "Patient filter query", title: "Deterministic cohort filtering across multiple include or exclude conditions." },
      patient_transition_cohort: { label: "Transition query", title: "Deterministic query over patients who changed from one term to another over time." },
      patient_started_after_cohort: { label: "Started-after query", title: "Deterministic temporal query over patients who started one term after another." },
      patient_temporal_order_cohort: { label: "Temporal order query", title: "Deterministic temporal query over the order of events in patient timelines." },
      patient_inventory: { label: "Patient inventory", title: "Deterministic listing of patients in the current cohort." },
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

  function renderQueryBadge(label, title) {
    const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
    return `<span class="query-chip badge"${safeTitle}>${escapeHtml(label)}</span>`;
  }

  function getQueryProvenanceChips(payload) {
    const data = payload && payload.data ? payload.data : {};
    const intentInfo = queryIntentPresentation(payload && payload.intent ? payload.intent : "unknown");
    const chips = [renderQueryBadge(intentInfo.label, intentInfo.title)];
    if (data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio") {
      chips.push(renderQueryBadge("LLM-planned", "LM Studio translated the prompt into a constrained internal cohort plan."));
      chips.push(renderQueryBadge("Deterministic execution", "The app executed the planned query against local cohort data without using the model to produce the result."));
      if (data.planner.model) chips.push(renderQueryBadge(data.planner.model, "LM Studio model used for semantic query planning."));
      return chips;
    }
    chips.push(renderQueryBadge(data.provider === "lm_studio" ? "LLM answer" : "Deterministic", data.provider === "lm_studio"
      ? "LM Studio answered directly from the provided context."
      : "The app answered using deterministic dataset logic."));
    if (data.model) chips.push(renderQueryBadge(data.model, "LM Studio model used for this answer."));
    return chips;
  }

  function describeQueryProvenance(payload) {
    const data = payload && payload.data ? payload.data : {};
    if (data.execution === "deterministic" && data.planner && data.planner.provider === "lm_studio") {
      const model = data.planner.model ? ` using ${data.planner.model}` : "";
      return `LM Studio semantic planner${model} translated the request into an internal cohort plan, and the result was executed with deterministic dataset logic.`;
    }
    return `Provider: ${data.provider === "lm_studio" ? "LM Studio fallback" : "deterministic dataset logic"}.`;
  }

  function resetQueryWorkspace() {
    state.queryHistory = [];
    state.queryTurns = [];
    state.queryExecutionMode = "auto";
    renderTopDiseaseChips();
    if (queryDiseaseStatusEl) queryDiseaseStatusEl.textContent = "Click a disease to preload a deterministic cohort query.";
    setLatestQueryState({ ids: [], prompt: "", analysisPrompt: "", idType: "patient" });
    queryMetaEl.innerHTML = "";
    queryReplyEl.innerHTML = '<div class="empty">Ask about medications, diseases, or a patient timeline.</div>';
    queryReasonEl.innerHTML = '<div class="empty">Run a query to see how the answer was produced.</div>';
    if (queryActionsEl) queryActionsEl.innerHTML = "";
    queryFollowupsEl.innerHTML = "";
    queryDataEl.textContent = "";
    queryDetailsEl.open = false;
    renderQueryExecutionMode();
    renderQueryStarterPrompts();
    renderQueryThread();
  }

  function renderQueryThread() {
    renderQueryStarterPrompts();
    if (!queryThreadEl) return;
    if (queryTabEl) queryTabEl.classList.toggle("query-tab-empty", !state.queryTurns.length);
    if (!state.queryTurns.length) {
      queryThreadEl.innerHTML = '<div class="empty">Ask a query to start a conversational thread. Follow-up questions will reuse recent query history.</div>';
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
        return `<article class="analysis-turn query-thread-turn query-thread-turn-user"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${escapeHtml(turn.prompt || "")}</p></div></article>`;
      }
      const payload = turn.payload || {};
      const data = payload.data || {};
      const toneClass = turn.pending ? "query-thread-turn-pending" : data.source === "error" ? "query-thread-turn-error" : "query-thread-turn-assistant";
      return `
        <article class="analysis-turn query-thread-turn ${toneClass}">
          <div class="analysis-turn-label">${turn.pending ? "Running" : "Assistant"}</div>
          ${turn.pending ? "" : `<div class="query-thread-turn-meta">${getQueryProvenanceChips(payload).join("")}</div>`}
          <div class="analysis-turn-body">
            ${turn.pending ? renderActivityCard(turn.pendingLabel || "Running query", turn.pendingDetail || "Working through the query and preparing cohort-aware results.") : renderQueryReply(payload)}
            ${!turn.pending && index === latestAssistantIndex ? queryActionsMarkup(payload) : ""}
            ${!turn.pending && index === latestAssistantIndex ? renderFollowupButtonsMarkup(payload.data && payload.data.follow_up_suggestions) : ""}
          </div>
        </article>
      `;
    }).join("");
  }

  function renderQueryMeta(payload) {
    queryMetaEl.innerHTML = getQueryProvenanceChips(payload).join("");
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

  function inferRecordIdsFromQueryPayload(payload) {
    const fromSampleData = payload && payload.data && Array.isArray(payload.data.sample_ids)
      ? payload.data.sample_ids.filter(Boolean)
      : [];
    if (fromSampleData.length) return Array.from(new Set(fromSampleData));
    const fromOriginalData = payload && payload.data && Array.isArray(payload.data.original_record_ids)
      ? payload.data.original_record_ids.filter(Boolean)
      : [];
    if (fromOriginalData.length) return Array.from(new Set(fromOriginalData));
    const fromPatientOriginalIds = payload && payload.data && Array.isArray(payload.data.patients)
      ? payload.data.patients.flatMap((item) => Array.isArray(item && item.original_record_ids) ? item.original_record_ids : []).filter(Boolean)
      : [];
    if (fromPatientOriginalIds.length) return Array.from(new Set(fromPatientOriginalIds));
    return [];
  }

  function inferPatientIdsFromQueryPayload(payload) {
    const fromData = payload && payload.data && Array.isArray(payload.data.patient_ids)
      ? payload.data.patient_ids.filter(Boolean)
      : [];
    if (fromData.length) return fromData;
    const fromPatientObjects = payload && payload.data && Array.isArray(payload.data.patients)
      ? payload.data.patients.map((item) => item && item.patient_id).filter(Boolean)
      : [];
    if (fromPatientObjects.length) return fromPatientObjects;
    const replyText = String((payload && payload.reply) || "");
    const knownIds = currentPatientsProvider().map((patient) => patient.patient_id).filter(Boolean);
    const found = [];
    for (const patientId of knownIds) {
      const escaped = patientId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const pattern = new RegExp(`(^|[^A-Za-z0-9_])${escaped}($|[^A-Za-z0-9_])`, "i");
      if (pattern.test(replyText) && !found.includes(patientId)) found.push(patientId);
    }
    if (found.length) return found;
    const inferred = [];
    const lines = replyText.split("\r\n").join("\n").split("\n");
    for (const line of lines) {
      const trimmed = line.trim().replace(/^[-*]\s+/, "");
      if (!trimmed) continue;
      const match = trimmed.match(/^([A-Za-z]*_?\d+(?::[A-Za-z0-9_-]+)?)$/);
      if (match && !inferred.includes(match[1])) inferred.push(match[1]);
    }
    if (inferred.length) return inferred;
    const inlineMatches = replyText.match(/\b(?:[A-Za-z]+_)?\d+(?::[A-Za-z0-9_-]+)?\b/g) || [];
    for (const token of inlineMatches) {
      if (!inferred.includes(token)) inferred.push(token);
    }
    return inferred;
  }

  function queryActionsMarkup(payload) {
    const patientIds = inferPatientIdsFromQueryPayload(payload);
    const recordIds = inferRecordIdsFromQueryPayload(payload);
    setLatestQueryState({
      ids: patientIds,
      recordIds,
      prompt: questionEl.value.trim(),
      analysisPrompt: patientIds.length ? "Interpret this selected cohort and summarize the main clinical and treatment patterns." : "",
      idType: "patient",
    });
    if (!patientIds.length) return "";
    const phenoRankerPatientIds = phenoRankerPatientIdsProvider();
    const compatibleIds = phenoRankerPatientIds.length ? patientIds.filter((patientId) => phenoRankerPatientIds.includes(patientId)) : [];
    const allCompatible = patientIds.length > 0 && compatibleIds.length === patientIds.length;
    const idsPayload = escapeHtml(patientIds.join(","));
    const scopeIds = recordIds.length ? recordIds : patientIds;
    const scopePayload = escapeHtml(scopeIds.join(","));
    return `
      <div class="query-actions query-actions-inline" style="margin-top:12px;">
        <button type="button" class="query-chip action query-workflow-primary" data-query-action="use-analysis" data-query-patient-ids="${idsPayload}" data-query-scope-ids="${scopePayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 17 18 7"></path><path d="M9 7h9v9"></path><path d="M5 5h6"></path><path d="M5 11v8h8"></path></svg></span><span class="query-action-label">Open in Analysis</span></button>
        <button type="button" class="query-chip query-chip-deterministic query-workflow-secondary" data-query-action="save-cohort" data-query-patient-ids="${idsPayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v14H5z"></path><path d="M8 5v6h8V5"></path><path d="M9 19v-5h6v5"></path></svg></span><span class="query-action-label">Save cohort</span></button>
        <details class="query-inline-actions">
          <summary><span class="query-inline-actions-more">More actions</span><span class="query-inline-actions-less">Less actions</span></summary>
          <div class="query-actions">
            <button type="button" class="query-chip query-chip-planner" data-query-action="copy-ids" data-query-patient-ids="${idsPayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M5 15V5a2 2 0 0 1 2-2h10"></path></svg></span><span class="query-action-label">Copy patient IDs</span></button>
            ${allCompatible ? `<button type="button" class="query-chip action" data-query-action="use-pheno" data-query-patient-ids="${idsPayload}"><span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 17 18 7"></path><path d="M9 7h9v9"></path><path d="M5 5h6"></path><path d="M5 11v8h8"></path></svg></span><span class="query-action-label">Use IDs in Pheno-Ranker</span></button>` : ""}
            ${phenoRankerPatientIds.length && !allCompatible ? '<span class="query-chip badge">This result is grouped at patient level. Pheno-Ranker needs the original record IDs or timepoints.</span>' : ""}
          </div>
        </details>
      </div>
    `;
  }

  function renderQueryActions(payload) {
    if (queryActionsEl) queryActionsEl.innerHTML = queryActionsMarkup(payload);
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
    if (!question) {
      queryStatusEl.textContent = "Enter a question first.";
      return;
    }
    state.queryInFlight = true;
    askBtnEl.disabled = true;
    queryStatusEl.className = "query-status loading";
    queryStatusEl.textContent = "Running query. Waiting for response...";
    queryReplyEl.innerHTML = "<p><strong>Running query...</strong><br>Please wait.</p>";
    queryReasonEl.innerHTML = "<p>Waiting for the response and its supporting context.</p>";
    queryMetaEl.innerHTML = "";
    if (queryActionsEl) queryActionsEl.innerHTML = "";
    setLatestQueryState({ ids: [] });
    queryFollowupsEl.innerHTML = "";
    state.queryTurns.push({ role: "user", prompt: question });
    state.queryTurns.push({
      role: "assistant",
      pending: true,
      pendingLabel: "Parsing request",
      pendingDetail: "Interpreting the cohort question and selecting the right query path.",
      payload: { reply: "Running query..." },
    });
    renderQueryThread();
    startQueryProgressUpdates();
    await nextFrame();
    try {
      const response = await fetch("/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          q: question,
          data_dir: refs.dataDirEl.value.trim(),
          query_mode: queryMode,
          history: state.queryHistory.slice(-6),
        }),
      });
      if (!response.ok) {
        const error = await response.json();
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
        queryStatusEl.className = "query-status";
        queryStatusEl.textContent = "Query failed.";
        return;
      }
      const payload = await response.json();
      stopQueryProgressUpdates();
      state.queryTurns[state.queryTurns.length - 1] = { role: "assistant", payload };
      renderQueryThread();
      queryReplyEl.innerHTML = renderQueryReply(payload);
      renderQueryMeta(payload);
      renderQueryReason(payload);
      renderQueryActions(payload);
      renderFollowupButtons(payload.data && payload.data.follow_up_suggestions);
      queryDataEl.textContent = JSON.stringify(payload.data, null, 2);
      queryDetailsEl.open = false;
      state.queryHistory.push({ role: "user", content: question });
      state.queryHistory.push({ role: "assistant", content: payload.reply || "" });
      state.queryHistory = state.queryHistory.slice(-8);
      state.queryExecutionMode = "auto";
      renderQueryExecutionMode();
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "Done.";
    } catch (error) {
      stopQueryProgressUpdates();
      queryReplyEl.innerHTML = `<p>${escapeHtml(error && error.message ? error.message : "Request failed.")}</p>`;
      queryReasonEl.innerHTML = "<p>The request failed before a valid response payload reached the UI.</p>";
      queryDataEl.textContent = "";
      queryDetailsEl.open = false;
      if (queryActionsEl) queryActionsEl.innerHTML = "";
      setLatestQueryState({ ids: [] });
      state.queryTurns[state.queryTurns.length - 1] = {
        role: "assistant",
        payload: { intent: "query_error", reply: error && error.message ? error.message : "Request failed.", data: { source: "error", provider: "deterministic" } },
      };
      renderQueryThread();
      state.queryExecutionMode = "auto";
      renderQueryExecutionMode();
      queryStatusEl.className = "query-status";
      queryStatusEl.textContent = "Network error.";
    } finally {
      stopQueryProgressUpdates();
      state.queryInFlight = false;
      askBtnEl.disabled = false;
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
        refs.analysisSelectedPatientIdsEl.value = state.latestQueryPatientIds.join(",");
      }
      sendPromptToAnalysis(analysisButton.dataset.analysisPrompt, {
        llmOnly: analysisButton.dataset.analysisLlmOnly === "true",
      });
      return;
    }
    const button = event.target.closest("[data-prompt]");
    if (!button || !queryExamplesEl.contains(button)) return;
    questionEl.value = button.dataset.prompt;
    state.queryExecutionMode = "auto";
    renderQueryExecutionMode();
    questionEl.focus();
  }

  function handleQueryFollowupsClick(event) {
    const button = event.target.closest("[data-prompt]");
    if (!button || !queryFollowupsEl.contains(button)) return;
    questionEl.value = button.dataset.prompt;
    state.queryExecutionMode = "auto";
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
      state.queryExecutionMode = "auto";
      renderQueryExecutionMode();
      questionEl.focus();
    }
  }

  return {
    renderQueryReply,
    renderQueryMeta,
    renderQueryReason,
    renderQueryActions,
    renderQueryExecutionMode,
    resetQueryWorkspace,
    renderQueryThread,
    askQuery,
    loadDiseaseOptions,
    preloadDiseaseCohort,
    handleQueryExamplesClick,
    handleQueryFollowupsClick,
    handleDocumentClick,
    setExecutionMode(value) {
      state.queryExecutionMode = value;
    },
  };
}
