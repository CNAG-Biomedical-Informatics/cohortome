import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

export function createClearChatsView(dialog) {
  const root=createRoot(dialog);
  return {render(m) {
    flushSync(()=>root.render(<>
      <h3 id="clearChatsTitle">Clear chat history</h3>
      <p>Applies across all folders and workspaces, regardless of search. Folders are kept.</p>
      <p>Messages and inline results are removed. Generated runs and files remain in Run history. Datasets and saved cohorts are kept.</p>
      <label>Chat type <select id="clearChatsKind" value={m.kind} disabled={m.busy} onChange={e=>m.onKind(e.target.value)}>{[['both','All chat types'],['query','Query only'],['analysis','Analysis only'],['pheno','Pheno-Ranker only']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label><input id="clearChatsPinned" type="checkbox" checked={m.includePins} disabled={m.busy} onChange={e=>m.onPins(e.target.checked)}/> Include pinned chats</label>
      <p id="clearChatsCount">{m.count} chats selected for deletion.</p><p role="status" id="clearChatsStatus">{m.status}</p>
      <div className="chat-move-actions"><button type="button" id="clearChatsCancel" className="secondary-btn" disabled={m.busy} onClick={m.onCancel}>Cancel</button><button type="button" id="clearChatsConfirm" className="danger-btn danger-confirm" disabled={m.busy || !m.count} onClick={m.onConfirm}>Delete chats…</button></div>
    </>));
  }};
}

export function createMoveChatView(dialog) {
  const root=createRoot(dialog);
  return {render(m) {
    flushSync(()=>root.render(<form method="dialog" onSubmit={e=>{if(m.busy)e.preventDefault();}}>
      <strong id="chatMoveTitle">Move chat</strong>
      <label htmlFor="chatMoveDestination">Folder</label>
      <select id="chatMoveDestination" value={m.destination} disabled={m.busy} onChange={e=>m.onChange(e.target.value)}><option value="">Unfiled</option>{m.folders.map(folder=><option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>
      <p id="chatMoveError" role="status">{m.error}</p>
      <div className="chat-move-actions"><button value="cancel" disabled={m.busy}>Cancel</button><button id="chatMoveConfirm" type="button" disabled={m.busy} onClick={m.onConfirm}>Move</button></div>
    </form>));
  }};
}
