import {openDatasetConfirmation} from './react/ui.js';
// Selection is UI state only; every operation still uses the existing
// permission-checked per-dataset endpoint.
export function createDatasetBulkAi({reload, canManage, onChange}) {
  const selected = new Set();
  let notice = '';
  function snapshot(datasets) {
    for (const id of selected) if (!datasets.some(d => d.dataset_id === id)) selected.delete(id);
    const matching = () => datasets.filter(d => selected.has(d.dataset_id));
    return {
      selected: new Set(selected), total: datasets.length, notice,
      preparable: matching().filter(d => !d.query_store_status?.ready
        && String(d.query_store_status?.status || 'not_built') !== 'building').length,
      toggle(id, checked) { if (checked) selected.add(id); else selected.delete(id); onChange(); },
      selectAll(checked) { selected.clear(); if (checked) datasets.forEach(d => selected.add(d.dataset_id)); onChange(); },
      review() { review(matching()); },
      prepare() { reviewPreparation(matching()); },
    };
  }
  function reviewPreparation(datasets) {
    if (!canManage()) return;
    const candidates = datasets.filter(d => !d.query_store_status?.ready
      && String(d.query_store_status?.status || 'not_built') !== 'building');
    if (!candidates.length) return;
    openDatasetConfirmation({kind:'rebuild', datasets:candidates, skipped:datasets.length-candidates.length,
      onApply: async (_, report) => {
        if (!canManage()) throw new Error('Dataset administration is only available to administrators.');
        const failures = [];
        let prepared = 0;
        for (const [index,dataset] of candidates.entries()) {
          report(`Rebuilding ${index+1} of ${candidates.length}: ${dataset.name || dataset.dataset_id}…`);
          try {
            const response = await fetch(`/datasets/${encodeURIComponent(dataset.dataset_id)}/prepare-store`, {method:'POST'});
            const payload = await response.json().catch(()=>({}));
            if (!response.ok) throw new Error(payload.detail || 'Build failed.');
            prepared++;
          } catch(error) {failures.push({dataset,message:error.message || 'Build failed.'});}
        }
        selected.clear();
        failures.forEach(({dataset})=>selected.add(dataset.dataset_id));
        notice = `Rebuilt ${prepared} ${prepared===1 ? 'store' : 'stores'}${failures.length ? `; ${failures.length} failed.` : '.'}`;
        onChange();
        await reload({preservePendingSelection:true});
        return {close:!failures.length, complete:true,
          status:failures.map(({dataset,message})=>`${dataset.name || dataset.dataset_id}: ${message}`).join(' ')};
      }});
  }
  function review(datasets) {
    if (!canManage() || !datasets.length) return;
    openDatasetConfirmation({kind:'permissions',datasets,onApply:async ({permission})=>{
      if (!canManage()) throw new Error('Dataset administration is only available to administrators.');
      const response=await fetch('/datasets/bulk-ai-access',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dataset_ids:datasets.map(d=>d.dataset_id),ai_provider_access:permission})});
      const payload=await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to update permissions.');
      notice=`AI permissions updated for ${datasets.length} datasets.`;
      selected.clear(); onChange();
      await reload({preservePendingSelection:true});
      return {close:true};
    }});
  }
  return {snapshot};
}
