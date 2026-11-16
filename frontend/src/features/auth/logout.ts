import { accountVar, userVar } from "features/core/apollo/localState";
import { buildSessionHeaders, clearLegacyBrowserTokens } from "features/auth/session";

const LOGOUT_REDIRECT_KEY = "manifest_logout_redirect";

function setLogoutRedirectFlag(enabled: boolean): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }
  try {
    if (enabled) {
      sessionStorage.setItem(LOGOUT_REDIRECT_KEY, "1");
    } else {
      sessionStorage.removeItem(LOGOUT_REDIRECT_KEY);
    }
  } catch {
    /* ignore storage failures */
  }
}

export function isLogoutRedirectInProgress(): boolean {
  if (typeof sessionStorage === "undefined") {
    return false;
  }
  try {
    return sessionStorage.getItem(LOGOUT_REDIRECT_KEY) === "1";
  } catch {
    return false;
  }
}

export function clearLogoutRedirectInProgress(): boolean {
  const hadFlag = isLogoutRedirectInProgress();
  setLogoutRedirectFlag(false);
  return hadFlag;
}

export async function requestServerLogout(): Promise<void> {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: buildSessionHeaders(),
  }).catch(() => undefined);
}

export function clearClientLogoutState(): void {
  clearLegacyBrowserTokens();
  userVar({ isLoggedIn: false, authChecked: true, isGuest: false, userData: null });
  accountVar({ accountData: null, loading: false, error: null });
}

export async function performLogout(): Promise<void> {
  setLogoutRedirectFlag(true);
  await requestServerLogout();
  clearClientLogoutState();
}
