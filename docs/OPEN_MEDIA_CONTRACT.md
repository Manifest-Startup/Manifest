# Manifest ⇄ Open Media integration contract (v1)

Base: `https://api.openmedia.site` (local: the URL `npm run local` prints for the Worker). JSON everywhere. Errors: `{error, error_description}` with 4xx/5xx.

## 1. Identity — "Continue with Open Media" for a web app (OAuth 2.1, PKCE, no client secret)
- Since ADR 0002 this is Manifest's **only** sign-in. Manifest sends `login_hint` (an email) when it knows one.
- Manifest is a public OAuth client identified by a **Client ID Metadata Document** URL:
  `client_id = https://manifeststartup.com/oauth/open-media-client.json`
  (doc: `{client_id, client_name:"Manifest", client_uri:"https://manifeststartup.com", redirect_uris:["https://manifeststartup.com/api/auth/open-media/callback"], grant_types:["authorization_code","refresh_token"], response_types:["code"], token_endpoint_auth_method:"none", scope:"account"}`).
  Open Media must accept this client for scope `account` (the "Sign in with Open Media" grant). If CIMD is not supported for this grant, OM adds an allowlist secret `OAUTH_TRUSTED_CLIENTS` instead — but the Manifest side must not change.
- Endpoints (existing provider): `GET /authorize`, `POST /oauth/token` (authorization_code + refresh_token; read `token_endpoint` from discovery), discovery `/.well-known/oauth-authorization-server`. Access token ~1 h, refresh 90 d.
- **REST with OAuth (new):** every `/v1/me/*` route is also reachable as `/v1/connected/me/*` with `Authorization: Bearer <OAuth access token>`. Same request/response bodies. `/v1/me/*` with Supabase session tokens keeps working unchanged.

## 2. Messaging (under `/v1/connected`)
- `GET  /v1/connected/me` → `{id, handle, display_name, avatar_url, email, email_verified, has_profile}`. `email`/`email_verified` come from the session's user; a person without a profile gets `has_profile:false` (no 404). Manifest auto-links an existing account only when `email_verified` is `true`.
- `GET  /v1/connected/me/conversations?app=manifest` → `{conversations:[{id, kind, title, context|null, members:[{id,handle,display_name,avatar_url}], last_message:{id,body,sender_id,created_at}|null, unread_count, updated_at}]}`. `app` filter optional (omit = all).
- `POST /v1/connected/me/conversations` `{handle, context?}` → 201 `{conversation:{…same shape…}}`. Re-uses the existing direct conversation with that person; sets `context` only if the conversation has none. `context` = `{app:"manifest", idea_id:string, title?:string, url?:string}` (≤ 2 KB, validated).
- `GET  /v1/connected/me/conversations/{id}/messages?limit=&before=` → `{messages:[{id, conversation_id, sender_id, body, created_at, reply_to_message_id|null}]}` newest-last.
- `POST /v1/connected/me/conversations/{id}/messages` `{body, client_id?}` (header `Idempotency-Key` also accepted) → 201 `{message:{…}}`.
- `POST /v1/connected/me/conversations/{id}/read` → 200.
- One inbox (Open Media ADR 0044): `GET /v1/connected/me/inbox?limit=`, `GET /v1/connected/me/inbox/{id}`, `POST /v1/connected/me/inbox/{id}/messages` `{body, reply_to_message_id?, client_id?}` and `POST /v1/connected/me/inbox/{id}/read`. Open Media assembles chats and email (one conversation per person or company) with its own app code, lays threads out with email as clean text, and routes replies (chat message, or threaded email from the receiving mailbox). Manifest's Messages page and `myInbox` / `inboxConversation` / `replyInInbox` / `markInboxRead` pass it through and store nothing.
- `POST /v1/connected/me/realtime-token` → `{supabase_url, anon_key, access_token, expires_at}` — the person's own short-lived Supabase access token so a browser can subscribe to Realtime `postgres_changes` on `messages` (RLS-limited).

