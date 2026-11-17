import React from 'react';
import {createRoot} from 'react-dom/client';

export function createAboutSettingsView(host) {
  const root=createRoot(host);
  return {render({report,status,ready,onCopy}) {
    root.render(<><summary>About COHORTome</summary>
      <p className="section-note">Research software · Apache-2.0. Detected versions on this web server, not a worker health check. Optional tools may be absent. Versions are cached until restart.</p>
      <p><a href="https://github.com/mrueda/cohortome" target="_blank" rel="noopener">Source code</a> · <a href="https://mrueda.github.io/cohortome/" target="_blank" rel="noopener">Documentation</a> · <a href="https://github.com/mrueda/cohortome/blob/main/LICENSE" target="_blank" rel="noopener">License</a></p>
      <pre id="aboutVersionReport" style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}} aria-live="polite">{report}</pre>
      <button id="aboutCopyReport" type="button" disabled={!ready} onClick={onCopy}>Copy version report</button>
      <span id="aboutCopyStatus" role="status">{status}</span>
    </>);
  }};
}
