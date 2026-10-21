/** Dataset installation controls; no credentials are persisted in browser storage. */
import { modalityIcon, modalityLabel } from './modalities.js';
export function createResourceInstaller({ escapeHtml, refresh, select }) {
  const el = (id) => document.getElementById(id);
  const add = el("resourceAdd"), panel = el("resourcePanel"), list = el("resourceList");
  const status = el("resourceStatus"), bar = el("resourceProgress");
  const cancel = el("resourceCancel"), use = el("resourceSelect"), file = el("resourceFile");
  let current = null, timer = null, busy = false, refreshedId = null;
  let monitoring = false, notice = null, notified = "";
  let catalogue = new Map();
  const terms = el("resourceTerms"), termsCheck = el("resourceTermsCheck"), termsAccept = el("resourceTermsAccept");
  function reviewSource(resource) {
    if (terms.open) return Promise.resolve(false);
    termsCheck.checked = false;
    termsAccept.disabled = true;
    terms.returnValue = "";
    el("resourceTermsTitle").textContent = `Download from ${resource.source_label}`;
    el("resourceTermsStudy").textContent = `${resource.source_label} study record`;
    el("resourceTermsPolicy").textContent = resource.source_policy_label;
    el("resourceTermsDescription").textContent = `COHORTome will download ${resource.name} and prepare it locally.`;
    el("resourceTermsStudy").href = resource.source_page;
    el("resourceTermsPolicy").href = resource.source_policy_url;
    el("resourceTermsStatement").textContent = resource.review_statement;
    el("resourceTermsAdditional").replaceChildren(...(resource.additional_source_links || []).map(link => {
      const anchor = document.createElement("a");
      anchor.href = link.url; anchor.textContent = link.label;
      anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
      return anchor;
    }));
    return new Promise(resolve => {
      terms.addEventListener("close", () => resolve(terms.returnValue === "reviewed" && termsCheck.checked), {once: true});
      terms.showModal();
    });
  }
  termsCheck?.addEventListener("change", () => { termsAccept.disabled = !termsCheck.checked; });
  termsAccept?.addEventListener("click", () => { if (termsCheck.checked) terms.close("reviewed"); });
  el("resourceTermsCancel")?.addEventListener("click", () => terms.close("cancel"));
  const acknowledgementKey = "cohortome.resource.notice.acknowledged";
  let acknowledged = "";
  try { acknowledged = sessionStorage.getItem(acknowledgementKey) || ""; } catch (_) {}
  const resultKey = job => job?.id ? `${job.id}:${job.stage}` : "";
  function acknowledge() {
    acknowledged = resultKey(current);
    if (acknowledged) {
      try { sessionStorage.setItem(acknowledgementKey, acknowledged); } catch (_) {}
    }
    notice?.remove();
    if (!busy) add.textContent = "＋ Add dataset";
  }
  const alreadyInstalled = job => Boolean(job.already_installed || job.message?.startsWith("Already installed"));
  function notifyFinished(job) {
    if (!job.id || !["ready", "failed", "cancelled"].includes(job.stage)) return;
    const key = `${job.id}:${job.stage}`;
    if (notified === key || acknowledged === key) return;
    notified = key;
    notice?.remove();
    notice = document.createElement("div");
    notice.className = "job-completion-notice resource-completion-notice";
    const message = document.createElement("span");
    message.setAttribute("role", "status");
    message.textContent = alreadyInstalled(job) ? "Dataset already installed — no changes made."
      : job.stage === "ready" ? `${job.name || "Dataset"}: import complete.`
      : job.stage === "failed" ? "Dataset import failed. Open the result for details." : "Dataset import cancelled.";
    const view = document.createElement("button");
    view.type = "button";
    view.textContent = "View import";
    view.onclick = () => { if (!panel.open) panel.showModal(); acknowledge(); };
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.textContent = "Dismiss";
    dismiss.onclick = acknowledge;
    notice.append(message, view, dismiss);
    document.body.append(notice);
  }
  async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed. Please retry.");
    return data;
  }
  function show(job) {
    current = job;
    busy = !["ready", "failed", "cancelled"].includes(job.stage);
    add.textContent = busy ? "View dataset installation…" : alreadyInstalled(job) ? "✓ Already installed — view"
      : job.stage === "ready" ? "✓ Import complete — view" : job.stage === "failed" ? "Import failed — view" : "＋ Add dataset";
    if (!busy && acknowledged === resultKey(job)) add.textContent = "＋ Add dataset";
    if (busy) notice?.remove();
    panel.dataset.installStage = job.stage;
    const title = el("resourceResultTitle");
    title.classList.toggle("is-hidden", busy);
    title.textContent = alreadyInstalled(job) ? "Already installed — no changes made."
      : ({ready: "Import complete", failed: "Import failed", cancelled: "Import cancelled"}[job.stage] || "");
    use.textContent = alreadyInstalled(job) ? "Select existing dataset" : "Add to workspace selection";
    status.textContent = job.message || ({
      queued: "Waiting to install…", uploading: "Uploading package…",
      downloading: "Downloading…", validating: "Validating package…",
      building: "Preparing source data locally…",
      preparing: "Preparing database… You can continue using the app.",
    }[job.stage] || job.stage);
    if (job.stage === "failed" && job.message?.includes("GitHub")) {
      el("resourceAccess").open = true;
      if (panel.open) el("resourceToken").focus();
    }
    bar.classList.toggle("is-hidden", !busy);
    if (job.stage === "downloading" && job.total) {
      bar.max = job.total;
      bar.value = job.bytes;
      status.textContent += ` ${Math.round(job.bytes / job.total * 100)}%`;
    } else bar.removeAttribute("value");
    cancel.classList.toggle("is-hidden", !busy || !job.cancellable);
    use.classList.toggle("is-hidden", job.stage !== "ready");
    use.disabled = job.stage === "ready" && refreshedId !== job.id;
    file.disabled = busy;
    el("resourceImport").disabled = busy;
    list.querySelectorAll("button").forEach((button) => { button.disabled = busy || button.dataset.included === "true"; });
    notifyFinished(job);
  }
  async function poll() {
    clearTimeout(timer);
    try {
      const { jobs } = await api("/resources/jobs", {cache: "no-store"});
      if (!monitoring) return;
      if (jobs.length) {
        show(jobs[0]);
        if (current.stage === "ready" && refreshedId !== current.id) {
          await refresh();
          refreshedId = current.id;
          use.disabled = false;
        }
        if (busy) timer = setTimeout(poll, 1000);
      } else if (busy && current?.id) {
        busy = false;
        show({ stage: "failed", message: "Installation was interrupted by a server restart. Please retry." });
      }
      if (busy && !jobs.length && !current?.id) timer = setTimeout(poll, 1000);
    } catch (error) {
      status.textContent = error.message;
      if (busy) timer = setTimeout(poll, 3000);
    }
  }
  async function browse() {
    const browseButton = el("resourceBrowse");
    browseButton.disabled = true;
    if (!list.children.length) list.innerHTML = '<p class="section-note">Loading catalogue…</p>';
    try {
      const { resources, repository } = await api("/resources");
      catalogue = new Map(resources.map(resource => [resource.dataset_id, resource]));
      list.innerHTML = resources.slice().sort((a, b) => Number(Boolean(a.included)) - Number(Boolean(b.included))).map((r) => `
        <article class="resource-card${r.included ? " resource-card-included" : ""}">
          <div class="resource-card-heading">
            <span class="resource-card-symbol">${modalityIcon(r.synthetic ? "clinical" : "assay", "")}</span>
            <div><h4>${escapeHtml(r.name)}</h4><span class="resource-card-meta">${((r.source_bytes || r.archive_bytes) / 1e6).toFixed(2)} MB${r.install_mode === "source" ? " source download" : ""} <span aria-hidden="true">·</span> ${escapeHtml(r.version)}</span></div>
            <span class="resource-kind">${r.synthetic ? "Synthetic" : "Research data"}</span>
          </div>
          <p class="resource-description">${escapeHtml(r.description)}</p>
          <div class="resource-modalities" aria-label="${escapeHtml(r.modalities)}">${(r.modality_keys || []).map(key => `<span>${modalityIcon(key, "")}${escapeHtml(modalityLabel(key))}</span>`).join("")}</div>
          <div class="resource-card-bottom">
          <details class="view-help"><summary>Source &amp; terms</summary><p>${escapeHtml(r.terms)}</p>
            ${r.source_page ? `<a href="${escapeHtml(r.source_page)}" target="_blank" rel="noopener noreferrer">${escapeHtml(r.source_label)} study record</a>` : ""}
            <a href="https://github.com/${escapeHtml(repository)}/tree/main/datasets/${encodeURIComponent(r.dataset_id)}" target="_blank" rel="noopener noreferrer">Preparation and source documentation</a></details>
          <button class="${r.included ? "resource-included" : "resource-install-button"}" type="button" data-resource="${escapeHtml(r.dataset_id)}" data-source="${r.install_mode === "source"}" data-included="${Boolean(r.included)}" ${busy || r.included ? "disabled" : ""}>${r.included ? "✓ Included" : r.install_mode === "source" ? "↓ Fetch and prepare" : "↓ Download and install"}</button>
          </div>
        </article>`).join("");
    } catch (error) { status.textContent = error.message; }
    finally { browseButton.disabled = false; }
  }
  add?.addEventListener("click", () => {
    if (!panel.open) panel.showModal();
    void browse(); void poll();
  });
  el("resourceClose")?.addEventListener("click", () => panel.close());
  panel?.addEventListener("close", () => {
    el("resourceToken").value = "";
    add.focus();
  });
  el("resourceImport")?.addEventListener("click", () => file.click());
  el("resourceBrowse")?.addEventListener("click", browse);
  list?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-resource]");
    if (!button || busy) return;
    const fromSource = button.dataset.source === "true";
    if (fromSource && !(await reviewSource(catalogue.get(button.dataset.resource)))) return;
    if (busy || !monitoring) return;
    const token = el("resourceToken").value.trim();
    el("resourceToken").value = "";
    show({ stage: "queued", cancellable: false });
    try {
      show(await api("/resources/download", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: button.dataset.resource, github_token: fromSource ? "" : token,
          source_terms_acknowledged: fromSource }),
      }));
      void poll();
    } catch (error) { show({ stage: "failed", message: error.message }); }
  });
  file?.addEventListener("change", async () => {
    const archive = file.files[0];
    if (!archive || busy) return;
    if (archive.size > 1024 ** 3) {
      status.textContent = "ZIP exceeds the 1 GiB upload limit."; file.value = ""; return;
    }
    show({ stage: "uploading", cancellable: false });
    // Polling also retrieves the upload's server job ID so Cancel becomes available.
    timer = setTimeout(poll, 500);
    try {
      show(await api("/resources/upload", { method: "POST", headers: { "Content-Type": "application/zip" }, body: archive }));
      void poll();
    } catch (error) { show({ stage: "failed", message: error.message }); }
    finally { file.value = ""; }
  });
  cancel?.addEventListener("click", async () => {
    if (!current?.id) return;
    try {
      await api(`/resources/jobs/${current.id}/cancel`, { method: "POST" });
      status.textContent = "Cancelling…";
    } catch (error) { status.textContent = error.message; }
  });
  use?.addEventListener("click", () => {
    if (current?.dataset_id) {
      acknowledge();
      panel.close();
      select(current.dataset_id);
      status.textContent = "Added to selection. Click Apply workspace when ready.";
    }
  });
  return { setAllowed(allowed) {
    add?.classList.toggle("is-hidden", !allowed);
    if (allowed && !monitoring) {
      monitoring = true;
      void poll(); // Reattach after a reload, not only when the dialog is opened.
    }
    if (!allowed) {
      if (terms?.open) terms.close("cancel");
      if (panel?.open) panel.close();
      clearTimeout(timer);
      monitoring = false;
      notice?.remove();
      notified = "";
      el("resourceToken").value = "";
    }
  } };
}
