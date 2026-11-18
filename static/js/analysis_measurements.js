import {createMeasurementView} from './react/ui.js';
// Clinical inputs share the runners' scope and date rules; no LLM is needed.
export function createMeasurementSelector({ host, state, getContext, onChange }) {
  const panel = document.createElement("div");
  panel.hidden = true;
  host.appendChild(panel);
  let key = "", options = [], loading = false, error = "";
  let minimumDatedPatients = 1;
  const view=createMeasurementView(panel,value=>{
    state.analysisMeasurement = value;
    onChange();
  });
  function status() {
    const selected = options.find((entry) => entry.measure === state.analysisMeasurement);
    if (loading) return { complete: false, detail: "Checking measurement coverage…" };
    if (error) return { complete: false, detail: error };
    if (!selected) return { complete: false, detail: options.length ? "Choose a measurement available in this scope." : "No numeric clinical measurements in this scope." };
    if (!selected.compatible_units) return { complete: false, detail: "Inconsistent units; harmonize them before analysis." };
    if (selected.groups.some((group) => group.dated_patient_count < minimumDatedPatients)) return { complete: false, detail: `At least ${minimumDatedPatients} patients with dated values are required in each group.` };
    const detail = selected.groups.map((group, index) => `${selected.groups.length > 1 ? `Cohort ${index ? "B" : "A"}` : "Scope"}: ${group.patient_count} patients with values; ${group.repeated_patient_count} with values on two or more dates.`).join(" ");
    const complete = selected.groups.every((group) => group.repeated_patient_count > 0);
    return { complete, detail: detail + (complete ? " Missing observations are not imputed." : " Repeated dated observations are required in each group.") };
  }
  function render(required, minimum = 1) {
    minimumDatedPatients = minimum;
    panel.hidden = !required;
    if (!required) return;
    const context = getContext();
    const nextKey = JSON.stringify(context);
    if (key !== nextKey) {
      key = nextKey; options = []; error = ""; loading = true;
      fetch("/analysis/measurements", { method: "POST", headers: { "Content-Type": "application/json" }, body: nextKey })
        .then(async (response) => {
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.detail || "Cannot check measurements.");
          if (key !== nextKey) return;
          options = payload.measurements || [];
        }).catch((exc) => { if (key === nextKey) error = exc.message || "Cannot check measurements."; })
        .finally(() => { if (key === nextKey) { loading = false; onChange(false); } });
    }
    view.render({options,value:state.analysisMeasurement || "",loading,detail:status().detail});
  }
  return { render, status };
}
