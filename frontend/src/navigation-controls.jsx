import React, { useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

const sections = [
  ['general', 'General'],
  ['appearance', 'Appearance & plots'],
  ['query', 'Query & AI'],
  ['analysis', 'Analysis & Pheno-Ranker'],
  ['jobs', 'Jobs & storage'],
  ['about', 'Account & About'],
];
export function createSettingsNavigation(host) {
  const root = createRoot(host);
  return {
    render(selected, onSelect) {
      flushSync(() =>
        root.render(
          sections.map(([id, label]) => (
            <button
              key={id}
              type="button"
              data-settings-section={id}
              aria-current={id === selected ? 'page' : undefined}
              onClick={() => onSelect(id)}
            >
              {label}
            </button>
          )),
        ),
      );
    },
  };
}

function ChatResize({ workbench }) {
  const divider = useRef(null),
    drag = useRef(null),
    width = useRef(232),
    preferred = useRef(232);
  const [size, setSize] = useState({ width: 232, maximum: 420 });
  function setWidth(value) {
    const maximum = Math.max(200, Math.min(420, (workbench.clientWidth || 920) - 500));
    width.current = Math.round(Math.max(200, Math.min(maximum, value)));
    workbench.style.setProperty('--chat-sidebar-width', `${width.current}px`);
    setSize({ width: width.current, maximum });
  }
  function persist() {
    preferred.current = width.current;
    try {
      localStorage.setItem('cohortome.chatSidebarWidth', String(width.current));
    } catch (_) {
      /* Storage is optional. */
    }
  }
  function finish() {
    if (!drag.current) return;
    drag.current = null;
    workbench.classList.remove('is-resizing-chats');
    persist();
  }
  useLayoutEffect(() => {
    let saved = 232;
    try {
      saved = Number(localStorage.getItem('cohortome.chatSidebarWidth')) || saved;
    } catch (_) {
      /* Storage is optional. */
    }
    preferred.current = Number.isFinite(saved) ? saved : 232;
    setWidth(preferred.current);
    const resize = () => setWidth(preferred.current);
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      workbench.classList.remove('is-resizing-chats');
    };
  }, [workbench]);
  return (
    <div
      ref={divider}
      className="chat-width-divider"
      tabIndex={0}
      role="separator"
      aria-orientation="vertical"
      aria-label="Chats width"
      aria-controls="analysisChatDock"
      aria-valuemin={200}
      aria-valuemax={size.maximum}
      aria-valuenow={size.width}
      title="Drag to resize Chats. Use arrow keys when focused."
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        drag.current = { x: event.clientX, width: width.current };
        event.currentTarget.setPointerCapture(event.pointerId);
        event.currentTarget.focus();
        workbench.classList.add('is-resizing-chats');
        event.preventDefault();
      }}
      onPointerMove={(event) => {
        if (drag.current) setWidth(drag.current.width + event.clientX - drag.current.x);
      }}
      onPointerUp={finish}
      onPointerCancel={finish}
      onLostPointerCapture={finish}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 25 : 10;
        const values = {
          ArrowLeft: width.current - step,
          ArrowRight: width.current + step,
          Home: 200,
          End: 420,
        };
        if (!(event.key in values)) return;
        event.preventDefault();
        setWidth(values[event.key]);
        persist();
      }}
    />
  );
}
export function mountChatResize(workbench, sidebar) {
  // The host has no layout box, so the separator stays in the existing grid slot.
  const host = document.createElement('div');
  host.style.display = 'contents';
  sidebar.after(host);
  const root = createRoot(host);
  flushSync(() => root.render(<ChatResize workbench={workbench} />));
}
