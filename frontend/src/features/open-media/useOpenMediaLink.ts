import { useQuery, useReactiveVar } from "@apollo/client/react";

import { userVar } from "features/core/apollo/localState";
import { GET_OPEN_MEDIA_LINK } from "features/core/apollo/queries";
import type { OpenMediaLinkStatus } from "features/core/apollo/operationTypes";

export const OPEN_MEDIA_CONNECT_URL = "/api/integrations/open-media/connect";

export interface OpenMediaLinkState {
  loading: boolean;
  /** Open Media features exist on this server (false hides Messages and Pitch Shorts). */
  enabled: boolean;
  /** Linked and usable (not waiting for a reconnect). */
  ready: boolean;
  status: OpenMediaLinkStatus | null;
  connectUrl: string;
}

/** Whether Messages and Pitch Shorts can be used, and how to connect Open Media if not. */
export function useOpenMediaLink(): OpenMediaLinkState {
  const { isLoggedIn } = useReactiveVar(userVar);
  const { data, loading } = useQuery(GET_OPEN_MEDIA_LINK, {
    skip: !isLoggedIn,
    fetchPolicy: "cache-first",
  });
  const status = data?.openMediaLink ?? null;
  return {
    loading: isLoggedIn && loading && !status,
    // Unknown (still loading, logged out, or an error) counts as enabled so nothing flickers away.
    enabled: status ? status.enabled : true,
    ready: Boolean(status?.enabled && status.linked && !status.needsReconnect),
    status,
    connectUrl: status?.connectUrl || OPEN_MEDIA_CONNECT_URL,
  };
}
