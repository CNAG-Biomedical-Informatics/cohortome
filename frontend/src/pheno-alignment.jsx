import React from 'react';
import {createRoot} from 'react-dom/client';

function AlignmentGroup({title, items, bucketStyle, bucketName}) {
  if (!items.length) return <div className="empty">{title}: none.</div>;
  const groups = new Map();
  for (const item of items) {
    const bucket = item.bucket || 'other';
    if (!groups.has(bucket)) groups.set(bucket, []);
    groups.get(bucket).push(item);
  }
  return <div className="alignment-section"><h4>{title}</h4><div className="alignment-group-table-wrap"><table className="alignment-group-table"><thead><tr><th>Term Type</th><th>Matched Variable</th></tr></thead><tbody>{[...groups].sort(([a],[b])=>a.localeCompare(b)).flatMap(([bucket,entries])=>entries.map((entry,index)=>{
    const style = bucketStyle(bucket);
    return <tr key={`${bucket}:${index}`}><td><span className="alignment-bucket-pill" style={{'--bucket-bg':style.bg,'--bucket-ink':style.ink}}><span className="alignment-swatch"/>{bucketName(bucket)}</span></td><td><div className="alignment-label-cell">{entry.label || ''}</div><div className="alignment-path-cell">{entry.json_path || ''}</div></td></tr>;
  }))}</tbody></table></div></div>;
}
export function createPhenoAlignmentView(host, bucketStyle, bucketName) {
  const root = createRoot(host);
  return {render(model) {
    if (model.message) {root.render(<div className="empty">{model.message}</div>); return;}
    const payload = model.payload;
    const groups = [['Matched Variables','Shared',payload.shared],['Reference-Only Variables','Reference-only',payload.reference_only],['Target-Only Variables','Target-only',payload.target_only]].map(([title,label,items])=>({title,label,items:Array.isArray(items) ? items : []}));
    root.render(<><div className="section-note">Reference <strong>{payload.reference_id || 'unknown'}</strong> compared to target <strong>{payload.target_id || 'unknown'}</strong>.</div><div className="alignment-summary">{groups.map(group=><span className="alignment-stat" key={group.title}>{group.label} {group.items.length}</span>)}</div>{groups.map(group=><AlignmentGroup key={group.title} {...group} bucketStyle={bucketStyle} bucketName={bucketName}/>)}</>);
  }};
}
