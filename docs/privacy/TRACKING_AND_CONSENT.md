# Tracking and Consent

Last updated: **April 18, 2026**

This document describes how Manifest handles optional analytics, customer outreach preferences, and browser-level consent in the product. It is an engineering reference, not legal advice.

## Goals

- Keep the default experience minimal: only essential storage works before a user chooses anything.
- Separate operationally necessary cookies from optional analytics and outreach.
- Record a policy version and timestamp whenever a privacy choice is saved.
- Give signed-in and anonymous visitors one consistent privacy surface.

## Current consent categories

### Strictly necessary

Always enabled. These support:

- Session and authentication cookies
- Security controls such as CSRF/session handling
- The first-party preference cookie that remembers a privacy choice

### Product analytics

Optional. When enabled, Manifest can:

- Initialize PostHog in the browser
- Capture survey CTA events and web-vitals events
- Set the analytics-scoped `visitor_id` cookie
- Log first-visit customer rows through the visitor middleware
- Capture selected server-side analytics events that now fail closed without consent

### Product updates and research follow-up

Optional. This stores a user preference for outreach. It does not block direct replies to a message a visitor already sent through the contact form or survey.

### Do not sell or share my personal information

Optional CPRA-style opt-out. When enabled, optional analytics remains off even if the analytics toggle was previously on.

## Data model

### Browser cookies

- `manifest_privacy_consent`: first-party consent payload used by the frontend and backend
- `manifest_privacy_visitor`: first-party browser identifier used only to persist anonymous privacy choices
- `visitor_id`: analytics-scoped identifier, present only when optional analytics is enabled

### Database

`privacy_consents` stores an audit trail with:

- `user_id` when authenticated
- `visitor_id` for anonymous browsers
- `policy_version`
- `analytics_enabled`
- `communications_enabled`
- `do_not_sell_or_share`
- `consent_payload`
- `ip_hash` (salted one-way hash, not raw IP)
- `consent_updated_at`

## Runtime flow

1. A fresh visitor lands on the site with no optional analytics enabled.
2. The frontend requests `GET /api/privacy/consent`.
3. If no saved preference exists, the privacy banner appears.
4. When the user saves a choice, the frontend calls `POST /api/privacy/consent`.
5. The backend writes the audit row, updates cookies, and the frontend syncs PostHog accordingly.
6. Visitor logging and optional server-side analytics run only when consent allows them.

## Files to know

- `frontend/src/features/privacy/PrivacyConsentContext.tsx`
- `frontend/src/features/privacy/PrivacyConsentBanner.tsx`
- `frontend/src/features/privacy/analyticsClient.ts`
- `frontend/src/features/account/components/PrivacyControlsPanel.tsx`
- `backend/app/routes/privacy_routes.py`
- `backend/app/services/compliance/privacy_consent.py`
- `backend/app/routes/customer_routes.py`
- `backend/app/main.py`
- `supabase/migrations/20260418120000_privacy_consents.sql`

## Operational checklist

- Keep the policy version in sync with customer-facing disclosures when the legal text changes.
- Review PostHog project region and DPA status during privacy/vendor reviews.
- Confirm the privacy banner still appears for fresh browsers after significant bootstrap changes.
- Re-run backend privacy tests, frontend privacy tests, and Cypress privacy coverage before shipping changes to this area.
