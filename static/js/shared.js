export function chatCopyButton() {
  return '<button type="button" class="chat-copy-button" data-chat-copy title="Copy message" aria-label="Copy message"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg><span class="chat-copy-status" aria-live="polite"></span></button>';
}

if (typeof document !== "undefined") document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-chat-copy]");
  if (!button || button.disabled) return;
  const content = button.closest("article")?.querySelector("[data-chat-copy-content]");
  if (!content) return;
  const clone = content.cloneNode(true);
  clone.querySelectorAll("[data-query-sort]").forEach(el => el.replaceWith(document.createTextNode(el.textContent.replace(/[↑↓↕]/g, "").trim())));
  clone.querySelectorAll("[id]").forEach(el => el.removeAttribute("id"));
  clone.querySelectorAll("button, input, select, svg, script, style").forEach(el => el.remove());
  clone.style.cssText = "position:fixed;left:-100000px;top:0;width:900px";
  clone.setAttribute("aria-hidden", "true");
  document.body.appendChild(clone);
  const text = clone.innerText.trim();
  clone.remove();
  button.disabled = true;
  const status = button.querySelector(".chat-copy-status");
  try {
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); copied = true; } catch (_) { /* HTTP/denied clipboard falls back below. */ }
    }
    if (!copied && !fallbackCopyText(text)) throw new Error("Clipboard unavailable");
    status.textContent = "Copied";
  } catch (_) {
    status.textContent = "Could not copy";
  } finally {
    button.disabled = false;
    window.setTimeout(() => { status.textContent = ""; }, 2000);
  }
});

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

export async function downloadFile(url, filename) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "Download unavailable. Check your access and try again.");
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
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
