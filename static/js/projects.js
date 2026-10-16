// One resume format for browser download/upload and native file dialogs.
export function createProjectsUi({state, refs, sessions, query, workspace, datasets, navigation}) {
  const rail = document.querySelector('.app-icon-rail');
  const save = document.createElement('button'), open = document.createElement('button');
  save.textContent = 'Save project…'; open.textContent = 'Open project…';
  for (const [button, path] of [
    [save, 'M5 3h12l4 4v14H3V3h2Zm2 0v7h10V3M7 21v-7h10v7'],
    [open, 'M3 7V4h6l2 3h10v13H3V7Zm0 3h18'],
  ]) {
    const icon = document.createElement('span');
    icon.className = 'button-icon'; icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="${path}"/></svg>`;
    button.prepend(icon);
  }
  save.className = open.className = 'app-sidebar-settings';
  save.id = 'saveProjectBtn'; open.id = 'openProjectBtn';
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  status.className = 'app-project-status';
  const toggle = document.createElement('button');
  toggle.type = 'button'; toggle.id = 'projectsMenuBtn'; toggle.className = 'rail-projects';
  toggle.title = 'Projects — save or open';
  toggle.setAttribute('aria-label', toggle.title);
  toggle.setAttribute('aria-haspopup', 'dialog');
  toggle.setAttribute('aria-controls', 'projectsMenu');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.append(save.querySelector('.button-icon').cloneNode(true));
  rail.insertBefore(toggle, document.getElementById('runHistoryDrawerBtn'));
  const section = document.createElement('div');
  section.id = 'projectsMenu'; section.className = 'account-menu app-project-menu';
  section.hidden = true; section.setAttribute('role', 'dialog');
  section.setAttribute('aria-label', 'Projects');
  const heading = document.createElement('p');
  heading.className = 'app-nav-heading'; heading.textContent = 'Projects';
  const hint = document.createElement('p');
  hint.className = 'app-project-hint'; hint.textContent = 'Save or reopen your working state. Data files are not included.';
  section.append(heading, hint, save, open, status);
  document.body.append(section);
  function showMenu(visible, focus = false) {
    section.hidden = !visible;
    toggle.setAttribute('aria-expanded', String(visible));
    if (visible) {
      const bounds = toggle.getBoundingClientRect();
      section.style.left = `${Math.max(8, Math.min(bounds.right + 8, window.innerWidth - section.offsetWidth - 8))}px`;
      section.style.bottom = `${Math.max(8, Math.min(window.innerHeight - bounds.bottom, window.innerHeight - section.offsetHeight - 8))}px`;
      if (focus) save.focus();
    }
  }
  toggle.addEventListener('click', () => showMenu(section.hidden, true));
  document.addEventListener('click', event => {
    if (!section.contains(event.target) && !toggle.contains(event.target)) showMenu(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !section.hidden) { showMenu(false); toggle.focus(); }
  });
  window.addEventListener('resize', () => showMenu(false));
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.cohortome,application/json'; input.hidden = true;
  section.append(input);
  let busy = false, projectName = 'My project';
  const native = () => window.__COHORTOME_DESKTOP__ && window.__TAURI__?.core;
  function idle() {
    if (busy || state.queryInFlight || state.analysisInFlight || state.loadInFlight) {
      throw new Error('Wait for the current operation to finish before saving or opening a project.');
    }
  }
  async function api(path, body) {
    const response = await fetch(`/projects/${path}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Invalid project file.');
    return payload;
  }
  async function run(action) {
    showMenu(true);
    try {
      idle(); busy = true; save.disabled = open.disabled = true;
      await action();
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; save.disabled = open.disabled = false; showMenu(true); }
  }
  async function saveProject() {
    if (!state.currentDatasetIds.length) throw new Error('Select and apply a dataset before saving a project.');
    const name = window.prompt('Project name. Datasets and results remain in this installation; the file contains references and conversation text.', projectName);
    if (!name?.trim()) return;
    const session = await sessions.flushCurrentForProject();
    const tab = document.querySelector('.tab-panel.active')?.id.replace(/Tab$/, '') || 'dashboard';
    const body = {name:name.trim(), view:['dashboard','datasets','query','analysis','pheno'].includes(tab) ? tab : 'dashboard',
      analysis_session_id:session?.datasetId === datasets.currentDatasetSelectionKey() ? session.id : '',
      query_prompt:refs.questionEl.value, query_context:state.queryContextMode,
      conversation:state.queryTurns.filter(t => !t.pending).slice(-16).map(t => ({
        role:t.role, text:String(t.role === 'user' ? t.prompt || '' : t.payload?.reply || '').slice(0,16000),
        context:t.contextMode === 'general' ? 'general' : 'workspace'}))};
    const project = await api('export', body);
    const text = JSON.stringify(project, null, 2);
    if (new TextEncoder().encode(text).length > 1024*1024) throw new Error('Project exceeds the 1 MiB limit.');
    if (native()) {
      const saved = await native().invoke('save_project_file', {text});
      if (!saved) { status.textContent = 'Save cancelled.'; return; }
    } else {
      const url = URL.createObjectURL(new Blob([text], {type:'application/json'}));
      const link = document.createElement('a'); link.href = url;
      link.download = name.replace(/[^a-zA-Z0-9_-]/g, '_') + '.cohortome'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    }
    projectName = name; status.textContent = `Saved project: ${name}. Data and results stay in this installation.`;
  }
  async function restore(text) {
    if (new TextEncoder().encode(text).length > 1024*1024) throw new Error('Choose a project smaller than 1 MiB.');
    const project = JSON.parse(text);
    const check = await api('inspect', project);
    if (!window.confirm(`Open “${project.name}”? This replaces the current workspace selection and Query conversation. Analyses will not run automatically.${check.warnings.length ? '\n' + check.warnings.join('\n') : ''}`)) return;
    await sessions.flushCurrentForProject();
    const result = await api('open', project);
    await datasets.loadDatasets();
    await workspace.loadPatients({respectAdminGate:false, targetDatasetIds:result.dataset_ids});
    if (state.currentDatasetIds.slice().sort().join('|') !== result.dataset_ids.slice().sort().join('|')) {
      throw new Error('The project workspace could not load. Reopen it after resolving the dataset error.');
    }
    await sessions.loadAnalysisSessionsFromBackend();
    if (project.analysis_session_id) sessions.selectAnalysisSession(project.analysis_session_id);
    query.resetQueryWorkspace();
    query.setContextMode(project.query_context);
    state.queryTurns = project.conversation.map(m => m.role === 'user'
      ? {role:'user', prompt:m.text, contextMode:m.context}
      : {role:'assistant', contextMode:m.context, payload:{reply:m.text, data:{}}});
    // Saved text is a reading record, not a live result handle or model history.
    state.queryHistory = [];
    query.renderQueryThread(); refs.questionEl.value = project.query_prompt;
    navigation.setActiveTab(project.view);
    projectName = project.name;
    status.textContent = `Opened ${project.name}. Saved Query text is read-only history; rerun queries for tables and cohort actions. ${result.warnings.join(' ')}`;
  }
  save.addEventListener('click', () => run(saveProject));
  open.addEventListener('click', () => {
    if (native()) void run(async () => { const text = await native().invoke('open_project_file'); if (text !== null) await restore(text); });
    else { try { idle(); input.click(); } catch (error) { status.textContent = error.message; } }
  });
  input.addEventListener('change', () => run(async () => {
    const file = input.files[0]; input.value = '';
    if (!file) return;
    if (file.size > 1024*1024) throw new Error('Choose a project smaller than 1 MiB.');
    await restore(await file.text());
  }));
}
