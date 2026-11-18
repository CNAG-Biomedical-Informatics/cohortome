import { useClinicalFilters } from './clinical-filters/use-clinical-filters.js';
import { clinicalRuleLabel } from '../../static/js/clinical_filters.js';
import { ClinicalValueEditor } from './clinical-filters/value-editor.jsx';
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
            <ClinicalValueEditor
              {...{
                field,
                model,
                current,
                operatorInput,
                suggestions,
                changeOperator,
                inputValue,
                addValue,
                toggleValue,
              }}
            />
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
