/** Dataset installation controls; no credentials are persisted in browser storage. */
import {createResourcesView,createResourceTermsView,createResourceNoticeView} from './react/ui.js';
export function createResourceInstaller({ escapeHtml, refresh, select }) {
  const el = (id) => document.getElementById(id);
  const add = el("resourceAdd"), panel = el("resourcePanel"), list = el("resourceList");
  const status = el("resourceStatus"), bar = el("resourceProgress");
  const cancel = el("resourceCancel"), use = el("resourceSelect"), file = el("resourceFile");
  let current = null, timer = null, busy = false, refreshedId = null;
  let monitoring = false, notified = "";
  const noticeHost = document.createElement("div");
  document.body.append(noticeHost);
  const noticeView = createResourceNoticeView(noticeHost);
  let catalogue = new Map();
  let category = 'all';
  const catalogueView = list ? createResourcesView(list,el('resourceFilters')) : null;
  let repositoryName = '', loadedCatalogue = false;
  function filterCatalogue() {
    if (!loadedCatalogue || !catalogueView) return;
    const resources=[...catalogue.values()];
    catalogueView.render({resources,repository:repositoryName,busy,category});
    if(el('resourceFilterEmpty')) el('resourceFilterEmpty').hidden = resources.some(r=>category==='all' || (r.install_mode || 'archive')===category);
  }
  function filterResources(event) {
    const button = event.target.closest('[data-category]');
    if (!button) return;
    category = button.dataset.category;
    filterCatalogue();
  }
  const terms = el("resourceTerms");
  const termsView = terms ? createResourceTermsView(terms) : null;
  function reviewSource(resource) {
    if (!termsView || terms.open) return Promise.resolve(false);
    let checked = false;
    terms.returnValue = "";
    function renderTerms() {
      termsView.render({resource,checked,onCheck:value=>{checked=value;renderTerms();},
        onCancel:()=>terms.close("cancel"),
        onAccept:()=>{if(checked) terms.close("reviewed");}});
    }
    renderTerms();
    return new Promise(resolve => {
      terms.addEventListener("close", () => resolve(terms.returnValue === "reviewed" && checked), {once:true});
      terms.showModal();
    });
  }
  const acknowledgementKey = "cohortome.resource.notice.acknowledged";
  let acknowledged = "";
  try { acknowledged = sessionStorage.getItem(acknowledgementKey) || ""; } catch (_) {}
  const resultKey = job => job?.id ? `${job.id}:${job.stage}` : "";
  function acknowledge() {
    acknowledged = resultKey(current);
    if (acknowledged) {
      try { sessionStorage.setItem(acknowledgementKey, acknowledged); } catch (_) {}
    }
    noticeView.render(null);
    if (!busy) add.textContent = "＋ Add dataset";
  }
  const alreadyInstalled = job => Boolean(job.already_installed || job.message?.startsWith("Already installed"));
  function notifyFinished(job) {
    if (!job.id || !["ready", "failed", "cancelled"].includes(job.stage)) return;
    const key = `${job.id}:${job.stage}`;
    if (notified === key || acknowledged === key) return;
    notified = key;
    noticeView.render(null);
    const message = alreadyInstalled(job) ? "Dataset already installed — no changes made."
      : job.stage === "ready" ? `${job.name || "Dataset"}: import complete.`
      : job.stage === "failed" ? "Dataset import failed. Open the result for details." : "Dataset import cancelled.";
    noticeView.render({message,
      onView:()=>{if(!panel.open) panel.showModal();acknowledge();},
      onDismiss:acknowledge});
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
    if (busy) noticeView.render(null);
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
    filterCatalogue();
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
  async function browse(refreshCatalogue = false) {
    const browseButton = el("resourceBrowse");
    browseButton.disabled = true;
    if (!loadedCatalogue) catalogueView?.render({loading:true});
    try {
      const { resources, repository, message, catalogue_source } = await api(
        refreshCatalogue ? "/resources/refresh" : "/resources",
        refreshCatalogue ? { method: "POST" } : { cache: "no-store" });
      el("resourceCatalogueStatus").textContent = message || (catalogue_source === "cached"
        ? "Saved COHORTome-store catalogue. Refresh to check for new datasets."
        : "Bundled catalogue. Refresh to check COHORTome-store for new datasets.");
      catalogue = new Map(resources.map(resource => [resource.dataset_id, resource]));
      repositoryName = repository;
      loadedCatalogue = true;
      filterCatalogue();
    } catch (error) { status.textContent = error.message; }
    finally { browseButton.disabled = false; }
  }
  function openResources() {
    if (!panel.open) panel.showModal();
    void browse(true); void poll();
  }
  function closeResources() { return panel.close(); }
  function closedResources() {
    el("resourceToken").value = "";
    add.focus();
  }
  function pickArchive() { return file.click(); }
  function refreshResources() { return browse(true); }
  async function downloadResource(event) {
    const button = event.target.closest("[data-resource]");
    if (!button || button.disabled || busy) return;
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
  }
  async function importArchive() {
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
  }
  async function cancelInstall() {
    if (!current?.id) return;
    try {
      await api(`/resources/jobs/${current.id}/cancel`, { method: "POST" });
      status.textContent = "Cancelling…";
    } catch (error) { status.textContent = error.message; }
  }
  function useDataset() {
    if (current?.dataset_id) {
      acknowledge();
      panel.close();
      select(current.dataset_id);
      status.textContent = "Added to selection. Click Apply workspace when ready.";
    }
  }
  return { filterResources, openResources, closeResources, closedResources, pickArchive, refreshResources, downloadResource, importArchive, cancelInstall, useDataset, setAllowed(allowed) {
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
      noticeView.render(null);
      notified = "";
      el("resourceToken").value = "";
    }
  } };
}
