"""Open Media adapter: the only Manifest code that talks to Open Media.

Open Media (``api.openmedia.site``) owns conversations, messages, video clips,
likes and comments. Manifest keeps only pointers (the user's linked Open Media
account, ``pitch_reels.om_post_id``). Everything here follows
``docs/OPEN_MEDIA_CONTRACT.md``.

Modules:

- ``settings``  — ``OPEN_MEDIA_*`` environment settings
- ``store``     — the encrypted account link in ``integrations`` (service_id ``open_media``)
- ``client``    — HTTP client: timeouts, retries, access-token refresh
- ``identity``  — "Continue with Open Media" sign-in (OAuth 2.1 + PKCE), account matching and the link
- ``messaging`` — conversations, messages, unread counts, Realtime token
- ``clips``     — video upload, clip posts, likes, comments, reshares, the clips feed
- ``webhooks``  — signed webhook verification, dedupe and cache invalidation
"""
