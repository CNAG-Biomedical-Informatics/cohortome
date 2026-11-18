import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { PhenoExplanation } from './pheno-explanation.jsx';

function UserTurn({ prompt }) {
  return (
    <article className="analysis-turn analysis-turn-user">
      <div className="analysis-turn-label">You</div>
      <div className="analysis-turn-body">
        <p>{prompt}</p>
      </div>
    </article>
  );
}
function Progress({ request, message, error, kind }) {
  return (
    <>
      <UserTurn prompt={request} />
      <article
        className={`analysis-turn ${error ? 'analysis-turn-error' : 'analysis-turn-pending'} pheno-${kind}-progress`}
        role="status"
        aria-live="polite"
        aria-busy={!error}
      >
        <div className="analysis-turn-label">Pheno-Ranker</div>
        <div className="analysis-turn-body">
          {!error && (
            <div className="analysis-thinking-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          )}
          <span>{message}</span>
        </div>
      </article>
    </>
  );
}
export function createPhenoThreadView(host) {
  const root = createRoot(host);
  return {
    render({ turns, activeResult, runProgress, explanationProgress }) {
      flushSync(() =>
        root.render(
          <>
            {turns.map((turn, index) => (
              <React.Fragment key={index}>
                <UserTurn prompt={turn.prompt} />
                <article className="analysis-turn analysis-turn-assistant" data-pheno-reply={index}>
                  <div className="analysis-turn-label">
                    {turn.kind === 'explanation' ? 'Explanation' : 'Pheno-Ranker'}
                  </div>
                  {turn.kind === 'error' ? (
                    <>
                      <p role="alert">{turn.payload.message}</p>
                      <details>
                        <summary>Details</summary>
                        <pre>{turn.payload.detail || ''}</pre>
                      </details>
                    </>
                  ) : turn.kind === 'explanation' ? (
                    <PhenoExplanation model={turn.explanation} />
                  ) : (
                    <>
                      <p>
                        {turn.kind === 'queued' ? 'Background job submitted.' : 'Completed run'}
                      </p>
                      <button
                        type="button"
                        className="query-chip"
                        data-pheno-turn={index}
                        hidden={index === activeResult}
                      >
                        {turn.kind === 'queued' ? 'Check result' : 'Show results'}
                      </button>
                      <div data-pheno-result-host={index} />
                    </>
                  )}
                </article>
              </React.Fragment>
            ))}
            {runProgress && (
              <Progress
                kind="run"
                request={runProgress.prompt || 'Run Pheno-Ranker'}
                message="Running Pheno-Ranker…"
              />
            )}
            {explanationProgress && <Progress kind="explanation" {...explanationProgress} />}
          </>,
        ),
      );
    },
  };
}
