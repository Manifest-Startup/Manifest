# Manifest - Startup Building Platform

## Overview
Manifest is a full-stack web application designed to transform raw ideas into investor-ready startups. It leverages AI to generate essential startup assets such as business models, pitch decks, patents, and legal documents. The platform aims to provide a comprehensive ecosystem for entrepreneurs, featuring AI-powered idea qualification, social networking capabilities, and robust investment tracking, ultimately empowering users to efficiently develop and launch their ventures.

## User Preferences
- Follow DRY/SOLID principles
- Eliminate code duplication
- Keep codebase lean and maintainable

## UX Core Principles
- Extremely simple to understand and use, with no or minimal learning curve
- Extremely robust, with the product inferring intent and handling complexity underneath
- Extremely scalable and low maintenance, with centralized patterns and reusable interaction models

## System Architecture
The application is structured into a React-based frontend and a FastAPI-based backend, communicating via GraphQL and Socket.IO for real-time updates. A key architectural component is the MCP (Model Context Protocol) Server, which exposes the platform's functionalities to external AI agents.

**UI/UX Decisions:**
- **Naming**: Prefer short, self-explanatory labels that are usually one or two words (`Ideas`, `Search`, `Founder`, `Similar Ideas`) over workspace-heavy jargon.
- **Dark Mode System**: Comprehensive dark mode support with `ThemeContext` for 'light', 'dark', or 'system' modes, persisting preferences and syncing with OS settings.
- **Shorts Experience**: Implements an immersive, full-screen startup discovery surface with single-card vertical scrolling and minimal chrome.
- **Voice Agent UI**: A floating voice button triggers a ChatGPT-style modal for voice interactions.
- **Idea publish control** (`IdeaPublishBadge`, also exported as `VerifiedBadge` / `PublishTick`): platform-scale blue verified circle with white check when published; neutral circle with plus when draft; shared hook `useIdeaPublishToggle`.
- **Minimalist Design**: Emphasis on essential buttons and a clean interface to reduce cognitive load.
- **Color Scheme**: Utilizes sky/blue gradients for primary actions and gray for secondary elements.

**Technical Implementations:**
- **Frontend**: React 18 with TypeScript, Apollo Client, Redux Toolkit, and TailwindCSS for styling.
- **Backend**: FastAPI with Strawberry GraphQL, Uvicorn, and Socket.IO.
- **Unified AI Router**: All AI functionality uses `AIRouter` class (`backend/app/services/ai_router.py`) with the native OpenAI API:
  - Single `OPENAI_API_KEY` environment variable for all AI features
  - Shared backend wrapper for chat, JSON-mode responses, embeddings, TTS, and web search
  - Methods: `chat()`, `chat_json()`, `chat_stream()`, `embed()`, `tts()`, `web_search()`
  - Replaces provider-specific branching in the app layer
- **Public API Access**: Provides a REST API at `/api/v1` for programmatic access to idea management and document generation, including API key management, billing tiers, and rate limiting.
- **Manifest AI Voice Agent**: Features a voice-only ideation companion using Web Speech API for input, OpenAI TTS for output, and GPT-4o-mini for intelligent conversation.
- **Publishing System**: Allows users to toggle the public visibility of their ideas, reflected by grey/blue tick indicators and controlling visibility in Shorts.
- **Investment System**: Supports cash and sweat equity investments, cap table management, and a personal portfolio dashboard.
- **Social Features**: Includes user follow/unfollow functionality, idea reactions, comments, and a public Shorts surface.
- **Encrypted Messaging System**: Direct messaging between users for startup collaboration:
  - End-to-end encryption support with public key exchange
  - Conversation threads linked to specific ideas
  - Message types: text, sweat equity offers, investment proposals
  - Real-time updates via Apollo polling (5-10s intervals)
  - Integrated into idea pages and the public Shorts experience
  - Backend: `messaging_service.py` with GraphQL mutations/queries
  - Frontend: `features/messaging/components/` (IdeaOwnerPanel, ChatPanel, ConversationsList, MessageButton)
- **OAuth Implementation**: Supports third-party OAuth integrations (Google, Apple, GitHub, Microsoft, Slack, Notion, LinkedIn, Stripe) with HMAC-SHA256 signed state tokens for security.
- **Native iOS App**: A Swift/SwiftUI native iOS application within the `Manifest Startup/` folder provides full feature parity with the web application, following an MVVM architecture.

