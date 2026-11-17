import React, {Fragment} from 'react';
import {createRoot} from 'react-dom/client';

const paths = {
  pin:'M9 3h6l-1 6 4 4v2H6v-2l4-4-1-6ZM12 15v6',
  move:'M3 7V4h6l2 3h10v13H3ZM8 13h8m-3-3 3 3-3 3',
  rename:'m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14v6Z',
  delete:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  folder:'M3 7V5h7l2 2h9v13H3ZM3 10h18',
  analysis:'M4 3v17h17M9 16v-4m5 4V6m5 10V9',
  query:'M4 4h16v12H9l-5 4Z',
};
function Icon({kind, unpin}) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === 'pheno' ? <><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="m8 8 3 7m5-7-3 7M9 6h6"/></> : <path d={paths[kind]}/>}
    {unpin && <path d="m3 3 18 18"/>}
  </svg>;
}
function Action({kind, children, unpin, ...props}) {
  return <button type="button" className={kind === 'delete' ? 'danger-btn' : undefined} onClick={event=>event.currentTarget.closest('details')?.removeAttribute('open')} {...props}><span className="chat-menu-icon" aria-hidden="true"><Icon kind={kind} unpin={unpin}/></span>{children}</button>;
}
const chatKey = item => `${item.chatKind || 'analysis'}:${item.id}`;
function Card({item, model}) {
  const kind = item.chatKind || 'analysis', key = chatKey(item);
  const prefix = kind === 'analysis' ? 'analysis-session' : kind;
  const pinned = model.organization.pinned.includes(key);
  const select = model.selection;
  const label = kind === 'analysis' ? item.title : `${kind === 'query' ? 'Query' : 'Pheno-Ranker'}: ${item.title}`;
  return <div className={`analysis-session-card${item.active ? ' is-active' : ''}`}>
    {select.selecting && <input className="chat-delete-check" type="checkbox" data-select-chat={key} aria-label={`Select ${item.title || 'Untitled chat'}`} checked={select.selected.includes(key)} disabled={select.busy} onChange={event=>select.toggle(key,event.target.checked)}/>}
    <button type="button" className="analysis-session-main" {...{[`data-${kind === 'analysis' ? prefix : kind+'-session'}-id`]:item.id}} aria-current={item.active ? 'true' : undefined} aria-label={label} title={label}>
      <div className="analysis-session-title"><span className="chat-type-icon" title={`${kind === 'analysis' ? 'Analysis' : kind === 'query' ? 'Query' : 'Pheno-Ranker'} chat`}><Icon kind={kind}/></span>{item.title}</div>
      {item.status && <small className="analysis-chat-status">{item.status}</small>}
    </button>
    <details className="analysis-chat-menu"><summary aria-label={`Actions for ${item.title}`}>⋯</summary><div>
      <Action kind="pin" unpin={pinned} data-chat-pin={item.id} data-chat-kind={kind}>{pinned ? 'Unpin' : 'Pin'}</Action>
      <Action kind="move" data-chat-move={item.id} data-chat-kind={kind}>Move to folder…</Action>
      <Action kind="rename" {...{[`data-${prefix}-rename`]:item.id}}>Rename</Action>
      <Action kind="delete" {...{[`data-${prefix}-delete`]:item.id}}>Delete</Action>
    </div></details>
  </div>;
}
function ChatList({model}) {
  const {items, search, organization:o, selection:s} = model;
  const folders = [...o.folders].sort((a,b)=>a.name.localeCompare(b.name));
  const cards = (rows, empty) => rows.length ? rows.map(item=><Card key={chatKey(item)} item={item} model={model}/>) : <div className="empty">{empty}</div>;
  const pinned = items.filter(item=>o.pinned.includes(chatKey(item)));
  const shortcuts = folders.filter(f=>o.pinned.includes(`folder:${f.id}`) && (!search || f.name.toLocaleLowerCase().includes(search)));
  let previous = '';
  return <>
    {s.selecting && <div className="chat-selection-bar"><span>{s.selected.length} selected (including hidden selections)</span><button type="button" className="danger-btn" data-delete-selected disabled={s.busy || !s.selected.length}>Delete selected…</button><button type="button" className="secondary-btn" data-cancel-selection disabled={s.busy}>Cancel</button></div>}
    {!folders.length && !o.pinned.length ? (items.length ? items.map(item=>{
      const heading = item.group !== previous; previous = item.group;
      return <Fragment key={chatKey(item)}>{heading && <h4 className="analysis-chat-date">{item.group}</h4>}<Card item={item} model={model}/></Fragment>;
    }) : <div className="empty">No matching chats.</div>) : <>
      {!!(pinned.length || shortcuts.length) && <section aria-label="Pinned"><h4 className="analysis-chat-date">Pinned</h4>{shortcuts.map(f=><button key={f.id} className="chat-folder-shortcut" type="button" data-folder-open={f.id}><Icon kind="folder"/><span>{f.name}</span></button>)}{pinned.map(item=><Card key={chatKey(item)} item={item} model={model}/>)}</section>}
      {!!folders.length && <h4 className="analysis-chat-date">Folders</h4>}
      {folders.map(f=>{
        const members = items.filter(item=>o.assignments[chatKey(item)] === f.id);
        if (search && !members.length && !f.name.toLocaleLowerCase().includes(search)) return null;
        const open = !!search || !o.collapsed.includes(f.id), pin = o.pinned.includes(`folder:${f.id}`);
        return <section key={f.id} className="chat-folder" data-folder-id={f.id}><div className="chat-folder-heading"><button type="button" data-folder-toggle={f.id} aria-expanded={open} title={f.name}><Icon kind="folder"/><span>{f.name}</span><small>{members.length}</small></button><details className="analysis-chat-menu"><summary aria-label={`Actions for folder ${f.name}`}>⋯</summary><div><Action kind="pin" unpin={pin} data-chat-pin={f.id} data-chat-kind="folder">{pin ? 'Unpin' : 'Pin'}</Action><Action kind="rename" data-folder-rename={f.id}>Rename</Action><Action kind="delete" data-folder-delete={f.id}>Delete folder</Action></div></details></div><div className="chat-folder-body" hidden={!open}>{cards(members,'No chats in this folder.')}</div></section>;
      })}
      <section aria-label="Unfiled"><h4 className="analysis-chat-date">Unfiled</h4>{cards(items.filter(item=>!folders.some(f=>f.id === o.assignments[chatKey(item)])), 'No unfiled chats.')}</section>
    </>}
  </>;
}
export function createChatListView(host) {
  const root = createRoot(host);
  return {render(model){root.render(<ChatList model={model}/>);}};
}
