import React from "react";

import { OPEN_MEDIA_SECURITY_URL } from "features/auth/openMediaSignIn";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";

/**
 * How this account signs in. Open Media is Manifest's identity provider, so
 * passkeys, passwords and second factors are managed there. Messages and Pitch
 * Shorts also run on the same Open Media account.
 */
const OpenMediaSection: React.FC = () => {
  const openMedia = useOpenMediaLink();
  const status = openMedia.status;
  const handle = status?.handle ? `@${status.handle}` : null;

  return (
    <div className="space-y-4" data-testid="open-media-section">
      <p className="text-sm text-gray500 dark:text-gray400" aria-live="polite">
        {openMedia.loading
          ? "Checking how you sign in…"
          : status?.linked && status.needsReconnect
            ? `Signed in with Open Media${handle ? ` ${handle}` : ""}. The connection for Messages and Pitch Shorts expired; continue with Open Media again to renew it.`
            : status?.linked
              ? `Signed in with Open Media${handle ? ` ${handle}` : ""}.`
              : "This account isn't linked to Open Media yet. Continue with Open Media to link it."}
      </p>
      {!openMedia.loading && openMedia.enabled === false ? (
        <p className="text-sm text-gray500 dark:text-gray400">Messages and Pitch Shorts are off on this server.</p>
      ) : null}

      {!openMedia.loading ? (
        <div className="flex flex-wrap items-center gap-3">
          {!status?.linked || status.needsReconnect ? (
            <a
              className="manifest-control manifest-control-primary"
              href={openMedia.connectUrl}
              data-testid="open-media-connect-button"
            >
              Continue with Open Media
            </a>
          ) : null}
          <a
            className="manifest-control manifest-control-secondary"
            href={OPEN_MEDIA_SECURITY_URL}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="open-media-security-link"
          >
            Manage sign-in and security
          </a>
        </div>
      ) : null}
    </div>
  );
};

export default OpenMediaSection;
