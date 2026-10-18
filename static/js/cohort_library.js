import { downloadIcon } from './shared.js';

const iconPaths = {
  cohort: '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3"/>',
  inspect: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
  'load-analysis': '<path d="M4 3v17h17M8 16v-4M13 16V7M18 16v-7"/>',
  'load-pheno': '<circle cx="5" cy="6" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="10" cy="19" r="3"/><path d="m8 6 7 1M6 9l3 7m7-6-4 6"/>',
  'load-datasets': '<path d="M3 7h7l2 2h9v11H3Z"/><path d="M3 7V4h7l2 3h8v2"/>',
  rename: '<path d="m16 3 5 5-12 12H4v-5ZM14 5l5 5"/>',
  delete: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
};
const icon = name => `<span class="button-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${iconPaths[name] || ''}</svg></span>`;

export function createCohortLibrary({escapeHtml: esc, datasetLabels, activeIds, restoreWorkspace, reloadScope, onAction}) {
  const list = document.getElementById('cohortLibraryList');
  const search = document.getElementById('cohortLibrarySearch');
  const suggestions = document.getElementById('cohortLibrarySuggestions');
  const status = document.getElementById('cohortLibraryStatus');
  const pages = document.getElementById('cohortLibraryPages');
  let items = [], page = 0, revision = 0;
  const pageSize = 12;
  const say = message => { if (status) status.textContent = message; };
  const find = id => items.find(item => item.id === id);
  const ready = item => item.dataset_ids?.length && item.dataset_ids.every(id => activeIds().includes(id));
  const action = (item, key, label, disabled = false) => `<button type="button" class="query-chip" data-saved-cohort-id="${esc(item.id)}" data-saved-cohort-action="${key}" ${disabled ? 'disabled' : ''}>${key.startsWith('export') ? downloadIcon() : icon(key)}${label}</button>`;

  function render() {
    if (!list) return;
    if (suggestions) suggestions.innerHTML = items.map(item =>
      `<option value="${esc(item.name)}" label="${esc(datasetLabels(item.dataset_ids || []).join(' · '))}"></option>`).join('');
    const term = search.value.trim().toLocaleLowerCase();
    const matches = items.filter(item => [item.name, ...(item.dataset_ids || []), ...datasetLabels(item.dataset_ids || [])].join(' ').toLocaleLowerCase().includes(term));
    page = Math.min(page, Math.max(0, Math.ceil(matches.length / pageSize) - 1));
    list.innerHTML = matches.length ? `<div class="cohort-library-grid">${matches.slice(page * pageSize, (page + 1) * pageSize).map(item => {
      const available = ready(item);
      const date = new Date(item.created_at);
      return `<article class="cohort-library-card">
        <div class="cohort-card-top">
          <span class="cohort-card-symbol">${icon('cohort')}</span>
          <span class="cohort-card-state ${available ? 'is-loaded' : ''}">${available ? 'Datasets loaded' : 'Datasets not loaded'}</span>
          <details class="cohort-card-menu cohort-card-manage"><summary aria-label="Manage ${esc(item.name)}" title="Manage cohort">${icon('more')}</summary>
            <div class="cohort-card-menu-items">${action(item, 'rename', 'Rename')}${action(item, 'delete', 'Delete')}</div>
          </details>
        </div>
        <h3>${esc(item.name)}</h3>
        <div class="cohort-library-datasets">${datasetLabels(item.dataset_ids || []).map(label => `<span>${esc(label)}</span>`).join('')}</div>
        <dl class="cohort-card-counts">
          <div><dt>Patients</dt><dd>${Number(item.patient_count || 0).toLocaleString()}</dd></div>
          <div><dt>Samples</dt><dd>${Number(item.sample_count || 0).toLocaleString()}</dd></div>
        </dl>
        <div class="cohort-card-actions saved-cohort-actions">
          ${action(item, 'inspect', 'Members')}
          <details class="cohort-card-menu cohort-library-more"><summary>${downloadIcon()}Export</summary>
            <div class="cohort-card-menu-items">
              ${action(item, 'export-clinical', 'Export clinical data')}
              ${action(item, 'export-molecular', 'Export molecular data')}
              ${action(item, 'export', 'Export membership')}
            </div>
          </details>
        </div>
        <div class="cohort-card-footer">
          <small>Created ${Number.isNaN(date.getTime()) ? 'date unavailable' : esc(date.toLocaleDateString())}</small>
          <div class="saved-cohort-actions">${available ? '<span class="cohort-card-use-label">Use in</span>' + action(item, 'load-analysis', 'Analysis') + action(item, 'load-pheno', 'Pheno-Ranker') : action(item, 'load-datasets', 'Load datasets')}</div>
        </div>
      </article>`;
    }).join('')}</div>` : `<div class="empty">${items.length ? 'No cohorts match your search.' : 'No accessible saved cohorts. Save a patient or sample selection to create one.'}</div>`;
    pages.innerHTML = matches.length > pageSize ? `<button class="query-chip" data-page="-1" ${page === 0 ? 'disabled' : ''}>Previous</button><span>${page * pageSize + 1}–${Math.min(matches.length, (page + 1) * pageSize)} of ${matches.length}</span><button class="query-chip" data-page="1" ${(page + 1) * pageSize >= matches.length ? 'disabled' : ''}>Next</button>` : '';
  }

  async function load() {
    const current = ++revision;
    say('Loading cohorts…');
    try {
      const response = await fetch('/saved-cohorts/library', {cache: 'no-store'});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to load cohorts.');
      if (current !== revision) return;
      items = payload.cohorts || [];
      render();
      say(`${items.length} saved cohort${items.length === 1 ? '' : 's'}`);
    } catch (error) {
      if (current !== revision) return;
      items = []; render(); say(error.message);
    }
  }

  function inspect(item) {
    document.getElementById('cohortMembersDialog')?.remove();
    const dialog = document.createElement('dialog');
    dialog.id = 'cohortMembersDialog';
    dialog.className = 'chat-move-dialog cohort-members-dialog';
    dialog.setAttribute('aria-labelledby', 'cohortMembersTitle');
    dialog.innerHTML = `<h3 id="cohortMembersTitle">${esc(item.name)}</h3><div class="cohort-members-table"></div><div class="saved-cohort-actions"><button class="query-chip" data-prev>Previous</button><span role="status"></span><button class="query-chip" data-next>Next</button><button class="query-chip" data-close>Close</button></div>`;
    const members = item.members || [];
    let offset = 0;
    const draw = () => {
      dialog.querySelector('.cohort-members-table').innerHTML = `<table class="assay-table"><thead><tr><th>Dataset</th><th>Patient ID</th><th>Sample ID</th></tr></thead><tbody>${members.slice(offset, offset + 50).map(member => `<tr><td>${esc(datasetLabels([member.dataset_id])[0] || member.dataset_id)}</td><td>${esc(member.patient_id)}</td><td>${esc(member.sample_id || '—')}</td></tr>`).join('')}</tbody></table>`;
      dialog.querySelector('[role=status]').textContent = members.length ? `${offset + 1}–${Math.min(offset + 50, members.length)} of ${members.length}` : 'No members';
      dialog.querySelector('[data-prev]').disabled = offset === 0;
      dialog.querySelector('[data-next]').disabled = offset + 50 >= members.length;
    };
    dialog.querySelector('[data-prev]').onclick = () => { offset -= 50; draw(); };
    dialog.querySelector('[data-next]').onclick = () => { offset += 50; draw(); };
    dialog.querySelector('[data-close]').onclick = () => dialog.close();
    dialog.onclose = () => dialog.remove();
    document.body.append(dialog); draw(); dialog.showModal();
  }

  search?.addEventListener('input', () => { page = 0; render(); });
  pages?.addEventListener('click', event => {
    const button = event.target.closest('[data-page]');
    if (button && !button.disabled) { page += Number(button.dataset.page); render(); }
  });
  document.getElementById('cohortLibraryRefresh')?.addEventListener('click', load);
  document.addEventListener('click', event => {
    list?.querySelectorAll('.cohort-card-menu[open]').forEach(menu => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });
  list?.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const menu = event.target.closest('.cohort-card-menu[open]');
    if (menu) { menu.open = false; menu.querySelector('summary').focus(); }
  });
  list?.addEventListener('click', async event => {
    const button = event.target.closest('[data-saved-cohort-action]');
    if (!button || button.disabled) return;
    const menu = button.closest('.cohort-card-menu');
    if (menu) menu.open = false;
    const item = find(button.dataset.savedCohortId);
    if (!item) return;
    const key = button.dataset.savedCohortAction;
    if (key === 'inspect') return inspect(item);
    if (key === 'load-datasets') {
      button.disabled = true; say('Loading cohort datasets…');
      try { await restoreWorkspace(item.dataset_id); await reloadScope(); render(); say('Datasets loaded. Choose Analysis or Pheno-Ranker.'); }
      catch (error) { say(error.message); button.disabled = false; }
      return;
    }
    if (key.startsWith('load-') && !ready(item)) { render(); say('Load this cohort’s datasets first.'); return; }
    if (key === 'load-analysis' || key === 'load-pheno') {
      button.disabled = true;
      try { await reloadScope(item.id); }
      catch (error) { say(error.message); button.disabled = false; return; }
      if (!ready(item)) { render(); say('Load this cohort’s datasets first.'); return; }
    }
    if (key === 'delete' && !window.confirm(`Delete cohort "${item.name}"? Source data and existing run files are kept.`)) return;
    onAction(button);
  });
  return {load, render, find, say, clear() { ++revision; items = []; page = 0; if (search) search.value = ''; render(); say(''); document.getElementById('cohortMembersDialog')?.remove(); }};
}
