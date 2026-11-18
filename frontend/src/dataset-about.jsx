import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { DatasetDocument } from './dataset-document.jsx';

function About({ datasetId, dispose }) {
  const ref = useRef(null),
    content = useRef(null);
  const [data, setData] = useState(null),
    [selected, setSelected] = useState(''),
    [error, setError] = useState('');
  useLayoutEffect(() => {
    ref.current.showModal();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/datasets/${encodeURIComponent(datasetId)}/about`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok)
          throw Error('Unable to load dataset documentation. Close this panel and try again.');
        setData(await response.json());
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setError(error.message);
      });
    return () => controller.abort();
  }, [datasetId]);
  useLayoutEffect(() => {
    if (content.current) content.current.scrollTop = 0;
  }, [selected]);
  const doc = (data?.documents || []).find((d) => d.filename === selected);
  return (
    <dialog
      ref={ref}
      className="dataset-about-dialog"
      aria-labelledby="dataset-about-title"
      onClose={dispose}
      onClick={(event) => {
        const button = event.target.closest('[data-document]');
        if (button) {
          event.preventDefault();
          if (data?.documents.some((d) => d.filename === button.dataset.document))
            setSelected(button.dataset.document);
        }
      }}
    >
      <header>
        <div>
          <small>About this dataset</small>
          <h2 id="dataset-about-title">
            {data?.name || (error ? 'Dataset documentation' : 'Loading…')}
          </h2>
        </div>
        <button
          type="button"
          className="query-chip secondary-btn"
          data-close=""
          aria-label="Close about this dataset"
          onClick={() => ref.current.close()}
        >
          Close
        </button>
      </header>
      <p data-description="" hidden={!!doc}>
        {data?.description || ''}
      </p>
      <nav aria-label="Dataset documentation">
        {doc ? (
          <button
            type="button"
            className="dataset-about-link"
            data-summary=""
            onClick={() => setSelected('')}
          >
            ← Summary
          </button>
        ) : (
          (data?.documents || []).map((d) => (
            <a
              key={d.filename}
              className="dataset-about-link"
              href={`/datasets/${encodeURIComponent(datasetId)}/about/${encodeURIComponent(d.filename)}`}
              data-document={d.filename}
            >
              {d.filename === 'README.md' ? 'Read full documentation →' : 'Terms and attribution →'}
            </a>
          ))
        )}
      </nav>
      <div
        ref={content}
        className="dataset-about-content"
        role="region"
        aria-label="Dataset documentation content"
        tabIndex="0"
        hidden={!doc}
      >
        {doc && <DatasetDocument text={doc.text} />}
      </div>
      <p role="status" aria-live="polite">
        {error ||
          (!data
            ? 'Loading dataset documentation…'
            : data.unavailable?.length
              ? 'Some package documentation could not be read.'
              : data.documents?.length
                ? ''
                : 'No additional documentation is included in this dataset.')}
      </p>
    </dialog>
  );
}
export function showDatasetAbout(datasetId) {
  const previousFocus = document.activeElement,
    host = document.createElement('div');
  document.body.append(host);
  const root = createRoot(host);
  root.render(
    <About
      datasetId={datasetId}
      dispose={() =>
        queueMicrotask(() => {
          root.unmount();
          host.remove();
          previousFocus?.focus();
        })
      }
    />,
  );
}
