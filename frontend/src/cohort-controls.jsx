import { useLayoutEffect, useRef } from 'react';

export function ScopeBar({scopeUi, className}) {
  const host = useRef(null);
  useLayoutEffect(() => scopeUi.mount(host.current), [scopeUi]);
  return <div ref={host} className={className}/>;
}

export function SaveIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 3h12l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8"/></svg>;
}

export function DiseaseChips({diseases, selected, showAll, onSelect, onToggle,
  multipleLabel = 'Matching any selected disease', title}) {
  const items = showAll ? diseases : diseases.filter((item, index) => index < 8 || selected.has(item.disease));
  return <>
    <button type="button" className="query-chip query-chip-deterministic" data-disease=""
      aria-pressed={!selected.size} onClick={() => onSelect('')}>All diseases</button>
    {items.map(item => <button key={item.disease} type="button" className="query-chip query-chip-deterministic"
      data-disease={item.disease} title={title} aria-pressed={selected.has(item.disease)} onClick={() => onSelect(item.disease)}>
      {item.disease} <span className="query-chip badge">{Number(item.patient_count) || 0}</span>
    </button>)}
    {diseases.length > 8 && <button type="button" className="query-chip" data-more-diseases=""
      aria-expanded={showAll} onClick={onToggle}>{showAll ? 'Show fewer' : 'More diseases…'}</button>}
    {selected.size > 1 && <span className="section-note">{multipleLabel}</span>}
  </>;
}
