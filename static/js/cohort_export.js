import {downloadFile, downloadStatus} from './shared.js';
import {createMolecularExportView} from './react/ui.js';

export async function openMolecularExport(cohortId) {
  if (document.getElementById('cohortExportDialog')) return;
  const dialog = document.createElement('dialog');
  dialog.id = 'cohortExportDialog';
  dialog.className = 'chat-move-dialog cohort-export-dialog';
  dialog.setAttribute('aria-labelledby', 'cohortExportTitle');
  document.body.append(dialog);
  const view = createMolecularExportView(dialog);
  let items = [], selected = [], busy = false, closed = false, scope = '';
  let status = 'Checking available assays…';
  const chosen = () => selected.map(index=>items[index]);
  const bytes = () => chosen().reduce((sum,item)=>sum + item.source_bytes,0);
  const canDownload = () => !busy && selected.length > 0 && selected.length <= 32 && bytes() <= 128*1048576;
  function render() {
    if (closed) return;
    view.render({items,selected,busy,scope,status,downloadDisabled:!canDownload(),
      onClose:()=>{if (!busy) dialog.close();},onDownload:download,
      onSelect:(index,checked)=>{
        if (busy || !items[index]?.available) return;
        selected = checked ? [...new Set([...selected,index])] : selected.filter(i=>i!==index);
        const size = bytes();
        status = `${selected.length} assays selected · ${(size / 1048576).toFixed(1)} MiB source data${size > 128*1048576 ? ' — select fewer assays' : ''}`;
        render();
      }});
  }
  dialog.addEventListener('cancel',event=>{if (busy) event.preventDefault();});
  dialog.addEventListener('close',()=>{closed = true;view.destroy();dialog.remove();});
  render();
  dialog.showModal();
  try {
    const response = await fetch('/saved-cohorts/' + encodeURIComponent(cohortId) + '/export-assays', {cache:'no-store'});
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Cannot load export options.');
    if (closed) return;
    items = payload.assays;
    scope = payload.sample_scope ? 'Sample cohort: only the saved samples will be exported.'
      : 'Patient cohort: all linked samples for the saved patients will be exported.';
    status = items.some(item=>item.available) ? 'Select assays to export.' : 'No supported assays with matching samples are available.';
  } catch (error) {status = error.message;}
  render();
  async function download() {
    if (!canDownload() || closed) return;
    const assays = chosen().map(({key,fingerprint})=>({key,fingerprint}));
    busy = true;
    status = 'Preparing molecular export…';
    render();
    try {
      const result = await downloadFile('/saved-cohorts/' + encodeURIComponent(cohortId) + '/export-molecular', 'cohort-molecular-data.zip', {
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assays})});
      status = downloadStatus(result);
    } catch (error) {status = error.message;}
    finally {busy = false;render();}
  }
}
