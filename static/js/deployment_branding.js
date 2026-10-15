export function createDeploymentBrandingUi() {
  const byId = id => document.getElementById(id);
  const dialog = byId('deploymentAppearanceDialog');
  const name = byId('deploymentBrandName'), website = byId('deploymentBrandWebsite');
  const file = byId('deploymentBrandFile'), status = byId('deploymentBrandStatus');
  const save = byId('deploymentBrandSave'), remove = byId('deploymentBrandRemove');
  let saved = {name: '', website: '', logo: ''}, logo = '', busy = false, generation = 0;

  function display(host, value, linked = true) {
    host.replaceChildren();
    host.hidden = !value.logo;
    if (!value.logo) return;
    const content = document.createElement(linked && value.website ? 'a' : 'div');
    if (content.tagName === 'A') {
      content.href = value.website; content.target = '_blank'; content.rel = 'noopener noreferrer';
      content.title = `Visit ${value.name} website (opens a new tab)`;
    }
    const image = document.createElement('img');
    image.src = value.logo; image.alt = `${value.name || 'Deployment'} logo`;
    const label = document.createElement('span'); label.textContent = value.name;
    content.append(image, label); host.append(content);
  }
  function preview() { display(byId('deploymentBrandPreview'), {name: name.value, logo}, false); }
  function setBusy(value) {
    busy = value; save.disabled = value; remove.disabled = value || !saved.logo;
    file.disabled = value; name.disabled = value; website.disabled = value;
  }
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
      saved = result; display(byId('deploymentBrand'), saved);
    } catch (_) {
      if (ticket === generation) display(byId('deploymentBrand'), {logo: ''});
    }
  }
  byId('deploymentAppearanceBtn').addEventListener('click', async () => {
    dialog.showModal(); status.textContent = 'Loading deployment branding…'; setBusy(true);
    try {
      saved = await request(); logo = saved.logo;
      name.value = saved.name; website.value = saved.website; file.value = '';
      preview(); status.textContent = '';
    } catch (error) { status.textContent = error.message; }
    finally { setBusy(false); }
  });
  byId('deploymentAppearanceClose').addEventListener('click', () => dialog.close());
  name.addEventListener('input', preview);
  file.addEventListener('change', async () => {
    const selected = file.files[0]; if (!selected) return;
    setBusy(true); status.textContent = '';
    try {
      if (selected.size > 512 * 1024) throw new Error('The logo must be at most 512 KiB.');
      if (selected.type !== 'image/png') throw new Error('Choose a PNG image.');
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('Cannot read this file.')); reader.readAsDataURL(selected);
      });
      const image = new Image(); image.src = data; await image.decode();
      if (image.width > 2048 || image.height > 2048 || image.width * image.height > 2097152) throw new Error('Use a logo up to 2048 pixels per side and 2 megapixels.');
      logo = data; preview();
    } catch (error) {
      file.value = ''; status.textContent = error.message || 'Cannot read this PNG.';
    } finally { setBusy(false); }
  });
  byId('deploymentAppearanceForm').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    if (!logo) { status.textContent = 'Choose a PNG logo first.'; return; }
    setBusy(true);
    try {
      saved = await request('PUT', {name: name.value, website: website.value, logo});
      ++generation; display(byId('deploymentBrand'), saved);
      status.textContent = 'Branding saved for this deployment. Other users will see it when they refresh.';
    } catch (error) { status.textContent = error.message; }
    finally { setBusy(false); }
  });
  remove.addEventListener('click', async () => {
    if (busy || !window.confirm('Remove the secondary logo and name for all users?')) return;
    setBusy(true);
    try {
      saved = await request('DELETE'); ++generation; logo = ''; file.value = ''; name.value = ''; website.value = '';
      display(byId('deploymentBrand'), saved); preview(); status.textContent = 'Deployment branding removed.';
    } catch (error) { status.textContent = error.message; }
    finally { setBusy(false); }
  });
  return { syncAuth(auth) {
    const authenticated = !auth.enabled || Boolean(auth.authenticated && auth.user);
    const admin = authenticated && (!auth.enabled || auth.user?.role === 'admin');
    byId('deploymentAppearanceBtn').classList.toggle('is-hidden', !admin);
    if (!admin) dialog.close();
    if (authenticated) void load();
    else { ++generation; saved = {logo: ''}; display(byId('deploymentBrand'), saved); }
  }};
}
