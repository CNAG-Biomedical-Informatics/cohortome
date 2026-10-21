export function createPatientOverview({state, navigation, escapeHtml: esc, scope, openTimeline}) {
  const input = document.getElementById('patientOverviewSearch');
  const list = document.getElementById('patientOverviewMatches');
  const status = document.getElementById('patientOverviewStatus');
  const detail = document.getElementById('patientOverviewDetail');
  let timer, controller, generation = 0, matches = [], active = -1, nextPage = null, loading = false;
  const more = document.getElementById('patientOverviewMore');
  const timelineButton = document.getElementById('patientTimelineBtn');
  function clearSelection() {
    state.patientOverviewSelection = null;
    timelineButton.disabled = true;
    if (state.currentDashboardSubtab === 'timeline') navigation.setDashboardSubtab('patients');
  }
  const value = text => esc(String(text || 'Not recorded'));
  function close() {
    list.hidden = true; input.setAttribute('aria-expanded', 'false');
    more.hidden = true;
    input.removeAttribute('aria-activedescendant'); active = -1;
  }
  function reset() {
    clearSelection();
    clearTimeout(timer); controller?.abort(); generation++;
    close(); matches = []; list.replaceChildren(); detail.replaceChildren(); input.value = '';
    status.textContent = 'Browse patients or type a patient ID or ClarID.';
  }
  async function request(path, params, signal) {
    const response = await fetch(`/patient-overview/${path}?${new URLSearchParams(params)}`, {signal});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load patient information.');
    return data;
  }
  async function choose(index) {
    const match = matches[index]; if (!match) return;
    clearSelection();
    clearTimeout(timer); controller?.abort(); controller = new AbortController();
    const ticket = ++generation, selectedScope = scope();
    close(); input.value = match.patient_id; detail.replaceChildren();
    status.textContent = 'Opening patient timeline…';
    try {
      state.patientOverviewSelection = { patientId: match.patient_id, datasetId: match.dataset_id };
      timelineButton.disabled = false;
      await openTimeline(match.patient_id, match.dataset_id);
      if (ticket !== generation || selectedScope !== scope()) return;
      status.textContent = `Selected ${match.patient_id} in ${match.dataset_label}. Details are in Timeline.`;
    } catch (error) {
      if (ticket === generation && error.name !== 'AbortError') status.textContent = error.message;
    }
  }
  function searchPatients(append = false) {
    if (append && (loading || !nextPage)) return;
    clearTimeout(timer); controller?.abort(); generation++;
    if (!append) { close(); matches = []; nextPage = null; }
    const q = input.value.trim();
    if (!scope()) { status.textContent = 'Select and apply a dataset first.'; return; }
    status.textContent = q ? 'Searching…' : 'Loading patients…';
    loading = true; more.disabled = true;
    const ticket = generation, selectedScope = scope();
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const data = await request('search', {workspace:selectedScope, q, ...(append ? nextPage : {})}, controller.signal);
        if (ticket !== generation || selectedScope !== scope()) return;
        matches = append ? matches.concat(data.matches) : data.matches;
        nextPage = data.next || null;
        list.innerHTML = matches.map((m,i) => `<button type="button" role="option" aria-selected="false" tabindex="-1" id="patient-match-${i}" data-match="${i}"><strong>${value(m.patient_id)}</strong><span>${value(m.dataset_label)}${m.diagnosis ? ` · ${value(m.diagnosis)}` : ''}${m.clarid ? ` · ${value(m.clarid)}` : ''}</span></button>`).join('');
        list.hidden = !matches.length; input.setAttribute('aria-expanded', String(!!matches.length));
        more.hidden = !nextPage;
        status.textContent = matches.length ? `${matches.length} patients shown. Select one or type to filter.` : 'No matching patients in the active datasets.';
      } catch (error) {
        if (ticket === generation && error.name !== 'AbortError') status.textContent = error.message;
      } finally { if (ticket === generation) { loading = false; more.disabled = false; } }
    }, 200);
  }
  input.addEventListener('input', () => {
    clearSelection(); detail.replaceChildren(); searchPatients();
  });
  input.addEventListener('focus', () => { if (list.hidden) searchPatients(); });
  input.addEventListener('click', () => { if (list.hidden && !loading) searchPatients(); });
  more.addEventListener('click', () => searchPatients(true));
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') { close(); return; }
    if (list.hidden || !matches.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      active = active < 0 ? (event.key === 'ArrowDown' ? 0 : matches.length - 1)
        : (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
      [...list.children].forEach((el,i) => el.setAttribute('aria-selected', String(i === active)));
      input.setAttribute('aria-activedescendant', `patient-match-${active}`);
      list.children[active].scrollIntoView({block:'nearest'});
    } else if (event.key === 'Enter' && active >= 0) { event.preventDefault(); void choose(active); }
  });
  list.addEventListener('click', event => {
    const option = event.target.closest('[data-match]'); if (option) void choose(Number(option.dataset.match));
  });
  document.addEventListener('click', event => { if (!event.target.closest('.patient-lookup')) close(); });
  window.addEventListener('cohortome:workspace-changing', reset);
  document.getElementById('patientOverviewViewBtn').addEventListener('click', () => navigation.setDashboardSubtab('patients'));
  timelineButton.addEventListener('click', () => {
    if (state.patientOverviewSelection && !timelineButton.disabled) void openTimeline(state.patientOverviewSelection.patientId, state.patientOverviewSelection.datasetId);
  });
  document.getElementById('dashboardPatientsBtn').addEventListener('click', () => {
    navigation.setDashboardSubtab('patients'); input.focus();
  });
}
