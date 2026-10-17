// Display labels never replace execution keys or plot-selection IDs.
export function identityKey(datasetId, kind, sourceId) {
  if (!datasetId || !sourceId || !['patient', 'sample'].includes(kind)) throw new Error('Incomplete dataset identity.');
  const bytes = new TextEncoder().encode(JSON.stringify([datasetId, kind, sourceId]));
  return 'cohortome-v1-' + btoa(Array.from(bytes, b => String.fromCharCode(b)).join('')).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

export function decodeIdentity(value) {
  const raw = String(value || "");
  if (!raw.startsWith("cohortome-v1-")) return null;
  try {
    const token = raw.slice("cohortome-v1-".length).replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(token), (char) => char.charCodeAt(0));
    const parts = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!Array.isArray(parts) || parts.length !== 3 || !parts.every((part) => typeof part === "string" && part)) return null;
    if (!["patient", "sample"].includes(parts[1])) return null;
    return { datasetId: parts[0], kind: parts[1], sourceId: parts[2] };
  } catch {
    return null;
  }
}

export function displayIdentity(value, showDataset = true) {
  const raw = String(value || "");
  // Pheno-Ranker labels its comparison groups independently of source identity.
  const group = raw.match(/^(C\d+_)(cohortome-v1-.+)$/);
  const identity = decodeIdentity(group ? group[2] : raw);
  if (!identity) return raw;
  const label = showDataset ? `${identity.datasetId} · ${identity.sourceId}` : identity.sourceId;
  return group ? `${group[1]}${label}` : label;
}
