import React, { useLayoutEffect, useRef, useState } from 'react';
import { renderSupplemental, resetSupplementalView } from './shared/view-root.js';

export function openImagingDialog(url, trigger) {
  const host = document.createElement('div');
  document.body.append(host);
  const close = () => {
    resetSupplementalView(host);
    host.remove();
    if (trigger?.isConnected) trigger.focus();
  };
  function Viewer() {
    const dialog = useRef(null),
      button = useRef(null);
    useLayoutEffect(() => {
      dialog.current.showModal();
      button.current.focus();
    }, []);
    return (
      <dialog ref={dialog} className="local-imaging-viewer" onClose={close}>
        <button ref={button} type="button" onClick={() => dialog.current.close()}>
          Close viewer
        </button>
        <iframe title="OHIF imaging viewer" src={url} />
      </dialog>
    );
  }
  renderSupplemental(host, <Viewer />);
}
export function mountJobNotice(message, onView) {
  const host = document.createElement('div');
  host.className = 'job-completion-notice';
  document.body.append(host);
  const close = () => {
    resetSupplementalView(host);
    host.remove();
  };
  renderSupplemental(
    host,
    <>
      <span role="status">{message}</span>
      <button
        type="button"
        onClick={() => {
          onView();
          close();
        }}
      >
        View runs
      </button>
      <button type="button" onClick={close}>
        Dismiss
      </button>
    </>,
  );
  return close;
}
export function renderDismissibleNotice(host, message, onDismiss) {
  renderSupplemental(
    host,
    <>
      <span>{message}</span>{' '}
      <button type="button" className="query-chip" onClick={onDismiss}>
        Dismiss
      </button>
    </>,
  );
}
export function renderNewChatGuidance(host, onNew) {
  renderSupplemental(
    host,
    <>
      <div>
        To work with the current data, start a new chat and select your cohorts and assay again.
        Your previous chat and results are kept.
      </div>{' '}
      <button type="button" className="query-chip" onClick={onNew}>
        New chat with current data
      </button>
    </>,
  );
}
function Restore({ restore, reopen, scope }) {
  const [status, setStatus] = useState(''),
    [error, setError] = useState('');
  async function load() {
    setStatus('loading');
    setError('');
    try {
      await restore(scope);
      await reopen();
      setStatus('done');
    } catch (error) {
      setStatus('retry');
      setError(error.message || 'The original workspace is unavailable.');
    }
  }
  if (status === 'done') return null;
  return (
    <>
      {' '}
      <button type="button" className="query-chip" disabled={status === 'loading'} onClick={load}>
        {status === 'loading'
          ? 'Loading datasets…'
          : status === 'retry'
            ? 'Retry loading datasets'
            : 'Load this chat’s datasets'}
      </button>
      {error && (
        <span data-restore-error="true" role="status">
          {error}
        </span>
      )}
    </>
  );
}
export function renderWorkspaceRestore(host, model) {
  renderSupplemental(host, <Restore {...model} />);
}
export function renderExampleToggle(host, container, count) {
  function Toggle() {
    const [collapsed, setCollapsed] = useState(true);
    return (
      <button
        type="button"
        className="query-chip query-chip-toggle"
        onClick={() => {
          container.classList.toggle('is-collapsed', !collapsed);
          setCollapsed(!collapsed);
        }}
      >
        {collapsed ? `See more (${count})` : 'Show fewer'}
      </button>
    );
  }
  renderSupplemental(host, <Toggle />);
}
