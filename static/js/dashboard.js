export function createDashboardUi(ctx) {
  const { refs, helpers, callbacks, state, constants } = ctx;
  const {
    patientsEl,
    patientSearchEl,
    dashboardEl,
    dashboardTimelineEl,
    detailEl,
    dataDirEl,
    molecularDashboardStatusEl,
    molecularDashboardCardsEl,
    analysisMolecularDatasetListEl,
    analysisCatalogMolecularDatasetListEl,
    analysisMolecularGeneEl,
    analysisMolecularGenesEl,
    analysisMolecularStatusEl,
    analysisCatalogMolecularStatusEl,
    analysisMolecularResultEl,
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
    renderAnalysisCatalog,
    renderAnalysisCatalogMolecularPanel,
  } = callbacks;
  const { MAX_VISIBLE_PATIENTS } = constants;
  const DASHBOARD_PLOT_COLORS = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed", "#ea580c", "#dc2626"];
  const DASHBOARD_TIMELINE_DOMAINS = [
    { key: "diseases", label: "Disease", color: "#1d4ed8", symbol: "circle" },
    { key: "treatments", label: "Treatment", color: "#92400e", symbol: "diamond" },
    { key: "phenotypic_features", label: "Phenotype", color: "#166534", symbol: "square" },
    { key: "measures", label: "Measure", color: "#0f766e", symbol: "triangle-up" },
    { key: "procedures", label: "Procedure", color: "#b91c1c", symbol: "cross" },
    { key: "exposures", label: "Exposure", color: "#6d28d9", symbol: "x" },
    { key: "molecular", label: "Molecular", color: "#0891b2", symbol: "star" },
  ];

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
    const plotResult = window.Plotly.newPlot(el, traces, layout, { ...dashboardPlotConfig(), ...configOverrides });
    if (typeof afterPlot === "function") {
      Promise.resolve(plotResult).then(() => afterPlot(el)).catch(() => {});
    }
    window.requestAnimationFrame(() => {
      if (window.Plotly && window.Plotly.Plots && typeof window.Plotly.Plots.resize === "function") {
        window.Plotly.Plots.resize(el);
      }
    });
  }

  function timelineSelectedPatientIds() {
    if (!Array.isArray(state.dashboardTimelineSelectedPatientIds)) {
      state.dashboardTimelineSelectedPatientIds = [];
    }
    return state.dashboardTimelineSelectedPatientIds.map((item) => String(item || "").trim()).filter(Boolean);
  }

  function timelineSelectedPatientSet() {
    return new Set(timelineSelectedPatientIds());
  }

  function setTimelineSelectedPatientIds(ids) {
    state.dashboardTimelineSelectedPatientIds = Array.from(new Set((Array.isArray(ids) ? ids : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean))).sort();
  }

  function currentRosterPatients() {
    const query = String(patientSearchEl && patientSearchEl.value ? patientSearchEl.value : "").trim().toLowerCase();
    const patients = Array.isArray(state.currentPatients) ? state.currentPatients : [];
    if (!query) return patients;
    return patients.filter((patient) => String(patient && patient.patient_id ? patient.patient_id : "").toLowerCase().includes(query));
  }

  function toggleTimelinePatient(patientId, summary) {
    const normalized = String(patientId || "").trim();
    if (!normalized) return;
    const selected = timelineSelectedPatientSet();
    if (selected.has(normalized)) {
      selected.delete(normalized);
    } else {
      selected.add(normalized);
    }
    setTimelineSelectedPatientIds(Array.from(selected));
    renderPatientList(currentRosterPatients());
    renderDashboardTimeline(summary);
  }

  function toggleTimelinePatientSelection(patientId) {
    toggleTimelinePatient(patientId, state.dashboardSummaryState || state.dashboardSummary || {});
  }

  function patientIdFromTimelinePoint(point) {
    if (!point || typeof point !== "object") return "";
    const direct = point.customdata;
    if (Array.isArray(direct) && direct.length) {
      return String(direct[0] || "").trim();
    }
    if (direct !== undefined && direct !== null) {
      return String(direct || "").trim();
    }
    const index = Number.isInteger(point.pointNumber)
      ? point.pointNumber
      : (Number.isInteger(point.pointIndex) ? point.pointIndex : null);
    const traceCustomData = point.data && Array.isArray(point.data.customdata) ? point.data.customdata : [];
    if (index !== null && traceCustomData.length > index) {
      const value = traceCustomData[index];
      if (Array.isArray(value) && value.length) {
        return String(value[0] || "").trim();
      }
      if (value !== undefined && value !== null) {
        return String(value || "").trim();
      }
    }
    const fullTraceCustomData = point.fullData && Array.isArray(point.fullData.customdata) ? point.fullData.customdata : [];
    if (index !== null && fullTraceCustomData.length > index) {
      const value = fullTraceCustomData[index];
      if (Array.isArray(value) && value.length) {
        return String(value[0] || "").trim();
      }
      if (value !== undefined && value !== null) {
        return String(value || "").trim();
      }
    }
    return String(point.y || point.label || "").trim();
  }

  function setTimelineSelectionFromPoints(points, summary) {
    const ids = (Array.isArray(points) ? points : [])
      .map((point) => patientIdFromTimelinePoint(point))
      .filter(Boolean);
    if (!ids.length) return;
    setTimelineSelectedPatientIds(ids);
    renderDashboardTimeline(summary);
  }

  function setTimelineStatus(message) {
    const statusEl = document.getElementById("dashboard-timeline-selection-status");
    if (statusEl) {
      statusEl.textContent = message;
    }
  }

  async function saveTimelineSelection() {
    const selectedIds = timelineSelectedPatientIds();
    if (!selectedIds.length || typeof saveIdsAsCohort !== "function") {
      setTimelineStatus("Select one or more patients in the timeline first.");
      return;
    }
    const saved = await saveIdsAsCohort({
      patientIds: selectedIds,
      sourceKind: "dashboard_timeline",
      sourcePrompt: `Dashboard timeline selection (${selectedIds.length} patients)`,
      statusTarget: "analysis",
    });
    setTimelineStatus(saved ? `Saved ${selectedIds.length} selected patient${selectedIds.length === 1 ? "" : "s"} as a cohort.` : "Unable to save selected timeline cohort.");
  }

  function sendTimelineSelectionToAnalysis() {
    const selectedIds = timelineSelectedPatientIds();
    if (!selectedIds.length || typeof sendPatientIdsToAnalysis !== "function") {
      setTimelineStatus("Select one or more patients in the timeline first.");
      return;
    }
    sendPatientIdsToAnalysis(selectedIds, { sourceLabel: "Dashboard timeline" });
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
    if (visitEntries.length) {
      mountPlot(
        "dashboard-plot-visits",
        [{
          type: "bar",
          x: visitEntries.map(([label]) => label),
          y: visitEntries.map(([, value]) => Number(value || 0)),
          marker: { color: "#7c3aed" },
          hovertemplate: "%{x} visits: %{y}<extra></extra>",
        }],
        dashboardPlotLayout({
          xaxis: { ...dashboardPlotLayout().xaxis, title: { text: "Visits per patient bucket", font: { color: "#61758c", size: 12 } } },
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

  function normalizeTimelineItems(summary) {
    const timelines = Array.isArray(summary && summary.timelines) ? summary.timelines : [];
    const molecularCoverage = molecularTimelineCoverage();
    return timelines
      .map((item) => {
        const patientId = String(item && item.patient_id ? item.patient_id : "").trim();
        const firstDate = String(item && item.first_event_date ? item.first_event_date : "").trim();
        const lastDate = String(item && item.last_event_date ? item.last_event_date : "").trim() || firstDate;
        const firstTime = Date.parse(firstDate);
        const lastTime = Date.parse(lastDate);
        const hasDatedRange = patientId && Number.isFinite(firstTime) && Number.isFinite(lastTime);
        return {
          patient_id: patientId,
          visit_count: Number(item && item.visit_count ? item.visit_count : 0),
          first_event_date: firstDate,
          last_event_date: lastDate,
          first_time: hasDatedRange ? firstTime : null,
          last_time: hasDatedRange ? Math.max(lastTime, firstTime) : null,
          has_dated_range: Boolean(hasDatedRange),
          events: [
            ...(Array.isArray(item && item.events) ? item.events : []),
            ...molecularTimelineEvents(patientId, firstDate, lastDate, molecularCoverage.get(patientId)),
          ].map((event) => {
            const eventDate = String(event && event.event_date ? event.event_date : "").trim();
            return {
              visit_id: String(event && event.visit_id ? event.visit_id : "").trim(),
              event_date: eventDate,
              event_time: Number.isFinite(Date.parse(eventDate)) ? Date.parse(eventDate) : null,
              event_type: String(event && event.event_type ? event.event_type : "").trim(),
              diagnosis: String(event && event.diagnosis ? event.diagnosis : "").trim(),
              biosample_id: String(event && event.biosample_id ? event.biosample_id : "").trim(),
              domains: Array.isArray(event && event.domains) ? event.domains : [],
            };
          }),
        };
      })
      .filter((item) => item.patient_id)
      .sort((a, b) => {
        if (a.first_time !== null && b.first_time !== null && a.first_time !== b.first_time) {
          return a.first_time - b.first_time;
        }
        if (a.first_time !== null && b.first_time === null) return -1;
        if (a.first_time === null && b.first_time !== null) return 1;
        return a.patient_id.localeCompare(b.patient_id);
      });
  }

  function molecularTimelineCoverage() {
    const coverage = new Map();
    const datasets = Array.isArray(state.molecularDatasetsState) ? state.molecularDatasetsState : [];
    datasets.forEach((dataset) => {
      const datasetName = String(dataset && dataset.dataset_name ? dataset.dataset_name : "molecular dataset").trim();
      const sampleIds = Array.isArray(dataset && dataset.sample_ids) ? dataset.sample_ids : [];
      const patientIds = Array.isArray(dataset && dataset.patient_ids) ? dataset.patient_ids : [];
      const addSample = (patientId, sampleId) => {
        const normalizedPatientId = String(patientId || "").trim();
        if (!normalizedPatientId) return;
        const entry = coverage.get(normalizedPatientId) || { sampleIds: new Set(), datasetNames: new Set() };
        if (sampleId) entry.sampleIds.add(String(sampleId));
        entry.datasetNames.add(datasetName);
        coverage.set(normalizedPatientId, entry);
      };
      sampleIds.forEach((sampleId) => {
        const sampleText = String(sampleId || "").trim();
        const patientId = sampleText.includes(":") ? sampleText.split(":", 1)[0] : "";
        addSample(patientId, sampleText);
      });
      patientIds.forEach((patientId) => addSample(patientId, ""));
    });
    return coverage;
  }

  function molecularTimelineEvents(patientId, firstDate, lastDate, coverage) {
    if (!patientId || !coverage) return [];
    const sampleIds = Array.from(coverage.sampleIds || []);
    const datasetNames = Array.from(coverage.datasetNames || []);
    const eventDate = firstDate || lastDate || "";
    return [{
      visit_id: sampleIds.length ? `molecular:${sampleIds.slice(0, 2).join(",")}` : "molecular",
      event_date: eventDate,
      event_type: "molecular sample coverage",
      diagnosis: "",
      biosample_id: sampleIds.slice(0, 3).join(", "),
      domains: [{
        key: "molecular",
        label: "Molecular",
        count: sampleIds.length || datasetNames.length,
        examples: datasetNames.slice(0, 3),
      }],
    }];
  }

  function timelineDomainKeys(event) {
    return (Array.isArray(event && event.domains) ? event.domains : [])
      .map((domain) => String(domain && domain.key ? domain.key : "").trim())
      .filter(Boolean);
  }

  function selectedTimelineDomainSet() {
    if (!Array.isArray(state.dashboardTimelineDomains) || !state.dashboardTimelineDomains.length) {
      state.dashboardTimelineDomains = DASHBOARD_TIMELINE_DOMAINS.map((item) => item.key);
    }
    return new Set(state.dashboardTimelineDomains);
  }

  function eventPrimarySelectedDomain(event, selectedDomains) {
    const keys = new Set(timelineDomainKeys(event));
    return DASHBOARD_TIMELINE_DOMAINS.find((domain) => selectedDomains.has(domain.key) && keys.has(domain.key)) || null;
  }

  function eventHoverLabel(patientId, event, primaryDomain) {
    const domainParts = (Array.isArray(event.domains) ? event.domains : []).map((domain) => {
      const examples = Array.isArray(domain.examples) ? domain.examples.slice(0, 2).join(", ") : "";
      return `${domain.label || domain.key}${examples ? `: ${examples}` : ""}`;
    });
    return [
      `Patient: ${patientId}`,
      event.visit_id ? `Visit: ${event.visit_id}` : "",
      event.event_date ? `Date: ${event.event_date}` : "",
      primaryDomain && primaryDomain.label ? `Marker: ${primaryDomain.label}` : "",
      event.event_type ? `Type: ${event.event_type}` : "",
      event.diagnosis ? `Diagnosis: ${event.diagnosis}` : "",
      event.biosample_id ? `Biosample: ${event.biosample_id}` : "",
      domainParts.length ? `BFF terms: ${domainParts.join(" | ")}` : "",
    ].filter(Boolean).join("<br>");
  }

  function timelineEventRows(timelineItems, selectedDomains, selectedPatients) {
    const rows = [];
    timelineItems.forEach((item) => {
      item.events.forEach((event) => {
        const domainKeys = timelineDomainKeys(event);
        const matchingDomains = (Array.isArray(event.domains) ? event.domains : [])
          .filter((domain) => selectedDomains.has(String(domain && domain.key ? domain.key : "").trim()));
        if (!matchingDomains.length) return;
        rows.push({
          patient_id: item.patient_id,
          visit_id: event.visit_id || "",
          event_date: event.event_date || "",
          event_type: event.event_type || "",
          diagnosis: event.diagnosis || "",
          biosample_id: event.biosample_id || "",
          domains: matchingDomains,
          domain_keys: domainKeys,
          selected: selectedPatients.has(item.patient_id),
        });
      });
    });
    return rows.sort((a, b) => (
      String(a.patient_id).localeCompare(String(b.patient_id))
      || String(a.event_date).localeCompare(String(b.event_date))
      || String(a.visit_id).localeCompare(String(b.visit_id))
    ));
  }

  function timelineEventKey(row) {
    if (!row || typeof row !== "object") return "";
    return [
      row.patient_id,
      row.visit_id,
      row.event_date,
      row.event_type,
      row.biosample_id,
      (Array.isArray(row.domains) ? row.domains.map((domain) => domain.key || domain.label || "").join("+") : ""),
    ].map((item) => String(item || "").trim()).join("|");
  }

  function renderTimelineInspector(row) {
    if (!detailEl || !row) return;
    state.dashboardTimelineInspectedEventKey = timelineEventKey(row);
    const selected = timelineSelectedPatientSet().has(String(row.patient_id || ""));
    const domainCards = (Array.isArray(row.domains) ? row.domains : []).map((domain) => {
      const examples = Array.isArray(domain.examples) && domain.examples.length
        ? domain.examples.slice(0, 4).map((item) => `<span class="pill">${escapeHtml(String(item))}</span>`).join("")
        : '<span class="section-note">No examples captured for this domain.</span>';
      return `
        <div class="evidence-card">
          <strong>${escapeHtml(domain.label || domain.key || "Domain")}</strong>
          <div>${escapeHtml(String(domain.count || 0))} item${Number(domain.count || 0) === 1 ? "" : "s"}</div>
          <div>${examples}</div>
        </div>
      `;
    }).join("");
    detailEl.innerHTML = `
      <div class="workspace-card">
        <div class="dashboard-section-header">
          <div>
            <div class="dashboard-card-eyebrow">Timeline inspector</div>
            <h3>${escapeHtml(row.patient_id || "Patient")} ${row.visit_id ? `· ${escapeHtml(row.visit_id)}` : ""}</h3>
          </div>
          <span class="query-chip badge">${selected ? "Selected" : "Not selected"}</span>
        </div>
        <div class="molecular-stats">
          <span class="query-chip badge">Date: ${escapeHtml(row.event_date || "undated")}</span>
          ${row.event_type ? `<span class="query-chip badge">Type: ${escapeHtml(row.event_type)}</span>` : ""}
          ${row.diagnosis ? `<span class="query-chip badge">Diagnosis: ${escapeHtml(row.diagnosis)}</span>` : ""}
          ${row.biosample_id ? `<span class="query-chip badge">Sample: ${escapeHtml(row.biosample_id)}</span>` : ""}
        </div>
        <h3>Evidence at this timepoint</h3>
        <div class="evidence-grid">${domainCards || '<div class="empty">No domain evidence captured for this event.</div>'}</div>
      </div>
    `;
  }

  function renderTimelineEventTable(timelineItems, selectedDomains, selectedPatients, summary) {
    const tableEl = document.getElementById("dashboard-timeline-event-table");
    const searchEl = document.getElementById("dashboardTimelineEventSearch");
    const countEl = document.getElementById("dashboard-timeline-event-count");
    if (!tableEl) return;
    const query = String(searchEl && searchEl.value ? searchEl.value : "").trim().toLowerCase();
    const selectedOnly = selectedPatients.size > 0 && !query;
    const allRows = timelineEventRows(timelineItems, selectedDomains, selectedPatients);
    const scopedRows = allRows.filter((row) => {
      if (selectedOnly && !selectedPatients.has(row.patient_id)) return false;
      if (!query) return true;
      const haystack = [
        row.patient_id,
        row.visit_id,
        row.event_date,
        row.event_type,
        row.diagnosis,
        row.biosample_id,
        row.domains.map((domain) => `${domain.label || domain.key} ${(domain.examples || []).join(" ")}`).join(" "),
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    if (countEl) {
      countEl.textContent = query
        ? `${scopedRows.length} matching events across the timeline`
        : selectedOnly
        ? `${scopedRows.length} events for ${selectedPatients.size} selected patient${selectedPatients.size === 1 ? "" : "s"}`
        : `${scopedRows.length} visible events`;
    }
    if (!scopedRows.length) {
      tableEl.innerHTML = '<div class="empty">No events match the current timeline filters.</div>';
      return;
    }
    const rows = scopedRows.slice(0, 200);
    tableEl.innerHTML = `
      <table class="dashboard-timeline-table">
        <thead>
          <tr>
            <th>Inspect</th>
            <th>Patient</th>
            <th>Visit</th>
            <th>Date</th>
            <th>Domains</th>
            <th>Context</th>
            <th>Molecular sample</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row, index) => {
            const domainLabels = row.domains.map((domain) => {
              const meta = DASHBOARD_TIMELINE_DOMAINS.find((item) => item.key === domain.key) || {};
              return `<span class="dashboard-timeline-domain-pill" style="--timeline-domain-color:${escapeHtml(meta.color || "#64748b")}">${escapeHtml(domain.label || domain.key)}</span>`;
            }).join("");
            const context = [row.diagnosis, row.event_type].filter(Boolean).join(" | ") || "n/a";
            const isInspected = timelineEventKey(row) === String(state.dashboardTimelineInspectedEventKey || "");
            return `
              <tr class="${row.selected ? "is-selected" : ""}${isInspected ? " is-inspected" : ""}" data-dashboard-event-patient="${escapeHtml(row.patient_id)}">
                <td><button type="button" class="dashboard-timeline-inspect-btn${isInspected ? " is-active" : ""}" data-dashboard-event-inspect="${escapeHtml(String(index))}" title="Inspect this timepoint" aria-label="Inspect ${escapeHtml(row.patient_id)} ${escapeHtml(row.visit_id || "timepoint")}" aria-pressed="${isInspected ? "true" : "false"}">
                  ${isInspected
                    ? '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m5 12 4 4L19 6"></path></svg>'
                    : '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 5c5 0 9 5 9 7s-4 7-9 7-9-5-9-7 4-7 9-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>'}
                </button></td>
                <td><strong>${escapeHtml(row.patient_id)}</strong></td>
                <td>${escapeHtml(row.visit_id || "n/a")}</td>
                <td>${escapeHtml(row.event_date || "undated")}</td>
                <td><div class="dashboard-timeline-domain-pills">${domainLabels}</div></td>
                <td>${escapeHtml(context)}</td>
                <td>${escapeHtml(row.biosample_id || "")}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
      ${scopedRows.length > rows.length ? `<div class="section-note">Showing first ${rows.length} of ${scopedRows.length} matching events.</div>` : ""}
    `;
    tableEl.querySelectorAll("[data-dashboard-event-patient]").forEach((row) => {
      row.addEventListener("click", () => {
        toggleTimelinePatient(row.getAttribute("data-dashboard-event-patient"), summary);
      });
    });
    tableEl.querySelectorAll("[data-dashboard-event-inspect]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const index = Number.parseInt(button.getAttribute("data-dashboard-event-inspect") || "-1", 10);
        if (Number.isInteger(index) && rows[index]) {
          renderTimelineInspector(rows[index]);
          renderTimelineEventTable(timelineItems, selectedDomains, selectedPatients, summary);
        }
      });
    });
  }

  function renderDashboardTimeline(summary) {
    const timelineItems = normalizeTimelineItems(summary);
    const timelinePlotEl = document.getElementById("dashboard-plot-timeline");
    if (!timelinePlotEl) return;
    const scopedTimelineItems = timelineItems;
    if (!scopedTimelineItems.length) {
      timelinePlotEl.innerHTML = '<div class="empty">No patient timeline data available.</div>';
      return;
    }

    const visibleItems = scopedTimelineItems.slice(0, 40);
    const datedItems = visibleItems.filter((item) => item.has_dated_range);
    const activePatientId = String(state.selectedPatientId || "");
    const selectedPatientIds = timelineSelectedPatientIds();
    const selectedPatients = new Set(selectedPatientIds);
    const selectedDomains = selectedTimelineDomainSet();
    const presentDomainKeys = new Set();
    visibleItems.forEach((item) => {
      item.events.forEach((event) => {
        timelineDomainKeys(event).forEach((key) => presentDomainKeys.add(key));
      });
    });
    const controlsEl = document.getElementById("dashboard-timeline-controls");
    if (controlsEl) {
      controlsEl.innerHTML = DASHBOARD_TIMELINE_DOMAINS.map((domain) => {
        const disabled = !presentDomainKeys.has(domain.key);
        return `
          <label class="dashboard-timeline-domain${disabled ? " is-disabled" : ""}" style="--timeline-domain-color:${escapeHtml(domain.color)}">
            <input type="checkbox" value="${escapeHtml(domain.key)}"${selectedDomains.has(domain.key) ? " checked" : ""}${disabled ? " disabled" : ""}>
            <span class="dashboard-timeline-domain-dot"></span>
            <span>${escapeHtml(domain.label)}</span>
          </label>
        `;
      }).join("");
      controlsEl.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.addEventListener("change", () => {
          const selected = Array.from(controlsEl.querySelectorAll('input[type="checkbox"]:checked'))
            .map((item) => String(item.value || "").trim())
            .filter(Boolean);
          state.dashboardTimelineDomains = selected.length ? selected : DASHBOARD_TIMELINE_DOMAINS.map((item) => item.key);
          renderDashboardTimeline(summary);
        });
      });
    }
    const overflowNoteEl = document.getElementById("dashboard-timeline-overflow-note");
    if (overflowNoteEl) {
      overflowNoteEl.textContent = scopedTimelineItems.length > visibleItems.length
        ? `Showing first ${visibleItems.length} of ${scopedTimelineItems.length} patients. Use the patient roster search to narrow the workspace.`
        : "";
    }
    const statusEl = document.getElementById("dashboard-timeline-selection-status");
    if (statusEl) {
      statusEl.textContent = selectedPatientIds.length
        ? `${selectedPatientIds.length} patient${selectedPatientIds.length === 1 ? "" : "s"} selected from the timeline.`
        : "Click timeline bars or event markers to build a patient selection.";
    }
    const useAnalysisBtn = document.getElementById("dashboardTimelineUseAnalysisBtn");
    const saveBtn = document.getElementById("dashboardTimelineSaveCohortBtn");
    const clearBtn = document.getElementById("dashboardTimelineClearSelectionBtn");
    [useAnalysisBtn, saveBtn, clearBtn].forEach((button) => {
      if (button) button.disabled = !selectedPatientIds.length;
    });
    if (useAnalysisBtn) {
      useAnalysisBtn.addEventListener("click", sendTimelineSelectionToAnalysis);
    }
    if (saveBtn) {
      saveBtn.addEventListener("click", () => {
        void saveTimelineSelection();
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        setTimelineSelectedPatientIds([]);
        renderDashboardTimeline(summary);
      });
    }
    const eventSearchEl = document.getElementById("dashboardTimelineEventSearch");
    if (eventSearchEl) {
      eventSearchEl.addEventListener("input", () => {
        renderTimelineEventTable(visibleItems, selectedDomains, selectedPatients, summary);
      });
    }

    if (!datedItems.length) {
      timelinePlotEl.innerHTML = '<div class="empty">No dated patient ranges available.</div>';
      renderTimelineEventTable(visibleItems, selectedDomains, selectedPatients, summary);
      return;
    }
    renderTimelineEventTable(visibleItems, selectedDomains, selectedPatients, summary);

    const oneDayMs = 24 * 60 * 60 * 1000;
    const yLabels = datedItems.map((item) => item.patient_id);
    const durations = datedItems.map((item) => Math.max(((item.last_time || item.first_time) - item.first_time) / oneDayMs, 1));
    const eventPoints = [];
    datedItems.forEach((item) => {
      item.events.forEach((event) => {
        if (event.event_time === null) return;
        const primaryDomain = eventPrimarySelectedDomain(event, selectedDomains);
        if (!primaryDomain) return;
        eventPoints.push({
          patient_id: item.patient_id,
          visit_id: event.visit_id,
          event_date: event.event_date,
          domain: primaryDomain,
          selected: selectedPatients.has(item.patient_id),
          hover: eventHoverLabel(item.patient_id, event, primaryDomain),
        });
      });
    });
    const eventTraces = DASHBOARD_TIMELINE_DOMAINS.map((domain) => {
      const domainPoints = eventPoints.filter((point) => point.domain.key === domain.key);
      if (!domainPoints.length) return null;
      return {
        type: "scatter",
        mode: "markers",
        name: domain.label,
        x: domainPoints.map((point) => point.event_date),
        y: domainPoints.map((point) => point.patient_id),
        customdata: domainPoints.map((point) => [point.patient_id, point.visit_id]),
        text: domainPoints.map((point) => point.hover),
        marker: {
          color: domain.color,
          symbol: domain.symbol,
          size: domainPoints.map((point) => point.selected ? 14 : 10),
          line: {
            color: domainPoints.map((point) => point.selected ? "#0f172a" : "#ffffff"),
            width: domainPoints.map((point) => point.selected ? 2.5 : 1.5),
          },
        },
        hovertemplate: "%{text}<extra></extra>",
      };
    }).filter(Boolean);
    mountPlot(
      "dashboard-plot-timeline",
      [
        {
          type: "bar",
          orientation: "h",
          name: "Patient span",
          y: yLabels,
          x: durations,
          base: datedItems.map((item) => item.first_event_date),
          customdata: datedItems.map((item) => item.patient_id),
          marker: {
            color: datedItems.map((item) => selectedPatients.has(item.patient_id) ? "#1d4ed8" : (item.patient_id === activePatientId ? "#60a5fa" : "#bae6fd")),
            line: {
              color: datedItems.map((item) => selectedPatients.has(item.patient_id) ? "#0f172a" : (item.patient_id === activePatientId ? "#1d4ed8" : "#38bdf8")),
              width: datedItems.map((item) => selectedPatients.has(item.patient_id) || item.patient_id === activePatientId ? 2 : 1),
            },
          },
          hovertemplate: "Patient: %{customdata}<br>Start: %{base}<br>Duration: %{x:.0f} days<br>Click to select/unselect<extra></extra>",
        },
        ...eventTraces,
      ],
      dashboardPlotLayout({
        height: Math.max(260, Math.min(560, datedItems.length * 24 + 80)),
        margin: { t: 12, r: 20, b: 42, l: 110 },
        xaxis: {
          ...dashboardPlotLayout().xaxis,
          type: "date",
          title: { text: "Clinical time", font: { color: "#61758c", size: 12 } },
        },
        yaxis: {
          ...dashboardPlotLayout().yaxis,
          automargin: true,
          autorange: "reversed",
        },
        clickmode: "event+select",
        dragmode: "lasso",
        showlegend: Boolean(eventTraces.length),
        legend: {
          orientation: "h",
          yanchor: "bottom",
          y: 1.02,
          xanchor: "left",
          x: 0,
        },
      }),
      (el) => {
        if (el && typeof el.on === "function") {
          el.on("plotly_click", (event) => {
            const point = event && Array.isArray(event.points) ? event.points[0] : null;
            const patientId = patientIdFromTimelinePoint(point);
            toggleTimelinePatient(patientId, summary);
          });
          el.on("plotly_selected", (event) => {
            setTimelineSelectionFromPoints(event && event.points, summary);
          });
          el.on("plotly_deselect", () => {
            setTimelineSelectedPatientIds([]);
            renderDashboardTimeline(summary);
          });
        }
      },
      {
        displayModeBar: true,
        modeBarButtonsToAdd: ["select2d", "lasso2d"],
        modeBarButtonsToRemove: ["zoom2d", "pan2d", "autoScale2d"],
      }
    );
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
    const timelineSelected = state.currentDashboardSubtab === "timeline" && timelineSelectedPatientSet().has(String(patient.patient_id || ""));
    const activeClass = state.selectedPatientId === patient.patient_id || timelineSelected ? "active" : "";
    const datasetNames = Array.isArray(patient.dataset_names) ? patient.dataset_names : [];
    const datasetBadge = isMultiDatasetWorkspace() && datasetNames.length
      ? `<span class="pill">${escapeHtml(datasetNames.join(", "))}</span>`
      : "";
    const selectionBadge = timelineSelected ? '<span class="pill">selected</span>' : "";
    const compactTimeline = state.currentDashboardSubtab === "timeline";
    if (compactTimeline) {
      return `
        <div class="patient-card patient-card-compact ${activeClass}" data-patient-id="${patient.patient_id}">
          <div class="patient-card-compact-main">
            <strong>${patient.patient_id}</strong>
            ${selectionBadge}
          </div>
          <div class="patient-card-compact-meta">
            <span>${escapeHtml(String(patient.visit_count || 0))} visits</span>
            <span>${escapeHtml(patient.sex || "sex n/a")}</span>
            <span>${escapeHtml(String(patient.evidence.diseases.count || 0))} dx</span>
          </div>
        </div>
      `;
    }
    return `
      <div class="patient-card ${activeClass}" data-patient-id="${patient.patient_id}">
        <strong>${patient.patient_id}</strong>
        <div>
          ${selectionBadge}
          ${datasetBadge}
          <span class="pill">${patient.visit_count} visits</span>
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
    patientsEl.innerHTML = summary + visibleItems.map(summaryCard).join("");
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
          ${datasetLine}
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

  function renderDashboard(summary) {
    state.dashboardSummary = summary;
    const expanded = Boolean(state.dashboardClinicalExpanded);
    const totals = summary && summary.totals ? summary.totals : {};
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
            <h4>Visits per patient</h4>
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
    const timelineMarkup = `
      <section class="section-card dashboard-timeline-card">
        <div class="section-card-header">
          <div class="section-card-eyebrow">Longitudinal coverage</div>
          <h3>Patient timeline</h3>
        </div>
        <div class="section-note">Click timeline bars or event markers to toggle one patient, or drag with the lasso/select tool to select several patients. Event markers are colored by BFF domain, including molecular sample coverage when present.</div>
        <div id="dashboard-timeline-controls" class="dashboard-timeline-controls"></div>
        <div class="dashboard-timeline-actions">
          <div id="dashboard-timeline-selection-status" class="section-note">Click timeline bars or event markers to build a patient selection.</div>
          <div class="dashboard-timeline-action-buttons">
            <button id="dashboardTimelineUseAnalysisBtn" type="button" class="query-chip action" disabled>Open in Analysis</button>
            <button id="dashboardTimelineSaveCohortBtn" type="button" class="query-chip query-chip-deterministic" disabled>Save cohort</button>
            <button id="dashboardTimelineClearSelectionBtn" type="button" class="query-chip" disabled>Clear</button>
          </div>
        </div>
        <div class="dashboard-plot-frame dashboard-timeline-plot" id="dashboard-plot-timeline"></div>
        <div id="dashboard-timeline-overflow-note" class="section-note"></div>
        <div class="dashboard-timeline-event-card">
          <div class="dashboard-timeline-event-header">
            <div>
              <h4>Selection table</h4>
              <div id="dashboard-timeline-event-count" class="section-note">Filter by patient, visit, domain, diagnosis, event type, or sample.</div>
            </div>
            <input id="dashboardTimelineEventSearch" class="patient-search dashboard-timeline-event-search" aria-label="Search all timeline fields" placeholder="Search all fields">
          </div>
          <div id="dashboard-timeline-event-table" class="dashboard-timeline-table-wrap"></div>
        </div>
      </section>
    `;

    dashboardEl.innerHTML = `
      <section class="section-card dashboard-hero">
        <h2>Clinical dashboard</h2>
        <p>Key workspace metrics and quick patterns before drilling into one patient.</p>
        <div class="molecular-kpi-grid">
          <div class="molecular-kpi"><span class="molecular-kpi-label">Patients</span><strong class="molecular-kpi-value">${escapeHtml(formatNumber(totals.patients || summary.patients || 0))}</strong></div>
          <div class="molecular-kpi"><span class="molecular-kpi-label">Timepoints</span><strong class="molecular-kpi-value">${escapeHtml(formatNumber(totals.visits || summary.visits || 0))}</strong></div>
          <div class="molecular-kpi"><span class="molecular-kpi-label">Avg visits / patient</span><strong class="molecular-kpi-value">${escapeHtml(String(totals.avg_visits_per_patient || 0))}</strong></div>
          <div class="molecular-kpi"><span class="molecular-kpi-label">Source files</span><strong class="molecular-kpi-value">${escapeHtml(formatNumber(totals.source_files || 0))}</strong></div>
        </div>
      </section>
      ${overviewMarkup}
    `;
    if (dashboardTimelineEl) {
      dashboardTimelineEl.innerHTML = timelineMarkup;
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
    const compareMode = Boolean(analysisCompareModeEl && analysisCompareModeEl.checked);
    analysisSelectedPatientIdsEl.disabled = compareMode || Boolean(selectedCohort);
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
    renderMolecularDatasetSelector();
    renderMolecularDashboardCards(state.molecularDatasetsState);
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
      renderMolecularDatasetSelector();
      renderMolecularDashboardCards(state.molecularDatasetsState);
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
    renderMolecularDatasetSelector();
    renderMolecularDashboardCards(state.molecularDatasetsState);
    if (typeof renderAnalysisCatalog === "function") {
      renderAnalysisCatalog();
    }
    renderGlobalContext();
    syncCurrentAnalysisSessionFromUi({ render: true });
  }

  function renderMolecularScopeCard(scope) {
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
      <div class="molecular-scope-card">
        <h4>${escapeHtml(scope.label || "Scope")}</h4>
        <div class="molecular-stats">
          <span class="query-chip badge">Samples: ${escapeHtml(String(scope.sample_count || 0))}</span>
          <span class="query-chip badge">Patients: ${escapeHtml(String(scope.patient_count || 0))}</span>
          <span class="query-chip badge">Mean: ${escapeHtml(mean)}</span>
          <span class="query-chip badge">Median: ${escapeHtml(median)}</span>
          <span class="query-chip badge">Range: ${escapeHtml(min)} to ${escapeHtml(max)}</span>
        </div>
        ${values.length ? `
          <div class="molecular-table-wrap">
            <table class="molecular-table">
              <thead><tr><th>Patient</th><th>Sample</th><th>Raw count</th></tr></thead>
              <tbody>${preview}</tbody>
            </table>
          </div>
          ${more}
        ` : '<div class="empty">No molecular samples matched this scope for the selected gene.</div>'}
      </div>
    `;
  }

  function renderMolecularExpressionResult(payload) {
    if (!analysisMolecularResultEl) return;
    if (!payload) {
      analysisMolecularResultEl.className = "molecular-result empty";
      analysisMolecularResultEl.textContent = "No molecular expression summary yet.";
      return;
    }
    const payloads = Array.isArray(payload) ? payload : [payload];
    if (!payloads.length) {
      analysisMolecularResultEl.className = "molecular-result empty";
      analysisMolecularResultEl.textContent = "No molecular expression summary yet.";
      return;
    }
    analysisMolecularResultEl.className = "molecular-result";
    analysisMolecularResultEl.innerHTML = payloads.map((item) => {
      const sections = [renderMolecularScopeCard(item.scope_a)];
      if (item.scope_b) sections.push(renderMolecularScopeCard(item.scope_b));
      const geneTooltip = [
        String(item.gene_id || "").trim(),
        String(item.gene_symbol || "").trim(),
        String(item.gene_name || "").trim(),
      ].filter(Boolean).join(" • ");
      const geneMarkup = item.ensembl_url
        ? `<a class="molecular-result-gene-link" href="${escapeHtml(item.ensembl_url)}" target="_blank" rel="noopener" title="${escapeHtml(geneTooltip || String(item.gene_id || ""))}">${escapeHtml(item.gene_id)}</a>`
        : `<span title="${escapeHtml(geneTooltip || String(item.gene_id || ""))}">${escapeHtml(item.gene_id)}</span>`;
      return `
        <div class="molecular-expression-card">
          <div class="molecular-result-header">
            <strong>${geneMarkup}</strong>
            ${item.gene_symbol && item.gene_symbol !== item.gene_id ? `<span class="query-chip badge">${escapeHtml(item.gene_symbol)}</span>` : ""}
            <span class="query-chip badge">${escapeHtml(item.dataset_name)}</span>
          </div>
          <div class="molecular-result-grid">${sections.join("")}</div>
        </div>
      `;
    }).join("");
  }

  function selectedMolecularDatasetNames() {
    return state.selectedMolecularDatasets.slice();
  }

  function molecularDatasetListElements() {
    return [analysisMolecularDatasetListEl, analysisCatalogMolecularDatasetListEl].filter(Boolean);
  }

  function currentAnalysisCatalogItem() {
    return Array.isArray(state.analysisCatalogItems)
      ? state.analysisCatalogItems.find((item) => String(item && item.id ? item.id : "") === String(state.analysisSelectedCatalogItemId || ""))
      : null;
  }

  function requiresSingleSelectedMolecularDataset(item) {
    const itemId = String(item && item.id ? item.id : "").trim();
    return itemId === "molecular-differential-expression"
      || itemId === "molecular-deseq2-differential-expression"
      || itemId === "molecular-hallmark-pathway-enrichment"
      || itemId === "molecular-signature-workflow";
  }

  function contextualMolecularDatasets() {
    const item = currentAnalysisCatalogItem();
    if (!item || !item.requires_molecular) {
      return [];
    }
    const compareRequired = Boolean(item.default_compare_mode);
    const compatibleDatasets = state.molecularDatasetsState.filter((dataset) => {
      const patientIds = Array.isArray(dataset && dataset.patient_ids) ? dataset.patient_ids : [];
      if (!patientIds.length) {
        return true;
      }
      const overlap = currentMolecularScopeOverlap(patientIds);
      if (compareRequired) {
        return overlap.overlapA > 0 && overlap.overlapB > 0;
      }
      if (overlap.scopeASize || overlap.scopeBSize) {
        return overlap.overlapA > 0 || overlap.overlapB > 0;
      }
      return true;
    });
    const compatibleNames = new Set(compatibleDatasets.map((dataset) => dataset.dataset_name));
    const filteredSelected = state.selectedMolecularDatasets.filter((name) => compatibleNames.has(name));
    if (filteredSelected.length !== state.selectedMolecularDatasets.length) {
      state.selectedMolecularDatasets = filteredSelected;
    }
    if (
      requiresSingleSelectedMolecularDataset(item)
      && compatibleDatasets.length === 1
      && (
        state.selectedMolecularDatasets.length !== 1
        || state.selectedMolecularDatasets[0] !== compatibleDatasets[0].dataset_name
      )
    ) {
      state.selectedMolecularDatasets = [compatibleDatasets[0].dataset_name];
    }
    return compatibleDatasets;
  }

  function renderMolecularDatasetSelector() {
    const item = currentAnalysisCatalogItem();
    const contextRequiresMolecular = Boolean(item && item.requires_molecular);
    const mainListEl = analysisMolecularDatasetListEl;
    const contextualListEl = analysisCatalogMolecularDatasetListEl;
    if (!mainListEl && !contextualListEl) return;
    if (!state.molecularDatasetsState.length) {
      if (mainListEl) mainListEl.innerHTML = '<div class="empty">No molecular dataset loaded</div>';
      if (contextualListEl) contextualListEl.innerHTML = '<div class="empty">No molecular dataset loaded</div>';
      return;
    }
    const selected = new Set(state.selectedMolecularDatasets);
    const renderOption = (dataset, options = {}) => {
      const overlap = currentMolecularScopeOverlap(dataset.patient_ids);
      const small = options.includeOverlap
        ? `${escapeHtml(String(dataset.sample_count || 0))} samples, ${escapeHtml(String(dataset.gene_count || 0))} genes • A overlap ${escapeHtml(String(overlap.overlapA))}${analysisCompareModeEl && analysisCompareModeEl.checked ? ` • B overlap ${escapeHtml(String(overlap.overlapB))}` : ""}`
        : `${escapeHtml(String(dataset.sample_count || 0))} samples, ${escapeHtml(String(dataset.gene_count || 0))} genes`;
      return `
      <label class="molecular-dataset-option">
        <input type="checkbox" value="${escapeHtml(dataset.dataset_name)}"${selected.has(dataset.dataset_name) ? " checked" : ""}>
        <span>
          <strong>${escapeHtml(dataset.dataset_name)}</strong>
          <small>${small}</small>
        </span>
      </label>
    `;
    };
    if (mainListEl) {
      mainListEl.innerHTML = state.molecularDatasetsState.map((dataset) => renderOption(dataset)).join("");
    }
    if (contextualListEl) {
      if (!contextRequiresMolecular) {
        contextualListEl.innerHTML = '<div class="empty">Choose a molecular analysis to select a compatible dataset.</div>';
        return;
      }
      const availableDatasets = contextualMolecularDatasets();
      if (!availableDatasets.length) {
        contextualListEl.innerHTML = '<div class="empty">No molecular datasets are available in this workspace.</div>';
        return;
      }
      contextualListEl.innerHTML = availableDatasets.map((dataset) => renderOption(dataset, { includeOverlap: true })).join("");
    }
  }

  function syncSelectedMolecularDatasets() {
    const available = new Set(state.molecularDatasetsState.map((item) => item.dataset_name));
    state.selectedMolecularDatasets = state.selectedMolecularDatasets.filter((item) => available.has(item));
    renderMolecularDatasetSelector();
  }

  function clearMolecularWorkspaceSelection() {
    state.selectedMolecularDatasets = [];
    if (analysisMolecularGeneEl) {
      analysisMolecularGeneEl.value = "";
    }
    renderMolecularExpressionResult(null);
  }

  function molecularDatasetOverlap(datasetName) {
    const normalizedName = String(datasetName || "").trim();
    if (!normalizedName) return null;
    const dataset = state.molecularDatasetsState.find((item) => String(item && item.dataset_name ? item.dataset_name : "").trim() === normalizedName);
    if (!dataset) return null;
    return currentMolecularScopeOverlap(dataset.patient_ids);
  }

  function currentMolecularScopeOverlap(patientIds) {
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

  function renderMolecularDashboardCards(datasets) {
    if (!molecularDashboardCardsEl) return;
    if (!Array.isArray(datasets) || !datasets.length) {
      molecularDashboardCardsEl.innerHTML = '<div class="empty">No molecular datasets loaded.</div>';
      return;
    }
    const formatMolecularModality = (value) => {
      const text = String(value || "molecular").trim();
      if (!text) return "Molecular";
      return text.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
    };
    const workspaceSummary = datasets.reduce((summary, item) => {
      summary.datasetCount += 1;
      summary.sampleCount += Number(item.sample_count || 0);
      summary.patientCount += Number(item.patient_count || 0);
      summary.geneCount = Math.max(summary.geneCount, Number(item.gene_count || 0));
      return summary;
    }, {
      datasetCount: 0,
      sampleCount: 0,
      patientCount: 0,
      geneCount: 0,
    });
    molecularDashboardCardsEl.innerHTML = `
      <section class="molecular-workspace-summary">
        <div class="molecular-workspace-summary-copy">
          <strong class="molecular-workspace-summary-title">Molecular workspace</strong>
        </div>
        <div class="molecular-workspace-kpis">
          <div class="molecular-kpi molecular-kpi-compact"><span class="molecular-kpi-label">Datasets</span><strong class="molecular-kpi-value">${escapeHtml(String(workspaceSummary.datasetCount))}</strong></div>
          <div class="molecular-kpi molecular-kpi-compact"><span class="molecular-kpi-label">Samples</span><strong class="molecular-kpi-value">${escapeHtml(String(workspaceSummary.sampleCount))}</strong></div>
          <div class="molecular-kpi molecular-kpi-compact"><span class="molecular-kpi-label">Patients</span><strong class="molecular-kpi-value">${escapeHtml(String(workspaceSummary.patientCount))}</strong></div>
          <div class="molecular-kpi molecular-kpi-compact"><span class="molecular-kpi-label">Max genes / dataset</span><strong class="molecular-kpi-value">${escapeHtml(String(workspaceSummary.geneCount))}</strong></div>
        </div>
      </section>
      ${datasets.map((item) => {
      const overlap = currentMolecularScopeOverlap(item.patient_ids);
      const topGenes = Array.isArray(item.top_genes) ? item.top_genes : [];
      const topGenesMarkup = topGenes.length
        ? topGenes.map((gene) => {
          const title = [
            String(gene.gene_id || "").trim(),
            String(gene.gene_symbol || "").trim(),
            String(gene.gene_name || "").trim(),
            `Total raw count: ${String(gene.total_raw_count || 0)}`,
          ].filter(Boolean).join(" • ");
          if (gene.ensembl_url) {
            return `<a class="molecular-gene-pill molecular-gene-pill-link" href="${escapeHtml(String(gene.ensembl_url || ""))}" target="_blank" rel="noopener" title="${escapeHtml(title)}">${escapeHtml(gene.gene_id)}</a>`;
          }
          return `<span class="molecular-gene-pill" title="${escapeHtml(title)}">${escapeHtml(gene.gene_id)}</span>`;
        }).join("")
        : '<span class="section-note">No top-gene summary available.</span>';
      const overlapMarkup = overlap.scopeASize || overlap.scopeBSize
        ? `
          <div class="molecular-card-section">
            <strong>Current Analysis scope</strong>
            <div class="molecular-stats">
              <span class="query-chip badge">A overlap: ${escapeHtml(String(overlap.overlapA))} / ${escapeHtml(String(overlap.scopeASize || item.clinical_overlap_patient_count || 0))}</span>
              ${analysisCompareModeEl && analysisCompareModeEl.checked ? `<span class="query-chip badge">B overlap: ${escapeHtml(String(overlap.overlapB))} / ${escapeHtml(String(overlap.scopeBSize || item.clinical_overlap_patient_count || 0))}</span>` : ""}
            </div>
          </div>
        `
        : "";
      return `
        <article class="molecular-dashboard-card">
          <div class="molecular-card-header">
            <div>
              <div class="molecular-card-eyebrow">Loaded dataset</div>
              <strong class="molecular-card-title">${escapeHtml(item.dataset_name)}</strong>
            </div>
            <span class="query-chip badge molecular-modality-badge">${escapeHtml(formatMolecularModality(item.modality))}</span>
          </div>
          <div class="molecular-card-meta">
            <span class="dataset-picker-tag">${escapeHtml(item.dataset_name)}</span>
            <span class="dataset-picker-tag">${escapeHtml(formatMolecularModality(item.modality))}</span>
          </div>
          <div class="molecular-kpi-grid">
            <div class="molecular-kpi"><span class="molecular-kpi-label">Samples</span><strong class="molecular-kpi-value">${escapeHtml(String(item.sample_count || 0))}</strong></div>
            <div class="molecular-kpi"><span class="molecular-kpi-label">Patients</span><strong class="molecular-kpi-value">${escapeHtml(String(item.patient_count || 0))}</strong></div>
            <div class="molecular-kpi"><span class="molecular-kpi-label">Genes</span><strong class="molecular-kpi-value">${escapeHtml(String(item.gene_count || 0))}</strong></div>
            <div class="molecular-kpi"><span class="molecular-kpi-label">Clinical overlap</span><strong class="molecular-kpi-value">${escapeHtml(String(item.clinical_overlap_patient_count || 0))}</strong></div>
          </div>
          <div class="molecular-card-section">
            <strong>Sample-level summary</strong>
            <div class="molecular-summary-grid">
              <div class="molecular-summary-item"><span>Total counts / sample</span><strong>${escapeHtml(Number(item.mean_total_counts_per_sample || 0).toFixed(1))}</strong></div>
              <div class="molecular-summary-item"><span>Detected genes / sample</span><strong>${escapeHtml(Number(item.mean_detected_genes_per_sample || 0).toFixed(1))}</strong></div>
            </div>
          </div>
          ${overlapMarkup}
          <div class="molecular-card-section">
            <strong>Top abundant genes</strong>
            <div class="molecular-gene-list">${topGenesMarkup}</div>
          </div>
        </article>
      `;
    }).join("")}`;
  }

  async function loadMolecularGeneSuggestions() {
    if (!analysisMolecularGenesEl) return;
    const datasetNames = selectedMolecularDatasetNames();
    if (!datasetNames.length) {
      analysisMolecularGenesEl.innerHTML = "";
      return;
    }
    const query = encodeURIComponent(String(analysisMolecularGeneEl && analysisMolecularGeneEl.value ? analysisMolecularGeneEl.value.trim() : ""));
    const dataDir = encodeURIComponent((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim());
    try {
      const payloads = await Promise.all(datasetNames.map(async (datasetName) => {
        const dataset = encodeURIComponent(datasetName);
        const response = await fetch(`/molecular/genes?data_dir=${dataDir}&dataset_name=${dataset}&q=${query}&limit=50`);
        if (!response.ok) throw new Error("Unable to load molecular genes.");
        return response.json();
      }));
      const genes = Array.from(new Set(payloads.flatMap((payload) => Array.isArray(payload.genes) ? payload.genes : []))).sort();
      const annotations = payloads.reduce((acc, payload) => {
        const current = payload && payload.annotations && typeof payload.annotations === "object" ? payload.annotations : {};
        return { ...acc, ...current };
      }, {});
      analysisMolecularGenesEl.innerHTML = genes.map((geneId) => {
        const annotation = annotations[geneId] && typeof annotations[geneId] === "object" ? annotations[geneId] : {};
        const geneSymbol = String(annotation.gene_symbol || "").trim();
        const geneName = String(annotation.gene_name || "").trim();
        const title = [geneId, geneSymbol, geneName].filter(Boolean).join(" • ");
        const label = geneSymbol ? `${geneSymbol} · ${geneId}` : geneId;
        return `<option value="${escapeHtml(geneId)}" label="${escapeHtml(label)}" title="${escapeHtml(title || geneId)}"></option>`;
      }).join("");
    } catch (_error) {
      analysisMolecularGenesEl.innerHTML = "";
    }
  }

  async function loadMolecularDatasets(options = {}) {
    if (!analysisMolecularStatusEl || !molecularDashboardStatusEl) return;
    const scopeId = String(options.scopeId || ((dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim()) || "").trim();
    const previousScopeId = String(state.molecularDatasetsScopeId || "").trim();
    const scopeChanged = previousScopeId !== scopeId;
    state.molecularDatasetsScopeId = scopeId;
    if (scopeChanged) {
      clearMolecularWorkspaceSelection();
    }
    const dataDir = encodeURIComponent(scopeId);
    analysisMolecularStatusEl.className = "query-status loading";
    analysisMolecularStatusEl.textContent = "Checking molecular datasets...";
    if (analysisCatalogMolecularStatusEl) {
      analysisCatalogMolecularStatusEl.textContent = "Checking molecular datasets...";
    }
    molecularDashboardStatusEl.className = "query-status loading";
    molecularDashboardStatusEl.textContent = "Checking molecular datasets...";
    try {
      const payload = options.prefetched && typeof options.prefetched === "object"
        ? options.prefetched
        : await (async () => {
          const response = await fetch(`/molecular/datasets?data_dir=${dataDir}`);
          if (!response.ok) throw new Error("Unable to load molecular datasets.");
          return response.json();
        })();
      const datasets = Array.isArray(payload.datasets) ? payload.datasets : [];
      state.molecularDatasetsState = datasets;
      syncSelectedMolecularDatasets();
      renderMolecularDashboardCards(state.molecularDatasetsState);
      if (typeof renderAnalysisCatalogMolecularPanel === "function") {
        renderAnalysisCatalogMolecularPanel();
      }
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
      if (!datasets.length) {
        analysisMolecularStatusEl.className = "query-status";
        analysisMolecularStatusEl.textContent = "No molecular datasets are currently available for quick expression checks.";
        if (analysisCatalogMolecularStatusEl) {
          analysisCatalogMolecularStatusEl.textContent = "No molecular datasets are currently available in this workspace.";
        }
        molecularDashboardStatusEl.className = "query-status";
        molecularDashboardStatusEl.textContent = "No molecular datasets are currently available.";
        renderMolecularExpressionResult(null);
        return;
      }
      analysisMolecularStatusEl.className = "query-status";
      analysisMolecularStatusEl.textContent = `Loaded ${datasets.length} molecular dataset${datasets.length === 1 ? "" : "s"} for quick expression checks.`;
      if (analysisCatalogMolecularStatusEl) {
        analysisCatalogMolecularStatusEl.textContent = datasets.length === 1
          ? `1 molecular dataset available for Analysis.`
          : `${datasets.length} molecular datasets available. Some molecular tools require exactly one selected dataset.`;
      }
      molecularDashboardStatusEl.className = "query-status";
      molecularDashboardStatusEl.textContent = `Loaded ${datasets.length} molecular dataset${datasets.length === 1 ? "" : "s"}.`;
      await loadMolecularGeneSuggestions();
    } catch (error) {
      analysisMolecularStatusEl.className = "query-status";
      analysisMolecularStatusEl.textContent = error && error.message ? error.message : "Unable to load molecular datasets.";
      if (analysisCatalogMolecularStatusEl) {
        analysisCatalogMolecularStatusEl.textContent = error && error.message ? error.message : "Unable to load molecular datasets.";
      }
      molecularDashboardStatusEl.className = "query-status";
      molecularDashboardStatusEl.textContent = error && error.message ? error.message : "Unable to load molecular datasets.";
      state.molecularDatasetsState = [];
      clearMolecularWorkspaceSelection();
      renderMolecularDatasetSelector();
      renderMolecularDashboardCards(state.molecularDatasetsState);
      if (typeof renderAnalysisCatalogMolecularPanel === "function") {
        renderAnalysisCatalogMolecularPanel();
      }
      if (typeof renderAnalysisCatalog === "function") {
        renderAnalysisCatalog();
      }
    }
  }

  async function runMolecularExpressionAnalysis() {
    if (!analysisMolecularGeneEl || !analysisMolecularStatusEl) return;
    const datasetNames = selectedMolecularDatasetNames();
    const geneId = String(analysisMolecularGeneEl.value || "").trim();
    if (!datasetNames.length || !geneId) {
      analysisMolecularStatusEl.className = "query-status";
      analysisMolecularStatusEl.textContent = "Choose at least one molecular dataset and a gene ID first.";
      return;
    }
    analysisMolecularStatusEl.className = "query-status loading";
    analysisMolecularStatusEl.textContent = "Fetching molecular expression summary...";
    try {
      const selectedCohortA = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
        : null;
      const selectedCohortB = Array.isArray(state.savedCohorts)
        ? state.savedCohorts.find((item) => item.id === state.analysisCompareSavedCohortId)
        : null;
      const payloads = await Promise.all(datasetNames.map(async (datasetName) => {
        const response = await fetch("/molecular/expression", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_dir: (dataDirEl.dataset && dataDirEl.dataset.scopeId) ? dataDirEl.dataset.scopeId : dataDirEl.value.trim(),
            dataset_name: datasetName,
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
        if (!response.ok) throw new Error("Unable to fetch molecular expression.");
        return response.json();
      }));
      renderMolecularExpressionResult(payloads);
      analysisMolecularStatusEl.className = "query-status";
      analysisMolecularStatusEl.textContent = `Expression summary ready for ${geneId} across ${datasetNames.length} dataset${datasetNames.length === 1 ? "" : "s"}.`;
    } catch (error) {
      renderMolecularExpressionResult(null);
      analysisMolecularStatusEl.className = "query-status";
      analysisMolecularStatusEl.textContent = error && error.message ? error.message : "Unable to fetch molecular expression.";
    }
  }

  function handleMolecularDatasetSelectionChange(sourceEl = null, changedInput = null) {
    const listEl = sourceEl || analysisMolecularDatasetListEl || analysisCatalogMolecularDatasetListEl;
    if (!listEl) return;
    let selected = Array.from(listEl.querySelectorAll('input[type="checkbox"]:checked'))
      .map((item) => item.value)
      .filter(Boolean);
    const item = currentAnalysisCatalogItem();
    if (requiresSingleSelectedMolecularDataset(item) && selected.length > 1) {
      const changedValue = changedInput && changedInput.checked ? String(changedInput.value || "").trim() : "";
      selected = changedValue ? [changedValue] : selected.slice(-1);
    }
    state.selectedMolecularDatasets = selected;
    renderMolecularDatasetSelector();
    void loadMolecularGeneSuggestions();
  }

  function handleMolecularGeneInput() {
    void loadMolecularGeneSuggestions();
  }

  return {
    renderPatientList,
    renderDetail,
    renderDashboard,
    renderAnalysisScopeSummary,
    renderAnalysisCompareScopeSummary,
    renderMolecularDatasetSelector,
    renderMolecularExpressionResult,
    renderMolecularDashboardCards,
    loadMolecularDatasets,
    runMolecularExpressionAnalysis,
    handleMolecularDatasetSelectionChange,
    handleMolecularGeneInput,
    molecularDatasetOverlap,
    toggleTimelinePatientSelection,
  };
}
