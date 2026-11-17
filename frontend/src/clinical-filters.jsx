import { useId, useLayoutEffect, useRef, useState } from 'react';
import { clinicalOperators as operators, clinicalNoValue as noValue, parseClinicalFilterValues, clinicalRuleLabel } from '../../static/js/clinical_filters.js';

function initialState(draft) {
  return {fields:[], rules:structuredClone(draft.clinical_filters), labels:draft.clinical_labels.slice(),
    fingerprint:draft.fingerprint, catalogueFingerprint:'', loaded:false, loading:false, catalogueError:'',
    open:false, picker:true, fieldId:'', group:'', query:'', editing:null, operator:'eq',
    inputs:['', ''], values:[], validation:'', stale:''};
}

export function ClinicalFilters({workspace, scopeUi, isCurrent}) {
  const [model, setModel] = useState(() => initialState(scopeUi.getDraft()));
  // The ref lets debounced edits and async catalogue replies read the latest draft.
  const current = useRef(model), mounted = useRef(false), editTimer = useRef(null);
  const request = useRef(null), requestId = useRef(0), signature = useRef(JSON.stringify(model.rules));
  const search = useRef(null), operatorInput = useRef(null), suggestions = useId();
  const update = changes => {current.current = {...current.current, ...changes}; setModel(current.current);};
  const live = () => mounted.current && isCurrent(workspace);
  const cancelEdit = () => {clearTimeout(editTimer.current); editTimer.current = null;};
  const selected = () => current.current.fields.find(field => field.id === current.current.fieldId);
  function report(message = '') {
    if (!live()) return;
    const state = current.current;
    const labels = state.rules.map((rule, index) => {
      const field = state.fields.find(item => item.id === rule.field_id);
      return field ? `${clinicalRuleLabel(rule, field)} [${field.dataset_labels.join(', ')}]` : state.labels[index] || 'Clinical filter';
    });
    signature.current = JSON.stringify(state.rules);
    scopeUi.patch({clinical_filters:state.rules, fingerprint:state.fingerprint, clinical_labels:labels});
    scopeUi.setValidation('clinical', message);
  }
  useLayoutEffect(() => {
    mounted.current = true;
    const unsubscribe = scopeUi.subscribe((snapshot, reason) => {
      if (!live()) return;
      const next = JSON.stringify(snapshot.draft.clinical_filters);
      if (next !== signature.current || ['discard', 'clear'].includes(reason)) {
        cancelEdit(); signature.current = next;
        update({rules:structuredClone(snapshot.draft.clinical_filters), labels:snapshot.draft.clinical_labels.slice(),
          fingerprint:snapshot.draft.fingerprint || (snapshot.draft.clinical_filters.length ? '' : current.current.catalogueFingerprint),
          editing:null, open:false, stale:'', validation:''});
      }
      if (reason === 'settled' && snapshot.errorStatus === 409 && snapshot.draft.clinical_filters.length) {
        cancelEdit(); update({stale:snapshot.error}); report(snapshot.error);
      }
    });
    return () => {mounted.current = false; unsubscribe(); cancelEdit(); requestId.current++; request.current?.abort();};
  }, [workspace, scopeUi, isCurrent]);
  useLayoutEffect(() => {
    if (model.open && model.picker && model.loaded) search.current?.focus();
    else if (model.open && !model.picker) operatorInput.current?.focus();
  }, [model.open, model.picker, model.loaded, model.fieldId]);

  async function loadFields() {
    const ticket = ++requestId.current;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    update({loading:true, catalogueError:''});
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch('/cohort-builder/fields?' + new URLSearchParams({workspace}), {signal:controller.signal});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Clinical fields are unavailable.');
      if (!live() || ticket !== requestId.current) return;
      const state = current.current;
      update({fields:payload.fields || [], loaded:true, loading:false, catalogueFingerprint:payload.fingerprint,
        fingerprint:!state.rules.length || !state.fingerprint ? payload.fingerprint : state.fingerprint});
    } catch (error) {
      if (live() && ticket === requestId.current) update({loading:false,
        catalogueError:error.name === 'AbortError' ? 'Loading clinical fields timed out.' : error.message});
    } finally {clearTimeout(timeout);}
  }
  function valueDefaults(field, operator) {
    return field?.kind === 'number' && operator === 'between' && field.observed_range?.length === 2
      && field.observed_range.every(Number.isFinite) && field.observed_range[0] < field.observed_range[1]
      ? field.observed_range.map(String) : ['', ''];
  }
  function chooseField(fieldId) {
    const field = current.current.fields.find(item => item.id === fieldId);
    if (!field || current.current.stale) return;
    const operator = field.is_recorded_age && field.operators.includes('between') ? 'between' : field.operators[0];
    update({fieldId, picker:false, operator, inputs:valueDefaults(field, operator), values:[], validation:''});
    if (noValue(operator)) scheduleEdit();
  }
  async function toggleEditor() {
    if (current.current.stale) return;
    if (editTimer.current !== null) {cancelEdit(); commitEdit();}
    const open = !(current.current.open && current.current.picker);
    update({open});
    if (!open) return;
    update({editing:null, fieldId:'', group:'', query:'', values:[], picker:true, validation:''});
    report();
    if (!current.current.loaded) await loadFields();
  }
  async function editRule(index) {
    if (current.current.stale) return;
    cancelEdit(); update({editing:index});
    if (!current.current.loaded) await loadFields();
    if (!live() || current.current.stale || current.current.editing === null) return;
    const rule = current.current.rules[index];
    if (!rule) return;
    update({fieldId:rule.field_id, operator:rule.operator, open:true, picker:false, validation:'',
      inputs:rule.operator === 'in' ? ['', ''] : [String(rule.values[0] ?? ''), String(rule.values[1] ?? '')],
      values:rule.operator === 'in' ? rule.values.slice() : []});
  }
  function removeRule(index) {
    if (current.current.stale) return;
    cancelEdit();
    update({editing:null, open:false, rules:current.current.rules.filter((_, i) => i !== index),
      labels:current.current.labels.filter((_, i) => i !== index)}); report();
  }
  function scheduleEdit(delay = 350) {
    cancelEdit();
    if (!live() || current.current.stale || !selected()) return;
    report('Finish editing the clinical filter.');
    editTimer.current = setTimeout(commitEdit, delay);
  }
  function commitEdit() {
    editTimer.current = null;
    const state = current.current, field = selected();
    if (!live() || state.stale || !field) return;
    try {
      const inputs = state.inputs.slice(0, state.operator === 'between' ? 2 : 1);
      const raw = state.operator === 'in' ? [...state.values, ...inputs.filter(value => String(value).trim())] : inputs;
      if (state.operator === 'in' && !raw.length) {
        const rules = state.rules.filter((_, index) => index !== state.editing);
        update({rules, editing:null, validation:''}); report(); return;
      }
      const values = parseClinicalFilterValues(field.kind, state.operator, raw);
      if (state.editing === null && state.rules.length >= 20) throw new Error('Use at most 20 clinical filters.');
      const rules = state.rules.slice(), editing = state.editing ?? rules.length;
      rules[editing] = {field_id:field.id, operator:state.operator, values};
      update({rules, editing, validation:''}); report();
    } catch (error) {update({validation:error.message}); report(error.message);}
  }
  function changeOperator(operator) {
    cancelEdit(); const inputs = valueDefaults(selected(), operator);
    update({operator, inputs, values:[], validation:''});
    if (noValue(operator) || inputs.slice(0, operator === 'between' ? 2 : 1).every(value => value !== '')) scheduleEdit();
    else report();
  }
  function inputValue(index, value, delay = 350) {
    const inputs = current.current.inputs.slice(); inputs[index] = value; update({inputs});
    if (current.current.operator !== 'in') scheduleEdit(delay);
  }
  function addValue(value = current.current.inputs[0]) {
    try {
      const values = [...new Set([...current.current.values, ...parseClinicalFilterValues(selected().kind, 'in', [value])])];
      update({values, inputs:['', ''], validation:''}); scheduleEdit(0);
    } catch (error) {update({validation:error.message});}
  }
  function toggleValue(value) {
    if (current.current.operator !== 'in') {inputValue(0, String(value), 0); return;}
    if (current.current.values.includes(value)) {
      update({values:current.current.values.filter(item => item !== value)}); scheduleEdit(0);
    } else addValue(String(value));
  }
  function reload() {
    cancelEdit(); requestId.current++; request.current?.abort();
    scopeUi.setValidation('clinical', '');
    scopeUi.patch({clinical_filters:[], fingerprint:'', clinical_labels:[]});
    update(initialState(scopeUi.getDraft()));
  }

  const field = model.fields.find(item => item.id === model.fieldId);
  const categories = [...new Set(model.fields.map(item => item.group || 'Clinical fields'))].sort();
  const choices = model.fields.filter(item => (!model.group || (item.group || 'Clinical fields') === model.group)
    && `${item.label} ${item.unit} ${item.dataset_labels.join(' ')}`.toLocaleLowerCase().includes(model.query.trim().toLocaleLowerCase()));
  const range = field?.kind === 'number' && model.operator === 'between' && field.observed_range?.length === 2
    && field.observed_range.every(Number.isFinite) && field.observed_range[0] < field.observed_range[1] ? field.observed_range : null;
  const type = field?.kind === 'number' ? 'number' : field?.kind === 'date' ? 'date' : 'text';
  const valueInput = (label, index) => <label key={label}>{label}{field?.kind === 'boolean'
    ? <select data-clinical-value="" aria-label={label} disabled={!!model.stale} value={model.inputs[index]} onChange={event => inputValue(index, event.target.value, 0)}>
      <option value="">Choose…</option><option value="true">Yes</option><option value="false">No</option>
    </select>
    : <input type={type} aria-label={label} data-clinical-value="" disabled={!!model.stale} step={type === 'number' ? 'any' : undefined}
      list={type === 'text' ? suggestions : undefined} value={model.inputs[index]} onChange={event => inputValue(index, event.target.value)}/>}</label>;
  return <>
    <div className="clinical-filter-toolbar">
      <button type="button" className="query-chip clinical-filter-add" aria-expanded={model.open} disabled={!!model.stale} onClick={toggleEditor}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 5h16M7 12h10M10 19h4"/></svg>Add clinical filter
      </button>
      <button type="button" className="query-chip clinical-filter-clear" hidden={!model.rules.length && !editTimer.current} disabled={!!model.stale}
        onClick={() => {cancelEdit(); update({rules:[], labels:[], editing:null, open:false}); report();}}>Clear clinical filters</button>
    </div>
    <div className="clinical-filter-rules" aria-label="Active clinical filters">{model.rules.map((rule, index) => {
      const source = model.fields.find(item => item.id === rule.field_id);
      const label = source ? clinicalRuleLabel(rule, source) : model.labels[index] || 'Clinical filter';
      return <span className="clinical-filter-chip" key={index} title={source?.dataset_labels.join(', ') || ''}>
        <button type="button" className="query-chip" data-edit-clinical={index} disabled={!!model.stale} aria-label={`Edit clinical filter: ${label}`} onClick={() => editRule(index)}>{label} <span aria-hidden="true">✎</span></button>
        <button type="button" className="query-chip" data-remove-clinical={index} disabled={!!model.stale} aria-label={`Remove clinical filter: ${label}`} onClick={() => removeRule(index)}>×</button>
      </span>;
    })}</div>
    <div className="clinical-filter-editor" hidden={!model.open}>
      <div className="clinical-filter-catalogue-status" role="status">{model.loading ? 'Loading clinical fields…' : model.catalogueError
        ? <><span>{model.catalogueError}</span>{' '}<button type="button" className="query-chip" onClick={loadFields}>Retry</button></>
        : model.loaded && !model.fields.length ? 'No supported clinical fields are available in this workspace.' : ''}</div>
      <div className="clinical-filter-controls" hidden={!model.loaded || !model.fields.length || model.loading || !!model.catalogueError}>
        <div className="clinical-filter-picker" hidden={!model.picker}>
          <div className="clinical-filter-picker-heading"><strong>Choose a field</strong><input ref={search} type="search" className="clinical-filter-search"
            aria-label="Search clinical fields" placeholder="Search fields…" value={model.query} onChange={event => update({query:event.target.value})}/></div>
          <div className="clinical-filter-groups" aria-label="Clinical field categories">{['', ...categories].map(group =>
            <button type="button" className="query-chip" key={group} data-field-group={group} aria-pressed={model.group === group} onClick={() => update({group})}>
              {group || 'All fields'} <span className="badge">{model.fields.filter(item => !group || (item.group || 'Clinical fields') === group).length}</span>
            </button>)}</div>
          <div className="clinical-filter-browse">{choices.length ? choices.map(item =>
            <button type="button" className="clinical-filter-field-card" key={item.id} data-field-id={item.id} aria-pressed={item.id === model.fieldId}
              disabled={!!model.stale} onClick={() => chooseField(item.id)}><strong>{item.label}</strong><small>{[item.unit, ...item.dataset_labels].filter(Boolean).join(' · ')}</small></button>)
            : <p className="section-note">No matching fields.</p>}</div>
        </div>
        <form className="clinical-filter-form" hidden={model.picker || !field} onSubmit={event => {
          event.preventDefault(); if (model.operator === 'in' && model.inputs[0].trim()) addValue(); else scheduleEdit(0);
        }}>
          <div className="clinical-filter-picker-heading"><strong className="clinical-filter-selected-name">{field?.label || ''}</strong>
            <button type="button" className="query-chip clinical-filter-change" disabled={!!model.stale} onClick={() => {cancelEdit(); update({editing:null, picker:true, validation:''}); report();}}>Change field</button>
          </div>
          <p className="clinical-filter-source section-note">{field ? `Available in: ${field.dataset_labels.join(', ')}${field.unit ? ' · ' + field.unit : ''}${field.observed_range ? ' · Recorded range: ' + field.observed_range.join('–') + ' (any visit; not a reference range)' : ''}` : ''}</p>
          <div className="clinical-filter-value-row"><label>Operator<select ref={operatorInput} className="clinical-filter-operator" aria-label="Operator" disabled={!!model.stale}
            value={model.operator} onChange={event => changeOperator(event.target.value)}>{(field?.operators || []).map(operator => <option key={operator} value={operator}>{operators[operator] || operator}</option>)}</select></label>
            <div className="clinical-filter-values">{!noValue(model.operator) && <>
              {valueInput('Value', 0)}{model.operator === 'between' && valueInput('Upper value', 1)}
              {model.operator === 'in' && <><button type="button" className="query-chip clinical-filter-add-value" disabled={!!model.stale} onClick={() => addValue()}>Add value</button>
                <span className="clinical-filter-draft-values">{model.values.map((value, index) => <button type="button" className="query-chip" key={String(value)} data-draft={index}
                  disabled={!!model.stale} aria-label={`Remove value ${value}`} onClick={() => toggleValue(value)}>{`${value} ×`}</button>)}</span></>}
              <datalist id={suggestions}>{(field?.options || []).slice(0, 50).map(value => <option key={String(value)} value={String(value)}/>)}</datalist>
              {range && <div className="clinical-range">{['Minimum', 'Maximum'].map((label, index) => <label key={label}>{label}
                <input type="range" aria-label={`${label} range`} min={range[0]} max={range[1]} step="any" disabled={!!model.stale}
                  value={model.inputs[index] === '' ? range[index] : model.inputs[index]} onChange={event => {
                    const other = Number(current.current.inputs[1 - index]); let value = Number(event.target.value);
                    if (Number.isFinite(other)) value = index ? Math.max(value, other) : Math.min(value, other);
                    inputValue(index, String(Math.round(value * 100) / 100));
                  }}/></label>)}</div>}
              {field?.kind === 'string' && !!field.options?.length && <div className="clinical-filter-recorded-values"><small>Recorded choices (up to 50)</small>
                {field.options.slice(0, 50).map((value, index) => <button type="button" className="query-chip" key={String(value)} data-value-index={index} disabled={!!model.stale}
                  aria-pressed={model.operator === 'in' ? model.values.includes(value) : model.inputs[0] === String(value)} onClick={() => toggleValue(value)}>{String(value)}</button>)}
              </div>}
            </>}</div>
          </div><div className="clinical-filter-validation" role="alert">{model.validation}</div>
        </form>
        <details className="clinical-filter-help"><summary>How clinical filters work</summary><p>Recorded at any visit. All filters must match; they may match different visits. Missing fields in other datasets are not included. Recorded ranges are not clinical reference ranges.</p></details>
      </div>
    </div>
    <div className="clinical-filter-status" role="status">{model.stale && <><span>{model.stale}</span>{' '}<button type="button" className="query-chip" onClick={reload}>Reload clinical filters</button></>}</div>
  </>;
}
