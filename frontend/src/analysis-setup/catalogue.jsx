import React from 'react';
export function CatalogueDrawer({ actions }) {
  return (
    <div
      id="analysisCatalogDrawer"
      onClick={actions.analysisCatalogDrawerClick}
      className="analysis-catalog-drawer is-hidden"
      aria-hidden="true"
    >
      <div className="analysis-catalog-drawer-backdrop" data-analysis-catalog-close="true"></div>
      <div
        className="analysis-catalog-drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="analysisCatalogDrawerTitle"
      >
        <div className="analysis-catalog-drawer-header">
          <div>
            <strong id="analysisCatalogDrawerTitle">Analysis Catalog</strong>
            <div className="section-note">
              Curated, structured analyses that preconfigure the current Analysis thread.
            </div>
          </div>
          <button
            id="analysisCatalogDrawerCloseBtn"
            onClick={actions.analysisCatalogDrawerCloseBtnClick}
            type="button"
            className="query-chip"
          >
            Close
          </button>
        </div>
        <div className="analysis-catalog-toolbar analysis-catalog-toolbar-drawer">
          <label className="analysis-catalog-search">
            <span className="analysis-catalog-search-label">Search</span>
            <input
              id="analysisCatalogDrawerSearch"
              onInput={actions.analysisCatalogDrawerSearchInput}
              type="search"
              placeholder="Find tools by name, tag, runner, or description"
            />
          </label>
          <div
            id="analysisCatalogDrawerFilters"
            onClick={actions.analysisCatalogDrawerFiltersClick}
            className="analysis-catalog-filters"
            role="tablist"
            aria-label="Analysis Catalog filters"
          >
            <button
              type="button"
              className="query-chip is-active"
              data-analysis-catalog-filter="all"
              aria-pressed="true"
            >
              All
            </button>
            <button
              type="button"
              className="query-chip"
              data-analysis-catalog-filter="clinical"
              aria-pressed="false"
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="clinical"
                aria-hidden="true"
              ></span>
              Clinical
            </button>
            <button
              type="button"
              className="query-chip"
              data-analysis-catalog-filter="assay"
              aria-pressed="false"
            >
              <span
                className="analysis-domain-icon"
                data-modality-symbol="assay"
                aria-hidden="true"
              ></span>
              Assays
            </button>
            <button
              type="button"
              className="query-chip"
              data-analysis-catalog-filter="workflow"
              aria-pressed="false"
            >
              Workflow
            </button>
            <button
              type="button"
              className="query-chip"
              data-analysis-catalog-filter="background"
              aria-pressed="false"
            >
              Background
            </button>
            <button
              type="button"
              className="query-chip"
              data-analysis-catalog-filter="external"
              aria-pressed="false"
            >
              External
            </button>
          </div>
        </div>
        <div
          id="analysisCatalogDrawerList"
          onClick={actions.analysisCatalogDrawerListClick}
          className="analysis-catalog-list"
        >
          <div className="empty">Loading curated analyses...</div>
        </div>
      </div>
    </div>
  );
}
