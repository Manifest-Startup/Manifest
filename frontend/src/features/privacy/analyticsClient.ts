import { createLogger } from "features/core/logError";

import type { PrivacyConsentState } from "./types";

// Type-only import — erased at build time, so it adds nothing to the bundle.
// The real posthog-js module is loaded *lazily* (see loadPostHog) so its
// ~60KB gzip stays off the critical boot path and only downloads once a user
// has actually consented to analytics.
type PostHog = (typeof import("posthog-js"))["default"];

const logger = createLogger("privacy.analytics");

const posthogKey = process.env.REACT_APP_PUBLIC_POSTHOG_KEY || "";
const posthogHost = process.env.REACT_APP_PUBLIC_POSTHOG_HOST || "";
const hasPostHogConfig = Boolean(posthogKey && posthogHost);

// Cap the pre-load buffer so a never-resolving import can't grow unbounded.
const MAX_PENDING_EVENTS = 50;

let initialized = false;
let analyticsEnabled = false;
let posthog: PostHog | null = null;
let loadPromise: Promise<PostHog | null> | null = null;
const pendingEvents: Array<{ event: string; properties?: Record<string, unknown> }> = [];

function loadPostHog(): Promise<PostHog | null> {
  if (loadPromise) {
    return loadPromise;
  }
  loadPromise = import("posthog-js")
    .then((mod) => {
      posthog = mod.default;
      return posthog;
    })
    .catch((error) => {
      logger.warn("Failed to load posthog-js; analytics disabled for this session.", error);
      return null;
    });
  return loadPromise;
}

function flushPendingEvents(ph: PostHog): void {
  while (pendingEvents.length > 0) {
    const queued = pendingEvents.shift();
    if (queued) {
      ph.capture(queued.event, queued.properties);
    }
  }
}

function ensurePostHogInitialized(): void {
  if (typeof window === "undefined" || !hasPostHogConfig || initialized) {
    return;
  }
  void loadPostHog().then((ph) => {
    if (!ph || initialized) {
      return;
    }
    ph.init(posthogKey, {
      api_host: posthogHost,
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      disable_session_recording: true,
      persistence: "localStorage+cookie",
      cross_subdomain_cookie: false,
    });
    initialized = true;
    if (analyticsEnabled) {
      ph.opt_in_capturing();
      flushPendingEvents(ph);
    } else {
      ph.opt_out_capturing();
      pendingEvents.length = 0;
    }
  });
}

export function hasAnalyticsConfiguration(): boolean {
  return hasPostHogConfig;
}

export function canCaptureAnalytics(): boolean {
  return analyticsEnabled && initialized;
}

export function syncAnalyticsConsent(consent: PrivacyConsentState): void {
  analyticsEnabled = Boolean(
    consent.hasStoredPreference && consent.analyticsEnabled && !consent.doNotSellOrShare,
  );

  if (!hasPostHogConfig || typeof window === "undefined") {
    if (!hasPostHogConfig && process.env.NODE_ENV !== "production") {
      logger.warn(
        "[Manifest] Warning: PostHog environment variables are missing. Please set REACT_APP_PUBLIC_POSTHOG_KEY and REACT_APP_PUBLIC_POSTHOG_HOST in a .env file.",
      );
    }
    return;
  }

  if (!analyticsEnabled) {
    pendingEvents.length = 0;
    if (initialized && posthog) {
      posthog.opt_out_capturing();
    }
    return;
  }

  // Consent granted: lazy-load + initialize PostHog (no-op if already done).
  if (initialized && posthog) {
    posthog.opt_in_capturing();
  } else {
    ensurePostHogInitialized();
  }
}

export function captureAnalyticsEvent(event: string, properties?: Record<string, unknown>): void {
  if (!analyticsEnabled) {
    return;
  }
  if (initialized && posthog) {
    posthog.capture(event, properties);
    return;
  }
  // Enabled but PostHog is still loading — buffer and flush on init so the
  // first events after consent aren't dropped.
  if (pendingEvents.length < MAX_PENDING_EVENTS) {
    pendingEvents.push({ event, properties });
  }
  ensurePostHogInitialized();
}
