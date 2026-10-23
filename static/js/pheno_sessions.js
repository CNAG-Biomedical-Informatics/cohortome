import { addWorkspaceRestoreAction } from './workspace_restore.js';
// Persist structured runs, not HTML. Existing renderers restore plots and tables.
export function createPhenoSessionsUi({state, refs, pheno, escapeHtml: esc, renderList, openTab, actions, restoreWorkspace}) {
  let items = [], current = null, chain = Promise.resolve(), epoch = 0, restoring = false, timer, runSetup;
  const panel = document.getElementById('phenoChatHistory');
  const resultWorkspace = document.getElementById('phenoResultWorkspace');
  const resultHome = resultWorkspace.parentElement;
  let activeResult = -1;
  let explanationProgress = null;
  let runProgress = null;
  const status = document.getElementById('phenoChatStatus');
  function recovery(failed = false, conflict = false) {
    document.getElementById('phenoChatSave').classList.toggle('is-hidden', !failed);
    document.getElementById('phenoChatReload').classList.toggle('is-hidden', !conflict);
  }
  const scope = () => String(refs.dataDirEl.dataset.scopeId || '');
  const fields = {prompt:'phenoPrompt', action:'phenoAction', mode:'phenoMode', patient_id:'phenoPatientId',
    selected_patient_ids:'phenoSelectedPatientIds', similarity_metric_cohort:'phenoSimilarityMetric',
    sort_by:'phenoSortBy', max_out:'phenoMaxOut', graph_min_weight:'phenoGraphMinWeight', graph_max_weight:'phenoGraphMaxWeight'};
  const checks = {align:'phenoAlign', render_heatmap:'phenoRenderHeatmap', render_mds:'phenoRenderMds', render_graph:'phenoRenderGraph'};
  function setup() {
    const data = Object.fromEntries(Object.entries(fields).map(([key,id]) => [key, document.getElementById(id)?.value || '']));
    data.patient_id = pheno.getPatientTargetId();
    Object.entries(checks).forEach(([key,id]) => {data[key] = Boolean(document.getElementById(id)?.checked);});
    for (const [key,id] of [['include_terms','phenoIncludeTerms'], ['exclude_terms','phenoExcludeTerms']])
      data[key] = (document.getElementById(id)?.value || '').split(',').map(s => s.trim()).filter(Boolean);
    data.selected_saved_cohort_ids = [...state.phenoSelectedSavedCohortIds];
    data.query_selection = state.phenoQuerySelection || null;
    return data;
  }
  async function request(url, options) {
    const response = await fetch(url, options), data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Unable to save Pheno-Ranker chat.');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function issue() {
    if (!current) return '';
    if (current.dataset_id !== scope()) return 'Apply this chat’s original workspace or start a new Pheno-Ranker chat.';
    if (['stale','unknown','unavailable'].includes(current.workspace_status?.state)) return 'Workspace data changed. Start a new Pheno-Ranker chat.';
    return '';
  }
  function render() {
    document.getElementById('phenoChatTitle').textContent = current?.title || 'New chat';
    // Move, do not clone, the live renderer: plots and their event handlers stay intact.
    resultHome.append(resultWorkspace);
    panel.innerHTML = (current?.turns || []).map((turn,index) => {
      const explanation = turn.kind === 'explanation';
      const prompt = explanation ? (turn.payload.llm_reply ? 'Explain these results with LLM' : 'Explain these results')
        : (turn.setup?.prompt || turn.label || 'Run Pheno-Ranker');
      const content = turn.kind === 'error' ? `<p role="alert">${esc(turn.payload.message)}</p><details><summary>Details</summary><pre>${esc(turn.payload.detail || '')}</pre></details>`
        : explanation ? pheno.explanationMarkup(turn.payload)
        : `<p>${esc(turn.kind === 'queued' ? 'Background job submitted.' : 'Completed run')}</p>
          <button type="button" class="query-chip" data-pheno-turn="${index}">${turn.kind === 'queued' ? 'Check result' : 'Show results'}</button>
          <div data-pheno-result-host="${index}"></div>`;
      return `<article class="analysis-turn analysis-turn-user"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${esc(prompt)}</p></div></article>
        <article class="analysis-turn analysis-turn-assistant" data-pheno-reply="${index}"><div class="analysis-turn-label">${explanation ? 'Explanation' : 'Pheno-Ranker'}</div>${content}</article>`;
    }).join('');
    if (runProgress) {
      panel.insertAdjacentHTML('beforeend', `<article class="analysis-turn analysis-turn-user"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${esc(runProgress.prompt || 'Run Pheno-Ranker')}</p></div></article>
        <article class="analysis-turn analysis-turn-pending pheno-run-progress" role="status" aria-live="polite" aria-busy="true"><div class="analysis-turn-label">Pheno-Ranker</div><div class="analysis-turn-body"><div class="analysis-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></div><span>Running Pheno-Ranker…</span></div></article>`);
    }
    if (explanationProgress) {
      panel.insertAdjacentHTML('beforeend', `<article class="analysis-turn analysis-turn-user"><div class="analysis-turn-label">You</div><div class="analysis-turn-body"><p>${esc(explanationProgress.request)}</p></div></article>
        <article class="analysis-turn ${explanationProgress.error ? 'analysis-turn-error' : 'analysis-turn-pending'} pheno-explanation-progress" role="status" aria-live="polite" aria-busy="${!explanationProgress.error}"><div class="analysis-turn-label">Pheno-Ranker</div><div class="analysis-turn-body">${explanationProgress.error ? '' : '<div class="analysis-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></div>'}${esc(explanationProgress.message)}</div></article>`);
    }
    const host = panel.querySelector(`[data-pheno-result-host="${activeResult}"]`);
    if (host) {
      host.append(resultWorkspace);
      panel.querySelector(`[data-pheno-turn="${activeResult}"]`).hidden = true;
    }
    renderList();
  }
  function ensure() {
    if (!current) current = {id:crypto.randomUUID(), revision:0, dataset_id:scope(), title:setup().prompt.slice(0,100) || 'New chat', turns:[]};
    return current;
  }
  function save() {
    clearTimeout(timer);
    if (restoring || (!current && !setup().prompt.trim())) return Promise.resolve(true);
    if (!scope()) {status.textContent = 'Load a workspace before saving a chat.'; return Promise.resolve(false);}
    if (issue()) {status.textContent = issue(); return Promise.resolve(false);}
    const target = ensure(), version = epoch;
    target.setup = setup();
    if (!target.title_custom) target.title = (target.turns[0]?.setup?.prompt || target.setup.prompt || 'New chat').slice(0,100);
    const data = JSON.parse(JSON.stringify(target));
    chain = chain.then(async () => {
      if (version !== epoch) return false;
      try {
        data.revision = target.revision;
        const saved = await request('/pheno-sessions', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
        if (version !== epoch) return false;
        target.revision = saved.revision;
        items = [saved, ...items.filter(item => item.id !== saved.id)];
        recovery(); status.textContent = 'Saved'; render(); return true;
      } catch (error) {if (version === epoch) {recovery(true, error.status === 409 && target.revision > 0); status.textContent = 'Not saved: ' + error.message;} return false;}
    });
    return chain;
  }
  async function load() {
    const version = epoch;
    try {const data = await request('/pheno-sessions'); if (version === epoch) {items = data.sessions; render();}}
    catch (error) {if (version === epoch) status.textContent = error.message;}
  }
  function detach() {clearTimeout(timer); epoch++; current = null; runSetup = null; activeResult = -1; explanationProgress = null; runProgress = null; recovery(); status.textContent = ''; render();}
  async function showTurn(index) {
    if (pheno.chatBusy() || restoring) return;
    const turn = current?.turns[index]; if (!turn) return;
    restoring = true;
    try {
      if (turn.kind === 'explanation') {
        const run = current.turns.find(t => t.kind === 'result' && t.payload.job_id === turn.payload.chat_run_job_id);
        if (run) {pheno.restoreChatSetup(run.setup); await pheno.restoreChatResult(run.payload);}
        pheno.restoreChatExplanation(turn.payload);
      }
      else {
        let result = turn.payload;
        if (turn.kind === 'queued') {
          const id = result.data?.job_id;
          const job = await request('/jobs/' + encodeURIComponent(id));
          if (!job.result_payload) {status.textContent = 'This job has no completed result yet. Check Jobs for its status.'; return;}
          result = job.result_payload;
        }
        pheno.restoreChatSetup(turn.setup || current.setup);
        await pheno.restoreChatResult(result);
        activeResult = index;
        render();
      }
      status.textContent = issue() || 'Saved result. Generated files are loaded from run history.';
    } catch (error) {status.textContent = 'Cannot reopen result: ' + error.message;}
    finally {restoring = false;}
  }
  async function open(id, discard = false) {
    if (pheno.chatBusy() || restoring) {status.textContent = 'Wait for the current operation to finish.'; return;}
    if (discard) {clearTimeout(timer); await chain;}
    else if ((current || scope()) && !issue() && !await save()) return;
    const version = epoch;
    try {
      const item = await request('/pheno-sessions/' + encodeURIComponent(id));
      if (version !== epoch) return;
      current = item; activeResult = -1; explanationProgress = null; runProgress = null; recovery(); pheno.resetPhenoRunWorkspace(); pheno.restoreChatSetup(item.setup);
      openTab(true); render(); status.textContent = issue() || 'Saved';
      const latest = item.turns.map((t,i) => ['result','queued'].includes(t.kind) ? i : -1).filter(i => i >= 0).at(-1);
      if (latest !== undefined) await showTurn(latest);
      addWorkspaceRestoreAction(status, { scope: item.dataset_id, currentScope: scope(),
        restore: restoreWorkspace, reopen: () => open(id, true) });
    } catch (error) {status.textContent = error.message;}
  }
  async function newChat() {
    if (pheno.chatBusy() || restoring) {status.textContent = 'Wait for the current operation to finish.'; return;}
    if (!issue() && !await save()) return;
    detach(); pheno.resetPhenoRunWorkspace(); pheno.restoreChatSetup({}); openTab();
    document.getElementById('analysisChatSearch').value = '';
    if (scope()) {ensure(); await save();}
    render();
    refs.phenoPromptEl.focus();
  }
  async function record(kind, payload) {
    if (restoring || issue()) return;
    if (kind === 'explanation') explanationProgress = null;
    else runProgress = null;
    const chat = ensure();
    if (kind === 'result' && chat.turns.some(t => t.kind === kind && t.payload.job_id === payload.job_id)) return;
    chat.turns.push({kind, payload, setup:kind === 'explanation' ? setup() : (runSetup || setup())});
    if (kind === 'result') activeResult = chat.turns.length - 1;
    render(); await save();
    panel.lastElementChild?.scrollIntoView({block:'start', behavior:'smooth'});
  }
  panel.addEventListener('click', event => {const b=event.target.closest('[data-pheno-turn]'); if(b) void showTurn(Number(b.dataset.phenoTurn));});
  document.getElementById('phenoChatSave').addEventListener('click', () => void save());
  document.getElementById('phenoChatReload').addEventListener('click', () => {
    if (current && window.confirm('Reload the saved chat and discard unsaved changes in this window?')) void open(current.id, true);
  });
  document.getElementById('phenoTab').addEventListener('input', event => {
    if (!Object.values(fields).includes(event.target.id) && !Object.values(checks).includes(event.target.id)) return;
    clearTimeout(timer); if (!restoring && !pheno.chatBusy()) timer = setTimeout(() => void save(), 700);
  });
  document.getElementById('analysisSessionList').addEventListener('click', async event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.phenoSessionId) return void open(button.dataset.phenoSessionId);
    const id = button.dataset.phenoRename || button.dataset.phenoDelete; if (!id || pheno.chatBusy() || restoring) return;
    try {
      if (!await save()) return;
      if (button.dataset.phenoRename) {
        const name = window.prompt('Rename Pheno-Ranker chat', items.find(i => i.id === id)?.title || '');
        if (!name?.trim()) return;
        const item = await request('/pheno-sessions/' + encodeURIComponent(id));
        const saved = await request('/pheno-sessions', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...item,title:name.trim().slice(0,200),title_custom:true})});
        if (current?.id === id) {current.title=saved.title; current.title_custom=true; current.revision=saved.revision;}
      } else {
        if (!window.confirm('Delete this chat? Generated runs, files and saved cohorts are kept.')) return;
        await request('/pheno-sessions/' + encodeURIComponent(id), {method:'DELETE'});
        forget([id]);
      }
      await load();
    } catch(error) {status.textContent = error.message;}
  });
  function forget(ids) {
    if (ids.includes(current?.id)) {detach(); pheno.resetPhenoRunWorkspace(); pheno.restoreChatSetup({});}
    items=items.filter(i => !ids.includes(i.id)); render();
  }
  window.addEventListener('cohortome:workspace-changing', detach);
  return {save, load, newChat, issue, record, forgetDeletedChats:forget,
    explanationStatus(update) {
      explanationProgress = update.error
        ? {request: explanationProgress?.request || 'Explain results', message: update.error, error: true}
        : {request: update.llm ? 'Explain these results with LLM' : 'Explain these results',
           message: update.llm ? 'Explaining results with LLM…' : 'Explaining results…', error: false};
      render();
      panel.lastElementChild?.scrollIntoView({block:'nearest', behavior:'smooth'});
    },
    async beforeRun() {
      const saved = await save();
      if (saved) {
        runSetup = setup(); runProgress = runSetup; activeResult = -1; explanationProgress = null;
        resultWorkspace.classList.add('is-hidden');
        render();
        panel.lastElementChild?.scrollIntoView({block:'nearest', behavior:'smooth'});
      }
      return saved;
    },
    clear() {items=[]; detach();},
    entries:() => items.map(item => ({...item, chatKind:'pheno', updatedAt:item.updated_at})),
    renderCard(item) {
      const active=current?.id===item.id && document.getElementById('phenoTab').classList.contains('active');
      return `<div class="analysis-session-card${active?' is-active':''}"><button type="button" class="analysis-session-main" data-pheno-session-id="${esc(item.id)}" aria-label="Pheno-Ranker: ${esc(item.title)}"><div class="analysis-session-title"><span class="chat-type-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="m8 8 3 7m5-7-3 7M9 6h6"/></svg></span>${esc(item.title)}</div></button><details class="analysis-chat-menu"><summary aria-label="Chat actions">⋯</summary><div>${actions('pheno',item.id)}<button data-pheno-rename="${esc(item.id)}">Rename</button><button data-pheno-delete="${esc(item.id)}">Delete</button></div></details></div>`;
    }};
}
