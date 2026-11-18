import { StarterPrompts } from './starter-prompts.jsx';
import React from 'react';
export function PatientScopeSetup({ actions }) {
  return (
    <details id="analysisWorkspaceSetup" className="analysis-setup-card">
      <summary className="analysis-setup-summary">
        <div className="analysis-setup-summary-copy">
          <strong>Patients and cohorts</strong>
          <div className="section-note">Use the full workspace or choose a subset.</div>
        </div>
        <div className="analysis-setup-summary-body">
          <div id="analysisSelectedPatientIdsSummary" className="section-note">
            Scope: full workspace.
          </div>
          <div
            id="analysisSelectedSavedCohortSelection"
            onClick={actions.analysisSelectedSavedCohortSelectionClick}
            className="section-note is-hidden"
          ></div>
          <div id="analysisCompareSelectedPatientIdsSummary" className="section-note is-hidden">
            Cohort B: select a saved cohort from Saved Cohorts to compare.
          </div>
          <div
            id="analysisCompareSavedCohortSelection"
            onClick={actions.analysisCompareSavedCohortSelectionClick}
            className="section-note is-hidden"
          ></div>
        </div>
      </summary>
      <div className="analysis-setup-body">
        <div>
          <label htmlFor="analysisSelectedPatientIds">Scope</label>
          <input
            id="analysisSelectedPatientIds"
            onInput={actions.analysisSelectedPatientIdsInput}
            placeholder="Full workspace by default, or provide patient/original record IDs"
          />
        </div>
        <div className="pheno-checks analysis-setup-checks">
          <label>
            <input
              id="analysisCompareMode"
              onChange={actions.analysisCompareModeChange}
              type="checkbox"
            />{' '}
            Compare against a second cohort
          </label>
        </div>
        <div
          id="analysisCompareField"
          className="analysis-setup-compare"
          style={{ display: 'none' }}
        >
          <input
            id="analysisCompareSelectedPatientIds"
            onInput={actions.analysisCompareSelectedPatientIdsInput}
            type="hidden"
            defaultValue=""
          />
        </div>
        <details className="analysis-setup-saved-cohorts">
          <summary className="analysis-setup-saved-cohorts-header">
            <strong>Saved Cohorts</strong>
            <span className="section-note">
              Attach existing saved cohorts as Cohort A or Cohort B.
            </span>
          </summary>
          <div id="savedCohorts" onClick={actions.savedCohortsClick} className="empty">
            No saved cohorts yet.
          </div>
        </details>
        <StarterPrompts onExample={actions.example} />
      </div>
    </details>
  );
}
