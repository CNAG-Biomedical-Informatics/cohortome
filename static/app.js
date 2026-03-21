      const cohortTabBtnEl = document.getElementById("cohortTabBtn");
      const queryTabBtnEl = document.getElementById("queryTabBtn");
      const phenoTabBtnEl = document.getElementById("phenoTabBtn");
      const cohortTabEl = document.getElementById("cohortTab");
      const queryTabEl = document.getElementById("queryTab");
      const phenoTabEl = document.getElementById("phenoTab");
      const patientsEl = document.getElementById("patients");
      const dashboardEl = document.getElementById("dashboard");
      const detailEl = document.getElementById("detail");
      const dataDirEl = document.getElementById("dataDir");
      const loadStatusEl = document.getElementById("loadStatus");
      const queryReplyEl = document.getElementById("queryReply");
      const queryStatusEl = document.getElementById("queryStatus");
      const queryMetaEl = document.getElementById("queryMeta");
      const lmStatusEl = document.getElementById("lmStatus");
      const queryReasonEl = document.getElementById("queryReason");
      const queryActionsEl = document.getElementById("queryActions");
      const queryFollowupsEl = document.getElementById("queryFollowups");
      const queryExamplesEl = document.getElementById("queryExamples");
      const queryDataEl = document.getElementById("queryData");
      const queryDetailsEl = document.getElementById("queryDetails");
      const questionEl = document.getElementById("question");
      const askBtnEl = document.getElementById("askBtn");
      const loadBtnEl = document.getElementById("loadBtn");
      const patientSearchEl = document.getElementById("patientSearch");
      const phenoActionEl = document.getElementById("phenoAction");
      const phenoModeEl = document.getElementById("phenoMode");
      const phenoPromptEl = document.getElementById("phenoPrompt");
      const phenoExamplesEl = document.getElementById("phenoExamples");
      const phenoPlanBtnEl = document.getElementById("phenoPlanBtn");
      const phenoPlanRunBtnEl = document.getElementById("phenoPlanRunBtn");
      const phenoPlanStatusEl = document.getElementById("phenoPlanStatus");
      const phenoPlanMetaEl = document.getElementById("phenoPlanMeta");
      const phenoLmStatusEl = document.getElementById("phenoLmStatus");
      const phenoPlanEl = document.getElementById("phenoPlan");
      const phenoPlanReasoningEl = document.getElementById("phenoPlanReasoning");
      const phenoReferenceFilesSummaryEl = document.getElementById("phenoReferenceFilesSummary");
      const phenoPatientFieldEl = document.getElementById("phenoPatientField");
      const phenoPatientIdEl = document.getElementById("phenoPatientId");
      const phenoSelectedPatientIdsEl = document.getElementById("phenoSelectedPatientIds");
      const phenoSelectedPatientIdsSummaryEl = document.getElementById("phenoSelectedPatientIdsSummary");
      const phenoIncludeTermsEl = document.getElementById("phenoIncludeTerms");
      const phenoExcludeTermsEl = document.getElementById("phenoExcludeTerms");
      const phenoSimilarityMetricEl = document.getElementById("phenoSimilarityMetric");
      const phenoSortByEl = document.getElementById("phenoSortBy");
      const phenoMaxOutFieldEl = document.getElementById("phenoMaxOutField");
      const phenoMaxOutEl = document.getElementById("phenoMaxOut");
      const phenoAlignChecksEl = document.getElementById("phenoAlignChecks");
      const phenoAlignEl = document.getElementById("phenoAlign");
      const phenoRenderHeatmapEl = document.getElementById("phenoRenderHeatmap");
      const phenoRenderMdsEl = document.getElementById("phenoRenderMds");
      const phenoPlotChecksEl = document.getElementById("phenoPlotChecks");
      const phenoRunBtnEl = document.getElementById("phenoRunBtn");
      const phenoExplainBtnEl = document.getElementById("phenoExplainBtn");
      const phenoExplainLlmBtnEl = document.getElementById("phenoExplainLlmBtn");
      const phenoStatusEl = document.getElementById("phenoStatus");
      const phenoExplainDetailEl = document.getElementById("phenoExplainDetail");
      const phenoCommandEl = document.getElementById("phenoCommand");
      const phenoFilesEl = document.getElementById("phenoFiles");
      const phenoOutputDetailsEl = document.getElementById("phenoOutputDetails");
      const phenoOutputPreviewEl = document.getElementById("phenoOutputPreview");
      const phenoAlignmentDetailEl = document.getElementById("phenoAlignmentDetail");
      const phenoLogsEl = document.getElementById("phenoLogs");
      const phenoPreviewsEl = document.getElementById("phenoPreviews");
      const MAX_VISIBLE_PATIENTS = 80;
      const PHENO_BUCKET_STYLES = {
        diseases: { bg: "#dbeafe", ink: "#1d4ed8" },
        phenotypicFeatures: { bg: "#dcfce7", ink: "#166534" },
        treatments: { bg: "#fef3c7", ink: "#92400e" },
        procedures: { bg: "#fee2e2", ink: "#b91c1c" },
        exposures: { bg: "#ede9fe", ink: "#6d28d9" },
        measures: { bg: "#cffafe", ink: "#0f766e" },
        sex: { bg: "#fce7f3", ink: "#be185d" },
        ethnicity: { bg: "#e0f2fe", ink: "#0369a1" },
        identifier: { bg: "#f3f4f6", ink: "#111827" },
        other: { bg: "#e5e7eb", ink: "#374151" },
      };
      let selectedPatientId = null;
      let currentPatients = [];
      let queryInFlight = false;
      let loadInFlight = false;
      let phenoInFlight = false;
      let phenoPlanInFlight = false;
      let phenoTableState = null;
      let phenoRunState = null;
      let phenoSelectedAlignmentKey = "";
      let latestQueryPatientIds = [];
      let phenoRankerPatientIds = [];
      let phenoReferenceFiles = [];

      function setActiveTab(tabName) {
        const showCohort = tabName === "cohort";
        const showQuery = tabName === "query";
        const showPheno = tabName === "pheno";
        cohortTabBtnEl.classList.toggle("active", showCohort);
        queryTabBtnEl.classList.toggle("active", showQuery);
        phenoTabBtnEl.classList.toggle("active", showPheno);
        cohortTabEl.classList.toggle("active", showCohort);
        queryTabEl.classList.toggle("active", showQuery);
        phenoTabEl.classList.toggle("active", showPheno);
      }

      function formatNumber(value) {
        return new Intl.NumberFormat().format(value);
      }

      async function loadLmStatus() {
        if (!lmStatusEl || !phenoLmStatusEl) {
          return;
        }
        try {
          const response = await fetch("/lm-status");
          if (!response.ok) {
            throw new Error("Unable to load LM status.");
          }
          const payload = await response.json();
          let text = "LM Studio: disabled";
          if (payload.enabled) {
            text = payload.model
              ? `LM Studio model: ${payload.model}`
              : "LM Studio: enabled, but no model is loaded";
          }
          lmStatusEl.textContent = text;
          phenoLmStatusEl.textContent = text;
        } catch (error) {
          const text = "LM Studio model: unavailable";
          lmStatusEl.textContent = text;
          phenoLmStatusEl.textContent = text;
        }
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
          return escapeHtml(part)
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>");
        }).join("");
      }

      function renderQueryStructuredTable(payload) {
        const data = payload && payload.data ? payload.data : {};
        if (Array.isArray(data.medications) && data.medications.length) {
          const rows = data.medications.slice(0, 100).map((item) => `
            <tr>
              <td>${escapeHtml(String(item.medication || ""))}</td>
              <td>${escapeHtml(String(item.patient_count ?? ""))}</td>
            </tr>
          `).join("");
          return `
            <div class="section-note">Medication inventory (${data.medications.length}).</div>
            <table>
              <thead><tr><th>Medication</th><th>Patients</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          `;
        }
        if (Array.isArray(data.diseases) && data.diseases.length) {
          const rows = data.diseases.slice(0, 100).map((item) => `
            <tr>
              <td>${escapeHtml(String(item.disease || ""))}</td>
              <td>${escapeHtml(String(item.patient_count ?? ""))}</td>
            </tr>
          `).join("");
          return `
            <div class="section-note">Disease inventory (${data.diseases.length}).</div>
            <table>
              <thead><tr><th>Disease</th><th>Patients</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          `;
        }
        if (Array.isArray(data.patients) && data.patients.length && payload && payload.intent === "patient_medication_count_cohort") {
          const rows = data.patients.slice(0, 100).map((item) => `
            <tr>
              <td>${escapeHtml(String(item.patient_id || ""))}</td>
              <td>${escapeHtml(String(item.sex || ""))}</td>
              <td>${escapeHtml(String(item.visit_count ?? ""))}</td>
              <td>${escapeHtml(String(item.medication_count ?? ""))}</td>
            </tr>
          `).join("");
          return `
            <div class="section-note">Matching patients (${data.patients.length}).</div>
            <table>
              <thead><tr><th>Patient</th><th>Sex</th><th>Visits</th><th>Medications</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          `;
        }
        return "";
      }

      function renderQueryReply(payloadOrValue) {
        const structured = typeof payloadOrValue === "object" && payloadOrValue ? renderQueryStructuredTable(payloadOrValue) : "";
        if (structured) {
          return structured;
        }
        const value = typeof payloadOrValue === "object" && payloadOrValue ? payloadOrValue.reply : payloadOrValue;
        const lines = String(value || "").split("\r\n").join("\n").split("\n");
        const blocks = [];
        let paragraphLines = [];
        let listItems = [];
        let codeLines = [];
        let tableLines = [];
        let inCodeBlock = false;

        function flushParagraph() {
          if (!paragraphLines.length) {
            return;
          }
          blocks.push(`<p>${paragraphLines.map((line) => renderInlineCode(line)).join("<br>")}</p>`);
          paragraphLines = [];
        }

        function flushList() {
          if (!listItems.length) {
            return;
          }
          blocks.push(`<ul>${listItems.map((line) => `<li>${renderInlineCode(line)}</li>`).join("")}</ul>`);
          listItems = [];
        }

        function flushCodeBlock() {
          if (!codeLines.length) {
            return;
          }
          blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
          codeLines = [];
        }

        function isTableLine(line) {
          return line.includes("|");
        }

        function isTableSeparatorLine(line) {
          const cells = line.split("|").map((cell) => cell.trim()).filter(Boolean);
          if (!cells.length) {
            return false;
          }
          return cells.every((cell) => cell.length >= 3 && cell.split("-").join("").split(":").join("") === "");
        }

        function splitTableCells(line) {
          let normalized = line.trim();
          if (normalized.startsWith("|")) {
            normalized = normalized.slice(1);
          }
          if (normalized.endsWith("|")) {
            normalized = normalized.slice(0, -1);
          }
          return normalized.split("|").map((cell) => renderInlineCode(cell.trim()));
        }

        function flushTable() {
          if (tableLines.length < 2) {
            if (tableLines.length) {
              paragraphLines = paragraphLines.concat(tableLines);
            }
            tableLines = [];
            return;
          }
          const headerLine = tableLines[0];
          const separatorLine = tableLines[1];
          if (!isTableSeparatorLine(separatorLine)) {
            paragraphLines = paragraphLines.concat(tableLines);
            tableLines = [];
            return;
          }
          const headers = splitTableCells(headerLine);
          const rows = tableLines.slice(2).map(splitTableCells);
          blocks.push(
            `<table><thead><tr>${headers.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>` +
            `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table>`
          );
          tableLines = [];
        }

        for (const rawLine of lines) {
          const trimmed = rawLine.trim();

          if (trimmed.startsWith("```")) {
            flushParagraph();
            flushList();
            flushTable();
            if (inCodeBlock) {
              flushCodeBlock();
              inCodeBlock = false;
            } else {
              inCodeBlock = true;
            }
            continue;
          }

          if (inCodeBlock) {
            codeLines.push(rawLine);
            continue;
          }

          if (!trimmed) {
            flushParagraph();
            flushList();
            flushTable();
            continue;
          }

          if (isTableLine(trimmed)) {
            flushParagraph();
            flushList();
            tableLines.push(trimmed);
            continue;
          }

          flushTable();

          if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
            flushParagraph();
            listItems.push(trimmed.slice(2));
            continue;
          }

          if (trimmed.startsWith("### ")) {
            flushParagraph();
            flushList();
            flushTable();
            blocks.push(`<h4>${renderInlineCode(trimmed.slice(4))}</h4>`);
            continue;
          }

          if (trimmed.startsWith("## ")) {
            flushParagraph();
            flushList();
            flushTable();
            blocks.push(`<h4>${renderInlineCode(trimmed.slice(3))}</h4>`);
            continue;
          }

          if (trimmed.startsWith("# ")) {
            flushParagraph();
            flushList();
            flushTable();
            blocks.push(`<h4>${renderInlineCode(trimmed.slice(2))}</h4>`);
            continue;
          }

          paragraphLines.push(trimmed);
        }

        flushParagraph();
        flushList();
        flushTable();
        if (inCodeBlock) {
          flushCodeBlock();
        }

        return blocks.join("") || "<p>No answer returned.</p>";
      }

      function renderQueryMeta(payload) {
        const chips = [];
        const provider = payload && payload.data && payload.data.provider;
        chips.push(`<span class="query-chip badge">${escapeHtml(payload.intent || "unknown")}</span>`);
        chips.push(`<span class="query-chip badge">${escapeHtml(provider === "lm_studio" ? "LM Studio" : "Deterministic")}</span>`);
        queryMetaEl.innerHTML = chips.join("");
      }

      function renderQueryReason(payload) {
        const data = payload.data || {};
        const provider = data.provider;
        const reasons = [];
        reasons.push(`Intent: ${payload.intent || "unknown"}.`);
        reasons.push(`Provider: ${provider === "lm_studio" ? "LM Studio fallback" : "deterministic dataset logic"}.`);
        if (data.context && data.context.dataset_overview) {
          const totals = data.context.dataset_overview;
          reasons.push(`Context included cohort totals for ${totals.patients} patients and ${totals.visits} visits.`);
        } else if (typeof data.patient_count === "number") {
          reasons.push(`Matched patient count: ${data.patient_count}.`);
        } else if (Array.isArray(data.medications)) {
          reasons.push(`Medication inventory size shown: ${data.medications.length}.`);
        } else if (Array.isArray(data.diseases)) {
          reasons.push(`Disease inventory size shown: ${data.diseases.length}.`);
        }
        if (payload.intent === "needs_clarification") {
          reasons.push("The prompt was too vague, so the UI is suggesting more specific follow-up questions.");
        }
        if (payload.intent === "unsupported") {
          reasons.push("The deterministic router did not recognize the query pattern, and no fallback answer was produced.");
        }
        queryReasonEl.innerHTML = `<p>${reasons.map(escapeHtml).join("<br>")}</p>`;
      }

      function renderFollowupButtons(items) {
        const followups = Array.isArray(items) ? items.slice(0, 4) : [];
        if (!followups.length) {
          queryFollowupsEl.innerHTML = "";
          return;
        }
        queryFollowupsEl.innerHTML = followups.map((item) => `
          <button type="button" class="query-chip" data-prompt="${escapeHtml(item)}">${escapeHtml(item)}</button>
        `).join("");
      }

      function inferPatientIdsFromQueryPayload(payload) {
        const fromOriginalData = payload && payload.data && Array.isArray(payload.data.original_record_ids)
          ? payload.data.original_record_ids.filter(Boolean)
          : [];
        if (fromOriginalData.length) {
          return fromOriginalData;
        }
        const fromPatientOriginalIds = payload && payload.data && Array.isArray(payload.data.patients)
          ? payload.data.patients
              .flatMap((item) => Array.isArray(item && item.original_record_ids) ? item.original_record_ids : [])
              .filter(Boolean)
          : [];
        if (fromPatientOriginalIds.length) {
          return Array.from(new Set(fromPatientOriginalIds));
        }
        const fromData = payload && payload.data && Array.isArray(payload.data.patient_ids)
          ? payload.data.patient_ids.filter(Boolean)
          : [];
        if (fromData.length) {
          return fromData;
        }
        const fromPatientObjects = payload && payload.data && Array.isArray(payload.data.patients)
          ? payload.data.patients
              .map((item) => item && item.patient_id)
              .filter(Boolean)
          : [];
        if (fromPatientObjects.length) {
          return fromPatientObjects;
        }
        const replyText = String((payload && payload.reply) || "");
        const knownIds = currentPatients.map((patient) => patient.patient_id).filter(Boolean);
        const found = [];
        for (const patientId of knownIds) {
          const escaped = patientId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          const pattern = new RegExp(`(^|[^A-Za-z0-9_])${escaped}($|[^A-Za-z0-9_])`, "i");
          if (pattern.test(replyText) && !found.includes(patientId)) {
            found.push(patientId);
          }
        }
        if (found.length) {
          return found;
        }
        const inferred = [];
        const lines = replyText.split("\r\n").join("\n").split("\n");
        for (const line of lines) {
          const trimmed = line.trim().replace(/^[-*]\s+/, "");
          if (!trimmed) {
            continue;
          }
          const match = trimmed.match(/^([A-Za-z]*_?\d+(?::[A-Za-z0-9_-]+)?)$/);
          if (match && !inferred.includes(match[1])) {
            inferred.push(match[1]);
          }
        }
        if (inferred.length) {
          return inferred;
        }
        const inlineMatches = replyText.match(/\b(?:[A-Za-z]+_)?\d+(?::[A-Za-z0-9_-]+)?\b/g) || [];
        for (const token of inlineMatches) {
          if (!inferred.includes(token)) {
            inferred.push(token);
          }
        }
        return inferred;
      }

      function renderQueryActions(payload) {
        const patientIds = inferPatientIdsFromQueryPayload(payload);
        latestQueryPatientIds = patientIds;
        if (!patientIds.length) {
          queryActionsEl.innerHTML = "";
          return;
        }
        const compatibleIds = phenoRankerPatientIds.length
          ? patientIds.filter((patientId) => phenoRankerPatientIds.includes(patientId))
          : [];
        const allCompatible = patientIds.length > 0 && compatibleIds.length === patientIds.length;
        queryActionsEl.innerHTML = `
          <button type="button" class="query-chip" data-query-action="copy-ids">Copy patient IDs</button>
          ${allCompatible ? '<button type="button" class="query-chip action" data-query-action="use-pheno">Use IDs in Pheno-Ranker</button>' : ""}
          ${phenoRankerPatientIds.length && !allCompatible ? '<span class="query-chip badge">This result is grouped at patient level. Pheno-Ranker needs the original record IDs or timepoints.</span>' : ""}
        `;
      }

      async function copyPatientIdsFromQuery() {
        if (!latestQueryPatientIds.length) {
          return;
        }
        const payload = latestQueryPatientIds.join(",");
        try {
          await navigator.clipboard.writeText(payload);
          queryStatusEl.className = "query-status";
          queryStatusEl.textContent = `Copied ${latestQueryPatientIds.length} patient IDs.`;
        } catch (_error) {
          queryStatusEl.className = "query-status";
          queryStatusEl.textContent = "Unable to copy patient IDs from the browser.";
        }
      }

      function renderSelectedPatientIdsSummary() {
        const ids = getCurrentScopeIds();
        if (!ids.length) {
          phenoSelectedPatientIdsSummaryEl.textContent = "Scope: full cohort.";
          return;
        }
        const preview = ids.slice(0, 8).join(", ");
        const suffix = ids.length > 8 ? ` ... (+${ids.length - 8} more)` : "";
        const invalidIds = phenoRankerPatientIds.length
          ? ids.filter((patientId) => !phenoRankerPatientIds.includes(patientId))
          : [];
        if (invalidIds.length) {
          phenoSelectedPatientIdsSummaryEl.textContent = `Scope: ${ids.length} IDs entered. Some are patient-level IDs, but Pheno-Ranker needs the original record IDs or timepoints for this reference: ${invalidIds.join(", ")}.`;
          return;
        }
        phenoSelectedPatientIdsSummaryEl.textContent = `Scope: ${ids.length} selected patients. ${preview}${suffix}`;
      }

      function sendPatientIdsToPhenoRanker() {
        if (!latestQueryPatientIds.length) {
          return;
        }
        phenoActionEl.value = "compare";
        phenoModeEl.value = "cohort";
        phenoSelectedPatientIdsEl.value = latestQueryPatientIds.join(",");
        renderSelectedPatientIdsSummary();
        updatePhenoMode();
        setActiveTab("pheno");
        phenoStatusEl.className = "pheno-status";
        phenoStatusEl.textContent = `Loaded ${latestQueryPatientIds.length} patient IDs from the query result into the current scope.`;
      }

      function nextFrame() {
        return new Promise((resolve) => {
          window.requestAnimationFrame(() => resolve());
        });
      }

      async function loadPhenoRankerPatientIds() {
        try {
          const dataDir = encodeURIComponent(dataDirEl.value.trim());
          const response = await fetch(`/pheno-ranker/patient-ids?data_dir=${dataDir}`);
          if (!response.ok) {
            phenoRankerPatientIds = [];
            phenoReferenceFiles = [];
            phenoReferenceFilesSummaryEl.textContent = "Active cohort files: unavailable.";
            return;
          }
          const payload = await response.json();
          phenoRankerPatientIds = Array.isArray(payload.patient_ids) ? payload.patient_ids.filter(Boolean) : [];
          phenoReferenceFiles = Array.isArray(payload.reference_files) ? payload.reference_files.filter(Boolean) : [];
          if (!phenoReferenceFiles.length) {
            phenoReferenceFilesSummaryEl.textContent = "Active cohort files: none.";
          } else {
            const labels = phenoReferenceFiles.map((item) => item.split("/").pop()).join(", ");
            phenoReferenceFilesSummaryEl.textContent = `Active cohort files (${phenoReferenceFiles.length}): ${labels}`;
          }
        } catch (_error) {
          phenoRankerPatientIds = [];
          phenoReferenceFiles = [];
          phenoReferenceFilesSummaryEl.textContent = "Active cohort files: unavailable.";
        }
      }

      function updatePhenoMode() {
        const patientMode = phenoModeEl.value === "patient";
        const extractMode = phenoActionEl.value === "extract";
        phenoPatientFieldEl.classList.toggle("is-hidden", !patientMode || extractMode);
        phenoMaxOutFieldEl.classList.toggle("is-hidden", !patientMode || extractMode);
        phenoAlignChecksEl.classList.toggle("is-hidden", !patientMode || extractMode);
        phenoPlotChecksEl.classList.toggle("is-hidden", patientMode || extractMode);
      }

      function renderPhenoPlanReasoning(items) {
        const lines = Array.isArray(items) ? items.filter(Boolean) : [];
        if (!lines.length) {
          phenoPlanReasoningEl.innerHTML = '<div class="empty">No planner reasoning yet.</div>';
          return;
        }
        phenoPlanReasoningEl.innerHTML = `<ul class="mini-list">${lines.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
      }

      function getPhenoPlanBlockingIssues(plan) {
        const normalized = plan || {};
        const action = String(normalized.action || "compare");
        const mode = String(normalized.mode || "cohort");
        const patientId = String(normalized.patient_id || "").trim();
        const scopeIds = typeof normalized.selected_patient_ids === "string"
          ? normalized.selected_patient_ids.split(",").map((item) => item.trim()).filter(Boolean)
          : (Array.isArray(normalized.selected_patient_ids) ? normalized.selected_patient_ids.map((item) => String(item || "").trim()).filter(Boolean) : []);
        const issues = [];

        if (action === "extract" && !scopeIds.length) {
          issues.push("Extraction needs a non-empty Scope before it can run.");
        }

        if (mode === "patient") {
          if (!patientId && scopeIds.length !== 1) {
            issues.push("Patient mode needs exactly one target patient from Patient ID or Scope.");
          }
          if (!patientId && scopeIds.length === 1) {
            issues.push(`Patient mode will use ${scopeIds[0]} as the target patient.`);
          }
          if (scopeIds.length > 1) {
            issues.push("Patient mode cannot run with multiple IDs in Scope.");
          }
        }

        return issues;
      }

      function renderPhenoPlanState(plan, reasoning) {
        const issues = getPhenoPlanBlockingIssues(plan);
        phenoPlanStatusEl.classList.remove("warning");
        phenoPlanEl.classList.remove("is-blocking");
        phenoPlanReasoningEl.classList.remove("is-blocking");

        if (!issues.length) {
          return;
        }

        phenoPlanStatusEl.classList.add("warning");
        phenoPlanEl.classList.add("is-blocking");
        phenoPlanReasoningEl.classList.add("is-blocking");

        const warningHtml = `
          <div class="planner-warning">
            <strong>Planner output is not runnable yet.</strong>
            <ul class="mini-list">${issues.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </div>
        `;

        if (Array.isArray(reasoning) && reasoning.length) {
          phenoPlanReasoningEl.innerHTML = `${warningHtml}${phenoPlanReasoningEl.innerHTML}`;
        } else {
          phenoPlanReasoningEl.innerHTML = warningHtml;
        }
      }

      function renderPhenoPlanMeta(source) {
        if (!source) {
          phenoPlanMetaEl.innerHTML = "";
          return;
        }
        const isLm = String(source) === "lm_studio";
        const label = isLm ? "LM-based" : "Deterministic";
        const className = isLm ? "query-chip query-chip-llm badge" : "query-chip query-chip-deterministic badge";
        phenoPlanMetaEl.innerHTML = `<span class="${className}">${escapeHtml(label)}</span>`;
      }

      function renderPhenoNoPlanState(reasoning) {
        phenoPlanStatusEl.className = "pheno-status warning";
        phenoPlanStatusEl.textContent = "Planner did not find a runnable Pheno-Ranker request yet.";
        phenoPlanEl.classList.add("is-blocking");
        phenoPlanReasoningEl.classList.add("is-blocking");
        phenoPlanEl.textContent = "No actionable plan.";
        renderPhenoPlanReasoning(reasoning || []);
        phenoPlanReasoningEl.innerHTML = `
          <div class="planner-warning">
            <strong>No runnable plan yet.</strong>
            <div>Describe a comparison or extraction request instead of a greeting or generic note.</div>
          </div>
          ${phenoPlanReasoningEl.innerHTML}
        `;
      }

      function compactPhenoPlan(plan) {
        const compact = {};
        for (const [key, value] of Object.entries(plan || {})) {
          if (Array.isArray(value) && !value.length) {
            continue;
          }
          if (value === "" || value === null || value === undefined) {
            continue;
          }
          compact[key] = value;
        }
        return compact;
      }

      function parsePhenoTermsInput(value) {
        return String(value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      }

      function getCurrentScopeIds() {
        return String(phenoSelectedPatientIdsEl.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      }

      function applyPhenoPlan(plan) {
        const normalized = plan || {};
        phenoActionEl.value = normalized.action || "compare";
        phenoModeEl.value = normalized.mode || "cohort";
        const scopeIdsBeforePlan = getCurrentScopeIds();
        phenoPatientIdEl.value = normalized.patient_id || "";
        if (typeof normalized.selected_patient_ids === "string" && normalized.selected_patient_ids.trim()) {
          phenoSelectedPatientIdsEl.value = normalized.selected_patient_ids;
        }
        const scopeIdsAfterPlan = getCurrentScopeIds();
        if (phenoModeEl.value === "patient" && !phenoPatientIdEl.value.trim() && scopeIdsAfterPlan.length === 1) {
          phenoPatientIdEl.value = scopeIdsAfterPlan[0];
        } else if (
          phenoModeEl.value === "patient"
          && !phenoPatientIdEl.value.trim()
          && !scopeIdsAfterPlan.length
          && scopeIdsBeforePlan.length === 1
        ) {
          phenoPatientIdEl.value = scopeIdsBeforePlan[0];
        }
        renderSelectedPatientIdsSummary();
        phenoIncludeTermsEl.value = Array.isArray(normalized.include_terms) ? normalized.include_terms.join(",") : (normalized.include_terms || "");
        phenoExcludeTermsEl.value = Array.isArray(normalized.exclude_terms) ? normalized.exclude_terms.join(",") : (normalized.exclude_terms || "");
        phenoSimilarityMetricEl.value = normalized.similarity_metric_cohort || "";
        phenoSortByEl.value = normalized.sort_by || "";
        phenoMaxOutEl.value = Number(normalized.max_out || 10);
        phenoAlignEl.checked = Boolean(normalized.align);
        phenoRenderHeatmapEl.checked = Boolean(normalized.render_heatmap);
        phenoRenderMdsEl.checked = Boolean(normalized.render_mds);
        updatePhenoMode();
      }

      async function requestPhenoPlan() {
        if (phenoPlanInFlight) {
          return null;
        }
        const text = phenoPromptEl.value.trim();
        if (!text) {
          phenoPlanStatusEl.textContent = "Describe a Pheno-Ranker request first.";
          return null;
        }

        phenoPlanInFlight = true;
        phenoPlanBtnEl.disabled = true;
        phenoPlanRunBtnEl.disabled = true;
        phenoPlanStatusEl.className = "pheno-status loading";
        phenoPlanStatusEl.textContent = "Interpreting request...";
        renderPhenoPlanMeta("");
        phenoPlanEl.textContent = "Waiting for interpreted plan...";
        renderPhenoPlanReasoning([]);
        await nextFrame();

        try {
          const response = await fetch("/pheno-ranker/plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text,
              data_dir: dataDirEl.value.trim(),
              selected_patient_ids: phenoSelectedPatientIdsEl.value.trim(),
            }),
          });
          if (!response.ok) {
            const error = await response.json();
            const detail = error.detail && typeof error.detail === "object" ? JSON.stringify(error.detail, null, 2) : String(error.detail || "Planner request failed.");
            phenoPlanStatusEl.className = "pheno-status";
            phenoPlanStatusEl.textContent = "Planner failed.";
            renderPhenoPlanMeta("");
            phenoPlanEl.textContent = detail;
            renderPhenoPlanReasoning([]);
            return null;
          }
          const payload = await response.json();
          renderPhenoPlanMeta(payload.source || "deterministic");
          if (!payload.plan || typeof payload.plan !== "object") {
            renderPhenoNoPlanState(payload.reasoning || []);
            return payload;
          }
          applyPhenoPlan(payload.plan || {});
          phenoPlanEl.textContent = JSON.stringify(compactPhenoPlan(payload.plan || {}), null, 2);
          renderPhenoPlanReasoning(payload.reasoning || []);
          const blockingIssues = getPhenoPlanBlockingIssues(payload.plan || {});
          phenoPlanStatusEl.className = "pheno-status";
          phenoPlanStatusEl.textContent = blockingIssues.length
            ? "Planner found a blocking issue. Fix the highlighted fields before running."
            : "Planner ready. Review the interpreted plan for the current scope, then run it.";
          renderPhenoPlanState(payload.plan || {}, payload.reasoning || []);
          return payload;
        } catch (error) {
          phenoPlanStatusEl.className = "pheno-status";
          phenoPlanStatusEl.textContent = "Planner request failed.";
          renderPhenoPlanMeta("");
          phenoPlanEl.textContent = error && error.message ? error.message : "Unexpected planner failure.";
          renderPhenoPlanReasoning([]);
          return null;
        } finally {
          phenoPlanInFlight = false;
          phenoPlanBtnEl.disabled = false;
          phenoPlanRunBtnEl.disabled = false;
        }
      }

      async function planPhenoRanker() {
        await requestPhenoPlan();
      }

      async function planAndRunPhenoRanker() {
        const payload = await requestPhenoPlan();
        if (!payload || !payload.plan) {
          return;
        }
        await runPhenoRanker();
      }

      function renderPhenoFiles(files) {
        if (!Array.isArray(files) || !files.length) {
          phenoFilesEl.innerHTML = '<div class="empty">No output files yet.</div>';
          return;
        }
        phenoFilesEl.innerHTML = `<ul class="pheno-file-list">${files.map((file) => `<li><a href="${file.url}" target="_blank" rel="noreferrer">${escapeHtml(file.name)}</a> (${file.size} bytes)</li>`).join("")}</ul>`;
      }

      function parseTsvLines(text) {
        const lines = String(text || "").split("\r\n").join("\n").split("\n").filter((line) => line.trim() && line.includes("\t"));
        if (!lines.length) {
          return null;
        }
        const header = lines[0].split("\t").map((cell) => cell.trim());
        if (header.length < 2) {
          return null;
        }
        const bodyRows = lines.slice(1)
          .map((line) => line.split("\t").map((cell) => cell.trim()))
          .filter((cells) => cells.length === header.length);
        if (!bodyRows.length) {
          return null;
        }
        return [header].concat(bodyRows);
      }

      function normalizePhenoBucketName(bucket) {
        const value = String(bucket || "").trim();
        if (!value) {
          return "Other";
        }
        if (value === "phenotypicFeatures") {
          return "Phenotypic Features";
        }
        if (value === "identifier") {
          return "Identifier";
        }
        if (value === "sex") {
          return "Sex";
        }
        return value.charAt(0).toUpperCase() + value.slice(1);
      }

      function getPhenoBucketStyle(bucket) {
        return PHENO_BUCKET_STYLES[bucket] || PHENO_BUCKET_STYLES.other;
      }

      function renderPhenoAlignmentPlaceholder(message) {
        phenoAlignmentDetailEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
      }

      function renderPhenoExplainPlaceholder(message) {
        phenoExplainDetailEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
      }

      function hasPhenoAlignmentFiles(files) {
        return Array.isArray(files) && files.some((file) => file.name === "alignment.target.csv");
      }

      function groupAlignmentItemsByBucket(items) {
        const groups = {};
        for (const item of Array.isArray(items) ? items : []) {
          const bucket = item.bucket || "other";
          if (!groups[bucket]) {
            groups[bucket] = [];
          }
          groups[bucket].push(item);
        }
        return Object.entries(groups).sort((left, right) => left[0].localeCompare(right[0]));
      }

      function renderAlignmentRows(entries) {
        return entries.map((entry) => {
          const bucket = entry.bucket || "other";
          const style = getPhenoBucketStyle(bucket);
          return `<tr>
            <td>
              <span class="alignment-bucket-pill" style="--bucket-bg:${style.bg};--bucket-ink:${style.ink};">
                <span class="alignment-swatch"></span>
                ${escapeHtml(normalizePhenoBucketName(bucket))}
              </span>
            </td>
            <td>
              <div class="alignment-label-cell">${escapeHtml(entry.label || "")}</div>
              <div class="alignment-path-cell">${escapeHtml(entry.json_path || "")}</div>
            </td>
          </tr>`;
        }).join("");
      }

      function renderAlignmentGroup(items, title) {
        const groups = groupAlignmentItemsByBucket(items);
        if (!groups.length) {
          return `<div class="empty">${escapeHtml(title)}: none.</div>`;
        }
        return `<div class="alignment-section">
          <h4>${escapeHtml(title)}</h4>
          <div class="alignment-group-table-wrap">
            <table class="alignment-group-table">
              <thead>
                <tr>
                  <th>Term Type</th>
                  <th>Matched Variable</th>
                </tr>
              </thead>
              <tbody>
                ${groups.map(([, entries]) => renderAlignmentRows(entries)).join("")}
              </tbody>
            </table>
          </div>
        </div>`;
      }

      function renderPhenoAlignmentDetail(payload) {
        const referenceId = payload.reference_id || "unknown";
        const targetId = payload.target_id || "unknown";
        const shared = Array.isArray(payload.shared) ? payload.shared : [];
        const referenceOnly = Array.isArray(payload.reference_only) ? payload.reference_only : [];
        const targetOnly = Array.isArray(payload.target_only) ? payload.target_only : [];
        phenoAlignmentDetailEl.innerHTML =
          `<div class="section-note">Reference <strong>${escapeHtml(referenceId)}</strong> compared to target <strong>${escapeHtml(targetId)}</strong>.</div>` +
          `<div class="alignment-summary">
            <span class="alignment-stat">Shared ${shared.length}</span>
            <span class="alignment-stat">Reference-only ${referenceOnly.length}</span>
            <span class="alignment-stat">Target-only ${targetOnly.length}</span>
          </div>` +
          renderAlignmentGroup(shared, "Matched Variables") +
          renderAlignmentGroup(referenceOnly, "Reference-Only Variables") +
          renderAlignmentGroup(targetOnly, "Target-Only Variables");
      }

      function renderPhenoExplainDetail(payload) {
        const matches = Array.isArray(payload.matches) ? payload.matches : [];
        if (!matches.length) {
          renderPhenoExplainPlaceholder("No explanation could be generated for this run.");
          return;
        }
        const targetId = payload.target_id || "unknown";
        const topN = String(payload.top_n || matches.length);
        const source = payload.source === "lm_studio"
          ? '<span class="query-chip query-chip-llm badge">LM-based</span>'
          : '<span class="query-chip query-chip-deterministic badge">Deterministic</span>';
        const llmReply = payload.llm_reply
          ? `<div class="query-section" style="margin-bottom:12px;"><h4>LLM Explanation</h4>${renderQueryReply(payload.llm_reply)}</div>`
          : "";
        phenoExplainDetailEl.innerHTML =
          `<div class="pheno-explain-header">
            <div class="pheno-explain-title-row">
              <div class="pheno-explain-title-block">
                <strong>Target ${escapeHtml(targetId)}</strong>
                <span>Top ${escapeHtml(topN)} matches from <code>rank.txt</code></span>
              </div>
              <div class="pheno-explain-meta">${source}</div>
            </div>
          </div>` +
          llmReply +
          `<div class="pheno-explain-match-grid">` +
          matches.map((match, index) => {
            const metrics = Object.entries(match.metrics || {})
              .filter(([, value]) => value !== "")
              .map(([key, value]) => `<span class="alignment-stat">${escapeHtml(key)} ${escapeHtml(String(value))}</span>`)
              .join("");
            const highlights = Array.isArray(match.metric_highlights) ? match.metric_highlights : [];
            const alignment = match.alignment || {};
            const shared = Array.isArray(alignment.top_shared_items) ? alignment.top_shared_items : [];
            const referenceOnly = Array.isArray(alignment.top_reference_only_items) ? alignment.top_reference_only_items : [];
            const targetOnly = Array.isArray(alignment.top_target_only_items) ? alignment.top_target_only_items : [];
            const renderLabelGroup = (title, items, toneClass) => {
              if (!items.length) {
                return "";
              }
              return `
                <div class="pheno-explain-group ${toneClass}">
                  <div class="pheno-explain-group-title">${escapeHtml(title)}</div>
                  <div class="pheno-explain-chip-wrap">
                    ${items.map((item) => {
                      const bucket = item.bucket || "other";
                      const style = getPhenoBucketStyle(bucket);
                      return `<span class="alignment-bucket-pill pheno-explain-chip" style="--bucket-bg:${style.bg};--bucket-ink:${style.ink};">
                        <span class="alignment-swatch"></span>
                        ${escapeHtml(item.label || "")}
                      </span>`;
                    }).join("")}
                  </div>
                </div>
              `;
            };
            return `
              <div class="pheno-explain-match-card">
                <div class="pheno-explain-match-head">
                  <div>
                    <div class="pheno-explain-match-rank">Match ${index + 1}</div>
                    <h4>${escapeHtml(match.reference_id || "Unknown match")}</h4>
                  </div>
                </div>
                <div class="alignment-summary">${metrics || '<span class="alignment-stat">No numeric metrics detected</span>'}</div>
                ${highlights.length ? `<ul class="pheno-explain-highlight-list">${highlights.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>` : ""}
                <div class="pheno-explain-groups">
                  ${renderLabelGroup("Shared variables", shared, "is-shared")}
                  ${renderLabelGroup("Match-only variables", referenceOnly, "is-reference")}
                  ${renderLabelGroup("Target-only variables", targetOnly, "is-target")}
                </div>
              </div>
            `;
          }).join("") +
          `</div>`;
      }

      async function explainPhenoResults() {
        if (!phenoRunState || !phenoRunState.jobId) {
          renderPhenoExplainPlaceholder("Run Pheno-Ranker first.");
          return;
        }
        if (phenoRunState.mode !== "patient") {
          renderPhenoExplainPlaceholder("Explain results currently supports patient-mode runs only.");
          return;
        }
        phenoExplainBtnEl.disabled = true;
        phenoExplainDetailEl.innerHTML = '<div class="empty">Explaining results...</div>';
        try {
          const response = await fetch(`/pheno-ranker/explain/${encodeURIComponent(phenoRunState.jobId)}?top_n=3`);
          if (!response.ok) {
            const error = await response.json();
            renderPhenoExplainPlaceholder(error.detail || "Unable to explain these results.");
            return;
          }
          const payload = await response.json();
          renderPhenoExplainDetail(payload);
        } catch (error) {
          renderPhenoExplainPlaceholder(error && error.message ? error.message : "Unable to explain these results.");
        } finally {
          phenoExplainBtnEl.disabled = false;
        }
      }

      async function explainPhenoResultsWithLlm() {
        if (!phenoRunState || !phenoRunState.jobId) {
          renderPhenoExplainPlaceholder("Run Pheno-Ranker first.");
          return;
        }
        if (phenoRunState.mode !== "patient") {
          renderPhenoExplainPlaceholder("Explain with LLM currently supports patient-mode runs only.");
          return;
        }
        phenoExplainLlmBtnEl.disabled = true;
        phenoExplainDetailEl.innerHTML = '<div class="empty">Explaining results with LM Studio...</div>';
        try {
          const response = await fetch(`/pheno-ranker/explain-llm/${encodeURIComponent(phenoRunState.jobId)}?top_n=3`);
          if (!response.ok) {
            const error = await response.json();
            renderPhenoExplainPlaceholder(error.detail || "Unable to explain these results with LM Studio.");
            return;
          }
          const payload = await response.json();
          renderPhenoExplainDetail(payload);
        } catch (error) {
          renderPhenoExplainPlaceholder(error && error.message ? error.message : "Unable to explain these results with LM Studio.");
        } finally {
          phenoExplainLlmBtnEl.disabled = false;
        }
      }

      async function loadPhenoAlignment(referenceId, targetId) {
        if (!phenoRunState || !phenoRunState.jobId || !phenoRunState.alignmentAvailable) {
          renderPhenoAlignmentPlaceholder("No alignment output is available for this run.");
          return;
        }
        const selectionKey = `${referenceId}::${targetId}`;
        phenoSelectedAlignmentKey = selectionKey;
        renderSortablePhenoTable();
        phenoAlignmentDetailEl.innerHTML = "<div class=\"empty\">Loading alignment details...</div>";
        try {
          const response = await fetch(`/pheno-ranker/alignment/${encodeURIComponent(phenoRunState.jobId)}?reference_id=${encodeURIComponent(referenceId)}&target_id=${encodeURIComponent(targetId)}`);
          if (!response.ok) {
            const error = await response.json();
            renderPhenoAlignmentPlaceholder(error.detail || "Alignment details are unavailable for this pair.");
            return;
          }
          const payload = await response.json();
          renderPhenoAlignmentDetail(payload);
        } catch (error) {
          renderPhenoAlignmentPlaceholder(error && error.message ? error.message : "Unable to load alignment details.");
        }
      }

      function inferPhenoColumnType(rows, columnIndex) {
        const values = rows.map((row) => row[columnIndex]).filter((value) => value !== "");
        if (!values.length) {
          return "text";
        }
        const numericValues = values.filter((value) => Number.isFinite(Number(value.replace(/,/g, ""))));
        return numericValues.length === values.length ? "number" : "text";
      }

      function comparePhenoCells(left, right, type, direction) {
        if (type === "number") {
          const leftValue = Number(String(left || "").replace(/,/g, ""));
          const rightValue = Number(String(right || "").replace(/,/g, ""));
          return direction === "asc" ? leftValue - rightValue : rightValue - leftValue;
        }
        const compared = String(left || "").localeCompare(String(right || ""), undefined, { numeric: true, sensitivity: "base" });
        return direction === "asc" ? compared : -compared;
      }

      function renderSortablePhenoTable() {
        if (!phenoTableState || !Array.isArray(phenoTableState.headers) || !Array.isArray(phenoTableState.rows)) {
          phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
          return;
        }
        const { headers, rows, sortIndex, sortDirection, sourceName, interactive, referenceColumnIndex, targetColumnIndex } = phenoTableState;
        const type = inferPhenoColumnType(rows, sortIndex);
        const sortedRows = rows.slice().sort((left, right) => comparePhenoCells(left[sortIndex], right[sortIndex], type, sortDirection));
        const note = interactive
          ? `${sourceName} loaded as TSV. Click a column header to sort. Click one result row to inspect matched variables for that pair.`
          : `${sourceName} loaded as TSV. Click a column header to sort.`;
        phenoOutputPreviewEl.innerHTML =
          `<div class="section-note">${escapeHtml(note)}</div>` +
          `<div class="pheno-output-table-wrap"><table class="pheno-output-table"><thead><tr>${
            headers.map((cell, index) => {
              const active = index === sortIndex;
              const arrow = active ? (sortDirection === "asc" ? " ▲" : " ▼") : "";
              return `<th><button type="button" class="pheno-sort-btn" data-pheno-sort-index="${index}" data-active="${active ? "true" : "false"}">${escapeHtml(cell)}${arrow}</button></th>`;
            }).join("")
          }</tr></thead><tbody>${
            sortedRows.map((row) => {
              const referenceId = interactive && referenceColumnIndex >= 0 ? row[referenceColumnIndex] : "";
              const targetId = interactive && targetColumnIndex >= 0 ? row[targetColumnIndex] : "";
              const selectionKey = `${referenceId}::${targetId}`;
              const isSelected = interactive && phenoSelectedAlignmentKey === selectionKey;
              const rowClass = interactive ? ` class="is-clickable${isSelected ? " is-selected" : ""}"` : "";
              const attrs = interactive
                ? ` data-pheno-reference-id="${escapeHtml(referenceId)}" data-pheno-target-id="${escapeHtml(targetId)}"`
                : "";
              return `<tr${rowClass}${attrs}>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`;
            }).join("")
          }</tbody></table></div>`;
      }

      function setPhenoTable(rows, sourceName, options) {
        if (!Array.isArray(rows) || rows.length < 2) {
          phenoTableState = null;
          return;
        }
        const tableOptions = options || {};
        phenoTableState = {
          headers: rows[0],
          rows: rows.slice(1),
          sortIndex: 0,
          sortDirection: "asc",
          sourceName,
          interactive: Boolean(tableOptions.interactive),
          referenceColumnIndex: Number.isInteger(tableOptions.referenceColumnIndex) ? tableOptions.referenceColumnIndex : -1,
          targetColumnIndex: Number.isInteger(tableOptions.targetColumnIndex) ? tableOptions.targetColumnIndex : -1,
        };
        renderSortablePhenoTable();
      }

      async function renderPhenoOutputPreview(files) {
        const items = Array.isArray(files) ? files : [];
        const preferred = items.find((file) => file.name === "rank.txt") || items.find((file) => file.name === "matrix.txt");
        if (!preferred) {
          phenoTableState = null;
          phenoOutputPreviewEl.innerHTML = '<div class="empty">No rank or matrix output file available for preview.</div>';
          return;
        }
        try {
          const response = await fetch(preferred.url);
          if (!response.ok) {
            phenoTableState = null;
            phenoOutputPreviewEl.innerHTML = '<div class="empty">Unable to load output preview.</div>';
            return;
          }
          const text = await response.text();
          if (preferred.name === "rank.txt") {
            const rows = parseTsvLines(text);
            if (rows && rows.length >= 2) {
              const header = rows[0];
              const referenceColumnIndex = header.indexOf("REFERENCE(ID)");
              const targetColumnIndex = header.indexOf("TARGET(ID)");
              setPhenoTable(rows, preferred.name, {
                interactive: hasPhenoAlignmentFiles(items) && referenceColumnIndex >= 0 && targetColumnIndex >= 0,
                referenceColumnIndex,
                targetColumnIndex,
              });
              return;
            }
          }
          phenoTableState = null;
          if (preferred.name === "matrix.txt") {
            const previewLines = text.split("\r\n").join("\n").split("\n").slice(0, 20).join("\n");
            phenoOutputPreviewEl.innerHTML =
              '<div class="section-note">Matrix preview is intentionally limited. Use the file link or the plot outputs for full cohort inspection.</div>' +
              `<pre>${escapeHtml(previewLines)}</pre>`;
            return;
          }
          phenoOutputPreviewEl.innerHTML = `<pre>${escapeHtml(text)}</pre>`;
        } catch (error) {
          phenoTableState = null;
          phenoOutputPreviewEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : "Unable to load output preview.")}</div>`;
        }
      }

      function renderPhenoPreviews(files) {
        const images = Array.isArray(files) ? files.filter((file) => file.name.endsWith(".png")) : [];
        if (!images.length) {
          phenoPreviewsEl.innerHTML = '<div class="empty">No plot previews available.</div>';
          return;
        }
        phenoPreviewsEl.innerHTML = images
          .map((file) => `<div class="pheno-preview-card"><strong>${escapeHtml(file.name)}</strong><img src="${file.url}" alt="${escapeHtml(file.name)}"></div>`)
          .join("");
      }

      async function runPhenoRanker() {
        if (phenoInFlight) {
          return;
        }
        const scopeIds = getCurrentScopeIds();
        if (phenoModeEl.value === "patient") {
          if (!phenoPatientIdEl.value.trim() && scopeIds.length === 1) {
            phenoPatientIdEl.value = scopeIds[0];
          }
          if (scopeIds.length > 1) {
            phenoStatusEl.textContent = "Patient mode expects exactly one patient in scope, or one explicit Patient ID.";
            return;
          }
          if (!phenoPatientIdEl.value.trim()) {
            phenoStatusEl.textContent = "Enter a patient ID for patient mode, or set the scope to exactly one patient.";
            return;
          }
        }
        if (phenoActionEl.value === "extract" && !phenoSelectedPatientIdsEl.value.trim()) {
          phenoStatusEl.textContent = "Define a non-empty scope for extraction mode.";
          return;
        }
        if (phenoRankerPatientIds.length) {
          const invalidScopeIds = scopeIds.filter((patientId) => !phenoRankerPatientIds.includes(patientId));
          if (invalidScopeIds.length) {
            phenoStatusEl.textContent = `Scope contains IDs not present in the current Pheno-Ranker reference: ${invalidScopeIds.join(", ")}.`;
            return;
          }
        }

        phenoInFlight = true;
        phenoRunBtnEl.disabled = true;
        phenoStatusEl.className = "pheno-status loading";
        phenoStatusEl.textContent = "Running Pheno-Ranker...";
        phenoCommandEl.textContent = "Preparing command...";
        phenoFilesEl.innerHTML = '<div class="empty">Waiting for Pheno-Ranker outputs.</div>';
        phenoRunState = null;
        phenoSelectedAlignmentKey = "";
        phenoTableState = null;
        phenoOutputDetailsEl.open = phenoModeEl.value === "patient";
        phenoOutputPreviewEl.innerHTML = '<div class="empty">Waiting for output preview.</div>';
        renderPhenoAlignmentPlaceholder("Waiting for alignment details.");
        phenoLogsEl.textContent = "Waiting for logs...";
        phenoPreviewsEl.innerHTML = '<div class="empty">Waiting for plot previews.</div>';
        await nextFrame();

        try {
          const response = await fetch("/pheno-ranker/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: phenoActionEl.value,
              mode: phenoModeEl.value,
              data_dir: dataDirEl.value.trim(),
              patient_id: phenoPatientIdEl.value.trim(),
              selected_patient_ids: phenoSelectedPatientIdsEl.value.trim(),
              include_terms: parsePhenoTermsInput(phenoIncludeTermsEl.value),
              exclude_terms: parsePhenoTermsInput(phenoExcludeTermsEl.value),
              similarity_metric_cohort: phenoSimilarityMetricEl.value,
              sort_by: phenoSortByEl.value,
              max_out: Number(phenoMaxOutEl.value || 10),
              align: phenoAlignEl.checked,
              render_heatmap: phenoRenderHeatmapEl.checked,
              render_mds: phenoRenderMdsEl.checked,
            }),
          });

          if (!response.ok) {
            const error = await response.json();
            const detailObject = error.detail && typeof error.detail === "object" ? error.detail : null;
            const detail = detailObject ? JSON.stringify(detailObject, null, 2) : String(error.detail || "Pheno-Ranker request failed.");
            phenoStatusEl.className = "pheno-status";
            phenoStatusEl.textContent = "Pheno-Ranker failed.";
            phenoCommandEl.textContent = detailObject && detailObject.command ? detailObject.command : "Command failed before completion.";
            phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
            phenoLogsEl.textContent = detail;
            phenoFilesEl.innerHTML = '<div class="empty">No output files available.</div>';
            phenoPreviewsEl.innerHTML = '<div class="empty">No plot previews available.</div>';
            return;
          }

          const payload = await response.json();
          phenoRunState = {
            jobId: payload.job_id,
            mode: payload.mode,
            alignmentAvailable: hasPhenoAlignmentFiles(payload.files),
          };
          phenoOutputDetailsEl.open = payload.mode === "patient";
          phenoStatusEl.className = "pheno-status";
          phenoStatusEl.textContent = `Completed ${payload.mode} run ${payload.job_id}.`;
          phenoCommandEl.textContent = [
            ...(Array.isArray(payload.pre_commands) ? payload.pre_commands.map((item, index) => `Preparation step ${index + 1}:\n${item}`) : []),
            payload.command ? `Final run:\n${payload.command}` : "No command returned.",
          ].join("\n\n");
          phenoLogsEl.textContent = [payload.stderr || "", ...(payload.plots || []).map((item) => `${item.script}\nstdout:\n${item.stdout}\nstderr:\n${item.stderr}`)].filter(Boolean).join("\n\n") || "No diagnostic logs.";
          renderPhenoFiles(payload.files);
          await renderPhenoOutputPreview(payload.files);
          if (payload.mode === "patient" && phenoRunState.alignmentAvailable) {
            renderPhenoAlignmentPlaceholder("Alignment output is ready. Click one row in rank.txt to inspect matched variables for that pair.");
          } else if (payload.mode === "patient") {
            renderPhenoAlignmentPlaceholder("This patient-mode run did not generate alignment output. Alignment is enabled by default for patient mode, so this usually means it was turned off manually.");
          } else {
            renderPhenoAlignmentPlaceholder("Alignment details are only available for patient-mode runs with --align.");
          }
          if (payload.mode === "patient") {
            renderPhenoExplainPlaceholder("Patient-mode results are ready. Click Explain results to summarize the top matches.");
          } else {
            renderPhenoExplainPlaceholder("Explain results currently focuses on patient-mode rank.txt outputs.");
          }
          renderPhenoPreviews(payload.files);
        } catch (error) {
          phenoStatusEl.className = "pheno-status";
          phenoStatusEl.textContent = "Network error while running Pheno-Ranker.";
          phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
          renderPhenoAlignmentPlaceholder("Alignment details are unavailable because the run failed.");
          renderPhenoExplainPlaceholder("Explain results are unavailable because the run failed.");
          phenoLogsEl.textContent = error && error.message ? error.message : "Unexpected request failure.";
        } finally {
          phenoInFlight = false;
          phenoRunBtnEl.disabled = false;
        }
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
          await loadPhenoRankerPatientIds();
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
        queryReasonEl.innerHTML = "<p>Waiting for the response and its supporting context.</p>";
        queryMetaEl.innerHTML = "";
        queryActionsEl.innerHTML = "";
        latestQueryPatientIds = [];
        queryFollowupsEl.innerHTML = "";
        await nextFrame();

        try {
          const response = await fetch(`/query?data_dir=${dataDir}&q=${encodeURIComponent(question)}`);
          if (!response.ok) {
            const error = await response.json();
            queryReplyEl.innerHTML = `<p>${escapeHtml(error.detail)}</p>`;
            queryReasonEl.innerHTML = "<p>The request reached the API but returned an error response.</p>";
            queryDataEl.textContent = "";
            queryDetailsEl.open = false;
            queryActionsEl.innerHTML = "";
            queryStatusEl.className = "query-status";
            queryStatusEl.textContent = "Query failed.";
            return;
          }
          const payload = await response.json();
          queryReplyEl.innerHTML = renderQueryReply(payload);
          renderQueryMeta(payload);
          renderQueryReason(payload);
          renderQueryActions(payload);
          renderFollowupButtons(payload.data && payload.data.follow_up_suggestions);
          queryDataEl.textContent = JSON.stringify(payload.data, null, 2);
          queryDetailsEl.open = false;
          queryStatusEl.className = "query-status";
          queryStatusEl.textContent = "Done.";
        } catch (error) {
          queryReplyEl.innerHTML = `<p>${escapeHtml(error && error.message ? error.message : "Request failed.")}</p>`;
          queryReasonEl.innerHTML = "<p>The request failed before a valid response payload reached the UI.</p>";
          queryDataEl.textContent = "";
          queryDetailsEl.open = false;
          queryActionsEl.innerHTML = "";
          latestQueryPatientIds = [];
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
      phenoTabBtnEl.addEventListener("click", () => setActiveTab("pheno"));
      phenoPlanBtnEl.addEventListener("click", planPhenoRanker);
      phenoPlanRunBtnEl.addEventListener("click", planAndRunPhenoRanker);
      phenoRunBtnEl.addEventListener("click", runPhenoRanker);
      phenoExplainBtnEl.addEventListener("click", explainPhenoResults);
      phenoExplainLlmBtnEl.addEventListener("click", explainPhenoResultsWithLlm);
      phenoModeEl.addEventListener("change", updatePhenoMode);
      phenoActionEl.addEventListener("change", updatePhenoMode);
      phenoSelectedPatientIdsEl.addEventListener("input", renderSelectedPatientIdsSummary);
      window.__patientNavigatorLoadPatients = loadPatients;
      window.__patientNavigatorAskQuery = askQuery;
      patientsEl.addEventListener("click", (event) => {
        const card = event.target.closest(".patient-card");
        if (!card || !patientsEl.contains(card)) {
          return;
        }
        loadPatient(card.dataset.patientId);
      });
      queryExamplesEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-prompt]");
        if (!button || !queryExamplesEl.contains(button)) {
          return;
        }
        questionEl.value = button.dataset.prompt;
        questionEl.focus();
      });
      queryFollowupsEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-prompt]");
        if (!button || !queryFollowupsEl.contains(button)) {
          return;
        }
        questionEl.value = button.dataset.prompt;
        questionEl.focus();
      });
      phenoExamplesEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-pheno-prompt]");
        if (!button || !phenoExamplesEl.contains(button)) {
          return;
        }
        phenoPromptEl.value = button.dataset.phenoPrompt;
        phenoPromptEl.focus();
      });
      queryActionsEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-query-action]");
        if (!button || !queryActionsEl.contains(button)) {
          return;
        }
        if (button.dataset.queryAction === "use-pheno") {
          sendPatientIdsToPhenoRanker();
          return;
        }
        if (button.dataset.queryAction === "copy-ids") {
          copyPatientIdsFromQuery();
        }
      });
      phenoOutputPreviewEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-pheno-sort-index]");
        if (button && phenoOutputPreviewEl.contains(button) && phenoTableState) {
          const nextIndex = Number(button.dataset.phenoSortIndex);
          if (!Number.isInteger(nextIndex)) {
            return;
          }
          if (phenoTableState.sortIndex === nextIndex) {
            phenoTableState.sortDirection = phenoTableState.sortDirection === "asc" ? "desc" : "asc";
          } else {
            phenoTableState.sortIndex = nextIndex;
            phenoTableState.sortDirection = inferPhenoColumnType(phenoTableState.rows, nextIndex) === "number" ? "desc" : "asc";
          }
          renderSortablePhenoTable();
          return;
        }
        const row = event.target.closest("[data-pheno-reference-id]");
        if (!row || !phenoOutputPreviewEl.contains(row) || !phenoTableState || !phenoTableState.interactive) {
          return;
        }
        loadPhenoAlignment(row.dataset.phenoReferenceId || "", row.dataset.phenoTargetId || "");
      });
      questionEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          askQuery();
        }
      });
      patientSearchEl.addEventListener("input", () => renderPatientList(filterPatients(patientSearchEl.value)));
      updatePhenoMode();
      renderSelectedPatientIdsSummary();
      loadPhenoRankerPatientIds();
      loadLmStatus();
      renderPhenoAlignmentPlaceholder("Run patient mode, then click one row in rank.txt to inspect matched variables for that pair.");
      renderPhenoExplainPlaceholder("Run patient mode, then click Explain results to summarize the top matches from rank.txt.");
    
