import React from 'react';

export function AuthPanel({ logoUrl, logoAlt }) {
  return (
    <>
      <div className="auth-gate-card">
        <div className="auth-gate-copy">
          <div className="auth-gate-heading">
            {logoUrl && <img className="auth-gate-heading-logo" src={logoUrl} alt={logoAlt} />}
            <h2>Sign in</h2>
          </div>
          <p>
            Authentication is required before any clinical, assay, or analysis workspace is shown.
          </p>
        </div>
        <div id="authGateStatus" className="section-note">
          Enter your credentials to open your private workspace.
        </div>
        <div id="authOidcForm" className="auth-oidc-form is-hidden">
          <button id="authOidcLoginBtn" type="button">
            <span className="button-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                <path d="M10 17l5-5-5-5"></path>
                <path d="M15 12H3"></path>
              </svg>
            </span>
            <span id="authOidcLoginLabel">Sign in with provider</span>
          </button>
        </div>
        <div className="auth-gate-form">
          <input id="authUsername" placeholder="Username" autoComplete="username" />
          <input
            id="authPassword"
            type="password"
            placeholder="Password"
            autoComplete="current-password"
          />
          <button id="authLoginBtn" type="button">
            <span className="button-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                <path d="M10 17l5-5-5-5"></path>
                <path d="M15 12H3"></path>
              </svg>
            </span>
            <span id="authLoginLabel">Sign in</span>
          </button>
        </div>
        <div id="authPasswordResetPrompt" className="auth-reset-prompt is-hidden">
          <button id="authForgotPasswordBtn" type="button" className="secondary-btn">
            Forgot password?
          </button>
        </div>
        <div id="authPasswordResetUnavailable" className="section-note is-hidden">
          Forgot password? Contact your administrator.
        </div>
        <div id="authPasswordResetPanel" className="auth-reset-panel is-hidden" aria-live="polite">
          <div id="authPasswordResetRequestForm" className="auth-reset-form">
            <label htmlFor="authPasswordResetIdentifier">Reset password</label>
            <div className="auth-gate-form">
              <input
                id="authPasswordResetIdentifier"
                type="text"
                placeholder="Username or email"
                autoComplete="username"
              />
              <button id="authPasswordResetRequestBtn" type="button">
                Send reset link
              </button>
              <button id="authPasswordResetCancelBtn" type="button" className="secondary-btn">
                Cancel
              </button>
            </div>
          </div>
          <div id="authPasswordResetConfirmForm" className="auth-reset-form is-hidden">
            <label htmlFor="authPasswordResetNewPassword">Choose a new password</label>
            <div className="auth-gate-form">
              <input
                id="authPasswordResetNewPassword"
                type="password"
                placeholder="New password"
                autoComplete="new-password"
              />
              <input
                id="authPasswordResetConfirmPassword"
                type="password"
                placeholder="Confirm password"
                autoComplete="new-password"
              />
              <button id="authPasswordResetConfirmBtn" type="button">
                Reset password
              </button>
            </div>
            <button id="authPasswordResetConfirmCancelBtn" type="button" className="secondary-btn">
              Back to sign in
            </button>
          </div>
          <div id="authPasswordResetStatus" className="section-note">
            Enter your username or email to receive a reset link.
          </div>
        </div>
      </div>
    </>
  );
}
