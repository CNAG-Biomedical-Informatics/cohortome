import React from 'react';

export function UsersShell() {
  return (
    <section id="usersTab" className="tab-panel">
      <div className="controls">
        <label>Users</label>
        <div className="section-note">
          Create local users and manage application role, groups, password, and sign-in status.
          External identity providers can be added later without changing dataset authorization
          rules.
        </div>
        <div id="usersCreateCard" className="dataset-picker-card"></div>
        <div id="usersStatus" className="query-status">
          Loading users...
        </div>
        <div id="usersList" className="analysis-session-list">
          <div className="empty">No users available.</div>
        </div>
      </div>
    </section>
  );
}

export function ModelsShell() {
  return (
    <section id="modelsTab" className="tab-panel">
      <div className="controls">
        <label>Model Administration</label>
        <div className="section-note">
          Manage approved OpenAI-compatible LLM endpoints. Users select a provider in Settings;
          dataset classification and provider boundary still control what model context is allowed.
        </div>
        <div id="modelsCreateCard" className="dataset-picker-card"></div>
        <div id="modelsStatus" className="query-status">
          Loading model providers...
        </div>
        <div id="modelsList" className="dataset-picker-list">
          <div className="empty">No model providers configured.</div>
        </div>
      </div>
    </section>
  );
}
