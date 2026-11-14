/** Logged-in sessions counted toward showing the product feedback prompt (Track B modal). */
export const PRODUCT_FEEDBACK_SESSION_COUNT_KEY = "manifest_product_feedback_session_count";
export const PRODUCT_FEEDBACK_DISMISSED_KEY = "manifest_product_feedback_survey_dismissed";
export const PRODUCT_FEEDBACK_SESSION_BUMP_KEY = "manifest_product_feedback_session_bumped";
export const PRODUCT_FEEDBACK_MODAL_SHOWN_SESSION_KEY = "manifest_product_feedback_modal_shown";

export const PRODUCT_FEEDBACK_VISIT_THRESHOLD = 3;

export function readSessionCount(): number {
  try {
    const raw = localStorage.getItem(PRODUCT_FEEDBACK_SESSION_COUNT_KEY);
    const n = parseInt(raw || "0", 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

export function isFeedbackSurveyDismissed(): boolean {
  try {
    return localStorage.getItem(PRODUCT_FEEDBACK_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function dismissFeedbackSurvey(): void {
  try {
    localStorage.setItem(PRODUCT_FEEDBACK_DISMISSED_KEY, "1");
  } catch {
    /* ignore */
  }
}

/** Increment once per browser session when the user is logged in. */
export function hasModalBeenShownThisSession(): boolean {
  try {
    return sessionStorage.getItem(PRODUCT_FEEDBACK_MODAL_SHOWN_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function markModalShownThisSession(): void {
  try {
    sessionStorage.setItem(PRODUCT_FEEDBACK_MODAL_SHOWN_SESSION_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function bumpSessionCountIfNeeded(): number {
  try {
    if (sessionStorage.getItem(PRODUCT_FEEDBACK_SESSION_BUMP_KEY) === "1") {
      return readSessionCount();
    }
    sessionStorage.setItem(PRODUCT_FEEDBACK_SESSION_BUMP_KEY, "1");
    const next = readSessionCount() + 1;
    localStorage.setItem(PRODUCT_FEEDBACK_SESSION_COUNT_KEY, String(next));
    return next;
  } catch {
    return readSessionCount();
  }
}
