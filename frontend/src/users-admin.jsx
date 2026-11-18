import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';

function UserCard({ user }) {
  const values = () => ({
    display_name: user.display_name || user.username || '',
    email: user.email || '',
    role: user.role || 'user',
    groups: (user.groups || []).join(', '),
    enabled: user.enabled !== false,
  });
  const [draft, setDraft] = useState(values);
  const password = useRef(null);
  useEffect(() => {
    setDraft(values());
    if (password.current) password.current.value = '';
  }, [user]);
  const field = (name) => ({
    'data-auth-user-field': name,
    'data-auth-user': user.username,
    value: draft[name],
    onChange: (event) => setDraft((previous) => ({ ...previous, [name]: event.target.value })),
  });
  const action = (name) => ({ 'data-auth-user-action': name, 'data-auth-user': user.username });
  return (
    <details className="dataset-admin-card" data-auth-user-card={user.username}>
      <summary className="dataset-admin-summary">
        <span className="dataset-admin-summary-main">
          <span className="dataset-picker-title">
            {user.display_name || user.username || 'Unknown user'}
          </span>
          <span className="dataset-picker-meta">
            <span className="dataset-picker-tag">{user.username}</span>
            <span className="dataset-picker-tag">{user.role || 'user'}</span>
            <span className="dataset-picker-tag">auth: {user.auth_source || 'local'}</span>
          </span>
        </span>
        <span
          className={`dataset-picker-tag dataset-picker-tag-${user.enabled !== false ? 'ready' : 'danger'}`}
        >
          {user.enabled !== false ? 'Enabled' : 'Disabled'}
        </span>
      </summary>
      <div className="dataset-admin-body">
        <div className="query-grid query-grid-compact" style={{ marginTop: 12 }}>
          <div>
            <label>
              Display name
              <input type="text" {...field('display_name')} />
            </label>
          </div>
          <div>
            <label>
              Role
              <select {...field('role')}>
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </label>
          </div>
          <div className="query-grid-span-2">
            <label>
              Email
              <input type="email" {...field('email')} placeholder="Optional password-reset email" />
            </label>
          </div>
          <div className="query-grid-span-2">
            <label>
              Groups
              <input type="text" {...field('groups')} placeholder="Comma-separated groups" />
            </label>
          </div>
        </div>
        <div className="query-row" style={{ marginTop: 12 }}>
          <label className="dataset-picker-check">
            <input
              type="checkbox"
              data-auth-user-field="enabled"
              data-auth-user={user.username}
              checked={draft.enabled}
              onChange={(event) =>
                setDraft((previous) => ({ ...previous, enabled: event.target.checked }))
              }
            />
            <span>Enabled</span>
          </label>
          <button type="button" className="query-chip query-chip-deterministic" {...action('save')}>
            Save
          </button>
          <input
            ref={password}
            type="password"
            data-auth-user-field="password"
            data-auth-user={user.username}
            placeholder="New password"
            autoComplete="new-password"
          />
          <button type="button" className="query-chip" {...action('reset-password')}>
            Reset password
          </button>
          <button type="button" className="query-chip danger-btn" {...action('delete')}>
            Delete
          </button>
        </div>
      </div>
    </details>
  );
}
export function createUsersAdminView(host) {
  const root = createRoot(host);
  return {
    render(users = [], message = 'No users configured.') {
      root.render(
        users.length ? (
          users.map((user) => <UserCard key={user.username} user={user} />)
        ) : (
          <div className="empty">{message}</div>
        ),
      );
    },
  };
}
