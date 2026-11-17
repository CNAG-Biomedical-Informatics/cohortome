import {showDatasetAbout} from './react/ui.js';
// Deliberately limited Markdown: no HTML, images, embeds or local-file links.
export function documentMarkup(text, escapeHtml) {
  const inline = value => {
    const tokens = String(value).split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^\s)]+\))/g);
    return tokens.map(token => {
      if (token.startsWith('`') && token.endsWith('`')) return `<code>${escapeHtml(token.slice(1, -1))}</code>`;
      if (token.startsWith('**') && token.endsWith('**')) return `<strong>${escapeHtml(token.slice(2, -2))}</strong>`;
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        if (link[2] === 'TERMS.md' || link[2] === 'README.md') return `<button type="button" class="dataset-about-link" data-document="${link[2]}">${escapeHtml(link[1])}</button>`;
        if (/^https?:\/\//i.test(link[2])) return `<a href="${escapeHtml(link[2])}" target="_blank" rel="noopener noreferrer">${escapeHtml(link[1])}</a>`;
        return escapeHtml(link[1]);
      }
      return escapeHtml(token);
    }).join('');
  };
  const lines = String(text).replace(/\r/g, '').split('\n');
  const output = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    if (line.startsWith('```')) {
      const code = [];
      while (++i < lines.length && !lines[i].startsWith('```')) code.push(lines[i]);
      output.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
    } else if (/^#{1,6} /.test(line)) {
      output.push(`<h3>${inline(line.replace(/^#+ /, ''))}</h3>`);
    } else if (/^\s*[-*] /.test(line)) {
      const items = [line];
      while (/^\s*[-*] /.test(lines[i + 1] || '')) items.push(lines[++i]);
      output.push(`<ul>${items.map(s => `<li>${inline(s.replace(/^\s*[-*] /, ''))}</li>`).join('')}</ul>`);
    } else if (line.startsWith('|') && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
      const cells = s => s.trim().replace(/^\||\|$/g, '').split('|');
      const headers = cells(line); i++;
      const rows = [];
      while ((lines[i + 1] || '').startsWith('|')) rows.push(cells(lines[++i]));
      output.push(`<div class="dataset-about-table"><table><thead><tr>${headers.map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(c => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
    } else {
      const paragraph = [line];
      while (lines[i + 1]?.trim() && !/^(#|```|\||\s*[-*] )/.test(lines[i + 1])) paragraph.push(lines[++i]);
      output.push(`<p>${inline(paragraph.join(' '))}</p>`);
    }
  }
  return output.join('');
}

export function openDatasetAbout(datasetId, escapeHtml) {
  showDatasetAbout(datasetId,text=>documentMarkup(text,escapeHtml));
}
