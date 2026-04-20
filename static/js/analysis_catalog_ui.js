export function createAnalysisCatalogUi(ctx) {
  const { refs, state, helpers, callbacks, constants } = ctx;
  const {
    queryStarterPanelEl,
    queryPlannerBtnEl,
    queryMemoryBtnEl,
    queryGranularityModeValueEl,
    queryPolicyInfoBtnEl,
    analysisStarterPanelEl,
    analysisStarterHostEl,
    analysisComposerExamplesBtnEl,
    analysisCatalogStatusEl,
    analysisCatalogSearchEl,
    analysisCatalogFiltersEl,
    analysisCatalogListEl,
    analysisCatalogBrowseBtnEl,
    analysisCatalogDrawerEl,
    analysisCatalogDrawerSearchEl,
    analysisCatalogDrawerFiltersEl,
    analysisCatalogDrawerListEl,
    analysisCatalogMolecularPanelEl,
    analysisCatalogMolecularStatusEl,
    analysisPromptEl,
    analysisCompareModeEl,
    analysisStatusEl,
  } = refs;
  const { escapeHtml, currentStorageNamespace } = helpers;
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

  function ensureAnalysisStarterPanelPlacement() {
    if (!analysisStarterHostEl || !analysisStarterPanelEl) {
      return;
    }
    if (analysisStarterPanelEl.parentElement !== analysisStarterHostEl) {
      analysisStarterHostEl.appendChild(analysisStarterPanelEl);
    }
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
    ensureAnalysisStarterPanelPlacement();
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

  ensureAnalysisStarterPanelPlacement();

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

  function analysisCatalogQueueIcon() {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h11"></path><path d="M8 12h11"></path><path d="M8 18h11"></path><path d="m4 6 0 .01"></path><path d="m4 12 0 .01"></path><path d="m4 18 0 .01"></path></svg>';
  }

  function analysisCatalogRunnerTypeLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) return "";
    if (normalized === "rscript") return "Rscript";
    if (normalized === "snakemake") return "Snakemake";
    if (normalized === "nextflow") return "Nextflow";
    if (normalized === "python") return "Python";
    if (normalized === "bash") return "Bash";
    if (normalized === "cli") return "CLI";
    if (normalized === "container") return "Container";
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
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

  function isDifferentialExpressionCatalogItem(item) {
    const itemId = String(item && item.id ? item.id : "").trim();
    return itemId === "molecular-differential-expression" || itemId === "molecular-deseq2-differential-expression";
  }

  function analysisCatalogUsageStorageKey() {
    return `${currentStorageNamespace(state.authState)}.analysisCatalogUsage`;
  }

  function readAnalysisCatalogUsage() {
    try {
      const raw = window.localStorage.getItem(analysisCatalogUsageStorageKey());
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function writeAnalysisCatalogUsage(value) {
    try {
      window.localStorage.setItem(analysisCatalogUsageStorageKey(), JSON.stringify(value || {}));
    } catch (error) {
      // Ignore storage failures; suggestions are a convenience feature only.
    }
  }

  function recordAnalysisCatalogUsage(itemId) {
    const normalized = String(itemId || "").trim();
    if (!normalized) return;
    const usage = readAnalysisCatalogUsage();
    const current = usage[normalized] && typeof usage[normalized] === "object" ? usage[normalized] : {};
    usage[normalized] = {
      count: Number(current.count || 0) + 1,
      lastUsedAt: Date.now(),
    };
    writeAnalysisCatalogUsage(usage);
  }

  function normalizeAnalysisCatalogQuery(value) {
    return String(value || "").trim().toLowerCase();
  }

  function normalizeAnalysisCatalogFilter(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return ["all", "clinical", "molecular", "background", "external"].includes(normalized) ? normalized : "all";
  }

  function analysisCatalogFilterLabel(value) {
    const normalized = normalizeAnalysisCatalogFilter(value);
    if (normalized === "clinical") return "Clinical";
    if (normalized === "molecular") return "Molecular";
    if (normalized === "background") return "Background jobs";
    if (normalized === "external") return "External";
    return "All";
  }

  function analysisCatalogItemMatchesFilter(item, filter) {
    const normalized = normalizeAnalysisCatalogFilter(filter);
    if (normalized === "all") return true;
    if (normalized === "molecular") {
      return Boolean(item && item.requires_molecular);
    }
    if (normalized === "background") {
      return String(item && item.execution_backend ? item.execution_backend : "").trim().toLowerCase() === "job";
    }
    if (normalized === "external") {
      return String(item && item.runner_type ? item.runner_type : "").trim().toLowerCase() !== "builtin";
    }
    if (normalized === "clinical") {
      return !Boolean(item && item.requires_molecular);
    }
    return true;
  }

  function analysisCatalogItemSearchText(item) {
    return [
      String(item && item.name ? item.name : ""),
      String(item && item.description ? item.description : ""),
      String(item && item.category ? item.category : ""),
      String(item && item.guidance ? item.guidance : ""),
      String(item && item.runner_type ? analysisCatalogRunnerTypeLabel(item.runner_type) : ""),
      ...(Array.isArray(item && item.tags) ? item.tags : []),
    ].join(" ").toLowerCase();
  }

  function filteredAnalysisCatalogItems() {
    const items = Array.isArray(state.analysisCatalogItems) ? state.analysisCatalogItems : [];
    const query = normalizeAnalysisCatalogQuery(state.analysisCatalogQuery);
    const filter = normalizeAnalysisCatalogFilter(state.analysisCatalogFilter);
    return items.filter((item) => {
      if (!analysisCatalogItemMatchesFilter(item, filter)) {
        return false;
      }
      if (!query) {
        return true;
      }
      return analysisCatalogItemSearchText(item).includes(query);
    });
  }

  function analysisCatalogSuggestionScore(item, usage) {
    const itemId = String(item && item.id ? item.id : "").trim();
    const current = usage[itemId] && typeof usage[itemId] === "object" ? usage[itemId] : {};
    const count = Number(current.count || 0);
    const lastUsedAt = Number(current.lastUsedAt || 0);
    const compareRequired = Boolean(item && item.default_compare_mode);
    const molecularRequired = Boolean(item && item.requires_molecular);
    const external = String(item && item.runner_type ? item.runner_type : "").trim().toLowerCase() !== "builtin";
    const background = String(item && item.execution_backend ? item.execution_backend : "").trim().toLowerCase() === "job";
    const selected = itemId === String(state.analysisSelectedCatalogItemId || "").trim();
    let score = 0;
    if (selected) score += 10000;
    if (item && item.available) score += 200;
    if (count > 0) score += Math.min(count, 8) * 120;
    if (lastUsedAt > 0) {
      const ageHours = Math.max(0, (Date.now() - lastUsedAt) / 3600000);
      score += Math.max(0, 96 - ageHours);
    }
    if (compareRequired && analysisCompareModeEl && analysisCompareModeEl.checked) score += 40;
    if (!compareRequired && !(analysisCompareModeEl && analysisCompareModeEl.checked)) score += 18;
    if (molecularRequired && state.analysisCatalogWorkspace && state.analysisCatalogWorkspace.has_molecular_datasets) score += 24;
    if (background) score += 12;
    if (external) score += 8;
    return score;
  }

  function suggestedAnalysisCatalogItems(items) {
    const visibleItems = Array.isArray(items) ? items : [];
    if (!visibleItems.length) {
      return [];
    }
    const usage = readAnalysisCatalogUsage();
    return [...visibleItems]
      .sort((left, right) => analysisCatalogSuggestionScore(right, usage) - analysisCatalogSuggestionScore(left, usage))
      .slice(0, 4);
  }

  function syncAnalysisCatalogControls() {
    const query = String(state.analysisCatalogQuery || "");
    const filter = normalizeAnalysisCatalogFilter(state.analysisCatalogFilter);
    if (analysisCatalogSearchEl && analysisCatalogSearchEl.value !== query) {
      analysisCatalogSearchEl.value = query;
    }
    if (analysisCatalogDrawerSearchEl && analysisCatalogDrawerSearchEl.value !== query) {
      analysisCatalogDrawerSearchEl.value = query;
    }
    [analysisCatalogFiltersEl, analysisCatalogDrawerFiltersEl].forEach((container) => {
      if (!container) return;
      Array.from(container.querySelectorAll("[data-analysis-catalog-filter]")).forEach((button) => {
        const active = normalizeAnalysisCatalogFilter(button.dataset.analysisCatalogFilter || "") === filter;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    });
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
    if (isDifferentialExpressionCatalogItem(item)) {
      if (selectedDatasetNames.length === 1) {
        analysisCatalogMolecularStatusEl.textContent = `Selected dataset: ${selectedDatasetNames[0]}. This differential-expression tool will use the selected transcriptomics matrix.`;
      } else if (selectedDatasetNames.length > 1) {
        analysisCatalogMolecularStatusEl.textContent = `Selected ${selectedDatasetNames.length} molecular datasets. This differential-expression tool requires exactly one dataset.`;
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
    const selected = String(item && item.id ? item.id : "") === String(state.analysisSelectedCatalogItemId || "");
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
      metaBadges.push(`<span class="query-chip badge">${escapeHtml(analysisCatalogRunnerTypeLabel(item.runner_type))}</span>`);
    }
    if (String(item.execution_backend || "").toLowerCase() === "job") {
      metaBadges.push(`<span class="query-chip badge">${analysisCatalogQueueIcon()}<span>Background job</span></span>`);
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
      <article class="analysis-catalog-card${compact ? " is-compact" : ""}${drawer ? " is-drawer" : ""}${availability.available ? "" : " is-disabled"}${selected ? " is-selected" : ""}">
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
    syncAnalysisCatalogControls();
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
    const visibleItems = filteredAnalysisCatalogItems();
    const unavailableCount = visibleItems.filter((item) => !item.available).length;
    const filter = normalizeAnalysisCatalogFilter(state.analysisCatalogFilter);
    const query = normalizeAnalysisCatalogQuery(state.analysisCatalogQuery);
    if (analysisCatalogStatusEl) {
      const summaryBits = [`${visibleItems.length} of ${state.analysisCatalogItems.length} tools`];
      if (filter !== "all") {
        summaryBits.push(analysisCatalogFilterLabel(filter));
      }
      if (query) {
        summaryBits.push(`matching "${query}"`);
      }
      if (unavailableCount) {
        summaryBits.push(`${unavailableCount} unavailable in this workspace`);
      }
      if (state.analysisCatalogWorkspace && state.analysisCatalogWorkspace.has_molecular_datasets) {
        summaryBits.push(`${state.analysisCatalogWorkspace.molecular_dataset_count} molecular dataset${state.analysisCatalogWorkspace.molecular_dataset_count === 1 ? "" : "s"}`);
      }
      analysisCatalogStatusEl.textContent = summaryBits.join(" · ");
    }
    if (!visibleItems.length) {
      const message = query || filter !== "all"
        ? "No analyses match the current search and filters."
        : "No curated analyses available.";
      analysisCatalogListEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
      if (analysisCatalogDrawerListEl) {
        analysisCatalogDrawerListEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
      }
      renderAnalysisCatalogMolecularPanel();
      return;
    }
    const suggested = suggestedAnalysisCatalogItems(visibleItems);
    const grouped = visibleItems.reduce((acc, item) => {
      const key = String(item.category || "General");
      if (!acc[key]) acc[key] = [];
      acc[key].push(item);
      return acc;
    }, {});
    analysisCatalogListEl.innerHTML = [
      suggested.length
        ? `<section class="analysis-catalog-group"><div class="analysis-catalog-group-label">Suggested</div><div class="analysis-catalog-grid analysis-catalog-grid-compact">${suggested.map((item) => renderAnalysisCatalogCard(item, { compact: true })).join("")}</div></section>`
        : "",
      ...Object.entries(grouped).map(([category, items]) => {
      const cards = items.map((item) => renderAnalysisCatalogCard(item, { compact: true })).join("");
      return `<section class="analysis-catalog-group"><div class="analysis-catalog-group-label">${escapeHtml(category)}</div><div class="analysis-catalog-grid analysis-catalog-grid-compact">${cards}</div></section>`;
      }),
    ].filter(Boolean).join("");
    if (analysisCatalogDrawerListEl) {
      analysisCatalogDrawerListEl.innerHTML = Object.entries(grouped).map(([category, items]) => {
        const cards = items.map((item) => renderAnalysisCatalogCard(item, { drawer: true })).join("");
        return `<section class="analysis-catalog-group"><div class="analysis-catalog-group-label">${escapeHtml(category)}</div><div class="analysis-catalog-grid">${cards}</div></section>`;
      }).join("");
    }
    renderAnalysisCatalogMolecularPanel();
  }

  function setAnalysisCatalogSearch(value) {
    state.analysisCatalogQuery = String(value || "").trim();
    renderAnalysisCatalog();
  }

  function setAnalysisCatalogFilter(value) {
    state.analysisCatalogFilter = normalizeAnalysisCatalogFilter(value);
    renderAnalysisCatalog();
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
    recordAnalysisCatalogUsage(state.analysisSelectedCatalogItemId);
    renderAnalysisCatalog();
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
    analysisCatalogQueueIcon,
    analysisCatalogRunnerTypeLabel,
    selectedAnalysisMolecularDatasetNames,
    currentAnalysisCatalogItem,
    renderAnalysisCatalogMolecularPanel,
    analysisCatalogUiAvailability,
    renderAnalysisCatalogCard,
    setAnalysisCatalogDrawerOpen,
    renderAnalysisCatalog,
    setAnalysisCatalogSearch,
    setAnalysisCatalogFilter,
    loadAnalysisCatalog,
    applyAnalysisCatalogItemById,
  };
}
