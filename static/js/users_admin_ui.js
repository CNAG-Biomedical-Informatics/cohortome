import {createUsersAdminView} from './react/ui.js';

export function createUsersAdminUi(ctx) {
  const { refs, state, callbacks } = ctx;
  const {
    usersCreateCardEl,
    usersStatusEl,
    usersListEl,
    userCreateUsernameEl,
    userCreateDisplayNameEl,
    userCreateEmailEl,
    userCreatePasswordEl,
    userCreateRoleEl,
    userCreateGroupsEl,
    userCreateEnabledEl,
  } = refs;
  const { canManageDataset, renderDatasetAdminList } = callbacks;

  function parseUserGroupsInput(value) {
    return String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function formatUserGroupsInput(groups) {
    return Array.isArray(groups) ? groups.join(", ") : "";
  }

  function clearUserCreateForm() {
    if (userCreateUsernameEl) userCreateUsernameEl.value = "";
    if (userCreateDisplayNameEl) userCreateDisplayNameEl.value = "";
    if (userCreateEmailEl) userCreateEmailEl.value = "";
    if (userCreatePasswordEl) userCreatePasswordEl.value = "";
    if (userCreateRoleEl) userCreateRoleEl.value = "user";
    if (userCreateGroupsEl) userCreateGroupsEl.value = "";
    if (userCreateEnabledEl) userCreateEnabledEl.checked = true;
  }

  const usersView = usersListEl ? createUsersAdminView(usersListEl) : null;
  function renderAuthUsersList(users) { usersView?.render(users); }

  async function loadAuthUsers() {
    if (!usersListEl || !usersStatusEl) return;
    if (!canManageDataset()) {
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = "Admin access required.";
      usersView.render([], 'User administration is only visible to administrators.');
      if (usersCreateCardEl) {
        usersCreateCardEl.classList.add("is-hidden");
      }
      return;
    }
    if (usersCreateCardEl) {
      usersCreateCardEl.classList.remove("is-hidden");
    }
    usersStatusEl.className = "query-status loading";
    usersStatusEl.textContent = "Loading users...";
    try {
      const response = await fetch("/auth/users");
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Unable to load users.");
      }
      const payload = await response.json();
      const users = Array.isArray(payload.users) ? payload.users : [];
      state.availableAuthUsers = users.slice();
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = `${users.length} user${users.length === 1 ? "" : "s"} configured.`;
      renderDatasetAdminList();
      renderAuthUsersList(users);
    } catch (error) {
      state.availableAuthUsers = [];
      renderDatasetAdminList();
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = error && error.message ? error.message : "Unable to load users.";
      usersView.render([], 'User list unavailable.');
    }
  }

  async function createAuthUser() {
    if (!canManageDataset()) {
      return;
    }
    const username = userCreateUsernameEl ? userCreateUsernameEl.value.trim() : "";
    const password = userCreatePasswordEl ? userCreatePasswordEl.value : "";
    const displayName = userCreateDisplayNameEl ? userCreateDisplayNameEl.value.trim() : "";
    const email = userCreateEmailEl ? userCreateEmailEl.value.trim() : "";
    const role = userCreateRoleEl ? userCreateRoleEl.value : "user";
    const groups = parseUserGroupsInput(userCreateGroupsEl ? userCreateGroupsEl.value : "");
    const enabled = userCreateEnabledEl ? userCreateEnabledEl.checked : true;
    usersStatusEl.className = "query-status loading";
    usersStatusEl.textContent = "Creating user...";
    try {
      const response = await fetch("/auth/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          display_name: displayName,
          email,
          role,
          groups,
          enabled,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to create user.");
      }
      clearUserCreateForm();
      await loadAuthUsers();
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = `User ${payload.username || username} created.`;
    } catch (error) {
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = error && error.message ? error.message : "Unable to create user.";
    }
  }

  async function saveAuthUser(username) {
    const card = usersListEl ? usersListEl.querySelector(`[data-auth-user-card="${CSS.escape(username)}"]`) : null;
    if (!card) {
      return;
    }
    const displayName = card.querySelector('[data-auth-user-field="display_name"]')?.value?.trim() || "";
    const email = card.querySelector('[data-auth-user-field="email"]')?.value?.trim() || "";
    const role = card.querySelector('[data-auth-user-field="role"]')?.value || "user";
    const groups = parseUserGroupsInput(card.querySelector('[data-auth-user-field="groups"]')?.value || "");
    const enabled = Boolean(card.querySelector('[data-auth-user-field="enabled"]')?.checked);
    usersStatusEl.className = "query-status loading";
    usersStatusEl.textContent = `Saving ${username}...`;
    try {
      const response = await fetch(`/auth/users/${encodeURIComponent(username)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: displayName,
          email,
          role,
          groups,
          enabled,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to update user.");
      }
      await loadAuthUsers();
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = `User ${payload.username || username} updated.`;
    } catch (error) {
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = error && error.message ? error.message : "Unable to update user.";
    }
  }

  async function resetAuthUserPassword(username) {
    const card = usersListEl ? usersListEl.querySelector(`[data-auth-user-card="${CSS.escape(username)}"]`) : null;
    const passwordField = card ? card.querySelector('[data-auth-user-field="password"]') : null;
    const password = passwordField ? passwordField.value : "";
    usersStatusEl.className = "query-status loading";
    usersStatusEl.textContent = `Resetting password for ${username}...`;
    try {
      const response = await fetch(`/auth/users/${encodeURIComponent(username)}/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to reset password.");
      }
      if (passwordField) {
        passwordField.value = "";
      }
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = `Password reset for ${payload.username || username}.`;
    } catch (error) {
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = error && error.message ? error.message : "Unable to reset password.";
    }
  }

  async function deleteAuthUser(username) {
    if (!window.confirm(`Delete user ${username}?`)) {
      return;
    }
    usersStatusEl.className = "query-status loading";
    usersStatusEl.textContent = `Deleting ${username}...`;
    try {
      const response = await fetch(`/auth/users/${encodeURIComponent(username)}`, {
        method: "DELETE",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to delete user.");
      }
      await loadAuthUsers();
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = `User ${username} deleted.`;
    } catch (error) {
      usersStatusEl.className = "query-status";
      usersStatusEl.textContent = error && error.message ? error.message : "Unable to delete user.";
    }
  }

  return {
    parseUserGroupsInput,
    formatUserGroupsInput,
    clearUserCreateForm,
    renderAuthUsersList,
    loadAuthUsers,
    createAuthUser,
    saveAuthUser,
    resetAuthUserPassword,
    deleteAuthUser,
  };
}
