// Display names only. Backend catalogs remain authoritative for capabilities.
const ASSAY_LABELS = Object.freeze({
  transcriptomics: "Transcriptomics",
  methylation: "DNA methylation",
  olink: "OLINK",
  proteomics: "Proteomics",
  flow_cytometry: "Immune-cell abundance",
  serology: "Serology",
  genotyping: "Genotyping",
  imaging: "Imaging",
  raw_counts: "Raw counts",
  m_values: "M-values",
  relative_abundance: "Relative abundance",
  protein_abundance: "Protein abundance",
  cell_population_abundance: "Cell-population abundance",
  quantitative_measurement: "Quantitative measurement",
  allele_dosage: "Allele dosage",
  dicom_derived_measurements: "DICOM-derived measurements",
});

export function formatAssayModality(value) {
  const text = String(value || "assay").trim();
  if (!text) return "Assays";
  return ASSAY_LABELS[text] || text.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatAssayDataType(value) {
  const text = String(value || "feature_matrix").trim();
  if (!text) return "Feature matrix";
  return ASSAY_LABELS[text] || text.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatAssayRequirementLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "";
  if (ASSAY_LABELS[normalized]) {
    return ASSAY_LABELS[normalized];
  }
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
