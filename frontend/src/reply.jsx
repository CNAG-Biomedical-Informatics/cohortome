import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {QueryTable} from './query-table.jsx';

function Inline({text}) {
  return String(text).split('`').map((part,index)=>index%2 ? <code key={index}>{part}</code> : <React.Fragment key={index}>{part.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((token,i)=>token.startsWith('**') && token.endsWith('**') ? <strong key={i}>{token.slice(2,-2)}</strong> : token.startsWith('*') && token.endsWith('*') ? <em key={i}>{token.slice(1,-1)}</em> : token)}</React.Fragment>);
}
// A deliberately small Markdown subset. API text is rendered as text nodes;
// HTML, scripts, embedded media and arbitrary links are never interpreted.
export function ReplyText({text}) {
  const blocks=[], lines=String(text || '').replaceAll('\r\n','\n').split('\n');
  let paragraph=[], list=[], table=[], code=[], inCode=false;
  const add=node=>blocks.push(<React.Fragment key={blocks.length}>{node}</React.Fragment>);
  const flushParagraph=()=>{if(paragraph.length) add(<p>{paragraph.map((line,i)=><React.Fragment key={i}>{i>0 && <br/>}<Inline text={line}/></React.Fragment>)}</p>);paragraph=[];};
  const flushList=()=>{if(list.length) add(<ul>{list.map((line,i)=><li key={i}><Inline text={line}/></li>)}</ul>);list=[];};
  const flushCode=()=>{if(code.length) add(<pre><code>{code.join('\n')}</code></pre>);code=[];};
  const flushTable=()=>{
    const separator=(table[1] || '').split('|').map(s=>s.trim()).filter(Boolean);
    if(table.length<2 || !separator.length || !separator.every(s=>s.length>=3 && s.replaceAll('-','').replaceAll(':','')==='')) {paragraph.push(...table);table=[];return;}
    const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(s=>s.trim());
    add(<table><thead><tr>{cells(table[0]).map((cell,i)=><th key={i}><Inline text={cell}/></th>)}</tr></thead><tbody>{table.slice(2).map((row,i)=><tr key={i}>{cells(row).map((cell,j)=><td key={j}><Inline text={cell}/></td>)}</tr>)}</tbody></table>);table=[];
  };
  for(const line of lines) {
    const trimmed=line.trim();
    if(trimmed.startsWith('```')) {flushParagraph();flushList();flushTable();if(inCode)flushCode();inCode=!inCode;continue;}
    if(inCode){code.push(line);continue;}
    if(!trimmed){flushParagraph();flushList();flushTable();continue;}
    if(trimmed.includes('|')){flushParagraph();flushList();table.push(trimmed);continue;}
    flushTable();
    if(trimmed.startsWith('- ') || trimmed.startsWith('* ')){flushParagraph();list.push(trimmed.slice(2));continue;}
    if(/^#{1,3} /.test(trimmed)){flushParagraph();flushList();add(<h4><Inline text={trimmed.replace(/^#{1,3} /,'')}/></h4>);continue;}
    paragraph.push(trimmed);
  }
  flushTable();flushParagraph();flushList();if(inCode)flushCode();
  return blocks.length ? blocks : <p>No answer returned.</p>;
}
export function Reply({model}) {return <><ReplyText text={model?.text}/><QueryTable model={model?.table}/></>;}
export function createReplyView(host) {
  const root=createRoot(host);
  return {render(model){flushSync(()=>root.render(model?.empty ? <div className="empty">{model.empty}</div> : <Reply model={model}/>));}};
}
