from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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


class QueryTurn(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    q: str
    data_dir: str = DEFAULT_DATA_DIR
    history: List[QueryTurn] = Field(default_factory=list)


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
      .tab-bar {
        display: flex;
        gap: 10px;
        margin: 20px 0 18px;
      }
      .tab-btn {
        width: auto;
        padding: 12px 18px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.82);
        color: var(--ink);
        box-shadow: none;
      }
      .tab-btn.active {
        background: linear-gradient(135deg, var(--accent), var(--accent-deep));
        color: white;
      }
      .tab-panel {
        display: none;
      }
      .tab-panel.active {
        display: block;
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
      .query-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 10px;
        align-items: center;
      }
      .query-row button {
        width: auto;
        min-width: 120px;
        padding: 12px 16px;
        border-radius: 999px;
      }
      .query-status {
        min-height: 20px;
        font-size: 0.92rem;
        color: var(--muted);
        font-weight: 600;
      }
      .query-status.loading {
        color: var(--accent-deep);
      }
      .load-status {
        min-height: 20px;
        font-size: 0.92rem;
        color: var(--muted);
        font-weight: 600;
      }
      .load-status.loading {
        color: var(--accent-deep);
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
        padding: 14px 16px;
        border-radius: 18px;
        min-height: 72px;
        background: linear-gradient(135deg, var(--teal-soft), #f0f9ff);
        border: 1px solid rgba(37, 99, 235, 0.12);
        color: var(--ink);
      }
      #queryReply p,
      #queryReply ul {
        margin: 0 0 10px;
      }
      #queryReply p:last-child,
      #queryReply ul:last-child {
        margin-bottom: 0;
      }
      #queryReply ul {
        padding-left: 20px;
      }
      #queryReply code {
        padding: 2px 6px;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid var(--line);
        font-size: 0.92em;
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

      <div class="tab-bar">
        <button id="cohortTabBtn" class="tab-btn active" type="button">Cohort</button>
        <button id="queryTabBtn" class="tab-btn" type="button">Query</button>
      </div>

      <section id="cohortTab" class="tab-panel active">
        <div class="controls">
          <label for="dataDir">Local data directory</label>
          <input id="dataDir" value="/media/mrueda/2TBS/CNAG/Project_PatientNavigator/patient-navigator/data">
          <button id="loadBtn" type="button">Load patients</button>
          <div id="loadStatus" class="load-status">Choose a folder and click Load patients.</div>
        </div>

          <section>
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
          </section>
      </section>

      <section id="queryTab" class="tab-panel">
        <div class="controls">
          <label for="question">Ask a question</label>
          <div class="query-row">
            <input id="question" value="How many patients have Prednisolone?">
            <button id="askBtn" type="button">Run query</button>
          </div>
          <div id="queryStatus" class="query-status">Press Enter or click Run query.</div>
          <div id="queryReply" class="empty">Ask about medications, diseases, or a patient timeline.</div>
          <details id="queryDetails">
            <summary>Show structured data</summary>
            <pre id="queryData"></pre>
          </details>
        </div>
      </section>
    </main>

    <script>
      const cohortTabBtnEl = document.getElementById("cohortTabBtn");
      const queryTabBtnEl = document.getElementById("queryTabBtn");
      const cohortTabEl = document.getElementById("cohortTab");
      const queryTabEl = document.getElementById("queryTab");
      const patientsEl = document.getElementById("patients");
      const dashboardEl = document.getElementById("dashboard");
      const detailEl = document.getElementById("detail");
      const dataDirEl = document.getElementById("dataDir");
      const loadStatusEl = document.getElementById("loadStatus");
      const queryReplyEl = document.getElementById("queryReply");
      const queryStatusEl = document.getElementById("queryStatus");
      const queryDataEl = document.getElementById("queryData");
      const queryDetailsEl = document.getElementById("queryDetails");
      const questionEl = document.getElementById("question");
      const askBtnEl = document.getElementById("askBtn");
      const loadBtnEl = document.getElementById("loadBtn");
      const patientSearchEl = document.getElementById("patientSearch");
      const MAX_VISIBLE_PATIENTS = 80;
      let selectedPatientId = null;
      let currentPatients = [];
      let queryInFlight = false;
      let loadInFlight = false;

      function setActiveTab(tabName) {
        const showCohort = tabName === "cohort";
        cohortTabBtnEl.classList.toggle("active", showCohort);
        queryTabBtnEl.classList.toggle("active", !showCohort);
        cohortTabEl.classList.toggle("active", showCohort);
        queryTabEl.classList.toggle("active", !showCohort);
      }

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
        const visibleItems = items.slice(0, MAX_VISIBLE_PATIENTS);
        const summary = items.length > MAX_VISIBLE_PATIENTS
          ? `<div class="section-note">Showing first ${MAX_VISIBLE_PATIENTS} of ${items.length} matching patients. Use search to narrow the list.</div>`
          : "";
        patientsEl.innerHTML = summary + visibleItems.map(summaryCard).join("");
      }

      function renderDetail(patient) {
        const previewPayload = {
          patient_id: patient.patient_id,
          summary: patient.summary,
          patient_context: patient.patient_context,
          evidence: patient.evidence,
          key_fragments: (patient.key_fragments || []).slice(0, 12).map((fragment) => ({
            category: fragment.category,
            label: fragment.label,
            visit_id: fragment.visit_id,
            event_type: fragment.event_type,
            event_date: fragment.event_date,
            source_file: fragment.source_file,
            record_index: fragment.record_index,
            path: fragment.path,
          })),
          visits: (patient.visits || []).slice(0, 8).map((visit) => ({
            visit_id: visit.visit_id,
            event_type: visit.event_type,
            event_date: visit.event_date,
            diagnosis: visit.diagnosis,
            evidence: visit.evidence,
            key_fragments: (visit.key_fragments || []).slice(0, 6).map((fragment) => ({
              category: fragment.category,
              label: fragment.label,
              path: fragment.path,
            })),
          })),
        };
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
              <summary>Show structured patient preview</summary>
              <pre>${JSON.stringify(previewPayload, null, 2)}</pre>
            </details>
          </div>
        `;
      }

      function escapeHtml(value) {
        return String(value)
          .split("&").join("&amp;")
          .split("<").join("&lt;")
          .split(">").join("&gt;")
          .split('"').join("&quot;")
          .split("'").join("&#39;");
      }

      function renderInlineCode(value) {
        const parts = String(value).split("`");
        return parts.map((part, index) => {
          if (index % 2 === 1) {
            return `<code>${escapeHtml(part)}</code>`;
          }
          return escapeHtml(part);
        }).join("");
      }

      function renderQueryReply(value) {
        const blocks = String(value || "").split("\\r\\n").join("\\n").split("\\n\\n");
        return blocks.map((block) => {
          const lines = block.split("\\n").map((line) => line.trim()).filter(Boolean);
          if (!lines.length) {
            return "";
          }
          if (lines.every((line) => line.startsWith("- "))) {
            return `<ul>${lines.map((line) => `<li>${renderInlineCode(line.slice(2))}</li>`).join("")}</ul>`;
          }
          return `<p>${lines.map((line) => renderInlineCode(line)).join("<br>")}</p>`;
        }).join("");
      }

      function nextFrame() {
        return new Promise((resolve) => {
          window.requestAnimationFrame(() => resolve());
        });
      }

      async function loadPatients() {
        if (loadInFlight) {
          return;
        }
        loadInFlight = true;
        loadBtnEl.disabled = true;
        loadStatusEl.className = "load-status loading";
        loadStatusEl.textContent = "Loading patients and dashboard...";
        await nextFrame();

        try {
          const dataDir = encodeURIComponent(dataDirEl.value.trim());
          const patientResponse = await fetch(`/patients?data_dir=${dataDir}`);
          if (!patientResponse.ok) {
            const error = await patientResponse.json();
            patientsEl.innerHTML = `<div class="empty">${error.detail}</div>`;
            detailEl.innerHTML = '<div class="empty">Fix the data directory and try again.</div>';
            dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
            loadStatusEl.className = "load-status";
            loadStatusEl.textContent = "Load failed.";
            return;
          }

          const patients = await patientResponse.json();
          currentPatients = patients;
          if (!patients.length) {
            selectedPatientId = null;
            patientsEl.innerHTML = '<div class="empty">No patient records found in the selected directory.</div>';
            detailEl.innerHTML = '<div class="empty">No timeline to display.</div>';
            dashboardEl.innerHTML = '<div class="empty">No dashboard to display.</div>';
            loadStatusEl.className = "load-status";
            loadStatusEl.textContent = "No patients found.";
            return;
          }

          renderPatientList(filterPatients(patientSearchEl.value));
          selectedPatientId = null;
          detailEl.innerHTML = '<div class="empty">Select a patient to inspect the patient workspace.</div>';
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = `Loaded ${patients.length} patients.`;

          dashboardEl.innerHTML = '<div class="empty">Loading dashboard...</div>';
          window.setTimeout(() => {
            fetch(`/dashboard?data_dir=${dataDir}`)
            .then(async (response) => {
              if (!response.ok) {
                dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
                return;
              }
              renderDashboard(await response.json());
            })
            .catch(() => {
              dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
            });
          }, 0);
        } catch (error) {
          patientsEl.innerHTML = '<div class="empty">Unable to load patients.</div>';
          detailEl.innerHTML = '<div class="empty">Patient workspace unavailable.</div>';
          dashboardEl.innerHTML = '<div class="empty">Dashboard unavailable.</div>';
          loadStatusEl.className = "load-status";
          loadStatusEl.textContent = error && error.message ? error.message : "Load failed.";
        } finally {
          loadInFlight = false;
          loadBtnEl.disabled = false;
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
        renderPatientList(filterPatients(patientSearchEl.value));
      }

      async function askQuery() {
        if (queryInFlight) {
          return;
        }
        const dataDir = encodeURIComponent(dataDirEl.value.trim());
        const question = questionEl.value.trim();
        if (!question) {
          queryStatusEl.textContent = "Enter a question first.";
          return;
        }
        queryInFlight = true;
        askBtnEl.disabled = true;
        queryStatusEl.className = "query-status loading";
        queryStatusEl.textContent = "Running query. Waiting for response...";
        queryReplyEl.innerHTML = "<p><strong>Running query...</strong><br>Please wait.</p>";
        await nextFrame();

        try {
          const response = await fetch(`/query?data_dir=${dataDir}&q=${encodeURIComponent(question)}`);
          if (!response.ok) {
            const error = await response.json();
            queryReplyEl.innerHTML = `<p>${escapeHtml(error.detail)}</p>`;
            queryDataEl.textContent = "";
            queryDetailsEl.open = false;
            queryStatusEl.className = "query-status";
            queryStatusEl.textContent = "Query failed.";
            return;
          }
          const payload = await response.json();
          queryReplyEl.innerHTML = renderQueryReply(payload.reply);
          queryDataEl.textContent = JSON.stringify(payload.data, null, 2);
          queryDetailsEl.open = false;
          queryStatusEl.className = "query-status";
          queryStatusEl.textContent = "Done.";
        } catch (error) {
          queryReplyEl.innerHTML = `<p>${escapeHtml(error && error.message ? error.message : "Request failed.")}</p>`;
          queryDataEl.textContent = "";
          queryDetailsEl.open = false;
          queryStatusEl.className = "query-status";
          queryStatusEl.textContent = "Network error.";
        } finally {
          queryInFlight = false;
          askBtnEl.disabled = false;
        }
      }

      loadBtnEl.addEventListener("click", loadPatients);
      askBtnEl.addEventListener("click", askQuery);
      cohortTabBtnEl.addEventListener("click", () => setActiveTab("cohort"));
      queryTabBtnEl.addEventListener("click", () => setActiveTab("query"));
      window.__patientNavigatorLoadPatients = loadPatients;
      window.__patientNavigatorAskQuery = askQuery;
      patientsEl.addEventListener("click", (event) => {
        const card = event.target.closest(".patient-card");
        if (!card || !patientsEl.contains(card)) {
          return;
        }
        loadPatient(card.dataset.patientId);
      });
      questionEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          askQuery();
        }
      });
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


@app.post("/query")
def query_app_post(request: QueryRequest) -> Dict:
    try:
        return answer_query(
            request.data_dir,
            request.q,
            history=[turn.model_dump() for turn in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/dashboard")
def get_dashboard(data_dir: str = Query(default=DEFAULT_DATA_DIR)) -> Dict:
    try:
        return dashboard_summary(data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
