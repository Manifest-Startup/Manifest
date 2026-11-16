import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useApolloClient, useReactiveVar } from "@apollo/client/react";

import { userVar } from "features/core/apollo/localState";
import { GET_IDEAS } from "features/core/apollo/queries";
import { openMediaSignInUrl } from "features/auth/openMediaSignIn";
import { useMessage } from "features/notifications/context/MessageContext";

const GUEST_NUDGE_MS = 8 * 60 * 1000;

/**
 * Dismissible banner + light nudges for try-before-signup guests.
 */
const GuestSessionBanner: React.FC = () => {
  const { isLoggedIn, isGuest } = useReactiveVar(userVar);
  const client = useApolloClient();
  const location = useLocation();
  const { setMessage } = useMessage();
  const [dismissed, setDismissed] = useState(false);
  const timeNudgeSent = useRef(false);
  const signingIn = useRef(false);

  const show = Boolean(isLoggedIn && isGuest && !dismissed);

  useEffect(() => {
    if (!show) {
      return undefined;
    }
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (signingIn.current) {
        return; // leaving for Open Media sign-in keeps the workspace (it is merged on return)
      }
      try {
        const cached = client.readQuery<{ ideas?: { ideaId?: string }[] }>({ query: GET_IDEAS });
        const hasIdeas = (cached?.ideas?.length ?? 0) > 0;
        if (!hasIdeas) {
          return;
        }
      } catch {
        return;
      }
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [client, show]);

  useEffect(() => {
    if (!show || timeNudgeSent.current) {
      return undefined;
    }
    const t = window.setTimeout(() => {
      if (timeNudgeSent.current) {
        return;
      }
      timeNudgeSent.current = true;
      setMessage("Continue with Open Media to keep this workspace permanently.", "info");
    }, GUEST_NUDGE_MS);
    return () => window.clearTimeout(t);
  }, [setMessage, show]);

  if (!show) {
    return null;
  }

  return (
    <div
      className="border-b border-amber-200/90 bg-amber-50/95 px-4 py-3 text-sm text-amber-950 shadow-sm backdrop-blur-sm dark:border-amber-800/80 dark:bg-amber-950/50 dark:text-amber-100"
      role="status"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-medium leading-6">
          You&apos;re trying Manifest without an account. Your work is saved on our servers for this browser session.
          <span className="font-semibold"> Continue with Open Media</span> to keep it forever and unlock publishing,
          messages, and investing.
        </p>
        <div className="flex shrink-0 items-center gap-2">
          {/* A full-page navigation: the sign-in callback merges this guest workspace into the account. */}
          <a
            href={openMediaSignInUrl(`${location.pathname}${location.search}`)}
            onClick={() => {
              signingIn.current = true;
            }}
            data-testid="guest-continue-with-open-media"
            className="rounded-full bg-amber-600 px-4 py-2 text-center text-xs font-bold uppercase tracking-wide text-white hover:bg-amber-700 dark:bg-amber-500 dark:hover:bg-amber-400"
          >
            Continue with Open Media
          </a>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="rounded-full border border-amber-300/80 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100/80 dark:border-amber-700 dark:text-amber-50 dark:hover:bg-amber-900/40"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
};

export default GuestSessionBanner;
