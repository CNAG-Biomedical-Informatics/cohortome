// Shared data-type identity. Not for status colours or scientific value scales.
const definitions = {
  clinical: ['Clinical', 'purple', '#6d28d9', '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M12 9v7M8.5 12.5h7"/>'],
  assay: ['Assays', 'green', '#166534', '<path d="M7 3c0 4 3 4 3 8s-3 4-3 8M17 3c0 4-3 4-3 8s3 4 3 8M8 6h8M8 18h8"/>'],
  imaging: ['Imaging', 'teal', '#0f766e', '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="12" cy="12" r="5"/><path d="M12 9v6M9 12h6"/>'],
  transcriptomics: ['Transcriptomics', 'blue', '#1d4ed8', '<path d="M7 3c0 4 10 5 10 9s-10 5-10 9M17 3c0 4-10 5-10 9s10 5 10 9M8 6h8M8 18h8M9 10h6M9 14h6"/>'],
  methylation: ['DNA methylation', 'purple', '#6d28d9', '<path d="M7 3v7l-4 8a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-4-8V3M5 3h10M6 15h8"/><circle cx="19" cy="6" r="3"/>'],
  flow_cytometry: ['Immune-cell abundance', 'amber', '#92400e', '<circle cx="6" cy="7" r="3"/><circle cx="17" cy="6" r="2"/><circle cx="13" cy="16" r="4"/><circle cx="4" cy="18" r="1"/>'],
  serology: ['Serology', 'red', '#b91c1c', '<path d="M12 3S5 11 5 15a7 7 0 0 0 14 0c0-4-7-12-7-12Z"/><path d="M9 16a3 3 0 0 0 3 3"/>'],
  proteomics: ['Proteomics', 'teal', '#0f766e', '<path d="M4 5c0-3 16-3 16 1S4 9 4 13s16 1 16 5-16 5-16 1M4 5c0 5 16 8 16 13"/>'],
  genotyping: ['Genotyping', 'green', '#166534', '<path d="M7 3c0 4 10 5 10 9s-10 5-10 9M17 3c0 4-10 5-10 9s10 5 10 9M8 6h8M8 18h8"/>'],
};
export function modalityKey(value) {
  const key = String(value || 'assay').trim().toLowerCase();
  if (key === 'dicom' || key.startsWith('imaging')) return 'imaging';
  if (key.startsWith('olink') || key.startsWith('proteomics')) return 'proteomics';
  if (key.startsWith('immune_cell') || key.startsWith('flow_cytometry')) return 'flow_cytometry';
  if (key.startsWith('variant')) return 'genotyping';
  return Object.keys(definitions).find(name => key === name || key.startsWith(name + '_')) || 'assay';
}
export function modalityLabel(value) {
  const raw = String(value || 'assay').trim();
  if (raw.toLowerCase().startsWith('olink')) return 'OLINK';
  const key = modalityKey(raw);
  return key !== 'assay' || ['assay', 'assays', ''].includes(raw.toLowerCase())
    ? definitions[key][0] : raw.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}
export function modalityColor(value, resolved = false) {
  const [, tone, fallback] = definitions[modalityKey(value)];
  const variable = `--theme-${tone}-ink`;
  return resolved ? (getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || fallback)
    : `var(${variable}, ${fallback})`;
}
export function modalityIcon(value, className = 'assay-overview-icon') {
  const key = modalityKey(value);
  return `<svg class="${className}" data-modality-icon="${key}" style="color:${modalityColor(key)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${definitions[key][3]}</svg>`;
}
