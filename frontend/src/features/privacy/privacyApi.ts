import { defaultPrivacyConsentState, type PrivacyConsentState, type PrivacyConsentUpdate } from "./types";

function pick<T>(payload: Record<string, unknown>, camelKey: string, snakeKey: string): T | undefined {
  if (camelKey in payload) {
    return payload[camelKey] as T | undefined;
  }
  return payload[snakeKey] as T | undefined;
}

function normalizeConsentState(payload: Partial<PrivacyConsentState> | null | undefined): PrivacyConsentState {
  const source = (payload || {}) as Record<string, unknown>;
  return {
    ...defaultPrivacyConsentState,
    hasStoredPreference: Boolean(pick(source, "hasStoredPreference", "has_stored_preference")),
    necessaryEnabled: true,
    analyticsEnabled: Boolean(pick(source, "analyticsEnabled", "analytics_enabled")),
    communicationsEnabled: Boolean(pick(source, "communicationsEnabled", "communications_enabled")),
    doNotSellOrShare: Boolean(pick(source, "doNotSellOrShare", "do_not_sell_or_share")),
    policyVersion:
      pick<string>(source, "policyVersion", "policy_version") || defaultPrivacyConsentState.policyVersion,
    consentUpdatedAt:
      pick<string>(source, "consentUpdatedAt", "consent_updated_at") || null,
    source:
      (pick<string>(source, "source", "source") || defaultPrivacyConsentState.source),
  };
}

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    throw new Error(`Privacy request failed with status ${response.status}`);
  }
  return response.json();
}

export async function fetchPrivacyConsent(): Promise<PrivacyConsentState> {
  const response = await fetch("/api/privacy/consent", {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });
  return normalizeConsentState(await readJson(response) as Partial<PrivacyConsentState>);
}

export async function savePrivacyConsent(update: PrivacyConsentUpdate): Promise<PrivacyConsentState> {
  const response = await fetch("/api/privacy/consent", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(update),
  });
  return normalizeConsentState(await readJson(response) as Partial<PrivacyConsentState>);
}
