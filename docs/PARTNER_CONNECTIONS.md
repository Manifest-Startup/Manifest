# Partner connections

Connected integrations are a founder's **key partners**: every Business Model Canvas lists them under Key Partners, and canvas generation treats them as current partners (facts), not candidates.

## How a partner gets connected

One path for the app and for agents: `startIntegrationConnection(serviceId, name)` (plugin tool `start_integration_connection`).

| Partner | What happens | Shown as |
| --- | --- | --- |
| Open Media | Linked when the person signs in with Open Media (the only sign-in) | Linked |
| One of the 8 providers below, **with its app registered** | Returns `connectUrl`; the person approves on the provider's official sign-in page; tokens are stored encrypted (`token_crypto`) | Linked |
| Any other partner, or one of the 8 before its app is registered | Recorded straight away without credentials | Added as partner |

`integrations { linked }` tells the two apart. Credentials are never returned by the API or to agents.

## Status (2026-11-18)

None of the 8 provider apps is registered in production: `GET /auth/<provider>/start` answers `not_configured`, so Connect adds them as partners. Only Open Media is linked for real.

## Register a provider's official app (owner task)

For each provider, create an OAuth app in its developer console, set the redirect URI to
`https://manifeststartup.com/auth/<provider>/callback`, then add the two values as Render secrets on the backend service and redeploy. Connect then opens the provider's sign-in and the card shows **Linked**.

| Provider | Developer console | Render env vars | Scopes Manifest requests |
| --- | --- | --- | --- |
| `google` | Google Cloud Console → APIs & Services → Credentials | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | openid, email, profile, drive.readonly |
| `apple` | Apple Developer → Certificates, IDs & Profiles → Services IDs | `APPLE_CLIENT_ID`, `APPLE_CLIENT_SECRET` | name, email |
| `github` | GitHub → Settings → Developer settings → OAuth Apps (org: Manifest-Startup) | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | read:user, user:email, repo |
| `microsoft` | Microsoft Entra admin center → App registrations | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | openid, email, profile, offline_access, User.Read |
| `slack` | api.slack.com/apps → Create app → OAuth & Permissions | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` | channels:read, chat:write, users:read |
| `notion` | notion.so/my-integrations → Public integration | `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET` | (set in the integration's capabilities) |
| `linkedin` | linkedin.com/developers → Create app → Auth | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | openid, profile, email |
| `stripe` | Stripe Dashboard → Connect → Settings (OAuth) | `STRIPE_CLIENT_ID`, `STRIPE_SECRET_KEY` | read_write |

Verify after each one: `curl -s https://manifeststartup.com/auth/<provider>/start` should no longer return `not_configured` (it needs a signed-in session to return the authorize URL).

## Known gaps

- Tokens are stored but not refreshed: Google and Microsoft access tokens expire after about an hour. Add refresh before any feature calls those APIs with stored tokens.
- The other catalogue partners (Asana, Figma, HubSpot, Shopify, …) have no OAuth handler; they are added as partners by name. Adding one means a new `OAUTH_PROVIDERS` entry plus its app registration.
