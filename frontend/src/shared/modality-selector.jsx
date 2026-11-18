import { ModalityIcon } from './modality-icon.jsx';
import { modalityColor } from '../../../static/js/modalities.js';

export function ModalitySelector({ id, className = '', modalities, selected, label, onChange }) {
  return (
    <div
      id={id}
      className={`modality-selector ${className}`}
      role="group"
      aria-label="Required data types"
    >
      {modalities.map((modality) => (
        <label key={modality} style={{ '--modality-color': modalityColor(modality, true) }}>
          <input
            type="checkbox"
            value={modality}
            checked={selected.includes(modality)}
            onChange={(event) => onChange(modality, event.target.checked)}
          />
          <ModalityIcon modality={modality} />
          <span>{label(modality)}</span>
        </label>
      ))}
    </div>
  );
}
