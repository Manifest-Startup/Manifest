import React from "react";

import type { PrivacyConsentState, PrivacyConsentUpdate } from "./types";

interface PrivacyPreferenceFieldsProps {
  draft: PrivacyConsentUpdate;
  onChange: (draft: PrivacyConsentUpdate) => void;
  dense?: boolean;
  showHelper?: boolean;
}

function ToggleRow({
  checked,
  disabled = false,
  label,
  description,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  description: string;
  onChange?: (value: boolean) => void;
}) {
  return (
    <label className={`flex items-start gap-3 rounded-2xl border border-stone200 bg-white/80 px-4 py-4 dark:border-neutral700 dark:bg-neutral900/80 ${disabled ? "opacity-80" : ""}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={label}
        onChange={(event) => onChange?.(event.target.checked)}
        className="mt-1 h-4 w-4 rounded border-stone300 text-accent-600 focus:ring-accent-200 dark:border-neutral600 dark:bg-neutral900"
      />
      <span className="block">
        <span className="block text-sm font-semibold text-neutral900 dark:text-white">{label}</span>
        <span className="mt-1 block text-sm leading-6 text-gray500 dark:text-gray400">{description}</span>
      </span>
    </label>
  );
}

export const buildDraftFromConsent = (consent: PrivacyConsentState): PrivacyConsentUpdate => ({
  analyticsEnabled: consent.analyticsEnabled,
  communicationsEnabled: consent.communicationsEnabled,
  doNotSellOrShare: consent.doNotSellOrShare,
});

const PrivacyPreferenceFields: React.FC<PrivacyPreferenceFieldsProps> = ({
  draft,
  onChange,
  dense = false,
  showHelper = true,
}) => {
  return (
    <div className={`space-y-3 ${dense ? "" : "mt-4"}`}>
      <ToggleRow
        checked
        disabled
        label="Strictly necessary"
        description="Session, security, and preference cookies that keep the product working and remember this choice."
      />
      <ToggleRow
        checked={draft.analyticsEnabled}
        label="Product analytics"
        description="Measure onboarding, survey completion, and performance so we can improve the workspace without collecting optional data by default."
        onChange={(analyticsEnabled) => onChange({ ...draft, analyticsEnabled })}
      />
      <ToggleRow
        checked={draft.communicationsEnabled}
        label="Product updates and research follow-up"
        description="Allow Manifest to contact you about early access, feedback requests, or launch updates. Turning this off does not block replies to messages you send us."
        onChange={(communicationsEnabled) => onChange({ ...draft, communicationsEnabled })}
      />
      <ToggleRow
        checked={draft.doNotSellOrShare}
        label="Do not sell or share my personal information"
        description="Use this CPRA-style opt-out to stop optional cross-service sharing. When enabled, optional analytics stays off."
        onChange={(doNotSellOrShare) =>
          onChange({
            ...draft,
            doNotSellOrShare,
            analyticsEnabled: doNotSellOrShare ? false : draft.analyticsEnabled,
          })
        }
      />
      {showHelper ? (
        <p className="text-xs leading-5 text-gray500 dark:text-gray400">
          We store the latest privacy choice with a policy version and timestamp so you can revisit it later.
        </p>
      ) : null}
    </div>
  );
};

export default PrivacyPreferenceFields;
