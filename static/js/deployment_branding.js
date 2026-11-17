import {createDeploymentLogoView,createDeploymentFormView} from './react/ui.js';

export function createDeploymentBrandingUi() {
  const byId = id => document.getElementById(id);
  const dialog = byId('deploymentAppearanceDialog');
  const formView=createDeploymentFormView(dialog), logoView=createDeploymentLogoView(byId('deploymentBrand'));
  let name='', website='', status='';
  let saved = {name: '', website: '', logo: ''}, logo = '', busy = false, generation = 0;
  function render() {
    formView.render({name,website,logo,status,busy,savedLogo:saved.logo,
      onName:value=>{name=value;render();},onWebsite:value=>{website=value;render();},
      onClose:()=>dialog.close(),onFile:selectFile,onSave:saveBranding,onRemove:removeBranding});
  }
  const clearFile=()=>{byId('deploymentBrandFile').value='';};
  function setBusy(value) {busy=value;render();}
  render();
  async function request(method = 'GET', body) {
    const response = await fetch('/deployment-branding', {method, headers: {'Content-Type': 'application/json'},
      ...(body ? {body: JSON.stringify(body)} : {})});
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to save branding. Check the fields and PNG file.');
    return payload;
  }
  async function load() {
    const ticket = ++generation;
    try {
      const result = await request();
      if (ticket !== generation) return;
      saved = result; logoView.render(saved);
    } catch (_) {
      if (ticket === generation) logoView.render({logo: ''});
    }
  }
  byId('deploymentAppearanceBtn').addEventListener('click', async () => {
    dialog.showModal(); status = 'Loading deployment branding…'; setBusy(true);
    try {
      saved = await request(); logo = saved.logo;
      name = saved.name; website = saved.website; clearFile();
      render(); status = '';
    } catch (error) { status = error.message; }
    finally { setBusy(false); }
  });
  async function selectFile(selected) {
    if (!selected || busy) return;
    setBusy(true); status = '';
    try {
      if (selected.size > 512 * 1024) throw new Error('The logo must be at most 512 KiB.');
      if (selected.type !== 'image/png') throw new Error('Choose a PNG image.');
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('Cannot read this file.')); reader.readAsDataURL(selected);
      });
      const image = new Image(); image.src = data; await image.decode();
      if (image.width > 2048 || image.height > 2048 || image.width * image.height > 2097152) throw new Error('Use a logo up to 2048 pixels per side and 2 megapixels.');
      logo = data; render();
    } catch (error) {
      clearFile(); status = error.message || 'Cannot read this PNG.';
    } finally { setBusy(false); }
  }
  async function saveBranding() {
    if (busy) return;
    if (!logo) { status = 'Choose a PNG logo first.'; render(); return; }
    setBusy(true);
    try {
      saved = await request('PUT', {name: name, website: website, logo});
      ++generation; logoView.render(saved);
      status = 'Branding saved for this deployment. Other users will see it when they refresh.';
    } catch (error) { status = error.message; }
    finally { setBusy(false); }
  }
  async function removeBranding() {
    if (busy || !window.confirm('Remove the secondary logo and name for all users?')) return;
    setBusy(true);
    try {
      saved = await request('DELETE'); ++generation; logo = ''; clearFile(); name = ''; website = '';
      logoView.render(saved); render(); status = 'Deployment branding removed.';
    } catch (error) { status = error.message; }
    finally { setBusy(false); }
  }
  return { syncAuth(auth) {
    const authenticated = !auth.enabled || Boolean(auth.authenticated && auth.user);
    const admin = authenticated && (!auth.enabled || auth.user?.role === 'admin');
    byId('deploymentAppearanceBtn').classList.toggle('is-hidden', !admin);
    if (!admin) dialog.close();
    if (authenticated) void load();
    else { ++generation; saved = {logo: ''}; logoView.render(saved); }
  }};
}
