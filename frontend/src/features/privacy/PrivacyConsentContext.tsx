import React from "react";

import { initWebVitals } from "reportWebVitals";

import { captureAnalyticsEvent, canCaptureAnalytics, hasAnalyticsConfiguration, syncAnalyticsConsent } from "./analyticsClient";
import { fetchPrivacyConsent, savePrivacyConsent } from "./privacyApi";
import { defaultPrivacyConsentState, type PrivacyConsentState, type PrivacyConsentUpdate } from "./types";

const STORAGE_KEY = "manifest.privacy-consent.v1";

interface PrivacyConsentContextValue {
  consent: PrivacyConsentState;
  loading: boolean;
  saving: boolean;
  updateConsent: (update: PrivacyConsentUpdate) => Promise<PrivacyConsentState>;
  refreshConsent: () => Promise<void>;
}

const PrivacyConsentContext = React.createContext<PrivacyConsentContextValue | undefined>(undefined);

function readStoredConsent(): PrivacyConsentState {
  if (typeof window === "undefined") {
    return defaultPrivacyConsentState;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return defaultPrivacyConsentState;
    }
    const parsed = JSON.parse(raw) as PrivacyConsentState;
    return { ...defaultPrivacyConsentState, ...parsed };
  } catch {
    return defaultPrivacyConsentState;
  }
}

function writeStoredConsent(consent: PrivacyConsentState): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
}

export const PrivacyConsentProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [consent, setConsent] = React.useState<PrivacyConsentState>(() => readStoredConsent());
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const webVitalsStartedRef = React.useRef(false);

  const refreshConsent = React.useCallback(async () => {
    const serverConsent = await fetchPrivacyConsent();
    setConsent(serverConsent);
    writeStoredConsent(serverConsent);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    fetchPrivacyConsent()
      .then((serverConsent) => {
        if (cancelled) {
          return;
        }
        setConsent(serverConsent);
        writeStoredConsent(serverConsent);
      })
      .catch(() => {
        if (!cancelled) {
          writeStoredConsent(consent);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    syncAnalyticsConsent(consent);
    if (!webVitalsStartedRef.current && canCaptureAnalytics()) {
      webVitalsStartedRef.current = true;
      initWebVitals();
      captureAnalyticsEvent("privacy_consent_applied", {
        analytics_enabled: consent.analyticsEnabled,
        do_not_sell_or_share: consent.doNotSellOrShare,
        source: consent.source,
      });
    }
  }, [consent]);

  const updateConsent = React.useCallback(
    async (update: PrivacyConsentUpdate) => {
      const previous = consent;
      const optimistic: PrivacyConsentState = {
        ...consent,
        ...update,
        hasStoredPreference: true,
        consentUpdatedAt: new Date().toISOString(),
        source: update.source || consent.source,
      };
      setSaving(true);
      setConsent(optimistic);
      writeStoredConsent(optimistic);
      try {
        const saved = await savePrivacyConsent(update);
        setConsent(saved);
        writeStoredConsent(saved);
        return saved;
      } catch (error) {
        setConsent(previous);
        writeStoredConsent(previous);
        throw error;
      } finally {
        setSaving(false);
      }
    },
    [consent],
  );

  const value = React.useMemo<PrivacyConsentContextValue>(
    () => ({
      consent,
      loading,
      saving,
      updateConsent,
      refreshConsent,
    }),
    [consent, loading, saving, updateConsent, refreshConsent],
  );

  return <PrivacyConsentContext.Provider value={value}>{children}</PrivacyConsentContext.Provider>;
};

export function usePrivacyConsent(): PrivacyConsentContextValue {
  const context = React.useContext(PrivacyConsentContext);
  if (!context) {
    throw new Error("usePrivacyConsent must be used within PrivacyConsentProvider");
  }
  return context;
}

export function useAnalyticsAvailability(): { configured: boolean; enabled: boolean } {
  return {
    configured: hasAnalyticsConfiguration(),
    enabled: canCaptureAnalytics(),
  };
}
