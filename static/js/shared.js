export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function renderActivityCard(label, detail) {
  return `
    <div class="analysis-pending-card">
      <div class="analysis-turn-meta">
        <span class="query-chip badge">pending</span>
        <span class="query-chip badge">${escapeHtml(label || "Working")}</span>
      </div>
      <div class="analysis-pending-row">
        <div class="analysis-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></div>
        <span>${escapeHtml(detail || "Working on your request.")}</span>
      </div>
    </div>
  `;
}

export function fallbackCopyText(text) {
  const previousFocus = document.activeElement;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  const selection = document.getSelection();
  const selectedRange = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  let success = false;
  try {
    success = document.execCommand("copy");
  } catch (_error) {
    success = false;
  }
  document.body.removeChild(textarea);
  if (previousFocus && previousFocus.isConnected && typeof previousFocus.focus === "function") {
    previousFocus.focus({ preventScroll: true });
  }
  if (selectedRange && selection) {
    selection.removeAllRanges();
    selection.addRange(selectedRange);
  }
  return success;
}
