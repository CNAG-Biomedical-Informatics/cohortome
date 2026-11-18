import React, { useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';

const permissions = {
  blocked: 'Blocked',
  safe_summary: 'Summary only',
  detailed_allowed: 'Detailed context',
};

function DatasetConfirmation({ kind, datasets, skipped = 0, onApply, onReload, dispose }) {
  const dialog = useRef(null),
    input = useRef(null),
    inFlight = useRef(false);
  const [busy, setBusy] = useState(false),
    [status, setStatus] = useState('');
  const [permission, setPermission] = useState('blocked'),
    [confirmation, setConfirmation] = useState('');
  const [removeFiles, setRemoveFiles] = useState(false),
    [invalid, setInvalid] = useState(false),
    [complete, setComplete] = useState(false);
  const removal = kind === 'remove',
    rebuild = kind === 'rebuild',
    id = datasets[0]?.dataset_id;
  const title = removal
    ? `Remove ${datasets[0].name || id}?`
    : rebuild
      ? 'Rebuild query stores'
      : 'Change AI permissions';
  useLayoutEffect(() => {
    dialog.current.showModal();
    if (removal) input.current.focus();
  }, []);
  async function apply() {
    if (inFlight.current || complete) return;
    if (removal && confirmation.trim() !== id) {
      setInvalid(true);
      setStatus(`Enter the dataset ID exactly as shown: ${id}`);
      input.current.focus();
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setStatus(
      removal ? 'Removing dataset…' : rebuild ? 'Rebuilding query stores…' : 'Saving permissions…',
    );
    try {
      const result = await onApply(
        { confirmation: confirmation.trim(), remove_files: removeFiles, permission },
        setStatus,
      );
      if (result?.close) {
        dialog.current.close();
        return;
      }
      setStatus(result?.status || '');
      setComplete(!!result?.complete);
    } catch (error) {
      setStatus(error.message || 'Unable to complete this action.');
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="dataset-remove-dialog"
      aria-label={title}
      onClose={dispose}
      onCancel={(e) => {
        if (inFlight.current || (removal && complete)) e.preventDefault();
      }}
    >
      <h3>{title}</h3>
      {removal ? (
        <>
          <p>
            This removes the dataset from COHORTome and clears its prepared store. Saved chats,
            cohorts and results are kept, but references to this dataset will no longer load.
            Reimporting does not repair those references.
          </p>
          <label>
            <input
              type="checkbox"
              data-remove-files=""
              checked={removeFiles}
              disabled={busy || complete}
              onChange={(e) => setRemoveFiles(e.target.checked)}
            />{' '}
            Also move installer-managed files to the storage folder’s removed directory
            (recoverable).
          </label>
          <p>Other source folders are never removed. Active jobs must finish first.</p>
          <label>
            Type <strong>{id}</strong> to confirm
            <input
              ref={input}
              data-remove-confirm=""
              autoComplete="off"
              value={confirmation}
              disabled={busy || complete}
              aria-invalid={invalid || undefined}
              onChange={(e) => {
                setConfirmation(e.target.value);
                setInvalid(false);
                setStatus('');
              }}
            />
          </label>
        </>
      ) : (
        <>
          {rebuild && (
            <p>
              COHORTome will rebuild {datasets.length} dataset-local DuckDB{' '}
              {datasets.length === 1 ? 'index' : 'indexes'}, one at a time.
            </p>
          )}
          <ul>
            {datasets.map((d) => (
              <li key={d.dataset_id}>
                {d.name || d.dataset_id}
                {!rebuild &&
                  ` — ${permissions[d.ai_provider_access] || d.ai_provider_access || ''}`}
              </li>
            ))}
          </ul>
          {rebuild ? (
            !!skipped && (
              <p>
                {skipped} selected {skipped === 1 ? 'dataset is' : 'datasets are'} already ready or
                currently being prepared.
              </p>
            )
          ) : (
            <>
              <label>
                New permission{' '}
                <select
                  value={permission}
                  disabled={busy}
                  onChange={(e) => setPermission(e.target.value)}
                >
                  {Object.entries(permissions).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                Private datasets remain blocked from external providers. Classification and user
                access will not change.
              </p>
            </>
          )}
        </>
      )}
      <p role="status" {...(removal ? { 'data-remove-status': '' } : {})}>
        {status}
      </p>
      <div className="dataset-picker-actions">
        <button
          type="button"
          className="query-chip secondary-btn"
          {...(removal ? { 'data-remove-cancel': '' } : { 'data-cancel': '' })}
          disabled={busy}
          onClick={() => (removal && complete ? onReload() : dialog.current.close())}
        >
          {complete ? (removal ? 'Reload workspace' : 'Close') : 'Cancel'}
        </button>
        <button
          type="button"
          className={
            removal
              ? 'query-chip danger-btn danger-confirm'
              : rebuild
                ? 'primary-btn'
                : 'query-chip'
          }
          {...(removal ? { 'data-remove-submit': '' } : { 'data-apply': '' })}
          hidden={removal && complete}
          disabled={busy || complete}
          onClick={apply}
        >
          {removal
            ? 'Remove dataset'
            : rebuild
              ? `Rebuild ${datasets.length} ${datasets.length === 1 ? 'store' : 'stores'}`
              : `Apply to ${datasets.length} datasets`}
        </button>
      </div>
    </dialog>
  );
}

export function openDatasetConfirmation(options) {
  const host = document.createElement('div');
  document.body.append(host);
  const root = createRoot(host);
  const dispose = () =>
    queueMicrotask(() => {
      root.unmount();
      host.remove();
    });
  root.render(<DatasetConfirmation {...options} dispose={dispose} />);
}
