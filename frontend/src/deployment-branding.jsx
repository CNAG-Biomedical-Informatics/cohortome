import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

function Logo({value,linked=true}) {
  if(!value.logo)return null;
  const content=<><img src={value.logo} alt={`${value.name || 'Deployment'} logo`}/><span>{value.name}</span></>;
  return linked && value.website ? <a href={value.website} target="_blank" rel="noopener noreferrer" title={`Visit ${value.name} website (opens a new tab)`}>{content}</a> : <div title={value.name || 'Deployment logo'}>{content}</div>;
}
export function createDeploymentLogoView(host) {
  const root=createRoot(host);
  return {render(value){host.hidden=!value.logo;root.render(<Logo value={value}/>);}};
}
export function createDeploymentFormView(dialog) {
  const root=createRoot(dialog);
  return {render(m) {
    flushSync(()=>root.render(<form id="deploymentAppearanceForm" onSubmit={e=>{e.preventDefault();m.onSave();}}>
      <div className="deployment-appearance-heading"><h2 id="deploymentAppearanceTitle">Deployment appearance</h2><button id="deploymentAppearanceClose" type="button" className="secondary-btn" aria-label="Close deployment appearance" onClick={m.onClose}>Close</button></div>
      <p>Add a programme or institution logo for all users of this installation. The COHORTome logo stays unchanged.</p>
      <label htmlFor="deploymentBrandName">Name</label><input id="deploymentBrandName" required maxLength={100} placeholder="e.g. 3TR" value={m.name} disabled={m.busy} onChange={e=>m.onName(e.target.value)}/>
      <label htmlFor="deploymentBrandWebsite">Website (optional)</label><input id="deploymentBrandWebsite" type="url" maxLength={2048} placeholder="https://example.org" value={m.website} disabled={m.busy} onChange={e=>m.onWebsite(e.target.value)}/>
      <label htmlFor="deploymentBrandFile">Logo (PNG)</label><input id="deploymentBrandFile" type="file" accept="image/png,.png" aria-describedby="deploymentBrandFileHelp" disabled={m.busy} onChange={e=>m.onFile(e.target.files[0])}/>
      <p id="deploymentBrandFileHelp" className="section-note">Up to 512 KiB, 2048 pixels per side and 2 megapixels. Use a still PNG. Leave unchanged to keep the saved logo.</p>
      <p className="section-note">Sidebar preview</p><div id="deploymentBrandPreview" className="deployment-brand" hidden={!m.logo}><Logo value={m} linked={false}/></div>
      <p id="deploymentBrandStatus" role="status" aria-live="polite">{m.status}</p>
      <div className="deployment-appearance-actions"><button type="submit" id="deploymentBrandSave" disabled={m.busy}>Save branding</button><button type="button" id="deploymentBrandRemove" className="secondary-btn" disabled={m.busy || !m.savedLogo} onClick={m.onRemove}>Remove branding</button></div>
    </form>));
  }};
}
