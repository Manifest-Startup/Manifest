import React, { useMemo, useState } from "react";
import { useMutation } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import { DISCONNECT_OPEN_MEDIA, GET_OPEN_MEDIA_LINK } from "features/core/apollo/queries";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";

const RESULT_MESSAGES: Record<string, { text: string; error?: boolean }> = {
  linked: { text: "Open Media connected. Messages and Pitch Shorts are ready." },
  cancelled: { text: "Open Media sign-in was cancelled.", error: true },
  error: { text: "Open Media sign-in didn't finish. Try again.", error: true },
  full_account_required: { text: "Create a full account to connect Open Media.", error: true },
  disabled: { text: "Open Media isn't available on this server.", error: true },
};

/**
 * "Connect Open Media": messages and pitch shorts run on the user's Open Media account.
 * Linking is an OAuth redirect handled by the backend; this card shows the status.
 */
const OpenMediaSection: React.FC = () => {
  const openMedia = useOpenMediaLink();
  const [error, setError] = useState<string | null>(null);
  const [disconnect, { loading: disconnecting }] = useMutation(DISCONNECT_OPEN_MEDIA, {
    refetchQueries: [{ query: GET_OPEN_MEDIA_LINK }],
  });
  const result = useMemo(() => {
    if (typeof window === "undefined") return null;
    const key = new URLSearchParams(window.location.search).get("open_media");
    return key ? RESULT_MESSAGES[key] ?? null : null;
  }, []);
  const status = openMedia.status;

  const onDisconnect = async () => {
    setError(null);
    try {
      await disconnect();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disconnect. Try again.");
    }
  };

  return (
    <div className="space-y-4" data-testid="open-media-section">
      <p className="text-sm text-gray500 dark:text-gray400" aria-live="polite">
        {openMedia.loading
          ? "Checking your Open Media connection…"
          : !openMedia.enabled
            ? "Open Media isn't available on this server, so Messages and Pitch Shorts are off."
            : status?.linked && status.needsReconnect
              ? `Your connection to @${status.handle} expired. Reconnect to keep messages and shorts working.`
              : status?.linked
                ? `Connected as @${status.handle}.`
                : "Not connected. Connect once to message founders and post pitch shorts."}
      </p>

      {openMedia.enabled && !openMedia.loading ? (
        <div className="flex flex-wrap items-center gap-3">
          {!status?.linked || status.needsReconnect ? (
            <a
              className="manifest-control manifest-control-primary"
              href={openMedia.connectUrl}
              data-testid="open-media-connect-button"
            >
              {status?.needsReconnect ? "Reconnect Open Media" : "Connect Open Media"}
            </a>
          ) : null}
          {status?.linked ? (
            <Button type="button" variant="secondary" onClick={onDisconnect} disabled={disconnecting}>
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </Button>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <p
          role={result.error ? "alert" : "status"}
          className={`text-sm ${result.error ? "text-red-600 dark:text-red-400" : "text-green-700 dark:text-green-400"}`}
        >
          {result.text}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
};

export default OpenMediaSection;
