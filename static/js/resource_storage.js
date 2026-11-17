import {createStorageSettingsView} from './react/ui.js';

export function createResourceStorage() {
  const panel=document.getElementById('resourceStorageSettings');
  const view=createStorageSettingsView(panel);
  let directory='', status='', busy=false;
  const canBrowse=!!(window.__COHORTOME_DESKTOP__ && window.__TAURI__?.core);
  function render() {
    view.render({directory,status,busy,canBrowse,onChange:value=>{directory=value;render();},onBrowse:browse,onSave:save});
  }
  function fill(data) {
    directory=data.directory;
    status=`${(data.free_bytes / 1024 ** 3).toFixed(1)} GiB available.`;
  }
  async function browse() {
    if(busy || !canBrowse)return;
    busy=true;render();
    try {
      const chosen=await window.__TAURI__.core.invoke('pick_dataset_folder');
      if(chosen){directory=chosen;status='Save to use this folder for new imports.';}
    } catch (_) {status='Could not open the folder picker. You can enter the path directly.';}
    finally {busy=false;render();}
  }
  async function save() {
    if(busy)return;
    busy=true;render();
    try {
      const response=await fetch('/resource-storage',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({directory:directory.trim()})});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string' ? data.detail : 'Enter an existing absolute folder path.');
      fill(data);
      status=`Storage folder saved. New imports use this folder; existing datasets are unchanged. ${(data.free_bytes / 1024 ** 3).toFixed(1)} GiB available.`;
    } catch(error){status=error.message;}
    finally {busy=false;render();}
  }
  render();
  return {async load() {
    try {
      const response=await fetch('/resource-storage');
      panel.hidden=response.status===401 || response.status===403;
      if(panel.hidden){directory='';status='';return;}
      const data=await response.json();
      if(!response.ok)throw new Error(data.detail || 'Could not read storage settings.');
      fill(data);
    } catch(error){status=error.message;}
    finally {render();}
  }};
}
