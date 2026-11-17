import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';

function CreateUser(){return <>
            <div>
              <div className="dataset-picker-title">
                <span>Create local user</span>
              </div>
              <div className="query-grid query-grid-compact">
                <div>
                  <label htmlFor="userCreateUsername">Username</label>
                  <input id="userCreateUsername" type="text" placeholder="e.g. alice"/>
                </div>
                <div>
                  <label htmlFor="userCreateDisplayName">Display name</label>
                  <input id="userCreateDisplayName" type="text" placeholder="e.g. Alice Example"/>
                </div>
                <div>
                  <label htmlFor="userCreateEmail">Email</label>
                  <input id="userCreateEmail" type="email" placeholder="e.g. alice@example.org"/>
                </div>
                <div>
                  <label htmlFor="userCreatePassword">Password</label>
                  <input id="userCreatePassword" type="password" placeholder="Initial password"/>
                </div>
                <div>
                  <label htmlFor="userCreateRole">Role</label>
                  <select id="userCreateRole">
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div className="query-grid-span-2">
                  <label htmlFor="userCreateGroups">Groups</label>
                  <input id="userCreateGroups" type="text" placeholder="Comma-separated groups, e.g. cnag, analysts"/>
                </div>
              </div>
              <div className="query-row">
                <label className="dataset-picker-check">
                  <input id="userCreateEnabled" type="checkbox" defaultChecked/>
                  <span>Enabled</span>
                </label>
                <button id="userCreateBtn" type="button">Create user</button>
              </div>
            </div>
          </>;}

function CreateProvider(){return <>
            <div>
              <div className="dataset-picker-title">
                <span>Add model provider</span>
              </div>
              <div className="query-grid query-grid-compact">
                <div>
                  <label htmlFor="modelCreateId">Provider ID</label>
                  <input id="modelCreateId" type="text" placeholder="e.g. cnag-local" autoComplete="off"/>
                </div>
                <div>
                  <label htmlFor="modelCreateLabel">Display name</label>
                  <input id="modelCreateLabel" type="text" placeholder="e.g. CNAG local model"/>
                </div>
                <div className="query-grid-span-2">
                  <label htmlFor="modelCreateBaseUrl">Base URL</label>
                  <input id="modelCreateBaseUrl" type="url" placeholder="http://127.0.0.1:1234/v1"/>
                </div>
                <div>
                  <label htmlFor="modelCreateModel">Model ID</label>
                  <input id="modelCreateModel" type="text" placeholder="Optional; discover from provider"/>
                </div>
                <div>
                  <label htmlFor="modelCreateTimeout">Timeout (seconds)</label>
                  <input id="modelCreateTimeout" type="number" min="1" max="300" step="1" defaultValue="30"/>
                </div>
                <div>
                  <label htmlFor="modelCreateBoundary">Data boundary</label>
                  <select id="modelCreateBoundary">
                    <option value="external">External</option>
                    <option value="local">Local</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="modelCreateApiKey">API key</label>
                  <input id="modelCreateApiKey" type="password" placeholder="Optional for local providers" autoComplete="new-password"/>
                </div>
              </div>
              <div className="section-note">Mark a provider as local only when it operates inside the deployment's approved private-data boundary. API keys are write-only.</div>
              <div className="query-row">
                <label className="dataset-picker-check">
                  <input id="modelCreateEnabled" type="checkbox" defaultChecked/>
                  <span>Enabled</span>
                </label>
                <button id="modelCreateBtn" type="button">Add provider</button>
              </div>
            </div>
          </>;}

export function mountAdminCreationForms(){
  for(const [id,Component] of [['usersCreateCard',CreateUser],['modelsCreateCard',CreateProvider]]){
    const host=document.getElementById(id);
    if(host) flushSync(()=>createRoot(host).render(<Component/>));
  }
}
