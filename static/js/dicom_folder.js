import {createDicomFolderView} from './react/ui.js';

export function openDicomFolderDialog(datasets) {
  const dialog = document.createElement('dialog');
  dialog.className = 'dicom-folder-dialog';
  document.body.append(dialog);
  const view = createDicomFolderView(dialog);
  let busy = false, done = false, closed = false, message = '';
  function render() {
    if (closed) return;
    view.render({datasets,busy,done,message,desktop:!!window.__COHORTOME_DESKTOP__,
      canBrowse:!!window.__TAURI__?.core,
      onClose:()=>{if (!busy) dialog.close();},
      onBrowse:async setDirectory=>{
        try {
          const directory = await window.__TAURI__.core.invoke('pick_dataset_folder');
          if (!closed && directory) setDirectory(directory);
        } catch (_) {
          message = 'Could not open the folder picker. Enter the path instead.';
          render();
        }
      },onSubmit:link});
  }
  async function link(dataset,directory) {
    if (busy || done || closed) return;
    busy = true;
    message = 'Reading DICOM headers and checking patient links…';
    render();
    try {
      const response = await fetch('/local-viewer/datasets/' + encodeURIComponent(dataset) + '/folder', {
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({directory})});
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not link this folder.');
      message = `Linked ${result.studies} studies, ${result.instances} instances and ${result.patients} patients. Files remain in their original folder.`;
      done = true;
    } catch (error) {message = error.message;}
    finally {busy = false;render();}
  }
  dialog.addEventListener('cancel',event=>{if (busy) event.preventDefault();});
  dialog.addEventListener('close',()=>{closed = true;view.destroy();dialog.remove();});
  render();
  dialog.showModal();
}
