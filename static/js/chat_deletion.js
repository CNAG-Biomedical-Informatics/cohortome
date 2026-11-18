import {createClearChatsView} from './react/ui.js';
// Bulk actions use the same owner-checked endpoints as individual deletion.
export function createChatDeletionUi({ state, escapeHtml: esc, render, prepare, forget, entries, pins }) {
  let selecting = false, busy = false, epoch = 0;
  const selected = new Map();
  const list = document.getElementById('analysisSessionList');
  const notice = document.getElementById('chatFolderStatus');
  const dialog = document.createElement('dialog');
  dialog.className = 'chat-move-dialog'; dialog.id = 'clearChatsDialog';
  dialog.setAttribute('aria-labelledby', 'clearChatsTitle');
  document.body.append(dialog);
  const view=createClearChatsView(dialog);
  let kind='both', includePins=false, status='';
  const key = item => `${item.chatKind || 'analysis'}:${item.id}`;
  function message(text) { notice.textContent = text; notice.hidden = !text; status=text; updateCount(); }
  function targets() {
    const pinned = new Set(pins());
    return entries().filter(item => (kind === 'both' || (item.chatKind || 'analysis') === kind)
      && (includePins || !pinned.has(key(item))));
  }
  function updateCount() {
    view.render({kind,includePins,busy,status,count:targets().length,
      onKind:value=>{kind=value;updateCount();},onPins:value=>{includePins=value;updateCount();},
      onCancel:()=>{if(!busy)dialog.close();},onConfirm:()=>void remove(targets())});
  }
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  async function remove(items) {
    if (busy) return;
    if (state.queryInFlight || state.analysisInFlight || state.loadInFlight) {
      message('Wait for the current operation to finish before deleting chats.'); return;
    }
    if (!items.length) return;
    if (!window.confirm(`Delete ${items.length} chats? This cannot be undone. Chat messages and inline results will be removed. Datasets, saved cohorts, generated runs and their files are kept. Background jobs are not cancelled.`)) return;
    busy = true; updateCount(); render();
    const version = epoch;
    const deleted = [];
    try {
      await prepare();
      for (const item of items) {
        if (version !== epoch) return;
        const type = item.chatKind || 'analysis';
        const suffix = type === 'analysis' ? '?keep_generated_jobs=true' : '';
        const response = await fetch(`/${type}-sessions/${encodeURIComponent(item.id)}${suffix}`, { method: 'DELETE' });
        if (version !== epoch) return;
        if (!response.ok && response.status !== 404) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to delete chat.');
        }
        deleted.push(item);
        selected.delete(key(item));
        // Remove local state immediately so autosave cannot recreate a deleted chat.
        forget(item);
      }
      selecting = false; selected.clear();
      message(`Deleted ${deleted.length} chats. Generated runs and saved cohorts were kept.`);
      if (dialog.open) dialog.close();
    } catch (error) {
      message(`Deleted ${deleted.length} of ${items.length} chats. ${error.message} Remaining chats were kept.`);
    } finally { busy = false; updateCount(); render(); }
  }
  document.getElementById('selectChatsBtn').addEventListener('click', () => {
    selecting = true; selected.clear();
    render();
  });
  function toggle(chatKey, checked) {
    if (busy) return;
    const item = entries().find(item => key(item) === chatKey);
    if (!item) return;
    if (checked) selected.set(key(item), item); else selected.delete(key(item));
    render();
  }
  list.addEventListener('click', event => {
    if (event.target.closest('[data-delete-selected]')) void remove([...selected.values()]);
    if (event.target.closest('[data-cancel-selection]') && !busy) { selecting = false; selected.clear(); render(); }
  });
  return {
    clear() { epoch++; selecting = false; selected.clear(); dialog.close(); },
    open() { status=''; includePins=false; updateCount(); dialog.showModal(); },
    snapshot() { return {selecting, busy, selected:[...selected.keys()], toggle}; },
  };
}
