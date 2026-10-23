// Organization is separate from chat contents, dataset bindings and autosaves.
export function addChatMenuIcons(root) {
  const paths = {
    pin: 'M9 3h6l-1 6 4 4v2H6v-2l4-4-1-6ZM12 15v6',
    move: 'M3 7V4h6l2 3h10v13H3ZM8 13h8m-3-3 3 3-3 3',
    rename: 'm15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14v6Z',
    delete: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  };
  root.querySelectorAll('.analysis-chat-menu button').forEach(button => {
    const action = Object.keys(button.dataset).find(key => /Pin$|Move$|Rename$|Delete$/.test(key));
    const kind = action?.match(/Pin$|Move$|Rename$|Delete$/)?.[0].toLowerCase();
    if (kind === 'delete') button.classList.add('danger-btn');
    if (!paths[kind] || button.querySelector('.chat-menu-icon')) return;
    const icon = document.createElement('span');
    icon.className = 'chat-menu-icon'; icon.setAttribute('aria-hidden', 'true');
    const slash = kind === 'pin' && button.textContent.trim() === 'Unpin' ? '<path d="m3 3 18 18"/>' : '';
    icon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[kind]}"/>${slash}</svg>`;
    button.prepend(icon);
  });
}

export function createChatFoldersUi({ escapeHtml: esc, renderList }) {
  const list = document.getElementById('analysisSessionList');
  const status = document.getElementById('chatFolderStatus');
  const dialog = document.getElementById('chatMoveDialog');
  const destination = document.getElementById('chatMoveDestination');
  const moveError = document.getElementById('chatMoveError');
  const confirm = document.getElementById('chatMoveConfirm');
  const search = document.getElementById('analysisChatSearch');
  const searchToggle = document.getElementById('chatSearchToggle');
  const folderIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 7V5h7l2 2h9v13H3ZM3 10h18"/></svg>';
  let data = { folders: [], assignments: {}, pinned: [] };
  let epoch = 0;
  let pendingMove = null;
  const collapsed = new Set();
  const key = item => `${item.chatKind || 'analysis'}:${item.id}`;
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
  function actions(kind, id) {
    const pinned = (data.pinned || []).includes(`${kind}:${id}`);
    return `<button type="button" data-chat-pin="${esc(id)}" data-chat-kind="${kind}">${pinned ? 'Unpin' : 'Pin'}</button><button type="button" data-chat-move="${esc(id)}" data-chat-kind="${kind}">Move to folder…</button>`;
  }
  function organize(items, row, term) {
    const pinned = new Set(data.pinned || []);
    const folders = [...data.folders].sort((a, b) => a.name.localeCompare(b.name));
    if (!folders.length && !pinned.size) return items.map(item => row(item, true)).join('') || '<div class="empty">No matching chats.</div>';
    const shortcuts = items.filter(item => pinned.has(key(item))).map(item => row(item, false)).join('');
    const folderShortcuts = folders.filter(folder => pinned.has(`folder:${folder.id}`) && (!term || folder.name.toLocaleLowerCase().includes(term)))
      .map(folder => `<button class="chat-folder-shortcut" type="button" data-folder-open="${esc(folder.id)}">${folderIcon}<span>${esc(folder.name)}</span></button>`).join('');
    let html = shortcuts || folderShortcuts ? `<section aria-label="Pinned"><h4 class="analysis-chat-date">Pinned</h4>${folderShortcuts}${shortcuts}</section>` : '';
    if (folders.length) html += '<h4 class="analysis-chat-date">Folders</h4>';
    for (const folder of folders) {
      const members = items.filter(item => data.assignments[key(item)] === folder.id);
      if (term && !members.length && !folder.name.toLocaleLowerCase().includes(term)) continue;
      const open = Boolean(term) || !collapsed.has(folder.id);
      html += `<section class="chat-folder" data-folder-id="${esc(folder.id)}"><div class="chat-folder-heading"><button type="button" data-folder-toggle="${esc(folder.id)}" aria-expanded="${open}" title="${esc(folder.name)}">${folderIcon}<span>${esc(folder.name)}</span><small>${members.length}</small></button><details class="analysis-chat-menu"><summary aria-label="Actions for folder ${esc(folder.name)}">⋯</summary><div><button type="button" data-chat-pin="${esc(folder.id)}" data-chat-kind="folder">${pinned.has(`folder:${folder.id}`) ? 'Unpin' : 'Pin'}</button><button type="button" data-folder-rename="${esc(folder.id)}">Rename</button><button type="button" data-folder-delete="${esc(folder.id)}">Delete folder</button></div></details></div><div class="chat-folder-body" ${open ? '' : 'hidden'}>${members.map(item => row(item, false)).join('') || '<div class="empty">No chats in this folder.</div>'}</div></section>`;
    }
    const folderIds = new Set(folders.map(folder => folder.id));
    const unfiled = items.filter(item => !folderIds.has(data.assignments[key(item)]));
    html += `<section aria-label="Unfiled"><h4 class="analysis-chat-date">Unfiled</h4>${unfiled.map(item => row(item, false)).join('') || '<div class="empty">No unfiled chats.</div>'}</section>`;
    return html;
  }
  document.getElementById('newChatFolderBtn').addEventListener('click', async () => {
    document.getElementById('newChatChoices').hidden = true;
    document.getElementById('analysisNewSessionBtn').setAttribute('aria-expanded', 'false');
    const name = window.prompt('New folder name');
    if (name === null) return;
    try { await request('', 'POST', { name: name.trim() }); } catch (error) { message(error.message); }
  });
  searchToggle.addEventListener('click', () => {
    search.hidden = !search.hidden;
    searchToggle.setAttribute('aria-expanded', String(!search.hidden));
    if (!search.hidden) search.focus();
    else { search.value = ''; renderList(); }
  });
  search.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    event.stopPropagation(); search.value = ''; search.hidden = true;
    searchToggle.setAttribute('aria-expanded', 'false'); searchToggle.focus(); renderList();
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
        destination.innerHTML = '<option value="">Unfiled</option>' + data.folders.map(folder => `<option value="${esc(folder.id)}">${esc(folder.name)}</option>`).join('');
        destination.value = data.assignments[`${d.chatKind}:${d.chatMove}`] || '';
        moveError.textContent = ''; dialog.showModal(); destination.focus();
      }
    } catch (error) { message(error.message); }
  });
  confirm.addEventListener('click', async () => {
    if (!pendingMove) return;
    confirm.disabled = true;
    try {
      if (await request('/move', 'POST', { ...pendingMove, folder_id: destination.value })) dialog.close();
    } catch (error) { moveError.textContent = error.message; }
    finally { confirm.disabled = false; }
  });
  return { load, clear, actions, organize, pins: () => data.pinned || [] };
}
