import {createVariantView, createVariantPanelsView} from './react/ui.js';

export function createVariantBrowser({state, saveIdsAsCohort, onPanels}) {
  const host = document.getElementById('variantBrowser');
  const overview = document.getElementById('assayOverviewView');
  const cards = document.getElementById('variantPanelCards');
  let panels = [], opener = null, scope = '', generation = 0, searchGeneration = 0, detailGeneration = 0, timer;
  let openRevision = 0, model = {};
  const current = ticket => ticket === generation && scope === state.currentDatasetScopeId;
  const update = patch => {model = {...model, ...patch}; view.render(model);};
  const view = createVariantView(host, {
    back, dataset:dataset => {update({dataset, chromosome:'', classification:'', offset:0}); void search();},
    query:q => {++searchGeneration; ++detailGeneration; update({q, detail:null}); clearTimeout(timer); timer = setTimeout(() => {update({offset:0}); void search();},250);},
    filter:(key,value) => {update({[key]:value, offset:0}); void search();},
    page:delta => {update({offset:Math.max(0, model.offset + delta)}); void search();},
    sort:key => {update({direction:model.sortBy === key && model.direction === 'asc' ? 'desc' : 'asc', sortBy:key, offset:0}); void search(true);},
    detail:showDetail, closeDetail:() => {++detailGeneration; update({detail:null});}, save,
  });
  const panelView = createVariantPanelsView(cards, open);
  function back() {
    ++searchGeneration; ++detailGeneration; clearTimeout(timer);
    host.hidden = true; view.reset();
    if (overview) overview.hidden = false;
    if (opener?.isConnected) opener.focus();
  }
  async function request(route, params) {
    const selected = state.activePatientScope?.workspace === scope ? state.activePatientScope.selection : null;
    const response = await fetch('/variants/' + route + '?' + new URLSearchParams({workspace:scope, ...params}),
      selected ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({members:selected.members || []})} : {});
    if (!response.ok) {
      let message = 'Unable to load variants.';
      try {message = (await response.json()).detail || message;} catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }
  async function load(nextScope) {
    if (!host) return;
    scope = nextScope; const ticket = ++generation;
    ++searchGeneration; ++detailGeneration; clearTimeout(timer);
    host.hidden = true; view.reset();
    if (overview) overview.hidden = false;
    panels = []; opener = null;
    if (cards) {panelView.render([]); cards.hidden = true;}
    onPanels?.([]);
    if (!scope) return;
    try {
      const result = await request('panels', {});
      if (!current(ticket)) return;
      panels = result;
      if (onPanels) {onPanels(panels); return;}
      if (cards) {cards.hidden = !panels.length; panelView.render(panels);}
    } catch (error) {if (current(ticket) && cards) {cards.hidden = false; panelView.render([],error.message);}}
  }
  async function open(dataset, button) {
    if (button) opener = button;
    if (!current(generation)) return;
    clearTimeout(timer); ++detailGeneration;
    host.hidden = false;
    if (overview) overview.hidden = true;
    update({panels, dataset, q:'', chromosome:'', classification:'', chromosomes:[], classifications:[],
      offset:0, sortBy:model.sortBy || 'position', direction:model.direction || 'asc', result:null,
      detail:null, status:'', busy:false, openRevision:++openRevision});
    await search();
  }
  async function search(sorting = false) {
    clearTimeout(timer);
    const ticket = generation, queryTicket = ++searchGeneration;
    ++detailGeneration;
    update({busy:true, ...(sorting ? {} : {detail:null, result:null, status:'Loading variants…'})});
    const {dataset, q, chromosome, classification, offset, sortBy, direction} = model;
    try {
      const result = await request('search', {dataset_id:dataset, q, chromosome, classification, offset, sort_by:sortBy, direction});
      if (!current(ticket) || queryTicket !== searchGeneration || host.hidden) return;
      update({result, chromosomes:result.chromosomes, classifications:result.classifications,
        status:result.total ? '' : 'No variants match these filters.'});
    } catch (error) {if (current(ticket) && queryTicket === searchGeneration && !host.hidden) update({status:error.message});}
    finally {if (current(ticket) && queryTicket === searchGeneration && !host.hidden) update({busy:false});}
  }
  async function showDetail(dataset, id) {
    const ticket = generation, selected = ++detailGeneration;
    update({detail:{loading:true, dataset,id}});
    try {
      const data = await request('detail', {dataset_id:dataset, variant_id:id});
      if (current(ticket) && selected === detailGeneration && !host.hidden) update({detail:{dataset,id,data}});
    } catch (error) {if (current(ticket) && selected === detailGeneration && !host.hidden) update({detail:{error:error.message}});}
  }
  async function save() {
    const ticket = generation, selected = detailGeneration, detail = model.detail;
    if (!detail?.data?.members?.length || detail.saving) return;
    const isCurrent = () => current(ticket) && selected === detailGeneration && !host.hidden && model.detail?.data === detail.data;
    update({detail:{...detail, saving:true}});
    try {
      const saved = await saveIdsAsCohort({members:detail.data.members, sourceKind:'manual', statusTarget:'none', isCurrent,
        sourcePrompt:'Alternate-allele carriers: ' + detail.id + '; dataset ' + detail.dataset + '; fully called genotypes only'});
      if (isCurrent()) update({detail:{...model.detail, status:saved ? 'Saved. Find the cohort in Cohorts.' : 'Cohort was not saved.'}});
    } catch (error) {if (isCurrent()) update({detail:{...model.detail, status:error.message}});}
    finally {if (isCurrent()) update({detail:{...model.detail, saving:false}});}
  }
  return {load, open};
}
