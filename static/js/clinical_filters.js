// Clinical predicates are evaluated by DuckDB. This component only edits rules
// and reports a dataset-qualified selection to its owning coverage view.
const operators = {
  eq: 'is', ne: 'is not', in: 'is any of', contains: 'contains',
  lt: 'less than', lte: 'at most', gt: 'greater than', gte: 'at least',
  between: 'between', is_present: 'is recorded', is_missing: 'is not recorded',
};
const noValue = op => ['is_present', 'is_missing'].includes(op);

export function parseClinicalFilterValues(kind, operator, inputs) {
  if (noValue(operator)) return [];
  const values = inputs.map(raw => {
    const text = String(raw).trim();
    if (!text) throw new Error('Enter a value.');
    if (kind === 'number') {
      const value = Number(text);
      if (!Number.isFinite(value)) throw new Error('Enter a finite number.');
      return value;
    }
    if (kind === 'boolean') {
      if (!['true', 'false'].includes(text)) throw new Error('Choose Yes or No.');
      return text === 'true';
    }
    if (kind === 'date') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || !Number.isFinite(Date.parse(text))
          || new Date(text).toISOString().slice(0, 10) !== text) throw new Error('Enter a valid date.');
    }
    return text;
  });
  const required = operator === 'between' ? 2 : 1;
  if (values.length < required) throw new Error(operator === 'between' ? 'Enter both range limits.' : 'Enter a value.');
  if (operator === 'between' && values[0] > values[1]) throw new Error('The lower limit must not exceed the upper limit.');
  if (values.length > 50) throw new Error('Use at most 50 values.');
  return operator === 'in' ? [...new Set(values)] : values;
}

export function clinicalRuleLabel(rule, field) {
  const display = value => typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);
  const value = rule.values.map(display).join(rule.operator === 'between' ? ' and ' : ' or ');
  return `${field.label} ${operators[rule.operator] || rule.operator}${value ? ' ' + value : ''}${value && field.unit ? ' ' + field.unit : ''}`;
}

