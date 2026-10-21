export function createResourceStorage() {
  const el = id => document.getElementById(id);
  const panel = el("resourceStorageSettings"), input = el("resourceStorageDirectory");
  const status = el("resourceStorageStatus"), save = el("resourceStorageSave"), browse = el("resourceStorageBrowse");
  function fill(data) {
    input.value = data.directory;
    status.textContent = `${(data.free_bytes / 1024 ** 3).toFixed(1)} GiB available.`;
  }
  browse.hidden = !(window.__COHORTOME_DESKTOP__ && window.__TAURI__?.core);
  browse.addEventListener("click", async () => {
    try {
      const directory = await window.__TAURI__.core.invoke("pick_dataset_folder");
      if (directory) { input.value = directory; status.textContent = "Save to use this folder for new imports."; }
    } catch (_error) { status.textContent = "Could not open the folder picker. You can enter the path directly."; }
  });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const response = await fetch("/resource-storage", { method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({directory: input.value.trim()}) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Enter an existing absolute folder path.");
      fill(data);
      status.textContent = `Storage folder saved. New imports use this folder; existing datasets are unchanged. ${(data.free_bytes / 1024 ** 3).toFixed(1)} GiB available.`;
    } catch (error) { status.textContent = error.message; }
    finally { save.disabled = false; }
  });
  return { async load() {
    try {
      const response = await fetch("/resource-storage");
      panel.hidden = response.status === 403;
      if (response.status === 403) { input.value = ""; return; }
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not read storage settings.");
      fill(data);
    } catch (error) { status.textContent = error.message; }
  } };
}
