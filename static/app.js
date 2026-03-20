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
      const queryReasonEl = document.getElementById("queryReason");
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
      const phenoPlanBtnEl = document.getElementById("phenoPlanBtn");
      const phenoPlanRunBtnEl = document.getElementById("phenoPlanRunBtn");
      const phenoPlanStatusEl = document.getElementById("phenoPlanStatus");
      const phenoPlanEl = document.getElementById("phenoPlan");
      const phenoPlanReasoningEl = document.getElementById("phenoPlanReasoning");
      const phenoPatientFieldEl = document.getElementById("phenoPatientField");
      const phenoPatientIdEl = document.getElementById("phenoPatientId");
      const phenoSelectedPatientIdsEl = document.getElementById("phenoSelectedPatientIds");
      const phenoIncludeTermsEl = document.getElementById("phenoIncludeTerms");
      const phenoExcludeTermsEl = document.getElementById("phenoExcludeTerms");
      const phenoSimilarityMetricEl = document.getElementById("phenoSimilarityMetric");
      const phenoSortByEl = document.getElementById("phenoSortBy");
      const phenoMaxOutFieldEl = document.getElementById("phenoMaxOutField");
      const phenoMaxOutEl = document.getElementById("phenoMaxOut");
      const phenoRenderHeatmapEl = document.getElementById("phenoRenderHeatmap");
      const phenoRenderMdsEl = document.getElementById("phenoRenderMds");
      const phenoPlotChecksEl = document.getElementById("phenoPlotChecks");
      const phenoRunBtnEl = document.getElementById("phenoRunBtn");
      const phenoStatusEl = document.getElementById("phenoStatus");
      const phenoCommandEl = document.getElementById("phenoCommand");
      const phenoFilesEl = document.getElementById("phenoFiles");
      const phenoOutputPreviewEl = document.getElementById("phenoOutputPreview");
      const phenoLogsEl = document.getElementById("phenoLogs");
      const phenoPreviewsEl = document.getElementById("phenoPreviews");
      const MAX_VISIBLE_PATIENTS = 80;
      let selectedPatientId = null;
      let currentPatients = [];
      let queryInFlight = false;
      let loadInFlight = false;
      let phenoInFlight = false;
      let phenoPlanInFlight = false;
      let phenoTableState = null;

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

      function renderQueryReply(value) {
        const lines = String(value || "").split("\\r\\n").join("\\n").split("\\n");
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
          blocks.push(`<pre><code>${escapeHtml(codeLines.join("\\n"))}</code></pre>`);
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

      function nextFrame() {
        return new Promise((resolve) => {
          window.requestAnimationFrame(() => resolve());
        });
      }

      function updatePhenoMode() {
        const patientMode = phenoModeEl.value === "patient";
        const extractMode = phenoActionEl.value === "extract";
        phenoPatientFieldEl.classList.toggle("is-hidden", !patientMode || extractMode);
        phenoMaxOutFieldEl.classList.toggle("is-hidden", !patientMode || extractMode);
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

      function applyPhenoPlan(plan) {
        const normalized = plan || {};
        phenoActionEl.value = normalized.action || "compare";
        phenoModeEl.value = normalized.mode || "cohort";
        phenoPatientIdEl.value = normalized.patient_id || "";
        phenoSelectedPatientIdsEl.value = normalized.selected_patient_ids || "";
        phenoIncludeTermsEl.value = Array.isArray(normalized.include_terms) ? normalized.include_terms.join(",") : (normalized.include_terms || "");
        phenoExcludeTermsEl.value = Array.isArray(normalized.exclude_terms) ? normalized.exclude_terms.join(",") : (normalized.exclude_terms || "");
        phenoSimilarityMetricEl.value = normalized.similarity_metric_cohort || "";
        phenoSortByEl.value = normalized.sort_by || "";
        phenoMaxOutEl.value = Number(normalized.max_out || 10);
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
            }),
          });
          if (!response.ok) {
            const error = await response.json();
            const detail = error.detail && typeof error.detail === "object" ? JSON.stringify(error.detail, null, 2) : String(error.detail || "Planner request failed.");
            phenoPlanStatusEl.className = "pheno-status";
            phenoPlanStatusEl.textContent = "Planner failed.";
            phenoPlanEl.textContent = detail;
            renderPhenoPlanReasoning([]);
            return null;
          }
          const payload = await response.json();
          applyPhenoPlan(payload.plan || {});
          phenoPlanEl.textContent = JSON.stringify(compactPhenoPlan(payload.plan || {}), null, 2);
          renderPhenoPlanReasoning(payload.reasoning || []);
          phenoPlanStatusEl.className = "pheno-status";
          phenoPlanStatusEl.textContent = `Planner ready (${payload.source || "deterministic"}). Review the interpreted plan, then run it.`;
          return payload;
        } catch (error) {
          phenoPlanStatusEl.className = "pheno-status";
          phenoPlanStatusEl.textContent = "Planner request failed.";
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
        const lines = String(text || "").split("\\r\\n").join("\\n").split("\\n").filter((line) => line.trim() && line.includes("\\t"));
        if (!lines.length) {
          return null;
        }
        const header = lines[0].split("\\t").map((cell) => cell.trim());
        if (header.length < 2) {
          return null;
        }
        const bodyRows = lines.slice(1)
          .map((line) => line.split("\\t").map((cell) => cell.trim()))
          .filter((cells) => cells.length === header.length);
        if (!bodyRows.length) {
          return null;
        }
        return [header].concat(bodyRows);
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
        const { headers, rows, sortIndex, sortDirection, sourceName } = phenoTableState;
        const type = inferPhenoColumnType(rows, sortIndex);
        const sortedRows = rows.slice().sort((left, right) => comparePhenoCells(left[sortIndex], right[sortIndex], type, sortDirection));
        phenoOutputPreviewEl.innerHTML =
          `<div class="section-note">${escapeHtml(sourceName)} loaded as TSV. Click a column header to sort.</div>` +
          `<div class="pheno-output-table-wrap"><table class="pheno-output-table"><thead><tr>${
            headers.map((cell, index) => {
              const active = index === sortIndex;
              const arrow = active ? (sortDirection === "asc" ? " ▲" : " ▼") : "";
              return `<th><button type="button" class="pheno-sort-btn" data-pheno-sort-index="${index}" data-active="${active ? "true" : "false"}">${escapeHtml(cell)}${arrow}</button></th>`;
            }).join("")
          }</tr></thead><tbody>${
            sortedRows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")
          }</tbody></table></div>`;
      }

      function setPhenoTable(rows, sourceName) {
        if (!Array.isArray(rows) || rows.length < 2) {
          phenoTableState = null;
          return;
        }
        phenoTableState = {
          headers: rows[0],
          rows: rows.slice(1),
          sortIndex: 0,
          sortDirection: "asc",
          sourceName,
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
              setPhenoTable(rows, preferred.name);
              return;
            }
          }
          phenoTableState = null;
          if (preferred.name === "matrix.txt") {
            const previewLines = text.split("\\r\\n").join("\\n").split("\\n").slice(0, 20).join("\\n");
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
        phenoPreviewsEl.innerHTML = images.map((file) => `<div><strong>${escapeHtml(file.name)}</strong><img src="${file.url}" alt="${escapeHtml(file.name)}"></div>`).join("");
      }

      async function runPhenoRanker() {
        if (phenoInFlight) {
          return;
        }
        if (phenoModeEl.value === "patient" && !phenoPatientIdEl.value.trim()) {
          phenoStatusEl.textContent = "Enter a patient ID for patient mode.";
          return;
        }
        if (phenoActionEl.value === "extract" && !phenoSelectedPatientIdsEl.value.trim()) {
          phenoStatusEl.textContent = "Enter one or more selected patient IDs for extraction mode.";
          return;
        }

        phenoInFlight = true;
        phenoRunBtnEl.disabled = true;
        phenoStatusEl.className = "pheno-status loading";
        phenoStatusEl.textContent = "Running Pheno-Ranker...";
        phenoCommandEl.textContent = "Preparing command...";
        phenoFilesEl.innerHTML = '<div class="empty">Waiting for Pheno-Ranker outputs.</div>';
        phenoTableState = null;
        phenoOutputPreviewEl.innerHTML = '<div class="empty">Waiting for output preview.</div>';
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
          phenoStatusEl.className = "pheno-status";
          phenoStatusEl.textContent = `Completed ${payload.mode} run ${payload.job_id}.`;
          phenoCommandEl.textContent = payload.command || "No command returned.";
          phenoLogsEl.textContent = [payload.stderr || "", ...(payload.plots || []).map((item) => `${item.script}\\nstdout:\\n${item.stdout}\\nstderr:\\n${item.stderr}`)].filter(Boolean).join("\\n\\n") || "No diagnostic logs.";
          renderPhenoFiles(payload.files);
          await renderPhenoOutputPreview(payload.files);
          renderPhenoPreviews(payload.files);
        } catch (error) {
          phenoStatusEl.className = "pheno-status";
          phenoStatusEl.textContent = "Network error while running Pheno-Ranker.";
          phenoOutputPreviewEl.innerHTML = '<div class="empty">No output preview available.</div>';
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
            queryStatusEl.className = "query-status";
            queryStatusEl.textContent = "Query failed.";
            return;
          }
          const payload = await response.json();
          queryReplyEl.innerHTML = renderQueryReply(payload.reply);
          renderQueryMeta(payload);
          renderQueryReason(payload);
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
      phenoModeEl.addEventListener("change", updatePhenoMode);
      phenoActionEl.addEventListener("change", updatePhenoMode);
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
      phenoOutputPreviewEl.addEventListener("click", (event) => {
        const button = event.target.closest("[data-pheno-sort-index]");
        if (!button || !phenoOutputPreviewEl.contains(button) || !phenoTableState) {
          return;
        }
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
      });
      questionEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          askQuery();
        }
      });
      patientSearchEl.addEventListener("input", () => renderPatientList(filterPatients(patientSearchEl.value)));
      updatePhenoMode();
    
