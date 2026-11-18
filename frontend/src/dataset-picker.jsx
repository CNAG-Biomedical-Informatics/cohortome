import React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';

function Trait({ trait, decorative = false }) {
  // SVGs come only from the application's fixed icon catalogue, never metadata.
  return (
    <span
      className={`dataset-trait-icon dataset-trait-icon-${trait.key}`}
      data-dataset-trait={trait.key}
      role={decorative ? undefined : 'img'}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : trait.label}
      title={decorative ? undefined : trait.label}
      dangerouslySetInnerHTML={{ __html: trait.svg }}
    />
  );
}

export function createDatasetPickerView(host, legendHost, onChange) {
  const root = createRoot(host);
  return {
    render({ datasets, legend, desktop }) {
      legendHost?.classList.toggle('is-hidden', !legend.length);
      root.render(
        <>
          {!datasets.length && <div className="empty">No dataset available.</div>}
          {datasets.map((d) => (
            <label
              key={d.id}
              data-dataset-card={d.id}
              className={`dataset-picker-card${d.checked ? ' is-selected' : ''}${d.active ? ' is-active' : ''}${d.checked && !d.active ? ' is-pending-add' : ''}${d.active && !d.checked ? ' is-pending-removal' : ''}`}
            >
              <input
                type="checkbox"
                data-dataset-checkbox={d.id}
                checked={d.checked}
                onChange={(event) => onChange(d.id, event.target.checked)}
              />
              <div>
                <div className="dataset-picker-title">
                  <span>{d.name}</span>
                  {d.active && (
                    <span className="dataset-picker-state dataset-picker-state-active">Active</span>
                  )}
                  {d.checked && !d.active && (
                    <span className="dataset-picker-state dataset-picker-state-pending">
                      Pending add
                    </span>
                  )}
                  {d.active && !d.checked && (
                    <span className="dataset-picker-state dataset-picker-state-removal">
                      Pending removal
                    </span>
                  )}
                  {d.checked && !d.store.ready && (
                    <span className="dataset-picker-state dataset-picker-state-removal">
                      {d.store.status.replaceAll('_', ' ')}
                    </span>
                  )}
                  <button
                    type="button"
                    className="query-chip secondary-btn dataset-about-button"
                    data-dataset-about={d.id}
                    aria-label={`About ${d.name}`}
                  >
                    <span aria-hidden="true">ⓘ</span> About
                  </button>
                </div>
                {!!d.traits.length && (
                  <div className="dataset-trait-icons">
                    {d.traits.map((trait) => (
                      <Trait key={trait.key} trait={trait} />
                    ))}
                  </div>
                )}
                <div className="dataset-picker-meta">
                  <span className="dataset-picker-tag">{d.id}</span>
                  <span className="dataset-picker-tag">{d.access}</span>
                  {d.tags.map((tag, index) => (
                    <span key={index} className="dataset-picker-tag dataset-picker-tag-content">
                      {tag}
                    </span>
                  ))}
                  {!desktop && !!d.groups.length && (
                    <span className="dataset-picker-tag">groups: {d.groups.join(', ')}</span>
                  )}
                  {!desktop && !!d.users.length && (
                    <span className="dataset-picker-tag">users: {d.users.join(', ')}</span>
                  )}
                </div>
                {d.description && (
                  <div className="dataset-picker-description" title={d.description}>
                    {d.description}
                  </div>
                )}
              </div>
            </label>
          ))}
          {legendHost &&
            createPortal(
              legend.length ? (
                <>
                  <span className="dataset-trait-legend-title">Legend</span>
                  {legend.map((trait) => (
                    <span
                      key={trait.key}
                      className="dataset-trait-legend-item"
                      data-dataset-trait-legend={trait.key}
                    >
                      <Trait trait={trait} decorative />
                      <span>{trait.legendLabel}</span>
                    </span>
                  ))}
                </>
              ) : null,
              legendHost,
            )}
        </>,
      );
    },
  };
}
