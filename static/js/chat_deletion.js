// Bulk actions use the same owner-checked endpoints as individual deletion.
export function createChatDeletionUi({ state, escapeHtml: esc, render, prepare, forget, entries, pins }) {
  let selecting = false, busy = false, epoch = 0;
  const selected = new Map();
  const list = document.getElementById('analysisSessionList');
  const notice = document.getElementById('chatFolderStatus');
  const dialog = document.createElement('dialog');
  dialog.className = 'chat-move-dialog'; dialog.id = 'clearChatsDialog';
  dialog.setAttribute('aria-labelledby', 'clearChatsTitle');
  dialog.innerHTML = `<h3 id="clearChatsTitle">Clear chat history</h3>
    <p>Applies across all folders and workspaces, regardless of search. Folders are kept.</p>
    <p>Messages and inline results are removed. Generated runs and files remain in Run history. Datasets and saved cohorts are kept.</p>
    <label>Chat type <select id="clearChatsKind"><option value="both">Query and Analysis</option><option value="query">Query only</option><option value="analysis">Analysis only</option></select></label>
    <label><input id="clearChatsPinned" type="checkbox"> Include pinned chats</label>
    <p id="clearChatsCount"></p><p role="status" id="clearChatsStatus"></p>
    <div class="chat-move-actions"><button type="button" id="clearChatsCancel">Cancel</button><button type="button" id="clearChatsConfirm" class="danger-btn">Delete chats…</button></div>`;
  document.body.append(dialog);
  const kind = dialog.querySelector('select'), includePins = dialog.querySelector('input');
  const confirm = dialog.querySelector('#clearChatsConfirm');
  const status = dialog.querySelector('[role=status]');
  const key = item => `${item.chatKind || 'analysis'}:${item.id}`;
  function message(text) { notice.textContent = text; notice.hidden = !text; status.textContent = text; }
  function targets() {
    const pinned = new Set(pins());
    return entries().filter(item => (kind.value === 'both' || (item.chatKind || 'analysis') === kind.value)
      && (includePins.checked || !pinned.has(key(item))));
  }
  function updateCount() {
    dialog.querySelector('#clearChatsCount').textContent = `${targets().length} chats selected for deletion.`;
    confirm.disabled = busy || !targets().length;
  }
  kind.addEventListener('change', updateCount); includePins.addEventListener('change', updateCount);
  dialog.querySelector('#clearChatsCancel').addEventListener('click', () => { if (!busy) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  async function remove(items) {
    if (busy) return;
    if (state.queryInFlight || state.analysisInFlight || state.loadInFlight) {
      message('Wait for the current operation to finish before deleting chats.'); return;
    }
    if (!items.length) return;
    const queries = items.filter(item => item.chatKind === 'query').length;
    if (!window.confirm(`Delete ${items.length} chats (${queries} Query, ${items.length - queries} Analysis)? This cannot be undone. Chat messages and inline results will be removed. Datasets, saved cohorts, generated runs and their files are kept. Background jobs are not cancelled.`)) return;
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
    } catch (error) {
      message(`Deleted ${deleted.length} of ${items.length} chats. ${error.message} Remaining chats were kept.`);
    } finally { busy = false; updateCount(); render(); }
  }
  confirm.addEventListener('click', () => void remove(targets()));
  document.getElementById('selectChatsBtn').addEventListener('click', () => {
    selecting = true; selected.clear();
    document.getElementById('newChatChoices').hidden = true;
    document.getElementById('analysisNewSessionBtn').setAttribute('aria-expanded', 'false');
    render();
  });
  list.addEventListener('change', event => {
    const input = event.target.closest('[data-select-chat]');
    if (!input || busy) return;
    const item = entries().find(item => key(item) === input.dataset.selectChat);
    if (!item) return;
    if (input.checked) selected.set(key(item), item); else selected.delete(key(item));
    render();
  });
  list.addEventListener('click', event => {
    if (event.target.closest('[data-delete-selected]')) void remove([...selected.values()]);
    if (event.target.closest('[data-cancel-selection]') && !busy) { selecting = false; selected.clear(); render(); }
  });
  return {
    clear() { epoch++; selecting = false; selected.clear(); dialog.close(); },
    open() { status.textContent = ''; includePins.checked = false; updateCount(); dialog.showModal(); },
    row(item, html) {
      if (!selecting) return html;
      const checkbox = `<input class="chat-delete-check" type="checkbox" data-select-chat="${esc(key(item))}" aria-label="Select ${esc(item.title || 'Untitled chat')}" ${selected.has(key(item)) ? 'checked' : ''} ${busy ? 'disabled' : ''}>`;
      return html.replace(/(<div class="analysis-session-card[^"]*">)/, match => match + checkbox);
    },
    toolbar() {
      return selecting ? `<div class="chat-selection-bar"><span>${selected.size} selected (including hidden selections)</span><button type="button" data-delete-selected ${busy || !selected.size ? 'disabled' : ''}>Delete selected…</button><button type="button" data-cancel-selection ${busy ? 'disabled' : ''}>Cancel</button></div>` : '';
    },
  };
}
