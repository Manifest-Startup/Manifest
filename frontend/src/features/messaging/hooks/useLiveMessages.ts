import { useCallback } from "react";
import { useApolloClient } from "@apollo/client/react";

import {
  GET_CONVERSATION_MESSAGES,
  GET_MY_CONVERSATIONS,
  GET_UNREAD_MESSAGE_COUNT,
} from "features/core/apollo/queries";
import { useOpenMediaRealtime } from "features/open-media/useOpenMediaRealtime";

/** Fallback poll for message lists when Realtime is unavailable (Realtime does the live work). */
export const MESSAGES_FALLBACK_POLL_MS = 5 * 60_000;

/** Refetch the inbox, open threads and the unread badge whenever Open Media reports a message change. */
export function useLiveMessages(enabled: boolean): void {
  const client = useApolloClient();
  const refresh = useCallback(() => {
    void client.refetchQueries({
      include: [GET_MY_CONVERSATIONS, GET_CONVERSATION_MESSAGES, GET_UNREAD_MESSAGE_COUNT],
    });
  }, [client]);
  useOpenMediaRealtime(enabled, refresh);
}
