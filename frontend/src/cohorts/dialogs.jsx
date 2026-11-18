import React, { useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Icon, Action } from './actions.jsx';
export function NameForm({ dialog, defaultName, rename, setResult }) {
  const input = useRef(null);
  useLayoutEffect(() => {
    dialog.showModal();
    input.current.focus();
    input.current.select();
  }, []);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const name = input.current.value.trim();
        if (!name) {
          input.current.setCustomValidity('Enter a cohort name.');
          input.current.reportValidity();
          return;
        }
        setResult(name);
        dialog.close();
      }}
    >
      <h3 id="cohortNameTitle">{rename ? 'Rename cohort' : 'Save cohort'}</h3>
      <label htmlFor="cohortNameInput">Cohort name</label>
      <input
        ref={input}
        id="cohortNameInput"
        type="text"
        required
        autoComplete="off"
        defaultValue={defaultName}
        onInput={() => input.current.setCustomValidity('')}
      />
      <div className="chat-move-actions">
        <button
          type="button"
          className="secondary-btn"
          data-cohort-name-cancel
          onClick={() => dialog.close()}
        >
          Cancel
        </button>
        <button type="submit" className="primary-btn">
          {rename ? 'Rename' : 'Save cohort'}
        </button>
      </div>
    </form>
  );
}

export function requestCohortName(defaultName, rename = false) {
  return new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.id = 'cohortNameDialog';
    dialog.className = 'chat-move-dialog';
    dialog.setAttribute('aria-labelledby', 'cohortNameTitle');
    document.body.append(dialog);
    const root = createRoot(dialog);
    let result = null;
    dialog.addEventListener(
      'close',
      () => {
        root.unmount();
        dialog.remove();
        resolve(result);
      },
      { once: true },
    );
    root.render(
      <NameForm
        dialog={dialog}
        defaultName={defaultName}
        rename={rename}
        setResult={(value) => {
          result = value;
        }}
      />,
    );
  });
}

export function Members({ item, labels, dialog }) {
  const [offset, setOffset] = useState(0),
    members = item.members || [];
  useLayoutEffect(() => {
    dialog.showModal();
  }, []);
  return (
    <>
      <h3 id="cohortMembersTitle">{item.name}</h3>
      <div className="cohort-members-table">
        <table className="assay-table">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Patient ID</th>
              <th>Sample ID</th>
            </tr>
          </thead>
          <tbody>
            {members.slice(offset, offset + 50).map((m, i) => (
              <tr key={offset + i}>
                <td>{labels([m.dataset_id])[0] || m.dataset_id}</td>
                <td>{m.patient_id}</td>
                <td>{m.sample_id || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="saved-cohort-actions">
        <button
          type="button"
          className="query-chip"
          data-prev
          disabled={!offset}
          onClick={() => setOffset(offset - 50)}
        >
          Previous
        </button>
        <span role="status">
          {members.length
            ? `${offset + 1}–${Math.min(offset + 50, members.length)} of ${members.length}`
            : 'No members'}
        </span>
        <button
          type="button"
          className="query-chip"
          data-next
          disabled={offset + 50 >= members.length}
          onClick={() => setOffset(offset + 50)}
        >
          Next
        </button>
        <button type="button" className="query-chip" data-close onClick={() => dialog.close()}>
          Close
        </button>
      </div>
    </>
  );
}

export function inspectCohortMembers(item, labels) {
  document.getElementById('cohortMembersDialog')?.close();
  const dialog = document.createElement('dialog');
  dialog.id = 'cohortMembersDialog';
  dialog.className = 'chat-move-dialog cohort-members-dialog';
  dialog.setAttribute('aria-labelledby', 'cohortMembersTitle');
  document.body.append(dialog);
  const root = createRoot(dialog);
  dialog.addEventListener(
    'close',
    () => {
      root.unmount();
      dialog.remove();
    },
    { once: true },
  );
  root.render(<Members item={item} labels={labels} dialog={dialog} />);
}
