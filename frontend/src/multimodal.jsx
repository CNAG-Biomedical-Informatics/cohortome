import { createRoot } from 'react-dom/client';
import { PatientInventory } from './patient-inventory.jsx';
import { ScopeBar, DiseaseChips, SaveIcon } from './cohort-controls.jsx';
import { modalityPresentation, modalityColor } from '../../static/js/modalities.js';

function ModalityIcon({ value }) {
  const presentation = modalityPresentation(value);
  // SVG paths come only from the application's fixed modality icon definitions.
  return (
    <svg
      className="assay-overview-icon"
      data-modality-icon={presentation.key}
      style={{ color: modalityColor(presentation.key) }}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: presentation.icon }}
    />
  );
}

function Combinations({ groups, modalities, labels, onSelect }) {
  const maximum = Math.max(1, ...groups.map((group) => group.patients.length));
  if (!groups.length)
    return <p className="empty">No matches. Broaden the cohort, disease or data-type filters.</p>;
  return (
    <table className="assay-table">
      <thead>
        <tr>
          <th>Patients</th>
          {modalities.map((modality) => (
            <th key={modality}>
              <ModalityIcon value={modality} /> {labels[modality]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {groups.map((group, index) => (
          <tr className="coverage-match" key={JSON.stringify(group.modalities)}>
            <td>
              <button
                className="query-chip"
                type="button"
                data-combination={index}
                aria-label={`${group.modalities.map((value) => labels[value]).join(' + ')}: ${group.patients.length} patients`}
                onClick={() => onSelect(group.modalities)}
              >
                {group.patients.length}
              </button>
              <span
                className="coverage-bar"
                style={{ width: (group.patients.length / maximum) * 85 }}
                aria-hidden="true"
              />
            </td>
            {modalities.map((modality) => (
              <td
                key={modality}
                className="coverage-dot"
                style={{ color: modalityColor(modality) }}
              >
                <span
                  aria-label={group.modalities.includes(modality) ? 'Available' : 'Not recorded'}
                >
                  {group.modalities.includes(modality) ? '●' : '·'}
                </span>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MatchingPatients({ patients, page, onPage, onInspect }) {
  const pages = Math.max(1, Math.ceil(patients.length / 25));
  return (
    <>
      <div className="assay-table-wrap">
        <table className="assay-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Dataset</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {patients.slice(page * 25, (page + 1) * 25).map((patient, index) => (
              <tr key={JSON.stringify([patient.dataset_id, patient.patient_id])}>
                <td>{patient.patient_id}</td>
                <td>{patient.dataset_label}</td>
                <td>
                  <button
                    className="query-chip"
                    type="button"
                    data-patient={page * 25 + index}
                    disabled={!patient.has_clinical}
                    onClick={() => onInspect(patient)}
                  >
                    Inspect
                  </button>
                  {patient.has_clinical ? '' : ' No clinical record'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        className="query-chip coverage-prev"
        disabled={page === 0}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>{' '}
      Page {page + 1} of {pages}{' '}
      <button
        type="button"
        className="query-chip coverage-next"
        disabled={page + 1 === pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </>
  );
}

function Multimodal({ model, actions, scopeUi }) {
  if (model.phase === 'loading') return <p className="section-note">Loading patient coverage…</p>;
  if (model.phase === 'error')
    return (
      <>
        <p>{model.error}</p>
        <button className="query-chip" type="button" onClick={actions.retry}>
          Retry coverage
        </button>
      </>
    );
  const {
    draft,
    cohorts,
    modalities,
    labels,
    diseases,
    showAllDiseases,
    groups,
    patients,
    page,
    canSave,
    saveStatus,
    warnings,
    inspector,
  } = model;
  return (
    <>
      <ScopeBar scopeUi={scopeUi} className="coverage-scope-bar" />
      <section className="coverage-filter-section">
        <h3>Filter patients</h3>
        <div className="coverage-filter-row">
          <label className="coverage-match-mode">
            <span>Patient group</span>
            <select
              className="coverage-cohort"
              aria-label="Patient group"
              disabled={!cohorts.length && draft.base_members === null}
              value={draft.base_members !== null ? '__selection__' : draft.cohort_id}
              onChange={(event) => actions.cohort(event.target.value)}
            >
              <option value="">All patients in this workspace</option>
              {cohorts.map((cohort) => (
                <option key={cohort.id} value={cohort.id}>
                  {cohort.name} · {cohort.patient_count} patients
                </option>
              ))}
              {draft.base_members !== null && (
                <option value="__selection__">{draft.base_members.length} selected patients</option>
              )}
            </select>
          </label>
          <label className="coverage-match-mode">
            <span>Match</span>
            <select
              className="coverage-mode"
              value={draft.exact ? 'exact' : 'includes'}
              onChange={(event) => actions.mode(event.target.value)}
            >
              <option value="includes">At least these types</option>
              <option value="exact">Only these types</option>
            </select>
          </label>
        </div>
        <div className="coverage-start-description">
          <button
            type="button"
            className="query-chip"
            data-edit-patient-filters=""
            onClick={actions.editPatients}
          >
            Edit clinical filters in Patients
          </button>
        </div>
        <div className="coverage-clinical-section" hidden={!diseases.length}>
          <h4>Diseases</h4>
          <div
            className="coverage-diseases"
            role="group"
            aria-label="Disease filters"
            hidden={!diseases.length}
          >
            <DiseaseChips
              diseases={diseases}
              selected={new Set(draft.diseases)}
              showAll={showAllDiseases}
              onSelect={actions.disease}
              onToggle={actions.toggleDiseases}
              title="Workspace patients with this disease"
              multipleLabel="Any selected disease"
            />
          </div>
        </div>
        <div className="coverage-modality-section">
          <h4>Required data</h4>
          <div className="coverage-selectors" role="group" aria-label="Required data types">
            {modalities.map((modality) => (
              <label key={modality}>
                <input
                  type="checkbox"
                  value={modality}
                  checked={draft.modalities.includes(modality)}
                  onChange={(event) => actions.modality(modality, event.target.checked)}
                />
                <ModalityIcon value={modality} />
                <span>{labels[modality]}</span>
              </label>
            ))}
          </div>
        </div>
      </section>
      <div className="coverage-result" aria-live="polite">
        <strong>{patients.length} patients in scope</strong>
        <button
          type="button"
          className="coverage-save"
          title="Save the applied patient scope for later use"
          disabled={!canSave}
          onClick={actions.save}
        >
          <SaveIcon />
          {`Save ${patients.length} ${patients.length === 1 ? 'patient' : 'patients'} as a cohort`}
        </button>
        <span className="coverage-save-status" role="status">
          {saveStatus}
        </span>
        <button type="button" className="query-chip" onClick={actions.clinical}>
          View Clinical
        </button>
      </div>
      <section className="coverage-data-section">
        <h4>Available combinations</h4>
        <p className="section-note">
          Filled dots show available data. Click a count to select a combination.
        </p>
        <div className="assay-table-wrap coverage-intersections">
          <Combinations
            groups={groups}
            modalities={modalities}
            labels={labels}
            onSelect={actions.combination}
          />
        </div>
        <details className="coverage-patients">
          <summary>Matching patients</summary>
          <div className="coverage-patient-list">
            <MatchingPatients
              patients={patients}
              page={page}
              onPage={actions.page}
              onInspect={actions.inspect}
            />
          </div>
        </details>
        <div className="coverage-inspector">
          {inspector &&
            (inspector.patient ? (
              <section>
                <h4>
                  {inspector.patient.patient_id} · {inspector.patient.dataset_label}
                </h4>
                <PatientInventory rows={inspector.samples} />
                {inspector.warnings.map((warning, index) => (
                  <p key={index}>{warning}</p>
                ))}
              </section>
            ) : (
              <section>{inspector.message}</section>
            ))}
        </div>
      </section>
      <details>
        <summary>How matching works</summary>
        <p>Patient-level matches—not necessarily the same specimen or visit.</p>
        <p>
          At least these types allows additional data. Only these types excludes additional
          non-clinical types. Clinical records are optional unless Clinical is selected.
        </p>
        <p>
          Each chart row is a recorded combination. Combinations with more non-clinical types appear
          first. Patient IDs remain separate across datasets. Imaging studies means a listed study,
          not confirmed image access.
        </p>
      </details>
      {!!warnings.length && (
        <details>
          <summary>Coverage limitations ({warnings.length})</summary>
          {warnings.map((warning, index) => (
            <p key={index}>{warning}</p>
          ))}
        </details>
      )}
    </>
  );
}

export function createMultimodalView({ host, scopeUi }) {
  const root = createRoot(host);
  return {
    render: (model, actions) =>
      root.render(<Multimodal model={model} actions={actions} scopeUi={scopeUi} />),
    destroy: () => root.unmount(),
  };
}
