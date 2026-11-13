// Edit draft predicates locally. The shared Apply to scope action evaluates
// the complete clinical + modality filter set once on the backend.
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

export function createClinicalFilters({host, workspace, escapeHtml: esc, isCurrent, onChange, onReload,
  initialFilters = [], initialFingerprint = '', initialLabels = []}) {
  let fields = [], fingerprint = initialFingerprint, rules = structuredClone(initialFilters), loaded = false, disposed = false;
  let catalogueFingerprint = '';
  let labels = initialLabels.slice();
  let loadController, catalogue = 0, draftValues = [], stale = false;
  let editTimer;
  const cancelEdit = () => { clearTimeout(editTimer); editTimer = null; };
  const live = () => !disposed && host.isConnected && isCurrent();
  const ruleLabels = () => rules.map((rule, index) => {
    const field = fields.find(f => f.id === rule.field_id);
    return field ? `${clinicalRuleLabel(rule, field)} [${field.dataset_labels.join(', ')}]` : labels[index] || 'Clinical filter';
  });
  const describe = () => ruleLabels().join('; AND ');
  host.innerHTML = `<div class="clinical-filter-toolbar">
    <button type="button" class="query-chip clinical-filter-add" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 5h16M7 12h10M10 19h4"/></svg>Add clinical filter</button>
    <button type="button" class="query-chip clinical-filter-clear" hidden>Clear clinical filters</button>
    </div><div class="clinical-filter-rules" aria-label="Active clinical filters"></div>
    <div class="clinical-filter-editor" hidden>
      <div class="clinical-filter-catalogue-status" role="status"></div>
      <div class="clinical-filter-controls" hidden>
        <div class="clinical-filter-picker">
        <div class="clinical-filter-picker-heading"><strong>Choose a field</strong><input type="search" class="clinical-filter-search" aria-label="Search clinical fields" placeholder="Search fields…"></div>
        <div class="clinical-filter-groups" aria-label="Clinical field categories"></div>
        <div class="clinical-filter-browse"></div></div>
        <form class="clinical-filter-form" hidden>
          <div class="clinical-filter-picker-heading"><strong class="clinical-filter-selected-name"></strong><button type="button" class="query-chip clinical-filter-change">Change field</button></div>
          <p class="clinical-filter-source section-note"></p>
          <div class="clinical-filter-value-row"><label>Operator<select class="clinical-filter-operator" aria-label="Operator"></select></label><div class="clinical-filter-values"></div>
          </div>
          <div class="clinical-filter-validation" role="alert"></div>
        </form>
        <details class="clinical-filter-help"><summary>How clinical filters work</summary><p>Recorded at any visit. All filters must match; they may match different visits. Missing fields in other datasets are not included. Recorded ranges are not clinical reference ranges.</p></details>
      </div>
    </div><div class="clinical-filter-status" role="status"></div>`;
  const add = host.querySelector('.clinical-filter-add'), clear = host.querySelector('.clinical-filter-clear');
  const editor = host.querySelector('.clinical-filter-editor'), controls = host.querySelector('.clinical-filter-controls');
  const catalogueStatus = host.querySelector('.clinical-filter-catalogue-status');
  const status = host.querySelector('.clinical-filter-status'), search = host.querySelector('.clinical-filter-search');
  const operator = host.querySelector('.clinical-filter-operator');
  let selectedFieldId = '';
  let editing = null;
  const picker = host.querySelector('.clinical-filter-picker');
  const form = host.querySelector('.clinical-filter-form'), valuesHost = host.querySelector('.clinical-filter-values');
  const validation = host.querySelector('.clinical-filter-validation');
  const selectedField = () => fields.find(f => f.id === selectedFieldId);
  let selectedGroup = '';
  const groups = host.querySelector('.clinical-filter-groups');
  const browse = host.querySelector('.clinical-filter-browse');
  const report = payload => { if (live()) onChange({active:rules.length > 0, filters:structuredClone(rules), rule_labels:ruleLabels(), description:describe(), fingerprint, ...payload}); };

  function renderRules() {
    clear.hidden = !rules.length; clear.disabled = stale;
    host.querySelector('.clinical-filter-rules').innerHTML = rules.map((rule, index) => {
      const field = fields.find(f => f.id === rule.field_id);
      const label = field ? clinicalRuleLabel(rule, field) : labels[index] || 'Clinical filter';
      return `<span class="clinical-filter-chip" title="${esc(field?.dataset_labels.join(', ') || '')}"><button type="button" class="query-chip" data-edit-clinical="${index}" ${stale ? 'disabled' : ''} aria-label="Edit clinical filter: ${esc(label)}">${esc(label)} <span aria-hidden="true">✎</span></button><button type="button" class="query-chip" data-remove-clinical="${index}" ${stale ? 'disabled' : ''} aria-label="Remove clinical filter: ${esc(label)}">×</button></span>`;
    }).join('');
    host.querySelectorAll('[data-remove-clinical]').forEach(button => button.onclick = () => {
      if (stale) return;
      cancelEdit();
      editing = null; editor.hidden = true; add.setAttribute('aria-expanded', 'false');
      const index = Number(button.dataset.removeClinical);
      rules.splice(index, 1); labels.splice(index, 1); renderRules(); evaluate();
    });
    host.querySelectorAll('[data-edit-clinical]').forEach(button => button.onclick = async () => {
      if (stale) return;
      cancelEdit();
      editing = Number(button.dataset.editClinical);
      if (!loaded) await loadFields();
      if (!live() || stale || editing === null) return;
      const rule = rules[editing]; selectedFieldId = rule.field_id;
      editor.hidden = false; picker.hidden = true; add.setAttribute('aria-expanded', 'true');
      renderField(); operator.value = rule.operator;
      draftValues = rule.operator === 'in' ? [...rule.values] : [];
      renderValues();
      if (rule.operator !== 'in') valuesHost.querySelectorAll('[data-clinical-value]').forEach((input, i) => {
        input.value = String(rule.values[i] ?? '');
        const slider = valuesHost.querySelectorAll('input[type="range"]')[i];
        if (slider) slider.value = input.value;
      });
      operator.focus();
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
      fields = payload.fields || [];
      catalogueFingerprint = payload.fingerprint;
      if (!rules.length || !fingerprint) fingerprint = payload.fingerprint;
      loaded = true;
      catalogueStatus.textContent = fields.length ? '' : 'No supported clinical fields are available in this workspace.';
      controls.hidden = !fields.length; renderFieldChoices(); renderRules();
    } catch (error) {
      if (!live() || ticket !== catalogue) return;
      catalogueStatus.innerHTML = `<span>${esc(error.name === 'AbortError' ? 'Loading clinical fields timed out.' : error.message)}</span> <button type="button" class="query-chip">Retry</button>`;
      catalogueStatus.querySelector('button').onclick = loadFields;
    } finally { clearTimeout(timer); }
  }
  function renderFieldChoices() {
    const term = search.value.trim().toLocaleLowerCase();
    const categories = [...new Set(fields.map(f => f.group || 'Clinical fields'))].sort();
    groups.innerHTML = ['', ...categories].map(group => `<button type="button" class="query-chip" data-field-group="${esc(group)}" aria-pressed="${group === selectedGroup}">${esc(group || 'All fields')} <span class="badge">${fields.filter(f => !group || (f.group || 'Clinical fields') === group).length}</span></button>`).join('');
    groups.querySelectorAll('[data-field-group]').forEach(button => button.onclick = () => { selectedGroup = button.dataset.fieldGroup; renderFieldChoices(); });
    const choices = fields.filter(f => (!selectedGroup || (f.group || 'Clinical fields') === selectedGroup) && `${f.label} ${f.unit} ${f.dataset_labels.join(' ')}`.toLocaleLowerCase().includes(term));
    browse.innerHTML = choices.map(f => `<button type="button" class="clinical-filter-field-card" data-field-id="${esc(f.id)}"><strong>${esc(f.label)}</strong><small>${esc([f.unit, ...f.dataset_labels].filter(Boolean).join(' · '))}</small></button>`).join('') || '<p class="section-note">No matching fields.</p>';
    browse.querySelectorAll('[data-field-id]').forEach(button => button.onclick = () => {
      selectedFieldId = button.dataset.fieldId; picker.hidden = true; renderField(); operator.focus();
      if (noValue(operator.value)) scheduleEdit();
    });
  }
  function renderField() {
    const field = selectedField(); form.hidden = !field; validation.textContent = ''; draftValues = [];
    host.querySelector('.clinical-filter-selected-name').textContent = field?.label || '';
    host.querySelector('.clinical-filter-source').textContent = field ? `Available in: ${field.dataset_labels.join(', ')}${field.unit ? ' · ' + field.unit : ''}${field.observed_range ? ' · Recorded range: ' + field.observed_range.join('–') + ' (any visit; not a reference range)' : ''}` : '';
    browse.querySelectorAll('[data-field-id]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.fieldId === field?.id)));
    if (!field) return;
    operator.innerHTML = field.operators.map(op => `<option value="${esc(op)}">${esc(operators[op] || op)}</option>`).join('');
    if (field.is_recorded_age && field.operators.includes('between')) operator.value = 'between';
    renderValues();
  }
  function renderValues() {
    const field = selectedField(); validation.textContent = '';
    if (noValue(operator.value)) { valuesHost.replaceChildren(); return; }
    const type = field.kind === 'number' ? 'number' : field.kind === 'date' ? 'date' : 'text';
    const input = label => field.kind === 'boolean'
      ? `<label>${label}<select data-clinical-value aria-label="${label}"><option value="">Choose…</option><option value="true">Yes</option><option value="false">No</option></select></label>`
      : `<label>${label}<input type="${type}" aria-label="${label}" ${type === 'number' ? 'step="any"' : ''} data-clinical-value ${type === 'text' ? 'list="clinical-filter-suggestions"' : ''}></label>`;
    valuesHost.innerHTML = input('Value') + (operator.value === 'between' ? input('Upper value') : '')
      + (operator.value === 'in' ? '<button type="button" class="query-chip clinical-filter-add-value">Add value</button><span class="clinical-filter-draft-values"></span>' : '')
      + `<datalist id="clinical-filter-suggestions">${(field.options || []).slice(0, 50).map(v => `<option value="${esc(String(v))}"></option>`).join('')}</datalist>`;
    if (field.kind === 'number' && operator.value === 'between' && field.observed_range?.length === 2) {
      const [low, high] = field.observed_range;
      if (Number.isFinite(low) && Number.isFinite(high) && low < high) {
        const inputs = [...valuesHost.querySelectorAll('[data-clinical-value]')];
        const range = document.createElement('div'); range.className = 'clinical-range';
        range.innerHTML = `<label>Minimum<input type="range" aria-label="Minimum range" min="${low}" max="${high}" step="any" value="${low}"></label><label>Maximum<input type="range" aria-label="Maximum range" min="${low}" max="${high}" step="any" value="${high}"></label>`;
        const sliders = [...range.querySelectorAll('input')];
        inputs.forEach((input, index) => {
          input.value = index ? high : low;
          input.addEventListener('input', () => {
            if (input.value !== '' && Number.isFinite(input.valueAsNumber)) sliders[index].value = input.value;
          });
          sliders[index].addEventListener('input', () => {
            const other = Number(inputs[1 - index].value);
            let value = Number(sliders[index].value);
            if (Number.isFinite(other)) value = index ? Math.max(value, other) : Math.min(value, other);
            sliders[index].value = value; input.value = String(Math.round(value * 100) / 100);
          });
        });
        valuesHost.append(range);
      }
    }
    if (field.kind === 'string' && field.options?.length) {
      const choices = document.createElement('div'); choices.className = 'clinical-filter-recorded-values';
      choices.innerHTML = '<small>Recorded choices (up to 50)</small>' + field.options.slice(0, 50).map((v, i) => `<button type="button" class="query-chip" data-value-index="${i}">${esc(String(v))}</button>`).join('');
      choices.querySelectorAll('[data-value-index]').forEach(button => button.onclick = () => {
        const value = field.options[Number(button.dataset.valueIndex)];
        if (operator.value === 'in' && draftValues.includes(value)) {
          draftValues = draftValues.filter(item => item !== value); renderValues(); scheduleEdit(0); return;
        }
        valuesHost.querySelector('[data-clinical-value]').value = field.options[Number(button.dataset.valueIndex)];
        if (operator.value === 'in') valuesHost.querySelector('.clinical-filter-add-value').click();
        else {
          choices.querySelectorAll('[data-value-index]').forEach(choice => choice.setAttribute('aria-pressed', String(choice === button)));
          scheduleEdit(0);
        }
      });
      valuesHost.append(choices);
    }
    if (operator.value === 'in') {
      const renderDraft = () => {
        valuesHost.querySelectorAll('[data-value-index]').forEach(button => button.setAttribute('aria-pressed', String(draftValues.includes(field.options[Number(button.dataset.valueIndex)]))));
        valuesHost.querySelector('.clinical-filter-draft-values').innerHTML = draftValues.map((v, index) => `<button type="button" class="query-chip" data-draft="${index}" aria-label="Remove value ${esc(String(v))}">${esc(String(v))} ×</button>`).join('');
        valuesHost.querySelectorAll('[data-draft]').forEach(b => b.onclick = () => {draftValues.splice(Number(b.dataset.draft), 1); renderDraft(); scheduleEdit(0);});
      };
      valuesHost.querySelector('.clinical-filter-add-value').onclick = () => {
        const input = valuesHost.querySelector('[data-clinical-value]');
        try { draftValues = [...new Set([...draftValues, ...parseClinicalFilterValues(field.kind, 'in', [input.value])])]; input.value = ''; validation.textContent = ''; renderDraft(); scheduleEdit(0); }
        catch (error) { validation.textContent = error.message; }
      };
      renderDraft();
    }
  }
  function evaluate() {
    if (stale) return;
    labels = ruleLabels(); status.textContent = ''; report({status:'ready'});
  }
  function invalidate(message) {
    if (!live()) return;
    stale = true;
    status.innerHTML = `<span>${esc(message)}</span> <button type="button" class="query-chip">Reload clinical filters</button>`;
    status.querySelector('button').onclick = onReload;
    cancelEdit(); add.disabled = true;
    form.querySelectorAll('input, select, button').forEach(control => { control.disabled = true; });
    renderRules();
    report({status:'error', members:[], message});
  }
  add.onclick = async () => {
    if (editTimer !== null && editTimer !== undefined) { cancelEdit(); commitEdit(); }
    editor.hidden = !editor.hidden && form.hidden;
    add.setAttribute('aria-expanded', String(!editor.hidden));
    if (!editor.hidden) {
      editing = null;
      evaluate(); // Discard an incomplete editor value, retaining its last valid rule.
      // Adding starts a new rule; the previously applied rule stays in the chips.
      selectedFieldId = ''; selectedGroup = ''; search.value = ''; draftValues = [];
      picker.hidden = false; renderField();
      if (!loaded) await loadFields(); else renderFieldChoices();
      search.focus();
    }
  };
  clear.onclick = () => { if (!stale) { cancelEdit(); editing = null; editor.hidden = true; add.setAttribute('aria-expanded', 'false'); rules = []; labels = []; renderRules(); evaluate(); } };
  search.oninput = renderFieldChoices;
  host.querySelector('.clinical-filter-change').onclick = () => { cancelEdit(); editing = null; evaluate(); form.hidden = true; picker.hidden = false; renderFieldChoices(); search.focus(); };
  operator.onchange = () => {
    cancelEdit(); draftValues = []; renderValues();
    if (noValue(operator.value) || [...valuesHost.querySelectorAll('[data-clinical-value]')].every(input => input.value !== '')) scheduleEdit();
    else evaluate(); // Abandon an incomplete draft, keeping the applied rule intact.
  };
  valuesHost.addEventListener('input', () => {
    // A free-text multi-value entry is an atomic value, added with Enter/Add
    // value. Otherwise a pause halfway through typing could add a partial term.
    if (operator.value !== 'in') scheduleEdit();
  });
  valuesHost.addEventListener('change', event => { if (event.target.tagName === 'SELECT') scheduleEdit(0); });
  form.onsubmit = event => {
    event.preventDefault();
    if (operator.value === 'in' && valuesHost.querySelector('[data-clinical-value]')?.value.trim()) {
      valuesHost.querySelector('.clinical-filter-add-value').click();
    } else scheduleEdit(0);
  };
  function scheduleEdit(delay = 350) {
    cancelEdit();
    if (stale || !selectedField() || !live()) return;
    clear.hidden = false;
    report({active:true, status:'loading', message:'Finish editing the clinical filter.'});
    editTimer = setTimeout(commitEdit, delay);
  }
  function commitEdit() {
    editTimer = null;
    const field = selectedField();
    if (!field || stale || !live()) return;
    try {
      const inputs = [...valuesHost.querySelectorAll('[data-clinical-value]')].map(input => input.value);
      const raw = operator.value === 'in' ? [...draftValues, ...inputs.filter(v => String(v).trim())] : inputs;
      if (operator.value === 'in' && !raw.length) {
        if (editing !== null) { rules.splice(editing, 1); labels.splice(editing, 1); }
        editing = null; validation.textContent = ''; renderRules(); evaluate(); return;
      }
      const values = parseClinicalFilterValues(field.kind, operator.value, raw);
      if (editing === null && rules.length >= 20) throw new Error('Use at most 20 clinical filters.');
      const rule = {field_id:field.id, operator:operator.value, values};
      if (editing === null) { editing = rules.length; rules.push(rule); } else rules[editing] = rule;
      validation.textContent = '';
      renderRules(); evaluate();
    } catch (error) {
      validation.textContent = error.message;
      report({active:true, status:'error', members:[], message:error.message});
    }
  }
  renderRules();
  return {invalidate,
    setFilters(next, nextFingerprint = '', nextLabels = []) {
      cancelEdit(); editing = null; rules = structuredClone(next);
      fingerprint = nextFingerprint || (rules.length ? '' : catalogueFingerprint);
      labels = nextLabels.slice(); stale = false; add.disabled = false;
      form.querySelectorAll('input, select, button').forEach(control => {control.disabled = false;});
      editor.hidden = true; add.setAttribute('aria-expanded', 'false'); validation.textContent = ''; status.textContent = '';
      renderRules();
    },
    destroy() { cancelEdit(); disposed = true; catalogue++; loadController?.abort(); }};
}
