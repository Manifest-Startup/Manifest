# 0002. Open Media is Manifest's only sign-in

- Status: Accepted (2026-11-15). Amends [0001](0001-open-media-for-messages-and-pitch-shorts.md) ("Manifest keeps its own login" no longer holds).
- Spec: [OPEN_MEDIA_SIGN_IN.md](../OPEN_MEDIA_SIGN_IN.md) · Contract: [OPEN_MEDIA_CONTRACT.md](../OPEN_MEDIA_CONTRACT.md)

## Context

Manifest ran its own email/password login, registration and password reset, a Replit OIDC "Continue with GitHub" that stopped working when Replit was retired, its own TOTP MFA (`MFA_ENCRYPTION_KEY`) and passkeys. Every account that used Messages or Pitch Shorts also had to link Open Media separately. Open Media is building one sign-in gateway (`openmedia.site/signin`) with passkeys, email links, passwords and optional MFA for all its apps.

## Decision

- **One button.** The login page offers only **Continue with Open Media** (OAuth 2.1 + PKCE, public client identified by `/oauth/open-media-client.json`) and **Try without an account**.
- **Routes** (`backend/app/routes/auth_routes.py`):
  - `GET /api/auth/open-media/start?next=` needs no session. It sets a 10-minute signed, HttpOnly, SameSite=Lax nonce cookie (path `/api/auth/open-media`) and redirects to Open Media `/authorize`. `state` is HMAC-signed `{nonce, next, guest?, user?, expiry}`; the PKCE verifier is derived from the nonce; `login_hint` is the signed-in account's email when reconnecting.
  - `GET /api/auth/open-media/callback` checks the state against the cookie (once, within 10 minutes), exchanges the code, reads `GET /v1/connected/me`, then finds the Manifest user in this order: the stored Open Media id, the signed-in account that started a reconnect, a non-guest account whose email matches Open Media's **verified** email (case-insensitive auto-link), else a new full account. An unverified or missing email creates nothing and returns `/login?error=unverified_email` (or `no_email`). It stores the tokens (the existing envelope-encrypted link), merges the browser's guest workspace with the existing `merge_guest_workspace_sql`, creates the normal Manifest session cookie, and redirects to a safe same-origin `next`.
  - `POST /api/auth/logout` revokes the session and clears cookies.
- **Removed:** GraphQL `loginUser`, `signupUser`, `requestPasswordReset`, `resetPassword`, `requestGuestAccountUpgradeEmail`, `completeGuestAccountUpgrade`, `mergeGuestWorkspace`, `beginTotpSetup`, `enableTotp`, `disableTotp`, `regenerateRecoveryCodes`, `mfaStatus`, `disconnectOpenMedia`, `PrivacyStatus.passwordResetRetentionMinutes`, and the `password`/`mfaCode` arguments of `requestAccountDeletion`; REST `/auth/login|callback|logout|me|status` (Replit), `/api/auth/step-up/*`, `/api/webauthn/*`, `/api/integrations/open-media/connect|callback`; the password, lockout, HIBP, TOTP, passkey, reset-token and guest-upgrade services; the Resend email sender.
- **Kept:** guest mode, sessions (list, revoke, logout), API keys for the MCP server, enterprise SSO/SCIM, Manifest's session JWT and cookies. Step-up for sensitive routes is now a fresh sign-in (`auth_iat`), and admin routes no longer check Manifest TOTP: second factors live in Open Media.
- **Data stays.** No columns are dropped (`password_hash`, `user_totp_mfa`, `webauthn_credentials`, reset tokens); DSAR export and tenant purge still cover them. Sessions issued before the change stay valid until they expire.
- **Demo mode** (local, no database) signs in the demo user from `/start` without contacting Open Media.

## Consequences

- People manage passkeys, passwords and two-step verification in Open Media. The Account page shows "Signed in with Open Media @handle" and links to Open Media's security settings.
- Every account that signs in is linked, so Messages and Pitch Shorts no longer need a separate "Connect" step; "Disconnect" is gone. Reconnecting (an expired refresh token) is the same sign-in.
- A password-only user whose Open Media email differs from their Manifest email gets a new, empty account. They can sign in once with a matching email, or support can link them.
- An Open Media outage blocks new sign-ins (existing sessions keep working). Manifest no longer enforces MFA for admins itself; it trusts Open Media's (follow-up below).
- Follow-ups: drop the unused auth columns and tables once no session predates this change; store `om_user_id` in an indexed column instead of JSON metadata; ask Open Media to expose `aal`/`amr` so admin routes can require a second factor; remove the `/auth/forgot-password` and `/auth/reset-password` redirects after old emails expire.
