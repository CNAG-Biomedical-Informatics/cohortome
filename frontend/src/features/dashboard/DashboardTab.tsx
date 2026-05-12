import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { DashboardSummary, DatasetRecord, EvidenceInventory, MolecularDatasetRecord, PatientContext, PatientSummary } from "../../api/types";

export function DashboardTab({ datasetId, selectedDatasets }: { datasetId: string; selectedDatasets: DatasetRecord[] }) {
  const [search, setSearch] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState("");

  const dashboard = useQuery({
    queryKey: ["dashboard", datasetId],
    queryFn: () => api.dashboard(datasetId),
    enabled: Boolean(datasetId),
  });
  const patients = useQuery({
    queryKey: ["patients", datasetId],
    queryFn: () => api.patients(datasetId),
    enabled: Boolean(datasetId),
  });
  const molecular = useQuery({
    queryKey: ["molecular-datasets", datasetId],
    queryFn: () => api.molecularDatasets(datasetId),
    enabled: Boolean(datasetId),
  });
  const patientDetail = useQuery({
    queryKey: ["patient", datasetId, selectedPatientId],
    queryFn: () => api.patient(datasetId, selectedPatientId),
    enabled: Boolean(datasetId && selectedPatientId),
  });

  const patientItems = patients.data || dashboard.data?.patients || [];
  const filteredPatients = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return patientItems.slice(0, 120);
    return patientItems.filter((patient) => patientSearchText(patient).includes(needle)).slice(0, 120);
  }, [patientItems, search]);

  return (
    <section className="react-dashboard-layout">
      <div className="section-heading">
        <div>
          <label>Dashboard</label>
          <h2>React workspace dashboard</h2>
          <p className="section-note">
            Workspace: {selectedDatasets.map((dataset) => dataset.name || dataset.dataset_id).join(", ") || datasetId || "none"}.
          </p>
        </div>
        <a className="query-chip" href="/#dashboardTab">Open legacy Dashboard</a>
      </div>

      {dashboard.error ? <div className="query-status">{(dashboard.error as Error).message}</div> : null}
      <ClinicalOverview summary={dashboard.data} loading={dashboard.isLoading} />
      <MolecularOverview datasets={molecular.data?.datasets || []} loading={molecular.isLoading} />

      <div className="react-dashboard-grid">
        <section className="pheno-result-card react-patient-list">
          <div className="section-heading">
            <div>
              <label>Patients</label>
              <h3>{patientItems.length} patients</h3>
            </div>
          </div>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search patients, sex, diseases, treatments" />
          {patients.error ? <div className="query-status">{(patients.error as Error).message}</div> : null}
          <div className="react-patient-card-list">
            {filteredPatients.map((patient) => (
              <button
                key={patient.patient_id}
                type="button"
                className={`patient-card react-patient-card${selectedPatientId === patient.patient_id ? " active" : ""}`}
                onClick={() => setSelectedPatientId(patient.patient_id)}
              >
                <strong>{patient.patient_id}</strong>
                <div>
                  <span className="pill">{patient.visit_count || 0} visits</span>
                  <span className="pill">{patient.sex || "sex n/a"}</span>
                  <span className="pill">{patient.evidence?.diseases?.count || 0} diseases</span>
                </div>
                <small>{dateRange(patient)}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="pheno-result-card react-patient-detail">
          {selectedPatientId ? (
            patientDetail.isLoading ? <div className="empty">Loading patient detail...</div> :
            patientDetail.error ? <div className="query-status">{(patientDetail.error as Error).message}</div> :
            patientDetail.data ? <PatientDetail patient={patientDetail.data} /> : <div className="empty">No detail available.</div>
          ) : (
            <div className="empty">Select a patient to inspect visits and evidence.</div>
          )}
        </section>
      </div>
    </section>
  );
}

function ClinicalOverview({ summary, loading }: { summary?: DashboardSummary; loading: boolean }) {
  const totals = summary?.totals || {};
  const diseases = summary?.top_diseases || [];
  const medications = summary?.top_medications || [];
  return (
    <section className="react-dashboard-overview">
      <MetricCard label="Patients" value={loading ? "..." : totals.patients ?? 0} />
      <MetricCard label="Visits" value={loading ? "..." : totals.visits ?? 0} />
      <MetricCard label="Avg visits" value={loading ? "..." : totals.avg_visits_per_patient ?? 0} />
      <MetricCard label="Source files" value={loading ? "..." : totals.source_files ?? 0} />
      <RankedCard title="Top diseases" items={diseases.map((item) => ({ label: item.disease || item.label || "Unknown", value: item.patient_count || item.value || 0 }))} />
      <RankedCard title="Top medications" items={medications.map((item) => ({ label: item.medication || item.label || "Unknown", value: item.patient_count || item.value || 0 }))} />
    </section>
  );
}

function MolecularOverview({ datasets, loading }: { datasets: MolecularDatasetRecord[]; loading: boolean }) {
  return (
    <section className="pheno-result-card">
      <div className="section-heading">
        <div>
          <label>Molecular</label>
          <h3>{loading ? "Loading molecular datasets" : `${datasets.length} molecular datasets`}</h3>
        </div>
      </div>
      {datasets.length ? (
        <div className="react-molecular-grid">
          {datasets.map((dataset) => (
            <article key={molecularDatasetName(dataset)} className="molecular-dashboard-card">
              <strong>{molecularDatasetName(dataset)}</strong>
              <div className="dataset-card-meta">
                <span>{dataset.sample_count ?? "?"} samples</span>
                <span>{dataset.patient_count ?? "?"} patients</span>
                <span>{dataset.gene_count ?? "?"} genes</span>
              </div>
            </article>
          ))}
        </div>
      ) : <div className="empty">No molecular datasets loaded in this workspace.</div>}
    </section>
  );
}

function PatientDetail({ patient }: { patient: PatientContext }) {
  return (
    <div className="react-patient-detail-body">
      <div>
        <label>Patient workspace</label>
        <h3>{patient.patient_id}</h3>
      </div>
      <div className="dataset-card-meta">
        <span>{patient.sex || "sex n/a"}</span>
        <span>{patient.vital_status || "status n/a"}</span>
        <span>{patient.visits?.length || patient.visit_count || 0} visits</span>
      </div>
      <EvidenceGrid evidence={patient.evidence} />
      <div className="react-visit-list">
        {(patient.visits || []).map((visit) => (
          <article key={visit.visit_id} className="react-visit-card">
            <strong>{visit.visit_id}</strong>
            <span>{visit.event_date || "date n/a"} · {visit.event_type || "event n/a"}</span>
            <p>{visit.diagnosis || visit.disease_label || "No diagnosis label."}</p>
            <EvidenceGrid evidence={visit.evidence} compact />
          </article>
        ))}
      </div>
    </div>
  );
}

function EvidenceGrid({ evidence, compact = false }: { evidence?: EvidenceInventory; compact?: boolean }) {
  const buckets = [
    ["Diseases", evidence?.diseases],
    ["Phenotypes", evidence?.phenotypic_features],
    ["Measures", evidence?.measures],
    ["Treatments", evidence?.treatments],
    ["Procedures", evidence?.procedures],
    ["Exposures", evidence?.exposures],
  ] as const;
  return (
    <div className={compact ? "react-evidence-grid compact" : "react-evidence-grid"}>
      {buckets.map(([label, bucket]) => (
        <div key={label} className="evidence-card">
          <strong>{label}</strong>
          <div>{bucket?.count || 0} items</div>
          {!compact ? <small>{bucket?.examples?.slice(0, 2).join(" | ") || "No examples"}</small> : null}
        </div>
      ))}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function RankedCard({ title, items }: { title: string; items: Array<{ label: string; value: number }> }) {
  return (
    <article className="pheno-result-card react-ranked-card">
      <h3>{title}</h3>
      {items.length ? items.slice(0, 8).map((item) => (
        <div key={item.label} className="react-ranked-row">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      )) : <div className="empty">No data.</div>}
    </article>
  );
}

function patientSearchText(patient: PatientSummary): string {
  return [
    patient.patient_id,
    patient.sex,
    patient.vital_status,
    ...(patient.evidence?.diseases?.examples || []),
    ...(patient.evidence?.treatments?.examples || []),
    ...(patient.dataset_names || []),
  ].join(" ").toLowerCase();
}

function dateRange(patient: PatientSummary): string {
  if (patient.first_event_date && patient.last_event_date && patient.first_event_date !== patient.last_event_date) {
    return `${patient.first_event_date} to ${patient.last_event_date}`;
  }
  return patient.first_event_date || patient.last_event_date || "No dated visits";
}

function molecularDatasetName(dataset: MolecularDatasetRecord): string {
  return dataset.name || dataset.dataset_name || "Molecular dataset";
}
