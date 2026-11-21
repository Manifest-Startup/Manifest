---
name: manifest-account
description: "Manage a person's Manifest account: profile, signed-in sessions (browsers, CLI, agents), privacy choices and data-subject requests (access, export, correct, object, erase), API keys, their own OpenAI key status and AI spend cap, connected integrations (GitHub: see manifest-github), surveys and contacting the team."
---

# Account, privacy and settings

## Profile
- `me`, `account`, `profile` read the person; `update_account` (input object) changes name, username, bio, location, skills or picture URL. Changing email may need re-verification.
- The profile picture upload stays in the app (Account → Profile).

## Sessions and security
- `my_sessions` lists browsers, the CLI and AI agents signed in, including this one.
- `revoke_account_session` signs one out; `revoke_other_account_sessions` signs out everything but the current session (both need `confirm: true`; revoking this agent's own session disconnects you).

## AI key and spend
- `ai_key_status` (never returns the key), `remove_openai_api_key` (needs `confirm: true`). Adding a key happens in Account → AI settings, never in chat.
- `my_cost_dashboard` (spend this month by feature), `my_cost_preflight`, `set_variable_cost_cap` (monthly USD cap, or pause AI spend).

## Privacy and data rights
- `privacy_status`, `privacy_consent`, `privacy_set_consent`, `privacy_withdraw_consent` (needs `confirm: true`).
- Data-subject requests: `dsar_access` (what Manifest holds), `dsar_export` (portable JSON), `dsar_rectify`, `dsar_object`, `dsar_retention_exceptions`, `dsar_erase_certificate`.
- `dsar_erase` and `request_account_deletion` permanently delete the account. Explain that it cannot be undone, suggest `dsar_export` first, and only proceed with `confirm: true` after an explicit yes. Some of these need a sign-in in the last 5 minutes; if refused, ask the person to reconnect Manifest and try again.

## API keys (for scripts)
- `keys_clients`, `keys_create_client`, `keys_delete_client`, `keys_create`, `keys_rotate`, `keys_revoke`, `keys_tiers`, `keys_usage`.
- A new key's secret is shown once: tell the person to copy it into their secret store, and don't repeat it later in the conversation.

## Integrations
- `integrations` and `integration` (never return credentials), `disconnect_integration` (needs `confirm: true`).
- Connected integrations are the person's **key partners**: every canvas lists them under Key Partners, Open Media included. An integration's linked field is true when the partner's own sign-in completed; otherwise it was added as a partner by name.
- `start_integration_connection` connects a partner by `serviceId` (`notion`, `stripe`, or any service; pass `name` for a custom partner). Say what you'll connect first. The result status is connected, already connected, or needs browser: then give the person `connectUrl` to approve it on the provider's own sign-in page. Never ask for passwords or tokens.
- `open_media_link` shows the linked Open Media account used for messages and pitch shorts.
- GitHub (connect it, repos, issues, pull requests, CI, releases): see the manifest-github skill. `github_bootstrap` still creates a repository for an idea.

## Feedback and trust
- `submit_survey`, `survey_insights`, `submit_contact_form` (show the message before sending).
- `trust_center`: Manifest's security posture. `voice_capabilities`: what Manifest's voice assistant can do.
