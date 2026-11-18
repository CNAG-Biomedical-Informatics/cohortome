import { useSyncExternalStore } from 'react';

export function ScopeBar({ scopeUi, className, previewLabel }) {
  const snapshot = useSyncExternalStore(scopeUi.subscribe, scopeUi.getSnapshot);
  const { chips, scopeLabel, dirty, busy, hasValidation, canApply } = snapshot;
  const issue = snapshot.error || snapshot.validation;
  return (
    <div className={['cohort-scope-bar', className].filter(Boolean).join(' ')}>
      <details className="cohort-filter-basket">
        <summary>
          {chips.length} {chips.length === 1 ? 'filter' : 'filters'}
        </summary>
        <div className="cohort-scope-filters" aria-label="Shared draft filters">
          {chips.length ? (
            chips.map((chip) => (
              <button
                key={`${chip.field}:${chip.index ?? ''}`}
                type="button"
                className="query-chip"
                data-scope-field={chip.field}
                data-scope-index={chip.index}
                aria-label={`Remove filter: ${chip.label}`}
                onClick={() => scopeUi.removeFilter(chip)}
              >
                {chip.label} <span aria-hidden="true">×</span>
              </button>
            ))
          ) : (
            <span className="section-note">No filters</span>
          )}
        </div>
      </details>
      <div className="cohort-scope-actions">
        <strong className="cohort-scope-state" aria-live="polite">
          {previewLabel || scopeLabel}
        </strong>
        <span className="cohort-scope-pending" hidden={!dirty}>
          Unapplied changes
        </span>
        <button
          type="button"
          className="primary-btn"
          data-scope-apply=""
          disabled={!canApply}
          onClick={() => void scopeUi.apply()}
        >
          {busy ? 'Applying…' : 'Apply to scope'}
        </button>
        <button
          type="button"
          className="query-chip"
          data-scope-discard=""
          hidden={!dirty && !hasValidation}
          disabled={busy}
          onClick={scopeUi.discard}
        >
          Discard changes
        </button>
        <button
          type="button"
          className="query-chip"
          data-scope-clear=""
          hidden={!chips.length}
          onClick={scopeUi.clearDraft}
        >
          Clear filters
        </button>
      </div>
      <p className="cohort-scope-message" role="status" hidden={!issue}>
        {issue}
      </p>
    </div>
  );
}

export function SaveIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 3h12l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8" />
    </svg>
  );
}

export function DiseaseChips({
  diseases,
  selected,
  showAll,
  onSelect,
  onToggle,
  multipleLabel = 'Matching any selected disease',
  title,
}) {
  const items = showAll
    ? diseases
    : diseases.filter((item, index) => index < 8 || selected.has(item.disease));
  return (
    <>
      <button
        type="button"
        className="query-chip query-chip-deterministic"
        data-disease=""
        aria-pressed={!selected.size}
        onClick={() => onSelect('')}
      >
        All diseases
      </button>
      {items.map((item) => (
        <button
          key={item.disease}
          type="button"
          className="query-chip query-chip-deterministic"
          data-disease={item.disease}
          title={title}
          aria-pressed={selected.has(item.disease)}
          onClick={() => onSelect(item.disease)}
        >
          {item.disease} <span className="query-chip badge">{Number(item.patient_count) || 0}</span>
        </button>
      ))}
      {diseases.length > 8 && (
        <button
          type="button"
          className="query-chip"
          data-more-diseases=""
          aria-expanded={showAll}
          onClick={onToggle}
        >
          {showAll ? 'Show fewer' : 'More diseases…'}
        </button>
      )}
      {selected.size > 1 && <span className="section-note">{multipleLabel}</span>}
    </>
  );
}
