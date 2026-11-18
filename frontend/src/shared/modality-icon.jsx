import { modalityPresentation, modalityColor } from '../../../static/js/modalities.js';

// SVG paths come only from the fixed application catalogue.
export function ModalityIcon({ modality }) {
  const item = modalityPresentation(modality);
  return (
    <svg
      className="assay-overview-icon"
      data-modality-icon={item.key}
      style={{ color: modalityColor(item.key) }}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: item.icon }}
    />
  );
}
