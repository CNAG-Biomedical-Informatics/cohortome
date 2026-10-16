import { formatAssayModality, formatAssayDataType } from "./assay_labels.js";
import { fallbackCopyText } from "./shared.js";
import { createTimelineUi } from "./timeline.js";

export function createDashboardUi(ctx) {
  const { refs, helpers, callbacks, state, constants } = ctx;
  const {
    patientsEl,
    patientSearchEl,
    dashboardEl,
    dashboardTimelineEl,
    detailEl,
    dataDirEl,
    assayDashboardStatusEl,
    assayDashboardOverviewEl,
    assayModalityTabsEl,
    assayDashboardCardsEl,
    multimodalReadinessPanelEl,
    multimodalReadinessStatusEl,
    multimodalReadinessContentEl,
    multimodalMatrixPanelEl,
    multimodalMatrixStatusEl,
    multimodalMatrixContentEl,
    dicomDashboardPanelEl,
    dicomDashboardHealthEl,
    dicomDashboardStatusEl,
    dicomDashboardStudiesEl,
    transcriptomicsQuickExpressionPanelEl,
    analysisAssayDatasetListEl,
    analysisCatalogAssayDatasetListEl,
    analysisAssayGeneEl,
    analysisAssayGenesEl,
    analysisAssayStatusEl,
    analysisCatalogAssayStatusEl,
    analysisAssayResultEl,
    analysisSelectedPatientIdsEl,
    analysisSelectedPatientIdsSummaryEl,
    analysisSelectedSavedCohortSelectionEl,
    analysisCompareModeEl,
    analysisCompareSelectedPatientIdsEl,
    analysisCompareSelectedPatientIdsSummaryEl,
    analysisCompareSavedCohortSelectionEl,
  } = refs;
  const { escapeHtml, formatNumber } = helpers;
  const {
    renderGlobalContext,
    syncCurrentAnalysisSessionFromUi,
    isMultiDatasetWorkspace,
    sendPatientIdsToAnalysis,
    saveIdsAsCohort,
    sendPromptToAnalysis,
    renderAnalysisCatalog,
    renderAnalysisCatalogAssayPanel,
    setDashboardSubtab,
  } = callbacks;
  const { MAX_VISIBLE_PATIENTS } = constants;
  const DASHBOARD_PLOT_COLORS = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed", "#ea580c", "#dc2626"];
  const { renderDashboardTimeline, timelinePanelMarkup } = createTimelineUi({
    state, refs,
    helpers: { escapeHtml, clinicalRepresentation, normalizedClarid,
      claridIdentityMarkup, dashboardPlotLayout, mountPlot },
    callbacks: {
      refreshPatientList: () => renderPatientList(currentRosterPatients()),
      saveIdsAsCohort, sendPatientIdsToAnalysis, handleClaridAction,
    },
  });

  function isCurrentWorkspaceScope(scopeId) {
    const normalized = String(scopeId || "").trim();
    return Boolean(normalized && normalized === String(state.currentDatasetScopeId || "").trim());
  }

  function clinicalRepresentation(payload = null) {
    const direct = String(payload && payload.clinical_representation ? payload.clinical_representation : "").trim().toLowerCase();
    if (direct) return direct;
    const activeIds = new Set(Array.isArray(state.currentDatasetIds) ? state.currentDatasetIds : []);
    const values = (Array.isArray(state.availableDatasets) ? state.availableDatasets : [])
      .filter((item) => activeIds.has(String(item && item.dataset_id ? item.dataset_id : "")))
      .map((item) => String(item && item.clinical_representation ? item.clinical_representation : "unspecified").trim().toLowerCase());
    return values.length && values.every((value) => value === values[0]) ? values[0] : "mixed";
  }

  function clinicalRecordLabel(payload, count, capitalize = false) {
    const representation = clinicalRepresentation(payload);
    const singular = representation === "snapshot" ? "timepoint" : representation === "person" ? "person record" : "clinical record";
    const label = Number(count) === 1 ? singular : `${singular}s`;
    return capitalize ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : label;
  }

  function plotlyAvailable() {
    return typeof window !== "undefined" && window.Plotly && typeof window.Plotly.newPlot === "function";
  }

  function dashboardPlotConfig() {
    return {
      displayModeBar: false,
      displaylogo: false,
      responsive: true,
    };
  }

  function dashboardPlotLayout(overrides) {
    return {
      margin: { t: 24, r: 18, b: 56, l: 56 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "#f8fbff",
      font: { family: "inherit", color: "#132238", size: 12 },
      xaxis: {
        automargin: true,
        gridcolor: "rgba(148,163,184,0.2)",
        zeroline: false,
        linecolor: "#cbd5e1",
        tickfont: { color: "#61758c" },
      },
      yaxis: {
        automargin: true,
        gridcolor: "rgba(148,163,184,0.2)",
        zeroline: false,
        linecolor: "#cbd5e1",
        tickfont: { color: "#61758c" },
      },
      legend: {
        orientation: "h",
        yanchor: "bottom",
        y: 1.02,
        xanchor: "left",
        x: 0,
      },
      hoverlabel: { bgcolor: "#132238", font: { color: "#f8fafc" } },
      ...overrides,
    };
  }

  function mountPlot(targetId, traces, layout, afterPlot, configOverrides = {}) {
    const el = document.getElementById(targetId);
    if (!el) return;
    if (!plotlyAvailable()) {
      el.innerHTML = '<div class="empty">Plot rendering unavailable.</div>';
      return;
    }
    const plotResult = window.CohortomeTheme.newPlot(el, traces, layout, { ...dashboardPlotConfig(), ...configOverrides });
    if (typeof afterPlot === "function") {
      Promise.resolve(plotResult).then(() => afterPlot(el)).catch(() => {});
    }
    window.requestAnimationFrame(() => {
      if (window.Plotly && window.Plotly.Plots && typeof window.Plotly.Plots.resize === "function") {
        window.Plotly.Plots.resize(el);
      }
    });
  }

  function currentRosterPatients() {
    const query = String(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : "").trim().toLowerCase();
    const patients = Array.isArray(state.currentPatients) ? state.currentPatients : [];
    if (!query) return patients;
    return patients.filter((patient) => patientMatchesIdentityQuery(patient, query));
  }

  function normalizedClarid(patient) {
    const value = patient && patient.clarid && typeof patient.clarid === "object" ? patient.clarid : null;
    if (!value || !String(value.human_id || "").trim() || !String(value.stub_id || "").trim()) return null;
    return value;
  }

  function patientMatchesIdentityQuery(patient, rawQuery) {
    const query = String(rawQuery || "").trim().toLowerCase();
    if (!query) return true;
    const clarid = normalizedClarid(patient);
    return [
      patient && patient.patient_id,
      clarid && clarid.human_id,
      clarid && clarid.stub_id,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  }

  function claridDecodedSummary(clarid) {
    if (!clarid) return "";
    const condition = clarid.condition_name
      ? `${clarid.condition_name} (${clarid.condition})` : clarid.condition;
    return [clarid.study, clarid.type, condition, clarid.sex, clarid.age_group]
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .join(" · ");
  }

  function claridIdentityMarkup(patient, compact = false) {
    const clarid = normalizedClarid(patient);
    if (!clarid) return "";
    const decoded = claridDecodedSummary(clarid);
    const subjectId = String(clarid.subject_id ?? "").trim();
    const version = [
      clarid.codebook_version ? `Codebook ${clarid.codebook_version}` : "",
      clarid.tools_version ? `Tools ${clarid.tools_version}` : "",
    ].filter(Boolean).join(" · ");
    return `
      <span class="clarid-identity${compact ? " is-compact" : ""}">
        <button type="button" class="clarid-badge" data-clarid-toggle aria-expanded="false" title="Show decoded ClarID metadata">
          ClarID
        </button>
        <span class="clarid-popover" role="dialog" aria-label="Decoded ClarID metadata">
          <strong>ClarID subject${subjectId ? ` ${escapeHtml(subjectId)}` : ""}</strong>
          <span class="clarid-decoded-summary">${escapeHtml(decoded || "Decoded subject metadata")}</span>
          <span class="clarid-code-row"><b>Human</b><code>${escapeHtml(clarid.human_id)}</code><button type="button" data-clarid-copy="${escapeHtml(clarid.human_id)}" aria-label="Copy human-readable ClarID">Copy</button></span>
          <span class="clarid-code-row"><b>Stub</b><code>${escapeHtml(clarid.stub_id)}</code><button type="button" data-clarid-copy="${escapeHtml(clarid.stub_id)}" aria-label="Copy ClarID stub">Copy</button></span>
          ${version ? `<small>${escapeHtml(version)}</small>` : ""}
        </span>
      </span>
    `;
  }

  function claridSearchFeedback(items) {
    const query = String(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : "").trim().toLowerCase();
    if (!query) return "";
    const match = items.find((patient) => {
      const clarid = normalizedClarid(patient);
      return clarid && [clarid.human_id, clarid.stub_id].some((value) => String(value || "").toLowerCase() === query);
    });
    if (!match) return "";
    const clarid = normalizedClarid(match);
    return `<div class="clarid-search-feedback" role="status"><strong>ClarID recognized</strong><span>${escapeHtml(claridDecodedSummary(clarid))}</span><span>Patient ${escapeHtml(match.patient_id)}</span></div>`;
  }

  function normalizeRankedItems(items, labelKey) {
    return (Array.isArray(items) ? items : []).map((item) => {
      if (Array.isArray(item)) {
        return { label: String(item[0] || "Unknown"), value: Number(item[1] || 0) };
      }
      return {
        label: String(item[labelKey] || item.label || "Unknown"),
        value: Number(item.patient_count || item.value || 0),
      };
    });
  }

  function renderDashboardCharts(summary) {
    const sexCounts = summary && summary.sex_counts ? summary.sex_counts : {};
    const visitDistribution = summary && summary.visit_distribution ? summary.visit_distribution : {};
    const topDiseases = normalizeRankedItems(summary && summary.top_diseases, "disease").slice(0, 8);
    const topMedications = normalizeRankedItems(summary && summary.top_medications ? summary.top_medications : summary && summary.top_treatments, "medication").slice(0, 8);
    const diseaseMedicationMatrix = summary && summary.disease_medication_matrix ? summary.disease_medication_matrix : {};

    const sexEntries = Object.entries(sexCounts);
    if (sexEntries.length) {
      mountPlot(
        "dashboard-plot-sex",
        [{
          type: "pie",
          labels: sexEntries.map(([label]) => label),
          values: sexEntries.map(([, value]) => Number(value || 0)),
          hole: 0.45,
          meta: { cohortome_group: sexEntries.map((_, index) => index) },
          marker: { colors: DASHBOARD_PLOT_COLORS },
          textinfo: "label+percent",
          hovertemplate: "%{label}: %{value}<extra></extra>",
        }],
        dashboardPlotLayout({
          margin: { t: 10, r: 10, b: 10, l: 10 },
          showlegend: false,
        })
      );
    }

    const visitEntries = Object.entries(visitDistribution);
    const snapshotRepresentation = clinicalRepresentation(summary) === "snapshot";
    if (visitEntries.length) {
      mountPlot(
        "dashboard-plot-visits",
        [{
          type: "bar",
          x: visitEntries.map(([label]) => label),
          y: visitEntries.map(([, value]) => Number(value || 0)),
          marker: { color: "#7c3aed" },
          hovertemplate: snapshotRepresentation ? "%{x} visits: %{y}<extra></extra>" : "%{x} records: %{y}<extra></extra>",
        }],
        dashboardPlotLayout({
          xaxis: { ...dashboardPlotLayout().xaxis, title: { text: snapshotRepresentation ? "Visits per patient bucket" : "Clinical records per patient", font: { color: "#61758c", size: 12 } } },
          yaxis: { ...dashboardPlotLayout().yaxis, title: { text: "Patients", font: { color: "#61758c", size: 12 } } },
        })
      );
    }

    if (topDiseases.length) {
      mountPlot(
        "dashboard-plot-diseases",
        [{
          type: "bar",
          orientation: "h",
          y: topDiseases.map((item) => item.label),
          x: topDiseases.map((item) => item.value),
          meta: { cohortome_group: topDiseases.map((_, index) => index) },
          marker: { color: topDiseases.map((_, index) => DASHBOARD_PLOT_COLORS[index % DASHBOARD_PLOT_COLORS.length]) },
          hovertemplate: "%{y}: %{x}<extra></extra>",
        }],
        dashboardPlotLayout({ margin: { t: 16, r: 16, b: 32, l: 150 } })
      );
    }

    if (topMedications.length) {
      mountPlot(
        "dashboard-plot-medications",
        [{
          type: "bar",
          orientation: "h",
          y: topMedications.map((item) => item.label),
          x: topMedications.map((item) => item.value),
          meta: { cohortome_group: topMedications.map((_, index) => index + 1) },
          marker: { color: topMedications.map((_, index) => DASHBOARD_PLOT_COLORS[(index + 1) % DASHBOARD_PLOT_COLORS.length]) },
          hovertemplate: "%{y}: %{x}<extra></extra>",
        }],
        dashboardPlotLayout({ margin: { t: 16, r: 16, b: 32, l: 150 } })
      );
    }

    const matrixDiseases = Array.isArray(diseaseMedicationMatrix.diseases) ? diseaseMedicationMatrix.diseases : [];
    const matrixMedications = Array.isArray(diseaseMedicationMatrix.medications) ? diseaseMedicationMatrix.medications : [];
    const matrixValues = Array.isArray(diseaseMedicationMatrix.values) ? diseaseMedicationMatrix.values : [];
    if (matrixDiseases.length && matrixMedications.length && matrixValues.length) {
      mountPlot(
        "dashboard-plot-disease-medication",
        [{
          type: "heatmap",
          x: matrixMedications,
          y: matrixDiseases,
          z: matrixValues,
          colorscale: [
            [0, "#eff6ff"],
            [0.35, "#bfdbfe"],
            [0.65, "#60a5fa"],
            [1, "#1d4ed8"],
          ],
          hovertemplate: "Disease: %{y}<br>Medication: %{x}<br>Patients: %{z}<extra></extra>",
          colorbar: { title: "Patients" },
        }],
        dashboardPlotLayout({
          margin: { t: 16, r: 20, b: 90, l: 160 },
          xaxis: {
            ...dashboardPlotLayout().xaxis,
            tickangle: -25,
            title: { text: "Medication", font: { color: "#61758c", size: 12 } },
          },
          yaxis: {
            ...dashboardPlotLayout().yaxis,
            title: { text: "Disease", font: { color: "#61758c", size: 12 } },
            autorange: "reversed",
          },
        })
      );
    }

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
    const activeClass = state.selectedPatientId === patient.patient_id ? "active" : "";
    const datasetNames = Array.isArray(patient.dataset_names) ? patient.dataset_names : [];
    const datasetBadge = isMultiDatasetWorkspace() && datasetNames.length
      ? `<span class="pill">${escapeHtml(datasetNames.join(", "))}</span>`
      : "";
    const selectionBadge = '';
    const compactTimeline = state.currentDashboardSubtab === "timeline";
    const recordCount = Number(patient.clinical_record_count ?? patient.visit_count ?? 0);
    const recordText = `${recordCount} ${clinicalRecordLabel(patient, recordCount)}`;
    if (compactTimeline) {
      return `
        <div class="patient-card patient-card-compact ${activeClass}" data-patient-id="${patient.patient_id}">
          <div class="patient-card-compact-main">
            <strong>${patient.patient_id}</strong>
            <span>${selectionBadge}${claridIdentityMarkup(patient, true)}</span>
          </div>
          <div class="patient-card-compact-meta">
            <span>${escapeHtml(recordText)}</span>
            <span>${escapeHtml(patient.sex || "sex n/a")}</span>
            <span>${escapeHtml(String(patient.evidence.diseases.count || 0))} dx</span>
          </div>
        </div>
      `;
    }
    return `
      <div class="patient-card ${activeClass}" data-patient-id="${patient.patient_id}">
        <div class="patient-card-identity"><strong>${patient.patient_id}</strong>${claridIdentityMarkup(patient)}</div>
        <div>
          ${selectionBadge}
          ${datasetBadge}
          <span class="pill">${escapeHtml(recordText)}</span>
          <span class="pill">${patient.sex || "sex: n/a"}</span>
          <span class="pill">${patient.evidence.diseases.count} diseases</span>
        </div>
        <small>${patient.first_event_date || "?"} to ${patient.last_event_date || "?"}</small>
      </div>
    `;
  }

  function renderPatientList(items) {
    if (!patientsEl) return;
    if (!items.length) {
      patientsEl.innerHTML = '<div class="empty">No patients match the current filter.</div>';
      return;
    }
    const visibleItems = items.slice(0, MAX_VISIBLE_PATIENTS);
    const summary = items.length > MAX_VISIBLE_PATIENTS
      ? `<div class="section-note">Showing first ${MAX_VISIBLE_PATIENTS} of ${items.length} matching patients. Use search to narrow the list.</div>`
      : "";
    patientsEl.innerHTML = claridSearchFeedback(items) + summary + visibleItems.map(summaryCard).join("");
  }

  function renderDetail(patient) {
    const datasetNames = Array.isArray(patient.patient_context && patient.patient_context.dataset_names)
      ? patient.patient_context.dataset_names
      : (Array.isArray(patient.dataset_names) ? patient.dataset_names : []);
    const datasetLine = isMultiDatasetWorkspace() && datasetNames.length
      ? `<p>Datasets: ${escapeHtml(datasetNames.join(", "))}</p>`
      : "";
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

    const personRepresentation = clinicalRepresentation(patient) === "person";
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
          <div class="patient-detail-identity"><p><strong>${patient.patient_id}</strong></p>${claridIdentityMarkup(patient)}</div>
          ${datasetLine}
          <p>Sex: ${patient.patient_context.sex || "n/a"} | DOB: ${patient.patient_context.date_of_birth || "n/a"} | Vital status: ${patient.patient_context.vital_status || "n/a"}</p>
          <p>Sources: ${(patient.patient_context.source_files || []).join(", ") || "n/a"}</p>
          <h3>Available evidence</h3>
          ${renderEvidence(patient.evidence)}
        </div>
        <div class="workspace-card">
          <h3>${personRepresentation ? "Clinical record overview" : "Visit overview"}</h3>
          <ul class="mini-list">${visits || `<li><small>No ${personRepresentation ? "clinical records" : "visits"} found.</small></li>`}</ul>
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

  function renderDashboard(summary) {
    state.dashboardSummary = summary;
    const expanded = Boolean(state.dashboardClinicalExpanded);
    const totals = summary && summary.totals ? summary.totals : {};
    const representation = clinicalRepresentation(summary);
    const snapshotRepresentation = representation === "snapshot";
    const timelineButton = document.getElementById("dashboardTimelineBtn");
    if (timelineButton) {
      timelineButton.hidden = false;
      timelineButton.setAttribute("aria-hidden", "false");
    }
    const recordCount = Number(totals.clinical_records ?? totals.visits ?? summary.visits ?? 0);
    const extraPlotsMarkup = expanded ? `
          <div class="dashboard-plot-card">
            <h4>Disease by medication</h4>
            <div class="dashboard-plot-frame" id="dashboard-plot-disease-medication"></div>
          </div>
    ` : "";
    const toggleLabel = expanded ? "Show less" : "See more";
    const overviewMarkup = `
      <section class="section-card">
        <div class="section-card-header">
          <div class="section-card-eyebrow">Clinical overview</div>
          <h3>At a glance</h3>
        </div>
        <div class="dashboard-plot-grid">
          <div class="dashboard-plot-card">
            <h4>Sex distribution</h4>
            <div class="dashboard-plot-frame" id="dashboard-plot-sex"></div>
          </div>
          <div class="dashboard-plot-card">
            <h4>${snapshotRepresentation ? "Visits per patient" : "Clinical records per patient"}</h4>
            <div class="dashboard-plot-frame" id="dashboard-plot-visits"></div>
          </div>
          <div class="dashboard-plot-card">
            <h4>Top diseases</h4>
            <div class="dashboard-plot-frame" id="dashboard-plot-diseases"></div>
          </div>
          <div class="dashboard-plot-card">
            <h4>Top medications</h4>
            <div class="dashboard-plot-frame" id="dashboard-plot-medications"></div>
          </div>
          ${extraPlotsMarkup}
        </div>
        <div class="query-examples-toggle">
          <button id="dashboardClinicalToggleBtn" type="button" class="query-chip query-chip-toggle">${toggleLabel}</button>
        </div>
      </section>
    `;


    dashboardEl.innerHTML = `
      <section class="section-card dashboard-hero">
        <h2>Clinical dashboard</h2>
        <p>Key workspace metrics and quick patterns before drilling into one patient.</p>
        <div class="assay-kpi-grid">
          <div class="assay-kpi"><span class="assay-kpi-label">Patients</span><strong class="assay-kpi-value">${escapeHtml(formatNumber(totals.patients || summary.patients || 0))}</strong></div>
          <div class="assay-kpi"><span class="assay-kpi-label">${snapshotRepresentation ? "Timepoints" : "Clinical records"}</span><strong class="assay-kpi-value">${escapeHtml(formatNumber(recordCount))}</strong></div>
          <div class="assay-kpi"><span class="assay-kpi-label">${snapshotRepresentation ? "Avg visits / patient" : "Representation"}</span><strong class="assay-kpi-value">${snapshotRepresentation ? escapeHtml(String(totals.avg_visits_per_patient || 0)) : escapeHtml(representation === "person" ? "One record per person" : "Mixed or unspecified")}</strong></div>
          <div class="assay-kpi"><span class="assay-kpi-label">Source files</span><strong class="assay-kpi-value">${escapeHtml(formatNumber(totals.source_files || 0))}</strong></div>
        </div>
      </section>
      ${overviewMarkup}
    `;
    if (dashboardTimelineEl) {
      dashboardTimelineEl.innerHTML = timelinePanelMarkup(snapshotRepresentation);
    }
    const toggleBtn = document.getElementById("dashboardClinicalToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        state.dashboardClinicalExpanded = !state.dashboardClinicalExpanded;
        renderDashboard(state.dashboardSummary || summary);
      });
    }
    renderDashboardCharts(summary);
    if (state.currentDashboardSubtab === "timeline") {
      renderDashboardTimeline(summary);
    }
  }

  function renderAnalysisScopeSummary() {
    const selectedCohort = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
      : null;
    const metadata = !selectedCohort && state.analysisScopeMetadata && typeof state.analysisScopeMetadata === "object"
      ? state.analysisScopeMetadata
      : {};
    const queryResultHandle = String(metadata.query_result_handle || "").trim();
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    analysisSelectedPatientIdsEl.disabled = compareMode || Boolean(selectedCohort) || Boolean(queryResultHandle);
    const selectedCohortUsesSampleIds = Boolean(
      selectedCohort
      && Array.isArray(selectedCohort.sample_ids)
      && selectedCohort.sample_ids.length
    );
    const ids = selectedCohort && Array.isArray(selectedCohort.sample_ids) && selectedCohort.sample_ids.length
      ? selectedCohort.sample_ids.map((item) => String(item).trim()).filter(Boolean)
      : selectedCohort && Array.isArray(selectedCohort.patient_ids)
      ? selectedCohort.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String(analysisSelectedPatientIdsEl.value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const countLabel = selectedCohort
      ? `${selectedCohort.patient_count || (selectedCohort.patient_ids || []).length} patients / ${selectedCohort.sample_count || ids.length} samples`
      : metadata && (metadata.patient_count || metadata.sample_count)
        ? `${metadata.patient_count || 0} patients / ${metadata.sample_count || ids.length} samples`
      : `${ids.length} ${ids.length === 1 ? "ID" : "IDs"}`;
    const metadataSource = metadata && metadata.source && metadata.source.kind
      ? String(metadata.source.kind).replace(/_/g, " ")
      : "";
    analysisSelectedPatientIdsSummaryEl.textContent = compareMode
      ? (selectedCohort
        ? `Cohort A: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
        : ids.length
          ? `Cohort A: ${countLabel} in scope${metadataSource ? ` from ${metadataSource}` : ""}.`
        : "Cohort A: select a saved cohort from Saved Cohorts to compare.")
      : (selectedCohort
        ? `Scope: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
        : queryResultHandle
          ? `Scope: ${metadata.id_type === "sample" ? metadata.sample_count || 0 : metadata.patient_count || 0} ${metadata.id_type === "sample" ? "samples" : "patients"} from the Query result; identifiers remain server-side.`
        : ids.length
          ? `Scope: ${countLabel} in scope${metadataSource ? ` from ${metadataSource}` : ""}.`
          : "Scope: full workspace.");
    if (analysisSelectedSavedCohortSelectionEl) {
      if (selectedCohort) {
        analysisSelectedSavedCohortSelectionEl.classList.remove("is-hidden");
        analysisSelectedSavedCohortSelectionEl.innerHTML = `<span class="query-chip badge">Cohort A source</span> <button type="button" class="query-chip query-chip-deterministic" data-analysis-clear-saved-cohort="a">${escapeHtml(selectedCohort.name || "Saved cohort")} ×</button>`;
      } else {
        analysisSelectedSavedCohortSelectionEl.classList.add("is-hidden");
        analysisSelectedSavedCohortSelectionEl.innerHTML = "";
      }
    }
    renderAssayDatasetSelector();
    renderAssayDashboardCards(state.assayDatasetsState);
    if (typeof renderAnalysisCatalog === "function") {
      renderAnalysisCatalog();
    }
    renderGlobalContext();
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  function renderAnalysisCompareScopeSummary() {
    if (!analysisCompareSelectedPatientIdsSummaryEl) return;
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    analysisCompareSelectedPatientIdsSummaryEl.classList.toggle("is-hidden", !compareMode);
    if (analysisCompareSavedCohortSelectionEl) {
      analysisCompareSavedCohortSelectionEl.classList.toggle("is-hidden", !compareMode);
      if (!compareMode) {
        analysisCompareSavedCohortSelectionEl.innerHTML = "";
      }
    }
    if (!compareMode) {
      renderAssayDatasetSelector();
      renderAssayDashboardCards(state.assayDatasetsState);
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
      renderGlobalContext();
      syncCurrentAnalysisSessionFromUi({ render: true });
      return;
    }
    const selectedCohort = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
      : null;
    const metadata = !selectedCohort && state.analysisCompareScopeMetadata && typeof state.analysisCompareScopeMetadata === "object"
      ? state.analysisCompareScopeMetadata
      : {};
    if (analysisCompareSelectedPatientIdsEl) {
      analysisCompareSelectedPatientIdsEl.disabled = true;
    }
    const selectedCohortUsesSampleIds = Boolean(
      selectedCohort
      && Array.isArray(selectedCohort.sample_ids)
      && selectedCohort.sample_ids.length
    );
    const ids = selectedCohort && Array.isArray(selectedCohort.sample_ids) && selectedCohort.sample_ids.length
      ? selectedCohort.sample_ids.map((item) => String(item).trim()).filter(Boolean)
      : selectedCohort && Array.isArray(selectedCohort.patient_ids)
      ? selectedCohort.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String((analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value) || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const countLabel = selectedCohort
      ? `${selectedCohort.patient_count || (selectedCohort.patient_ids || []).length} patients / ${selectedCohort.sample_count || ids.length} samples`
      : metadata && (metadata.patient_count || metadata.sample_count)
        ? `${metadata.patient_count || 0} patients / ${metadata.sample_count || ids.length} samples`
      : `${ids.length} IDs`;
    const metadataSource = metadata && metadata.source && metadata.source.kind
      ? String(metadata.source.kind).replace(/_/g, " ")
      : "";
    analysisCompareSelectedPatientIdsSummaryEl.textContent = selectedCohort
      ? `Cohort B: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
      : ids.length
        ? `Cohort B: ${countLabel} in scope${metadataSource ? ` from ${metadataSource}` : ""}.`
      : "Cohort B: select a saved cohort from Saved Cohorts to compare.";
    if (analysisCompareSavedCohortSelectionEl) {
      if (selectedCohort) {
        analysisCompareSavedCohortSelectionEl.innerHTML = `<span class="query-chip badge">Cohort B source</span> <button type="button" class="query-chip query-chip-deterministic" data-analysis-clear-saved-cohort="b">${escapeHtml(selectedCohort.name || "Saved cohort")} ×</button>`;
      } else {
        analysisCompareSavedCohortSelectionEl.innerHTML = "";
      }
    }
    renderAssayDatasetSelector();
    renderAssayDashboardCards(state.assayDatasetsState);
    if (typeof renderAnalysisCatalog === "function") {
      renderAnalysisCatalog();
    }
    renderGlobalContext();
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  function renderAssayScopeCard(scope) {
    const mean = typeof scope.mean === "number" ? scope.mean.toFixed(1) : "n/a";
    const median = typeof scope.median === "number" ? scope.median.toFixed(1) : "n/a";
    const min = scope.min === null || scope.min === undefined ? "n/a" : String(scope.min);
    const max = scope.max === null || scope.max === undefined ? "n/a" : String(scope.max);
    const values = Array.isArray(scope.values) ? scope.values : [];
    const preview = values.slice(0, 8).map((item) => (
      `<tr><td>${escapeHtml(item.patient_id)}</td><td>${escapeHtml(item.sample_id)}</td><td>${escapeHtml(String(item.raw_count))}</td></tr>`
    )).join("");
    const more = values.length > 8
      ? `<div class="section-note">Showing 8 of ${values.length} measurements.</div>`
      : "";
    return `
      <div class="assay-scope-card">
        <h4>${escapeHtml(scope.label || "Scope")}</h4>
        <div class="assay-stats">
          <span class="query-chip badge">Samples: ${escapeHtml(String(scope.sample_count || 0))}</span>
          <span class="query-chip badge">Patients: ${escapeHtml(String(scope.patient_count || 0))}</span>
          <span class="query-chip badge">Mean: ${escapeHtml(mean)}</span>
          <span class="query-chip badge">Median: ${escapeHtml(median)}</span>
          <span class="query-chip badge">Range: ${escapeHtml(min)} to ${escapeHtml(max)}</span>
        </div>
        ${values.length ? `
          <div class="assay-table-wrap">
            <table class="assay-table">
              <thead><tr><th>Patient</th><th>Sample</th><th>Raw count</th></tr></thead>
              <tbody>${preview}</tbody>
            </table>
          </div>
          ${more}
        ` : '<div class="empty">No assay samples matched this scope for the selected gene.</div>'}
      </div>
    `;
  }

  function renderAssayExpressionResult(payload) {
    if (!analysisAssayResultEl) return;
    if (!payload) {
      analysisAssayResultEl.className = "assay-result empty";
      analysisAssayResultEl.textContent = "No transcriptomics expression summary yet.";
      return;
    }
    const payloads = Array.isArray(payload) ? payload : [payload];
    if (!payloads.length) {
      analysisAssayResultEl.className = "assay-result empty";
      analysisAssayResultEl.textContent = "No transcriptomics expression summary yet.";
      return;
    }
    analysisAssayResultEl.className = "assay-result";
    analysisAssayResultEl.innerHTML = payloads.map((item) => {
      const sections = [renderAssayScopeCard(item.scope_a)];
      if (item.scope_b) sections.push(renderAssayScopeCard(item.scope_b));
      const geneTooltip = [
        String(item.gene_id || "").trim(),
        String(item.gene_symbol || "").trim(),
        String(item.gene_name || "").trim(),
      ].filter(Boolean).join(" • ");
      const geneMarkup = item.ensembl_url
        ? `<a class="assay-result-gene-link" href="${escapeHtml(item.ensembl_url)}" target="_blank" rel="noopener" title="${escapeHtml(geneTooltip || String(item.gene_id || ""))}">${escapeHtml(item.gene_id)}</a>`
        : `<span title="${escapeHtml(geneTooltip || String(item.gene_id || ""))}">${escapeHtml(item.gene_id)}</span>`;
      return `
        <div class="transcriptomics-expression-card">
          <div class="assay-result-header">
            <strong>${geneMarkup}</strong>
            ${item.gene_symbol && item.gene_symbol !== item.gene_id ? `<span class="query-chip badge">${escapeHtml(item.gene_symbol)}</span>` : ""}
            <span class="query-chip badge">${escapeHtml(item.dataset_name)}</span>
          </div>
          <div class="assay-result-grid">${sections.join("")}</div>
        </div>
      `;
    }).join("");
  }

  function selectedAssayDatasetNames() {
    const knownNames = new Set(
      state.assayDatasetsState.map((dataset) => String(dataset && dataset.dataset_name ? dataset.dataset_name : "").trim()).filter(Boolean)
    );
    return state.selectedAssayDatasets.filter((datasetName) => knownNames.has(datasetName));
  }

  function selectedTranscriptomicsAssayDatasetNames() {
    const transcriptomicsNames = new Set(
      state.assayDatasetsState
        .filter((dataset) => isQuickExpressionDataset(dataset))
        .map((dataset) => dataset.dataset_name)
    );
    return selectedAssayDatasetNames().filter((datasetName) => transcriptomicsNames.has(datasetName));
  }

  function assayDatasetListElements() {
    return [analysisAssayDatasetListEl, analysisCatalogAssayDatasetListEl].filter(Boolean);
  }

  function currentAnalysisCatalogItem() {
    return Array.isArray(state.analysisCatalogItems)
      ? state.analysisCatalogItems.find((item) => String(item && item.id ? item.id : "") === String(state.analysisSelectedCatalogItemId || ""))
      : null;
  }

  function requiresSingleSelectedAssayDataset(item) {
    const itemId = String(item && item.id ? item.id : "").trim();
    return itemId === "transcriptomics-deseq2-differential-expression"
      || itemId === "transcriptomics-limma-voom-differential-expression"
      || itemId === "transcriptomics-hallmark-pathway-enrichment"
      || itemId === "transcriptomics-signature-workflow"
      || itemId === "methylation-qc-pca"
      || itemId === "methylation-limma-differential-methylation"
      || itemId === "flow-cytometry-wilcoxon-cohort-comparison"
      || itemId === "serology-wilcoxon-cohort-comparison";
  }

  function normalizedAssayDataType(dataset) {
    const explicit = String(dataset && dataset.data_type ? dataset.data_type : "").trim();
    if (explicit) return explicit;
    const modality = String(dataset && dataset.modality ? dataset.modality : "").trim();
    if (modality.endsWith("_raw_counts")) return "raw_counts";
    if (modality.endsWith("_relative_abundance")) return "relative_abundance";
    if (modality.endsWith("_protein_abundance")) return "protein_abundance";
    if (modality.endsWith("_cell_population_abundance")) return "cell_population_abundance";
    if (modality.endsWith("_quantitative_measurement")) return "quantitative_measurement";
    return "";
  }

  function isQuickExpressionDataset(dataset) {
    return normalizedAssayModality(dataset && dataset.modality) === "transcriptomics"
      && normalizedAssayDataType(dataset) === "raw_counts"
      && dataset.supports_expression_summary !== false;
  }

  function assayMatchesCatalogRequirement(dataset, item) {
    if (!item || !item.requires_assays) return true;
    const requiredModalities = Array.isArray(item.required_modalities)
      ? item.required_modalities.map((value) => normalizedAssayModality(value)).filter(Boolean)
      : [];
    const requiredDataTypes = Array.isArray(item.required_data_types)
      ? item.required_data_types.map((value) => String(value || "").trim()).filter(Boolean)
      : [];
    const modality = normalizedAssayModality(dataset && dataset.modality);
    const dataType = normalizedAssayDataType(dataset);
    if (requiredModalities.length && !requiredModalities.includes(modality)) return false;
    if (requiredDataTypes.length && !requiredDataTypes.includes(dataType)) return false;
    return true;
  }

  function groupAssaysByModality(datasets) {
    const groups = new Map();
    (Array.isArray(datasets) ? datasets : []).forEach((dataset) => {
      const key = normalizedAssayModality(dataset && dataset.modality);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(dataset);
    });
    return Array.from(groups.entries()).sort((left, right) => formatAssayModality(left[0]).localeCompare(formatAssayModality(right[0])));
  }

  function contextualAssayDatasets() {
    const item = currentAnalysisCatalogItem();
    if (!item || !item.requires_assays) {
      return [];
    }
    const compareRequired = Boolean(item.default_compare_mode);
    const minimumOverlap = Math.max(1, Number(item.minimum_samples_per_cohort || 1));
    const compatibleDatasets = state.assayDatasetsState.filter((dataset) => {
      if (!assayMatchesCatalogRequirement(dataset, item)) {
        return false;
      }
      const patientIds = Array.isArray(dataset && dataset.patient_ids) ? dataset.patient_ids : [];
      if (!patientIds.length) {
        return true;
      }
      const overlap = currentAssayScopeOverlap(patientIds);
      if (compareRequired) {
        return overlap.overlapA >= minimumOverlap && overlap.overlapB >= minimumOverlap;
      }
      if (overlap.scopeASize || overlap.scopeBSize) {
        return overlap.overlapA > 0 || overlap.overlapB > 0;
      }
      return true;
    });
    const compatibleNames = new Set(compatibleDatasets.map((dataset) => dataset.dataset_name));
    const filteredSelected = state.selectedAssayDatasets.filter((name) => compatibleNames.has(name));
    if (filteredSelected.length !== state.selectedAssayDatasets.length) {
      state.selectedAssayDatasets = filteredSelected;
    }
    if (
      requiresSingleSelectedAssayDataset(item)
      && compatibleDatasets.length === 1
      && (
        state.selectedAssayDatasets.length !== 1
        || state.selectedAssayDatasets[0] !== compatibleDatasets[0].dataset_name
      )
    ) {
      state.selectedAssayDatasets = [compatibleDatasets[0].dataset_name];
    }
    return compatibleDatasets;
  }

  function renderAssayDatasetSelector() {
    const item = currentAnalysisCatalogItem();
    const contextRequiresAssay = Boolean(item && item.requires_assays);
    const mainListEl = analysisAssayDatasetListEl;
    const contextualListEl = analysisCatalogAssayDatasetListEl;
    if (!mainListEl && !contextualListEl) return;
    if (!state.assayDatasetsState.length) {
      if (mainListEl) mainListEl.innerHTML = '<div class="empty">No assay loaded</div>';
      if (contextualListEl) contextualListEl.innerHTML = '<div class="empty">No assay loaded</div>';
      return;
    }
    const selected = new Set(state.selectedAssayDatasets);
    const renderOption = (dataset, options = {}) => {
      const overlap = currentAssayScopeOverlap(dataset.patient_ids);
      const featureLabel = String(dataset.feature_label || "features").trim() || "features";
      const featureCount = Number(dataset.feature_count || dataset.gene_count || 0);
      const panel = dataset && dataset.feature_panel && typeof dataset.feature_panel === "object"
        ? dataset.feature_panel
        : null;
      const panelMeta = panel
        ? ` • Panel v${escapeHtml(String(panel.panel_version || ""))}${panel.independent_of_target_cohort ? " • independently selected" : ""}`
        : "";
      const baseMeta = `${escapeHtml(String(dataset.sample_count || 0))} samples, ${escapeHtml(String(featureCount))} ${escapeHtml(featureLabel)} • ${escapeHtml(formatAssayDataType(normalizedAssayDataType(dataset) || dataset.data_type))}${panelMeta}`;
      const small = options.includeOverlap
        ? `${baseMeta} • A overlap ${escapeHtml(String(overlap.overlapA))}${analysisCompareModeEl && analysisCompareModeEl.checked ? ` • B overlap ${escapeHtml(String(overlap.overlapB))}` : ""}`
        : baseMeta;
      return `
      <label class="assay-dataset-option">
        <input type="checkbox" value="${escapeHtml(dataset.dataset_name)}"${selected.has(dataset.dataset_name) ? " checked" : ""}>
        <span>
          <strong>${escapeHtml(String(dataset.label || dataset.dataset_name))}</strong>
          <small>${small}</small>
        </span>
      </label>
    `;
    };
    if (mainListEl) {
      const transcriptomicsDatasets = state.assayDatasetsState.filter((dataset) => isQuickExpressionDataset(dataset));
      mainListEl.innerHTML = transcriptomicsDatasets.length
        ? groupAssaysByModality(transcriptomicsDatasets).map(([modality, datasets]) => `
        <div class="assay-modality-group">
          <div class="assay-modality-group-title">${escapeHtml(formatAssayModality(modality))}</div>
          ${datasets.map((dataset) => renderOption(dataset)).join("")}
        </div>
      `).join("")
        : '<div class="empty">No raw-count transcriptomics assays available</div>';
    }
    if (contextualListEl) {
      if (!contextRequiresAssay) {
        contextualListEl.innerHTML = '<div class="empty">Choose an assay analysis to select a compatible assay.</div>';
        return;
      }
      const availableDatasets = contextualAssayDatasets();
      if (!availableDatasets.length) {
      contextualListEl.innerHTML = '<div class="empty">No compatible assays are available in this workspace.</div>';
        return;
      }
      contextualListEl.innerHTML = groupAssaysByModality(availableDatasets).map(([modality, datasets]) => `
        <div class="assay-modality-group">
          <div class="assay-modality-group-title">${escapeHtml(formatAssayModality(modality))}</div>
          ${datasets.map((dataset) => renderOption(dataset, { includeOverlap: true })).join("")}
        </div>
      `).join("");
    }
  }

  function syncSelectedAssayDatasets() {
    const available = new Set(state.assayDatasetsState.map((item) => item.dataset_name));
    state.selectedAssayDatasets = state.selectedAssayDatasets.filter((item) => available.has(item));
    renderAssayDatasetSelector();
  }

  function clearAssayWorkspaceSelection() {
    state.selectedAssayDatasets = [];
    if (analysisAssayGeneEl) {
      analysisAssayGeneEl.value = "";
    }
    renderAssayExpressionResult(null);
  }

  function clearDatasetWorkspaceViews(options = {}) {
    const signedOut = options.signedOut === true;
    const workspaceMessage = signedOut ? "Sign in to access shared assays." : "No workspace loaded.";
    state.assayDatasetsState = [];
    state.assayDatasetsScopeId = "";
    state.assayDashboardModalityFilter = "all";
    state.multimodalReadinessState = null;
    state.multimodalMatrixState = null;
    state.dicomStudiesState = [];
    state.dicomStatus = null;
    state.dashboardSummary = null;
    clearAssayWorkspaceSelection();
    if (analysisAssayGenesEl) analysisAssayGenesEl.innerHTML = "";
    renderAssayDatasetSelector();
    renderAssayDashboardCards([]);
    if (analysisAssayStatusEl) {
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = workspaceMessage;
    }
    if (analysisCatalogAssayStatusEl) {
      analysisCatalogAssayStatusEl.textContent = workspaceMessage;
    }
    if (assayDashboardStatusEl) {
      assayDashboardStatusEl.className = "query-status";
      assayDashboardStatusEl.textContent = workspaceMessage;
    }
    if (dicomDashboardHealthEl) {
      dicomDashboardHealthEl.innerHTML = `<div class="empty">${escapeHtml(signedOut ? "Sign in to inspect DICOM viewer status." : "Load a workspace to inspect DICOM viewer status.")}</div>`;
    }
    if (dicomDashboardStatusEl) {
      dicomDashboardStatusEl.className = "query-status";
      dicomDashboardStatusEl.textContent = signedOut ? "Sign in to access DICOM studies." : "No workspace loaded.";
    }
    if (dicomDashboardStudiesEl) {
      dicomDashboardStudiesEl.innerHTML = '<div class="empty">No DICOM studies loaded.</div>';
    }
    if (multimodalReadinessStatusEl) {
      multimodalReadinessStatusEl.className = "query-status";
      multimodalReadinessStatusEl.textContent = workspaceMessage;
    }
    if (multimodalReadinessContentEl) {
      multimodalReadinessContentEl.innerHTML = '<div class="empty">Load a workspace to review multimodal readiness.</div>';
    }
    if (multimodalMatrixStatusEl) {
      multimodalMatrixStatusEl.className = "query-status";
      multimodalMatrixStatusEl.textContent = workspaceMessage;
    }
    if (multimodalMatrixContentEl) {
      multimodalMatrixContentEl.innerHTML = '<div class="empty">Load a workspace to build a multimodal feature matrix.</div>';
    }
    if (typeof renderAnalysisCatalogAssayPanel === "function") renderAnalysisCatalogAssayPanel();
    if (typeof renderAnalysisCatalog === "function") renderAnalysisCatalog();
  }

  function assayDatasetOverlap(datasetName) {
    const normalizedName = String(datasetName || "").trim();
    if (!normalizedName) return null;
    const dataset = state.assayDatasetsState.find((item) => String(item && item.dataset_name ? item.dataset_name : "").trim() === normalizedName);
    if (!dataset) return null;
    return currentAssayScopeOverlap(dataset.patient_ids);
  }

  function currentAssayScopeOverlap(patientIds) {
    const datasetPatientIds = new Set((Array.isArray(patientIds) ? patientIds : []).map((item) => String(item)));
    const selectedCohortA = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
      : null;
    const selectedCohortB = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
      : null;
    const scopeA = selectedCohortA && Array.isArray(selectedCohortA.patient_ids)
      ? selectedCohortA.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String(analysisSelectedPatientIdsEl && analysisSelectedPatientIdsEl.value ? analysisSelectedPatientIdsEl.value : "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const scopeB = selectedCohortB && Array.isArray(selectedCohortB.patient_ids)
      ? selectedCohortB.patient_ids.map((item) => String(item).trim()).filter(Boolean)
      : String(analysisCompareSelectedPatientIdsEl && analysisCompareSelectedPatientIdsEl.value ? analysisCompareSelectedPatientIdsEl.value : "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const overlapA = scopeA.filter((item) => datasetPatientIds.has(item)).length;
    const overlapB = scopeB.filter((item) => datasetPatientIds.has(item)).length;
    return { overlapA, overlapB, scopeASize: scopeA.length, scopeBSize: scopeB.length };
  }

  function renderDicomHealth(payload) {
    if (!dicomDashboardHealthEl) return;
    const source = payload && typeof payload === "object" ? payload : {};
    state.dicomStatus = { ...(state.dicomStatus || {}), ...source };
    const enabled = Boolean(source.enabled);
    const manifestFound = Boolean(source.manifest_found);
    const studyCount = Number(source.study_count || 0);
    const ohifUrl = String(source.ohif_public_url || "").trim();
    const dicomwebUrl = String(source.dicomweb_public_url || "").trim();
    const orthanc = source.orthanc && typeof source.orthanc === "object" ? source.orthanc : {};
    const orthancChecked = Boolean(orthanc.checked);
    const orthancReachable = Boolean(orthanc.reachable);
    const orthancLabel = orthancChecked ? (orthancReachable ? "Reachable" : "Unreachable") : "Not checked";
    const orthancMessage = String(orthanc.message || "").trim();
    const studies = state.dicomStudiesState || [];
    const bundledCount = studies.filter(study => study.local_viewer_url).length;
    if (bundledCount && bundledCount === studies.length) {
      dicomDashboardHealthEl.innerHTML = `<div class="dicom-health-grid">
        <div class="dicom-health-card"><span class="assay-kpi-label">Viewer</span><strong>Bundled OHIF</strong><small>Opens inside COHORTome</small></div>
        <div class="dicom-health-card"><span class="assay-kpi-label">Studies</span><strong>${escapeHtml(String(bundledCount))} available</strong><small>Bundled synthetic images</small></div>
        <div class="dicom-health-card"><span class="assay-kpi-label">Image access</span><strong>Through COHORTome</strong><small>Dataset permissions checked on every request</small></div>
        <div class="dicom-health-card"><span class="assay-kpi-label">External services</span><strong>Not required</strong><small>No Docker or Orthanc service needed for these studies</small></div>
      </div>`;
      renderAssayDashboardOverview(state.assayDatasetsState || []);
      return;
    }
    dicomDashboardHealthEl.innerHTML = `
      <div class="dicom-health-grid">
        <div class="dicom-health-card">
          <span class="assay-kpi-label">External viewer</span>
          <strong>${enabled ? "Enabled" : "Disabled"}</strong>
          <small>${bundledCount ? `${bundledCount} studies use bundled OHIF; external viewing applies to the remaining studies` : 'Open studies in OHIF'}</small>
        </div>
        <div class="dicom-health-card">
          <span class="assay-kpi-label">Study manifest</span>
          <strong>${manifestFound ? "Found" : "Missing"}</strong>
          <small>${escapeHtml(String(studyCount))} configured stud${studyCount === 1 ? "y" : "ies"}</small>
        </div>
        <div class="dicom-health-card">
          <span class="assay-kpi-label">Orthanc</span>
          <strong>${escapeHtml(orthancLabel)}</strong>
          <small>${escapeHtml(orthancMessage || "Pixel store health is not checked")}</small>
        </div>
        <div class="dicom-health-card">
          <span class="assay-kpi-label">DICOMweb</span>
          <strong>${dicomwebUrl ? "Configured" : "Missing"}</strong>
          <small>Image access service</small>
        </div>
      </div>
      <details class="assay-card-section"><summary>Connection details</summary>
        <p>OHIF: ${escapeHtml(ohifUrl || "Not configured")}</p>
        <p>DICOMweb: ${escapeHtml(dicomwebUrl || "Not configured")}</p>
      </details>
    `;
    renderAssayDashboardOverview(state.assayDatasetsState || []);
  }

  function renderDicomHealthError(message) {
    if (!dicomDashboardHealthEl) return;
    dicomDashboardHealthEl.innerHTML = `<div class="empty">${escapeHtml(message || "Unable to load DICOM viewer status.")}</div>`;
  }

  function renderDicomStudies(payload) {
    if (!dicomDashboardStatusEl || !dicomDashboardStudiesEl) return;
    const source = payload && typeof payload === "object" ? payload : {};
    const enabled = Boolean(source.enabled);
    const studies = Array.isArray(source.studies) ? source.studies : [];
    const localAvailable = studies.some(study => study.local_viewer_url);
    state.dicomStatus = { ...(state.dicomStatus || {}), ...source };
    state.dicomStudiesState = studies;
    dicomDashboardStatusEl.className = "query-status";
    if (!studies.length) {
      dicomDashboardStatusEl.textContent = enabled
        ? "No DICOM studies are configured for this workspace."
        : "DICOM visualization is disabled. No DICOM studies are configured for this workspace.";
      dicomDashboardStudiesEl.innerHTML = '<div class="empty">No DICOM studies configured.</div>';
      renderAssayDashboardOverview(state.assayDatasetsState || []);
      return;
    }
    dicomDashboardStatusEl.textContent = localAvailable
      ? `Loaded ${studies.length} studies. Bundled viewing is available for synthetic images.`
      : enabled
      ? `Loaded ${studies.length} DICOM stud${studies.length === 1 ? "y" : "ies"} for OHIF viewing.`
      : `DICOM visualization is disabled. ${studies.length} configured stud${studies.length === 1 ? "y" : "ies"} found.`;
    const modalityCounts = new Map();
    studies.forEach(study => { const key = String(study.modality || 'Not recorded'); modalityCounts.set(key, (modalityCounts.get(key) || 0) + 1); });
    dicomDashboardStudiesEl.innerHTML = `<section class="imaging-coverage-summary">
      ${renderCoverageBars('Studies by imaging modality', Array.from(modalityCounts, ([label, count]) => ({label, count, modality:'imaging'})), 'studies')}
      <p class="section-note">Configured study inventory—not a count of unique patients or a check of image quality.</p>
    </section>` + studies.map((study) => {
      const series = Array.isArray(study.series) ? study.series : [];
      const instanceCount = series.reduce((total, item) => total + Number(item && item.instance_count ? item.instance_count : 0), 0);
      const ohifUrl = String(study.ohif_url || "").trim();
      const canOpen = enabled && ohifUrl;
      const title = String(study.label || study.study_description || study.study_instance_uid || "DICOM study").trim();
      const subtitle = [study.patient_id, study.sample_id, study.timepoint].map((item) => String(item || "").trim()).filter(Boolean).join(" • ");
      return `
        <article class="dicom-study-card">
          <div class="assay-card-header">
            <div>
              <div class="assay-card-eyebrow">${assayOverviewIcon('imaging')} DICOM study</div>
              <strong class="assay-card-title">${escapeHtml(title)}</strong>
            </div>
            <span class="query-chip badge assay-modality-badge">${escapeHtml(String(study.modality || "DICOM"))}</span>
          </div>
          ${subtitle ? `<div class="section-note">Patient / sample / timepoint: ${escapeHtml(subtitle)}</div>` : '<div class="section-note">Patient linkage not recorded.</div>'}
          <div class="assay-kpi-grid">
            <div class="assay-kpi"><span class="assay-kpi-label">Series</span><strong class="assay-kpi-value">${escapeHtml(String(series.length))}</strong></div>
            <div class="assay-kpi"><span class="assay-kpi-label">Instances</span><strong class="assay-kpi-value">${escapeHtml(String(instanceCount))}</strong></div>
          </div>
          <details class="assay-card-section">
            <summary>Study identifier</summary>
            <code class="dicom-uid">${escapeHtml(String(study.study_instance_uid || ""))}</code>
          </details>
          <div class="query-row dicom-card-actions">
            ${study.local_viewer_url
        ? `<button type="button" data-local-viewer="${escapeHtml(study.local_viewer_url)}">View images</button>`
        : canOpen
          ? `<a class="button-like" href="${escapeHtml(ohifUrl)}" target="_blank" rel="noopener" title="Opens the configured external viewer">View images</a>`
          : '<button type="button" disabled title="No viewer is configured for this study">View images</button>'}
          </div>
        </article>
      `;
    }).join("");
    dicomDashboardStudiesEl.querySelectorAll('[data-local-viewer]').forEach(button => {
      button.addEventListener('click', () => {
        const url = new URL(button.dataset.localViewer, window.location.origin);
        if (url.origin !== window.location.origin || !url.pathname.startsWith('/local-viewer/open/')) return;
        const dialog = document.createElement('dialog');
        dialog.className = 'local-imaging-viewer';
        const close = document.createElement('button');
        close.type = 'button'; close.textContent = 'Close viewer';
        const frame = document.createElement('iframe');
        frame.title = 'OHIF imaging viewer'; frame.src = url.href;
        dialog.append(close, frame);
        close.addEventListener('click', () => dialog.close());
        dialog.addEventListener('close', () => { dialog.remove(); button.focus(); });
        document.body.append(dialog); dialog.showModal(); close.focus();
      });
    });
    renderAssayDashboardOverview(state.assayDatasetsState || []);
  }

  async function loadDicomStudies(options = {}) {
    if (!dicomDashboardStatusEl || !dicomDashboardStudiesEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const dataDir = encodeURIComponent(scopeId);
    dicomDashboardStatusEl.className = "query-status loading";
    dicomDashboardStatusEl.textContent = "Checking DICOM studies...";
    if (dicomDashboardHealthEl) {
      dicomDashboardHealthEl.innerHTML = '<div class="empty">Checking DICOM viewer status...</div>';
    }
    const [studiesResult, statusResult] = await Promise.allSettled([
      fetch(`/dicom/studies?data_dir=${dataDir}`),
      fetch(`/dicom/status?data_dir=${dataDir}`),
    ]);
    if (!isCurrentWorkspaceScope(scopeId)) return;
    if (studiesResult.status === "fulfilled" && studiesResult.value.ok) {
      renderDicomStudies(await studiesResult.value.json());
    } else {
      const error = studiesResult.status === "rejected" ? studiesResult.reason : null;
      state.dicomStudiesState = [];
      dicomDashboardStatusEl.className = "query-status";
      dicomDashboardStatusEl.textContent = error && error.message ? error.message : "Unable to load DICOM studies.";
      dicomDashboardStudiesEl.innerHTML = '<div class="empty">No DICOM studies configured.</div>';
    }
    if (statusResult.status === "fulfilled" && statusResult.value.ok) {
      renderDicomHealth(await statusResult.value.json());
    } else {
      const error = statusResult.status === "rejected" ? statusResult.reason : null;
      renderDicomHealthError(error && error.message ? error.message : "Unable to load DICOM viewer status.");
    }
  }

  function normalizedAssayModality(value) {
    const normalized = String(value || "assay").trim() || "assay";
    if (normalized.startsWith("transcriptomics")) return "transcriptomics";
    if (normalized.startsWith("proteomics")) return "proteomics";
    if (normalized.startsWith("olink")) return "olink";
    if (normalized.startsWith("flow_cytometry") || normalized.startsWith("immune_cell")) return "flow_cytometry";
    if (normalized.startsWith("serology")) return "serology";
    if (normalized.startsWith("genotyping") || normalized.startsWith("variant")) return "genotyping";
    if (normalized.startsWith("imaging") || normalized === "dicom") return "imaging";
    return normalized;
  }

  function assayModalityCounts(datasets) {
    const counts = new Map();
    (Array.isArray(datasets) ? datasets : []).forEach((dataset) => {
      const modality = normalizedAssayModality(dataset && dataset.modality);
      counts.set(modality, (counts.get(modality) || 0) + 1);
    });
    return counts;
  }

  function assayModalityTabs(datasets) {
    datasets = (datasets || []).filter((item) => normalizedAssayModality(item.modality) !== "imaging");
    const counts = assayModalityCounts(datasets);
    return [
      { key: "all", label: "All", count: Array.isArray(datasets) ? datasets.length : 0 },
      ...Array.from(counts.entries())
        .sort((left, right) => formatAssayModality(left[0]).localeCompare(formatAssayModality(right[0])))
        .map(([key, count]) => ({ key, label: formatAssayModality(key), count })),
    ];
  }

  function selectedAssayModalityFilter() {
    const value = String(state.assayDashboardModalityFilter || "all").trim() || "all";
    const tabs = assayModalityTabs(state.assayDatasetsState || []);
    return tabs.some((tab) => tab.key === value) ? value : "all";
  }

  function renderAssayDashboardOverview(datasets) {
    if (!assayDashboardOverviewEl) return;
    const items = (Array.isArray(datasets) ? datasets : []).filter((item) => normalizedAssayModality(item.modality) !== "imaging");
    if (!items.length) {
      assayDashboardOverviewEl.innerHTML = '<div class="empty">Load assays to review modality coverage.</div>';
      return;
    }
    const patientIds = new Set();
    const sampleIds = new Set();
    let featureTotal = 0;
    items.forEach((item) => {
      (Array.isArray(item.patient_ids) ? item.patient_ids : []).forEach((id) => patientIds.add(String(id || "").trim()));
      (Array.isArray(item.sample_ids) ? item.sample_ids : []).forEach((id) => sampleIds.add(String(id || "").trim()));
      featureTotal += Number(item.feature_count || item.gene_count || 0);
    });
    const modalities = Array.from(assayModalityCounts(items).keys()).sort((left, right) => formatAssayModality(left).localeCompare(formatAssayModality(right)));
    const coverage = modalities.map(modality => {
      const assays = items.filter(item => normalizedAssayModality(item.modality) === modality);
      const known = assays.every(item => Array.isArray(item.patient_ids));
      const patients = new Set(assays.flatMap(item => item.patient_ids || []).map(String).filter(id => id.trim()));
      return { modality, count: known ? patients.size : null };
    });
    const largest = Math.max(1, ...coverage.map(item => item.count || 0));
    assayDashboardOverviewEl.innerHTML = `
      <section class="assay-overview-summary">
        <div class="assay-overview-copy">
          <strong class="assay-workspace-summary-title">Assay overview</strong>
          <div class="section-note">${escapeHtml(modalities.map((item) => formatAssayModality(item)).join(" · "))}</div>
        </div>
        <div class="assay-workspace-kpis">
          <div class="assay-kpi assay-kpi-compact"><span class="assay-kpi-label">Assays</span><strong class="assay-kpi-value">${escapeHtml(String(items.length))}</strong></div>
          <div class="assay-kpi assay-kpi-compact"><span class="assay-kpi-label">Samples</span><strong class="assay-kpi-value">${escapeHtml(String(sampleIds.size))}</strong></div>
          <div class="assay-kpi assay-kpi-compact"><span class="assay-kpi-label">Patients</span><strong class="assay-kpi-value">${escapeHtml(String(patientIds.size))}</strong></div>
          <div class="assay-kpi assay-kpi-compact"><span class="assay-kpi-label">Features</span><strong class="assay-kpi-value">${escapeHtml(String(featureTotal))}</strong></div>
        </div>
        <div class="assay-coverage-chart">
          <strong>Patients by modality</strong>
          <p class="section-note">Unique patients within each modality; a patient can appear in several rows.</p>
          ${coverage.map(({ modality, count }) => `<div class="assay-coverage-row">
            <span>${assayOverviewIcon(modality)}${escapeHtml(formatAssayModality(modality))}</span>
            <div class="assay-coverage-track" aria-hidden="true"><i style="width:${count === null ? 0 : count / largest * 100}%"></i></div>
            <strong>${count === null ? 'Not reported' : escapeHtml(formatNumber(count))}</strong>
          </div>`).join('')}
        </div>
      </section>
    `;
  }

  function renderAssayModalityTabs(datasets) {
    if (!assayModalityTabsEl) return;
    const tabs = assayModalityTabs(datasets);
    const selected = selectedAssayModalityFilter();
    assayModalityTabsEl.innerHTML = tabs.map((tab) => `
      <button type="button" class="assay-modality-tab${tab.key === selected ? " active" : ""}" data-assay-modality-filter="${escapeHtml(tab.key)}" aria-pressed="${tab.key === selected ? "true" : "false"}">
        <span>${escapeHtml(tab.label)}</span>
        <strong>${escapeHtml(String(tab.count))}</strong>
      </button>
    `).join("");
  }

  function renderDicomPanelVisibility() {
    if (!dicomDashboardPanelEl) return;
    dicomDashboardPanelEl.classList.remove("is-hidden");
    dicomDashboardPanelEl.setAttribute("aria-hidden", "false");
  }

  function renderTranscriptomicsQuickExpressionVisibility() {
    if (!transcriptomicsQuickExpressionPanelEl) return;
    const visible = selectedAssayModalityFilter() === "transcriptomics"
      && state.assayDatasetsState.some((dataset) => isQuickExpressionDataset(dataset));
    transcriptomicsQuickExpressionPanelEl.classList.toggle("is-hidden", !visible);
    transcriptomicsQuickExpressionPanelEl.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function renderMultimodalReadinessVisibility() {
    if (!multimodalReadinessPanelEl) return;
    multimodalReadinessPanelEl.classList.remove("is-hidden");
    multimodalReadinessPanelEl.setAttribute("aria-hidden", "false");
  }

  function renderMultimodalMatrixVisibility() {
    if (!multimodalMatrixPanelEl) return;
    multimodalMatrixPanelEl.classList.remove("is-hidden");
    multimodalMatrixPanelEl.setAttribute("aria-hidden", "false");
  }

  function renderReadinessKpis(workspace) {
    const source = workspace && typeof workspace === "object" ? workspace : {};
    return `
      <div class="assay-kpi-grid multimodal-kpi-grid">
        <div class="assay-kpi"><span class="assay-kpi-label">Clinical patients</span><strong class="assay-kpi-value">${escapeHtml(String(source.patient_count || 0))}</strong></div>
        <div class="assay-kpi"><span class="assay-kpi-label">Modalities</span><strong class="assay-kpi-value">${escapeHtml(String(source.modality_count || 0))}</strong></div>
        <div class="assay-kpi"><span class="assay-kpi-label">Multimodal patients</span><strong class="assay-kpi-value">${escapeHtml(String(source.multimodal_patient_count || 0))}</strong></div>
        <div class="assay-kpi"><span class="assay-kpi-label">Exact sample overlap</span><strong class="assay-kpi-value">${escapeHtml(String(source.exact_sample_overlap_count || 0))}</strong></div>
      </div>
    `;
  }

  function renderCoverageBars(title, rows, unit) {
    const validCount = value => value !== null && value !== undefined && Number.isFinite(Number(value)) && Number(value) >= 0;
    const max = Math.max(1, ...rows.filter(row => validCount(row.count)).map(row => Number(row.count)));
    return `<div class="assay-coverage-chart"><strong>${escapeHtml(title)}</strong>
      ${rows.map(row => `<div class="assay-coverage-row">
        <span>${assayOverviewIcon(row.modality)}${escapeHtml(String(row.label))}</span>
        <div class="assay-coverage-track" aria-hidden="true"><i style="width:${validCount(row.count) ? Number(row.count) / max * 100 : 0}%"></i></div>
        <strong>${validCount(row.count) ? escapeHtml(formatNumber(Number(row.count))) + ' ' + escapeHtml(Number(row.count) === 1 ? (unit === 'studies' ? 'study' : 'patient') : unit) : 'Not reported'}</strong>
      </div>`).join('') || '<p class="empty">No coverage reported.</p>'}</div>`;
  }

  function renderReadinessCoverageTable(modalities) {
    const rows = (Array.isArray(modalities) ? modalities : []).map((item) => `
      <tr>
        <td><strong>${escapeHtml(String(item.label || item.key || "Modality"))}</strong></td>
        <td>${escapeHtml(String(Number(item.dataset_count || 0) + Number(item.study_count || 0)))}</td>
        <td>${escapeHtml(String(item.patient_count || 0))}</td>
        <td>${escapeHtml(String(item.sample_count || 0))}</td>
        <td>${escapeHtml(String(item.feature_count || 0))}</td>
        <td>${escapeHtml(String(item.clinical_overlap_count || 0))}</td>
      </tr>
    `).join("");
    return `
      <div class="assay-card-section">
        ${renderCoverageBars('Patients by data type', (Array.isArray(modalities) ? modalities : []).map(item => ({label:item.label || item.key || 'Modality', modality:item.key, count:item.patient_count})), 'patients')}
        <p class="section-note">Patients can appear in more than one data type. Counts are not additive; shared patients are shown below.</p>
        <details><summary>Detailed coverage counts</summary>
        <div class="assay-table-wrap">
          <table class="assay-table multimodal-readiness-table">
            <thead><tr><th>Modality</th><th>Resources</th><th>Patients</th><th>Samples</th><th>Features</th><th>Clinical overlap</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="6">No modalities found.</td></tr>'}</tbody>
          </table>
        </div>
        </details>
      </div>
    `;
  }

  function renderReadinessOverlaps(overlaps) {
    const useful = (Array.isArray(overlaps) ? overlaps : [])
      .filter((item) => item && item.left !== "clinical" && item.right !== "clinical")
      .sort((left, right) => Number(right.patient_overlap_count || 0) - Number(left.patient_overlap_count || 0))
      .slice(0, 6);
    const content = useful.length
      ? useful.map((item) => `
        <article class="cross-modal-pair">
          <div class="cross-modal-pair-types">
            <span>${assayOverviewIcon(item.left)}${escapeHtml(String(item.left_label || item.left))}</span>
            <span class="cross-modal-pair-connector" aria-label="and">+</span>
            <span>${assayOverviewIcon(item.right)}${escapeHtml(String(item.right_label || item.right))}</span>
          </div>
          <div class="cross-modal-pair-count"><strong>${escapeHtml(String(item.patient_overlap_count ?? '—'))}</strong> <span>shared ${Number(item.patient_overlap_count) === 1 ? 'patient' : 'patients'}</span></div>
          <div class="cross-modal-pair-samples">${escapeHtml(String(item.sample_overlap_count ?? 'Not reported'))} matching sample ${Number(item.sample_overlap_count) === 1 ? 'ID' : 'IDs'}</div>
        </article>
      `).join("")
      : '<div class="empty">No cross-modal overlap is currently available.</div>';
    return `<div class="assay-card-section"><strong>Cross-modal overlap</strong>
      <p class="section-note">Up to six pairs with the most shared patients. Patient overlap does not imply the same visit or specimen; exact samples require matching identifiers.</p>
      <div class="cross-modal-pairs">${content}</div></div>`;
  }

  function renderReadinessIssues(issues) {
    const items = Array.isArray(issues) ? issues : [];
    if (!items.length) {
      return '<div class="assay-card-section"><strong>Linkage checks</strong><div class="query-status">No multimodal linkage issues detected.</div></div>';
    }
    return `
      <div class="assay-card-section">
        <strong>Linkage checks</strong>
        <div class="multimodal-issue-list">
          ${items.slice(0, 5).map((item) => `<div class="query-status ${String(item.severity || "") === "error" ? "error" : ""}">${escapeHtml(String(item.message || "Readiness issue detected."))}</div>`).join("")}
        </div>
      </div>
    `;
  }


  function renderMultimodalReadiness(payload) {
    if (!multimodalReadinessStatusEl || !multimodalReadinessContentEl) return;
    const source = payload && typeof payload === "object" ? payload : {};
    const modalities = Array.isArray(source.modalities) ? source.modalities : [];
    const issues = Array.isArray(source.issues) ? source.issues : [];
    state.multimodalReadinessState = source;
    multimodalReadinessStatusEl.className = issues.some((item) => item && item.severity === "error") ? "query-status error" : "query-status";
    multimodalReadinessStatusEl.textContent = modalities.length
      ? `Readiness checked across ${modalities.length} modality layer${modalities.length === 1 ? "" : "s"}.`
      : "No multimodal readiness data available.";
    multimodalReadinessContentEl.innerHTML = `
      ${renderReadinessKpis(source.workspace || {})}
      ${renderReadinessCoverageTable(modalities)}
      ${renderReadinessOverlaps(source.pairwise_overlaps || [])}
      ${renderReadinessIssues(issues)}
    `;
    renderMultimodalReadinessVisibility();
  }

  function renderMultimodalReadinessError(message) {
    if (!multimodalReadinessStatusEl || !multimodalReadinessContentEl) return;
    state.multimodalReadinessState = null;
    multimodalReadinessStatusEl.className = "query-status";
    multimodalReadinessStatusEl.textContent = message || "Unable to load multimodal readiness.";
    multimodalReadinessContentEl.innerHTML = '<div class="empty">Multimodal readiness is unavailable for this workspace.</div>';
    renderMultimodalReadinessVisibility();
  }

  function renderMatrixKpis(metadata) {
    const source = metadata && typeof metadata === "object" ? metadata : {};
    const missingPct = `${(Number(source.missing_fraction || 0) * 100).toFixed(1)}%`;
    return `
      <div class="assay-kpi-grid multimodal-kpi-grid">
        <div class="assay-kpi"><span class="assay-kpi-label">Rows</span><strong class="assay-kpi-value">${escapeHtml(String(source.row_count || 0))}</strong></div>
        <div class="assay-kpi"><span class="assay-kpi-label">Columns</span><strong class="assay-kpi-value">${escapeHtml(String(source.column_count || 0))}</strong></div>
        <div class="assay-kpi"><span class="assay-kpi-label">Feature groups</span><strong class="assay-kpi-value">${escapeHtml(String(source.feature_group_count || 0))}</strong></div>
        <div class="assay-kpi"><span class="assay-kpi-label">Missing cells</span><strong class="assay-kpi-value">${escapeHtml(missingPct)}</strong></div>
      </div>
    `;
  }

  function renderMatrixFeatureGroups(groups) {
    const items = Array.isArray(groups) ? groups : [];
    const content = items.length
      ? items.map((item) => `
        <div class="multimodal-feature-group">
          <strong>${escapeHtml(String(item.label || item.dataset_name || "Feature group"))}</strong>
          <span class="query-chip badge">${escapeHtml(formatAssayModality(item.modality || "assay"))}</span>
          <small>${escapeHtml(String(item.feature_count_selected || 0))} columns · ${escapeHtml(String(item.exact_sample_match_count || 0))} exact sample matches</small>
        </div>
      `).join("")
      : '<div class="empty">No feature groups selected.</div>';
    return `<div class="assay-card-section"><strong>Provenance</strong><div class="multimodal-feature-group-list">${content}</div></div>`;
  }

  function renderMatrixMissingness(missingness) {
    const rows = (Array.isArray(missingness) ? missingness : [])
      .filter((item) => Number(item.missing_count || 0) > 0)
      .sort((left, right) => Number(right.missing_fraction || 0) - Number(left.missing_fraction || 0))
      .slice(0, 6);
    if (!rows.length) {
      return '<div class="assay-card-section"><strong>Missingness</strong><div class="query-status">No missing values in selected preview columns.</div></div>';
    }
    return `
      <div class="assay-card-section">
        <strong>Missingness</strong>
        <div class="multimodal-overlap-list">
          ${rows.map((item) => `
            <div class="multimodal-overlap-row">
              <span>${escapeHtml(String(item.label || item.key || "Column"))}</span>
              <strong>${escapeHtml(String(item.missing_count || 0))}</strong>
              <small>${escapeHtml((Number(item.missing_fraction || 0) * 100).toFixed(1))}%</small>
              <div class="assay-coverage-track missingness-track" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, Number(item.missing_fraction || 0) * 100))}%"></i></div>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderMatrixWarnings(warnings) {
    const items = Array.isArray(warnings) ? warnings : [];
    if (!items.length) return "";
    return `
      <div class="assay-card-section">
        <strong>Matrix checks</strong>
        <div class="multimodal-issue-list">
          ${items.slice(0, 4).map((item) => `<div class="query-status">${escapeHtml(String(item.message || "Matrix warning."))}</div>`).join("")}
        </div>
      </div>
    `;
  }

  function renderMatrixPreviewTable(columns, rows) {
    const columnItems = Array.isArray(columns) ? columns : [];
    const rowItems = Array.isArray(rows) ? rows : [];
    if (!columnItems.length || !rowItems.length) {
      return '<div class="assay-card-section"><strong>Preview</strong><div class="empty">No matrix rows available.</div></div>';
    }
    return `
      <div class="assay-card-section">
        <strong>Preview</strong>
        <div class="assay-table-wrap multimodal-matrix-table-wrap">
          <table class="assay-table multimodal-matrix-table">
            <thead>
              <tr>${columnItems.map((column) => `<th title="${escapeHtml(String(column.key || ""))}">${escapeHtml(String(column.label || column.key || "Column"))}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${rowItems.map((row) => {
                const values = row && typeof row.values === "object" ? row.values : {};
                return `<tr>${columnItems.map((column) => {
                  const key = String(column.key || "");
                  const value = values[key];
                  return `<td>${escapeHtml(value === null || typeof value === "undefined" ? "" : String(value))}</td>`;
                }).join("")}</tr>`;
              }).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderMultimodalMatrix(payload) {
    if (!multimodalMatrixStatusEl || !multimodalMatrixContentEl) return;
    const source = payload && typeof payload === "object" ? payload : {};
    const metadata = source.metadata && typeof source.metadata === "object" ? source.metadata : {};
    state.multimodalMatrixState = source;
    multimodalMatrixStatusEl.className = "query-status";
    multimodalMatrixStatusEl.textContent = Number(metadata.row_count || 0)
      ? `Sample-level matrix: ${metadata.row_count || 0} rows x ${metadata.column_count || 0} columns.`
      : "No matrix rows available.";
    multimodalMatrixContentEl.innerHTML = `
      ${renderMatrixKpis(metadata)}
      <details class="assay-card-section"><summary>Feature groups and provenance</summary>${renderMatrixFeatureGroups(source.feature_groups || [])}</details>
      ${renderMatrixMissingness(source.missingness || [])}
      ${renderMatrixWarnings(source.warnings || [])}
      ${renderMatrixPreviewTable(source.columns || [], source.rows || [])}
    `;
    renderMultimodalMatrixVisibility();
  }

  function renderMultimodalMatrixError(message) {
    if (!multimodalMatrixStatusEl || !multimodalMatrixContentEl) return;
    state.multimodalMatrixState = null;
    multimodalMatrixStatusEl.className = "query-status";
    multimodalMatrixStatusEl.textContent = message || "Unable to build multimodal feature matrix.";
    multimodalMatrixContentEl.innerHTML = '<div class="empty">Multimodal feature matrix is unavailable for this workspace.</div>';
    renderMultimodalMatrixVisibility();
  }

  function renderAssayOverlapSection(item) {
    const overlap = currentAssayScopeOverlap(item.patient_ids);
    if (!(overlap.scopeASize || overlap.scopeBSize)) return "";
    return `
      <div class="assay-card-section">
        <strong>Current Analysis scope</strong>
        <div class="assay-stats">
          <span class="query-chip badge">A overlap: ${escapeHtml(String(overlap.overlapA))} / ${escapeHtml(String(overlap.scopeASize || item.clinical_overlap_patient_count || 0))}</span>
          ${analysisCompareModeEl && analysisCompareModeEl.checked ? `<span class="query-chip badge">B overlap: ${escapeHtml(String(overlap.overlapB))} / ${escapeHtml(String(overlap.scopeBSize || item.clinical_overlap_patient_count || 0))}</span>` : ""}
        </div>
      </div>
    `;
  }

  function renderTranscriptomicsHighlights(item) {
    const expected = item.data_type === "rsem_expected_counts";
    const summaryNumber = (value) => value != null && Number.isFinite(Number(value))
      ? escapeHtml(Number(value).toFixed(1)) : "Not calculated";
    const topGenes = Array.isArray(item.top_genes) ? item.top_genes : [];
    const topGenesMarkup = topGenes.length
      ? topGenes.map((gene) => {
        const title = [
          String(gene.gene_id || "").trim(),
          String(gene.gene_symbol || "").trim(),
          String(gene.gene_name || "").trim(),
          `Total ${expected ? "expected" : "raw"} count: ${String(gene.total_count ?? gene.total_raw_count ?? "Not calculated")}`,
        ].filter(Boolean).join(" • ");
        if (gene.ensembl_url) {
          return `<a class="assay-gene-pill assay-gene-pill-link" href="${escapeHtml(String(gene.ensembl_url || ""))}" target="_blank" rel="noopener" title="${escapeHtml(title)}">${escapeHtml(gene.gene_id)}</a>`;
        }
        return `<span class="assay-gene-pill" title="${escapeHtml(title)}">${escapeHtml(gene.gene_id)}</span>`;
      }).join("")
      : '<span class="section-note">No top-gene summary available.</span>';
    return `
      <div class="assay-card-section">
        <strong>Transcriptomics coverage</strong>
        <div class="assay-summary-grid">
          <div class="assay-summary-item"><span>${expected ? "Expected" : "Total"} counts / sample</span><strong>${summaryNumber(item.mean_total_counts_per_sample)}</strong></div>
          <div class="assay-summary-item"><span>Genes with counts &gt; 0 / sample</span><strong>${summaryNumber(item.mean_detected_genes_per_sample)}</strong></div>
        </div>
      </div>
      <div class="assay-card-section">
        <strong>Top abundant genes</strong>
        <div class="assay-gene-list">${topGenesMarkup}</div>
      </div>
    `;
  }

  function renderGenericAssayHighlights(item) {
    const modality = normalizedAssayModality(item.modality);
    const featureLabel = String(item.feature_label || "features").trim();
    const namespace = String(item.feature_id_type || item.feature_namespace || "feature_id").trim();
    const valueKind = String(item.value_kind || normalizedAssayDataType(item) || item.data_type || "feature_matrix").trim();
    const title = modality === "imaging" ? "Derived DICOM measurements" : `${formatAssayModality(modality)} matrix`;
    return `
      <details class="assay-card-section assay-technical-details">
        <summary>${escapeHtml(title)} · technical details</summary>
        <div class="assay-summary-grid">
          <div class="assay-summary-item"><span>Feature type</span><strong>${escapeHtml(featureLabel)}</strong></div>
          <div class="assay-summary-item"><span>Namespace</span><strong>${escapeHtml(namespace.replace(/_/g, " "))}</strong></div>
          <div class="assay-summary-item"><span>Value kind</span><strong>${escapeHtml(formatAssayDataType(valueKind))}</strong></div>
        </div>
      </details>
    `;
  }

  function assayOverviewIcon(modality) {
    const paths = {
      clinical: 'M9 3h6v3h4v15H5V6h4ZM9 3v5h6V3M8 12h8M8 16h5',
      dicom: 'M3 4h18v16H3ZM3 16l5-5 5 5 3-3 5 5M15 8h2',
      transcriptomics: 'M6 3c0 8 12 10 12 18M18 3c0 8-12 10-12 18M8 6h8M8 18h8M10 10h4M10 14h4',
      methylation: 'M6 3c0 8 12 10 12 18M18 3c0 8-12 10-12 18M8 6h8M8 18h8M19 7h3m-1-2v4',
      imaging: 'M3 4h18v16H3ZM3 16l5-5 5 5 3-3 5 5M15 8h2',
    };
    return `<svg class="assay-overview-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[modality] || 'M9 3h6M10 3v6L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M7 15h10'}"/></svg>`;
  }

  function renderAssayLinkage(item) {
    const total = Number(item.patient_count), linked = Number(item.clinical_overlap_patient_count);
    if (item.patient_count == null || item.clinical_overlap_patient_count == null || !Number.isFinite(total) || !Number.isFinite(linked) || total <= 0 || linked < 0 || linked > total) {
      return '<div class="assay-linkage"><strong>Clinical linkage</strong><span class="section-note">Coverage not available.</span></div>';
    }
    const percent = linked / total * 100;
    return `<div class="assay-linkage">
      <div><strong>Clinical linkage</strong><span>${escapeHtml(formatNumber(linked))} of ${escapeHtml(formatNumber(total))} assay patients · ${percent.toFixed(0)}%</span></div>
      <div class="assay-coverage-track" aria-hidden="true"><i style="width:${percent}%"></i></div>
      <small>${total === linked ? 'All assay patients have a linked clinical record.' : `${escapeHtml(formatNumber(total - linked))} assay patients have no linked clinical record in this workspace.`}</small>
    </div>`;
  }

  function renderAssayDashboardCard(item) {
    const modality = normalizedAssayModality(item.modality);
    const isTranscriptomics = modality === "transcriptomics";
    return `
      <article class="assay-dashboard-card assay-dashboard-card-${escapeHtml(modality)}">
        <div class="assay-card-header">
          <div>
            <div class="assay-card-eyebrow">${escapeHtml(modality === "imaging" ? "Imaging measurements" : isTranscriptomics ? "Expression assay" : `${formatAssayModality(modality)} assay`)}</div>
            <strong class="assay-card-title">${escapeHtml(item.label || item.dataset_name)}</strong>
          </div>
          <span class="assay-modality-badge">${assayOverviewIcon(modality)}${escapeHtml(formatAssayModality(modality))}</span>
        </div>
        <div class="assay-card-meta">
          <span class="dataset-picker-tag">${escapeHtml(item.dataset_name)}</span>
          <span class="dataset-picker-tag">${escapeHtml(formatAssayDataType(normalizedAssayDataType(item) || item.data_type))}</span>
        </div>
        <div class="assay-kpi-grid">
          <div class="assay-kpi"><span class="assay-kpi-label">Samples</span><strong class="assay-kpi-value">${escapeHtml(String(item.sample_count || 0))}</strong></div>
          <div class="assay-kpi"><span class="assay-kpi-label">Patients</span><strong class="assay-kpi-value">${escapeHtml(String(item.patient_count || 0))}</strong></div>
          <div class="assay-kpi"><span class="assay-kpi-label">Features</span><strong class="assay-kpi-value">${escapeHtml(String(item.feature_count || item.gene_count || 0))}</strong></div>
        </div>
        ${renderAssayLinkage(item)}
        ${isTranscriptomics ? renderTranscriptomicsHighlights(item) : renderGenericAssayHighlights(item)}
        ${renderAssayOverlapSection(item)}
      </article>
    `;
  }

  function filteredAssayDatasets(datasets) {
    const selected = selectedAssayModalityFilter();
    const items = Array.isArray(datasets) ? datasets : [];
    if (selected === "all") return items;
    return items.filter((item) => normalizedAssayModality(item && item.modality) === selected);
  }

  function renderAssayDashboardCards(datasets) {
    if (!assayDashboardCardsEl) return;
    const allItems = Array.isArray(datasets) ? datasets : [];
    for (const axis of ["X", "Y"]) {
      const select = document.getElementById(`associationAssay${axis}`);
      if (!select) continue;
      const previous = select.value;
      select.innerHTML = '<option value="">Choose a matrix</option>' + allItems.map(item => `<option value="${escapeHtml(item.dataset_name)}">${escapeHtml(formatAssayModality(item.modality))} · ${escapeHtml(item.label || item.dataset_name)}</option>`).join("");
      if (allItems.some(item => item.dataset_name === previous)) select.value = previous;
      const feature = document.getElementById(`associationFeature${axis}`);
      const search = document.getElementById(`associationSearch${axis}`);
      const status = document.getElementById(`associationFeatureStatus${axis}`);
      document.querySelector(`label[for="associationSearch${axis}"]`).textContent = `Search ${axis} features`;
      search.placeholder = "Name, description or ID";
      let description = document.getElementById(`associationDescription${axis}`);
      if (!description) {
        description = document.createElement("p");
        description.id = `associationDescription${axis}`;
        description.className = "section-note";
        description.setAttribute("role", "status");
        feature.after(description);
        feature.setAttribute("aria-describedby", `${status.id} ${description.id}`);
      }
      let annotations = {};
      feature.onchange = () => {
        const annotation = annotations[feature.value] || {};
        description.textContent = feature.value ? [
          annotation.description || annotation.gene_name || "No description supplied for this feature.",
          annotation.unit ? `Units: ${annotation.unit}.` : "Units not supplied.",
        ].join(" ") : "";
      };
      // Invalidates responses from previous renders as well as rapid searches.
      const resetFeatures = (label) => {
        feature._request = {};
        feature.innerHTML = `<option value="">${escapeHtml(label)}</option>`;
        feature.disabled = true;
        status.textContent = "";
        description.textContent = "";
        annotations = {};
      };
      let searchTimer;
      const loadFeatures = async () => {
        if (!select.value) return;
        resetFeatures("Loading features…");
        const request = feature._request;
        const assay = select.value;
        const scope = state.currentDatasetScopeId;
        const isCurrent = () => feature._request === request && select.value === assay && state.currentDatasetScopeId === scope;
        try {
          const response = await fetch(`/assays/features?data_dir=${encodeURIComponent(scope)}&assay_id=${encodeURIComponent(assay)}&q=${encodeURIComponent(search.value.trim())}&limit=50`);
          if (!response.ok) throw new Error("Feature lookup failed");
          const payload = await response.json();
          if (!isCurrent()) return;
          const ids = payload.genes || [];
          annotations = payload.annotations || {};
          feature.innerHTML = `<option value="">${ids.length ? "Choose a feature" : "No matching features"}</option>` + ids.map(id => {
            const annotation = annotations[id] || {};
            const label = annotation.label || annotation.gene_symbol || annotation.gene_name;
            return `<option value="${escapeHtml(id)}">${escapeHtml(label ? `${label} · ${id}` : `${id} · Name not supplied`)}</option>`;
          }).join("");
          feature.disabled = !ids.length;
          status.textContent = ids.length >= 50 ? "Showing up to 50 matches. Search to narrow the list." : `${ids.length} available feature${ids.length === 1 ? "" : "s"}${search.value.trim() ? " matching your search" : ""}.`;
          return true;
        } catch (_) {
          if (!isCurrent()) return;
          resetFeatures("Features unavailable");
          status.textContent = "Could not load features. Edit the search or reselect the matrix to retry.";
        }
      };
      select.onchange = () => {
        clearTimeout(searchTimer);
        search.value = "";
        search.disabled = !select.value;
        resetFeatures("Choose a matrix first");
        return loadFeatures();
      };
      search.oninput = () => {
        clearTimeout(searchTimer);
        resetFeatures("Searching features…");
        const request = feature._request;
        searchTimer = setTimeout(() => {
          if (feature._request === request) void loadFeatures();
        }, 250);
      };
      select.onchange();
    }
    const examples = document.getElementById("associationExamples");
    if (examples) {
      const flow = "synthetic_autoimmune_flow_cytometry";
      const serology = "synthetic_autoimmune_serology";
      examples.hidden = ![flow, serology].every(id => allItems.some(item => item.dataset_name === id));
      examples.innerHTML = examples.hidden ? "" : `<strong>Try a synthetic comparison</strong>
        <p>These examples explore how two simulated measurements vary together. They are not biological findings.</p>
        <button type="button" class="query-chip" data-example-x="CD4_T_cells_fraction" data-example-y="CRP_mg_L">CD4 T cells × C-reactive protein</button>
        <p>Compare a cell fraction with a soluble protein measurement.</p>
        <button type="button" class="query-chip" data-example-x="B_cells_fraction" data-example-y="Anti_dsDNA_IU_mL">B cells × anti-double-stranded DNA antibodies</button>
        <p>Compare a cell fraction with an antibody measurement. Neither example runs until you review it in Analysis.</p>`;
      examples.querySelectorAll("button").forEach(button => {
        button.onclick = async () => {
          await Promise.all([['X', flow, button.dataset.exampleX], ['Y', serology, button.dataset.exampleY]].map(async ([axis, assay, id]) => {
            const matrix = document.getElementById(`associationAssay${axis}`);
            matrix.value = assay;
            const loaded = await matrix.onchange();
            const feature = document.getElementById(`associationFeature${axis}`);
            if (loaded && matrix.value === assay && Array.from(feature.options).some(option => option.value === id)) {
              feature.value = id;
              feature.onchange();
            }
          }));
        };
      });
    }
    const associationBtn = document.getElementById("associationOpenBtn");
    if (associationBtn) {
      associationBtn.disabled = allItems.length < 2;
      associationBtn.onclick = () => {
        const parameters = {};
        for (const axis of ["X", "Y"]) {
          parameters[`assay_${axis.toLowerCase()}`] = document.getElementById(`associationAssay${axis}`).value;
          parameters[`feature_${axis.toLowerCase()}`] = document.getElementById(`associationFeature${axis}`).value.trim();
        }
        if (Object.values(parameters).some(value => !value)) {
          document.getElementById("associationStatus").textContent = "Choose both matrices and select a feature from each dropdown.";
          return;
        }
        sendPromptToAnalysis(`Compare measurements: ${JSON.stringify(parameters)}`);
        document.getElementById("associationStatus").textContent = "Comparison prompt ready. Review the question and cohort scope, keep A/B comparison off, then select Run analysis.";
      };
    }
    const imagingItems = allItems.filter((item) => normalizedAssayModality(item.modality) === "imaging");
    const imagingCards = document.getElementById("imagingDashboardCards");
    if (imagingCards) imagingCards.innerHTML = imagingItems.length
      ? imagingItems.map((item) => renderAssayDashboardCard(item)).join("")
      : '<div class="empty">No derived imaging measurements in this workspace. DICOM studies, when available, are listed above.</div>';
    const items = allItems.filter((item) => normalizedAssayModality(item.modality) !== "imaging");
    renderAssayDashboardOverview(items);
    renderAssayModalityTabs(items);
    renderDicomPanelVisibility();
    renderTranscriptomicsQuickExpressionVisibility();
    renderMultimodalReadinessVisibility();
    renderMultimodalMatrixVisibility();
    if (!items.length) {
      assayDashboardCardsEl.innerHTML = '<div class="empty">No assay data to display. Check the workspace selection and assay availability in Datasets.</div>';
      return;
    }
    const selected = selectedAssayModalityFilter();
    const visibleItems = filteredAssayDatasets(items);
    if (!visibleItems.length) {
      assayDashboardCardsEl.innerHTML = '<div class="empty">No assays match the selected modality. Choose another modality filter to see the available assays.</div>';
      return;
    }
    assayDashboardCardsEl.innerHTML = `
      <section class="assay-modality-section">
        <div class="assay-modality-section-header">
          <strong>${escapeHtml(selected === "all" ? "All assays" : formatAssayModality(selected))}</strong>
          <span class="query-chip badge">${escapeHtml(String(visibleItems.length))} assay${visibleItems.length === 1 ? "" : "s"}</span>
        </div>
        <div class="assay-dashboard-grid">
          ${visibleItems.map((item) => renderAssayDashboardCard(item)).join("")}
        </div>
      </section>
    `;
  }

  function handleAssayModalityFilter(value) {
    state.assayDashboardModalityFilter = String(value || "all").trim() || "all";
    renderAssayDashboardCards(state.assayDatasetsState || []);
  }

  async function loadMultimodalReadiness(options = {}) {
    if (!multimodalReadinessStatusEl || !multimodalReadinessContentEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const dataDir = encodeURIComponent(scopeId);
    multimodalReadinessStatusEl.className = "query-status loading";
    multimodalReadinessStatusEl.textContent = "Checking multimodal readiness...";
    multimodalReadinessContentEl.innerHTML = '<div class="empty">Checking modality overlap and linkage...</div>';
    try {
      const response = await fetch(`/assays/readiness?data_dir=${dataDir}`);
      if (!response.ok) throw new Error("Unable to load multimodal readiness.");
      const payload = await response.json();
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalReadiness(payload);
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalReadinessError(error && error.message ? error.message : "Unable to load multimodal readiness.");
    }
  }

  async function loadMultimodalMatrix(options = {}) {
    if (!multimodalMatrixStatusEl || !multimodalMatrixContentEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const dataDir = encodeURIComponent(scopeId);
    multimodalMatrixStatusEl.className = "query-status loading";
    multimodalMatrixStatusEl.textContent = "Building multimodal feature matrix...";
    multimodalMatrixContentEl.innerHTML = '<div class="empty">Joining clinical, assay, and imaging metadata...</div>';
    try {
      const response = await fetch(`/assays/matrix?data_dir=${dataDir}&max_features_per_dataset=3&max_rows=12`);
      if (!response.ok) throw new Error("Unable to build multimodal feature matrix.");
      const payload = await response.json();
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalMatrix(payload);
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderMultimodalMatrixError(error && error.message ? error.message : "Unable to build multimodal feature matrix.");
    }
  }

  async function loadAssayFeatureSuggestions() {
    if (!analysisAssayGenesEl) return;
    const datasetNames = selectedTranscriptomicsAssayDatasetNames();
    if (!datasetNames.length) {
      analysisAssayGenesEl.innerHTML = "";
      return;
    }
    const query = encodeURIComponent(String(analysisAssayGeneEl && analysisAssayGeneEl.value ? analysisAssayGeneEl.value.trim() : ""));
    const scopeId = String((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()).trim();
    const dataDir = encodeURIComponent(scopeId);
    try {
      const payloads = await Promise.all(datasetNames.map(async (datasetName) => {
        const dataset = encodeURIComponent(datasetName);
        const response = await fetch(`/assays/features?data_dir=${dataDir}&assay_id=${dataset}&q=${query}&limit=50`);
        if (!response.ok) throw new Error("Unable to load assay features.");
        return response.json();
      }));
      const genes = Array.from(new Set(payloads.flatMap((payload) => Array.isArray(payload.genes) ? payload.genes : []))).sort();
      const annotations = payloads.reduce((acc, payload) => {
        const current = payload && payload.annotations && typeof payload.annotations === "object" ? payload.annotations : {};
        return { ...acc, ...current };
      }, {});
      if (!isCurrentWorkspaceScope(scopeId)) return;
      analysisAssayGenesEl.innerHTML = genes.map((geneId) => {
        const annotation = annotations[geneId] && typeof annotations[geneId] === "object" ? annotations[geneId] : {};
        const geneSymbol = String(annotation.gene_symbol || "").trim();
        const geneName = String(annotation.gene_name || "").trim();
        const title = [geneId, geneSymbol, geneName].filter(Boolean).join(" • ");
        const label = geneSymbol ? `${geneSymbol} · ${geneId}` : geneId;
        return `<option value="${escapeHtml(geneId)}" label="${escapeHtml(label)}" title="${escapeHtml(title || geneId)}"></option>`;
      }).join("");
    } catch (_error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      analysisAssayGenesEl.innerHTML = "";
    }
  }

  async function loadAssayDatasets(options = {}) {
    if (!analysisAssayStatusEl || !assayDashboardStatusEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const previousScopeId = String(state.assayDatasetsScopeId || "").trim();
    const scopeChanged = previousScopeId !== scopeId;
    state.assayDatasetsScopeId = scopeId;
    if (scopeChanged) {
      clearAssayWorkspaceSelection();
    }
    const dataDir = encodeURIComponent(scopeId);
    void loadDicomStudies({ scopeId });
    void loadMultimodalReadiness({ scopeId });
    void loadMultimodalMatrix({ scopeId });
    analysisAssayStatusEl.className = "query-status loading";
    analysisAssayStatusEl.textContent = "Checking transcriptomics assays...";
    if (analysisCatalogAssayStatusEl) {
      analysisCatalogAssayStatusEl.textContent = "Checking assays...";
    }
    assayDashboardStatusEl.className = "query-status loading";
    assayDashboardStatusEl.textContent = "Checking assays...";
    try {
      const payload = options.prefetched && typeof options.prefetched === "object"
        ? options.prefetched
        : await (async () => {
          const response = await fetch(`/assays?data_dir=${dataDir}`);
          if (!response.ok) throw new Error("Unable to load assay datasets.");
          return response.json();
        })();
      if (!isCurrentWorkspaceScope(scopeId)) return;
      const datasets = Array.isArray(payload.datasets) ? payload.datasets : [];
      state.assayDatasetsState = datasets;
      syncSelectedAssayDatasets();
      renderAssayDashboardCards(state.assayDatasetsState);
      if (typeof renderAnalysisCatalogAssayPanel === "function") {
        renderAnalysisCatalogAssayPanel();
      }
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
      if (!datasets.length) {
        analysisAssayStatusEl.className = "query-status";
        analysisAssayStatusEl.textContent = "No raw-count transcriptomics assays are currently available for quick expression checks.";
        if (analysisCatalogAssayStatusEl) {
          analysisCatalogAssayStatusEl.textContent = "No compatible assay datasets are currently available in this workspace.";
        }
        assayDashboardStatusEl.className = "query-status";
        assayDashboardStatusEl.textContent = "No assay datasets are currently available.";
        renderAssayExpressionResult(null);
        return;
      }
      analysisAssayStatusEl.className = "query-status";
      const transcriptomicsCount = datasets.filter((dataset) => isQuickExpressionDataset(dataset)).length;
      analysisAssayStatusEl.textContent = transcriptomicsCount
        ? `Loaded ${transcriptomicsCount} raw-count transcriptomics assay${transcriptomicsCount === 1 ? "" : "s"} for quick expression checks.`
        : "No raw-count transcriptomics assays are currently available for quick expression checks.";
      if (analysisCatalogAssayStatusEl) {
        analysisCatalogAssayStatusEl.textContent = datasets.length === 1
          ? `1 assay dataset available for Analysis.`
          : `${datasets.length} assays available. Some assay tools require exactly one selected assay.`;
      }
      assayDashboardStatusEl.className = "query-status";
      const laboratoryCount = datasets.filter((item) => normalizedAssayModality(item.modality) !== "imaging").length;
      assayDashboardStatusEl.textContent = `Loaded ${laboratoryCount} laboratory assay${laboratoryCount === 1 ? "" : "s"}.`;
      await loadAssayFeatureSuggestions();
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = error && error.message ? error.message : "Unable to load transcriptomics assays.";
      if (analysisCatalogAssayStatusEl) {
        analysisCatalogAssayStatusEl.textContent = error && error.message ? error.message : "Unable to load assay datasets.";
      }
      assayDashboardStatusEl.className = "query-status";
      assayDashboardStatusEl.textContent = error && error.message ? error.message : "Unable to load assay datasets.";
      state.assayDatasetsState = [];
      clearAssayWorkspaceSelection();
      renderAssayDatasetSelector();
      renderAssayDashboardCards(state.assayDatasetsState);
      if (assayDashboardCardsEl) {
        assayDashboardCardsEl.innerHTML = '<div class="workspace-notice workspace-notice-unavailable" role="status"><strong>Assays unavailable</strong><p>Assay information could not be loaded. This does not mean the workspace has no assays. Apply workspace again in Datasets to retry.</p></div>';
      }
      const imagingCards = document.getElementById("imagingDashboardCards");
      if (imagingCards) imagingCards.innerHTML = '<div class="workspace-notice workspace-notice-unavailable" role="status"><strong>Imaging measurements unavailable</strong><p>The measurement inventory could not be loaded. Apply workspace again in Datasets to retry.</p></div>';
      if (typeof renderAnalysisCatalogAssayPanel === "function") {
        renderAnalysisCatalogAssayPanel();
      }
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
    }
  }

  async function runAssayExpressionAnalysis() {
    if (!analysisAssayGeneEl || !analysisAssayStatusEl) return;
    const datasetNames = selectedTranscriptomicsAssayDatasetNames();
    const geneId = String(analysisAssayGeneEl.value || "").trim();
    if (!datasetNames.length || !geneId) {
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = "Choose at least one raw-count transcriptomics assay and a gene ID first.";
      return;
    }
    analysisAssayStatusEl.className = "query-status loading";
    analysisAssayStatusEl.textContent = "Fetching transcriptomics expression summary...";
    const scopeId = String((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()).trim();
    try {
      const selectedCohortA = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
        : null;
      const selectedCohortB = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
        : null;
      const payloads = await Promise.all(datasetNames.map(async (datasetName) => {
        const response = await fetch("/assays/expression", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
            assay_id: datasetName,
            gene_id: geneId,
            selected_patient_ids: selectedCohortA && Array.isArray(selectedCohortA.patient_ids)
              ? selectedCohortA.patient_ids.join(",")
              : analysisSelectedPatientIdsEl.value.trim(),
            compare_selected_patient_ids: analysisCompareModeEl && analysisCompareModeEl.checked
              ? (selectedCohortB && Array.isArray(selectedCohortB.patient_ids)
                ? selectedCohortB.patient_ids.join(",")
                : analysisCompareSelectedPatientIdsEl.value.trim())
              : "",
          }),
        });
        if (!response.ok) throw new Error("Unable to fetch transcriptomics expression.");
        return response.json();
      }));
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderAssayExpressionResult(payloads);
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = `Expression summary ready for ${geneId} across ${datasetNames.length} assay${datasetNames.length === 1 ? "" : "s"}.`;
    } catch (error) {
      if (!isCurrentWorkspaceScope(scopeId)) return;
      renderAssayExpressionResult(null);
      analysisAssayStatusEl.className = "query-status";
      analysisAssayStatusEl.textContent = error && error.message ? error.message : "Unable to fetch transcriptomics expression.";
    }
  }

  function handleAssayDatasetSelectionChange(sourceEl = null, changedInput = null) {
    const listEl = sourceEl || analysisAssayDatasetListEl || analysisCatalogAssayDatasetListEl;
    if (!listEl) return;
    let selected = Array.from(listEl.querySelectorAll('input[type="checkbox"]:checked'))
      .map((item) => item.value)
      .filter(Boolean);
    const item = currentAnalysisCatalogItem();
    if (requiresSingleSelectedAssayDataset(item) && selected.length > 1) {
      const changedValue = changedInput && changedInput.checked ? String(changedInput.value || "").trim() : "";
      selected = changedValue ? [changedValue] : selected.slice(-1);
    }
    state.selectedAssayDatasets = selected;
    renderAssayDatasetSelector();
    void loadAssayFeatureSuggestions();
  }

  function handleAssayFeatureInput() {
    void loadAssayFeatureSuggestions();
  }

  function closeClaridPopovers(except = null) {
    document.querySelectorAll(".clarid-identity.is-open").forEach((identity) => {
      if (identity === except) return;
      identity.classList.remove("is-open");
      const toggle = identity.querySelector("[data-clarid-toggle]");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    });
  }

  async function handleClaridAction(event) {
    const copyButton = event.target.closest("[data-clarid-copy]");
    const toggle = event.target.closest("[data-clarid-toggle]");
    if (!copyButton && !toggle) return false;
    event.preventDefault();
    event.stopPropagation();
    if (toggle) {
      const identity = toggle.closest(".clarid-identity");
      const nextOpen = identity && !identity.classList.contains("is-open");
      closeClaridPopovers(nextOpen ? identity : null);
      if (identity) identity.classList.toggle("is-open", Boolean(nextOpen));
      toggle.setAttribute("aria-expanded", nextOpen ? "true" : "false");
      return true;
    }
    const value = String(copyButton.dataset.claridCopy || "");
    let copied = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        copied = true;
      } else {
        copied = fallbackCopyText(value);
      }
    } catch (_error) {
      copied = false;
    }
    const original = copyButton.textContent;
    copyButton.textContent = copied ? "Copied" : "Unavailable";
    window.setTimeout(() => { copyButton.textContent = original; }, 1400);
    return true;
  }

  return {
    claridIdentityMarkup,
    renderPatientList,
    renderDetail,
    renderDashboard,
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
    renderAssayDatasetSelector,
    renderAssayExpressionResult,
    renderAssayDashboardCards,
    handleAssayModalityFilter,
    renderDicomStudies,
    clearDatasetWorkspaceViews,
    loadDicomStudies,
    loadAssayDatasets,
    runAssayExpressionAnalysis,
    handleAssayDatasetSelectionChange,
    handleAssayFeatureInput,
    assayDatasetOverlap,
    handleClaridAction,
    closeClaridPopovers,
  };
}
