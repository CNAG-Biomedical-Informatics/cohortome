import {renderWorkspaceRestore} from './react/ui.js';
// An explicit action: inspecting a saved chat never changes active datasets.
export function addWorkspaceRestoreAction(container, {scope,currentScope,restore,reopen}) {
  if(!container || !scope || scope===currentScope || !restore) return;
  const host=document.createElement('span');
  container.append(host);
  renderWorkspaceRestore(host,{scope,restore,reopen});
}
