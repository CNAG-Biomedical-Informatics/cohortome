import React from 'react';
export function StarterPrompts() {
  return (
    <div id="analysisStarterPanel" className="analysis-starter-panel">
      <div className="analysis-starter-header">
        <div>
          <label htmlFor="analysisPrompt">Analysis</label>
          <div className="section-note">
            Use curated analyses for structured runs, or use quick prompts for simpler open-ended
            interpretation.
          </div>
        </div>
      </div>
      <div className="analysis-catalog-shell">
        <div className="analysis-catalog-block">
          <div className="analysis-catalog-block-header">
            <strong>Quick prompts</strong>
            <span className="section-note">
              Questions you can ask directly without using a catalog tool.
            </span>
          </div>
          <div className="section-note">
            Prompt types:{' '}
            <span className="query-chip query-chip-deterministic badge">Deterministic summary</span>{' '}
            <span className="query-chip query-chip-planner badge">LLM-planned</span>{' '}
            <span className="query-chip query-chip-llm badge">LLM interpretation</span>
          </div>
          <div className="query-examples" id="analysisExamples">
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="Summarize the main clinical patterns in this workspace and tell me what stands out."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Main workspace patterns</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="What stands out in treatment usage over time?"
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Treatment usage over time</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="Show the main disease burden, medication burden, and visit distribution in this workspace."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Disease, medication, and visit burden</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="Describe how this workspace changes over time and point out the most active periods."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>How the workspace changes over time</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="Which patient subgroups look most distinct within the current analysis scope?"
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Distinct patient subgroups</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="Summarize the top diseases and medications and tell me which patterns are most concentrated."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Top diseases and medications</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-deterministic"
              data-analysis-deterministic="true"
              data-analysis-prompt="Which numeric longitudinal measures are available in the current analysis scope?"
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Available longitudinal measures</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-planner"
              data-analysis-prompt="Tell me which diseases and medications most separate the active analysis scopes."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>What separates A from B</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-planner"
              data-analysis-prompt="Compare the active analysis scopes and focus on temporal differences and possible treatment-intensity differences."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Temporal and treatment-intensity differences</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-planner"
              data-analysis-prompt="Compare the active analysis scopes by disease burden, medication burden, and timepoint distribution."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Compare A vs B core profiles</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-llm"
              data-analysis-llm-only="true"
              data-analysis-prompt="Interpret the disease and medication profiles in this workspace and summarize the main themes."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Interpret disease and medication profiles</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-llm"
              data-analysis-llm-only="true"
              data-analysis-prompt="Write a concise workspace briefing for a clinician, including what stands out and what needs validation."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Clinician-facing workspace briefing</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-llm"
              data-analysis-llm-only="true"
              data-analysis-prompt="Write a short clinician-facing summary combining the current analysis scope profile and the observed transcriptomics expression findings."
            >
              <span className="analysis-domain-icons" aria-hidden="true">
                <span
                  className="analysis-domain-icon"
                  data-modality-symbol="clinical"
                  aria-hidden="true"
                ></span>
                <span
                  className="analysis-domain-icon"
                  data-modality-symbol="assay"
                  aria-hidden="true"
                ></span>
              </span>
              <span>Clinical + assay summary</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-llm"
              data-analysis-llm-only="true"
              data-analysis-prompt="Compare the active analysis scopes like a clinical reviewer and summarize the main similarities, differences, and uncertainties."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Clinical review of A vs B</span>
            </button>
            <button
              type="button"
              className="query-chip query-chip-llm"
              data-analysis-llm-only="true"
              data-analysis-prompt="Interpret the selected workspace subset as a possible clinical subgroup and explain what evidence supports that interpretation."
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              <span>Interpret selected subgroup</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
