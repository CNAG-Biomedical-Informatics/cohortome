export function openDicomFolderDialog(datasets, escapeHtml) {
    const dialog = document.createElement('dialog');
    dialog.className = 'dicom-folder-dialog';
    dialog.innerHTML = `<form><h3>Link DICOM files</h3>
      <label>Dataset<select name="dataset">${datasets.map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`).join('')}</select></label>
      <label>${window.__COHORTOME_DESKTOP__ ? 'Local folder' : 'Folder on the server'}<input name="directory" required autocomplete="off" placeholder="Absolute folder path"></label>
      <button type="button" class="query-chip" data-browse ${window.__TAURI__?.core ? '' : 'hidden'}>Choose folder…</button>
      <p>Files stay in this folder. DICOM PatientID must match a patient ID in this dataset. Linking replaces its previous folder links; no images are copied or deleted.</p>
      <p>COHORTome does not anonymize or certify these files. Only link data you are permitted to use.</p>
      <div role="status" aria-live="polite"></div>
      <div class="dicom-folder-actions"><button type="button" class="query-chip" data-cancel>Cancel</button><button type="submit" class="query-chip">Validate and link</button></div></form>`;
    document.body.append(dialog);
    dialog.showModal();
    const form = dialog.querySelector('form'), status = dialog.querySelector('[role=status]');
    const submit = form.querySelector('[type=submit]');
    let busy = false;
    dialog.querySelector('[data-cancel]').onclick = () => { if (!busy) dialog.close(); };
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => dialog.remove());
    dialog.querySelector('[data-browse]').onclick = async () => {
      try {
        const directory = await window.__TAURI__.core.invoke('pick_dataset_folder');
        if (directory) form.elements.directory.value = directory;
      } catch (_) { status.textContent = 'Could not open the folder picker. Enter the path instead.'; }
    };
    form.onsubmit = async event => {
      event.preventDefault();
      busy = true; submit.disabled = true;
      status.textContent = 'Reading DICOM headers and checking patient links…';
      try {
        const response = await fetch(`/local-viewer/datasets/${encodeURIComponent(form.elements.dataset.value)}/folder`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({directory: form.elements.directory.value.trim()}),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not link this folder.');
        status.textContent = `Linked ${result.studies} studies, ${result.instances} instances and ${result.patients} patients. Files remain in their original folder.`;
        submit.hidden = true;
        dialog.querySelector('[data-cancel]').textContent = 'Done';
      } catch (error) { status.textContent = error.message; }
      finally { busy = false; submit.disabled = false; }
    };
}
