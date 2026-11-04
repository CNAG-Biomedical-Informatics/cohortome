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

export async function openDatasetAbout(datasetId, escapeHtml) {
  const previousFocus = document.activeElement;
  const controller = new AbortController();
  const dialog = document.createElement('dialog');
  dialog.className = 'dataset-about-dialog';
  dialog.setAttribute('aria-labelledby', 'dataset-about-title');
  dialog.innerHTML = `<header><div><small>About this dataset</small><h2 id="dataset-about-title">Loading…</h2></div><button type="button" class="query-chip secondary-btn" data-close aria-label="Close about this dataset">Close</button></header><p data-description></p><nav aria-label="Dataset documentation"></nav><div class="dataset-about-content" role="region" aria-label="Dataset documentation content" tabindex="0"></div><p role="status" aria-live="polite"></p>`;
  document.body.append(dialog);
  dialog.querySelector('[data-close]').onclick = () => dialog.close();
  dialog.addEventListener('close', () => { controller.abort(); dialog.remove(); previousFocus?.focus(); });
  dialog.showModal();
  const status = dialog.querySelector('[role=status]');
  status.textContent = 'Loading dataset documentation…';
  try {
    const response = await fetch(`/datasets/${encodeURIComponent(datasetId)}/about`, {signal: controller.signal});
    if (!response.ok) throw new Error('Unable to load dataset documentation. Close this panel and try again.');
    const data = await response.json();
    dialog.querySelector('h2').textContent = data.name;
    dialog.querySelector('[data-description]').textContent = data.description;
    const nav = dialog.querySelector('nav');
    const content = dialog.querySelector('.dataset-about-content');
    const summary = () => {
      dialog.querySelector('[data-description]').hidden = false;
      nav.innerHTML = data.documents.map(d => `<a class="dataset-about-link" href="/datasets/${encodeURIComponent(datasetId)}/about/${encodeURIComponent(d.filename)}" data-document="${escapeHtml(d.filename)}">${d.filename === 'README.md' ? 'Read full documentation →' : 'Terms and attribution →'}</a>`).join('');
      content.innerHTML = '';
      content.hidden = true;
    };
    const select = filename => {
      const doc = data.documents.find(d => d.filename === filename);
      if (!doc) return;
      dialog.querySelector('[data-description]').hidden = true;
      nav.innerHTML = '<button type="button" class="dataset-about-link" data-summary>← Summary</button>';
      content.hidden = false;
      content.innerHTML = documentMarkup(doc.text, escapeHtml);
      content.scrollTop = 0;
    };
    dialog.addEventListener('click', event => {
      const button = event.target.closest('[data-document]');
      // Read inside the app, retaining desktop authentication and formatting.
      if (button) { event.preventDefault(); select(button.dataset.document); }
      if (event.target.closest('[data-summary]')) summary();
    });
    summary();
    status.textContent = data.unavailable.length ? 'Some package documentation could not be read.'
      : data.documents.length ? '' : 'No additional documentation is included in this dataset.';
  } catch (error) {
    if (error.name === 'AbortError') return;
    dialog.querySelector('h2').textContent = 'Dataset documentation';
    status.textContent = error.message;
  }
}
