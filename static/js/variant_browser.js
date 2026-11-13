import {modalityIcon, modalityLabel} from './modalities.js';

export function createVariantBrowser({state, escapeHtml: esc, saveIdsAsCohort, onPanels}) {
  const host = document.getElementById('variantBrowser');
  const overview = document.getElementById('assayOverviewView');
  const cards = document.getElementById('variantPanelCards');
  let panels = [], opener = null;
  let scope = '', generation = 0, searchGeneration = 0, detailGeneration = 0;
  let offset = 0, sortBy = 'position', direction = 'asc', timer;
  const current = ticket => ticket === generation && scope === state.currentDatasetScopeId;
  const value = text => esc(String(text || 'Not recorded'));
  function back() {
    ++searchGeneration; ++detailGeneration; clearTimeout(timer);
    host.hidden = true;
    if (overview) overview.hidden = false;
    if (opener?.isConnected) opener.focus();
  }
  async function request(route, params) {
    const selected = state.activePatientScope?.workspace === scope ? state.activePatientScope.selection : null;
    const response = await fetch(`/variants/${route}?${new URLSearchParams({workspace:scope, ...params})}`,
      selected ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({members:selected.members || []})} : {});
    if (!response.ok) {
      let message = 'Unable to load variants.';
      try { message = (await response.json()).detail || message; } catch (_) { /* HTTP error without JSON */ }
      throw new Error(message);
    }
    return response.json();
  }
  async function load(nextScope) {
    if (!host) return;
    scope = nextScope; const ticket = ++generation;
    ++searchGeneration; ++detailGeneration; clearTimeout(timer);
    host.hidden = true;
    if (overview) overview.hidden = false;
    panels = []; opener = null;
    if (cards) { cards.replaceChildren(); cards.hidden = true; }
    if (onPanels) onPanels([]);
    if (!scope) return;
    try {
      const result = await request('panels', {});
      if (!current(ticket)) return;
      panels = result;
      if (onPanels) { onPanels(panels); return; }
      cards.hidden = !panels.length;
      cards.innerHTML = panels.map((p, index) => {
        const technology = p.provenance?.technology;
        const modality = ['dna_sequencing', 'genotyping_array'].includes(technology) ? technology : 'genotyping';
        return `<article class="variant-panel-card"><div class="variant-panel-heading">${modalityIcon(modality)}<div><h4>${esc(modalityLabel(modality))}</h4><span class="section-note">${esc(p.label)}</span></div></div><div class="variant-panel-footer"><span>${Number(p.variants).toLocaleString()} variants · ${Number(p.samples).toLocaleString()} samples</span><button type="button" class="query-chip" data-variant-panel="${index}">Browse variants <span aria-hidden="true">→</span></button></div></article>`;
      }).join('');
      cards.querySelectorAll('[data-variant-panel]').forEach(button => {button.onclick = () => {
        opener = button; void open(panels[Number(button.dataset.variantPanel)].dataset_id);
      };});
    } catch (error) {
      if (current(ticket) && cards) { cards.hidden = false; cards.innerHTML = `<p class="section-note" role="status">${esc(error.message)}</p>`; }
    }
  }
  async function open(dataset, button) {
    if (button) opener = button;
    const ticket = generation;
    if (!current(ticket)) return;
    host.hidden = false;
    if (overview) overview.hidden = true;
    try {
      offset = 0;
      host.innerHTML = `<button type="button" class="ghost variant-back">← Back to assays</button><header class="variant-header"><div class="variant-heading">${modalityIcon('genotyping')}<div><h3>Variant browser</h3><span class="section-note">Explore variants. Select their carriers.</span></div></div><span class="variant-count"></span></header>
        <div class="variant-toolbar"><label>Dataset<select class="variant-dataset" aria-label="Dataset">${panels.map(p => `<option value="${esc(p.dataset_id)}">${esc(p.label)}</option>`).join('')}</select></label>
        <label class="variant-search">Find a variant<input type="search" placeholder="Variant ID, gene or position" aria-label="Search variant ID, gene or position"></label>
        <label>Chromosome<select class="variant-chromosome" aria-label="Chromosome"><option value="">All chromosomes</option></select></label>
        <label>Classification<select class="variant-classification" aria-label="Classification"><option value="">All classifications</option></select></label></div>
        <div class="variant-status section-note" role="status"></div><div class="variant-results"></div>
        <footer class="variant-pagination"><span></span><div><button type="button" class="ghost variant-prev">Previous</button><button type="button" class="ghost variant-next">Next</button></div></footer>
        <section class="variant-detail" hidden aria-label="Selected variant"></section>`;
      host.querySelector('.variant-back').onclick = back;
      host.querySelector('.variant-dataset').value = dataset;
      host.querySelector('.variant-back').focus();
      host.querySelector('.variant-dataset').addEventListener('change', () => {
        host.querySelector('.variant-chromosome').value = '';
        host.querySelector('.variant-classification').value = '';
        offset = 0; void search();
      });
      host.querySelector('input').addEventListener('input', () => {
        ++searchGeneration; ++detailGeneration;
        host.querySelector('.variant-detail').hidden = true;
        clearTimeout(timer); timer = setTimeout(() => {offset = 0; void search();}, 250);
      });
      for (const name of ['chromosome', 'classification']) host.querySelector(`.variant-${name}`).addEventListener('change', () => {offset = 0; void search();});
      host.querySelector('.variant-prev').onclick = () => {offset = Math.max(0, offset - 25); void search();};
      host.querySelector('.variant-next').onclick = () => {offset += 25; void search();};
      await search();
    } catch (error) { if (current(ticket) && !host.hidden) host.querySelector('.variant-status').textContent = error.message; }
  }
  async function search({sorting = false} = {}) {
    const ticket = generation, queryTicket = ++searchGeneration;
    ++detailGeneration;
    const detail = host.querySelector('.variant-detail'); if (!sorting) detail.hidden = true;
    const status = host.querySelector('.variant-status'); if (!sorting) status.textContent = 'Loading variants…';
    const dataset = host.querySelector('.variant-dataset').value;
    const results = host.querySelector('.variant-results');
    const existingTable = sorting ? results.querySelector('table') : null;
    if (!sorting) results.replaceChildren();
    results.setAttribute('aria-busy', 'true');
    host.querySelectorAll('.variant-pagination button').forEach(b => {b.disabled = true;});
    try {
      const result = await request('search', {dataset_id:dataset, q:host.querySelector('input').value,
        chromosome:host.querySelector('.variant-chromosome').value,
        classification:host.querySelector('.variant-classification').value, offset, sort_by:sortBy, direction});
      if (!current(ticket) || queryTicket !== searchGeneration) return;
      for (const [name, items, label] of [['chromosome', result.chromosomes, 'All chromosomes'], ['classification', result.classifications, 'All classifications']]) {
        const select = host.querySelector(`.variant-${name}`), selected = select.value;
        select.innerHTML = `<option value="">${label}</option>` + items.map(item => `<option value="${esc(item)}">${esc(item)}</option>`).join('');
        select.value = selected;
        select.disabled = !items.length;
      }
      host.querySelector('.variant-count').textContent = `${result.total.toLocaleString()} ${result.total === 1 ? 'variant' : 'variants'}`;
      status.textContent = result.total ? '' : 'No variants match these filters.';
      const columns = [['variant_id','Variant'], ['position','Location'], ['gene','Gene'], ['classification','Classification'], ['carriers','Carriers']];
      const rendered = document.createElement('template');
      rendered.innerHTML = result.rows.length ? `<div class="variant-table-wrap"><table><thead><tr>${columns.map(([key,label]) => `<th scope="col" aria-sort="${sortBy === key ? direction === 'asc' ? 'ascending' : 'descending' : 'none'}"><button type="button" data-sort="${key}">${label}${sortBy === key ? direction === 'asc' ? ' ↑' : ' ↓' : ''}</button></th>`).join('')}</tr></thead><tbody>${result.rows.map((r,i) => `<tr><td><button type="button" class="variant-open" data-row="${i}">${esc(r.variant_id)}</button><small>${esc(r.ref)} → ${esc(r.alt)}</small></td><td>${esc(r.chromosome)}:${Number(r.position).toLocaleString()}</td><td>${r.gene ? esc(r.gene) : '<span class="section-note">—</span>'}</td><td>${r.classification ? `<span class="variant-class-label">${esc(r.classification.replaceAll('_', ' '))}</span>` : '<span class="section-note">Not annotated</span>'}</td><td><span class="variant-carrier-count">${r.carriers}</span></td></tr>`).join('')}</tbody></table></div>` : '';
      if (existingTable && result.rows.length) {
        existingTable.querySelector('tbody').replaceChildren(...rendered.content.querySelector('tbody').children);
        existingTable.querySelectorAll('[data-sort]').forEach(button => {
          const updated = rendered.content.querySelector(`[data-sort="${button.dataset.sort}"]`);
          button.textContent = updated.textContent;
          button.closest('th').setAttribute('aria-sort', updated.closest('th').getAttribute('aria-sort'));
        });
      } else results.replaceChildren(rendered.content);
      host.querySelectorAll('[data-sort]').forEach(button => {button.onclick = () => {
        direction = sortBy === button.dataset.sort && direction === 'asc' ? 'desc' : 'asc';
        sortBy = button.dataset.sort; offset = 0; void search({sorting:true});
      };});
      host.querySelectorAll('[data-row]').forEach(button => {button.onclick = () => void showDetail(dataset, result.rows[Number(button.dataset.row)].variant_id);});
      host.querySelector('.variant-pagination span').textContent = result.total ? `${offset + 1}–${offset + result.rows.length} of ${result.total.toLocaleString()}` : '';
      host.querySelector('.variant-prev').disabled = offset === 0;
      host.querySelector('.variant-next').disabled = offset + 25 >= result.total;
    } catch (error) { if (current(ticket) && queryTicket === searchGeneration) status.textContent = error.message; }
    finally { if (current(ticket) && queryTicket === searchGeneration) results.setAttribute('aria-busy', 'false'); }
  }
  async function showDetail(dataset, id) {
    const ticket = generation, selected = ++detailGeneration;
    const detail = host.querySelector('.variant-detail'); detail.hidden = false;
    detail.innerHTML = '<p role="status">Loading variant…</p>';
    const isCurrent = () => current(ticket) && selected === detailGeneration && !detail.hidden;
    try {
      const data = await request('detail', {dataset_id:dataset, variant_id:id});
      if (!isCurrent()) return;
      const a = data.annotation, p = {...data.provenance};
      p.technology = {dna_sequencing:'DNA sequencing', genotyping_array:'Genotyping array', synthetic:'Synthetic'}[p.technology] || p.technology;
      const fields = [['Assembly',a.assembly], ['Gene',a.gene], ['Classification',a.classification],
        ['Annotation source',a.classification_source], ['Source version',a.classification_version],
        ['Review status',a.review_status || a.CLINVAR_CLNREVSTAT], ['Condition',a.condition || a.CLINVAR_CLNDN]];
      detail.innerHTML = `<header><h4>${esc(id)}</h4><button type="button" class="ghost variant-close" aria-label="Close variant details">Close</button></header>
        <div class="variant-call-counts">${Object.entries(data.counts).map(([key,count]) => `<span><strong>${count.toLocaleString()}</strong> ${esc(key)} calls</span>`).join('')}</div>
        <dl class="variant-fields">${fields.map(([key,text]) => `<div><dt>${key}</dt><dd>${value(text)}</dd></div>`).join('')}</dl>
        <details><summary>Provenance and supplied annotations</summary><dl class="variant-fields">${[['Technology',p.technology],['Method / platform',p.method || p.platform],['Original input',p.input_format],['Imported selection',p.selection]].map(([key,text]) => `<div><dt>${key}</dt><dd>${value(text)}</dd></div>`).join('')}</dl><pre>${esc(JSON.stringify(a, null, 2))}</pre></details>
        <p class="section-note">Carriers have a fully called genotype with an alternate allele. Missing and partial calls are excluded. An annotation is not a diagnosis.</p>
        <div class="variant-actions"><button type="button" class="variant-save" ${data.members.length ? '' : 'disabled'}>Save ${data.members.length} ${data.members.length === 1 ? 'carrier' : 'carriers'} as a cohort</button><span role="status"></span></div>`;
      detail.querySelector('.variant-close').onclick = () => {++detailGeneration; detail.hidden = true;};
      detail.querySelector('.variant-save').onclick = async event => {
        const button = event.currentTarget, status = detail.querySelector('.variant-actions span');
        button.disabled = true;
        try {
          const saved = await saveIdsAsCohort({members:data.members, sourceKind:'manual', statusTarget:'none', isCurrent,
            sourcePrompt:`Alternate-allele carriers: ${id}; dataset ${dataset}; fully called genotypes only`});
          if (isCurrent()) status.textContent = saved ? 'Saved. Find the cohort in Cohorts.' : 'Cohort was not saved.';
        } catch (error) { if (isCurrent()) status.textContent = error.message; }
        finally { if (isCurrent()) button.disabled = false; }
      };
      detail.scrollIntoView({block:'nearest', behavior:'auto'});
    } catch (error) { if (isCurrent()) detail.innerHTML = `<p role="alert">${esc(error.message)}</p>`; }
  }
  return {load, open};
}
