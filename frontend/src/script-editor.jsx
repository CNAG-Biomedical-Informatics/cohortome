import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {ModalityIcon} from './assay-overview.jsx';
import {formatAssayRequirementLabel} from '../../static/js/assay_labels.js';

function Summary({summary:s}) {
  const c=s.contract;
  return <><h4>Check before copying</h4><dl>{s.rows.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{value}</dd></React.Fragment>)}</dl>
    {!s.compare && <p className="section-note">This template does not define a Cohort B. For an A-versus-B question, enable comparison in Patients and prepare again.</p>}
    {c ? <><div className="query-result-table-scroll"><table><thead><tr><th>Assay</th><th>A samples</th>{s.compare && <th>B samples</th>}<th>Features</th></tr></thead><tbody>{Object.entries(c.assays || {}).map(([name,assay])=><tr key={name}><td>{formatAssayRequirementLabel(name)}</td><td>{assay.cohort_a_samples ?? 'Not checked'}</td>{s.compare && <td>{assay.cohort_b_samples ?? 'Not checked'}</td>}<td>{assay.features ?? 'Not checked'}</td></tr>)}</tbody></table></div>
      {(c.omitted_assays || []).map((assay,i)=><p key={i} className="section-note"><ModalityIcon modality={assay.modality}/> {formatAssayRequirementLabel(assay.modality)}: not included — {assay.reason}</p>)}
      {s.compare && Object.values(c.assays || {}).some(a=>!a.cohort_a_samples || !a.cohort_b_samples) && <p className="section-note">Some assays have no samples in one group. They cannot support an A/B comparison; choose an assay with samples in both groups.</p>}
    </> : <p className="section-note">Assay coverage has not been checked. Prepare the template to see the matched sample counts.</p>}
  </>;
}
function Editor({model:m,actions:a}) {
  return <><h4>Custom Python / R · synthetic prototype</h4><label htmlFor="analysisScriptLanguage">Language</label><select id="analysisScriptLanguage" value={m.language} disabled={m.busy} onChange={e=>a.language(e.target.value)}><option value="python">Python</option><option value="r">R</option></select>
    <p className="section-note">For limma-voom, choose R. To compare two groups, open Patients, turn on comparison and choose Cohort A and Cohort B before preparing.</p>
    <p className="section-note">COHORTome prepares the current cohorts and selected assays (all demo assays if none selected). The template describes the objects and includes loading code, not patient values. Only the bundled Synthetic cross-sectional demo is allowed.</p>
    <div className="pheno-actions"><button type="button" data-script-basic="" disabled={m.busy} onClick={a.basic}>Use 60-second test</button><button type="button" data-script-inputs="" disabled={m.busy || m.missing} onClick={a.inputs}>Check inputs</button><button type="button" data-script-prepare="" disabled={m.busy || m.missing} onClick={a.prepare}>Generate data-aware template</button><button type="button" className="query-chip" data-script-copy="" disabled={m.copyDisabled} onClick={a.copy}>Copy template for AI</button></div>
    <div data-script-summary="" aria-live="polite"><Summary summary={m.summary}/></div>
    <p className="section-note">Paste a complete script and click Run: inputs are prepared automatically without replacing your code. The 60-second test waits one minute so you can navigate elsewhere while it runs; it performs no scientific analysis. Generate a data-aware template only when you need loading code and instructions for an AI.</p>
    <label htmlFor="analysisScriptCode">Analysis script</label><textarea id="analysisScriptCode" rows="18" spellCheck={false} placeholder="Paste your complete Python or R script, or choose Use 60-second test." value={m.script} disabled={m.busy} onChange={e=>a.script(e.target.value)}/>
    <p className="section-note">Fixed packages; no network or installation. 90 seconds, 512 MiB. Save CSV, TXT or PNG under /work/output. Review statistical choices before running. The exact script and input contract are saved with the run.</p>
    <p data-script-status="" role="status">{m.status}</p>
  </>;
}
export function createScriptEditorView(host,actions) {
  const root=createRoot(host);
  return {render(model){flushSync(()=>root.render(<Editor model={model} actions={actions}/>));}};
}
