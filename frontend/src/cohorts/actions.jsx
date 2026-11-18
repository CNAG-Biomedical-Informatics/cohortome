import React from 'react';
export function Icon({ name }) {
  const path = {
    download: 'M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5',
    inspect: 'M3 10h18M9 10v10',
    'clinical-summary': 'M4 3v17h17M8 16v-4M13 16V7M18 16v-7',
    'load-analysis': 'M4 3v17h17M8 16v-4M13 16V7M18 16v-7',
    'load-datasets': 'M3 7h7l2 2h9v11H3ZM3 7V4h7l2 3h8v2',
    rename: 'm16 3 5 5-12 12H4v-5ZM14 5l5 5',
    delete: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  };
  return (
    <span className="button-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {path[name] && <path d={path[name]} />}
        {name === 'inspect' && <rect x="3" y="4" width="18" height="16" rx="2" />}
        {name === 'cohort' && (
          <>
            <circle cx="9" cy="7" r="3" />
            <path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3" />
          </>
        )}
        {name === 'load-pheno' && (
          <>
            <circle cx="5" cy="6" r="3" />
            <circle cx="18" cy="7" r="3" />
            <circle cx="10" cy="19" r="3" />
            <path d="m8 6 7 1M6 9l3 7m7-6-4 6" />
          </>
        )}
        {name === 'more' && [5, 12, 19].map((x) => <circle key={x} cx={x} cy="12" r="1" />)}
      </svg>
    </span>
  );
}

export function Action({
  item,
  action,
  children,
  disabled = false,
  icons = false,
  className = '',
  title,
}) {
  return (
    <button
      type="button"
      className={`query-chip ${action === 'delete' ? 'danger-btn' : ''} ${className}`}
      data-saved-cohort-id={item.id}
      data-saved-cohort-action={action}
      disabled={disabled}
      title={title}
    >
      {(icons || action.startsWith('export')) && (
        <Icon name={action.startsWith('export') ? 'download' : action} />
      )}{' '}
      {children}
    </button>
  );
}

export function Exports({ item }) {
  return (
    <>
      <Action item={item} action="export-clinical">
        Export clinical data
      </Action>
      <Action item={item} action="export-molecular">
        Export molecular data
      </Action>
      <Action
        item={item}
        action="export"
        title="Membership TSV and metadata JSON only; no clinical records or assay matrices"
      >
        Export membership
      </Action>
    </>
  );
}
