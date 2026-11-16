import { useEffect, useRef } from "react";
import { useApolloClient } from "@apollo/client/react";

import { GET_OPEN_MEDIA_REALTIME_TOKEN } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";

const logger = createLogger("useOpenMediaRealtime");
const REFRESH_EARLY_MS = 60_000;
const DEFAULT_TOKEN_LIFETIME_MS = 15 * 60_000;
const DEBOUNCE_MS = 400;

const expiryDelay = (expiresAt: string | null | undefined): number => {
  if (!expiresAt) return DEFAULT_TOKEN_LIFETIME_MS;
  const numeric = Number(expiresAt);
  const ms = Number.isFinite(numeric)
    ? (numeric < 1e12 ? numeric * 1000 : numeric)
    : new Date(expiresAt).getTime();
  const delay = ms - Date.now() - REFRESH_EARLY_MS;
  return Number.isFinite(delay) ? Math.max(30_000, delay) : DEFAULT_TOKEN_LIFETIME_MS;
};

/**
 * Live message updates from Open Media's Supabase Realtime (RLS limits rows to the user).
 * Calls `onChange` (debounced) when a message row the user can see changes. Callers keep
 * a slow poll as the fallback; any failure here just leaves that poll in charge.
 * `@supabase/supabase-js` is loaded on demand so it never lands in the boot bundle.
 */
export function useOpenMediaRealtime(enabled: boolean, onChange: () => void): void {
  const client = useApolloClient();
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let refreshTimer: number | undefined;
    let debounceTimer: number | undefined;
    let teardown: (() => void) | undefined;

    const notify = () => {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => onChangeRef.current(), DEBOUNCE_MS);
    };

    const connect = async () => {
      try {
        const { data } = await client.query({
          query: GET_OPEN_MEDIA_REALTIME_TOKEN,
          fetchPolicy: "network-only",
        });
        const token = data?.openMediaRealtimeToken;
        if (cancelled || !token?.supabaseUrl || !token.anonKey || !token.accessToken) return;
        const { createClient } = await import("@supabase/supabase-js");
        if (cancelled) return;
        // A third-party access token: supabase-js skips its own auth/session handling.
        const supabase = createClient(token.supabaseUrl, token.anonKey, {
          accessToken: async () => token.accessToken,
        });
        const channel = supabase
          .channel(`manifest-messages-${token.omUserId || "me"}`)
          .on("postgres_changes", { event: "*", schema: "public", table: "messages" }, notify)
          .subscribe();
        teardown = () => {
          void supabase.removeChannel(channel);
          void supabase.realtime.disconnect();
        };
        refreshTimer = window.setTimeout(() => {
          teardown?.();
          teardown = undefined;
          void connect();
        }, expiryDelay(token.expiresAt));
      } catch (error) {
        logger.log("realtime unavailable; polling only", error);
      }
    };

    void connect();
    return () => {
      cancelled = true;
      window.clearTimeout(refreshTimer);
      window.clearTimeout(debounceTimer);
      teardown?.();
    };
  }, [client, enabled]);
}
