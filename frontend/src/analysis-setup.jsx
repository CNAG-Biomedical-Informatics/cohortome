import { PatientScopeSetup } from './analysis-setup/patient-scope.jsx';
import { CatalogueDrawer } from './analysis-setup/catalogue.jsx';
import { AnalysisComposer } from './analysis-setup/composer.jsx';
import React from 'react';

export function AnalysisSetup({ shellActions }) {
  return (
    <>
      <summary>
        Edit setup <span className="section-note">Method, patients and inputs</span>
      </summary>
      <div id="analysisDatasetScope" className="section-note">
        Workspace dataset: current selection.
      </div>
      <PatientScopeSetup actions={shellActions.PatientScopeSetup} />
      <div id="analysisStarterHost"></div>
      <CatalogueDrawer actions={shellActions.CatalogueDrawer} />
      <AnalysisComposer actions={shellActions.AnalysisComposer} />
    </>
  );
}
