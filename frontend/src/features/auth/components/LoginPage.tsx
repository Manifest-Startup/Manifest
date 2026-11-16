import React from "react";
import { useReactiveVar } from "@apollo/client/react";
import { Link, useLocation } from "react-router-dom";

import { trackEvent } from "features/analytics/projectAnalytics";
import { clearLogoutRedirectInProgress } from "features/auth/logout";
import { useStartGuestSession } from "features/auth/hooks/useStartGuestSession";
import { openMediaSignInUrl, signInErrorMessage } from "features/auth/openMediaSignIn";
import { userVar } from "features/core/apollo/localState";

interface LoginLocationState {
  from?: { pathname?: string; search?: string };
}

/** The Open Media mark, drawn dark on light and light on dark. */
export const OpenMediaMark: React.FC<{ className?: string }> = ({ className = "h-5 w-5" }) => (
  <>
    <img src="/brand/open-media-mark-light.png" alt="" aria-hidden="true" className={`${className} dark:hidden`} />
    <img src="/brand/open-media-mark-dark.png" alt="" aria-hidden="true" className={`${className} hidden dark:block`} />
  </>
);

/**
 * Sign in to Manifest. Open Media is the only identity provider: one account for
 * Manifest and Open Media, with passkeys, email links or a password.
 */
const LoginPage: React.FC = () => {
  const location = useLocation();
  const { start: startGuest, loading: guestLoading } = useStartGuestSession("login");
  const [redirecting, setRedirecting] = React.useState(false);
  // A guest who opens this page already has a workspace: signing in merges it.
  const { isGuest } = useReactiveVar(userVar);

  const error = React.useMemo(
    () => signInErrorMessage(new URLSearchParams(location.search).get("error")),
    [location.search],
  );

  React.useEffect(() => {
    clearLogoutRedirectInProgress();
  }, []);

  const from = (location.state as LoginLocationState | null)?.from;
  // `/login?next=/path` (e.g. the Manifest CLI approval page) works like a redirect state.
  const nextParam = new URLSearchParams(location.search).get("next") ?? undefined;
  const next = from?.pathname ? `${from.pathname}${from.search ?? ""}` : nextParam;

  const onContinue = () => {
    setRedirecting(true);
    trackEvent("auth_started", { method: "open_media" });
  };

  return (
    <div className="manifest-page manifest-page-auth">
      <div className="manifest-auth-shell px-4">
        <section className="flex flex-col items-center py-10 text-center" aria-labelledby="login-title">
          <Link to="/" className="flex items-center gap-3" aria-label="Manifest home">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-neutral900 text-sm font-bold text-white dark:bg-white dark:text-neutral900">
              M
            </span>
            <span className="text-lg font-bold tracking-[-0.02em] text-theme-primary">Manifest</span>
          </Link>

          <h1 id="login-title" className="manifest-page-title mt-10">
            Sign in to Manifest
          </h1>
          <p className="mt-3 max-w-sm text-sm leading-6 text-theme-secondary">
            One account for Manifest and Open Media. Sign in with a passkey, email link or password.
          </p>

          {error ? (
            <p
              role="alert"
              className="mt-6 w-full rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
            >
              {error}
            </p>
          ) : null}

          <a
            href={openMediaSignInUrl(next)}
            onClick={onContinue}
            aria-busy={redirecting}
            data-testid="continue-with-open-media"
            className="mt-8 inline-flex w-full items-center justify-center gap-3 rounded-full bg-neutral900 px-6 py-3.5 text-[0.95rem] font-semibold text-white transition hover:bg-neutral800 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral900 focus-visible:ring-offset-2 dark:bg-white dark:text-neutral900 dark:hover:bg-stone100 dark:focus-visible:ring-white dark:focus-visible:ring-offset-neutral900"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white dark:bg-neutral900">
              <OpenMediaMark className="h-4 w-4" />
            </span>
            {redirecting ? "Opening Open Media…" : "Continue with Open Media"}
          </a>

          {isGuest ? (
            <Link
              to="/ideas"
              data-testid="back-to-guest-workspace"
              className="mt-4 text-sm font-semibold text-theme-secondary underline-offset-4 hover:text-theme-primary hover:underline"
            >
              Keep trying without an account
            </Link>
          ) : (
            <button
              type="button"
              onClick={startGuest}
              disabled={guestLoading}
              data-testid="try-without-account"
              className="mt-4 text-sm font-semibold text-theme-secondary underline-offset-4 hover:text-theme-primary hover:underline disabled:opacity-60"
            >
              {guestLoading ? "Opening a guest workspace…" : "Try without an account"}
            </button>
          )}

          <p className="mt-10 text-xs leading-6 text-gray500 dark:text-gray400">
            By continuing, you agree to our{" "}
            <Link to="/legal/terms" className="font-semibold underline-offset-2 hover:underline">
              Terms of Service
            </Link>{" "}
            and acknowledge our{" "}
            <Link to="/legal/privacy" className="font-semibold underline-offset-2 hover:underline">
              Privacy Policy
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
};

export default LoginPage;
