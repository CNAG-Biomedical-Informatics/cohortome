// Presentation-only normalization: do not infer sex from codes or change source data.
export function clinicalSexCounts(counts = {}) {
  const result = new Map();
  for (const [raw, value] of Object.entries(counts)) {
    const trimmed = raw.trim();
    const known = {male:'Male', female:'Female', unknown:'Unknown'};
    const label = known[trimmed.toLowerCase()] || trimmed || 'Unknown';
    const count = Number(value);
    if (Number.isFinite(count) && count > 0) result.set(label, (result.get(label) || 0) + count);
  }
  return [...result].sort(([a, n], [b, m]) =>
    (a === 'Unknown') - (b === 'Unknown') || m - n || a.localeCompare(b));
}

// Only catalogue identities establish comparability, never matching display labels.
export function clinicalMeasurements(datasets = []) {
  const fields = new Map();
  for (const dataset of datasets) {
    for (const row of dataset.rows || []) {
      if (row.kind !== 'number' || !row.field_id) continue;
      if (!fields.has(row.field_id)) fields.set(row.field_id, {id:row.field_id,
        label:row.label, unit:row.unit, sources:[]});
      fields.get(row.field_id).sources.push({dataset, row});
    }
  }
  return [...fields.values()].sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
}
