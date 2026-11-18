import React, { useLayoutEffect, useRef, useState } from 'react';

export function ChatsDrawer({ onNewChat, onChatSearch }) {
  const [choicesOpen, setChoicesOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const search = useRef(null);
  const searchButton = useRef(null);
  function closeSearch() {
    setSearchOpen(false);
    search.current.value = '';
    onChatSearch?.();
  }
  useLayoutEffect(() => {
    if (searchOpen) search.current.focus();
  }, [searchOpen]);
  const newButton = useRef(null);
  const choices = useRef(null);
  useLayoutEffect(() => {
    if (!choicesOpen) return;
    choices.current.querySelector('button')?.focus();
    const outside = (event) => {
      if (!choices.current.contains(event.target) && !newButton.current.contains(event.target)) {
        setChoicesOpen(false);
      }
    };
    const escape = (event) => {
      if (event.key !== 'Escape') return;
      setChoicesOpen(false);
      newButton.current.focus();
    };
    document.addEventListener('click', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('click', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [choicesOpen]);
  return (
    <div id="analysisChatsDrawer" className="analysis-chats-drawer is-hidden" aria-hidden="true">
      <div className="analysis-chats-drawer-backdrop" data-analysis-chats-close="true"></div>
      <aside
        className="analysis-sidebar analysis-chats-drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="analysisChatsDrawerTitle"
      >
        <div className="analysis-sidebar-header">
          <div className="analysis-sidebar-copy">
            <strong id="analysisChatsDrawerTitle">Chats</strong>
          </div>
          <button
            id="chatSearchToggle"
            ref={searchButton}
            onClick={() => {
              if (searchOpen) closeSearch();
              else setSearchOpen(true);
            }}
            type="button"
            className="query-chip chat-header-action"
            aria-label="Search chats"
            title="Search chats"
            aria-expanded={searchOpen}
            aria-controls="analysisChatSearch"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <circle cx="10" cy="10" r="6" />
              <path d="m15 15 6 6" />
            </svg>
          </button>
          <button
            id="analysisChatsDrawerCloseBtn"
            type="button"
            className="query-chip chat-header-action"
            aria-label="Close chats"
            title="Close chats"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M9 4v16m7-11-3 3 3 3" />
            </svg>
          </button>
          <button
            id="analysisNewSessionBtn"
            ref={newButton}
            onClick={() => setChoicesOpen((open) => !open)}
            type="button"
            className="query-chip chat-header-action"
            aria-label="New chat"
            title="New chat"
            aria-expanded={choicesOpen}
            aria-controls="newChatChoices"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-7" />
              <path d="m16 3 5 5M10 14l-1 4 4-1L22 8a2.1 2.1 0 0 0-5-5Z" />
            </svg>
          </button>
        </div>
        <div
          ref={choices}
          id="newChatChoices"
          className="new-chat-choices"
          hidden={!choicesOpen}
          aria-label="Choose chat type"
          onClick={(event) => {
            if (event.target.closest('button')) setChoicesOpen(false);
          }}
        >
          <button id="newQueryChatBtn" type="button" onClick={() => onNewChat?.('query')}>
            Query chat
          </button>
          <button id="newAnalysisChatBtn" type="button" onClick={() => onNewChat?.('analysis')}>
            Analysis chat
          </button>
          <button id="newPhenoChatBtn" type="button" onClick={() => onNewChat?.('pheno')}>
            Pheno-Ranker chat
          </button>
          <button id="newChatFolderBtn" type="button">
            New folder
          </button>
          <button id="selectChatsBtn" type="button">
            Select chats…
          </button>
        </div>
        <input
          id="analysisChatSearch"
          ref={search}
          onInput={() => onChatSearch?.()}
          onKeyDown={(event) => {
            if (event.key !== 'Escape') return;
            event.stopPropagation();
            closeSearch();
            searchButton.current.focus();
          }}
          type="search"
          aria-label="Search chats"
          placeholder="Search chats"
          hidden={!searchOpen}
        />
        <div id="analysisSessionList" className="analysis-session-list chat-session-list">
          <div className="empty">No chats yet.</div>
        </div>
        <div id="queryChatSaveStatus" role="status" className="chat-save-status" hidden></div>
        <div id="chatFolderStatus" role="status" className="chat-folder-status" hidden></div>
      </aside>
    </div>
  );
}

export function MoveChatDialog() {
  return (
    <dialog
      id="chatMoveDialog"
      className="chat-move-dialog"
      aria-labelledby="chatMoveTitle"
    ></dialog>
  );
}

export function DeleteChatDialog() {
  return (
    <div
      id="analysisSessionDeleteDialog"
      className="analysis-session-delete-dialog is-hidden"
      aria-hidden="true"
    >
      <div
        className="analysis-session-delete-dialog-backdrop"
        data-analysis-session-delete-close="true"
      ></div>
      <div
        className="analysis-session-delete-dialog-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="analysisSessionDeleteTitle"
      >
        <div className="analysis-session-delete-dialog-header">
          <div>
            <strong id="analysisSessionDeleteTitle">Delete chat</strong>
            <div className="section-note">
              Choose whether to remove only the chat while keeping generated runs, or delete the
              generated results, logs, and artifacts too.
            </div>
          </div>
          <button
            id="analysisSessionDeleteCloseBtn"
            type="button"
            className="query-chip secondary-btn"
          >
            Cancel
          </button>
        </div>
        <div className="analysis-session-delete-dialog-body">
          <div id="analysisSessionDeleteSummary" className="analysis-session-delete-summary">
            Delete this analysis session?
          </div>
          <div id="analysisSessionDeleteStatus" className="query-status is-hidden"></div>
        </div>
        <div className="analysis-session-delete-dialog-actions">
          <button id="analysisSessionDeleteOnlyBtn" type="button" className="query-chip danger-btn">
            Delete chat, keep runs
          </button>
          <button
            id="analysisSessionDeleteAllBtn"
            type="button"
            className="query-chip danger-btn danger-confirm"
          >
            Delete chat and generated data
          </button>
        </div>
      </div>
    </div>
  );
}
