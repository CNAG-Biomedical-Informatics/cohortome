import { Activity } from './activity.jsx';
import { QueryProvenance } from './query-provenance.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { QueryActions } from './query-actions.jsx';
import { Reply } from './reply.jsx';

function Followups({ items, metadata }) {
  const prompts = Array.isArray(items) ? items.slice(0, 4) : [];
  const byPrompt = new Map(
    (Array.isArray(metadata) ? metadata : [])
      .filter((item) => item && typeof item === 'object' && String(item.prompt || '').trim())
      .map((item) => [String(item.prompt).trim(), item]),
  );
  if (!prompts.length) return null;
  return (
    <div className="query-followups" style={{ marginTop: 12 }}>
      <div className="query-followups-label">Suggested follow-up queries</div>
      <div className="query-followups-list">
        {prompts.map((item, index) => {
          const prompt = String(item || '').trim(),
            meta = byPrompt.get(prompt) || {};
          const deterministic =
            meta.execution_kind === 'deterministic' || meta.execution_mode === 'deterministic_only';
          return (
            <button
              key={index}
              type="button"
              className={`query-chip ${deterministic ? 'query-chip-deterministic' : 'query-chip-planner'}`}
              data-prompt={prompt}
              data-query-followup-mode={deterministic ? 'deterministic_only' : 'planner_only'}
              title={
                deterministic
                  ? 'Runs with deterministic dataset logic; no LLM planning is requested.'
                  : 'Uses the LLM semantic planner, then executes the resulting dataset query deterministically.'
              }
            >
              <span>{prompt}</span>
              <span className="followup-mode-label">
                {deterministic ? 'Deterministic' : 'LLM-planned'}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
export function CopyButton() {
  return (
    <button
      type="button"
      className="chat-copy-button"
      data-chat-copy=""
      title="Copy message"
      aria-label="Copy message"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        aria-hidden="true"
      >
        <rect x="8" y="8" width="12" height="13" rx="2" />
        <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
      </svg>
      <span className="chat-copy-status" aria-live="polite" />
    </button>
  );
}
function QueryTurn({ turn, index }) {
  if (turn.role === 'user')
    return (
      <article
        className="analysis-turn query-thread-turn query-thread-turn-user"
        data-query-turn-index={index}
      >
        <div className="analysis-turn-label">You</div>
        <div className="analysis-turn-body">
          <p>{turn.prompt || ''}</p>
        </div>
      </article>
    );
  return (
    <article
      className={`analysis-turn query-thread-turn ${turn.tone}${turn.latest ? ' query-thread-turn-latest' : ''}`}
      data-query-turn-index={index}
    >
      <div className="analysis-turn-label">{turn.label}</div>
      <div className="analysis-turn-body">
        <div data-chat-copy-content="">
          {turn.pending ? <Activity {...turn.reply} /> : <Reply model={turn.reply} />}
        </div>
        <QueryActions model={turn.actions} />
        {!turn.pending && turn.latest && (
          <Followups items={turn.followups} metadata={turn.followupMetadata} />
        )}
      </div>
      {!turn.pending && (
        <>
          <details className="query-response-details">
            <summary>Response details</summary>
            <QueryProvenance items={turn.provenance} />
          </details>
          <CopyButton />
        </>
      )}
    </article>
  );
}
export function createQueryThreadView(host) {
  const root = createRoot(host);
  return {
    render(turns, general) {
      // The existing controller immediately locates new turns for scrolling and
      // result navigation. Commit before returning until that lifecycle migrates.
      flushSync(() =>
        root.render(
          turns.length ? (
            turns.map((turn, index) => <QueryTurn key={index} turn={turn} index={index} />)
          ) : (
            <div className="empty">
              {general
                ? 'Ask a general question. The model will not receive workspace context.'
                : 'Ask a query to start a conversational thread. Follow-up questions will reuse recent query history.'}
            </div>
          ),
        ),
      );
    },
  };
}
