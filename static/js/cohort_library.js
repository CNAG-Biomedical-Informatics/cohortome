import {createCohortLibraryView, inspectCohortMembers} from './react/ui.js';

export function createCohortLibrary({datasetLabels, activeIds, addRequiredDatasets, reloadScope, onAction}) {
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
  const view = list ? createCohortLibraryView(list,pages,suggestions) : null;
  function render() {
    if (!view) return;
    const term = search.value.trim().toLocaleLowerCase();
    const matches = items.filter(item => [item.name, ...(item.dataset_ids || []), ...datasetLabels(item.dataset_ids || [])].join(' ').toLocaleLowerCase().includes(term));
    page = Math.min(page, Math.max(0, Math.ceil(matches.length / pageSize) - 1));
    view.render({items:matches.slice(page*pageSize,(page+1)*pageSize).map(item=>({...item,available:ready(item),labels:datasetLabels(item.dataset_ids || [])})),
      suggestions:items.map(item=>({...item,labels:datasetLabels(item.dataset_ids || [])})),
      hasItems:!!items.length,page,pageSize,total:matches.length});
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

  function inspect(item) { inspectCohortMembers(item,datasetLabels); }

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
      button.disabled = true; say('Adding required datasets…');
      try {
        const added = await addRequiredDatasets(item.dataset_ids);
        await reloadScope(); render();
        say(`Added ${added} ${added === 1 ? 'dataset' : 'datasets'}; existing datasets retained. Choose Analysis or Pheno-Ranker.`);
      }
      catch (error) { say(error.message); button.disabled = false; }
      finally { button.disabled = false; }
      return;
    }
    if (key.startsWith('load-') && !ready(item)) { render(); say('Load this cohort’s datasets first.'); return; }
    if (key === 'load-analysis' || key === 'load-pheno') {
      button.disabled = true;
      try { await reloadScope(item.id); }
      catch (error) { say(error.message); button.disabled = false; return; }
      finally { button.disabled = false; }
      if (!ready(item)) { render(); say('Load this cohort’s datasets first.'); return; }
    }
    if (key === 'delete' && !window.confirm(`Delete cohort "${item.name}"? Source data and existing run files are kept.`)) return;
    onAction(button);
  });
  return {load, render, find, say, clear() { ++revision; items = []; page = 0; if (search) search.value = ''; render(); say(''); document.getElementById('cohortMembersDialog')?.close(); }};
}
