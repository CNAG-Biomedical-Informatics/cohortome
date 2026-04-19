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
    dataDir: typeof session.dataDir === "string" ? session.dataDir : defaultDataDir,
    catalogItemId: typeof session.catalogItemId === "string" ? session.catalogItemId : "",
    promptDraft: typeof session.promptDraft === "string" ? session.promptDraft : "Summarize the main clinical patterns in this cohort and tell me what stands out.",
    scope: typeof session.scope === "string" ? session.scope : "",
    compareMode: Boolean(session.compareMode),
    compareScope: typeof session.compareScope === "string" ? session.compareScope : "",
    savedCohortIdA: typeof session.savedCohortIdA === "string" ? session.savedCohortIdA : "",
    savedCohortIdB: typeof session.savedCohortIdB === "string" ? session.savedCohortIdB : "",
    history: Array.isArray(session.history) ? session.history : [],
    turns: Array.isArray(session.turns) ? session.turns : [],
    updatedAt: typeof session.updatedAt === "string" ? session.updatedAt : nowIso(),
  };
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
