import { userVar } from 'features/core/apollo/localState';

export interface GuestSessionPayload {
  token: string;
  userId: string;
  mergeSecret: string;
  email: string;
}

/**
 * Apply a guest session payload: token in localStorage + reactive user state.
 * Signing in later with Open Media merges the workspace on the server (the
 * guest's session cookie proves ownership), so the merge secret is not kept.
 */
export function applyGuestSessionPayload(payload: GuestSessionPayload | null | undefined): boolean {
  if (!payload?.token || !payload.userId) {
    return false;
  }
  if (typeof window !== 'undefined') {
    localStorage.setItem('access_token', payload.token);
  }
  userVar({
    isLoggedIn: true,
    isGuest: true,
    authChecked: true,
    userData: { userId: payload.userId, email: payload.email },
  });
  return true;
}
