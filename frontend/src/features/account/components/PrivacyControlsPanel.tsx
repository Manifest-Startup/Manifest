import React from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import { GET_PRIVACY_STATUS, REQUEST_ACCOUNT_DELETION } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import PrivacyPreferenceFields, { buildDraftFromConsent } from "features/privacy/PrivacyPreferenceFields";
import { usePrivacyConsent } from "features/privacy/PrivacyConsentContext";
import type { PrivacyConsentUpdate } from "features/privacy/types";

export type PrivacyPanelPart = "consent" | "retention" | "deletion";

const ALL_PARTS: PrivacyPanelPart[] = ["retention", "consent", "deletion"];

/**
 * Privacy choices, retention and account deletion. `parts` lets a page show
 * them separately (Settings puts deletion in its own danger card); `embedded`
 * drops the inner cards when the parent already provides one.
 */
const PrivacyControlsPanel: React.FC<{
  accountEmail?: string | null;
  parts?: PrivacyPanelPart[];
  embedded?: boolean;
}> = ({ accountEmail, parts = ALL_PARTS, embedded = false }) => {
  const { setMessage } = useMessage();
  const { data, loading, refetch } = useQuery(GET_PRIVACY_STATUS);
  const [requestDeletion, { loading: deletionLoading }] = useMutation(REQUEST_ACCOUNT_DELETION);
  const { consent, loading: consentLoading, saving: consentSaving, updateConsent } = usePrivacyConsent();
  // Typed by the person, never prefilled, so deletion can't be a single accidental click.
  const [confirmEmail, setConfirmEmail] = React.useState("");
  const [draft, setDraft] = React.useState<PrivacyConsentUpdate>(buildDraftFromConsent(consent));

  React.useEffect(() => {
    setDraft(buildDraftFromConsent(consent));
  }, [consent]);

  const privacyStatus = data?.privacyStatus;
  const emailMatches = accountEmail
    ? confirmEmail.trim().toLowerCase() === accountEmail.trim().toLowerCase()
    : confirmEmail.trim().length > 0;
  const block = embedded ? "" : "manifest-card px-5 py-5";
  const show = (part: PrivacyPanelPart) => parts.includes(part);

  const handleDeletionRequest = async () => {
    try {
      await requestDeletion({
        variables: { confirmEmail },
      });
      await refetch();
      setMessage("Deletion request recorded. Your browser session was cleared and support can complete the removal flow.", "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not submit the deletion request.", "error");
    }
  };

  const handleConsentSave = async () => {
    try {
      await updateConsent({
        ...draft,
        source: "account_privacy_panel",
      });
      setMessage("Privacy choices updated.", "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not update privacy choices.", "error");
    }
  };

  const retention = (
    <div className={block} key="retention">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">Retention at a glance</p>
      {loading ? (
        <p className="mt-3 text-sm text-gray500 dark:text-gray400">Loading privacy settings…</p>
      ) : (
        <div className="mt-3 grid gap-3">
          <div className="rounded-lg border border-stone200 bg-white px-4 py-4 dark:border-neutral700 dark:bg-neutral900">
            <p className="text-xs font-medium text-gray500 dark:text-gray400">Guest workspaces</p>
            <p className="mt-2 text-sm font-semibold text-neutral900 dark:text-white">
              {privacyStatus?.guestRetentionDays ?? 30} day retention window
            </p>
          </div>
        </div>
      )}
      {privacyStatus?.deletionRequestedAt ? (
        <p className="mt-4 text-sm font-medium text-amber-600 dark:text-amber-400">
          Deletion requested on {new Date(privacyStatus.deletionRequestedAt).toLocaleString()}.
        </p>
      ) : null}
    </div>
  );

  const consentBlock = (
    <div className={block} key="consent">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">Tracking and outreach</p>
      <p className="mt-2 text-sm leading-6 text-gray500 dark:text-gray400">
        Choose whether Manifest can use optional analytics to improve onboarding and whether we can contact you about product updates or research follow-up. Essential cookies remain on so sessions and security continue to work.
      </p>
      <p className="mt-2 text-xs leading-5 text-gray500 dark:text-gray400">
        Read the public{" "}
        <Link to="/legal/privacy" className="font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200">
          Privacy Policy
        </Link>{" "}
        for the user-facing explanation of these controls.
      </p>
      {consentLoading ? (
        <p className="mt-3 text-sm text-gray500 dark:text-gray400">Loading privacy preferences…</p>
      ) : (
        <>
          <PrivacyPreferenceFields draft={draft} onChange={setDraft} />
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-gray500 dark:text-gray400">
              {consent.hasStoredPreference && consent.consentUpdatedAt
                ? `Last updated ${new Date(consent.consentUpdatedAt).toLocaleString()}`
                : "No optional consent has been recorded yet."}
            </p>
            <Button type="button" variant="secondary" onClick={handleConsentSave} disabled={consentSaving}>
              {consentSaving ? "Saving..." : "Save privacy choices"}
            </Button>
          </div>
        </>
      )}
    </div>
  );

  const deletion = (
    <div className={block} key="deletion">
      {embedded ? null : <p className="text-sm font-semibold text-neutral900 dark:text-white">Delete account</p>}
      <p className={`${embedded ? "" : "mt-2 "}text-sm leading-6 text-gray500 dark:text-gray400`}>
        Export your workspace before continuing. Type your account email to confirm the request. Your Open Media
        account is not affected.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <Input
          type="email"
          label="Confirm account email"
          placeholder={accountEmail || "you@example.com"}
          autoComplete="off"
          value={confirmEmail}
          onChange={(event) => setConfirmEmail(event.target.value)}
        />
        <Button
          type="button"
          variant="secondary"
          className="!text-red-600 dark:!text-red-400"
          onClick={handleDeletionRequest}
          disabled={deletionLoading || !emailMatches}
        >
          {deletionLoading ? "Submitting..." : "Request account deletion"}
        </Button>
      </div>
    </div>
  );

  const blocks: Record<PrivacyPanelPart, React.ReactNode> = { consent: consentBlock, retention, deletion };

  return (
    <div className={embedded ? "space-y-6 divide-y divide-theme-primary [&>*+*]:pt-6" : "space-y-6"}>
      {parts.map((part) => blocks[part])}
    </div>
  );
};

export default PrivacyControlsPanel;
