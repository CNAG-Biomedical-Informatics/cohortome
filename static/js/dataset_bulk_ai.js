// Selection is UI state only; permissions remain on individual datasets.
export function createDatasetBulkAi({container, escapeHtml, reload, canManage}) {
  const selected = new Set();
  const labels = {blocked: 'Blocked', safe_summary: 'Summary only', detailed_allowed: 'Detailed context'};
  let notice = '';
  function mount(datasets) {
    for (const id of selected) if (!datasets.some(d => d.dataset_id === id)) selected.delete(id);
    const bar = document.createElement('div');
    bar.className = 'dataset-bulk-toolbar';
    bar.innerHTML = `<label><input type="checkbox" data-select-all> Select all</label>
      <span data-count></span><button type="button" class="query-chip" data-edit>Change AI permissions</button>
      <span role="status" data-status></span>`;
    container.prepend(bar);
    const boxes = [];
    const all = bar.querySelector('[data-select-all]');
    const edit = bar.querySelector('[data-edit]');
    function sync() {
      boxes.forEach(box => { box.checked = selected.has(box.value); });
      all.checked = datasets.length > 0 && selected.size === datasets.length;
      all.indeterminate = selected.size > 0 && !all.checked;
      edit.disabled = !selected.size;
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
    edit.onclick = () => review(datasets.filter(d => selected.has(d.dataset_id)));
    sync();
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
