const GUEST_USER_ID_KEY = "manifest_guest_user_id";
const GUEST_MERGE_SECRET_KEY = "manifest_guest_merge_secret";

export function persistGuestMergeCredentials(guestUserId: string, mergeSecret: string): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }
  try {
    sessionStorage.setItem(GUEST_USER_ID_KEY, guestUserId);
    sessionStorage.setItem(GUEST_MERGE_SECRET_KEY, mergeSecret);
  } catch {
    /* quota / private mode */
  }
}

export function readGuestMergeCredentials(): { guestUserId: string; mergeSecret: string } | null {
  if (typeof sessionStorage === "undefined") {
    return null;
  }
  try {
    const guestUserId = sessionStorage.getItem(GUEST_USER_ID_KEY);
    const mergeSecret = sessionStorage.getItem(GUEST_MERGE_SECRET_KEY);
    if (!guestUserId || !mergeSecret) {
      return null;
    }
    return { guestUserId, mergeSecret };
  } catch {
    return null;
  }
}

export function clearGuestMergeCredentials(): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }
  try {
    sessionStorage.removeItem(GUEST_USER_ID_KEY);
    sessionStorage.removeItem(GUEST_MERGE_SECRET_KEY);
  } catch {
    /* ignore */
  }
}