export function createClinicalFilters({host, workspace, escapeHtml: esc, isCurrent, onChange, onReload}) {
  let fields = [], fingerprint = '', rules = [], loaded = false, disposed = false;
  let loadController, evalController, evaluation = 0, catalogue = 0, draftValues = [], stale = false;
  const live = () => !disposed && host.isConnected && isCurrent();
  const describe = () => rules.map(rule => {
    const field = fields.find(f => f.id === rule.field_id);
    return field ? `${clinicalRuleLabel(rule, field)} [${field.dataset_labels.join(', ')}]` : 'Unavailable clinical field';
  }).join('; AND ');
  host.innerHTML = `<div class="clinical-filter-toolbar">
    <button type="button" class="query-chip clinical-filter-add" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 5h16M7 12h10M10 19h4"/></svg>Add clinical filter</button>
    <button type="button" class="query-chip clinical-filter-clear" hidden>Clear clinical filters</button>
    </div><div class="clinical-filter-rules" aria-label="Active clinical filters"></div>
    <div class="clinical-filter-editor" hidden>
      <div class="clinical-filter-catalogue-status" role="status"></div>
      <div class="clinical-filter-controls" hidden>
        <div class="clinical-filter-groups" aria-label="Clinical field categories"></div>
        <div class="clinical-filter-field-row">
          <label>Search clinical fields<input type="search" class="clinical-filter-search" aria-label="Search clinical fields" placeholder="Optional: narrow the list below"></label>
          <label>Clinical field<select class="clinical-filter-field" aria-label="Clinical field"><option value="">Choose a field</option></select></label>
        </div><div class="clinical-filter-browse"></div><p class="clinical-filter-source section-note"></p>
        <form class="clinical-filter-form" hidden>
          <div class="clinical-filter-value-row"><label>Operator<select class="clinical-filter-operator" aria-label="Operator"></select></label><div class="clinical-filter-values"></div>
          <button type="submit" class="query-chip">Apply filter</button></div>
          <div class="clinical-filter-validation" role="alert"></div>
        </form>
        <p class="section-note">Recorded at any visit. All filters must match; they may match different visits. Missing fields in other datasets are not included.</p>
      </div>
    </div><div class="clinical-filter-status" role="status"></div>`;
  const add = host.querySelector('.clinical-filter-add'), clear = host.querySelector('.clinical-filter-clear');
  const editor = host.querySelector('.clinical-filter-editor'), controls = host.querySelector('.clinical-filter-controls');
  const catalogueStatus = host.querySelector('.clinical-filter-catalogue-status');
  const status = host.querySelector('.clinical-filter-status'), search = host.querySelector('.clinical-filter-search');
  const fieldSelect = host.querySelector('.clinical-filter-field'), operator = host.querySelector('.clinical-filter-operator');
  const form = host.querySelector('.clinical-filter-form'), valuesHost = host.querySelector('.clinical-filter-values');
  const validation = host.querySelector('.clinical-filter-validation');
  const selectedField = () => fields.find(f => f.id === fieldSelect.value);
  let selectedGroup = '';
  const groups = host.querySelector('.clinical-filter-groups');
  const browse = host.querySelector('.clinical-filter-browse');
  const report = payload => { if (live()) onChange({active:rules.length > 0, filters:rules.slice(), description:describe(), fingerprint, ...payload}); };

  function renderRules() {
    clear.hidden = !rules.length; clear.disabled = stale;
    host.querySelector('.clinical-filter-rules').innerHTML = rules.map((rule, index) => {
      const field = fields.find(f => f.id === rule.field_id);
      const label = field ? clinicalRuleLabel(rule, field) : 'Unavailable field';
      return `<span class="clinical-filter-chip" title="${esc(field?.dataset_labels.join(', ') || '')}"><span>${esc(label)}</span><button type="button" class="query-chip" data-remove-clinical="${index}" ${stale ? 'disabled' : ''} aria-label="Remove clinical filter: ${esc(label)}">×</button></span>`;
    }).join('');
    host.querySelectorAll('[data-remove-clinical]').forEach(button => button.onclick = () => {
      if (stale) return;
      rules.splice(Number(button.dataset.removeClinical), 1); renderRules(); evaluate();
    });
  }
  async function loadFields() {
    const ticket = ++catalogue;
    loadController?.abort();
    const controller = new AbortController(); loadController = controller;
    catalogueStatus.textContent = 'Loading clinical fields…'; controls.hidden = true;
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch('/cohort-builder/fields?' + new URLSearchParams({workspace}), {signal:controller.signal});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Clinical fields are unavailable.');
      if (!live() || ticket !== catalogue) return;
      fields = payload.fields || []; fingerprint = payload.fingerprint; loaded = true;
      catalogueStatus.textContent = fields.length ? '' : 'No supported clinical fields are available in this workspace.';
      controls.hidden = !fields.length; renderFieldChoices(); renderRules();
    } catch (error) {
      if (!live() || ticket !== catalogue) return;
      catalogueStatus.innerHTML = `<span>${esc(error.name === 'AbortError' ? 'Loading clinical fields timed out.' : error.message)}</span> <button type="button" class="query-chip">Retry</button>`;
      catalogueStatus.querySelector('button').onclick = loadFields;
    } finally { clearTimeout(timer); }
  }
  function renderFieldChoices() {
    const previous = fieldSelect.value, term = search.value.trim().toLocaleLowerCase();
    const categories = [...new Set(fields.map(f => f.group || 'Clinical fields'))].sort();
    groups.innerHTML = ['', ...categories].map(group => `<button type="button" class="query-chip" data-field-group="${esc(group)}" aria-pressed="${group === selectedGroup}">${esc(group || 'All fields')} <span class="badge">${fields.filter(f => !group || (f.group || 'Clinical fields') === group).length}</span></button>`).join('');
    groups.querySelectorAll('[data-field-group]').forEach(button => button.onclick = () => { selectedGroup = button.dataset.fieldGroup; renderFieldChoices(); });
    const choices = fields.filter(f => (!selectedGroup || (f.group || 'Clinical fields') === selectedGroup) && `${f.label} ${f.unit} ${f.dataset_labels.join(' ')}`.toLocaleLowerCase().includes(term));
    browse.innerHTML = choices.map(f => `<button type="button" class="clinical-filter-field-card" data-field-id="${esc(f.id)}"><strong>${esc(f.label)}</strong><small>${esc([f.unit, ...f.dataset_labels].filter(Boolean).join(' · '))}</small></button>`).join('') || '<p class="section-note">No matching fields.</p>';
    browse.querySelectorAll('[data-field-id]').forEach(button => button.onclick = () => { fieldSelect.value = button.dataset.fieldId; renderField(); form.scrollIntoView({block:'nearest'}); });
    fieldSelect.innerHTML = '<option value="">Choose a field</option>' + choices.map(f => `<option value="${esc(f.id)}">${esc(f.label)}${f.unit ? ' · ' + esc(f.unit) : ''} · ${esc(f.dataset_labels.join(', '))}</option>`).join('');
    fieldSelect.value = choices.some(f => f.id === previous) ? previous : '';
    renderField();
  }
  function renderField() {
    const field = selectedField(); form.hidden = !field; validation.textContent = ''; draftValues = [];
    host.querySelector('.clinical-filter-source').textContent = field ? `Available in: ${field.dataset_labels.join(', ')}${field.unit ? ' · ' + field.unit : ''}${field.observed_range ? ' · Recorded range: ' + field.observed_range.join('–') + ' (any visit; not a reference range)' : ''}` : '';
    browse.querySelectorAll('[data-field-id]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.fieldId === field?.id)));
    if (!field) return;
    operator.innerHTML = field.operators.map(op => `<option value="${esc(op)}">${esc(operators[op] || op)}</option>`).join('');
    renderValues();
  }
  function renderValues() {
    const field = selectedField(); validation.textContent = '';
    if (noValue(operator.value)) { valuesHost.replaceChildren(); return; }
    const type = field.kind === 'number' ? 'number' : field.kind === 'date' ? 'date' : 'text';
    const input = label => field.kind === 'boolean'
      ? `<label>${label}<select data-clinical-value aria-label="${label}"><option value="true">Yes</option><option value="false">No</option></select></label>`
      : `<label>${label}<input type="${type}" aria-label="${label}" ${type === 'number' ? 'step="any"' : ''} data-clinical-value ${type === 'text' ? 'list="clinical-filter-suggestions"' : ''}></label>`;
    valuesHost.innerHTML = input('Value') + (operator.value === 'between' ? input('Upper value') : '')
      + (operator.value === 'in' ? '<button type="button" class="query-chip clinical-filter-add-value">Add value</button><span class="clinical-filter-draft-values"></span>' : '')
      + `<datalist id="clinical-filter-suggestions">${(field.options || []).slice(0, 50).map(v => `<option value="${esc(String(v))}"></option>`).join('')}</datalist>`;
    if (field.kind === 'string' && field.options?.length) {
      const choices = document.createElement('div'); choices.className = 'clinical-filter-recorded-values';
      choices.innerHTML = '<small>Recorded choices (up to 50)</small>' + field.options.slice(0, 50).map((v, i) => `<button type="button" class="query-chip" data-value-index="${i}">${esc(String(v))}</button>`).join('');
      choices.querySelectorAll('[data-value-index]').forEach(button => button.onclick = () => {
        valuesHost.querySelector('[data-clinical-value]').value = field.options[Number(button.dataset.valueIndex)];
        if (operator.value === 'in') valuesHost.querySelector('.clinical-filter-add-value').click();
      });
      valuesHost.append(choices);
    }
    if (operator.value === 'in') {
      const renderDraft = () => {
        valuesHost.querySelector('.clinical-filter-draft-values').innerHTML = draftValues.map((v, index) => `<button type="button" class="query-chip" data-draft="${index}" aria-label="Remove value ${esc(String(v))}">${esc(String(v))} ×</button>`).join('');
        valuesHost.querySelectorAll('[data-draft]').forEach(b => b.onclick = () => {draftValues.splice(Number(b.dataset.draft), 1); renderDraft();});
      };
      valuesHost.querySelector('.clinical-filter-add-value').onclick = () => {
        const input = valuesHost.querySelector('[data-clinical-value]');
        try { draftValues = [...new Set([...draftValues, ...parseClinicalFilterValues(field.kind, 'in', [input.value])])]; input.value = ''; validation.textContent = ''; renderDraft(); }
        catch (error) { validation.textContent = error.message; }
      };
      renderDraft();
    }
  }
  async function evaluate() {
    if (stale) return;
    const ticket = ++evaluation;
    evalController?.abort();
    if (!rules.length) { status.replaceChildren(); report({status:'ready', members:null}); return; }
    status.textContent = 'Updating clinical matches…'; report({status:'loading', members:[]});
    const controller = new AbortController(); evalController = controller;
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch('/cohort-builder/evaluate', {method:'POST', headers:{'Content-Type':'application/json'}, signal:controller.signal,
        body:JSON.stringify({workspace, fingerprint, filters:rules})});
      const payload = await response.json();
      if (!response.ok) {
        const error = new Error(typeof payload.detail === 'string' ? payload.detail : 'Clinical filters could not be evaluated.');
        error.stale = response.status === 409;
        throw error;
      }
      if (!Array.isArray(payload.members)) throw new Error('Clinical filters returned an invalid selection. Retry or clear the filters.');
      if (!live() || ticket !== evaluation) return;
      status.textContent = ''; report({status:'ready', members:payload.members, description:payload.description || describe(), fingerprint:payload.fingerprint});
    } catch (error) {
      if (!live() || ticket !== evaluation) return;
      const message = error.name === 'AbortError' ? 'Clinical filtering timed out. Retry or clear the filters.' : error.message;
      stale = Boolean(error.stale);
      status.innerHTML = `<span>${esc(message)}</span> <button type="button" class="query-chip">${stale ? 'Reload coverage and clear filters' : 'Retry filters'}</button>`;
      status.querySelector('button').onclick = stale ? onReload : evaluate;
      if (stale) {
        add.disabled = true; form.querySelector('[type="submit"]').disabled = true; renderRules();
      }
      report({status:'error', members:[], message});
    } finally { clearTimeout(timer); }
  }
  add.onclick = async () => {
    editor.hidden = !editor.hidden; add.setAttribute('aria-expanded', String(!editor.hidden));
    if (!editor.hidden) { if (!loaded) await loadFields(); groups.querySelector('button')?.focus(); }
  };
  clear.onclick = () => { if (!stale) { rules = []; renderRules(); evaluate(); } };
  search.oninput = renderFieldChoices;
  fieldSelect.onchange = renderField;
  operator.onchange = () => {draftValues = []; renderValues();};
  form.onsubmit = event => {
    event.preventDefault();
    const field = selectedField();
    if (!field || stale) return;
    try {
      const inputs = [...valuesHost.querySelectorAll('[data-clinical-value]')].map(input => input.value);
      const raw = operator.value === 'in' ? [...draftValues, ...inputs.filter(v => String(v).trim())] : inputs;
      const values = parseClinicalFilterValues(field.kind, operator.value, raw);
      if (rules.length >= 20) throw new Error('Use at most 20 clinical filters.');
      rules.push({field_id:field.id, operator:operator.value, values});
      renderRules(); editor.hidden = true; add.setAttribute('aria-expanded', 'false'); evaluate();
    } catch (error) { validation.textContent = error.message; }
  };
  return {destroy() { disposed = true; catalogue++; evaluation++; loadController?.abort(); evalController?.abort(); }};
}
