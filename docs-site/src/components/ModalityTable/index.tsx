import React from 'react';
import {modalityPresentation} from '../../../../static/js/modalities.js';
import styles from './styles.module.css';

const rows = [
  ['clinical', '', 'Beacon/BFF patient and visit records', 'Patient search, timelines, cohorts and phenotype analyses'],
  ['transcriptomics', '', 'Counts, RSEM expected counts or normalized expression', 'Gene exploration; count-based workflows need compatible counts'],
  ['methylation', '', 'Processed CpG M-values, including panels', 'Coverage, QC/PCA and differential methylation'],
  ['proteomics', 'Proteomics / OLINK', 'Processed protein abundances', 'Coverage, feature exploration and cross-modal associations'],
  ['metabolomics', 'Metabolomics / other assays', 'Numeric feature-by-sample matrices', 'Coverage and selected-feature exploration'],
  ['flow_cytometry', '', 'Processed flow-cytometry measurements', 'Feature exploration and curated cohort comparison'],
  ['serology', '', 'Quantitative marker measurements', 'Feature exploration and curated cohort comparison'],
  ['dna_sequencing', 'DNA sequencing', 'Prepared biallelic variant panels; optional annotations—not raw VCFs', 'Variant browsing, carrier cohorts and coverage'],
  ['genotyping_array', 'Genotyping arrays', 'Array-derived genotype / dosage matrices, or prepared variant panels', 'Coverage; variant browsing only for prepared panels'],
  ['imaging', '', 'Linked DICOM studies and derived measurements', 'OHIF viewing and measurement exploration'],
];

export default function ModalityTable() {
  return <div className={styles.wrapper} tabIndex={0} role="region" aria-label="Supported modalities">
    <table className={styles.table}>
      <thead><tr><th scope="col">Data</th><th scope="col">Prepared input</th><th scope="col">Use in COHORTome</th></tr></thead>
      <tbody>{rows.map(([key, label, input, use]) => {
        const appearance = modalityPresentation(key);
        return <tr key={key}>
          <th scope="row"><span className={styles.label} style={{'--modality-color': appearance.color, '--modality-dark': appearance.darkColor} as React.CSSProperties}>
            {/* Trusted, fixed SVG shapes from the application's registry, never dataset content. */}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{__html: appearance.icon}} />
            <span>{label || appearance.label}</span>
          </span></th><td>{input}</td><td>{use}</td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}
