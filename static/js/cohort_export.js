import { downloadFile, downloadIcon, downloadStatus } from './shared.js';

export async function openMolecularExport(cohortId, escapeHtml) {
  if (document.getElementById('cohortExportDialog')) return;
  const dialog = document.createElement('dialog');
  dialog.id = 'cohortExportDialog';
  dialog.className = 'chat-move-dialog cohort-export-dialog';
  dialog.setAttribute('aria-labelledby', 'cohortExportTitle');
  dialog.innerHTML = `<h3 id="cohortExportTitle">Export molecular data</h3>
    <p class="cohort-export-scope"></p>
    <div class="cohort-export-assays"></div>
    <details class="view-help"><summary>Contents and limits</summary>
      <p>ZIP with feature-by-sample TSV matrices, patient–sample links, and a manifest. Values are not normalized, rounded, or imputed. Clinical records, raw sequencing files, images, and additional sample covariates are not included.</p>
      <p>Limits: 64 MiB per source, 128 MiB total sources, 32 MiB exported content, and 100,000 feature rows across up to 32 assays. Source size is not the final download size. Large matrices require a separate export workflow.</p>
      <p>Import matrices with R or Python. Treat all downloads as research data; permission to use data is not permission to redistribute it.</p>
    </details>
    <p role="status">Checking available assays…</p>
    <div class="saved-cohort-actions"><button type="button" data-download disabled>${downloadIcon()}Download ZIP</button><button type="button" data-close>Close</button></div>`;
  document.body.append(dialog);
  const status = dialog.querySelector('[role=status]');
  const download = dialog.querySelector('[data-download]');
  const list = dialog.querySelector('.cohort-export-assays');
  let items = [], busy = false;
  dialog.querySelector('[data-close]').onclick = () => { if (!busy) dialog.close(); };
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => dialog.remove());
  dialog.showModal();
  const selected = () => [...list.querySelectorAll('input:checked')].map(input => items[Number(input.value)]);
  list.addEventListener('change', () => {
    const chosen = selected();
    const bytes = chosen.reduce((sum, item) => sum + item.source_bytes, 0);
    download.disabled = busy || !chosen.length || chosen.length > 32 || bytes > 128 * 1024 * 1024;
    status.textContent = `${chosen.length} assays selected · ${(bytes / 1048576).toFixed(1)} MiB source data${bytes > 128 * 1048576 ? ' — select fewer assays' : ''}`;
  });
  try {
    const response = await fetch(`/saved-cohorts/${encodeURIComponent(cohortId)}/export-assays`, {cache: 'no-store'});
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Cannot load export options.');
    if (!dialog.isConnected) return;
    items = payload.assays;
    dialog.querySelector('.cohort-export-scope').textContent = payload.sample_scope
      ? 'Sample cohort: only the saved samples will be exported.'
      : 'Patient cohort: all linked samples for the saved patients will be exported.';
    list.innerHTML = items.map((item, index) => `<label class="cohort-export-option">
      <input type="checkbox" value="${index}" ${item.available ? '' : 'disabled'}>
      <span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.dataset_id)} · ${escapeHtml(item.data_type || 'Unknown measurement type')}</small>
      <small>${item.available ? `${item.patient_count} patients · ${item.sample_count} samples · ${(item.source_bytes / 1048576).toFixed(1)} MiB source` : escapeHtml(item.reason)}</small></span>
    </label>`).join('');
    status.textContent = items.some(item => item.available) ? 'Select assays to export.' : 'No supported assays with matching samples are available.';
  } catch (error) { status.textContent = error.message; }
  download.onclick = async () => {
    busy = true; download.disabled = true;
    list.querySelectorAll('input').forEach(input => { input.disabled = true; });
    dialog.querySelector('[data-close]').disabled = true;
    status.textContent = 'Preparing molecular export…';
    try {
      const result = await downloadFile(`/saved-cohorts/${encodeURIComponent(cohortId)}/export-molecular`, 'cohort-molecular-data.zip', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({assays: selected().map(({key, fingerprint}) => ({key, fingerprint}))}),
      });
      status.textContent = downloadStatus(result);
    } catch (error) { status.textContent = error.message; }
    finally {
      busy = false;
      dialog.querySelector('[data-close]').disabled = false;
      list.querySelectorAll('input').forEach(input => { input.disabled = !items[Number(input.value)].available; });
      download.disabled = !selected().length;
    }
  };
}
