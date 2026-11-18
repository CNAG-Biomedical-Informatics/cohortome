import React from 'react';
import { renderSupplemental as render } from './view-root.js';
import { ModalityIcon } from './modality-icon.jsx';

export function renderNotice(host, message) {
  render(host, message ? <div className="empty">{message}</div> : null);
}

export function renderOptions(host, items = []) {
  const option = (item, index) => (
    <option
      key={item.value ?? index}
      value={item.value}
      label={item.labelAttribute}
      title={item.title}
      disabled={item.disabled}
    >
      {item.label}
    </option>
  );
  render(
    host,
    items.map((item, index) =>
      item.options ? (
        <optgroup key={index} label={item.label}>
          {item.options.map(option)}
        </optgroup>
      ) : (
        option(item, index)
      ),
    ),
  );
}

export function renderBadges(host, items = []) {
  render(
    host,
    items.map((item, index) => (
      <span key={index} className="query-chip badge">
        {item.modality && <ModalityIcon modality={item.modality} />} {item.label}
      </span>
    )),
  );
}
