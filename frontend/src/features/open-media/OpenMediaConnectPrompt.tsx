import React from "react";

import { OPEN_MEDIA_CONNECT_URL } from "./useOpenMediaLink";

interface OpenMediaConnectPromptProps {
  /** What connecting unlocks, e.g. "message founders". */
  purpose: string;
  reconnect?: boolean;
  connectUrl?: string;
  compact?: boolean;
}

/** One-tap "Connect Open Media" prompt shown where Open Media features need a linked account. */
const OpenMediaConnectPrompt: React.FC<OpenMediaConnectPromptProps> = ({
  purpose,
  reconnect = false,
  connectUrl = OPEN_MEDIA_CONNECT_URL,
  compact = false,
}) => (
  <div
    className={`manifest-empty text-center ${compact ? "px-4 py-4" : "px-6 py-10"}`}
    data-testid="open-media-connect-prompt"
  >
    <p className="text-sm font-semibold text-neutral900 dark:text-white">
      {reconnect ? "Reconnect Open Media" : "Connect Open Media"}
    </p>
    <p className="mx-auto mt-2 max-w-sm text-sm text-gray500 dark:text-gray400">
      {reconnect
        ? `Your Open Media connection expired. Reconnect it to ${purpose}.`
        : `Manifest uses your Open Media account to ${purpose}.`}
    </p>
    <a
      className="manifest-control manifest-control-primary mt-4 inline-flex"
      href={connectUrl}
      data-testid="open-media-connect-link"
    >
      {reconnect ? "Reconnect Open Media" : "Connect Open Media"}
    </a>
  </div>
);

export default OpenMediaConnectPrompt;
