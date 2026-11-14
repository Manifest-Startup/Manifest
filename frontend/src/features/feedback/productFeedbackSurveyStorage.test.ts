import {
  bumpSessionCountIfNeeded,
  PRODUCT_FEEDBACK_SESSION_BUMP_KEY,
  PRODUCT_FEEDBACK_SESSION_COUNT_KEY,
  readSessionCount,
} from "./productFeedbackSurveyStorage";

describe("productFeedbackSurveyStorage", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  test("bumpSessionCountIfNeeded increments once per browser session", () => {
    expect(readSessionCount()).toBe(0);
    expect(bumpSessionCountIfNeeded()).toBe(1);
    expect(bumpSessionCountIfNeeded()).toBe(1);
    expect(localStorage.getItem(PRODUCT_FEEDBACK_SESSION_COUNT_KEY)).toBe("1");
    expect(sessionStorage.getItem(PRODUCT_FEEDBACK_SESSION_BUMP_KEY)).toBe("1");
  });
});
