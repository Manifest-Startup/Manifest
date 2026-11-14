import { captureAnalyticsEvent } from "features/privacy/analyticsClient";

/**
 * Fires analytics events only when the user has opted in.
 */
export function useSurveyAnalytics() {
  const captureSurvey = (event: string, properties?: Record<string, unknown>) => {
    captureAnalyticsEvent(event, properties);
  };

  return { captureSurvey };
}
