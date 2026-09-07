// Timeline rendering, event inspection and whole-patient selection.
// State remains owned by the workspace; Dashboard supplies shared presentation helpers.
export function createTimelineUi({ state, refs, helpers, callbacks }) {
  const { detailEl } = refs;
  const { escapeHtml, clinicalRepresentation, normalizedClarid,
    claridIdentityMarkup, dashboardPlotLayout, mountPlot } = helpers;
  const { refreshPatientList, saveIdsAsCohort, sendPatientIdsToAnalysis, handleClaridAction } = callbacks;

  const DASHBOARD_TIMELINE_DOMAINS = [
    { key: "diseases", label: "Disease", color: "#1d4ed8", symbol: "circle" },
    { key: "treatments", label: "Treatment", color: "#92400e", symbol: "diamond" },
    { key: "phenotypic_features", label: "Phenotype", color: "#166534", symbol: "square" },
    { key: "measures", label: "Measure", color: "#0f766e", symbol: "triangle-up" },
    { key: "procedures", label: "Procedure", color: "#b91c1c", symbol: "cross" },
    { key: "exposures", label: "Exposure", color: "#6d28d9", symbol: "x" },
    { key: "assay", label: "Assay", color: "#0891b2", symbol: "star" },
  ];

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
    refreshPatientList();
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

  function normalizeTimelineItems(summary) {
    const timelines = Array.isArray(summary && summary.timelines) ? summary.timelines : [];
    const assayCoverage = assayTimelineCoverage();
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
            ...assayTimelineEvents(patientId, firstDate, lastDate, assayCoverage.get(patientId)),
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

  function assayTimelineCoverage() {
    const coverage = new Map();
    const datasets = Array.isArray(state.assayDatasetsState) ? state.assayDatasetsState : [];
    datasets.forEach((dataset) => {
      const datasetName = String(dataset && dataset.dataset_name ? dataset.dataset_name : "transcriptomics assay").trim();
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

  function assayTimelineEvents(patientId, firstDate, lastDate, coverage) {
    if (!patientId || !coverage) return [];
    const sampleIds = Array.from(coverage.sampleIds || []);
    const datasetNames = Array.from(coverage.datasetNames || []);
    const eventDate = firstDate || lastDate || "";
    return [{
      visit_id: sampleIds.length ? `assay:${sampleIds.slice(0, 2).join(",")}` : "assays",
      event_date: eventDate,
      event_type: "assay sample coverage",
      diagnosis: "",
      biosample_id: sampleIds.slice(0, 3).join(", "),
      domains: [{
        key: "assay",
        label: "Assay",
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
    if (!Array.isArray(state.dashboardTimelineDomains)) {
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

  function rosterPatient(patientId) {
    return (Array.isArray(state.currentPatients) ? state.currentPatients : [])
      .find((patient) => String(patient && patient.patient_id || "") === String(patientId || "")) || null;
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
    const rosterIdentity = rosterPatient(row.patient_id);
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
            <div class="patient-detail-identity"><h3>${escapeHtml(row.patient_id || "Patient")} ${row.visit_id ? `· ${escapeHtml(row.visit_id)}` : ""}</h3>${claridIdentityMarkup(rosterIdentity)}</div>
          </div>
          <span class="query-chip badge">${selected ? "Patient selected for cohort" : "Patient not selected for cohort"}</span>
        </div>
        <div class="assay-stats">
          <span class="query-chip badge">Date: ${escapeHtml(row.event_date || "undated")}</span>
          ${row.event_type ? `<span class="query-chip badge">Type: ${escapeHtml(row.event_type)}</span>` : ""}
          ${row.diagnosis ? `<span class="query-chip badge">Diagnosis: ${escapeHtml(row.diagnosis)}</span>` : ""}
          ${row.biosample_id ? `<span class="query-chip badge">Sample: ${escapeHtml(row.biosample_id)}</span>` : ""}
        </div>
        <h3>Evidence in this ${clinicalRepresentation(state.dashboardSummaryState || state.dashboardSummary) === "snapshot" ? "timepoint" : "clinical record"}</h3>
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
    const snapshotRepresentation = clinicalRepresentation(summary) === "snapshot";
    const eventNoun = snapshotRepresentation ? "events" : "records";
    const allRows = timelineEventRows(timelineItems, selectedDomains, selectedPatients);
    const inspected = allRows.find((row) => timelineEventKey(row) === state.dashboardTimelineInspectedEventKey);
    if (inspected) renderTimelineInspector(inspected);
    else if (state.dashboardTimelineInspectedEventKey && detailEl) {
      state.dashboardTimelineInspectedEventKey = "";
      detailEl.textContent = "The inspected event is no longer shown. Inspect another event for details.";
    }
    const scopedRows = allRows.filter((row) => {
      if (!query) return true;
      const haystack = [
        row.patient_id,
        normalizedClarid(rosterPatient(row.patient_id))?.human_id,
        normalizedClarid(rosterPatient(row.patient_id))?.stub_id,
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
      const recognized = query && (Array.isArray(state.currentPatients) ? state.currentPatients : []).find((patient) => {
        const clarid = normalizedClarid(patient);
        return clarid && [clarid.human_id, clarid.stub_id].some((value) => String(value || "").toLowerCase() === query);
      });
      countEl.textContent = recognized
        ? `ClarID recognized as patient ${recognized.patient_id} · ${scopedRows.length} matching ${eventNoun}`
        : query
        ? `${scopedRows.length} matching ${eventNoun}`
        : `${scopedRows.length} visible ${eventNoun}`;
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
            <th>Select patient</th>
            <th>Patient</th>
            <th>${snapshotRepresentation ? "Visit" : "Record"}</th>
            <th>Date</th>
            <th>Domains</th>
            <th>Context</th>
            <th>Assay sample</th>
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
            const identity = rosterPatient(row.patient_id);
            return `
              <tr class="${row.selected ? "is-selected" : ""}${isInspected ? " is-inspected" : ""}" data-dashboard-event-patient="${escapeHtml(row.patient_id)}">
                <td><button type="button" class="dashboard-timeline-inspect-btn${isInspected ? " is-active" : ""}" data-dashboard-event-inspect="${escapeHtml(String(index))}" title="Inspect this ${snapshotRepresentation ? "timepoint" : "clinical record"}" aria-label="Inspect ${escapeHtml(row.patient_id)} ${escapeHtml(row.visit_id || (snapshotRepresentation ? "timepoint" : "record"))}" aria-pressed="${isInspected ? "true" : "false"}">
                  ${isInspected
                    ? '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m5 12 4 4L19 6"></path></svg>'
                    : '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 5c5 0 9 5 9 7s-4 7-9 7-9-5-9-7 4-7 9-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>'}
                </button></td>
                <td><input type="checkbox" data-dashboard-select-patient="${escapeHtml(row.patient_id)}" aria-label="Select patient ${escapeHtml(row.patient_id)} for cohort"${row.selected ? " checked" : ""}></td>
                <td><div class="dashboard-timeline-patient-identity"><strong>${escapeHtml(row.patient_id)}</strong>${claridIdentityMarkup(identity, true)}</div></td>
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
    tableEl.querySelectorAll("[data-dashboard-select-patient]").forEach((input) => {
      input.addEventListener("change", () => {
        toggleTimelinePatient(input.getAttribute("data-dashboard-select-patient"), summary);
      });
    });
    tableEl.querySelectorAll("[data-clarid-toggle], [data-clarid-copy]").forEach((button) => {
      button.addEventListener("click", (event) => { void handleClaridAction(event); });
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
          state.dashboardTimelineDomains = selected;
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
        ? `${selectedPatientIds.length} patient${selectedPatientIds.length === 1 ? "" : "s"} selected. Whole patients—not just the visible dates or event types.`
        : "Use the patient checkboxes in Events to build a cohort.";
    }
    const actionsEl = document.getElementById("dashboard-timeline-actions");
    if (actionsEl) actionsEl.hidden = !selectedPatientIds.length;
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
    const durations = datedItems.map((item) => Math.max(((item.last_time || item.first_time) - item.first_time) / oneDayMs, 0));
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
          event_key: timelineEventKey({ ...event, patient_id: item.patient_id,
            domains: event.domains.filter((domain) => selectedDomains.has(domain.key)) }),
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
        customdata: domainPoints.map((point) => [point.patient_id, point.visit_id, point.event_key]),
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
          hovertemplate: "Patient: %{customdata}<br>Start: %{base}<br>Duration: %{x:.0f} days<br>Click to inspect first visible event<extra></extra>",
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
        clickmode: "event",
        dragmode: "zoom",
        showlegend: false,
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
            const visitId = Array.isArray(point?.customdata) ? point.customdata[1] : null;
            const eventKey = Array.isArray(point?.customdata) ? point.customdata[2] : null;
            const row = timelineEventRows(visibleItems, selectedDomains, selectedPatients)
              .find((item) => eventKey ? timelineEventKey(item) === eventKey
                : item.patient_id === patientId && (visitId === null || item.visit_id === visitId));
            if (row) {
              renderTimelineInspector(row);
              renderTimelineEventTable(visibleItems, selectedDomains, selectedPatients, summary);
              detailEl.scrollIntoView({ block: "nearest", behavior: "auto" });
            }
          });
        }
      },
      {
        displayModeBar: true,
        modeBarButtonsToRemove: ["select2d", "lasso2d"],
      }
    );
  }

  function timelinePanelMarkup(snapshotRepresentation) {
    return `
      <section class="section-card dashboard-timeline-card">
        <div class="section-card-header">
          <div class="section-card-eyebrow">${snapshotRepresentation ? "Longitudinal coverage" : "Clinical coverage"}</div>
          <h3>${snapshotRepresentation ? "Patient timeline" : "Patient records"}</h3>
        </div>
        <div class="section-note">Inspect visits and available samples. Click an event for details; drag to zoom. Zoom and event filters change this view only, not the data used in Analysis.</div>
        <div><strong id="dashboard-timeline-controls-label">Show events</strong><div id="dashboard-timeline-controls" class="dashboard-timeline-controls" role="group" aria-labelledby="dashboard-timeline-controls-label"></div></div>
        <div id="dashboard-timeline-actions" class="dashboard-timeline-actions" hidden>
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
              <h4>Events</h4>
              <div class="section-note">Inspect an event for details. Use checkboxes to select whole patients for a cohort or Analysis.</div>
              <div id="dashboard-timeline-event-count" class="section-note">Filter by patient, ${snapshotRepresentation ? "visit" : "record"}, domain, diagnosis, event type, or sample.</div>
            </div>
            <input id="dashboardTimelineEventSearch" class="patient-search dashboard-timeline-event-search" aria-label="Search all timeline fields" placeholder="Search all fields">
          </div>
          <div id="dashboard-timeline-event-table" class="dashboard-timeline-table-wrap"></div>
        </div>
      </section>
    `;
  }

  return { timelineSelectedPatientSet, toggleTimelinePatientSelection,
    renderDashboardTimeline, timelinePanelMarkup };
}
