import { createRoot } from 'react-dom/client';
import { ModalityIcon } from './assay-overview.jsx';

function Linkage({item, number}) {
  const total = Number(item.patient_count), linked = Number(item.clinical_overlap_patient_count);
  if (item.patient_count == null || item.clinical_overlap_patient_count == null || !Number.isFinite(total) || !Number.isFinite(linked) || total <= 0 || linked < 0 || linked > total)
    return <div className="assay-linkage"><strong>Clinical linkage</strong><span className="section-note">Coverage not available.</span></div>;
  const percent = linked / total * 100;
  return <div className="assay-linkage"><div><strong>Clinical linkage</strong><span>{number(linked)} of {number(total)} assay patients · {percent.toFixed(0)}%</span></div>
    <div className="assay-coverage-track" aria-hidden="true"><i style={{width:`${percent}%`}}/></div>
    <small>{total === linked ? 'All assay patients have a linked clinical record.' : `${number(total - linked)} assay patients have no linked clinical record in this workspace.`}</small></div>;
}
function Expression({item}) {
  if (item.count_summary_status === 'not_calculated_for_scope') return <p className="section-note">Expression summaries for this group are available in Analysis.</p>;
  const expected = item.data_type === 'rsem_expected_counts';
  const number = value => value != null && Number.isFinite(Number(value)) ? Number(value).toFixed(1) : 'Not calculated';
  return <><div className="assay-card-section"><strong>Transcriptomics coverage</strong><div className="assay-summary-grid">
    <div className="assay-summary-item"><span>{expected ? 'Expected' : 'Total'} counts / sample</span><strong>{number(item.mean_total_counts_per_sample)}</strong></div>
    <div className="assay-summary-item"><span>Genes with counts &gt; 0 / sample</span><strong>{number(item.mean_detected_genes_per_sample)}</strong></div>
  </div></div><div className="assay-card-section"><strong>Top abundant genes</strong><div className="assay-gene-list">
    {item.top_genes?.length ? item.top_genes.map((gene, index) => {
      const title = [gene.gene_id, gene.gene_symbol, gene.gene_name, `Total ${expected ? 'expected' : 'raw'} count: ${gene.total_count ?? gene.total_raw_count ?? 'Not calculated'}`].filter(Boolean).join(' • ');
      let url = '';
      try {const parsed = new URL(gene.ensembl_url); if (['http:', 'https:'].includes(parsed.protocol)) url = parsed.href;} catch (_) {}
      return url ? <a key={`${gene.gene_id}:${index}`} className="assay-gene-pill assay-gene-pill-link" href={url} target="_blank" rel="noopener" title={title}>{gene.gene_id}</a>
        : <span key={`${gene.gene_id}:${index}`} className="assay-gene-pill" title={title}>{gene.gene_id}</span>;
    }) : <span className="section-note">No top-gene summary available.</span>}
  </div></div></>;
}
function AssayCard({entry, model}) {
  const {item, modality, overlap, dataType, valueKind} = entry;
  const {formatModality, formatDataType, number, compare, openVariant} = model;
  if (item.variant_panel) return <article className="variant-panel-card">
    <div className="variant-panel-heading"><ModalityIcon modality={modality}/><div><h4>{formatModality(modality)}</h4><span className="section-note">{item.label}</span></div></div>
    <div className="variant-panel-footer"><span>{Number(item.variants).toLocaleString()} variants · {Number(item.samples).toLocaleString()} samples</span>
      <button type="button" className="query-chip" data-variant-dataset={item.dataset_id} onClick={event => openVariant(item.dataset_id, event.currentTarget)}>Browse variants <span aria-hidden="true">→</span></button></div>
  </article>;
  const expression = modality === 'transcriptomics';
  return <article className={`assay-dashboard-card assay-dashboard-card-${modality}`}>
    <div className="assay-card-header"><div><div className="assay-card-eyebrow">{modality === 'imaging' ? 'Imaging measurements' : expression ? 'Expression assay' : `${formatModality(modality)} assay`}</div>
      <strong className="assay-card-title">{item.label || item.dataset_name}</strong></div><span className="assay-modality-badge"><ModalityIcon modality={modality}/>{formatModality(modality)}</span></div>
    <div className="assay-card-meta"><span className="dataset-picker-tag">{item.dataset_name}</span><span className="dataset-picker-tag">{formatDataType(dataType)}</span></div>
    <div className="assay-kpi-grid">{[['Samples', item.sample_count || 0], ['Patients', item.patient_count || 0], ['Features', item.feature_count ?? item.gene_count ?? 'Not reported']].map(([label, value]) =>
      <div key={label} className="assay-kpi"><span className="assay-kpi-label">{label}</span><strong className="assay-kpi-value">{String(value)}</strong></div>)}</div>
    <Linkage item={item} number={number}/>
    {expression ? <Expression item={item}/> : <details className="assay-card-section assay-technical-details">
      <summary>{modality === 'imaging' ? 'Derived DICOM measurements' : `${formatModality(modality)} matrix`} · technical details</summary>
      <div className="assay-summary-grid">{[['Feature type', String(item.feature_label || 'features').trim()], ['Namespace', String(item.feature_id_type || item.feature_namespace || 'feature_id').trim().replace(/_/g, ' ')], ['Value kind', formatDataType(valueKind)]].map(([label, value]) =>
        <div key={label} className="assay-summary-item"><span>{label}</span><strong>{value}</strong></div>)}</div>
    </details>}
    {overlap && !!(overlap.scopeASize || overlap.scopeBSize) && <div className="assay-card-section"><strong>Current Analysis scope</strong><div className="assay-stats">
      <span className="query-chip badge">A overlap: {overlap.overlapA} / {overlap.scopeASize || item.clinical_overlap_patient_count || 0}</span>
      {compare && <span className="query-chip badge">B overlap: {overlap.overlapB} / {overlap.scopeBSize || item.clinical_overlap_patient_count || 0}</span>}
    </div></div>}
  </article>;
}
function AssayCards({model}) {
  if (model.empty) return <div className="empty">{model.empty}</div>;
  if (model.error) return <div className="workspace-notice workspace-notice-unavailable" role="status"><strong>{model.error.title}</strong><p>{model.error.message}</p></div>;
  const cards = model.entries.map(entry => <AssayCard key={JSON.stringify([entry.item.source_dataset_id, entry.item.dataset_name || entry.item.dataset_id])} entry={entry} model={model}/>);
  return model.imaging ? <>{cards}</> : <section className="assay-modality-section"><div className="assay-modality-section-header"><strong>{model.title}</strong><span className="query-chip badge">{cards.length} assay{cards.length === 1 ? '' : 's'}</span></div><div className="assay-dashboard-grid">{cards}</div></section>;
}
export function createAssayCardsView(host) {
  let root;
  return {render(model) {if (!host) return; root ||= createRoot(host); root.render(<AssayCards model={model}/>);}};
}
