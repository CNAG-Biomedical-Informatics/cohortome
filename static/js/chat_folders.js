
import {createMoveChatView} from './react/ui.js';

export function createChatFoldersUi({ escapeHtml: esc, renderList }) {
  const list = document.getElementById('analysisSessionList');
  const status = document.getElementById('chatFolderStatus');
  const dialog = document.getElementById('chatMoveDialog');
  const moveView=createMoveChatView(dialog);
  let destination='', moveError='', moving=false;
  let data = { folders: [], assignments: {}, pinned: [] };
  let epoch = 0;
  let pendingMove = null;
  const collapsed = new Set();
  const key = item => `${item.chatKind || 'analysis'}:${item.id}`;
  function renderMove() {
    moveView.render({folders:data.folders || [],destination,error:moveError,busy:moving,
      onChange:value=>{destination=value;renderMove();},onConfirm:confirmMove});
  }
  dialog.addEventListener('cancel',event=>{if(moving)event.preventDefault();});
  function message(text = '') { status.textContent = text; status.hidden = !text; }
  async function request(path = '', method = 'GET', body) {
    const version = epoch;
    const response = await fetch(`/chat-folders${path}`, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
    const value = await response.json();
    if (version !== epoch) return false;
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Unable to update folders.');
    data = value; message(); renderList(); return true;
  }
  async function load() { try { await request(); } catch (error) { message(error.message); } }
  function clear() { epoch++; data = { folders: [], assignments: {}, pinned: [] }; collapsed.clear(); dialog.close(); pendingMove = null; message(); renderList(); }
  function snapshot() {
    return {folders:data.folders || [],assignments:data.assignments || {},pinned:data.pinned || [],collapsed:[...collapsed]};
  }
  document.getElementById('newChatFolderBtn').addEventListener('click', async () => {
    const name = window.prompt('New folder name');
    if (name === null) return;
    try { await request('', 'POST', { name: name.trim() }); } catch (error) { message(error.message); }
  });
  list.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button) return;
    const d = button.dataset;
    try {
      if (d.folderToggle || d.folderOpen) {
        const id = d.folderToggle || d.folderOpen;
        if (d.folderOpen || collapsed.has(id)) collapsed.delete(id); else collapsed.add(id);
        renderList();
        const target = list.querySelector(`[data-folder-toggle="${CSS.escape(id)}"]`);
        target?.focus(); if (d.folderOpen) target?.scrollIntoView({ block: 'nearest' });
      } else if (d.folderRename) {
        const folder = data.folders.find(item => item.id === d.folderRename);
        const name = window.prompt('Rename folder', folder.name);
        if (name !== null) await request(`/${encodeURIComponent(folder.id)}`, 'PATCH', { name: name.trim() });
      } else if (d.folderDelete) {
        if (window.confirm('Delete this folder? Its chats will move to Unfiled. No chats, cohorts or runs will be deleted.')) await request(`/${encodeURIComponent(d.folderDelete)}`, 'DELETE');
      } else if (d.chatPin) {
        await request('/pin', 'POST', { kind: d.chatKind, chat_id: d.chatPin, pinned: !(data.pinned || []).includes(`${d.chatKind}:${d.chatPin}`) });
      } else if (d.chatMove) {
        // Refresh destinations in case another window renamed or deleted a folder.
        if (!await request()) return;
        pendingMove = { kind: d.chatKind, chat_id: d.chatMove };
        destination = data.assignments[`${d.chatKind}:${d.chatMove}`] || '';
        moveError=''; renderMove(); dialog.showModal(); dialog.querySelector('select').focus();
      }
    } catch (error) { message(error.message); }
  });
  async function confirmMove() {
    if (!pendingMove || moving) return;
    moving=true; renderMove();
    try {
      if (await request('/move', 'POST', { ...pendingMove, folder_id: destination })) dialog.close();
    } catch (error) { moveError=error.message; }
    finally { moving=false; renderMove(); }
  }
  return { load, clear, snapshot, pins: () => data.pinned || [] };
}
