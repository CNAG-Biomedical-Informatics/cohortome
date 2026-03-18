from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.bff import (
    build_patient_navigator,
    dashboard_summary,
    get_patient_context,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
)
from app.query import answer_query


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = str((BASE_DIR / "data").resolve())

app = FastAPI(title="Patient Navigator BFF MVP")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Patient-Navigator</title>
    <style>
      :root {
        --bg: #f4f8fc;
        --panel: rgba(255, 255, 255, 0.82);
        --panel-strong: rgba(255, 255, 255, 0.96);
        --ink: #132238;
        --muted: #61758c;
        --accent: #2563eb;
        --accent-deep: #1d4ed8;
        --accent-soft: #dbeafe;
        --teal-soft: #e0f2fe;
        --line: rgba(37, 99, 235, 0.12);
        --shadow: 0 18px 46px rgba(15, 23, 42, 0.08);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Palatino Linotype", "Book Antiqua", Georgia, serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(37, 99, 235, 0.12), transparent 26%),
          radial-gradient(circle at bottom right, rgba(14, 165, 233, 0.12), transparent 24%),
          linear-gradient(135deg, #f8fbff 0%, #edf4fb 100%);
        min-height: 100vh;
      }
      main {
        max-width: 1240px;
        margin: 0 auto;
        padding: 36px 20px 52px;
      }
      .hero {
        margin-bottom: 28px;
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 28px;
        background:
          linear-gradient(145deg, rgba(255, 255, 255, 0.96), rgba(240, 247, 255, 0.88));
        box-shadow: var(--shadow);
        position: relative;
        overflow: hidden;
      }
      .hero::after {
        content: "";
        position: absolute;
        inset: auto -50px -60px auto;
        width: 220px;
        height: 220px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(37, 99, 235, 0.16), transparent 65%);
      }
      h1 {
        margin: 0 0 8px;
        font-size: clamp(2.4rem, 5vw, 4.8rem);
        line-height: 0.9;
        letter-spacing: -0.04em;
      }
      p {
        margin: 0;
        color: var(--muted);
        max-width: 760px;
        font-size: 1.05rem;
        line-height: 1.5;
      }
      .controls, .dashboard-shell > section, .detail-shell {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(12px);
      }
      .controls {
        padding: 18px;
        display: grid;
        gap: 12px;
        margin: 20px 0;
      }
      label {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: var(--muted);
      }
      input, button {
        width: 100%;
        padding: 14px 16px;
        border-radius: 16px;
        border: 1px solid var(--line);
        font: inherit;
      }
      input {
        background: rgba(255, 255, 255, 0.82);
      }
      button {
        background: linear-gradient(135deg, var(--accent), var(--accent-deep));
        color: white;
        cursor: pointer;
        border: none;
        font-weight: 700;
        letter-spacing: 0.02em;
        box-shadow: 0 10px 24px rgba(122, 52, 25, 0.2);
      }
      .dashboard-shell {
        display: grid;
        grid-template-columns: 360px minmax(0, 1fr);
        gap: 18px;
        align-items: start;
      }
      .dashboard-shell > section, .detail-shell {
        padding: 22px;
        min-height: 420px;
      }
      h2, h3 {
        margin-top: 0;
        letter-spacing: -0.02em;
      }
      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        margin-bottom: 18px;
      }
      .metric-card {
        background: var(--panel-strong);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 18px;
      }
      .metric-card span {
        display: block;
        color: var(--muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 8px;
      }
      .metric-card strong {
        font-size: 2rem;
        line-height: 1;
      }
      .viz-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
      }
      .viz-card {
        background: var(--panel-strong);
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 18px;
      }
      .viz-card svg {
        width: 100%;
        height: 220px;
        display: block;
      }
      .mini-list {
        margin: 0;
        padding: 0;
        list-style: none;
      }
      .mini-list li {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 10px 0;
        border-bottom: 1px solid var(--line);
      }
      .mini-list li:last-child {
        border-bottom: 0;
      }
      .mini-list small {
        color: var(--muted);
      }
      .patient-card {
        padding: 16px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: var(--panel-strong);
        margin-bottom: 14px;
        cursor: pointer;
        transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
      }
      .patient-card:hover, .patient-card.active {
        border-color: var(--accent);
        background: linear-gradient(145deg, var(--accent-soft), #f8fbff);
        transform: translateY(-2px);
      }
      .patient-card strong {
        display: block;
        font-size: 1.1rem;
        margin-bottom: 8px;
      }
      .pill {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 999px;
        background: #eef4ff;
        font-size: 0.78rem;
        margin-right: 6px;
        margin-bottom: 6px;
      }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 0.85rem;
        background: #f8fbff;
        border-radius: 16px;
        border: 1px solid var(--line);
        padding: 16px;
        overflow: auto;
      }
      .timeline-item {
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 18px;
        margin-bottom: 18px;
        background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(244,248,255,0.98));
      }
      .fragment-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 12px;
        margin-top: 16px;
      }
      .fragment-card {
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 14px;
        background: var(--panel-strong);
      }
      .fragment-card small {
        color: var(--muted);
        display: block;
        margin-top: 6px;
      }
      .workspace-grid {
        display: grid;
        grid-template-columns: 1.1fr 0.9fr;
        gap: 16px;
      }
      .workspace-card {
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 18px;
        background: var(--panel-strong);
      }
      .evidence-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin: 16px 0 20px;
      }
      .evidence-card {
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 14px;
        background: linear-gradient(180deg, #ffffff, #f4f9ff);
      }
      .evidence-card strong {
        display: block;
        margin-bottom: 4px;
      }
      .evidence-card small {
        color: var(--muted);
        line-height: 1.35;
      }
      .empty {
        color: var(--muted);
      }
      .patient-search {
        margin-bottom: 14px;
      }
      .patient-list {
        max-height: 780px;
        overflow: auto;
        padding-right: 4px;
      }
      details {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 14px;
        background: rgba(255,255,255,0.72);
        border: 1px solid var(--line);
      }
      summary {
        cursor: pointer;
        color: var(--accent-deep);
        font-weight: 700;
      }
      #queryReply {
        padding: 16px 18px;
        border-radius: 18px;
        background: linear-gradient(135deg, var(--teal-soft), #f0f9ff);
        border: 1px solid rgba(37, 99, 235, 0.12);
        color: var(--ink);
      }
      .section-note {
        font-size: 0.92rem;
        color: var(--muted);
        margin-bottom: 16px;
      }
      @media (max-width: 900px) {
        .dashboard-shell, .viz-grid, .metrics-grid, .workspace-grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <div class="hero">
        <h1>Patient-Navigator</h1>
        <p>Explore patient timelines, inspect visit evidence, and answer common clinical questions from local records through a compact navigator interface.</p>
      </div>

      <div class="controls">
        <label for="dataDir">Local data directory</label>
        <input id="dataDir" value="/media/mrueda/2TBS/CNAG/Project_PatientNavigator/patient-navigator/data">
        <button id="loadBtn">Load patients</button>
      </div>

      <div class="controls">
        <label for="question">Ask a question</label>
        <input id="question" value="How many patients have Prednisolone?">
        <button id="askBtn">Run query</button>
        <div id="queryReply" class="empty">Ask about medications, diseases, or a patient timeline.</div>
        <details id="queryDetails">
          <summary>Show structured data</summary>
          <pre id="queryData"></pre>
        </details>
      </div>

      <div class="dashboard-shell">
        <section>
          <h2>Cohort</h2>
          <div class="section-note">Search and filter the patient list. The panel stays usable when the cohort grows.</div>
          <input id="patientSearch" class="patient-search" placeholder="Search patient ID">
          <div id="patients" class="patient-list empty">No patients loaded.</div>
        </section>
        <div>
          <section>
            <h2>Dashboard</h2>
            <div class="section-note">Overview metrics and quick cohort patterns to orient large datasets before drilling into one patient.</div>
            <div id="dashboard" class="empty">Load patients to build the dashboard.</div>
          </section>
          <div class="detail-shell" style="margin-top:18px;">
            <h2>Patient Workspace</h2>
            <div class="section-note">Focused patient brief with evidence highlights and key fragments, instead of a full timeline dump.</div>
            <div id="detail" class="empty">Select a patient to inspect the patient workspace.</div>
          </div>
        </div>
      </div>
    </main>

    <script>
      const patientsEl = document.getElementById("patients");
      const dashboardEl = document.getElementById("dashboard");
      const detailEl = document.getElementById("detail");
      const dataDirEl = document.getElementById("dataDir");
      const queryReplyEl = document.getElementById("queryReply");
      const queryDataEl = document.getElementById("queryData");
      const queryDetailsEl = document.getElementById("queryDetails");
      const patientSearchEl = document.getElementById("patientSearch");
      let selectedPatientId = null;
      let currentPatients = [];

      function formatNumber(value) {
        return new Intl.NumberFormat().format(value);
      }

      function renderBarChart(items, labelKey, valueKey, color) {
        if (!items.length) return '<div class="empty">No data.</div>';
        const max = Math.max(...items.map((item) => item[valueKey]), 1);
        const width = 520;
        const rowHeight = 26;
        const height = items.length * rowHeight + 8;
        const bars = items.map((item, index) => {
          const y = index * rowHeight + 4;
          const barWidth = Math.max(8, (item[valueKey] / max) * 300);
          return `
            <text x="0" y="${y + 14}" fill="#61758c" font-size="12">${item[labelKey]}</text>
            <rect x="190" y="${y}" width="${barWidth}" height="16" rx="8" fill="${color}"></rect>
            <text x="${200 + barWidth}" y="${y + 13}" fill="#132238" font-size="12">${item[valueKey]}</text>
          `;
        }).join("");
        return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMinYMin meet">${bars}</svg>`;
      }

      function renderDonutChart(entries, colors) {
        const items = Object.entries(entries || {});
        if (!items.length) return '<div class="empty">No data.</div>';
        const total = items.reduce((sum, [, value]) => sum + value, 0) || 1;
        let acc = 0;
        const cx = 110;
        const cy = 110;
        const r = 72;
        const stroke = 24;
        const arcs = items.map(([label, value], index) => {
          const start = (acc / total) * Math.PI * 2;
          acc += value;
          const end = (acc / total) * Math.PI * 2;
          const x1 = cx + r * Math.cos(start - Math.PI / 2);
          const y1 = cy + r * Math.sin(start - Math.PI / 2);
          const x2 = cx + r * Math.cos(end - Math.PI / 2);
          const y2 = cy + r * Math.sin(end - Math.PI / 2);
          const largeArc = end - start > Math.PI ? 1 : 0;
          return `<path d="M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}" fill="none" stroke="${colors[index % colors.length]}" stroke-width="${stroke}" stroke-linecap="round"></path>`;
        }).join("");
        const legend = items.map(([label, value], index) => `
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="width:10px;height:10px;border-radius:50%;background:${colors[index % colors.length]};display:inline-block;"></span>
            <small>${label}: ${value}</small>
          </div>
        `).join("");
        return `<div style="display:grid;grid-template-columns:220px 1fr;gap:10px;align-items:center;">
          <svg viewBox="0 0 220 220">
            ${arcs}
            <circle cx="${cx}" cy="${cy}" r="46" fill="white"></circle>
            <text x="${cx}" y="${cy - 2}" text-anchor="middle" fill="#132238" font-size="26" font-weight="700">${total}</text>
            <text x="${cx}" y="${cy + 20}" text-anchor="middle" fill="#61758c" font-size="12">patients</text>
          </svg>
          <div>${legend}</div>
        </div>`;
      }

      function renderDashboard(summary) {
        const meds = summary.top_medications.map((item) => ({ label: item.medication, value: item.patient_count }));
        const diseases = summary.top_diseases.map((item) => ({ label: item.disease, value: item.patient_count }));
        const visitDist = Object.entries(summary.visit_distribution).map(([label, value]) => ({ label, value }));
        dashboardEl.innerHTML = `
          <div class="metrics-grid">
            <div class="metric-card"><span>Patients</span><strong>${formatNumber(summary.totals.patients)}</strong></div>
            <div class="metric-card"><span>Visits</span><strong>${formatNumber(summary.totals.visits)}</strong></div>
            <div class="metric-card"><span>Avg Visits</span><strong>${summary.totals.avg_visits_per_patient}</strong></div>
            <div class="metric-card"><span>Files</span><strong>${formatNumber(summary.totals.source_files)}</strong></div>
          </div>
          <div class="viz-grid">
            <div class="viz-card">
              <h3>Sex Distribution</h3>
              ${renderDonutChart(summary.sex_counts, ["#2563eb", "#0ea5e9", "#7c3aed", "#94a3b8"])}
            </div>
            <div class="viz-card">
              <h3>Visits Per Patient</h3>
              ${renderBarChart(visitDist, "label", "value", "#60a5fa")}
            </div>
            <div class="viz-card">
              <h3>Top Medications</h3>
              ${renderBarChart(meds, "label", "value", "#2563eb")}
            </div>
            <div class="viz-card">
              <h3>Top Diseases</h3>
              ${renderBarChart(diseases, "label", "value", "#0ea5e9")}
            </div>
          </div>
        `;
      }

      function renderEvidence(evidence) {
        const labels = [
          ["diseases", "Diseases"],
          ["phenotypic_features", "Phenotypes"],
          ["measures", "Measures"],
          ["treatments", "Treatments"],
          ["procedures", "Procedures"],
          ["exposures", "Exposures"],
        ];

        return `
          <div class="evidence-grid">
            ${labels.map(([key, label]) => {
              const bucket = evidence[key];
              const examples = (bucket.examples || []).slice(0, 2).join(" | ") || "No examples";
              return `
                <div class="evidence-card">
                  <strong>${label}</strong>
                  <div>${bucket.count} items</div>
                  <small>${examples}</small>
                </div>
              `;
            }).join("")}
          </div>
        `;
      }

      function summaryCard(patient) {
        const activeClass = selectedPatientId === patient.patient_id ? "active" : "";
        return `
          <div class="patient-card ${activeClass}" data-patient-id="${patient.patient_id}">
            <strong>${patient.patient_id}</strong>
            <div>
              <span class="pill">${patient.visit_count} visits</span>
              <span class="pill">${patient.sex || "sex: n/a"}</span>
              <span class="pill">${patient.evidence.diseases.count} diseases</span>
            </div>
            <small>${patient.first_event_date || "?"} to ${patient.last_event_date || "?"}</small>
          </div>
        `;
      }

      function renderPatientList(items) {
        if (!items.length) {
          patientsEl.innerHTML = '<div class="empty">No patients match the current filter.</div>';
          return;
        }
        patientsEl.innerHTML = items.map(summaryCard).join("");
        patientsEl.querySelectorAll(".patient-card").forEach((node) => {
          node.addEventListener("click", () => loadPatient(node.dataset.patientId));
        });
      }

      function renderDetail(patient) {
        const fragments = (patient.key_fragments || []).map((fragment) => `
          <div class="fragment-card">
            <strong>${fragment.label}</strong>
            <div><span class="pill">${fragment.category}</span><span class="pill">${fragment.visit_id}</span></div>
            <small>${fragment.source_file}#${fragment.record_index} · ${fragment.path}</small>
          </div>
        `).join("");

        const visits = (patient.visits || []).slice(0, 8).map((visit) => `
          <li>
            <div>
              <strong>${visit.visit_id}</strong>
              <small>${visit.event_date || "undated"} · ${visit.diagnosis || visit.event_type || "event"}</small>
            </div>
            <span>${visit.key_fragments.length} fragments</span>
          </li>
        `).join("");

        detailEl.innerHTML = `
          <div class="workspace-grid">
            <div class="workspace-card">
              <p><strong>${patient.patient_id}</strong></p>
              <p>Sex: ${patient.patient_context.sex || "n/a"} | DOB: ${patient.patient_context.date_of_birth || "n/a"} | Vital status: ${patient.patient_context.vital_status || "n/a"}</p>
              <p>Sources: ${(patient.patient_context.source_files || []).join(", ") || "n/a"}</p>
              <h3>Available evidence</h3>
              ${renderEvidence(patient.evidence)}
            </div>
            <div class="workspace-card">
              <h3>Visit Overview</h3>
              <ul class="mini-list">${visits || '<li><small>No visits found.</small></li>'}</ul>
            </div>
          </div>
          <div class="workspace-card" style="margin-top:16px;">
            <h3>Key Fragments</h3>
            <div class="fragment-grid">${fragments || '<div class="empty">No key fragments available.</div>'}</div>
            <details>
              <summary>Show full structured patient data</summary>
              <pre>${JSON.stringify(patient, null, 2)}</pre>
            </details>
          </div>
        `;
      }

      async function loadPatients() {
        const dataDir = encodeURIComponent(dataDirEl.value.trim());
        const [patientResponse, dashboardResponse] = await Promise.all([
          fetch(`/patients?data_dir=${dataDir}`),
          fetch(`/dashboard?data_dir=${dataDir}`)
        ]);
        if (!patientResponse.ok) {
          const error = await patientResponse.json();
          patientsEl.innerHTML = `<div class="empty">${error.detail}</div>`;
          detailEl.innerHTML = '<div class="empty">Fix the data directory and try again.</div>';
          dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
          return;
        }

        const patients = await patientResponse.json();
        currentPatients = patients;
        if (dashboardResponse.ok) {
          renderDashboard(await dashboardResponse.json());
        } else {
          dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
        }
        if (!patients.length) {
          patientsEl.innerHTML = '<div class="empty">No patient records found in the selected directory.</div>';
          detailEl.innerHTML = '<div class="empty">No timeline to display.</div>';
          dashboardEl.innerHTML = '<div class="empty">No dashboard to display.</div>';
          return;
        }

        renderPatientList(filterPatients(patientSearchEl.value));

        if (!selectedPatientId) {
          await loadPatient(patients[0].patient_id);
        }
      }

      function filterPatients(query) {
        const value = (query || "").trim().toLowerCase();
        if (!value) return currentPatients;
        return currentPatients.filter((patient) => patient.patient_id.toLowerCase().includes(value));
      }

      async function loadPatient(patientId) {
        selectedPatientId = patientId;
        const dataDir = encodeURIComponent(dataDirEl.value.trim());
        const response = await fetch(`/patients/${patientId}/navigator?data_dir=${dataDir}`);
        if (!response.ok) {
          const error = await response.json();
          detailEl.innerHTML = `<div class="empty">${error.detail}</div>`;
          return;
        }
        const patient = await response.json();
        renderDetail(patient);
        await loadPatients();
      }

      async function askQuery() {
        const dataDir = encodeURIComponent(dataDirEl.value.trim());
        const question = encodeURIComponent(document.getElementById("question").value.trim());
        const response = await fetch(`/query?data_dir=${dataDir}&q=${question}`);
        if (!response.ok) {
          const error = await response.json();
          queryReplyEl.textContent = error.detail;
          queryDataEl.textContent = "";
          queryDetailsEl.open = false;
          return;
        }
        const payload = await response.json();
        queryReplyEl.textContent = payload.reply;
        queryDataEl.textContent = JSON.stringify(payload.data, null, 2);
        queryDetailsEl.open = false;
      }

      document.getElementById("loadBtn").addEventListener("click", loadPatients);
      document.getElementById("askBtn").addEventListener("click", askQuery);
      patientSearchEl.addEventListener("input", () => renderPatientList(filterPatients(patientSearchEl.value)));
    </script>
  </body>
</html>
"""


@app.get("/patients")
def get_patients(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> List[Dict]:
    try:
        patients = list_patient_summaries(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [patient.model_dump() for patient in patients]


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        patient = get_patient_context(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return patient.model_dump()


@app.get("/patients/{patient_id}/navigator")
def get_patient_navigator(patient_id: str, data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        navigator = build_patient_navigator(data_dir, patient_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if navigator is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return navigator.model_dump()


@app.get("/cohorts/medications")
def get_medication_counts(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> List[Dict]:
    try:
        return medication_counts(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/cohorts/medications/search")
def search_medication_cohort(
    medication: str = Query(..., min_length=1),
    data_dir: str = Query(default=DEFAULT_DATA_DIR),
) -> Dict:
    try:
        return medication_cohort(data_dir, medication)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/query")
def query_app(
    q: str = Query(..., min_length=1),
    data_dir: str = Query(default=DEFAULT_DATA_DIR),
) -> Dict:
    try:
        return answer_query(data_dir, q)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/dashboard")
def get_dashboard(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        return dashboard_summary(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
