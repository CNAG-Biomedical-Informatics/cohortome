import { QueryProvenance } from './query-provenance.jsx';
import { Activity } from './activity.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { ReplyText } from './reply.jsx';

function LabelGroup({ title, items, tone }) {
  if (!items.length) return null;
  return (
    <div className={`pheno-explain-group ${tone}`}>
      <div className="pheno-explain-group-title">{title}</div>
      <div className="pheno-explain-chip-wrap">
        {items.map((item, index) => (
          <span
            key={index}
            className="alignment-bucket-pill pheno-explain-chip"
            style={{ '--bucket-bg': item.style.bg, '--bucket-ink': item.style.ink }}
          >
            <span className="alignment-swatch" />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
function Matches({ matches }) {
  return (
    <div className="pheno-explain-match-grid">
      {matches.map((match, index) => (
        <div key={index} className="pheno-explain-match-card">
          <div className="pheno-explain-match-head">
            <div>
              <div className="pheno-explain-match-rank">Match {index + 1}</div>
              <h4>{match.reference_id || 'Unknown match'}</h4>
            </div>
          </div>
          <div className="alignment-summary">
            {match.metrics.length ? (
              match.metrics.map(([key, value]) => (
                <span key={key} className="alignment-stat">
                  {key} {String(value)}
                </span>
              ))
            ) : (
              <span className="alignment-stat">No numeric metrics detected</span>
            )}
          </div>
          {match.highlights.length > 0 && (
            <ul className="pheno-explain-highlight-list">
              {match.highlights.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}
          <div className="pheno-explain-groups">
            <LabelGroup title="Shared variables" items={match.shared} tone="is-shared" />
            <LabelGroup
              title="Match-only variables"
              items={match.referenceOnly}
              tone="is-reference"
            />
            <LabelGroup title="Target-only variables" items={match.targetOnly} tone="is-target" />
          </div>
        </div>
      ))}
    </div>
  );
}
export function PhenoExplanation({ model }) {
  if (model.message) return <div className="empty">{model.message}</div>;
  // Activity and provenance remain escaped application-generated markup.
  if (model.activity) return <Activity {...model.activity} />;
  return (
    <>
      <div className="pheno-explain-header">
        <div className="pheno-explain-title-row">
          <div className="pheno-explain-title-block">
            <strong>Target {model.targetId}</strong>
            <span>
              {model.isLlm ? (
                'Patient-level explanation with supporting match evidence'
              ) : (
                <>
                  Top {model.topN} matches from <code>rank.txt</code>
                </>
              )}
            </span>
          </div>
          <QueryProvenance className="pheno-explain-meta" items={model.provenance} />
        </div>
      </div>
      {model.reply && (
        <div className="query-section" style={{ marginBottom: 12 }}>
          <h4>LLM answer</h4>
          <ReplyText text={model.reply} />
        </div>
      )}
      {model.isLlm ? (
        <details className="query-section pheno-explain-evidence">
          <summary>Show details</summary>
          <div className="section-note" style={{ marginBottom: 12 }}>
            Supporting evidence from the top {model.topN} matches in <code>rank.txt</code>.
          </div>
          <Matches matches={model.matches} />
        </details>
      ) : (
        <Matches matches={model.matches} />
      )}
    </>
  );
}
export function createPhenoExplanationView(host) {
  const root = createRoot(host);
  return {
    render(model) {
      root.render(<PhenoExplanation model={model} />);
    },
  };
}
