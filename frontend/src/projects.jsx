import React, { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

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
export function ProjectControls({ viewRef }) {
  const [model, setModel] = useState(null);
  const [visible, setVisible] = useState(false);
  const button = useRef(null),
    menu = useRef(null);
  useLayoutEffect(() => {
    viewRef.current = { render: setModel, open: () => setVisible(true) };
    return () => {
      viewRef.current = null;
    };
  }, [viewRef]);
  useLayoutEffect(() => {
    if (!visible) return;
    const panel = menu.current,
      bounds = button.current.getBoundingClientRect();
    panel.style.left =
      Math.max(8, Math.min(bounds.right + 8, innerWidth - panel.offsetWidth - 8)) + 'px';
    panel.style.bottom =
      Math.max(8, Math.min(innerHeight - bounds.bottom, innerHeight - panel.offsetHeight - 8)) +
      'px';
    panel.querySelector('#saveProjectBtn').focus();
    const outside = (e) => {
      if (!panel.contains(e.target) && !button.current.contains(e.target)) setVisible(false);
    };
    const escape = (e) => {
      if (e.key === 'Escape') {
        setVisible(false);
        button.current.focus();
      }
    };
    const resize = () => setVisible(false);
    document.addEventListener('click', outside);
    document.addEventListener('keydown', escape);
    window.addEventListener('resize', resize);
    return () => {
      document.removeEventListener('click', outside);
      document.removeEventListener('keydown', escape);
      window.removeEventListener('resize', resize);
    };
  }, [visible]);
  if (!model) return null;
  return (
    <>
      <button
        type="button"
        id="projectsMenuBtn"
        className="rail-projects"
        ref={button}
        aria-expanded={visible}
        aria-controls="projectsMenu"
        aria-haspopup="dialog"
        title="Projects — save or open"
        aria-label="Projects — save or open"
        onClick={() => setVisible(!visible)}
      >
        <Icon kind="save" />
      </button>
      {createPortal(
        <div
          id="projectsMenu"
          className="account-menu app-project-menu"
          role="dialog"
          aria-label="Projects"
          ref={menu}
          hidden={!visible}
        >
          <Menu {...model} />
        </div>,
        document.body,
      )}
    </>
  );
}
