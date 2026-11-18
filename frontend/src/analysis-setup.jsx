import { PatientScopeSetup } from './analysis-setup/patient-scope.jsx';
import { CatalogueDrawer } from './analysis-setup/catalogue.jsx';
import { AnalysisComposer } from './analysis-setup/composer.jsx';
import React from 'react';

export function AnalysisSetup() {
  return (
    <>
      <summary>
        Edit setup <span className="section-note">Method, patients and inputs</span>
      </summary>
      <div id="analysisDatasetScope" className="section-note">
        Workspace dataset: current selection.
      </div>
      <PatientScopeSetup />
      <div id="analysisStarterHost"></div>
      <CatalogueDrawer />
      <AnalysisComposer />
    </>
  );
}
