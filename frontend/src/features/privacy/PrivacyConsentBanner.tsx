import React from "react";

import Button from "features/common-ui/Button";

import PrivacyPreferenceFields, { buildDraftFromConsent } from "./PrivacyPreferenceFields";
import { usePrivacyConsent } from "./PrivacyConsentContext";
import type { PrivacyConsentUpdate } from "./types";

const PrivacyConsentBanner: React.FC = () => {
  const { consent, loading, saving, updateConsent } = usePrivacyConsent();
  const [expanded, setExpanded] = React.useState(false);
  const [draft, setDraft] = React.useState<PrivacyConsentUpdate>(buildDraftFromConsent(consent));

  React.useEffect(() => {
    setDraft(buildDraftFromConsent(consent));
  }, [consent]);

  if (loading || consent.hasStoredPreference) {
    return null;
  }

  const acceptEssentialOnly = async () => {
    await updateConsent({
      analyticsEnabled: false,
      communicationsEnabled: false,
      doNotSellOrShare: true,
      source: "banner_essential_only",
    });
  };

  const acceptAll = async () => {
    await updateConsent({
      analyticsEnabled: true,
      communicationsEnabled: true,
      doNotSellOrShare: false,
      source: "banner_accept_all",
    });
  };

  const saveDraft = async () => {
    await updateConsent({
      ...draft,
      source: "banner_manage",
    });
  };

  return (
    <div className="fixed inset-x-0 bottom-[calc(env(safe-area-inset-bottom)+1rem)] z-50 px-4 sm:px-6" data-testid="privacy-consent-banner">
      <div className="mx-auto max-w-5xl rounded-3xl border border-stone200 bg-white/95 p-4 shadow-panel backdrop-blur dark:border-neutral700 dark:bg-neutral900/95">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Privacy choices</p>
            <p className="mt-2 text-sm font-semibold text-neutral900 dark:text-white">
              Manifest uses only essential storage by default. Optional analytics and outreach stay off until you choose them.
            </p>
            <p className="mt-2 text-sm leading-6 text-gray500 dark:text-gray400">
              You can keep only the essentials, accept all optional data uses, or tailor the choices here and later in Account settings.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => void acceptEssentialOnly()} disabled={saving}>
              Essential only
            </Button>
            <Button type="button" variant="secondary" onClick={() => setExpanded((current) => !current)} disabled={saving}>
              {expanded ? "Hide options" : "Manage"}
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={() => void acceptAll()}
              disabled={saving}
              className="shadow-none ring-1 ring-stone200/70 dark:ring-neutral700/70"
            >
              Accept all
            </Button>
          </div>
        </div>
        {expanded ? (
          <div className="mt-4 border-t border-stone200 pt-4 dark:border-neutral700">
            <PrivacyPreferenceFields draft={draft} onChange={setDraft} />
            <div className="mt-4 flex justify-end">
              <Button
                type="button"
                variant="primary"
                onClick={() => void saveDraft()}
                disabled={saving}
                className="shadow-none ring-1 ring-stone200/70 dark:ring-neutral700/70"
              >
                {saving ? "Saving..." : "Save privacy choices"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default PrivacyConsentBanner;
