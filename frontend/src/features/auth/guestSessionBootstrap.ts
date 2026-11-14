import { userVar } from 'features/core/apollo/localState';
import { persistGuestMergeCredentials } from 'features/auth/guestSessionStorage';

export interface GuestSessionPayload {
  token: string;
  userId: string;
  mergeSecret: string;
  email: string;
}

/** Apply guest session payload: token in localStorage + reactive user state. */
export function applyGuestSessionPayload(payload: GuestSessionPayload | null | undefined): boolean {
  if (!payload?.token || !payload.userId || !payload.mergeSecret) {
    return false;
  }
  if (typeof window !== 'undefined' && payload.token) {
    localStorage.setItem('access_token', payload.token);
  }
  persistGuestMergeCredentials(payload.userId, payload.mergeSecret);
  userVar({
    isLoggedIn: true,
    isGuest: true,
    authChecked: true,
    userData: { userId: payload.userId, email: payload.email },
  });
  return true;
}