## 3. Video clips
- `POST /v1/connected/me/media/videos` — raw request body, `Content-Type: video/mp4|video/quicktime|video/webm`, ≤ 100 MB → 201 `{video:{…opaque…}}`. OM stores it in `post-videos/<uid>/…`, computes sha256, strips nothing server-side (Veo output has no location data). The returned `video` object is passed back verbatim.
- `POST /v1/connected/me/posts` `{body, video?, context?, client_id?}` → 201 `{post:{id,…}}`. `video` = object from the upload. `context` same shape as above (`app`, `idea_id`, `title`, `url`).
- `DELETE /v1/connected/me/posts/{id}` → 200 (author only).
- Existing interactions, now also under `/v1/connected`: `POST|DELETE /v1/connected/me/posts/{id}/like`, `GET|POST /v1/connected/me/posts/{id}/comments` (`{body}`), reshare unchanged.
- Public read (no auth): `GET /v1/posts?media=video&app=manifest&limit=` and `GET /v1/feed?kind=clips&app=manifest`. Each post: `{id, body, created_at, author:{id,handle,display_name,avatar_url}, video:{url, poster_url|null, width|null, height|null, duration_ms|null}, context|null, counts:{likes, comments, reshares}}`. With a `/v1/connected` (or Supabase) bearer the same list is at `GET /v1/connected/me/feed?kind=clips&app=manifest` and adds `viewer:{liked:boolean}`.
- `GET /v1/posts/{id}` and `GET /v1/posts/{id}/comments` public.
- Open Media UI shows a small "From Manifest" chip on posts/conversations whose `context.app = "manifest"`, linking to `context.url`.

## 4. Outbound webhooks (new)
- Configured per app by Worker secret `APP_WEBHOOKS` = JSON `{"manifest":{"url":"https://manifeststartup.com/api/webhooks/open-media","secret":"<hex>"}}`.
- DB triggers write to `app_private.app_webhook_outbox` for: `message.created` (conversation has `context.app`), `post.liked`, `post.commented`, `post.deleted` (post has `context.app`). The existing `* * * * *` cron drains it (batch, retry with backoff up to ~24 h, then drop).
- Request: `POST <url>`, headers `Content-Type: application/json`, `X-Open-Media-Event: <type>`, `X-Open-Media-Delivery: <uuid>`, `X-Open-Media-Timestamp: <unix seconds>`, `X-Open-Media-Signature: sha256=<hex HMAC-SHA256(secret, timestamp + "." + raw_body)>`.
- Body (IDs only, never message text): `{id:<delivery uuid>, type, created_at, data:{conversation_id?, message_id?, post_id?, actor_id, recipient_ids:[om user ids], context}}`. Receivers reject timestamps older than 5 min and dedupe on `id`.

## As built (Open Media final API, 2026-11-15)

Differences from the text above that the Manifest adapter (`backend/app/services/integrations/open_media/`) handles:
- Errors: `/v1/connected/*` and `/oauth/token` use `{error, error_description}`; public `/v1/posts` and `/v1/feed` use `{error:{code,message}}`.
- Containers: public lists are `{data:[post…]}` (`/v1/feed?app=` adds `app, kind, nextCursor, next`); `GET conversations` → read `conversations`; `POST conversations` → `{id, with, conversation}`; `POST messages` → `{sent, conversationId, message}`; `POST posts` returns the post at the top level and under `post`. Posts carry extra camelCase fields, which are ignored.
- Video upload: `Content-Length` required (411), body must match the declared type (415), optional `?duration_ms=&width=&height=` (422 possible without `moov` metadata), up to 180 s. Response `{video:{path, posterPath, durationSeconds, width, height, contentType, sha256, sizeBytes, url}}`, passed back verbatim.
- `context`: keys limited to `app`, `idea_id`, `title`, `url` (≤ 2 KB); `url` must be https on manifeststartup.com or a subdomain.
- Webhook HMAC key is the UTF-8 bytes of the secret string (not hex-decoded). `post.commented` also carries `comment_id`; `recipient_ids` excludes the actor.
- Messages: `limit` 1–200, `before` = message id or ISO time. Realtime `expires_at` is unix seconds.
- Likes: `POST` and `DELETE` on `/like` (the adapter falls back to `PUT` on 405).
