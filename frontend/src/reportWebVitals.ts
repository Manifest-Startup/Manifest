import { onCLS, onINP, onLCP, onTTFB, type Metric } from 'web-vitals';

import { captureAnalyticsEvent, canCaptureAnalytics } from "features/privacy/analyticsClient";

const SAMPLE = 0.25;

function captureMetric(metric: Metric): void {
  if (typeof window === 'undefined' || process.env.NODE_ENV !== 'production') {
    return;
  }
  if (!canCaptureAnalytics()) {
    return;
  }
  if (Math.random() > SAMPLE) {
    return;
  }
  captureAnalyticsEvent('web_vitals', {
    metric_name: metric.name,
    value: metric.value,
    rating: metric.rating,
    delta: metric.delta,
    id: metric.id,
    path: window.location.pathname,
  });
}

let longTaskObserver: PerformanceObserver | null = null;

function initLongTaskObserver(): void {
  if (typeof window === 'undefined' || process.env.NODE_ENV !== 'production') {
    return;
  }
  if (longTaskObserver) {
    return;
  }
  try {
    longTaskObserver = new PerformanceObserver((list) => {
      let totalMs = 0;
      for (const e of list.getEntries()) {
        totalMs += (e as PerformanceEntry & { duration?: number }).duration ?? 0;
      }
      if (totalMs < 50) {
        return;
      }
      if (!canCaptureAnalytics()) {
        return;
      }
      if (Math.random() > SAMPLE) {
        return;
      }
      captureAnalyticsEvent('long_tasks', {
        total_duration_ms: Math.round(totalMs),
        path: window.location.pathname,
      });
    });
    longTaskObserver.observe({ type: 'longtask', buffered: true } as PerformanceObserverInit);
  } catch {
    /* unsupported */
  }
}

/** Real-user Core Web Vitals + sampled long-task signal (PostHog must be initialized). */
export function initWebVitals(): void {
  if (typeof window === 'undefined' || process.env.NODE_ENV !== 'production') {
    return;
  }

  onCLS(captureMetric);
  onINP(captureMetric);
  onLCP(captureMetric);
  onTTFB(captureMetric);
  initLongTaskObserver();
}
