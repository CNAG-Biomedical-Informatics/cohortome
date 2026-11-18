import { createRoot } from 'react-dom/client';
import { useLayoutEffect, useRef } from 'react';
import { ModalityIcon } from './assay-overview.jsx';
import { modalityLabel } from '../../static/js/modalities.js';

const columns = [
  ['variant_id', 'Variant'],
  ['position', 'Location'],
  ['gene', 'Gene'],
  ['classification', 'Classification'],
  ['carriers', 'Carriers'],
];
const fields = (entries) => (
  <dl className="variant-fields">
    {entries.map(([key, value]) => (
      <div key={key}>
        <dt>{key}</dt>
        <dd>{String(value || 'Not recorded')}</dd>
      </div>
    ))}
  </dl>
);
function Detail({ detail, actions }) {
  const host = useRef(null);
  useLayoutEffect(() => {
    if (detail?.data) host.current.scrollIntoView({ block: 'nearest' });
  }, [detail?.data]);
  const data = detail?.data,
    a = data?.annotation || {},
    p = data?.provenance || {};
  return (
    <section ref={host} className="variant-detail" hidden={!detail} aria-label="Selected variant">
      {detail?.loading && <p role="status">Loading variant…</p>}
      {detail?.error && <p role="alert">{detail.error}</p>}
      {data && (
        <>
          <header>
            <h4>{detail.id}</h4>
            <button
              type="button"
              className="ghost variant-close"
              aria-label="Close variant details"
              onClick={actions.closeDetail}
            >
              Close
            </button>
          </header>
          <div className="variant-call-counts">
            {Object.entries(data.counts).map(([key, count]) => (
              <span key={key}>
                <strong>{count.toLocaleString()}</strong> {key} calls
              </span>
            ))}
          </div>
          {fields([
            ['Assembly', a.assembly],
            ['Gene', a.gene],
            ['Classification', a.classification],
            ['Annotation source', a.classification_source],
            ['Source version', a.classification_version],
            ['Review status', a.review_status || a.CLINVAR_CLNREVSTAT],
            ['Condition', a.condition || a.CLINVAR_CLNDN],
          ])}
          <details>
            <summary>Provenance and supplied annotations</summary>
            {fields([
              [
                'Technology',
                {
                  dna_sequencing: 'DNA sequencing',
                  genotyping_array: 'Genotyping array',
                  synthetic: 'Synthetic',
                }[p.technology] || p.technology,
              ],
              ['Method / platform', p.method || p.platform],
              ['Original input', p.input_format],
              ['Imported selection', p.selection],
            ])}
            <pre>{JSON.stringify(a, null, 2)}</pre>
          </details>
          <p className="section-note">
            Carriers have a fully called genotype with an alternate allele. Missing and partial
            calls are excluded. An annotation is not a diagnosis.
          </p>
          <div className="variant-actions">
            <button
              type="button"
              className="variant-save"
              disabled={detail.saving || !data.members.length}
              onClick={actions.save}
            >
              Save {data.members.length} {data.members.length === 1 ? 'carrier' : 'carriers'} as a
              cohort
            </button>
            <span role="status">{detail.status || ''}</span>
          </div>
        </>
      )}
    </section>
  );
}
function VariantBrowser({ model: m, actions: a }) {
  const back = useRef(null);
  useLayoutEffect(() => {
    back.current.focus();
  }, [m.openRevision]);
  const rows = m.result?.rows || [];
  return (
    <>
      <button ref={back} type="button" className="ghost variant-back" onClick={a.back}>
        ← Back to assays
      </button>
      <header className="variant-header">
        <div className="variant-heading">
          <ModalityIcon modality="genotyping" />
          <div>
            <h3>Variant browser</h3>
            <span className="section-note">Explore variants. Select their carriers.</span>
          </div>
        </div>
        <span className="variant-count">
          {m.result
            ? `${m.result.total.toLocaleString()} ${m.result.total === 1 ? 'variant' : 'variants'}`
            : ''}
        </span>
      </header>
      <div className="variant-toolbar">
        <label>
          Dataset
          <select
            className="variant-dataset"
            aria-label="Dataset"
            value={m.dataset}
            onChange={(e) => a.dataset(e.target.value)}
          >
            {m.panels.map((p) => (
              <option key={p.dataset_id} value={p.dataset_id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="variant-search">
          Find a variant
          <input
            type="search"
            placeholder="Variant ID, gene or position"
            aria-label="Search variant ID, gene or position"
            value={m.q}
            onChange={(e) => a.query(e.target.value)}
          />
        </label>
        {[
          ['chromosome', 'Chromosome', 'All chromosomes', m.chromosomes],
          ['classification', 'Classification', 'All classifications', m.classifications],
        ].map(([key, label, all, options]) => (
          <label key={key}>
            {label}
            <select
              className={`variant-${key}`}
              aria-label={label}
              value={m[key]}
              disabled={!options.length}
              onChange={(e) => a.filter(key, e.target.value)}
            >
              <option value="">{all}</option>
              {options.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <div className="variant-status section-note" role="status">
        {m.status}
      </div>
      <div className="variant-results" aria-busy={m.busy}>
        {!!rows.length && (
          <div className="variant-table-wrap">
            <table>
              <thead>
                <tr>
                  {columns.map(([key, label]) => (
                    <th
                      key={key}
                      scope="col"
                      aria-sort={
                        m.sortBy === key
                          ? m.direction === 'asc'
                            ? 'ascending'
                            : 'descending'
                          : 'none'
                      }
                    >
                      <button type="button" data-sort={key} onClick={() => a.sort(key)}>
                        {label}
                        {m.sortBy === key ? (m.direction === 'asc' ? ' ↑' : ' ↓') : ''}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.variant_id}>
                    <td>
                      <button
                        type="button"
                        className="variant-open"
                        data-row={i}
                        onClick={() => a.detail(m.dataset, r.variant_id)}
                      >
                        {r.variant_id}
                      </button>
                      <small>
                        {r.ref} → {r.alt}
                      </small>
                    </td>
                    <td>
                      {r.chromosome}:{Number(r.position).toLocaleString()}
                    </td>
                    <td>{r.gene || <span className="section-note">—</span>}</td>
                    <td>
                      {r.classification ? (
                        <span className="variant-class-label">
                          {r.classification.replaceAll('_', ' ')}
                        </span>
                      ) : (
                        <span className="section-note">Not annotated</span>
                      )}
                    </td>
                    <td>
                      <span className="variant-carrier-count">{r.carriers}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <footer className="variant-pagination">
        <span>
          {m.result?.total
            ? `${m.offset + 1}–${m.offset + rows.length} of ${m.result.total.toLocaleString()}`
            : ''}
        </span>
        <div>
          <button
            type="button"
            className="ghost variant-prev"
            disabled={m.busy || !m.offset}
            onClick={() => a.page(-25)}
          >
            Previous
          </button>
          <button
            type="button"
            className="ghost variant-next"
            disabled={m.busy || !m.result || m.offset + 25 >= m.result.total}
            onClick={() => a.page(25)}
          >
            Next
          </button>
        </div>
      </footer>
      <Detail detail={m.detail} actions={a} />
    </>
  );
}
export function createVariantView(host, actions) {
  let root;
  return {
    render(model) {
      root ||= createRoot(host);
      root.render(<VariantBrowser model={model} actions={actions} />);
    },
    reset() {
      root?.unmount();
      root = null;
    },
  };
}
export function createVariantPanelsView(host, open) {
  let root;
  return {
    render(panels, error) {
      if (!host) return;
      root ||= createRoot(host);
      root.render(
        error ? (
          <p className="section-note" role="status">
            {error}
          </p>
        ) : (
          <>
            {panels.map((p, i) => {
              const technology = p.provenance?.technology,
                modality = ['dna_sequencing', 'genotyping_array'].includes(technology)
                  ? technology
                  : 'genotyping';
              return (
                <article className="variant-panel-card" key={p.dataset_id}>
                  <div className="variant-panel-heading">
                    <ModalityIcon modality={modality} />
                    <div>
                      <h4>{modalityLabel(modality)}</h4>
                      <span className="section-note">{p.label}</span>
                    </div>
                  </div>
                  <div className="variant-panel-footer">
                    <span>
                      {Number(p.variants).toLocaleString()} variants ·{' '}
                      {Number(p.samples).toLocaleString()} samples
                    </span>
                    <button
                      type="button"
                      className="query-chip"
                      data-variant-panel={i}
                      onClick={(e) => open(p.dataset_id, e.currentTarget)}
                    >
                      Browse variants <span aria-hidden="true">→</span>
                    </button>
                  </div>
                </article>
              );
            })}
          </>
        ),
      );
    },
  };
}
