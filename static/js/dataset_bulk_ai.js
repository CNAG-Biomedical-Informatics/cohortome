// Selection is UI state only; every operation still uses the existing
// permission-checked per-dataset endpoint.
export function createDatasetBulkAi({container, escapeHtml, reload, canManage}) {
  const selected = new Set();
  const labels = {blocked: 'Blocked', safe_summary: 'Summary only', detailed_allowed: 'Detailed context'};
  let notice = '';
  let menuEvents;
  let menuOpen = false;
  function mount(datasets) {
    menuEvents?.abort();
    menuEvents = new AbortController();
    for (const id of selected) if (!datasets.some(d => d.dataset_id === id)) selected.delete(id);
    const bar = document.createElement('div');
    bar.className = 'dataset-bulk-toolbar';
    bar.innerHTML = `<label><input type="checkbox" data-select-all> Select all</label>
      <div class="dataset-bulk-selection" data-selection hidden>
        <span data-count aria-live="polite"></span>
        <details class="dataset-bulk-menu">
          <summary>Actions <span aria-hidden="true">▾</span></summary>
          <div class="dataset-bulk-options">
            <span class="dataset-bulk-group">Data</span>
            <button type="button" data-prepare>Rebuild DuckDB</button>
            <span class="dataset-bulk-group">Permissions</span>
            <button type="button" data-edit>Change AI permissions…</button>
          </div>
        </details>
        <button type="button" class="query-chip secondary-btn" data-clear>Clear</button>
      </div>
      <span role="status" data-status></span>`;
    container.prepend(bar);
    const boxes = [];
    const all = bar.querySelector('[data-select-all]');
    const edit = bar.querySelector('[data-edit]');
    const prepare = bar.querySelector('[data-prepare]');
    const menu = bar.querySelector('details');
    menu.open = menuOpen;
    const closeMenu = () => { menuOpen = false; menu.open = false; };
    menu.querySelector('summary').addEventListener('click', () => { menuOpen = !menu.open; });
    function sync() {
      const selectedDatasets = datasets.filter(d => selected.has(d.dataset_id));
      const preparable = selectedDatasets.filter(d => !d.query_store_status?.ready
        && String(d.query_store_status?.status || 'not_built') !== 'building');
      boxes.forEach(box => {
        box.checked = selected.has(box.value);
        box.closest('[data-dataset-admin-card]').classList.toggle('is-bulk-selected', box.checked);
      });
      all.checked = datasets.length > 0 && selected.size === datasets.length;
      all.disabled = !datasets.length;
      all.indeterminate = selected.size > 0 && !all.checked;
      edit.disabled = !selected.size;
      prepare.disabled = !preparable.length;
      prepare.textContent = preparable.length ? `Rebuild DuckDB (${preparable.length})` : 'Rebuild DuckDB';
      prepare.title = preparable.length ? 'Rebuild stores that are not ready.' : 'Selected stores are already ready or being built.';
      bar.querySelector('[data-selection]').hidden = !selected.size;
      if (!selected.size) closeMenu();
      bar.querySelector('[data-count]').textContent = `${selected.size} selected`;
      bar.querySelector('[data-status]').textContent = notice;
    }
    container.querySelectorAll('[data-dataset-admin-card]').forEach(card => {
      const box = document.createElement('input');
      box.type = 'checkbox'; box.value = card.dataset.datasetAdminCard;
      box.setAttribute('aria-label', `Select ${datasets.find(d => d.dataset_id === box.value)?.name || box.value}`);
      box.addEventListener('click', event => event.stopPropagation());
      box.addEventListener('change', () => { box.checked ? selected.add(box.value) : selected.delete(box.value); sync(); });
      card.querySelector('summary').prepend(box); boxes.push(box);
    });
    all.onchange = () => { selected.clear(); if (all.checked) datasets.forEach(d => selected.add(d.dataset_id)); sync(); };
    bar.querySelector('[data-clear]').onclick = () => { selected.clear(); sync(); all.focus(); };
    edit.onclick = () => { closeMenu(); review(datasets.filter(d => selected.has(d.dataset_id))); };
    prepare.onclick = () => { closeMenu(); reviewPreparation(datasets.filter(d => selected.has(d.dataset_id))); };
    document.addEventListener('click', event => { if (!menu.contains(event.target)) closeMenu(); }, {signal:menuEvents.signal});
    menu.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault(); closeMenu(); menu.querySelector('summary').focus();
      }
    });
    sync();
  }
  function reviewPreparation(datasets) {
    if (!canManage()) return;
    const candidates = datasets.filter(d => !d.query_store_status?.ready
      && String(d.query_store_status?.status || 'not_built') !== 'building');
    if (!candidates.length) return;
    const skipped = datasets.length - candidates.length;
    const dialog = document.createElement('dialog');
    dialog.className = 'dataset-remove-dialog';
    dialog.setAttribute('aria-label', 'Rebuild query stores');
    dialog.innerHTML = `<h3>Rebuild query stores</h3>
      <p>COHORTome will rebuild ${candidates.length} dataset-local DuckDB ${candidates.length === 1 ? 'index' : 'indexes'}, one at a time.</p>
      <ul>${candidates.map(d => `<li>${escapeHtml(d.name || d.dataset_id)}</li>`).join('')}</ul>
      ${skipped ? `<p>${skipped} selected ${skipped === 1 ? 'dataset is' : 'datasets are'} already ready or currently being prepared.</p>` : ''}
      <p role="status"></p><div class="dataset-picker-actions"><button type="button" class="secondary-btn" data-cancel>Cancel</button>
      <button type="button" class="primary-btn" data-apply>Rebuild ${candidates.length} ${candidates.length === 1 ? 'store' : 'stores'}</button></div>`;
    document.body.append(dialog);
    let busy = false;
    const cancel = dialog.querySelector('[data-cancel]');
    const apply = dialog.querySelector('[data-apply]');
    const status = dialog.querySelector('[role=status]');
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    cancel.onclick = () => dialog.close();
    apply.onclick = async () => {
      if (busy || !canManage()) return;
      busy = true;
      dialog.querySelectorAll('button').forEach(button => { button.disabled = true; });
      const failures = [];
      let prepared = 0;
      for (const [index, dataset] of candidates.entries()) {
        status.textContent = `Rebuilding ${index + 1} of ${candidates.length}: ${dataset.name || dataset.dataset_id}…`;
        try {
          const response = await fetch(`/datasets/${encodeURIComponent(dataset.dataset_id)}/prepare-store`, {method: 'POST'});
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || 'Build failed.');
          prepared += 1;
        } catch (error) {
          failures.push({dataset, message: error.message || 'Build failed.'});
        }
      }
      selected.clear();
      failures.forEach(({dataset}) => selected.add(dataset.dataset_id));
      notice = failures.length
        ? `Rebuilt ${prepared} ${prepared === 1 ? 'store' : 'stores'}; ${failures.length} failed.`
        : `Rebuilt ${prepared} ${prepared === 1 ? 'store' : 'stores'}.`;
      await reload({preservePendingSelection: true});
      if (!failures.length) {
        dialog.close();
        return;
      }
      busy = false;
      status.textContent = failures.map(({dataset, message}) => `${dataset.name || dataset.dataset_id}: ${message}`).join(' ');
      cancel.textContent = 'Close';
      cancel.disabled = false;
    };
    dialog.showModal();
  }
  function review(datasets) {
    if (!canManage()) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'dataset-remove-dialog';
    dialog.setAttribute('aria-label', 'Change AI permissions');
    dialog.innerHTML = `<h3>Change AI permissions</h3>
      <ul>${datasets.map(d => `<li>${escapeHtml(d.name || d.dataset_id)} — ${escapeHtml(labels[d.ai_provider_access] || d.ai_provider_access)}</li>`).join('')}</ul>
      <label>New permission <select>${Object.entries(labels).map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></label>
      <p>Private datasets remain blocked from external providers. Classification and user access will not change.</p>
      <p role="status"></p><div class="dataset-picker-actions"><button type="button" class="query-chip" data-cancel>Cancel</button>
      <button type="button" class="query-chip" data-apply>Apply to ${datasets.length} datasets</button></div>`;
    document.body.append(dialog);
    let busy = false;
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('cancel', e => { if (busy) e.preventDefault(); });
    dialog.querySelector('[data-cancel]').onclick = () => dialog.close();
    dialog.querySelector('[data-apply]').onclick = async () => {
      if (busy || !canManage()) return;
      busy = true;
      dialog.querySelectorAll('button,select').forEach(el => { el.disabled = true; });
      const status = dialog.querySelector('[role=status]');
      status.textContent = 'Saving permissions…';
      try {
        const response = await fetch('/datasets/bulk-ai-access', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({dataset_ids: datasets.map(d => d.dataset_id), ai_provider_access: dialog.querySelector('select').value})});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || 'Unable to update permissions.');
        notice = `AI permissions updated for ${datasets.length} datasets.`;
        selected.clear();
        await reload({preservePendingSelection: true});
        dialog.close();
      } catch (error) { status.textContent = error.message || 'Unable to update permissions.'; }
      finally { busy = false; dialog.querySelectorAll('button,select').forEach(el => { el.disabled = false; }); }
    };
    dialog.showModal();
  }
  return {mount};
}
