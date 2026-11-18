import { createRoot } from 'react-dom/client';
import { ClinicalFilters } from './clinical-filters.jsx';
import { SelectField } from './shared/select-field';
import { ViewStatus } from './shared/view-status';
import { FilterPanel } from './shared/filter-panel';
import { ScopeBar, DiseaseChips } from './cohort-controls.jsx';

const columns = [
  {
    key: 'patient_id',
    label: 'Patient ID',
    icon: (
      <>
        <circle cx="12" cy="7" r="4" />
        <path d="M4 21v-3a8 8 0 0 1 16 0v3" />
      </>
    ),
  },
  {
    key: 'dataset_label',
    label: 'Dataset',
    icon: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0" />
      </>
    ),
  },
  {
    key: 'diagnosis',
    label: 'Diagnosis',
    icon: (
      <>
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M12 8v8M8 12h8" />
      </>
    ),
  },
  {
    key: 'clarid',
    label: 'ClarID',
    icon: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M7 10h3M7 14h3M13 10h4M13 14h4" />
      </>
    ),
  },
];
const value = (text) => String(text || 'Not recorded');

function PatientTable({ matches, sortBy, sortDirection, onSort, onChoose, loading }) {
  return (
    <table>
      <thead>
        <tr>
          {columns.map((column) => {
            const active = sortBy === column.key;
            return (
              <th
                key={column.key}
                scope="col"
                aria-sort={active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                <button
                  type="button"
                  className="patient-sort"
                  data-sort={column.key}
                  aria-label={`Sort by ${column.label}`}
                  onClick={() => onSort(column.key)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    aria-hidden="true"
                  >
                    {column.icon}
                  </svg>
                  {column.label}
                  <span aria-hidden="true">
                    {active ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
                  </span>
                </button>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {matches.length ? (
          matches.map((match, index) => (
            <tr
              key={JSON.stringify([match.dataset_id, match.patient_id])}
              data-match={index}
              onClick={() => onChoose(match)}
            >
              <td>
                <button
                  type="button"
                  className="patient-open"
                  aria-label={`Open patient ${value(match.patient_id)}`}
                >
                  {value(match.patient_id)}
                  <span aria-hidden="true"> →</span>
                </button>
              </td>
              <td>{value(match.dataset_label)}</td>
              <td>{value(match.diagnosis)}</td>
              <td>
                {match.clarid ? (
                  <span className="patient-browser-clarid" title={value(match.clarid)}>
                    {value(match.clarid)}
                  </span>
                ) : (
                  <span className="patient-browser-missing">Not recorded</span>
                )}
              </td>
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan="4" className="patient-browser-empty">
              <ViewStatus kind={loading ? 'loading' : 'empty'}>
                {loading ? 'Loading patients in scope…' : 'No patients to display.'}
              </ViewStatus>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function Patients({ model, actions, scopeUi, isClinicalCurrent }) {
  const {
    matches,
    sortBy,
    sortDirection,
    draft,
    diseases,
    origins,
    showAllDiseases,
    clinicalWorkspace,
    matchCount,
    status,
    saveStatus,
    saveLabel,
    loading,
    canSave,
    canNavigate,
    canNext,
    canPrevious,
    selectedPatient,
  } = model;
  return (
    <>
      <div className="patient-finder">
        <div className="dashboard-view-heading">
          <h2>Patients</h2>
          <span id="patientMatchCount" className="dashboard-count" role="status">
            {matchCount}
          </span>
          <details className="inline-view-help">
            <summary aria-label="About patient search">?</summary>
            <p>
              Filter patients by disease, clinical characteristics or sample origin. Save the
              matching group or refine it by data availability in Multimodal. Click a patient to
              inspect their timeline.
            </p>
          </details>
        </div>
        <ScopeBar
          scopeUi={scopeUi}
          previewLabel={model.previewLabel}
          save={{
            id: 'patientSaveCohort',
            enabled: canSave,
            label: saveLabel,
            onClick: actions.save,
            status: saveStatus,
          }}
        />
        <FilterPanel>
          <div className="patient-lookup">
            <label htmlFor="patientOverviewSearch">Patient ID or ClarID</label>
            <div className="patient-search-field">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                aria-hidden="true"
              >
                <circle cx="10.5" cy="10.5" r="6.5" />
                <path d="m16 16 4 4" />
              </svg>
              <input
                id="patientOverviewSearch"
                type="search"
                autoComplete="off"
                aria-controls="patientOverviewMatches"
                placeholder="Search by patient ID or ClarID…"
                value={draft.q}
                onChange={(event) => actions.search(event.target.value)}
              />
            </div>
          </div>
          <div
            id="patientDiseaseFilters"
            className="query-composer-disease-chips patient-disease-filters"
            role="group"
            aria-label="Filter patients by disease"
          >
            <DiseaseChips
              diseases={diseases}
              selected={new Set(draft.diseases)}
              showAll={showAllDiseases}
              onSelect={actions.disease}
              onToggle={actions.toggleDiseases}
            />
          </div>
          <div id="patientSampleOriginFilter" className="patient-lookup" hidden={!origins.length}>
            <SelectField
              label="Sample origin"
              id="patientSampleOrigin"
              value={draft.sample_origin}
              onChange={(event) => actions.origin(event.target.value)}
            >
              <option value="">All sample origins</option>
              {origins.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.label} · {row.id} ({Number(row.patient_count)})
                </option>
              ))}
            </SelectField>
          </div>
          <div
            id="patientClinicalFilters"
            className="patient-clinical-filters"
            hidden={!clinicalWorkspace}
          >
            {clinicalWorkspace && (
              <ClinicalFilters
                key={clinicalWorkspace}
                workspace={clinicalWorkspace}
                scopeUi={scopeUi}
                isCurrent={isClinicalCurrent}
              />
            )}
          </div>
        </FilterPanel>
        <div className="patient-cohort-actions">
          <button
            id="patientRefineMultimodal"
            type="button"
            className="secondary-btn"
            disabled={!canNavigate}
            onClick={actions.multimodal}
          >
            Multimodal filters
          </button>
        </div>
        <div
          id="patientOverviewMatches"
          className="patient-browser-table"
          aria-busy={loading || undefined}
        >
          <PatientTable
            loading={loading}
            matches={matches}
            sortBy={sortBy}
            sortDirection={sortDirection}
            onSort={actions.sort}
            onChoose={actions.choose}
          />
        </div>
        <div className="patient-browser-footer">
          <div id="patientOverviewStatus" className="section-note" role="status">
            {status}
          </div>
          <div className="patient-browser-pages">
            <button
              id="patientOverviewPrevious"
              type="button"
              className="query-chip"
              disabled={!canPrevious}
              onClick={actions.previous}
            >
              Previous
            </button>
            <button
              id="patientOverviewMore"
              type="button"
              className="query-chip"
              disabled={!canNext}
              onClick={actions.next}
            >
              Next
            </button>
          </div>
        </div>
      </div>
      <nav className="patient-view-switch" aria-label="Patient views">
        <button
          id="patientTimelineBtn"
          type="button"
          className="query-chip"
          disabled={!selectedPatient}
          hidden={!selectedPatient}
          onClick={actions.timeline}
        >
          View this patient's timeline
        </button>
      </nav>
    </>
  );
}

export function createPatientsView({ host, scopeUi, isClinicalCurrent, actions }) {
  const root = createRoot(host);
  return {
    render: (model) =>
      root.render(
        <Patients
          model={model}
          actions={actions}
          scopeUi={scopeUi}
          isClinicalCurrent={isClinicalCurrent}
        />,
      ),
  };
}