**Feature Specifications:**
- **AI-Powered Generation**: Generates business models, pitch decks, patents, and legal documents.
- **Idea Qualification**: AI-driven voice agent assists in qualifying startup ideas.
- **API Key Management**: Secure API key generation, validation, and usage tracking for external integrations.
- **User Authentication**: PostgreSQL-based authentication with bcrypt password hashing, JWT session tokens. Supports email/password signup and OAuth providers (Google, Apple, GitHub). Includes a forgot-password flow: `requestPasswordReset` (rate-limited per email + IP, returns generic response to prevent enumeration) emails a single-use, SHA-256-hashed token with a 30-minute TTL via Resend (`RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `APP_BASE_URL`); `resetPassword` consumes the token, updates the password, bumps `users.password_changed_at`, and returns a fresh JWT. Session JWTs carry a `pwd_iat` claim so any token issued before the most recent password change is rejected on the next request, signing every other device out automatically. If `RESEND_API_KEY` is unset, the reset link is logged to the server console as a dev fallback.
- **LLM Crawler Friendliness**: Platform optimized for AI agent accessibility:
  - `/llms.txt` - Detailed guidance for LLM crawlers (following llmstxt.org standard)
  - `/robots.txt` - Standard crawler guidance with LLM reference
  - `/sitemap.xml` - XML sitemap for content discovery
  - Structured JSON-LD data (Schema.org WebApplication and SoftwareApplication)
  - OpenGraph and Twitter Card meta tags for rich previews

## AI Architecture (AIRouter)
All AI services use the unified `AIRouter` class for consistent API access:

```python
from app.services.ai_router import AIRouter

# Initialize with OpenAI API
router = AIRouter()  # Uses OPENAI_API_KEY from environment

# Chat completion
response = router.chat("Analyze this startup idea")

# JSON response
data = router.chat_json("Return structured data")

# Streaming
for chunk in router.chat_stream("Generate a pitch"):
    print(chunk)

# Text-to-speech
audio = router.tts("Hello world", voice="nova")

# Embeddings
vectors = router.embed(["text1", "text2"])

# Web search (uses OpenAI search-preview models)
results = router.web_search("latest startup trends")
print(results["content"])  # Search results
print(results["citations"])  # Source URLs
```

**Key Features:**
- Single API key (`OPENAI_API_KEY`) for all AI models including web search
- Auto-retry behavior inside the shared router
- Native OpenAI support for chat, embeddings, search-preview, and conversational TTS
- Drop-in replacement for direct API calls

## External Dependencies
- **Database**: Replit PostgreSQL (primary data storage and user authentication)
- **AI Services**: OpenAI API
- **Analytics**: PostHog (optional, for analytics tracking)
- **Third-Party OAuth Providers**: Google, Apple, GitHub, Microsoft, Slack, Notion, LinkedIn, Stripe (for user authentication and integration)

## Team Collaboration Features
**Added: January 2026**

The platform now supports Google Docs-style team collaboration with the following features:

**Access Control (4 Role Levels):**
- **Owner**: Full control including sharing, managing access, transferring ownership, deleting
- **Editor**: Can view, edit, comment, and create versions
- **Commenter**: Can view and add comments (read-only for content)
- **Viewer**: Read-only access to view idea content

**Key Features:**
- **Share Modal**: Invite collaborators by email with role assignment
- **Version History**: Track all changes with automatic snapshots before restoring
- **Access Management**: Update or remove collaborator roles
- **Invitation System**: Pending invitations with accept/decline workflow

**Database Tables:**
- `idea_collaborators`: Tracks who has access to which ideas with their role and invitation status
- `idea_versions`: Stores versioned snapshots of idea content for history and restoration

**Frontend Components:**
- `ShareModal` (`frontend/src/features/collaboration/components/ShareModal.tsx`)
- `VersionHistory` (`frontend/src/features/collaboration/components/VersionHistory.tsx`)
- `CollaborationInvitations` (`frontend/src/features/collaboration/components/CollaborationInvitations.tsx`)

**Backend Services:**
- `CollaborationService` (`backend/app/services/collaboration_service.py`)
- GraphQL queries/mutations in `backend/app/graphql/schema.py`

**UI Design:**
- Minimal interface with only 2 buttons (Share, History) in idea header
- Sky/blue gradient styling consistent with platform design
- Intuitive role badges and status indicators

## Environment Variables
- `OPENAI_API_KEY` - Primary API key for all AI functionality
- `DATABASE_URL` - PostgreSQL connection
- `SESSION_SECRET` - Secret key for JWT session tokens (required for authentication)
- `AI_MODEL` - (Optional) Override default AI model (default: gpt-4o-mini)
- `MFA_ENCRYPTION_KEY` - Required in production: passphrase used by `pgp_sym_encrypt` for TOTP secrets
- `MANIFEST_KEK_V1`, `MANIFEST_KEK_V2`, … - Base64-encoded 32-byte KEKs for envelope encryption (Task #12). Required in production when `MANIFEST_KEK_PROVIDER=env`.
- `MANIFEST_KEK_ACTIVE_VERSION` - Selects which KEK new writes use (default `1`).
- `MANIFEST_KEK_PROVIDER` - One of `env` (default), `aws-kms`, `vault-transit`. Selects how KEK material is fetched (`backend/app/security/kek_provider.py`).
- `MANIFEST_KEK_V<n>_AWS_BLOB` / `MANIFEST_KEK_V<n>_VAULT_CT` - Per-KEK ciphertext blobs for the AWS KMS / Vault Transit providers respectively.
- `MANIFEST_DATA_REGION` - Region this worker serves (default `us`); enforced by `assert_region_match()`.
- `ENCRYPT_INTEGRATIONS_TOKENS` - Feature flag (`1` to enable). When ON, OAuth integration `access_token` / `refresh_token` are AES-GCM encrypted under per-user DEKs.

## Security & Compliance Hardening (Tasks #10–#15)
- **Task #10** — Threat model + compliance gap analysis (see `docs/security/THREAT_MODEL.md`, `COMPLIANCE_GAP_ANALYSIS.md`, `SOC2_READINESS.md`, `FINDINGS_BACKLOG.md`).
- **Task #11** — Identity, access & session hardening: bcrypt API keys + rotation, account lockout, password breach/history, step-up auth, WebAuthn/SAML/OIDC SSO, SCIM 2.0, default-deny GraphQL permissions, MFA + recovery codes (`pgp_sym_encrypt`-stored TOTP secret), session idle/concurrency caps.
- **Task #12** — Data protection, encryption & secrets:
  - `app/security/crypto.py` — KEK/DEK envelope encryption (AES-256-GCM, versioned KEK, fail-closed decrypt).
  - `app/security/kek_provider.py` — pluggable KEK provider (env / AWS KMS / Vault Transit) selected by `MANIFEST_KEK_PROVIDER`.
  - `app/security/tenant_keys.py` — per-tenant wrapped DEK store (`tenant_data_keys`) with `ON CONFLICT` race safety and a cursor-aware crypto-shred (`purge_tenant_keys_with_cursor`).
  - `app/security/data_residency.py` — `data_region` pinning + `assert_region_match()` write-path enforcement; gates wired into `oauth.save_integration`, `enterprise_sso.upsert_tenant`, and `scim.provision_user`.
  - `app/services/integration_token_crypto.py` — field-level encryption for `integrations.access_token/refresh_token` with feature flag, AAD bound to `(user_id, service_id)`, and online backfill that handles half-migrated rows.
  - `app/services/tenant_purge_service.py` — `purge_tenant(tenant_id)` GDPR Art. 17 / CCPA §1798.105 right-to-erasure entry point (atomic crypto-shred + scrub + tombstone + mandatory audit; required-step failure rolls everything back).
  - `backend/scripts/setup_data_protection_tables.py` — idempotent migration for `tenant_data_keys`, `integrations` ciphertext columns, `users.data_region`, `sso_tenant_configs.data_region`, `backup_integrity_checks`. Wired into `_run_startup_migrations()` so it runs on every boot.
  - Docs: `docs/security/DATA_CLASSIFICATION.md`, `ENCRYPTION_AND_KEY_MANAGEMENT.md`, `BACKUP_AND_RESTORE.md`, `DATA_RESIDENCY.md`.
  - Secrets scanning: `.gitleaks.toml` (custom rules for `manifest_sk_*`, `MANIFEST_KEK_V*`, OpenAI keys, PEM blocks) + `.pre-commit-config.yaml`.
  - Note on PII coverage: TOTP secrets are already encrypted via Postgres `pgp_sym_encrypt(MFA_ENCRYPTION_KEY)` from Task #11; `integrations` OAuth tokens are encrypted via this task. Broader PII column coverage (idea content, audit blobs) is intentionally deferred to Task #15 (privacy program) where data-flow mapping drives prioritisation.
- **Task #13** — Application surface hardening primitives:
  - `app/security/security_headers.py` — `SecurityHeadersMiddleware` adding nonce-based CSP (report-only by default; flip via `CSP_ENFORCE=true`), HSTS, COOP/CORP/Permissions-Policy, `frame-ancestors 'none'`. Wired into `main.py` after CORS.
  - `app/security/safe_http.py` — SSRF-safe outbound HTTP (`safe_request` sync + `safe_request_async`); blocks non-HTTP(S) schemes, credentialed URLs, RFC1918/loopback/link-local/cloud-metadata IPs (literal *and* DNS-resolved); re-validates each redirect hop; caps response size.
  - `app/security/rate_limit_policies.py` — tiered policies (AUTH/AI/DOC_GEN/UPLOAD/VOICE/DEFAULT) with per-user + per-IP buckets, weight-based cost, and 429 + Retry-After. Forwarding headers (`X-Forwarded-For`, `X-Real-IP`) are honored only when the immediate peer is in `TRUSTED_PROXY_CIDRS` — direct attackers cannot spoof the limiter identity.
  - `app/security/ai_safety.py` — untrusted-input delimiter wrapping, safety preamble, jailbreak heuristics, PII/secret redactors, `build_safe_messages` helper.
  - `app/graphql/schema.py` — `QueryDepthLimiter(12)`, `MaxAliasesLimiter(30)`, `MaxTokensLimiter(5000)`, `DisableIntrospection` in production (override via `GRAPHQL_INTROSPECTION=true`).
  - Tests: `backend/tests/test_security/{test_security_headers,test_safe_http,test_ai_safety,test_rate_limit_policies,test_graphql_hardening}.py` (72 passing).
  - Operator note: set `TRUSTED_PROXY_CIDRS` (comma-separated CIDRs of the load-balancer/CDN) in production so the rate limiter trusts forwarded IPs from those hops only.
  - Adoption-ready primitives — wiring into existing callers (outbound HTTP, AI services, auth/upload routes, CSRF sweep, file-upload pipeline, Socket.IO per-event throttle) tracked as follow-ups.
- **Task #14** — Audit logging, monitoring & incident response: hash-chained `security_audit_events`, fail-closed writer with PII redaction at the boundary, SIEM mirror, offline verifier with chain-break alerting, retention runner, MFA-bypass detector. (See prior commit for details.)
- **Task #15** — Privacy & compliance program (GDPR/CCPA/HIPAA):
  - `app/routes/dsar_routes.py` — formal DSAR endpoints under `/api/dsar` (access, portability, rectify, object/opt-out, erasure with crypto-shred + tamper-evident deletion certificate). Every endpoint emits a chained audit event.
  - `app/routes/trust_center_routes.py` — public `/api/trust-center` JSON snapshot of frameworks, controls, sub-processors, and DSAR endpoints. Mirrors `docs/security/TRUST_CENTER.md`.
  - `app/services/privacy_jurisdiction.py` — GDPR/CCPA/GPC-aware default consent profile resolved from edge headers (`cf-ipcountry`, `sec-gpc`).
  - `backend/scripts/run_privacy_retention.py` — single nightly retention orchestrator with per-class envvars (password reset / sessions / guests / consent ledger), audit emit on completion.
  - Docs: `docs/privacy/{ROPA,SUB_PROCESSORS,DPIA,BREACH_NOTIFICATION}.md`, `docs/security/{HIPAA_PROGRAM,TRUST_CENTER,DATA_RETENTION}.md`, `legal/{BAA_TEMPLATE,DPA_TEMPLATE,SCC_ANNEX}.md`. Privacy Policy refreshed with §15 (rights), §16 (age gate), §17 (program docs index).
  - Tests: `backend/tests/{test_dsar_routes,test_trust_center_route,test_privacy_jurisdiction,test_run_privacy_retention}.py` — 23 passing alongside the existing privacy suite.
  - Erasure path is built on T3 `tenant_purge_service.purge_tenant` (atomic crypto-shred + scrub + tombstone + audit) — DSAR `/erase` returns the deletion certificate (UUID, completion timestamp, SHA-256 of the per-table counts summary, audit event id).

## Frontend bundling invariants
- `frontend/vite.config.ts` `build.rollupOptions.output.manualChunks` MUST classify Apollo and its runtime peer deps (`rxjs`, `tslib`, `@wry/*`, `optimism`, `ts-invariant`, `hoist-non-react-statics`, `response-iterator`, `zen-observable`, `symbol-observable`) into the `apollo` chunk **before** the `react-vendor` rule. Otherwise Rollup hoists rxjs's `Subscriber`/`Observable` into the React vendor chunk, Apollo (which `class extends` them at module-init) imports them too early, and the page boots blank with `TypeError: Class extends value undefined is not a constructor or null`. `rxjs` is also pinned as a direct frontend dependency so package-manager refreshes can't drop the peer.
