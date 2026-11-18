import React from 'react';
import { ArtifactDownloads, EvidenceCard } from '../analysis-result-parts.jsx';
export function EvidenceResults({ model: m, turnIndex }) {
  const id = (suffix) => `analysis-plot-${turnIndex}-${suffix}`;
  return m.cards.map((card) => (
    <EvidenceCard key={card.suffix} id={id(card.suffix)} title={card.title} items={card.items} />
  ));
}
