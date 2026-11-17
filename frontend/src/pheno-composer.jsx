import React from 'react';

export function PhenoComposer() {
  return <>
<details id="phenoPromptDetails">
              <summary>Use a prompt instead</summary>
            <label htmlFor="phenoPrompt">Describe a run (optional)</label>
            <textarea id="phenoPrompt" rows="2" placeholder="Or describe what you want, for example: compare all patients by disease"></textarea>
            <div className="section-note">Prompt types: <span className="query-chip query-chip-deterministic badge">Deterministic</span> <span className="query-chip query-chip-llm badge">LLM answer</span></div>
            <div className="query-examples" id="phenoExamples">
              <button type="button" className="query-chip query-chip-deterministic" data-pheno-prompt="Compare all patients by phenotypicFeatures and diseases">Compare all by phenotypes and diseases</button>
              <button type="button" className="query-chip query-chip-deterministic" data-pheno-prompt="Find closest matches by disease">Find closest matches by disease</button>
              <button type="button" className="query-chip query-chip-deterministic" data-pheno-prompt="Compare patient SYN007:week_0 to all others using phenotypicFeatures">Compare one patient to all</button>
              <button type="button" className="query-chip query-chip-deterministic" data-pheno-prompt="Extract patients SYN001, SYN002, SYN003">Extract selected patients</button>
              <button type="button" className="query-chip query-chip-llm" data-pheno-prompt="Compare the selected patients by disease and explain the best matches">Compare selected patients by disease</button>
              <button type="button" className="query-chip query-chip-llm" data-pheno-prompt="Find the most relevant phenotypic matches for SYN010 and explain why they match">Explain why matches occur</button>
              <button type="button" className="query-chip query-chip-llm" data-pheno-prompt="Compare all patients using the most informative top-level terms and generate both plots">Use the most informative top-level terms</button>
              <button type="button" className="query-chip query-chip-llm" data-pheno-prompt="Compare the current scope and focus on the clinically most relevant similarities">Focus on clinically relevant similarities</button>
            </div>
            </details>
            <div id="phenoReadiness" className="pheno-readiness" role="status" aria-live="polite"></div>
            <div className="pheno-actions pheno-actions-primary" style={{marginTop:12}}>
              <button id="phenoRunBtn" type="button">
                <span className="button-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m5 3 14 9-14 9V3Z"></path>
                  </svg>
                </span>
                <span>Run Pheno-Ranker</span>
              </button>
            </div>
            <button id="phenoPlanRunBtn" type="button" className="is-hidden" aria-hidden="true" tabIndex="-1">Interpret and run</button>
            <div id="phenoBackgroundJobBanner" className="pheno-background-job-banner is-hidden" role="status" aria-live="polite" aria-atomic="true"></div>
  </>;
}
