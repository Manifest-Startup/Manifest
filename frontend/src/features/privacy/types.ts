export interface PrivacyConsentState {
  hasStoredPreference: boolean;
  necessaryEnabled: true;
  analyticsEnabled: boolean;
  communicationsEnabled: boolean;
  doNotSellOrShare: boolean;
  policyVersion: string;
  consentUpdatedAt: string | null;
  source: string;
}

export interface PrivacyConsentUpdate {
  analyticsEnabled: boolean;
  communicationsEnabled: boolean;
  doNotSellOrShare: boolean;
  source?: string;
}

export const defaultPrivacyConsentState: PrivacyConsentState = {
  hasStoredPreference: false,
  necessaryEnabled: true,
  analyticsEnabled: false,
  communicationsEnabled: false,
  doNotSellOrShare: false,
  policyVersion: "2026-04",
  consentUpdatedAt: null,
  source: "default",
};
