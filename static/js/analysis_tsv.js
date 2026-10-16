// R write.table output may quote headers, IDs, tabs and embedded newlines.
export function parseAnalysisTsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  const input = String(text || "").replace(/^\uFEFF/, "");
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (c === '"') {
      if (quoted && input[i + 1] === '"') { cell += '"'; i++; }
      else if (quoted || cell === "") quoted = !quoted;
      else cell += c;
    } else if (!quoted && c === "\t") {
      row.push(cell); cell = "";
    } else if (!quoted && (c === "\n" || c === "\r")) {
      if (c === "\r" && input[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some(value => value.trim())) rows.push(row);
      row = []; cell = "";
    } else cell += c;
  }
  if (quoted) throw new Error("Incomplete quoted field in plot data.");
  row.push(cell);
  if (row.some(value => value.trim())) rows.push(row);
  const headers = (rows.shift() || []).map(value => value.trim());
  return rows.map(values => Object.fromEntries(headers.map((header, i) => [header, values[i] ?? ""])));
}
