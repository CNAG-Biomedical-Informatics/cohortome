import React, {useLayoutEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

function Select({id,label,value,options,onChange,wide=false}) {
  return <div className={wide ? 'query-grid-span-2' : undefined}><label htmlFor={id}>{label}</label><select id={id} value={String(value)} onChange={e=>onChange(e.target.value)}>{options.map(([key,text])=><option key={key} value={key}>{text}</option>)}</select></div>;
}
function Check({id,label,value,onChange}) {
  return <label className="user-settings-check"><input id={id} type="checkbox" checked={!!value} onChange={e=>onChange(e.target.checked)}/> {label}</label>;
}
function Palette({name,label,options,value,onChange,children}) {
  useLayoutEffect(()=>{window.CohortomeTheme.palettePreview(name,value);},[name,value]);
  return <div><label htmlFor={`settings_${name}`}>{label}</label><select id={`settings_${name}`} value={value} onChange={e=>onChange(e.target.value)}>{options.map(([key,text])=><option key={key} value={key}>{text}</option>)}</select><div id={`preview_${name}`} aria-hidden="true"/>{children}</div>;
}
function Preferences({section,settings:s,providers,onChange}) {
  const change=key=>value=>onChange(key,value);
  if(section==='general') return <>
    <Select id="settingsLandingTabMode" label="Start behavior" value={s.landing_tab_mode} options={[["fixed","Fixed start tab"],["last","Remember last tab"]]} onChange={change('landing_tab_mode')}/>
    <Select id="settingsLandingTab" label="Start tab" value={s.landing_tab} options={[["dashboard","Dashboard"],["datasets","Datasets"],["cohorts","Cohorts"],["query","Query"],["analysis","Analysis"],["pheno","Pheno-Ranker"]]} onChange={change('landing_tab')}/>
    <Check id="settingsDashboardAssaysOpen" label="Open Dashboard on assays view" value={s.dashboard_assays_open} onChange={change('dashboard_assays_open')}/>
    <Check id="settingsDatasetCompactView" label="Compact dataset cards" value={s.dataset_compact_view} onChange={change('dataset_compact_view')}/>
  </>;
  if(section==='appearance') return <>
    <Select id="settingsAppearance" label="Appearance" value={s.appearance} options={[["light","Light"],["dark","Dark"],["system","System"]]} onChange={change('appearance')}/>
    <Palette name="plot_palette" label="Plot group colours" value={s.plot_palette} options={[["default","Current colours (default)"],["okabe-ito","Okabe–Ito"],["muted","Muted"]]} onChange={change('plot_palette')}/>
    <Palette name="heatmap_palette" label="Heatmaps · low to high" value={s.heatmap_palette} options={[["default","Current colours (default)"],["viridis","Viridis · purple to yellow"],["cividis","Cividis · blue to yellow"]]} onChange={change('heatmap_palette')}/>
    <Palette name="diverging_palette" label="Heatmaps · centred on zero" value={s.diverging_palette} options={[["default","Current colours (default)"],["blue-orange","Blue–white–orange"],["purple-green","Purple–white–green"]]} onChange={change('diverging_palette')}><p className="section-note">Applies to supported interactive plots after saving. Defaults preserve each tool's colours. Static R images, timeline event colours and significance colours are unchanged. Choose Current colours to reset.</p></Palette>
  </>;
  if(section==='query') {
    const options=providers.map(p=>[String(p.id || ''),`${p.label || p.id || 'Provider'} (${p.data_boundary==='local' ? 'local' : 'external'})${p.model ? ` - ${p.model}` : ''}${p.enabled===false ? ' (disabled)' : ''}`]);
    if(s.llm_provider_id && !options.some(([id])=>id===s.llm_provider_id)) options.push([s.llm_provider_id,`${s.llm_provider_id} (unavailable)`]);
    return <>
      <Select id="settingsQueryDisclosure" label="Response detail" value={s.query_disclosure_default} options={[["detailed","Detailed when allowed"],["summary","Summary"]]} onChange={change('query_disclosure_default')}/>
      <Select id="settingsQueryDefaultMode" label="Query mode" value={s.query_default_mode} options={[["auto","Auto"],["planner_only","Planner first"]]} onChange={change('query_default_mode')}/>
      <Select id="settingsLlmProvider" label="AI provider" wide value={s.llm_provider_id} options={options} onChange={change('llm_provider_id')}/>
      <Check id="settingsLatestQueryDetails" label="Latest query details" value={s.latest_query_details} onChange={change('latest_query_details')}/>
    </>;
  }
  if(section==='jobs') return <>
    <Select id="settingsRunRetention" label="Keep generated runs for" value={s.run_history_retention_days} options={[["7","7 days"],["30","30 days"],["90","90 days"],["180","180 days"],["365","1 year"],["0","Forever"]]} onChange={value=>onChange('run_history_retention_days',Number(value))}/>
    <Check id="settingsAnalysisAutoOpenJobs" label="Open Queue after background runs" value={s.analysis_auto_open_jobs} onChange={change('analysis_auto_open_jobs')}/>
    <Check id="settingsJobNotifications" label="Notify when background runs finish or fail (while this app is open)" value={s.job_notifications} onChange={change('job_notifications')}/>
  </>;
  return <>
    <Select id="settingsPhenoDefaultMetric" label="Pheno-Ranker similarity metric" value={s.pheno_default_metric} options={[["","Default"],["hamming","Hamming"],["jaccard","Jaccard"]]} onChange={change('pheno_default_metric')}/>
    {[
      ['settingsPhenoAdvancedOpen','pheno_advanced_open','Keep Pheno advanced options open'],
      ['settingsPhenoRenderHeatmap','pheno_render_heatmap','Render Pheno heatmap'],
      ['settingsPhenoRenderMds','pheno_render_mds','Render Pheno MDS'],
      ['settingsPhenoRenderUmap','pheno_render_umap','Render UMAP'],
      ['settingsPhenoRenderGraph','pheno_render_graph','Render Pheno graph'],
    ].map(([id,key,label])=><Check key={id} id={id} label={label} value={s[key]} onChange={change(key)}/>)}
  </>;
}
export function createSettingsPreferences(panel) {
  const roots=['appearance','general','query','jobs','analysis'].map(section=>[section,createRoot(panel.querySelector(`[data-settings-page="${section}"] > .user-settings-grid`))]);
  return {render(settings,providers,onChange){flushSync(()=>{for(const [section,root] of roots) root.render(<Preferences section={section} settings={settings} providers={providers} onChange={onChange}/>);});}};
}
