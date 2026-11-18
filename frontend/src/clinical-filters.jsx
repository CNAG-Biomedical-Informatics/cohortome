import { useClinicalFilters } from './clinical-filters/use-clinical-filters.js';
import {
  clinicalOperators as operators,
  clinicalNoValue as noValue,
  clinicalRuleLabel,
} from '../../static/js/clinical_filters.js';
export function ClinicalFilters(props) {
  const {
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
  } = useClinicalFilters(props);
  const field = model.fields.find((item) => item.id === model.fieldId);
  const categories = [
    ...new Set(model.fields.map((item) => item.group || 'Clinical fields')),
  ].sort();
  const choices = model.fields.filter(
    (item) =>
      (!model.group || (item.group || 'Clinical fields') === model.group) &&
      `${item.label} ${item.unit} ${item.dataset_labels.join(' ')}`
        .toLocaleLowerCase()
        .includes(model.query.trim().toLocaleLowerCase()),
  );
  const range =
    field?.kind === 'number' &&
    model.operator === 'between' &&
    field.observed_range?.length === 2 &&
    field.observed_range.every(Number.isFinite) &&
    field.observed_range[0] < field.observed_range[1]
      ? field.observed_range
      : null;
  const type = field?.kind === 'number' ? 'number' : field?.kind === 'date' ? 'date' : 'text';
  const valueInput = (label, index) => (
    <label key={label}>
      {label}
      {field?.kind === 'boolean' ? (
        <select
          data-clinical-value=""
          aria-label={label}
          disabled={!!model.stale}
          value={model.inputs[index]}
          onChange={(event) => inputValue(index, event.target.value, 0)}
        >
          <option value="">Choose…</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      ) : (
        <input
          type={type}
          aria-label={label}
          data-clinical-value=""
          disabled={!!model.stale}
          step={type === 'number' ? 'any' : undefined}
          list={type === 'text' ? suggestions : undefined}
          value={model.inputs[index]}
          onChange={(event) => inputValue(index, event.target.value)}
        />
      )}
    </label>
  );
  return (
    <>
      <div className="clinical-filter-toolbar">
        <button
          type="button"
          className="query-chip clinical-filter-add"
          aria-expanded={model.open}
          disabled={!!model.stale}
          onClick={toggleEditor}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            aria-hidden="true"
          >
            <path d="M4 5h16M7 12h10M10 19h4" />
          </svg>
          Add clinical filter
        </button>
        <button
          type="button"
          className="query-chip clinical-filter-clear"
          hidden={!model.rules.length && !editTimer.current}
          disabled={!!model.stale}
          onClick={() => {
            cancelEdit();
            update({ rules: [], labels: [], editing: null, open: false });
            report();
          }}
        >
          Clear clinical filters
        </button>
      </div>
      <div className="clinical-filter-rules" aria-label="Active clinical filters">
        {model.rules.map((rule, index) => {
          const source = model.fields.find((item) => item.id === rule.field_id);
          const label = source
            ? clinicalRuleLabel(rule, source)
            : model.labels[index] || 'Clinical filter';
          return (
            <span
              className="clinical-filter-chip"
              key={index}
              title={source?.dataset_labels.join(', ') || ''}
            >
              <button
                type="button"
                className="query-chip"
                data-edit-clinical={index}
                disabled={!!model.stale}
                aria-label={`Edit clinical filter: ${label}`}
                onClick={() => editRule(index)}
              >
                {label} <span aria-hidden="true">✎</span>
              </button>
              <button
                type="button"
                className="query-chip"
                data-remove-clinical={index}
                disabled={!!model.stale}
                aria-label={`Remove clinical filter: ${label}`}
                onClick={() => removeRule(index)}
              >
                ×
              </button>
            </span>
          );
        })}
      </div>
      <div className="clinical-filter-editor" hidden={!model.open}>
        <div className="clinical-filter-catalogue-status" role="status">
          {model.loading ? (
            'Loading clinical fields…'
          ) : model.catalogueError ? (
            <>
              <span>{model.catalogueError}</span>{' '}
              <button type="button" className="query-chip" onClick={loadFields}>
                Retry
              </button>
            </>
          ) : model.loaded && !model.fields.length ? (
            'No supported clinical fields are available in this workspace.'
          ) : (
            ''
          )}
        </div>
        <div
          className="clinical-filter-controls"
          hidden={!model.loaded || !model.fields.length || model.loading || !!model.catalogueError}
        >
          <div className="clinical-filter-picker" hidden={!model.picker}>
            <div className="clinical-filter-picker-heading">
              <strong>Choose a field</strong>
              <input
                ref={search}
                type="search"
                className="clinical-filter-search"
                aria-label="Search clinical fields"
                placeholder="Search fields…"
                value={model.query}
                onChange={(event) => update({ query: event.target.value })}
              />
            </div>
            <div className="clinical-filter-groups" aria-label="Clinical field categories">
              {['', ...categories].map((group) => (
                <button
                  type="button"
                  className="query-chip"
                  key={group}
                  data-field-group={group}
                  aria-pressed={model.group === group}
                  onClick={() => update({ group })}
                >
                  {group || 'All fields'}{' '}
                  <span className="badge">
                    {
                      model.fields.filter(
                        (item) => !group || (item.group || 'Clinical fields') === group,
                      ).length
                    }
                  </span>
                </button>
              ))}
            </div>
            <div className="clinical-filter-browse">
              {choices.length ? (
                choices.map((item) => (
                  <button
                    type="button"
                    className="clinical-filter-field-card"
                    key={item.id}
                    data-field-id={item.id}
                    aria-pressed={item.id === model.fieldId}
                    disabled={!!model.stale}
                    onClick={() => chooseField(item.id)}
                  >
                    <strong>{item.label}</strong>
                    <small>{[item.unit, ...item.dataset_labels].filter(Boolean).join(' · ')}</small>
                  </button>
                ))
              ) : (
                <p className="section-note">No matching fields.</p>
              )}
            </div>
          </div>
          <form
            className="clinical-filter-form"
            hidden={model.picker || !field}
            onSubmit={(event) => {
              event.preventDefault();
              if (model.operator === 'in' && model.inputs[0].trim()) addValue();
              else scheduleEdit(0);
            }}
          >
            <div className="clinical-filter-picker-heading">
              <strong className="clinical-filter-selected-name">{field?.label || ''}</strong>
              <button
                type="button"
                className="query-chip clinical-filter-change"
                disabled={!!model.stale}
                onClick={() => {
                  cancelEdit();
                  update({ editing: null, picker: true, validation: '' });
                  report();
                }}
              >
                Change field
              </button>
            </div>
            <p className="clinical-filter-source section-note">
              {field
                ? `Available in: ${field.dataset_labels.join(', ')}${field.unit ? ' · ' + field.unit : ''}${field.observed_range ? ' · Recorded range: ' + field.observed_range.join('–') + ' (any visit; not a reference range)' : ''}`
                : ''}
            </p>
            <div className="clinical-filter-value-row">
              <label>
                Operator
                <select
                  ref={operatorInput}
                  className="clinical-filter-operator"
                  aria-label="Operator"
                  disabled={!!model.stale}
                  value={model.operator}
                  onChange={(event) => changeOperator(event.target.value)}
                >
                  {(field?.operators || []).map((operator) => (
                    <option key={operator} value={operator}>
                      {operators[operator] || operator}
                    </option>
                  ))}
                </select>
              </label>
              <div className="clinical-filter-values">
                {!noValue(model.operator) && (
                  <>
                    {valueInput('Value', 0)}
                    {model.operator === 'between' && valueInput('Upper value', 1)}
                    {model.operator === 'in' && (
                      <>
                        <button
                          type="button"
                          className="query-chip clinical-filter-add-value"
                          disabled={!!model.stale}
                          onClick={() => addValue()}
                        >
                          Add value
                        </button>
                        <span className="clinical-filter-draft-values">
                          {model.values.map((value, index) => (
                            <button
                              type="button"
                              className="query-chip"
                              key={String(value)}
                              data-draft={index}
                              disabled={!!model.stale}
                              aria-label={`Remove value ${value}`}
                              onClick={() => toggleValue(value)}
                            >{`${value} ×`}</button>
                          ))}
                        </span>
                      </>
                    )}
                    <datalist id={suggestions}>
                      {(field?.options || []).slice(0, 50).map((value) => (
                        <option key={String(value)} value={String(value)} />
                      ))}
                    </datalist>
                    {range && (
                      <div className="clinical-range">
                        {['Minimum', 'Maximum'].map((label, index) => (
                          <label key={label}>
                            {label}
                            <input
                              type="range"
                              aria-label={`${label} range`}
                              min={range[0]}
                              max={range[1]}
                              step="any"
                              disabled={!!model.stale}
                              value={
                                model.inputs[index] === '' ? range[index] : model.inputs[index]
                              }
                              onChange={(event) => {
                                const other = Number(current.current.inputs[1 - index]);
                                let value = Number(event.target.value);
                                if (Number.isFinite(other))
                                  value = index ? Math.max(value, other) : Math.min(value, other);
                                inputValue(index, String(Math.round(value * 100) / 100));
                              }}
                            />
                          </label>
                        ))}
                      </div>
                    )}
                    {field?.kind === 'string' && !!field.options?.length && (
                      <div className="clinical-filter-recorded-values">
                        <small>Recorded choices (up to 50)</small>
                        {field.options.slice(0, 50).map((value, index) => (
                          <button
                            type="button"
                            className="query-chip"
                            key={String(value)}
                            data-value-index={index}
                            disabled={!!model.stale}
                            aria-pressed={
                              model.operator === 'in'
                                ? model.values.includes(value)
                                : model.inputs[0] === String(value)
                            }
                            onClick={() => toggleValue(value)}
                          >
                            {String(value)}
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
            <div className="clinical-filter-validation" role="alert">
              {model.validation}
            </div>
          </form>
          <details className="clinical-filter-help">
            <summary>How clinical filters work</summary>
            <p>
              Recorded at any visit. All filters must match; they may match different visits.
              Missing fields in other datasets are not included. Recorded ranges are not clinical
              reference ranges.
            </p>
          </details>
        </div>
      </div>
      <div className="clinical-filter-status" role="status">
        {model.stale && (
          <>
            <span>{model.stale}</span>{' '}
            <button type="button" className="query-chip" onClick={reload}>
              Reload clinical filters
            </button>
          </>
        )}
      </div>
    </>
  );
}
