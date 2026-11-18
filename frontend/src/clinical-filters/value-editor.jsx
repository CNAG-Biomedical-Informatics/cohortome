import {
  clinicalOperators as operators,
  clinicalNoValue as noValue,
} from '../../../static/js/clinical_filters.js';

export function ClinicalValueEditor({
  field,
  model,
  current,
  operatorInput,
  suggestions,
  changeOperator,
  inputValue,
  addValue,
  toggleValue,
}) {
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
                      value={model.inputs[index] === '' ? range[index] : model.inputs[index]}
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
  );
}
