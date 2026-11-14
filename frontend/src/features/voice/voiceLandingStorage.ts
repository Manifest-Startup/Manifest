/** Local preferences for voice-first landing and onboarding (no server round-trip). */

export const VOICE_MODE_STORAGE_KEY = 'manifest_voice_mode';
export const VOICE_INTRO_DISMISSED_KEY = 'manifest_voice_intro_dismissed';
/** When voice-first (`full`) auto-opens the overlay once per browser tab session. */
export const VOICE_FULL_AUTO_OPEN_SESSION_KEY = 'manifest_voice_full_auto_opened';

export type StoredVoiceMode = 'standard' | 'full';

export function getStoredVoiceMode(): StoredVoiceMode {
  if (typeof window === 'undefined') {
    return 'standard';
  }
  const raw = window.localStorage.getItem(VOICE_MODE_STORAGE_KEY);
  return raw === 'full' ? 'full' : 'standard';
}

export function setStoredVoiceMode(mode: StoredVoiceMode): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(VOICE_MODE_STORAGE_KEY, mode);
}

export function isVoiceIntroDismissed(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return window.localStorage.getItem(VOICE_INTRO_DISMISSED_KEY) === '1';
}

export function dismissVoiceIntro(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(VOICE_INTRO_DISMISSED_KEY, '1');
}
