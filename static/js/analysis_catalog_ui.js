export function createAnalysisCatalogUi(ctx) {
  const { refs, state, helpers, callbacks, constants } = ctx;
  const {
    queryStarterPanelEl,
    queryPlannerBtnEl,
    queryMemoryBtnEl,
    queryGranularityModeValueEl,
    queryPolicyInfoBtnEl,
    analysisStarterPanelEl,
    analysisComposerExamplesBtnEl,
    analysisCatalogStatusEl,
    analysisCatalogListEl,
    analysisCatalogBrowseBtnEl,
    analysisCatalogDrawerEl,
    analysisCatalogDrawerListEl,
    analysisCatalogMolecularPanelEl,
    analysisCatalogMolecularStatusEl,
    analysisPromptEl,
    analysisCompareModeEl,
    analysisStatusEl,
  } = refs;
  const { escapeHtml } = helpers;
  const { MAX_VISIBLE_EXAMPLES } = constants;
  const {
    queryWorkspacePolicyExplanation,
    renderMolecularDatasetSelector,
    renderAnalysisCompareMode,
    syncCurrentAnalysisSessionFromUi,
    currentDatasetSelectionKey,
    isWorkspaceAccessible,
  } = callbacks;

  function initializeExampleToggle(container, maxVisible = MAX_VISIBLE_EXAMPLES) {
    if (!container) {
      return;
    }
    const chips = Array.from(container.querySelectorAll(".query-chip"))
      .filter((chip) => !chip.classList.contains("badge") && !chip.classList.contains("query-chip-toggle"));
    if (chips.length <= maxVisible) {
      return;
    }
    chips.forEach((chip, index) => {
      chip.classList.toggle("is-extra-example", index >= maxVisible);
    });
    container.classList.add("is-collapsed");

    const toggleWrap = document.createElement("div");
    toggleWrap.className = "query-examples-toggle";

    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "query-chip query-chip-toggle";
    toggleBtn.textContent = `See more (${chips.length - maxVisible})`;
    toggleBtn.addEventListener("click", () => {
      const expanded = container.classList.toggle("is-collapsed");
      toggleBtn.textContent = expanded ? `See more (${chips.length - maxVisible})` : "Show fewer";
    });

    toggleWrap.appendChild(toggleBtn);
    container.insertAdjacentElement("afterend", toggleWrap);
  }

  function renderStarterPanelVisibility(panelEl, composerToggleEl, hasTurns, pinnedOpen) {
    if (!panelEl || !composerToggleEl) {
      return;
    }
    const visible = hasTurns ? pinnedOpen : true;
    panelEl.hidden = !visible;
    panelEl.classList.toggle("is-hidden", !visible);
    const inlineToggle = panelEl.querySelector(".query-examples-toggle");
    if (inlineToggle) {
      inlineToggle.hidden = !visible;
      inlineToggle.classList.toggle("is-hidden", !visible);
    }
    const siblingToggle = panelEl.nextElementSibling && panelEl.nextElementSibling.classList && panelEl.nextElementSibling.classList.contains("query-examples-toggle")
      ? panelEl.nextElementSibling
      : null;
    if (siblingToggle) {
      siblingToggle.hidden = !visible;
      siblingToggle.classList.toggle("is-hidden", !visible);
    }
    composerToggleEl.hidden = !hasTurns;
    composerToggleEl.textContent = "Starter prompts";
  }

  function renderQueryStarterPrompts() {
    if (!queryStarterPanelEl) {
      return;
    }
    queryStarterPanelEl.hidden = false;
    const siblingToggle = queryStarterPanelEl.nextElementSibling && queryStarterPanelEl.nextElementSibling.classList && queryStarterPanelEl.nextElementSibling.classList.contains("query-examples-toggle")
      ? queryStarterPanelEl.nextElementSibling
      : null;
    if (siblingToggle) {
      siblingToggle.hidden = false;
    }
  }

  function renderQueryExecutionMode() {
    if (queryPlannerBtnEl) {
      const active = state.queryExecutionMode === "planner_only";
      queryPlannerBtnEl.classList.toggle("is-active", active);
      queryPlannerBtnEl.setAttribute("aria-pressed", active ? "true" : "false");
      queryPlannerBtnEl.title = active
        ? "Semantic planner is enabled for the next query."
        : "Skip deterministic matching for the next query and use the LLM planner first.";
    }
    if (queryMemoryBtnEl) {
      const scopeAvailable = state.queryGranularityMode === "detailed";
      queryMemoryBtnEl.classList.toggle("is-active", state.queryFollowMemoryEnabled);
      queryMemoryBtnEl.setAttribute("aria-pressed", state.queryFollowMemoryEnabled ? "true" : "false");
      queryMemoryBtnEl.disabled = !scopeAvailable;
      queryMemoryBtnEl.classList.toggle("is-hidden", !scopeAvailable);
      queryMemoryBtnEl.title = !scopeAvailable
        ? "Prompt scope is unavailable in Summary mode."
        : state.queryFollowMemoryEnabled
          ? "Prompt scope follows the previous Query result for patient-oriented follow-up questions."
          : "Prompt scope is the current workspace unless you explicitly select scope elsewhere.";
      const scopedPatientIds = state.latestScopedContext && Array.isArray(state.latestScopedContext.patientIds)
        ? state.latestScopedContext.patientIds
        : [];
      const labelEl = queryMemoryBtnEl.querySelector("span:last-child");
      if (labelEl) {
        if (!scopeAvailable) {
          labelEl.textContent = "Prompt scope";
        } else if (!state.queryFollowMemoryEnabled) {
          labelEl.textContent = "Prompt scope: workspace";
        } else if (scopedPatientIds.length) {
          labelEl.textContent = `Prompt scope: previous result (${scopedPatientIds.length} patients)`;
        } else {
          labelEl.textContent = "Prompt scope: waiting for previous result";
        }
      }
    }
    if (queryGranularityModeValueEl) {
      queryGranularityModeValueEl.textContent = state.queryGranularityMode === "detailed" ? "Detailed" : "Summary";
      queryGranularityModeValueEl.title = state.queryGranularityMode === "detailed"
        ? "This workspace allows detailed in-app Query results."
        : "This workspace is limited to summary-level in-app Query results.";
    }
    if (queryPolicyInfoBtnEl) {
      const explanation = queryWorkspacePolicyExplanation();
      queryPolicyInfoBtnEl.classList.toggle("is-hidden", !explanation);
      queryPolicyInfoBtnEl.classList.toggle("is-warning", Boolean(explanation));
      queryPolicyInfoBtnEl.title = explanation || "Workspace policy details";
      queryPolicyInfoBtnEl.setAttribute("aria-label", explanation || "Workspace policy details");
    }
  }

  function renderAnalysisStarterPrompts() {
    if (!analysisStarterPanelEl || !analysisComposerExamplesBtnEl) {
      return;
    }
    analysisStarterPanelEl.hidden = false;
    analysisStarterPanelEl.classList.remove("is-hidden");
    const inlineToggle = analysisStarterPanelEl.querySelector(".query-examples-toggle");
    if (inlineToggle) {
      inlineToggle.hidden = false;
      inlineToggle.classList.remove("is-hidden");
    }
    const siblingToggle = analysisStarterPanelEl.nextElementSibling && analysisStarterPanelEl.nextElementSibling.classList && analysisStarterPanelEl.nextElementSibling.classList.contains("query-examples-toggle")
      ? analysisStarterPanelEl.nextElementSibling
      : null;
    if (siblingToggle) {
      siblingToggle.hidden = false;
      siblingToggle.classList.remove("is-hidden");
    }
    analysisComposerExamplesBtnEl.hidden = !(Array.isArray(state.analysisTurns) && state.analysisTurns.length > 0);
    analysisComposerExamplesBtnEl.textContent = "Catalog & prompts";
  }

  function normalizeAnalysisCatalogExecutionMode(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "deterministic") return "deterministic";
    if (normalized === "llm_only") return "llm_only";
    return "auto";
  }

  function analysisCatalogModeBadge(item) {
    const mode = String(item && item.execution_mode ? item.execution_mode : "auto");
    if (mode === "deterministic") {
      return { css: "query-chip-deterministic", label: "Deterministic" };
    }
    if (mode === "llm_only") {
      return { css: "query-chip-llm", label: "LLM answer" };
    }
    return { css: "query-chip-planner", label: "LLM-planned" };
  }

  function analysisCatalogIconSvg(kind) {
    const icons = {
      clinical: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
      compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7h8"></path><path d="M8 17h8"></path><path d="m6 9 2-2 2 2"></path><path d="m18 15-2 2-2-2"></path></svg>',
      trajectory: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 18h16"></path><path d="m5 15 4-4 3 2 7-7"></path></svg>',
      survival: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5"></path><path d="M4 19h16"></path><path d="m6 7 4 5 3-3 5 6"></path></svg>',
      molecular: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3c0 4 3 4 3 8s-3 4-3 8"></path><path d="M17 3c0 4-3 4-3 8s3 4 3 8"></path><path d="M8 6h8"></path><path d="M8 18h8"></path></svg>',
      external: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5"></path><path d="M10 14 19 5"></path><path d="M19 14v5H5V5h5"></path></svg>',
      general: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="3"></rect><path d="M8 8h8"></path><path d="M8 12h8"></path><path d="M8 16h5"></path></svg>',
    };
    return icons[kind] || icons.general;
  }

  function analysisCatalogIconKind(item) {
    const runnerType = String(item && item.runner_type ? item.runner_type : "").toLowerCase();
    if (runnerType && runnerType !== "builtin") return "external";
    const category = String(item && item.category ? item.category : "").toLowerCase();
    const id = String(item && item.id ? item.id : "").toLowerCase();
    if (category.includes("survival") || id.includes("survival") || id.includes("kaplan")) return "survival";
    if (category.includes("trajectory") || id.includes("trajectory")) return "trajectory";
    if (category.includes("molecular") || id.includes("molecular") || id.includes("volcano")) return "molecular";
    if (category.includes("compare") || id.includes("compare")) return "compare";
    if (category.includes("clinical") || id.includes("summary")) return "clinical";
    return "general";
  }

  function selectedAnalysisMolecularDatasetNames() {
    return Array.isArray(state.selectedMolecularDatasets)
      ? state.selectedMolecularDatasets.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
  }

  function currentAnalysisCatalogItem() {
    return Array.isArray(state.analysisCatalogItems)
      ? state.analysisCatalogItems.find((item) => String(item && item.id ? item.id : "") === String(state.analysisSelectedCatalogItemId || ""))
      : null;
  }

  function renderAnalysisCatalogMolecularPanel() {
    if (!analysisCatalogMolecularPanelEl || !analysisCatalogMolecularStatusEl) {
      return;
    }
    renderMolecularDatasetSelector();
    const item = currentAnalysisCatalogItem();
    const requiresMolecular = Boolean(item && item.requires_molecular);
    analysisCatalogMolecularPanelEl.classList.toggle("is-hidden", !requiresMolecular);
    if (!requiresMolecular) {
      return;
    }
    const selectedDatasetNames = selectedAnalysisMolecularDatasetNames();
    if (String(item.id || "") === "molecular-differential-expression") {
      if (selectedDatasetNames.length === 1) {
        analysisCatalogMolecularStatusEl.textContent = `Selected dataset: ${selectedDatasetNames[0]}. Differential expression will use this transcriptomics matrix.`;
      } else if (selectedDatasetNames.length > 1) {
        analysisCatalogMolecularStatusEl.textContent = `Selected ${selectedDatasetNames.length} molecular datasets. Differential expression requires exactly one dataset.`;
      } else {
        analysisCatalogMolecularStatusEl.textContent = "Select exactly one molecular dataset for differential expression. The cohorts define the groups; the dataset defines the transcriptomics matrix.";
      }
      return;
    }
    if (selectedDatasetNames.length === 1) {
      analysisCatalogMolecularStatusEl.textContent = `Selected dataset: ${selectedDatasetNames[0]}.`;
    } else if (selectedDatasetNames.length > 1) {
      analysisCatalogMolecularStatusEl.textContent = `${selectedDatasetNames.length} molecular datasets selected for this analysis.`;
    } else {
      analysisCatalogMolecularStatusEl.textContent = "Select the molecular dataset or datasets for this analysis.";
    }
  }

  function analysisCatalogUiAvailability(item) {
    let available = Boolean(item && item.available);
    let unavailableReason = String(item && item.unavailable_reason ? item.unavailable_reason : "").trim();
    if (available && item && item.default_compare_mode) {
      if (!(analysisCompareModeEl && analysisCompareModeEl.checked)) {
        available = false;
        unavailableReason = "Enable compare mode and select Cohort A and Cohort B.";
      } else if (!(state.analysisSelectedSavedCohortId && state.analysisCompareSavedCohortId)) {
        available = false;
        unavailableReason = "Select saved Cohort A and saved Cohort B for this comparison analysis.";
      }
    }
    return { available, unavailableReason };
  }

  function renderAnalysisCatalogCard(item, options = {}) {
    const compact = Boolean(options.compact);
    const drawer = Boolean(options.drawer);
    const availability = analysisCatalogUiAvailability(item);
    const modeBadge = analysisCatalogModeBadge(item);
    const iconKind = analysisCatalogIconKind(item);
    const metaBadges = [
      `<span class="query-chip badge ${modeBadge.css}">${escapeHtml(modeBadge.label)}</span>`,
    ];
    if (item.default_compare_mode) {
      metaBadges.push('<span class="query-chip badge">Compare mode</span>');
    }
    if (item.requires_molecular) {
      metaBadges.push('<span class="query-chip badge">Molecular</span>');
    }
    if (item.requires_detailed_access) {
      metaBadges.push('<span class="query-chip badge">Detailed required</span>');
    }
    if (item.runner_type && item.runner_type !== "builtin") {
      metaBadges.push(`<span class="query-chip badge">${escapeHtml(String(item.runner_type).toUpperCase())}</span>`);
    }
    if (String(item.execution_backend || "").toLowerCase() === "job") {
      metaBadges.push('<span class="query-chip badge">Background job</span>');
    }
    const requirements = Array.isArray(item.workspace_requirements) ? item.workspace_requirements : [];
    const requirementsHtml = !compact && requirements.length
      ? `<div class="section-note">${escapeHtml(requirements.join(" "))}</div>`
      : "";
    const guidanceHtml = !compact && item.guidance
      ? `<div class="section-note">${escapeHtml(item.guidance)}</div>`
      : "";
    const tagsHtml = !compact && Array.isArray(item.tags) && item.tags.length
      ? `<div class="analysis-catalog-tags">${item.tags.map((tag) => `<span class="query-chip badge">${escapeHtml(tag)}</span>`).join("")}</div>`
      : "";
    const availabilityHtml = availability.available
      ? ""
      : `<div class="analysis-catalog-unavailable">${escapeHtml(availability.unavailableReason || "Unavailable in this workspace.")}</div>`;
    return `
      <article class="analysis-catalog-card${compact ? " is-compact" : ""}${drawer ? " is-drawer" : ""}${availability.available ? "" : " is-disabled"}">
        <div class="analysis-catalog-head">
          <div class="analysis-catalog-icon" aria-hidden="true">${analysisCatalogIconSvg(iconKind)}</div>
          <div>
            <div class="analysis-catalog-title">${escapeHtml(item.name || "Curated analysis")}</div>
            <div class="analysis-catalog-meta">${metaBadges.join("")}</div>
          </div>
        </div>
        <div class="analysis-catalog-description">${escapeHtml(String(item.description || ""))}</div>
        ${requirementsHtml}
        ${guidanceHtml}
        ${tagsHtml}
        ${availabilityHtml}
        <div class="analysis-catalog-actions">
          <button type="button" class="query-chip action" data-analysis-catalog-id="${escapeHtml(String(item.id || ""))}" ${availability.available ? "" : "disabled"}>Use analysis</button>
        </div>
      </article>
    `;
  }

  function setAnalysisCatalogDrawerOpen(open) {
    if (!analysisCatalogDrawerEl) return;
    analysisCatalogDrawerEl.classList.toggle("is-hidden", !open);
    analysisCatalogDrawerEl.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function renderAnalysisCatalog() {
    if (!analysisCatalogListEl) {
      return;
    }
    if (!Array.isArray(state.analysisCatalogItems) || !state.analysisCatalogItems.length) {
      analysisCatalogListEl.innerHTML = '<div class="empty">No curated analyses available.</div>';
      if (analysisCatalogDrawerListEl) {
        analysisCatalogDrawerListEl.innerHTML = '<div class="empty">No curated analyses available.</div>';
      }
      if (analysisCatalogStatusEl) {
        analysisCatalogStatusEl.textContent = "No curated analyses available.";
      }
      renderAnalysisCatalogMolecularPanel();
      return;
    }
    const unavailableCount = state.analysisCatalogItems.filter((item) => !item.available).length;
    if (analysisCatalogStatusEl) {
      const summaryBits = [`${state.analysisCatalogItems.length} curated analyses`];
      if (unavailableCount) {
        summaryBits.push(`${unavailableCount} unavailable in this workspace`);
      }
      if (state.analysisCatalogWorkspace && state.analysisCatalogWorkspace.has_molecular_datasets) {
        summaryBits.push(`${state.analysisCatalogWorkspace.molecular_dataset_count} molecular dataset${state.analysisCatalogWorkspace.molecular_dataset_count === 1 ? "" : "s"}`);
      }
      analysisCatalogStatusEl.textContent = summaryBits.join(" · ");
    }
    const featured = state.analysisCatalogItems.slice(0, 4);
    analysisCatalogListEl.innerHTML = `<div class="analysis-catalog-featured-strip">${featured.map((item) => renderAnalysisCatalogCard(item, { compact: true })).join("")}</div>`;
    const grouped = state.analysisCatalogItems.reduce((acc, item) => {
      const key = String(item.category || "General");
      if (!acc[key]) acc[key] = [];
      acc[key].push(item);
      return acc;
    }, {});
    if (analysisCatalogDrawerListEl) {
      analysisCatalogDrawerListEl.innerHTML = Object.entries(grouped).map(([category, items]) => {
        const cards = items.map((item) => renderAnalysisCatalogCard(item, { drawer: true })).join("");
        return `<section class="analysis-catalog-group"><div class="analysis-catalog-group-label">${escapeHtml(category)}</div><div class="analysis-catalog-grid">${cards}</div></section>`;
      }).join("");
    }
    renderAnalysisCatalogMolecularPanel();
  }

  async function loadAnalysisCatalog() {
    if (!analysisCatalogListEl) {
      return;
    }
    if (!isWorkspaceAccessible()) {
      state.analysisCatalogItems = [];
      state.analysisCatalogWorkspace = null;
      analysisCatalogListEl.innerHTML = '<div class="empty">Sign in and load a workspace to browse curated analyses.</div>';
      if (analysisCatalogDrawerListEl) {
        analysisCatalogDrawerListEl.innerHTML = '<div class="empty">Sign in and load a workspace to browse curated analyses.</div>';
      }
      if (analysisCatalogStatusEl) {
        analysisCatalogStatusEl.textContent = "Workspace unavailable.";
      }
      return;
    }
    if (analysisCatalogBrowseBtnEl) {
      analysisCatalogBrowseBtnEl.disabled = false;
      analysisCatalogBrowseBtnEl.title = "";
    }
    if (state.queryGranularityMode !== "detailed") {
      state.analysisCatalogItems = [];
      state.analysisCatalogWorkspace = null;
      analysisCatalogListEl.innerHTML = '<div class="empty">Analysis Catalog requires Detailed workspace access.</div>';
      if (analysisCatalogDrawerListEl) {
        analysisCatalogDrawerListEl.innerHTML = '<div class="empty">Analysis Catalog requires Detailed workspace access.</div>';
      }
      if (analysisCatalogStatusEl) {
        analysisCatalogStatusEl.textContent = "Analysis Catalog requires Detailed workspace access.";
      }
      if (analysisCatalogBrowseBtnEl) {
        analysisCatalogBrowseBtnEl.disabled = true;
        analysisCatalogBrowseBtnEl.title = "Analysis Catalog requires Detailed workspace access.";
      }
      setAnalysisCatalogDrawerOpen(false);
      renderAnalysisCatalogMolecularPanel();
      return;
    }
    analysisCatalogListEl.innerHTML = '<div class="empty">Loading curated analyses...</div>';
    if (analysisCatalogDrawerListEl) {
      analysisCatalogDrawerListEl.innerHTML = '<div class="empty">Loading curated analyses...</div>';
    }
    if (analysisCatalogStatusEl) {
      analysisCatalogStatusEl.textContent = "Loading curated analyses...";
    }
    try {
      const response = await fetch(`/analysis/catalog?dataset_id=${encodeURIComponent(currentDatasetSelectionKey())}`);
      if (!response.ok) {
        throw new Error("Unable to load Analysis Catalog.");
      }
      const payload = await response.json();
      state.analysisCatalogItems = Array.isArray(payload.items) ? payload.items : [];
      state.analysisCatalogWorkspace = payload.workspace || null;
      renderAnalysisCatalog();
    } catch (error) {
      state.analysisCatalogItems = [];
      state.analysisCatalogWorkspace = null;
      analysisCatalogListEl.innerHTML = '<div class="empty">Unable to load curated analyses.</div>';
      if (analysisCatalogDrawerListEl) {
        analysisCatalogDrawerListEl.innerHTML = '<div class="empty">Unable to load curated analyses.</div>';
      }
      if (analysisCatalogStatusEl) {
        analysisCatalogStatusEl.textContent = error && error.message ? error.message : "Unable to load curated analyses.";
      }
      renderAnalysisCatalogMolecularPanel();
    }
  }

  function applyAnalysisCatalogItemById(itemId) {
    const item = Array.isArray(state.analysisCatalogItems)
      ? state.analysisCatalogItems.find((entry) => String(entry.id || "") === String(itemId || ""))
      : null;
    const availability = analysisCatalogUiAvailability(item);
    if (!item || !availability.available) {
      if (analysisStatusEl) {
        analysisStatusEl.className = "query-status";
        analysisStatusEl.textContent = availability.unavailableReason || "This curated analysis is unavailable in the current Analysis workspace.";
      }
      return;
    }
    if (analysisPromptEl) {
      analysisPromptEl.value = String(item.default_prompt || "").trim();
    }
    state.analysisExecutionMode = normalizeAnalysisCatalogExecutionMode(item.execution_mode);
    state.analysisSelectedCatalogItemId = String(item.id || "").trim();
    renderAnalysisCatalogMolecularPanel();
    if (analysisCompareModeEl) {
      analysisCompareModeEl.checked = Boolean(item.default_compare_mode);
      renderAnalysisCompareMode();
    }
    state.analysisExamplesPinnedOpen = false;
    syncCurrentAnalysisSessionFromUi({ render: true });
    if (analysisStatusEl) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = item.guidance
        ? `${item.name} selected. ${item.guidance}`
        : `${item.name} selected. Review the prompt and run the analysis.`;
    }
    setAnalysisCatalogDrawerOpen(false);
    analysisPromptEl && analysisPromptEl.focus();
  }

  return {
    initializeExampleToggle,
    renderStarterPanelVisibility,
    renderQueryStarterPrompts,
    renderQueryExecutionMode,
    renderAnalysisStarterPrompts,
    normalizeAnalysisCatalogExecutionMode,
    analysisCatalogModeBadge,
    analysisCatalogIconSvg,
    analysisCatalogIconKind,
    selectedAnalysisMolecularDatasetNames,
    currentAnalysisCatalogItem,
    renderAnalysisCatalogMolecularPanel,
    analysisCatalogUiAvailability,
    renderAnalysisCatalogCard,
    setAnalysisCatalogDrawerOpen,
    renderAnalysisCatalog,
    loadAnalysisCatalog,
    applyAnalysisCatalogItemById,
  };
}
