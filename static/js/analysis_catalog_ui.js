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
    analysisCatalogDisclosureEl,
    analysisCatalogDisclosureTitleEl,
    analysisCatalogDisclosureNoteEl,
    analysisCatalogBrowseBtnEl,
    analysisCatalogDrawerEl,
    analysisCatalogDrawerSearchEl,
    analysisCatalogDrawerFiltersEl,
    analysisCatalogDrawerListEl,
    analysisCatalogAssayPanelEl,
    analysisCatalogAssayStatusEl,
    analysisCatalogSetupBadgesEl,
    analysisSetupChecklistEl,
    analysisCatalogAssayTitleEl,
    analysisCatalogAssayNoteEl,
    analysisFlowBarEl,
    analysisComposerSetupEl,
    analysisComposerSetupTitleEl,
    analysisComposerSetupNoteEl,
    analysisComposerSetupStatusEl,
    analysisPromptEl,
    analysisCompareModeEl,
    analysisStatusEl,
    analysisRunBtnEl,
  } = refs;
  const { escapeHtml, currentStorageNamespace } = helpers;
  const { MAX_VISIBLE_EXAMPLES } = constants;
  const {
    queryWorkspacePolicyExplanation,
    renderAssayDatasetSelector,
    renderAnalysisCompareMode,
    syncCurrentAnalysisSessionFromUi,
    currentDatasetSelectionKey,
    isWorkspaceAccessible,
    assayDatasetOverlap,
    setAnalysisContextMode,
    refreshBackgroundWorkerStatus,
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
    const generalQuestion = state.queryContextMode === "general";
    if (queryPlannerBtnEl) {
      const active = state.queryExecutionMode === "planner_only";
      queryPlannerBtnEl.classList.toggle("is-active", active);
      queryPlannerBtnEl.setAttribute("aria-pressed", active ? "true" : "false");
      queryPlannerBtnEl.title = active
        ? "Semantic planner is enabled for the next query."
        : "Skip deterministic matching for the next query and use the LLM planner first.";
    }
    if (queryMemoryBtnEl) {
      const scopeAvailable = !generalQuestion && state.queryGranularityMode === "detailed";
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
      const scopedResultHandle = state.latestScopedContext
        ? String(state.latestScopedContext.resultHandle || "").trim()
        : "";
      const scopedTotalCount = state.latestScopedContext
        ? Math.max(0, Number(state.latestScopedContext.totalCount || 0))
        : 0;
      const labelEl = queryMemoryBtnEl.querySelector("span:last-child");
      if (labelEl) {
        if (!scopeAvailable) {
          labelEl.textContent = "Prompt scope";
        } else if (!state.queryFollowMemoryEnabled) {
          labelEl.textContent = "Prompt scope: workspace";
        } else if (scopedResultHandle) {
          const unit = state.latestScopedContext && state.latestScopedContext.idType === "sample" ? "samples" : "patients";
          labelEl.textContent = `Prompt scope: previous result (${scopedTotalCount} ${unit})`;
        } else if (scopedPatientIds.length) {
          labelEl.textContent = `Prompt scope: previous result (${scopedPatientIds.length} patients)`;
        } else {
          labelEl.textContent = "Prompt scope: waiting for previous result";
        }
      }
    }
    if (queryGranularityModeValueEl) {
      queryGranularityModeValueEl.textContent = generalQuestion
        ? "No workspace context"
        : state.queryGranularityMode === "detailed" ? "Detailed" : "Summary";
      queryGranularityModeValueEl.title = generalQuestion
        ? "No workspace or dataset context will be sent to the model."
        : state.queryGranularityMode === "detailed"
        ? "This workspace allows detailed in-app Query results."
        : "This workspace is limited to summary-level in-app Query results.";
    }
    if (queryPolicyInfoBtnEl) {
      const explanation = queryWorkspacePolicyExplanation();
      queryPolicyInfoBtnEl.classList.toggle("is-hidden", generalQuestion || !explanation);
      queryPolicyInfoBtnEl.classList.toggle("is-warning", !generalQuestion && Boolean(explanation));
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
    analysisComposerExamplesBtnEl.textContent = "Prompts";
  }

  ensureAnalysisStarterPanelPlacement();

  function normalizeAnalysisCatalogExecutionMode(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "deterministic") return "deterministic";
    if (normalized === "llm_only") return "llm_only";
    return "planner_only";
  }

  function analysisCatalogModeBadge(item) {
    const mode = String(item && item.execution_mode ? item.execution_mode : "auto");
    if (mode === "deterministic") {
      return { css: "query-chip-deterministic", label: "Deterministic" };
    }
    if (mode === "llm_only") {
      if (!state.lmStatus || state.lmStatus.available !== true) {
        return { css: "query-chip-llm", label: "LLM unavailable" };
      }
      return { css: "query-chip-llm", label: "LLM answer" };
    }
    if (!state.lmStatus || state.lmStatus.available !== true) {
      return { css: "query-chip-planner", label: "LLM planner unavailable" };
    }
    return { css: "query-chip-planner", label: "LLM-planned" };
  }

  function analysisCatalogIconSvg(kind) {
    const icons = {
      clinical: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
      compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7h8"></path><path d="M8 17h8"></path><path d="m6 9 2-2 2 2"></path><path d="m18 15-2 2-2-2"></path></svg>',
      trajectory: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 18h16"></path><path d="m5 15 4-4 3 2 7-7"></path></svg>',
      survival: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5"></path><path d="M4 19h16"></path><path d="m6 7 4 5 3-3 5 6"></path></svg>',
      assay: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3c0 4 3 4 3 8s-3 4-3 8"></path><path d="M17 3c0 4-3 4-3 8s3 4 3 8"></path><path d="M8 6h8"></path><path d="M8 18h8"></path></svg>',
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
    if (category.includes("assays") || id.includes("assays") || id.includes("volcano")) return "assay";
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
    if (normalized === "workflow") return "Workflow";
    if (normalized === "python") return "Python";
    if (normalized === "bash") return "Bash";
    if (normalized === "cli") return "CLI";
    if (normalized === "container") return "Container";
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
  }

  function formatAssayRequirementLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) return "";
    const labels = {
      transcriptomics: "Transcriptomics",
      methylation: "DNA methylation",
      olink: "OLINK",
      proteomics: "Proteomics",
      flow_cytometry: "Immune-cell abundance",
      serology: "Serology",
      genotyping: "Genotyping",
      imaging: "Imaging",
      raw_counts: "Raw counts",
      m_values: "M-values",
      relative_abundance: "Relative abundance",
      protein_abundance: "Protein abundance",
      cell_population_abundance: "Cell-population abundance",
      quantitative_measurement: "Quantitative measurement",
      allele_dosage: "Allele dosage",
      dicom_derived_measurements: "DICOM-derived measurements",
    };
    if (labels[normalized]) {
      return labels[normalized];
    }
    return normalized
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function analysisCatalogCapabilityBadges(item) {
    const badges = [];
    const analysisLevel = String(item && item.analysis_level ? item.analysis_level : "").trim().toLowerCase();
    if (analysisLevel) {
      badges.push(`${formatAssayRequirementLabel(analysisLevel)} level`);
    }
    const modalities = Array.isArray(item && item.required_modalities) ? item.required_modalities : [];
    modalities.forEach((modality) => {
      const label = formatAssayRequirementLabel(modality);
      if (label) badges.push(`Requires ${label}`);
    });
    const dataTypes = Array.isArray(item && item.required_data_types) ? item.required_data_types : [];
    dataTypes.forEach((dataType) => {
      const label = formatAssayRequirementLabel(dataType);
      if (label) badges.push(`Requires ${label}`);
    });
    return badges;
  }

  function selectedAnalysisAssayDatasetNames() {
    return Array.isArray(state.selectedAssayDatasets)
      ? state.selectedAssayDatasets.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
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
    return ["all", "clinical", "assay", "workflow", "background", "external"].includes(normalized) ? normalized : "all";
  }

  function analysisCatalogFilterLabel(value) {
    const normalized = normalizeAnalysisCatalogFilter(value);
    if (normalized === "clinical") return "Clinical";
    if (normalized === "assay") return "Assays";
    if (normalized === "workflow") return "Workflow";
    if (normalized === "background") return "Background";
    if (normalized === "external") return "External";
    return "All";
  }

  function analysisCatalogItemMatchesFilter(item, filter) {
    const normalized = normalizeAnalysisCatalogFilter(filter);
    if (normalized === "all") return true;
    if (normalized === "assay") {
      return Boolean(item && item.requires_assays);
    }
    if (normalized === "workflow") {
      return String(item && item.runner_type ? item.runner_type : "").trim().toLowerCase() === "workflow";
    }
    if (normalized === "background") {
      return String(item && item.execution_backend ? item.execution_backend : "").trim().toLowerCase() === "job";
    }
    if (normalized === "external") {
      return String(item && item.runner_type ? item.runner_type : "").trim().toLowerCase() !== "builtin";
    }
    if (normalized === "clinical") {
      return !Boolean(item && item.requires_assays);
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
    const assayRequired = Boolean(item && item.requires_assays);
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
    if (assayRequired && state.analysisCatalogWorkspace && state.analysisCatalogWorkspace.has_assay_datasets) score += 24;
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

  function analysisSetupSteps(item, options = {}) {
    if (!item) return [];
    const assumeCatalogSelection = Boolean(options.assumeCatalogSelection);
    const availability = analysisCatalogUiAvailability(item);
    const selectedDatasetNames = selectedAnalysisAssayDatasetNames();
    const steps = [
      {
        key: "workspace",
        label: "Workspace compatibility",
        detail: availability.available
          ? "Access, data representation, and required runner are available."
          : (availability.unavailableReason || "This analysis is unavailable in the current workspace."),
        complete: availability.available,
      },
    ];
    if (item.default_compare_mode) {
      const compareEnabled = assumeCatalogSelection || Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
      const cohortA = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((entry) => String(entry && entry.id ? entry.id : "") === String(state.analysisSelectedSavedCohortId || ""))
        : null;
      const cohortB = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((entry) => String(entry && entry.id ? entry.id : "") === String(state.analysisCompareSavedCohortId || ""))
        : null;
      const cohortIds = (cohort) => {
        const sampleIds = Array.isArray(cohort && cohort.sample_ids) ? cohort.sample_ids : [];
        const patientIds = Array.isArray(cohort && cohort.patient_ids) ? cohort.patient_ids : [];
        return (sampleIds.length ? sampleIds : patientIds).map((value) => String(value || "").trim()).filter(Boolean);
      };
      const cohortAIds = cohortIds(cohortA);
      const cohortBIds = cohortIds(cohortB);
      const cohortASet = new Set(cohortAIds);
      const overlapCount = cohortBIds.filter((value) => cohortASet.has(value)).length;
      const sameCohort = Boolean(state.analysisSelectedSavedCohortId)
        && String(state.analysisSelectedSavedCohortId) === String(state.analysisCompareSavedCohortId || "");
      const cohortBReady = compareEnabled && Boolean(state.analysisCompareSavedCohortId) && !sameCohort && overlapCount === 0;
      const cohortBDetail = !state.analysisCompareSavedCohortId
        ? "Attach a different saved cohort as the comparison group."
        : sameCohort
          ? "Cohort B must be different from Cohort A."
          : overlapCount
            ? `Cohort A and Cohort B overlap by ${overlapCount} ID${overlapCount === 1 ? "" : "s"}; choose disjoint cohorts.`
            : "Saved Cohort B is attached and disjoint from Cohort A.";
      steps.push(
        {
          key: "cohort-a",
          label: "Choose Cohort A",
          detail: state.analysisSelectedSavedCohortId
            ? "Saved Cohort A is attached."
            : "Attach a saved cohort as the primary group.",
          complete: compareEnabled && Boolean(state.analysisSelectedSavedCohortId),
          action: "choose-cohort-a",
          actionLabel: "Choose Cohort A",
        },
        {
          key: "cohort-b",
          label: "Choose Cohort B",
          detail: cohortBDetail,
          complete: cohortBReady,
          action: "choose-cohort-b",
          actionLabel: "Choose Cohort B",
        },
      );
    }
    if (item.requires_assays) {
      const singleAssay = requiresSingleSelectedAssayDataset(item);
      const selectedCount = selectedDatasetNames.length;
      let complete = singleAssay ? selectedCount === 1 : selectedCount > 0;
      let detail = singleAssay
        ? (selectedCount === 1 ? `Selected assay: ${selectedDatasetNames[0]}.` : selectedCount > 1 ? "Choose exactly one compatible assay." : "Choose one compatible assay.")
        : (selectedCount ? `${selectedCount} compatible assays selected.` : "Choose at least one compatible assay.");
      if (complete && singleAssay && item.default_compare_mode) {
        const overlap = typeof assayDatasetOverlap === "function" ? assayDatasetOverlap(selectedDatasetNames[0]) : null;
        const minimumOverlap = Math.max(1, Number(item.minimum_samples_per_cohort || 1));
        if (overlap) {
          complete = overlap.overlapA >= minimumOverlap && overlap.overlapB >= minimumOverlap;
          detail = `Selected assay: ${selectedDatasetNames[0]}. Cohort A overlap: ${overlap.overlapA} · Cohort B overlap: ${overlap.overlapB}; ${minimumOverlap} per cohort required.`;
        }
      }
      steps.push({
        key: "assay",
        label: singleAssay ? "Choose one assay" : "Choose assay data",
        detail,
        complete,
        action: "choose-assay",
        actionLabel: "Choose assay",
      });
    }
    const executionMode = String(item.execution_mode || "deterministic").trim().toLowerCase();
    if (executionMode === "llm_only" || executionMode === "auto") {
      const lmReady = Boolean(state.lmStatus && state.lmStatus.available === true);
      steps.push({
        key: "model",
        label: executionMode === "llm_only" ? "Language model" : "LLM planner",
        detail: lmReady ? "The configured language model is available." : "Start or enable the configured language model.",
        complete: lmReady,
      });
    }
    if (String(item.execution_backend || "").trim().toLowerCase() === "job") {
      const worker = state.backgroundWorkerStatus && typeof state.backgroundWorkerStatus === "object"
        ? state.backgroundWorkerStatus
        : null;
      const workerCount = worker ? Math.max(0, Number(worker.worker_count || 0)) : 0;
      steps.push({
        key: "worker",
        label: "Background worker",
        detail: worker && worker.available
          ? `${workerCount} background ${workerCount === 1 ? "worker is" : "workers are"} online.`
          : worker
            ? "No background worker is online. Start Redis and an Analysis worker, then check again."
            : "Checking the Analysis queue and background worker.",
        complete: Boolean(worker && worker.available),
        action: "check-worker",
        actionLabel: worker ? "Check again" : "Check worker",
      });
    }
    const promptValue = String(
      String(state.analysisSelectedCatalogItemId || "") === String(item.id || "")
        ? (analysisPromptEl && analysisPromptEl.value ? analysisPromptEl.value : "")
        : (item.default_prompt || "")
    ).trim();
    steps.push({
      key: "prompt",
      label: "Review configured prompt",
      detail: promptValue ? "The curated prompt is ready for review." : "Add the prompt that describes this run.",
      complete: Boolean(promptValue),
      action: "review-prompt",
      actionLabel: "Review prompt",
    });
    return steps;
  }

  function renderAnalysisSetupChecklist(setupState) {
    if (!analysisSetupChecklistEl) return;
    const steps = Array.isArray(setupState && setupState.steps) ? setupState.steps : [];
    if (!steps.length) {
      analysisSetupChecklistEl.innerHTML = "";
      return;
    }
    const firstIncompleteIndex = steps.findIndex((step) => !step.complete);
    analysisSetupChecklistEl.innerHTML = steps.map((step, index) => {
      const current = index === firstIncompleteIndex;
      const stateClass = step.complete ? "is-complete" : current ? "is-current" : "is-waiting";
      const stateLabel = step.complete ? "Done" : current ? "Next" : "Waiting";
      const action = current && step.action
        ? `<button type="button" class="query-chip action" data-analysis-setup-action="${escapeHtml(step.action)}">${escapeHtml(step.actionLabel || "Continue")}</button>`
        : "";
      return `
        <div class="analysis-setup-check ${stateClass}" data-analysis-setup-step="${escapeHtml(step.key)}">
          <span class="analysis-setup-check-index" aria-hidden="true">${step.complete ? "✓" : index + 1}</span>
          <span class="analysis-setup-check-copy">
            <strong>${escapeHtml(step.label)}</strong>
            <small>${escapeHtml(step.detail)}</small>
          </span>
          <span class="analysis-setup-check-state">${stateLabel}</span>
          ${action}
        </div>
      `;
    }).join("");
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

  function renderAnalysisCatalogAssayPanel() {
    if (!analysisCatalogAssayPanelEl || !analysisCatalogAssayStatusEl) {
      return;
    }
    const item = currentAnalysisCatalogItem();
    const hasSelectedItem = Boolean(item);
    analysisCatalogAssayPanelEl.classList.toggle("is-hidden", !hasSelectedItem);
    if (analysisComposerSetupEl) {
      analysisComposerSetupEl.classList.toggle("is-hidden", !hasSelectedItem);
    }
    if (!hasSelectedItem) {
      renderAnalysisSetupChecklist({ steps: [] });
      if (analysisCatalogSetupBadgesEl) {
        analysisCatalogSetupBadgesEl.innerHTML = "";
      }
      if (analysisComposerSetupTitleEl) {
        analysisComposerSetupTitleEl.textContent = "Analysis setup";
      }
      if (analysisComposerSetupNoteEl) {
        analysisComposerSetupNoteEl.textContent = "Select an analysis from the catalog to configure this run.";
      }
      if (analysisComposerSetupStatusEl) {
        analysisComposerSetupStatusEl.textContent = "Ready to run with the current Analysis scope.";
        analysisComposerSetupStatusEl.classList.remove("is-ready", "is-blocked");
      }
      if (analysisRunBtnEl && !state.analysisInFlight) {
        analysisRunBtnEl.disabled = false;
      }
      renderAnalysisFlowBar();
      return;
    }
    renderAssayDatasetSelector();
    const requiresAssay = Boolean(item && item.requires_assays);
    const compareRequired = Boolean(item && item.default_compare_mode);
    const selectedDatasetNames = selectedAnalysisAssayDatasetNames();
    const setupState = selectedAnalysisSetupState(item);
    renderAnalysisSetupChecklist(setupState);
    if (analysisCatalogAssayTitleEl) {
      analysisCatalogAssayTitleEl.textContent = item && item.name ? item.name : "Analysis setup";
    }
    if (analysisCatalogAssayNoteEl) {
      analysisCatalogAssayNoteEl.textContent = item && item.guidance
        ? String(item.guidance || "").trim()
        : "Complete the required inputs for this analysis.";
    }
    if (analysisComposerSetupTitleEl) {
      analysisComposerSetupTitleEl.textContent = item && item.name ? item.name : "Analysis setup";
    }
    if (analysisComposerSetupNoteEl) {
      analysisComposerSetupNoteEl.textContent = item && item.guidance
        ? String(item.guidance || "").trim()
        : "Complete the required inputs for this analysis.";
    }
    analysisCatalogAssayStatusEl.classList.toggle("is-ready", Boolean(setupState.ready));
    analysisCatalogAssayStatusEl.classList.toggle("is-blocked", !setupState.ready);
    if (analysisComposerSetupStatusEl) {
      analysisComposerSetupStatusEl.classList.toggle("is-ready", Boolean(setupState.ready));
      analysisComposerSetupStatusEl.classList.toggle("is-blocked", !setupState.ready);
    }
    if (analysisCatalogSetupBadgesEl) {
      const badges = [];
      badges.push(`<span class="query-chip badge">${requiresAssay ? "Needs assay" : "No assay required"}</span>`);
      analysisCatalogCapabilityBadges(item).forEach((badge) => {
        badges.push(`<span class="query-chip badge">${escapeHtml(badge)}</span>`);
      });
      badges.push(`<span class="query-chip badge">${compareRequired ? "Needs Cohort A + B" : "Single-scope analysis"}</span>`);
      if (compareRequired) {
        badges.push(`<span class="query-chip badge">${state.analysisSelectedSavedCohortId ? "Cohort A ready" : "Choose Cohort A"}</span>`);
        badges.push(`<span class="query-chip badge">${state.analysisCompareSavedCohortId ? "Cohort B ready" : "Choose Cohort B"}</span>`);
      } else {
        badges.push(`<span class="query-chip badge">${state.analysisSelectedSavedCohortId ? "Saved scope selected" : "Workspace or manual scope"}</span>`);
      }
      if (requiresAssay) {
        const selectedCount = selectedDatasetNames.length;
        const datasetBadge = requiresSingleSelectedAssayDataset(item)
          ? (selectedCount === 1 ? `Assay ready: ${selectedDatasetNames[0]}` : selectedCount > 1 ? `${selectedCount} assays selected` : "Choose 1 assay")
          : (selectedCount ? `${selectedCount} assay${selectedCount === 1 ? "" : "s"} selected` : "Choose assay");
        badges.push(`<span class="query-chip badge">${escapeHtml(datasetBadge)}</span>`);
      }
      analysisCatalogSetupBadgesEl.innerHTML = badges.join("");
    }
    if (analysisRunBtnEl && !state.analysisInFlight) {
      analysisRunBtnEl.disabled = state.analysisContextMode === "general" ? false : !setupState.ready;
    }
    [refs.analysisCatalogAssayDatasetListEl].filter(Boolean).forEach((listEl) => {
      listEl.classList.toggle("is-hidden", !requiresAssay);
    });
    if (!requiresAssay) {
      analysisCatalogAssayStatusEl.textContent = setupState.message;
      if (analysisComposerSetupStatusEl) {
        analysisComposerSetupStatusEl.textContent = setupState.message;
      }
      renderAnalysisFlowBar();
      return;
    }
    if (requiresSingleSelectedAssayDataset(item)) {
      if (selectedDatasetNames.length === 1) {
        const overlap = typeof assayDatasetOverlap === "function"
          ? assayDatasetOverlap(selectedDatasetNames[0])
          : null;
        if (overlap && item && item.default_compare_mode) {
          const minimumOverlap = Math.max(1, Number(item.minimum_samples_per_cohort || 1));
          const overlapMessage = `Cohort A overlap: ${overlap.overlapA}${analysisCompareModeEl && analysisCompareModeEl.checked ? ` · Cohort B overlap: ${overlap.overlapB}` : ""}.`;
          const statusMessage = setupState.ready
            ? `Selected assay: ${selectedDatasetNames[0]}. ${overlapMessage} Ready to run.`
            : `Selected assay: ${selectedDatasetNames[0]}. ${overlapMessage} This assay tool requires at least ${minimumOverlap} samples in both cohorts.`;
          analysisCatalogAssayStatusEl.textContent = statusMessage;
          if (analysisComposerSetupStatusEl) {
            analysisComposerSetupStatusEl.textContent = statusMessage;
          }
        } else {
          analysisCatalogAssayStatusEl.textContent = setupState.message;
          if (analysisComposerSetupStatusEl) {
            analysisComposerSetupStatusEl.textContent = setupState.message;
          }
        }
      } else if (selectedDatasetNames.length > 1) {
        analysisCatalogAssayStatusEl.textContent = setupState.message;
        if (analysisComposerSetupStatusEl) {
          analysisComposerSetupStatusEl.textContent = setupState.message;
        }
      } else {
        analysisCatalogAssayStatusEl.textContent = setupState.message;
        if (analysisComposerSetupStatusEl) {
          analysisComposerSetupStatusEl.textContent = setupState.message;
        }
      }
      renderAnalysisFlowBar();
      return;
    }
    analysisCatalogAssayStatusEl.textContent = setupState.message;
    if (analysisComposerSetupStatusEl) {
      analysisComposerSetupStatusEl.textContent = setupState.message;
    }
    renderAnalysisFlowBar();
  }

  function analysisFlowScopeLabel() {
    if (analysisCompareModeEl && analysisCompareModeEl.checked) {
      if (state.analysisSelectedSavedCohortId && state.analysisCompareSavedCohortId) {
        return "Cohort A + B";
      }
      return "Needs cohorts";
    }
    if (state.analysisSelectedSavedCohortId) {
      return "Saved cohort";
    }
    if (refs.analysisSelectedPatientIdsEl && refs.analysisSelectedPatientIdsEl.value.trim()) {
      const count = refs.analysisSelectedPatientIdsEl.value.split(",").map((item) => item.trim()).filter(Boolean).length;
      return count ? `${count} selected` : "Manual scope";
    }
    return "Full workspace";
  }

  function analysisFlowResultsLabel() {
    const turns = Array.isArray(state.analysisTurns) ? state.analysisTurns : [];
    if (!turns.length) return "Empty";
    const last = turns[turns.length - 1] || {};
    if (last.pending) return "Pending";
    const payload = last.payload || {};
    if (payload && payload.data && payload.data.execution === "queued") return "Job queued";
    if (String(payload.intent || "") === "analysis_error") return "Error";
    return "Generated";
  }

  const cohortSummaryPrompt = "Summarize the main clinical patterns in this workspace and tell me what stands out.";

  function renderMethodPicker() {
    const select = document.getElementById("analysisMethodSelect");
    if (!select) return;
    const general = state.analysisContextMode === "general";
    const item = currentAnalysisCatalogItem();
    const prompt = analysisPromptEl.value.trim();
    const method = item ? `catalog:${item.id}` : prompt.startsWith("Compare measurements:") ? "association"
      : /^Summarize the main clinical patterns in this (workspace|cohort) and tell me what stands out\.$/.test(prompt) ? "summary" : "custom";
    const items = Array.isArray(state.analysisCatalogItems) ? state.analysisCatalogItems : [];
    select.innerHTML = '<option value="summary">Describe my cohort · No LLM needed</option><option value="association">Associate two measurements · No LLM needed</option>'
      + '<optgroup label="Supported analyses">' + items.map(entry => {
        const availability = analysisCatalogUiAvailability(entry);
        const modeLabel = entry.execution_mode === "deterministic" ? "No LLM needed" : ["llm_only", "planner_only"].includes(entry.execution_mode) ? "Requires LLM" : "May use LLM";
        return `<option value="catalog:${escapeHtml(entry.id)}" ${availability.available ? "" : "disabled"}>${escapeHtml(entry.name)} · ${availability.available ? modeLabel : "Unavailable"}</option>`;
      }).join("") + '</optgroup><option value="custom">Write a request / follow-up</option>';
    select.value = method;
    document.getElementById("analysisMethodPicker").hidden = general;
    const comparison = document.getElementById("analysisMeasurementComparison");
    comparison.hidden = general || method !== "association";
    if (!comparison.hidden) comparison.open = true;
    analysisComposerExamplesBtnEl.hidden = !general && method !== "custom";
    if (analysisStarterPanelEl) analysisStarterPanelEl.hidden = !general && method !== "custom";
    const description = item ? [item.description, item.guidance].filter(Boolean).join(" ")
      : method === "association" ? "Check whether two measurements vary together across matched patients. Choose one feature from each modality. This is exploratory correlation, without covariate adjustment."
      : method === "summary" ? "Describe the clinical patterns in your patient scope. No assay selection or language model is needed."
      : "Write a supported analysis request or a follow-up. Some requests need an available language model; deterministic analyses remain available without one.";
    document.getElementById("analysisMethodDescription").textContent = description;
    const requestDetails = document.getElementById("analysisRequestDetails");
    if (requestDetails.dataset.method !== method || requestDetails.dataset.general !== String(general)) {
      requestDetails.open = general || method === "custom";
      requestDetails.dataset.method = method;
      requestDetails.dataset.general = String(general);
    }
    document.getElementById("analysisRunReview").textContent = general ? "Ask the selected model without workspace data."
      : `Patient scope: ${analysisFlowScopeLabel()}. ${item && item.execution_backend === "job" ? "Runs in the background; requires an available worker." : method === "custom" ? "Execution depends on the requested analysis." : "Runs directly."} Review the inputs and research question before running.`;
    select.onchange = () => {
      const chosen = select.value;
      if (chosen.startsWith("catalog:")) {
        applyAnalysisCatalogItemById(chosen.slice(8));
        return;
      }
      state.analysisSelectedCatalogItemId = "";
      state.analysisExecutionMode = chosen === "custom" ? "auto" : "deterministic";
      analysisPromptEl.value = chosen === "summary" ? cohortSummaryPrompt : chosen === "association" ? "Compare measurements: " : "";
      renderAnalysisCatalogAssayPanel();
      syncCurrentAnalysisSessionFromUi({ render: true });
    };
  }

  function renderAnalysisFlowBar() {
    renderMethodPicker();
    if (!analysisFlowBarEl) return;
    analysisFlowBarEl.hidden = state.analysisContextMode === "general";
    const item = currentAnalysisCatalogItem();
    const setupState = selectedAnalysisSetupState(item);
    const hasItem = Boolean(item);
    const setupSteps = Array.isArray(setupState.steps)
      ? setupState.steps.filter((step) => step.key !== "prompt")
      : [];
    const patientsReady = setupSteps.filter(step => step.key.startsWith("cohort-")).every(step => step.complete);
    const inputSteps = setupSteps.filter(step => !step.key.startsWith("cohort-"));
    const incompleteSetupCount = inputSteps.filter(step => !step.complete).length;
    const association = document.getElementById("analysisMethodSelect").value === "association";
    const comparisonReady = ["X", "Y"].every(axis => document.getElementById(`associationAssay${axis}`).value && document.getElementById(`associationFeature${axis}`).value);
    const requirementsReady = association ? comparisonReady : !hasItem || incompleteSetupCount === 0;
    const resultsLabel = analysisFlowResultsLabel();
    const hasPrompt = Boolean(analysisPromptEl && analysisPromptEl.value.trim());
    const hypothesisReady = document.getElementById("analysisStudyMode").value !== "hypothesis_driven" || Boolean(document.getElementById("analysisResearchQuestion").value.trim() && document.getElementById("analysisHypothesis").value.trim());
    const reviewReady = hasPrompt && hypothesisReady;
    const lastSubmission = (state.analysisTurns || []).slice().reverse().find(turn => turn.role === "user");
    const showingCurrentResult = lastSubmission && lastSubmission.prompt === analysisPromptEl.value.trim()
      && ["Generated", "Job queued", "Error"].includes(resultsLabel);
    const activeTarget = state.analysisInFlight
      ? "results"
      : !patientsReady ? "scope"
        : !requirementsReady
            ? "requirements"
          : reviewReady && showingCurrentResult ? "results" : "prompt";
    const steps = {
      catalog: {
        value: hasItem ? String(item.name || "Selected") : association ? "Two measurements" : document.getElementById("analysisMethodSelect").value === "summary" ? "Cohort summary" : "Custom request",
        state: "is-ready",
      },
      scope: {
        value: patientsReady ? analysisFlowScopeLabel() : "Choose cohorts",
        state: patientsReady ? "is-ready" : "is-blocked",
      },
      requirements: {
        value: association ? (requirementsReady ? "Measurements selected" : "Choose measurements") : !hasItem ? "Not required" : requirementsReady ? "Ready" : `${incompleteSetupCount} step${incompleteSetupCount === 1 ? "" : "s"} remaining`,
        state: requirementsReady ? "is-ready" : "is-blocked",
      },
      prompt: {
        value: state.analysisInFlight ? "Running" : !hypothesisReady ? "Add hypothesis" : !patientsReady || !requirementsReady ? "Waiting for setup" : hasPrompt ? "Ready to review" : "Enter request",
        state: state.analysisInFlight ? "is-running" : !reviewReady ? "is-blocked" : !patientsReady || !requirementsReady ? "is-neutral" : "is-ready",
      },
      results: {
        value: resultsLabel,
        state: resultsLabel === "Error" ? "is-blocked" : resultsLabel === "Empty" ? "is-neutral" : resultsLabel === "Pending" ? "is-running" : "is-ready",
      },
    };
    Array.from(analysisFlowBarEl.querySelectorAll("[data-analysis-flow-target]")).forEach((button) => {
      const target = String(button.dataset.analysisFlowTarget || "");
      const step = steps[target];
      if (!step) return;
      const valueEl = button.querySelector("strong");
      if (valueEl) valueEl.textContent = step.value;
      button.classList.remove("is-active", "is-ready", "is-blocked", "is-running", "is-neutral");
      button.classList.add(step.state);
      button.classList.toggle("is-active", target === activeTarget);
      if (target === activeTarget) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
  }

  function analysisCatalogUiAvailability(item) {
    return {
      available: Boolean(item && item.available),
      unavailableReason: String(item && item.unavailable_reason ? item.unavailable_reason : "").trim(),
    };
  }

  function selectedAnalysisSetupState(item, options = {}) {
    const availability = analysisCatalogUiAvailability(item);
    if (!item) {
      return { ready: false, message: "", availability, steps: [] };
    }
    const steps = analysisSetupSteps(item, options);
    const firstIncomplete = steps.find((step) => !step.complete);
    if (firstIncomplete) {
      return { ready: false, message: firstIncomplete.detail, availability, steps };
    }
    const selectedDatasetNames = selectedAnalysisAssayDatasetNames();
    const message = item.requires_assays
      ? `Ready to run with ${requiresSingleSelectedAssayDataset(item) ? selectedDatasetNames[0] : `${selectedDatasetNames.length} assay${selectedDatasetNames.length === 1 ? "" : "s"}`}.`
      : item.default_compare_mode
        ? "Ready to run with the selected Cohort A and Cohort B."
        : "Ready to run with the current Analysis scope.";
    return {
      ready: true,
      message,
      availability,
      steps,
    };
  }

  function focusFirstIncompleteAnalysisSetup() {
    const current = analysisSetupChecklistEl
      ? analysisSetupChecklistEl.querySelector(".analysis-setup-check.is-current")
      : null;
    const target = current || analysisCatalogAssayPanelEl;
    if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    const action = current ? current.querySelector("[data-analysis-setup-action]") : null;
    if (action) action.focus({ preventScroll: true });
  }

  async function handleAnalysisSetupAction(actionName) {
    const action = String(actionName || "").trim();
    if (action === "choose-cohort-a" || action === "choose-cohort-b") {
      const setup = document.getElementById("analysisWorkspaceSetup");
      const saved = setup ? setup.querySelector(".analysis-setup-saved-cohorts") : null;
      if (setup) setup.open = true;
      if (saved) saved.open = true;
      const selector = action === "choose-cohort-b"
        ? "[data-saved-cohort-action='load-analysis-b']"
        : "[data-saved-cohort-action='load-analysis']";
      const target = saved || setup;
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      window.requestAnimationFrame(() => {
        const choice = saved ? saved.querySelector(selector) : null;
        if (choice) choice.focus({ preventScroll: true });
        else if (saved) saved.querySelector("summary")?.focus({ preventScroll: true });
      });
      return;
    }
    if (action === "choose-assay") {
      if (analysisCatalogAssayDatasetListEl) {
        analysisCatalogAssayDatasetListEl.scrollIntoView({ behavior: "smooth", block: "center" });
        const choice = analysisCatalogAssayDatasetListEl.querySelector("input[type='checkbox']");
        if (choice) choice.focus({ preventScroll: true });
      }
      return;
    }
    if (action === "check-worker") {
      if (typeof refreshBackgroundWorkerStatus === "function") {
        await refreshBackgroundWorkerStatus();
      }
      renderAnalysisCatalog();
      focusFirstIncompleteAnalysisSetup();
      return;
    }
    if (action === "review-prompt" && analysisPromptEl) {
      analysisPromptEl.scrollIntoView({ behavior: "smooth", block: "center" });
      analysisPromptEl.focus({ preventScroll: true });
    }
  }

  function renderAnalysisCatalogCard(item, options = {}) {
    const compact = Boolean(options.compact);
    const drawer = Boolean(options.drawer);
    const availability = analysisCatalogUiAvailability(item);
    const setupState = selectedAnalysisSetupState(item, { assumeCatalogSelection: true });
    const modeBadge = analysisCatalogModeBadge(item);
    const iconKind = analysisCatalogIconKind(item);
    const selected = String(item && item.id ? item.id : "") === String(state.analysisSelectedCatalogItemId || "");
    const metaBadges = [
      `<span class="query-chip badge ${modeBadge.css}">${escapeHtml(modeBadge.label)}</span>`,
    ];
    if (item.default_compare_mode) {
      metaBadges.push('<span class="query-chip badge">Compare mode</span>');
    }
    if (item.requires_assays) {
      metaBadges.push('<span class="query-chip badge">Assays</span>');
    }
    analysisCatalogCapabilityBadges(item).forEach((badge) => {
      metaBadges.push(`<span class="query-chip badge">${escapeHtml(badge)}</span>`);
    });
    if (item.requires_detailed_access) {
      metaBadges.push('<span class="query-chip badge">Detailed required</span>');
    }
    if (item && item.debug_only) {
      metaBadges.push('<span class="query-chip badge">Debug</span>');
    }
    if (item.runner_type && item.runner_type !== "builtin") {
      metaBadges.push(`<span class="query-chip badge">${escapeHtml(analysisCatalogRunnerTypeLabel(item.runner_type))}</span>`);
    }
    if (String(item.execution_backend || "").toLowerCase() === "job") {
      metaBadges.push(`<span class="query-chip badge">${analysisCatalogQueueIcon()}<span>Background</span></span>`);
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
    const readinessLabel = availability.available
      ? (setupState.ready ? "Ready now" : "Needs setup")
      : "Unavailable";
    const readinessHtml = `<div class="analysis-catalog-readiness ${setupState.ready ? "is-ready" : "is-blocked"}"><strong>${escapeHtml(readinessLabel)}</strong>${setupState.message ? ` <span>${escapeHtml(setupState.message)}</span>` : ""}</div>`;
    const actionLabel = availability.available
      ? (setupState.ready ? "Use analysis" : "Set up")
      : "Unavailable";
    return `
      <article class="analysis-catalog-card${compact ? " is-compact" : ""}${drawer ? " is-drawer" : ""}${availability.available ? "" : " is-disabled"}${setupState.ready ? " is-ready" : " is-needs-setup"}${selected ? " is-selected" : ""}">
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
        ${readinessHtml}
        <div class="analysis-catalog-actions">
          <button type="button" class="query-chip action" data-analysis-catalog-id="${escapeHtml(String(item.id || ""))}" ${availability.available ? "" : "disabled"}>${escapeHtml(actionLabel)}</button>
        </div>
      </article>
    `;
  }

  function setAnalysisCatalogDrawerOpen(open) {
    if (!analysisCatalogDrawerEl) return;
    analysisCatalogDrawerEl.classList.toggle("is-hidden", !open);
    analysisCatalogDrawerEl.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function renderAnalysisCatalogDisclosureSummary() {
    const item = currentAnalysisCatalogItem();
    if (analysisCatalogDisclosureTitleEl) {
      analysisCatalogDisclosureTitleEl.textContent = item && item.name
        ? item.name
        : "Analysis Catalog";
    }
    if (analysisCatalogDisclosureNoteEl) {
      analysisCatalogDisclosureNoteEl.textContent = item
        ? "Selected analysis. Open to change it."
        : "Curated analyses and structured runs.";
    }
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
      renderAnalysisCatalogDisclosureSummary();
      renderAnalysisCatalogAssayPanel();
      return;
    }
    const visibleItems = filteredAnalysisCatalogItems();
    const catalogUniverse = Array.isArray(state.analysisCatalogItems) ? state.analysisCatalogItems : [];
    const readyItems = visibleItems.filter((item) => selectedAnalysisSetupState(item, { assumeCatalogSelection: true }).ready);
    const setupItems = visibleItems.filter((item) => !selectedAnalysisSetupState(item, { assumeCatalogSelection: true }).ready);
    const unavailableCount = visibleItems.filter((item) => !item.available).length;
    const filter = normalizeAnalysisCatalogFilter(state.analysisCatalogFilter);
    const query = normalizeAnalysisCatalogQuery(state.analysisCatalogQuery);
    if (analysisCatalogStatusEl) {
      const summaryBits = [`${visibleItems.length} of ${catalogUniverse.length} tools`];
      summaryBits.push(`${readyItems.length} ready now`);
      summaryBits.push(`${setupItems.length} need setup`);
      if (filter !== "all") {
        summaryBits.push(analysisCatalogFilterLabel(filter));
      }
      if (query) {
        summaryBits.push(`matching "${query}"`);
      }
      if (unavailableCount) {
        summaryBits.push(`${unavailableCount} unavailable in this workspace`);
      }
      if (state.analysisCatalogWorkspace && state.analysisCatalogWorkspace.has_assay_datasets) {
        summaryBits.push(`${state.analysisCatalogWorkspace.assay_dataset_count} assay${state.analysisCatalogWorkspace.assay_dataset_count === 1 ? "" : "s"}`);
      }
      if (catalogUniverse.some((item) => item && item.debug_only)) {
        summaryBits.push("debug tools visible");
      }
      analysisCatalogStatusEl.textContent = summaryBits.join(" · ");
    }
    renderAnalysisCatalogDisclosureSummary();
    if (!visibleItems.length) {
      const message = query || filter !== "all"
        ? "No analyses match the current search and filters."
        : "No curated analyses available.";
      analysisCatalogListEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
      if (analysisCatalogDrawerListEl) {
        analysisCatalogDrawerListEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
      }
      renderAnalysisCatalogAssayPanel();
      return;
    }
    const renderReadinessSection = (label, items, renderOptions = {}) => {
      const sectionClass = label === "Ready now" ? "is-ready" : "is-needs-setup";
      const note = label === "Ready now"
        ? "Can run with the current scope and inputs."
        : "Needs one or more inputs before it can run.";
      const headerHtml = `
        <div class="analysis-catalog-group-header">
          <div>
            <div class="analysis-catalog-group-label">${escapeHtml(label)}</div>
            <div class="analysis-catalog-group-note">${escapeHtml(note)}</div>
          </div>
          <span class="analysis-catalog-group-count">${items.length}</span>
        </div>
      `;
      if (!items.length) {
        const emptyMessage = label === "Ready now"
          ? "No analyses are ready with the current selection."
          : "No analyses need setup in this view.";
        return `
          <section class="analysis-catalog-group analysis-catalog-group-empty ${sectionClass}">
            ${headerHtml}
            <div class="empty">${escapeHtml(emptyMessage)}</div>
          </section>
        `;
      }
      const gridClass = renderOptions.compact ? "analysis-catalog-grid analysis-catalog-grid-compact" : "analysis-catalog-grid";
      const cards = items.map((item) => renderAnalysisCatalogCard(item, renderOptions)).join("");
      return `<section class="analysis-catalog-group ${sectionClass}">${headerHtml}<div class="${gridClass}">${cards}</div></section>`;
    };
    analysisCatalogListEl.innerHTML = [
      renderReadinessSection("Ready now", readyItems, { compact: true }),
      renderReadinessSection("Needs setup", setupItems, { compact: true }),
    ].filter(Boolean).join("");
    if (analysisCatalogDrawerListEl) {
      analysisCatalogDrawerListEl.innerHTML = [
        renderReadinessSection("Ready now", readyItems, { drawer: true }),
        renderReadinessSection("Needs setup", setupItems, { drawer: true }),
      ].filter(Boolean).join("");
    }
    renderAnalysisCatalogAssayPanel();
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
      renderAnalysisCatalogDisclosureSummary();
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
      renderAnalysisCatalogDisclosureSummary();
      renderAnalysisCatalogAssayPanel();
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
      renderAnalysisCatalogDisclosureSummary();
      renderAnalysisCatalogAssayPanel();
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
    if (typeof setAnalysisContextMode === "function") setAnalysisContextMode("workspace");
    if (analysisCompareModeEl) {
      analysisCompareModeEl.checked = Boolean(item.default_compare_mode);
      renderAnalysisCompareMode();
    }
    if (analysisPromptEl) {
      analysisPromptEl.value = String(item.default_prompt || "").trim();
    }
    state.analysisExecutionMode = normalizeAnalysisCatalogExecutionMode(item.execution_mode);
    state.analysisSelectedCatalogItemId = String(item.id || "").trim();
    recordAnalysisCatalogUsage(state.analysisSelectedCatalogItemId);
    renderAnalysisCatalog();
    renderAnalysisCatalogAssayPanel();
    const setupState = selectedAnalysisSetupState(item);
    state.analysisExamplesPinnedOpen = false;
    syncCurrentAnalysisSessionFromUi({ render: true });
    if (analysisStatusEl) {
      analysisStatusEl.className = "query-status";
      analysisStatusEl.textContent = setupState.ready
        ? (item.guidance ? `${item.name} selected. ${item.guidance}` : `${item.name} selected. Review the prompt and run the analysis.`)
        : `${item.name} selected. ${setupState.message}`;
    }
    if (analysisCatalogDisclosureEl) {
      analysisCatalogDisclosureEl.open = Boolean(item.requires_assays || !setupState.ready);
    }
    setAnalysisCatalogDrawerOpen(false);
    renderAnalysisCatalogDisclosureSummary();
    if (String(item.execution_backend || "").trim().toLowerCase() === "job"
      && !state.backgroundWorkerStatus
      && typeof refreshBackgroundWorkerStatus === "function") {
      void refreshBackgroundWorkerStatus();
    }
    if (setupState.ready) {
      analysisPromptEl && analysisPromptEl.focus();
    } else {
      window.requestAnimationFrame(focusFirstIncompleteAnalysisSetup);
    }
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
    selectedAnalysisAssayDatasetNames,
    currentAnalysisCatalogItem,
    renderAnalysisCatalogAssayPanel,
    renderAnalysisFlowBar,
    analysisCatalogUiAvailability,
    renderAnalysisCatalogCard,
    setAnalysisCatalogDrawerOpen,
    renderAnalysisCatalog,
    renderAnalysisCatalogDisclosureSummary,
    setAnalysisCatalogSearch,
    setAnalysisCatalogFilter,
    loadAnalysisCatalog,
    applyAnalysisCatalogItemById,
    focusFirstIncompleteAnalysisSetup,
    handleAnalysisSetupAction,
  };
}
