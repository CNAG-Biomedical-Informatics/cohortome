import { QueryProvenance } from './query-provenance.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { CopyButton } from './query-thread.jsx';
import { Reply } from './reply.jsx';
import { AnalysisResults, ArtifactDownloads } from './analysis-results.jsx';
function SectionIcon({ followup = false }) {
  return (
    <span className="analysis-inline-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {followup ? (
          <path d="M12 5v14m-7-7 7 7 7-7" />
        ) : (
          <>
            <ellipse cx="12" cy="6" rx="7" ry="3" />
            <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
          </>
        )}
      </svg>
    </span>
  );
}

function AnalysisTurn({ turn: t, index }) {
  if (t.role === 'user')
    return (
      <article className="analysis-turn analysis-turn-user" data-analysis-turn-index={index}>
        <div className="analysis-turn-label">You</div>
        <div className="analysis-turn-body">
          <p>{t.prompt}</p>
          {!t.general && (
            <>
              <div className="analysis-turn-scope">
                <strong>{t.compareScope ? 'Cohort A' : 'Scope'}:</strong> {t.scope}
              </div>
              {t.compareScope && (
                <div className="analysis-turn-scope">
                  <strong>Cohort B:</strong> {t.compareScope}
                </div>
              )}
            </>
          )}
        </div>
      </article>
    );
  if (t.pending)
    return (
      <article className="analysis-turn analysis-turn-pending" data-analysis-turn-index={index}>
        <div className="analysis-turn-label">{t.general ? 'Model' : 'Analysis'}</div>
        <div className="analysis-turn-meta">
          <span className="query-chip badge">pending</span>
          <span className="query-chip badge">{t.pendingLabel || 'Preparing response'}</span>
        </div>
        <div className="analysis-turn-body">
          <div className="analysis-pending-row">
            <div className="analysis-thinking-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <span>
              {t.pendingDetail || 'Building cohort context and waiting for the model reply.'}
            </span>
          </div>
        </div>
      </article>
    );
  const framing = t.framing;
  return (
    <article
      className={`analysis-turn ${t.error ? 'analysis-turn-error' : 'analysis-turn-assistant'} ${t.latest ? 'is-latest-result' : 'is-previous-result'}`}
      data-analysis-turn-index={index}
    >
      <div className="analysis-turn-label">
        {t.error
          ? t.general
            ? 'Model Error'
            : 'Analysis Error'
          : t.general
            ? 'Answer'
            : 'Analysis result'}
      </div>
      <div className="analysis-result-content">
        {t.heading && (
          <header className="analysis-result-heading">
            <h3>{t.heading}</h3>
            <div className="analysis-result-cohorts">
              {t.badges.map((badge, i) => (
                <span key={i} className={`analysis-cohort-badge ${badge.side || ''}`}>
                  {badge.text}
                </span>
              ))}
            </div>
          </header>
        )}
        {t.visuals && (
          <div key={JSON.stringify(t.data?.artifacts || [])} className="analysis-result-visuals">
            <div className="analysis-plot-grid">
              <AnalysisResults model={t.visuals} />
            </div>
          </div>
        )}
        <div className="analysis-turn-body" data-chat-copy-content="">
          <Reply model={t.reply} />
        </div>
        <CopyButton />
        {!!t.contextParts.length && (
          <div className="analysis-turn-context">
            <p>{t.contextParts.join(' | ')}</p>
          </div>
        )}
        <details className="query-section analysis-response-details">
          <summary>{t.general ? 'Response details' : 'Method and technical details'}</summary>
          <QueryProvenance className="analysis-turn-meta" items={t.provenance} analysis />
          {!t.general && framing && (
            <details className="query-section analysis-framing-result">
              <summary>
                {framing.mode === 'hypothesis_driven' ? 'Hypothesis-driven' : 'Exploratory'} ·
                Research question
              </summary>
              <p>{framing.question || 'No research question recorded.'}</p>
              {framing.mode === 'hypothesis_driven' && (
                <p>
                  <strong>Hypothesis:</strong> {framing.hypothesis || 'Not recorded'}
                </p>
              )}
              <p className="section-note">
                Captured at submission: {framing.captured_at || 'Not recorded'}. User-specified
                framing, not formal preregistration.
              </p>
            </details>
          )}
          {t.audit && (
            <details className="query-section">
              <summary>Analysis implementation</summary>
              <p>{t.audit.note}</p>
              <ArtifactDownloads
                title="Source snapshot"
                artifacts={[{ name: t.audit.filename, url: t.audit.url }]}
              />
              <p>
                SHA-256: <code>{t.audit.sha256}</code>
              </p>
            </details>
          )}
          <details className="query-section analysis-result-data">
            <summary>
              <span className="analysis-section-label">
                <SectionIcon />
                <span>{t.general ? 'Show response data' : 'Show analysis data'}</span>
              </span>
            </summary>
            <pre>{JSON.stringify(t.data, null, 2)}</pre>
          </details>
        </details>
        {!!t.followups.length && (
          <div className="analysis-result-followups">
            <div className="query-followups" style={{ marginTop: 12 }}>
              <div className="query-followups-label analysis-section-label">
                <SectionIcon followup />
                <span>Suggested follow-up queries</span>
              </div>
              <div className="query-followups-list">
                {t.followups.map((prompt, i) => (
                  <button
                    key={i}
                    type="button"
                    className="query-chip query-chip-llm"
                    data-analysis-followup-prompt={prompt}
                    data-analysis-followup-mode="llm_only"
                    title="Uses the LLM to interpret the completed analysis and its workspace context."
                  >
                    <span>{prompt}</span>
                    <span className="followup-mode-label">LLM interpretation</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
export function createAnalysisThreadView(host) {
  const root = createRoot(host);
  return {
    render(turns, sessionId = '') {
      flushSync(() =>
        root.render(
          turns.length ? (
            turns.map((turn, index) => (
              <AnalysisTurn key={`${sessionId}:${index}`} turn={turn} index={index} />
            ))
          ) : (
            <div className="empty">
              Run an analysis prompt to start a threaded analysis workspace.
            </div>
          ),
        ),
      );
    },
  };
}
