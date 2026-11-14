const CSRF_COOKIE_NAME = "manifest_csrf_token";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const prefix = `${CSRF_COOKIE_NAME}=`;
  const cookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  if (!cookie) {
    return null;
  }
  return decodeURIComponent(cookie.slice(prefix.length));
}

export function buildSessionHeaders(headers: Record<string, string> = {}): Record<string, string> {
  const csrfToken = getCsrfToken();
  return {
    ...headers,
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };
}

export function clearLegacyBrowserTokens(): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.removeItem("access_token");
  localStorage.removeItem("sb-access-token");
}
