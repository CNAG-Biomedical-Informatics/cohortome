import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {AuthPanel} from './auth-panel.jsx';
import {SettingsPanel} from './settings-panel.jsx';

// These stable hosts mount once, before refs and permission controllers bind.
// Child preference/report views own their empty hosts independently.
export function mountApplicationPanels() {
  const auth=document.getElementById('authGate');
  const settings=document.getElementById('userSettingsPanel');
  flushSync(()=>{
    if(auth) createRoot(auth).render(<AuthPanel logoUrl={auth.dataset.logoUrl} logoAlt={auth.dataset.logoAlt}/>);
    if(settings) createRoot(settings).render(<SettingsPanel/>);
  });
}
