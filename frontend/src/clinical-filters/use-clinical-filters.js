import { useId, useLayoutEffect, useRef, useState } from 'react';
import {
  clinicalOperators as operators,
  clinicalNoValue as noValue,
  parseClinicalFilterValues,
  clinicalRuleLabel,
} from '../../../static/js/clinical_filters.js';

function initialState(draft) {
  return {
    fields: [],
    rules: structuredClone(draft.clinical_filters),
    labels: draft.clinical_labels.slice(),
    fingerprint: draft.fingerprint,
    catalogueFingerprint: '',
    loaded: false,
    loading: false,
    catalogueError: '',
    open: false,
    picker: true,
    fieldId: '',
    group: '',
    query: '',
    editing: null,
    operator: 'eq',
    inputs: ['', ''],
    values: [],
    validation: '',
    stale: '',
  };
}

export function useClinicalFilters({ workspace, scopeUi, isCurrent }) {
  const [model, setModel] = useState(() => initialState(scopeUi.getDraft()));
  // The ref lets debounced edits and async catalogue replies read the latest draft.
  const current = useRef(model),
    mounted = useRef(false),
    editTimer = useRef(null);
  const request = useRef(null),
    requestId = useRef(0),
    signature = useRef(JSON.stringify(model.rules));
  const search = useRef(null),
    operatorInput = useRef(null),
    suggestions = useId();
  const update = (changes) => {
    current.current = { ...current.current, ...changes };
    setModel(current.current);
  };
  const live = () => mounted.current && isCurrent(workspace);
  const cancelEdit = () => {
    clearTimeout(editTimer.current);
    editTimer.current = null;
  };
  const selected = () =>
    current.current.fields.find((field) => field.id === current.current.fieldId);
  function report(message = '') {
    if (!live()) return;
    const state = current.current;
    const labels = state.rules.map((rule, index) => {
      const field = state.fields.find((item) => item.id === rule.field_id);
      return field
        ? `${clinicalRuleLabel(rule, field)} [${field.dataset_labels.join(', ')}]`
        : state.labels[index] || 'Clinical filter';
    });
    signature.current = JSON.stringify(state.rules);
    scopeUi.patch({
      clinical_filters: state.rules,
      fingerprint: state.fingerprint,
      clinical_labels: labels,
    });
    scopeUi.setValidation('clinical', message);
  }
  useLayoutEffect(() => {
    mounted.current = true;
    const unsubscribe = scopeUi.subscribe((snapshot, reason) => {
      if (!live()) return;
      const next = JSON.stringify(snapshot.draft.clinical_filters);
      if (next !== signature.current || ['discard', 'clear'].includes(reason)) {
        cancelEdit();
        signature.current = next;
        update({
          rules: structuredClone(snapshot.draft.clinical_filters),
          labels: snapshot.draft.clinical_labels.slice(),
          fingerprint:
            snapshot.draft.fingerprint ||
            (snapshot.draft.clinical_filters.length ? '' : current.current.catalogueFingerprint),
          editing: null,
          open: false,
          stale: '',
          validation: '',
        });
      }
      if (
        reason === 'settled' &&
        snapshot.errorStatus === 409 &&
        snapshot.draft.clinical_filters.length
      ) {
        cancelEdit();
        update({ stale: snapshot.error });
        report(snapshot.error);
      }
    });
    return () => {
      mounted.current = false;
      unsubscribe();
      cancelEdit();
      requestId.current++;
      request.current?.abort();
    };
  }, [workspace, scopeUi, isCurrent]);
  useLayoutEffect(() => {
    if (model.open && model.picker && model.loaded) search.current?.focus();
    else if (model.open && !model.picker) operatorInput.current?.focus();
  }, [model.open, model.picker, model.loaded, model.fieldId]);

  async function loadFields() {
    const ticket = ++requestId.current;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    update({ loading: true, catalogueError: '' });
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch('/cohort-builder/fields?' + new URLSearchParams({ workspace }), {
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok)
        throw new Error(
          typeof payload.detail === 'string' ? payload.detail : 'Clinical fields are unavailable.',
        );
      if (!live() || ticket !== requestId.current) return;
      const state = current.current;
      update({
        fields: payload.fields || [],
        loaded: true,
        loading: false,
        catalogueFingerprint: payload.fingerprint,
        fingerprint:
          !state.rules.length || !state.fingerprint ? payload.fingerprint : state.fingerprint,
      });
    } catch (error) {
      if (live() && ticket === requestId.current)
        update({
          loading: false,
          catalogueError:
            error.name === 'AbortError' ? 'Loading clinical fields timed out.' : error.message,
        });
    } finally {
      clearTimeout(timeout);
    }
  }
  function valueDefaults(field, operator) {
    return field?.kind === 'number' &&
      operator === 'between' &&
      field.observed_range?.length === 2 &&
      field.observed_range.every(Number.isFinite) &&
      field.observed_range[0] < field.observed_range[1]
      ? field.observed_range.map(String)
      : ['', ''];
  }
  function chooseField(fieldId) {
    const field = current.current.fields.find((item) => item.id === fieldId);
    if (!field || current.current.stale) return;
    const operator =
      field.is_recorded_age && field.operators.includes('between') ? 'between' : field.operators[0];
    update({
      fieldId,
      picker: false,
      operator,
      inputs: valueDefaults(field, operator),
      values: [],
      validation: '',
    });
    if (noValue(operator)) scheduleEdit();
  }
  async function toggleEditor() {
    if (current.current.stale) return;
    if (editTimer.current !== null) {
      cancelEdit();
      commitEdit();
    }
    const open = !(current.current.open && current.current.picker);
    update({ open });
    if (!open) return;
    update({
      editing: null,
      fieldId: '',
      group: '',
      query: '',
      values: [],
      picker: true,
      validation: '',
    });
    report();
    if (!current.current.loaded) await loadFields();
  }
  async function editRule(index) {
    if (current.current.stale) return;
    cancelEdit();
    update({ editing: index });
    if (!current.current.loaded) await loadFields();
    if (!live() || current.current.stale || current.current.editing === null) return;
    const rule = current.current.rules[index];
    if (!rule) return;
    update({
      fieldId: rule.field_id,
      operator: rule.operator,
      open: true,
      picker: false,
      validation: '',
      inputs:
        rule.operator === 'in'
          ? ['', '']
          : [String(rule.values[0] ?? ''), String(rule.values[1] ?? '')],
      values: rule.operator === 'in' ? rule.values.slice() : [],
    });
  }
  function removeRule(index) {
    if (current.current.stale) return;
    cancelEdit();
    update({
      editing: null,
      open: false,
      rules: current.current.rules.filter((_, i) => i !== index),
      labels: current.current.labels.filter((_, i) => i !== index),
    });
    report();
  }
  function scheduleEdit(delay = 350) {
    cancelEdit();
    if (!live() || current.current.stale || !selected()) return;
    report('Finish editing the clinical filter.');
    editTimer.current = setTimeout(commitEdit, delay);
  }
  function commitEdit() {
    editTimer.current = null;
    const state = current.current,
      field = selected();
    if (!live() || state.stale || !field) return;
    try {
      const inputs = state.inputs.slice(0, state.operator === 'between' ? 2 : 1);
      const raw =
        state.operator === 'in'
          ? [...state.values, ...inputs.filter((value) => String(value).trim())]
          : inputs;
      if (state.operator === 'in' && !raw.length) {
        const rules = state.rules.filter((_, index) => index !== state.editing);
        update({ rules, editing: null, validation: '' });
        report();
        return;
      }
      const values = parseClinicalFilterValues(field.kind, state.operator, raw);
      if (state.editing === null && state.rules.length >= 20)
        throw new Error('Use at most 20 clinical filters.');
      const rules = state.rules.slice(),
        editing = state.editing ?? rules.length;
      rules[editing] = { field_id: field.id, operator: state.operator, values };
      update({ rules, editing, validation: '' });
      report();
    } catch (error) {
      update({ validation: error.message });
      report(error.message);
    }
  }
  function changeOperator(operator) {
    cancelEdit();
    const inputs = valueDefaults(selected(), operator);
    update({ operator, inputs, values: [], validation: '' });
    if (
      noValue(operator) ||
      inputs.slice(0, operator === 'between' ? 2 : 1).every((value) => value !== '')
    )
      scheduleEdit();
    else report();
  }
  function inputValue(index, value, delay = 350) {
    const inputs = current.current.inputs.slice();
    inputs[index] = value;
    update({ inputs });
    if (current.current.operator !== 'in') scheduleEdit(delay);
  }
  function addValue(value = current.current.inputs[0]) {
    try {
      const values = [
        ...new Set([
          ...current.current.values,
          ...parseClinicalFilterValues(selected().kind, 'in', [value]),
        ]),
      ];
      update({ values, inputs: ['', ''], validation: '' });
      scheduleEdit(0);
    } catch (error) {
      update({ validation: error.message });
    }
  }
  function toggleValue(value) {
    if (current.current.operator !== 'in') {
      inputValue(0, String(value), 0);
      return;
    }
    if (current.current.values.includes(value)) {
      update({ values: current.current.values.filter((item) => item !== value) });
      scheduleEdit(0);
    } else addValue(String(value));
  }
  function reload() {
    cancelEdit();
    requestId.current++;
    request.current?.abort();
    scopeUi.setValidation('clinical', '');
    scopeUi.patch({ clinical_filters: [], fingerprint: '', clinical_labels: [] });
    update(initialState(scopeUi.getDraft()));
  }

  return {
    model,
    current,
    editTimer,
    search,
    operatorInput,
    suggestions,
    update,
    cancelEdit,
    report,
    loadFields,
    chooseField,
    toggleEditor,
    editRule,
    removeRule,
    scheduleEdit,
    changeOperator,
    inputValue,
    addValue,
    toggleValue,
    reload,
  };
}
