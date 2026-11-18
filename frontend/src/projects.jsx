import React, { useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

const paths = {
  save: 'M5 3h12l4 4v14H3V3h2Zm2 0v7h10V3M7 21v-7h10v7',
  open: 'M3 7V4h6l2 3h10v13H3V7Zm0 3h18',
};
function Icon({ kind }) {
  return (
    <span className="button-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      >
        <path d={paths[kind]} />
      </svg>
    </span>
  );
}
function Menu({ busy, status, onSave, onOpen, onFile }) {
  const file = useRef(null);
  return (
    <>
      <p className="app-nav-heading">Projects</p>
      <p className="app-project-hint">
        Save or reopen your working state. Data files are not included.
      </p>
      <button
        type="button"
        id="saveProjectBtn"
        className="app-sidebar-settings"
        disabled={busy}
        onClick={onSave}
      >
        <Icon kind="save" />
        Save project…
      </button>
      <button
        type="button"
        id="openProjectBtn"
        className="app-sidebar-settings"
        disabled={busy}
        onClick={() => onOpen(() => file.current.click())}
      >
        <Icon kind="open" />
        Open project…
      </button>
      <p role="status" className="app-project-status">
        {status}
      </p>
      <input
        ref={file}
        type="file"
        accept=".cohortome,application/json"
        hidden
        onChange={(e) => {
          const selected = e.target.files[0];
          e.target.value = '';
          if (selected) onFile(selected);
        }}
      />
    </>
  );
}
export function createProjectsView(toggle, menu) {
  const iconRoot = createRoot(toggle),
    menuRoot = createRoot(menu);
  flushSync(() => iconRoot.render(<Icon kind="save" />));
  return { render: (m) => flushSync(() => menuRoot.render(<Menu {...m} />)) };
}
