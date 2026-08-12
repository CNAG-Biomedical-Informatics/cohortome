export function nowIso() {
  return new Date().toISOString();
}

export function shortTimestamp(value) {
  if (!value) {
    return "Just now";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Just now";
  }
  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function analysisSessionId() {
  return `analysis-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function currentStorageNamespace(authState) {
  if (authState && authState.enabled) {
    if (authState.authenticated && authState.user && authState.user.username) {
      return `user.${authState.user.username}`;
    }
    return "user.signed-out";
  }
  return "user.local";
}

export function createAnalysisSession(overrides = {}, defaultDataDir = "") {
  const session = overrides || {};
  return {
    id: session.id || analysisSessionId(),
    title: typeof session.title === "string" ? session.title : "",
    datasetId: typeof session.datasetId === "string" ? session.datasetId : "",
    dataDir: typeof session.dataDir === "string" ? session.dataDir : defaultDataDir,
    workspaceFingerprint: session.workspaceFingerprint && typeof session.workspaceFingerprint === "object" ? session.workspaceFingerprint : {},
    workspaceStatus: session.workspaceStatus && typeof session.workspaceStatus === "object" ? session.workspaceStatus : {},
    catalogItemId: typeof session.catalogItemId === "string" ? session.catalogItemId : "",
    promptDraft: typeof session.promptDraft === "string" ? session.promptDraft : "Summarize the main clinical patterns in this cohort and tell me what stands out.",
    contextMode: session.contextMode === "general" ? "general" : "workspace",
    scope: typeof session.scope === "string" ? session.scope : "",
    scopeMetadata: normalizeSelectionMetadata(session.scopeMetadata || session.scope_metadata || {}),
    compareMode: Boolean(session.compareMode),
    compareScope: typeof session.compareScope === "string" ? session.compareScope : "",
    compareScopeMetadata: normalizeSelectionMetadata(session.compareScopeMetadata || session.compare_scope_metadata || {}),
    savedCohortIdA: typeof session.savedCohortIdA === "string" ? session.savedCohortIdA : "",
    savedCohortIdB: typeof session.savedCohortIdB === "string" ? session.savedCohortIdB : "",
    history: Array.isArray(session.history) ? session.history : [],
    turns: Array.isArray(session.turns) ? session.turns : [],
    updatedAt: typeof session.updatedAt === "string" ? session.updatedAt : nowIso(),
  };
}

export function normalizeSelectionMetadata(source = {}) {
  const item = source && typeof source === "object" ? source : {};
  const sampleIds = normalizeIdList(item.sample_ids || item.sampleIds || []);
  const patientIds = normalizeIdList(item.patient_ids || item.patientIds || []);
  if (!sampleIds.length && !patientIds.length) {
    return {};
  }
  const derivedPatientIds = patientIds.length
    ? patientIds
    : Array.from(new Set(sampleIds.map((value) => value.split(":", 1)[0].trim()).filter(Boolean)));
  const normalizedSampleIds = sampleIds.length ? sampleIds : (derivedPatientIds.length ? derivedPatientIds.slice() : []);
  const datasetIds = normalizeIdList(item.dataset_ids || item.datasetIds || []);
  const sourceInfo = item.source && typeof item.source === "object" ? item.source : {};
  return {
    id: typeof item.id === "string" ? item.id : "",
    name: typeof item.name === "string" ? item.name : "",
    dataset_id: typeof item.dataset_id === "string" ? item.dataset_id : (typeof item.datasetId === "string" ? item.datasetId : ""),
    dataset_ids: datasetIds,
    data_dir: typeof item.data_dir === "string" ? item.data_dir : (typeof item.dataDir === "string" ? item.dataDir : ""),
    id_type: typeof item.id_type === "string" ? item.id_type : (typeof item.idType === "string" ? item.idType : (sampleIds.length ? "sample" : "patient")),
    sample_ids: normalizedSampleIds,
    patient_ids: derivedPatientIds,
    sample_count: normalizedSampleIds.length,
    patient_count: derivedPatientIds.length,
    is_full_dataset: Boolean(item.is_full_dataset || item.isFullDataset),
    source: {
      kind: typeof sourceInfo.kind === "string" ? sourceInfo.kind : (typeof item.source_kind === "string" ? item.source_kind : (typeof item.sourceKind === "string" ? item.sourceKind : "")),
      prompt: typeof sourceInfo.prompt === "string" ? sourceInfo.prompt : (typeof item.source_prompt === "string" ? item.source_prompt : (typeof item.sourcePrompt === "string" ? item.sourcePrompt : "")),
    },
  };
}

export function createSelectionMetadata(options = {}) {
  const source = options && typeof options === "object" ? options : {};
  return normalizeSelectionMetadata({
    id: source.id || "",
    name: source.name || "",
    dataset_id: source.datasetId || source.dataset_id || "",
    dataset_ids: source.datasetIds || source.dataset_ids || [],
    data_dir: source.dataDir || source.data_dir || "",
    id_type: source.idType || source.id_type || "",
    sample_ids: source.sampleIds || source.sample_ids || [],
    patient_ids: source.patientIds || source.patient_ids || [],
    source: {
      kind: source.sourceKind || source.source_kind || "",
      prompt: source.sourcePrompt || source.source_prompt || "",
    },
  });
}

function normalizeIdList(items) {
  const values = Array.isArray(items) ? items : String(items || "").split(",");
  const seen = new Set();
  return values.map((item) => String(item || "").trim()).filter((value) => {
    if (!value || seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

export function analysisSessionTitle(session) {
  const customTitle = String(session && session.title || "").trim();
  if (customTitle) {
    return customTitle;
  }
  const firstUserTurn = (session && session.turns || []).find((turn) => turn.role === "user" && turn.prompt);
  const raw = (firstUserTurn && firstUserTurn.prompt)
    || (session && session.compareMode ? "Compare cohorts" : "")
    || (String(session && session.scope || "").trim() ? "Scoped analysis" : "")
    || (session && session.promptDraft)
    || "New analysis";
  const trimmed = String(raw || "").trim();
  if (!trimmed) {
    return "New analysis";
  }
  return trimmed.length > 56 ? `${trimmed.slice(0, 56)}...` : trimmed;
}

export function analysisSessionScopeSummary(session) {
  const scopeIds = String(session && session.scope || "").split(",").map((item) => item.trim()).filter(Boolean);
  const compareIds = String(session && session.compareScope || "").split(",").map((item) => item.trim()).filter(Boolean);
  const scopeCount = scopeIds.length;
  const compareCount = compareIds.length;
  const scopeUnit = scopeIds.some((item) => item.includes(":")) ? "sample IDs" : "patient IDs";
  const compareUnit = compareIds.some((item) => item.includes(":")) ? "sample IDs" : "patient IDs";
  if (session && session.compareMode) {
    const aLabel = scopeCount ? `${scopeCount} ${scopeUnit} in A` : "full workspace in A";
    const bLabel = compareCount ? `${compareCount} ${compareUnit} in B` : "full workspace in B";
    return `${aLabel} vs ${bLabel}`;
  }
  return scopeCount ? `${scopeCount} ${scopeUnit} in scope` : "Full workspace";
}

export function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

export function renderInlineCode(value, escapeHtml) {
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
