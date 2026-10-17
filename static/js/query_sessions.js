import { addWorkspaceRestoreAction } from './workspace_restore.js';
// Query persistence uses the same user-owned server storage as Analysis, not browser storage.
export function createQuerySessionsUi({ state, refs, query, escapeHtml, openQuery, closeDrawer, renderList, organizationActions, restoreWorkspace }) {
  const list = document.getElementById('analysisSessionList');
  const search = document.getElementById('analysisChatSearch');
  const status = document.getElementById('queryChatSaveStatus');
  const currentTitle = document.getElementById('queryCurrentChatTitle');
  const persistence = document.getElementById('queryChatPersistence');
  const contextNotice = document.getElementById('queryChatContextNotice');
  const messageBox = document.getElementById('queryChatMessage');
  const messageText = document.getElementById('queryChatMessageText');
  const retry = document.getElementById('queryChatSaveRetry');
  let items = [];
  let current = null;
  let epoch = 0;
  let saves = Promise.resolve();
  let timer;
  let editVersion = 0;
  let saveState = '';
  let conflict = false;
  const dataset = () => String(refs.dataDirEl.dataset.scopeId || '').trim();
  const title = item => item.title || 'New Query chat';
  function message(text = '', retryable = false) {
    status.textContent = text; status.hidden = !text;
    messageText.textContent = text; messageBox.hidden = !text;
    retry.hidden = !retryable;
    retry.textContent = conflict ? 'Reload saved chat' : 'Retry save';
  }
  async function request(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(typeof payload.detail === 'string' ? payload.detail : 'Unable to save Query chat.');
      error.status = response.status;
      throw error;
    }
    return payload;
  }
  function render() {
    currentTitle.textContent = current ? title(current) : 'New Query chat';
    persistence.textContent = saveState;
    const restored = current?.turns?.some(turn => turn.restored);
    const issue = continuationIssue();
    const source = current?.dataset_id || '';
    const record = state.availableDatasets?.find(item => item.dataset_id === source);
    const context = issue || (restored ? 'Saved results. Rerun a query to refresh tables and cohort actions.' : '');
    contextNotice.textContent = context ? `${context}${source ? ` Original workspace: ${record?.name || source}.` : ''}` : '';
    contextNotice.hidden = !context;
    const chatId = current?.id;
    addWorkspaceRestoreAction(contextNotice, { scope: source, currentScope: dataset(),
      restore: restoreWorkspace, reopen: () => open(chatId, true) });
    renderList();
  }
  function renderCard(item) {
    const active = current?.id === item.id && refs.queryTabEl.classList.contains('active');
    return `<div class="analysis-session-card${active ? ' is-active' : ''}">
      <button type="button" class="analysis-session-main" data-query-session-id="${escapeHtml(item.id)}" ${active ? 'aria-current="true"' : ''} aria-label="Query: ${escapeHtml(title(item))}" title="Query: ${escapeHtml(title(item))}"><div class="analysis-session-title"><span class="chat-type-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 4h16v12H9l-5 4Z"/></svg></span>${escapeHtml(title(item))}</div></button>
      <details class="analysis-chat-menu"><summary aria-label="Actions for ${escapeHtml(title(item))}">⋯</summary><div>${organizationActions?.('query', item.id) || ''}<button type="button" data-query-rename="${escapeHtml(item.id)}">Rename</button><button type="button" data-query-delete="${escapeHtml(item.id)}">Delete</button></div></details>
    </div>`;
  }
  async function load() {
    const version = epoch;
    try {
      const data = await request('/query-sessions');
      if (version !== epoch) return;
      items = data.sessions || [];
      message();
      render();
    } catch (error) { if (version === epoch) message(error.message); }
  }
  function detach() {
    clearTimeout(timer);
    current = null;
    editVersion = 0;
    saveState = '';
    conflict = false;
    message();
    render();
  }
  function clear() {
    epoch += 1;
    items = [];
    detach();
    message();
  }
  function snapshot() {
    if (!current) current = { id: crypto.randomUUID(), dataset_id: dataset(), revision: 0 };
    const first = state.queryTurns.find(turn => turn.role === 'user');
    const data = {
      id: current.id, revision: current.revision, dataset_id: current.dataset_id,
      title: current.title_custom ? current.title : String(first?.prompt || refs.questionEl.value || 'New Query chat').slice(0, 100),
      title_custom: Boolean(current.title_custom),
      prompt_draft: refs.questionEl.value, context_mode: state.queryContextMode,
      execution_mode: state.queryExecutionMode, history: state.queryHistory,
      turns: state.queryTurns.filter(turn => !turn.pending),
    };
    return JSON.parse(JSON.stringify(data));
  }
  function save() {
    clearTimeout(timer);
    if (!current && !state.queryTurns.length && !refs.questionEl.value.trim()) return Promise.resolve(true);
    const data = snapshot();
    const target = current;
    const version = epoch;
    const edits = editVersion;
    target.title = data.title;
    saveState = 'Saving…';
    render();
    saves = saves.then(async () => {
      if (version !== epoch) return false;
      try {
        data.revision = target.revision;
        const saved = await request('/query-sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (version !== epoch) return false;
        Object.assign(target, saved);
        items = [saved, ...items.filter(item => item.id !== saved.id)];
        if (current === target) {
          saveState = edits === editVersion ? 'Saved' : 'Unsaved changes';
          conflict = false;
          message();
        }
        render();
        return true;
      } catch (error) {
        if (version === epoch) {
          if (current === target) {
            saveState = 'Not saved';
            conflict = error.status === 409;
          }
          message(`Chat not saved: ${error.message}`, current === target);
          render();
        }
        return false;
      }
    });
    return saves;
  }
  async function newChat() {
    if (state.queryInFlight) { message('Wait for the current query to finish before starting another chat.'); return; }
    if (!await save()) return;
    query.resetQueryWorkspace();
    search.value = ''; render();
    openQuery(); closeDrawer(); refs.questionEl.focus();
  }
  async function open(id, discardDraft = false) {
    if (state.queryInFlight) { message('Wait for the current query to finish before switching chats.'); return; }
    if (discardDraft) { clearTimeout(timer); await saves; }
    if (!discardDraft && !await save()) return;
    const version = epoch;
    try {
      const item = await request(`/query-sessions/${encodeURIComponent(id)}`);
      if (version !== epoch) return;
      query.resetQueryWorkspace();
      current = item;
      saveState = 'Saved';
      state.queryHistory = item.history || [];
      state.queryTurns = item.turns || [];
      state.queryContextMode = item.context_mode;
      state.queryExecutionMode = item.execution_mode;
      refs.questionEl.value = item.prompt_draft || '';
      query.renderQueryContextMode();
      query.renderQueryThread();
      // Results are saved snapshots; never restore a live cohort/result handle implicitly.
      query.markRestoredChat();
      message();
      openQuery(); closeDrawer(); render();
    } catch (error) { if (version === epoch) message(error.message); }
  }
  function continuationIssue() {
    if (!current) return '';
    if (current.dataset_id !== dataset()) return 'This chat belongs to another workspace. Apply its original datasets or start a new Query chat.';
    if (['stale', 'unavailable', 'unknown'].includes(current.workspace_status?.state)) return 'The original workspace has changed. Start a new Query chat.';
    return '';
  }
  search.addEventListener('input', render);
  refs.questionEl.addEventListener('input', () => {
    clearTimeout(timer);
    editVersion += 1;
    saveState = 'Unsaved changes';
    render();
    if (!state.queryInFlight && !continuationIssue()) timer = setTimeout(() => void save(), 600);
  });
  retry.addEventListener('click', () => {
    if (conflict && current) {
      if (window.confirm('Reload the saved chat and discard your unsaved changes in this window?')) void open(current.id, true);
    } else void save();
  });
  list.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.querySessionId) return void open(button.dataset.querySessionId);
    const id = button.dataset.queryRename || button.dataset.queryDelete;
    if (!id) return;
    if (state.queryInFlight) { message('Wait for the current query to finish before changing chats.'); return; }
    try {
      if (!await save()) return;
      if (button.dataset.queryRename) {
        const value = window.prompt('Rename Query chat', title(items.find(item => item.id === id) || {}));
        if (value === null || !value.trim()) return;
        const item = await request(`/query-sessions/${encodeURIComponent(id)}`);
        const renamed = await request('/query-sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...item, title: value.trim().slice(0, 200), title_custom: true }) });
        if (current?.id === id) Object.assign(current, renamed);
      } else {
        if (!window.confirm('Delete this Query chat? Saved cohorts are kept.')) return;
        await request(`/query-sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (current?.id === id) query.resetQueryWorkspace();
      }
      await load();
    } catch (error) { message(error.message); }
  });
  return { load, save, clear, detach, newChat, continuationIssue, renderCard,
    forgetDeletedChats(ids) {
      if (ids.includes(current?.id)) { detach(); query.resetQueryWorkspace(); }
      items = items.filter(item => !ids.includes(item.id));
      render();
    },
    entries: () => items.map(item => ({ ...item, chatKind: 'query', updatedAt: item.updated_at })) };
}
