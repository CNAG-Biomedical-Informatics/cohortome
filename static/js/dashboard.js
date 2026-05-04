export function createDashboardUi(ctx) {
  const { refs, helpers, callbacks, state, constants } = ctx;
  const {
    patientsEl,
    dashboardEl,
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
    renderAnalysisCatalog,
    renderAnalysisCatalogMolecularPanel,
  } = callbacks;
  const { MAX_VISIBLE_PATIENTS } = constants;
  const DASHBOARD_PLOT_COLORS = ["#2563eb", "#0ea5e9", "#059669", "#7c3aed", "#ea580c", "#dc2626"];

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

  function mountPlot(targetId, traces, layout) {
    const el = document.getElementById(targetId);
    if (!el) return;
    if (!plotlyAvailable()) {
      el.innerHTML = '<div class="empty">Plot rendering unavailable.</div>';
      return;
    }
    window.Plotly.newPlot(el, traces, layout, dashboardPlotConfig());
    window.requestAnimationFrame(() => {
      if (window.Plotly && window.Plotly.Plots && typeof window.Plotly.Plots.resize === "function") {
        window.Plotly.Plots.resize(el);
      }
    });
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
    return `
      <div class="patient-card ${activeClass}" data-patient-id="${patient.patient_id}">
        <strong>${patient.patient_id}</strong>
        <div>
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
    const toggleBtn = document.getElementById("dashboardClinicalToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        state.dashboardClinicalExpanded = !state.dashboardClinicalExpanded;
        renderDashboard(state.dashboardSummary || summary);
      });
    }
    renderDashboardCharts(summary);
  }

  function renderAnalysisScopeSummary() {
    const selectedCohort = Array.isArray(state.savedCohorts)
      ? state.savedCohorts.find((item) => item.id === state.analysisSelectedSavedCohortId)
      : null;
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
      : `${ids.length} ${ids.length === 1 ? "ID" : "IDs"}`;
    analysisSelectedPatientIdsSummaryEl.textContent = compareMode
      ? (selectedCohort
        ? `Cohort A: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
        : "Cohort A: select a saved cohort from Saved Cohorts to compare.")
      : (selectedCohort
        ? `Scope: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
        : ids.length
          ? `Scope: ${ids.length} IDs in scope.`
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
      : `${ids.length} IDs`;
    analysisCompareSelectedPatientIdsSummaryEl.textContent = selectedCohort
      ? `Cohort B: using saved cohort "${selectedCohort.name}" (${countLabel}; ${ids.length} ${selectedCohortUsesSampleIds ? "sample IDs" : "patient IDs"} loaded).`
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
          <div class="molecular-card-eyebrow">Workspace overview</div>
          <strong class="molecular-workspace-summary-title">Loaded molecular workspace</strong>
          <div class="section-note">A quick summary of the active transcriptomics footprint before drilling into individual datasets.</div>
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
  };
}
