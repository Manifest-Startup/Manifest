/**
 * "Continue with Open Media" is Manifest's only way to sign in. The backend
 * route redirects to Open Media and back (OAuth 2.1 + PKCE), merges a guest
 * workspace if the browser has one, and sets the session cookie.
 */
export const OPEN_MEDIA_START_PATH = "/api/auth/open-media/start";

/** Where people manage passkeys, passwords and second factors (Open Media). */
export const OPEN_MEDIA_SECURITY_URL = "https://openmedia.site/signin";

/** The sign-in URL; ``next`` is where to land afterwards (a same-origin path). */
export function openMediaSignInUrl(next?: string): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) {
    return OPEN_MEDIA_START_PATH;
  }
  return `${OPEN_MEDIA_START_PATH}?${new URLSearchParams({ next }).toString()}`;
}

/** Messages for ``/login?error=<code>`` (codes come from the callback). */
export const SIGN_IN_ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled. Continue with Open Media when you're ready.",
  unverified_email: "Confirm your email address in Open Media, then continue again.",
  no_email: "Your Open Media account has no email address yet. Add one in Open Media, then continue again.",
  linked_elsewhere: "That Open Media account is linked to a different Manifest account.",
  account_disabled: "This Manifest account is disabled. Contact support if you think that's a mistake.",
  invalid_state: "That sign-in link was started in another browser or tab. Please try again.",
  expired: "That sign-in took too long. Please try again.",
  replayed: "That sign-in link was already used. Please try again.",
  failed: "Open Media sign-in didn't finish. Please try again.",
};

export function signInErrorMessage(code: string | null | undefined): string | null {
  if (!code) {
    return null;
  }
  return SIGN_IN_ERRORS[code] ?? SIGN_IN_ERRORS.failed;
}
