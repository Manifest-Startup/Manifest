import React from "react";

import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import { GET_SURVEY_INSIGHTS } from "features/core/apollo/queries";

interface DistributionItem {
  label: string;
  count: number;
  percentage?: number | null;
}

interface ThemeItem {
  theme: string;
  count: number;
}

interface SurveyInsights {
  generatedAt: string;
  windowDays: number;
  totalResponses: number;
  researchResponses: number;
  productFeedbackResponses: number;
  researchSignupIntentAvg?: number | null;
  researchFollowUpRate?: number | null;
  productPmfVeryDisappointedPct?: number | null;
  productNpsScore?: number | null;
  productProgressAvg?: number | null;
  productDeliverableAvg?: number | null;
  productSatisfactionAvg?: number | null;
  productEaseAvg?: number | null;
  productSatisfactionTopboxPct?: number | null;
  productAiQualityAvg?: number | null;
  topResearchRoles: DistributionItem[];
  topResearchValueProps: DistributionItem[];
  topResearchBarriers: DistributionItem[];
  topResearchFirstOutputs: DistributionItem[];
  topResearchTrustSignals: DistributionItem[];
  topProductBenefits: DistributionItem[];
  topProductTasks: DistributionItem[];
  topActionThemes: ThemeItem[];
}

interface SurveyInsightsData {
  surveyInsights: SurveyInsights;
}

interface SurveyInsightsPanelProps {
  variant?: "desktop" | "ios";
  windowDays?: number;
}

const metricValue = (value?: number | null, suffix = "", digits = 0): string => {
  if (value == null) {
    return "—";
  }
  if (digits > 0) {
    return `${value.toFixed(digits)}${suffix}`;
  }
  return `${Math.round(value)}${suffix}`;
};

const scoreValue = (value?: number | null, denominator = 5): string => {
  if (value == null) {
    return "—";
  }
  return `${value.toFixed(1)}/${denominator}`;
};

const npsValue = (value?: number | null): string => {
  if (value == null) {
    return "—";
  }
  return `${value > 0 ? "+" : ""}${value}`;
};

const firstLabel = (items: DistributionItem[]): string => items[0]?.label || "Not enough data yet";

const loadingShell = (variant: "desktop" | "ios") => {
  if (variant === "ios") {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm dark:border-neutral700 dark:bg-neutral800" data-testid="survey-insights-panel">
        <div className="h-5 w-40 animate-pulse rounded bg-gray-200 dark:bg-neutral700" />
        <div className="mt-4 grid grid-cols-2 gap-3">
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="h-20 animate-pulse rounded-xl bg-gray-100 dark:bg-neutral700" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <section className="manifest-panel p-4 sm:p-5" data-testid="survey-insights-panel">
      <div className="h-4 w-24 animate-pulse rounded bg-gray-200 dark:bg-neutral700" />
      <div className="mt-3 h-8 w-56 animate-pulse rounded bg-gray-200 dark:bg-neutral700" />
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3, 4, 5, 6].map((item) => (
          <div key={item} className="manifest-card h-24 animate-pulse" />
        ))}
      </div>
    </section>
  );
};

const emptyState = (variant: "desktop" | "ios") => {
  const classes =
    variant === "ios"
      ? "rounded-xl border border-gray-100 bg-white p-4 shadow-sm dark:border-neutral700 dark:bg-neutral800"
      : "manifest-panel p-4 sm:p-5";

  return (
    <section className={classes} data-testid="survey-insights-panel">
      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Signals</p>
      <h2 className="mt-3 text-[1.25rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">Survey insights</h2>
      <p className="mt-3 text-sm leading-7 text-gray500 dark:text-gray400">
        No survey data has landed yet. Responses from <code>/research</code> and <code>/feedback/survey</code> will appear here once they start
        coming in.
      </p>
    </section>
  );
};

const SurveyInsightsPanel: React.FC<SurveyInsightsPanelProps> = ({ variant = "desktop", windowDays = 90 }) => {
  const { data, loading, error } = useSafeQuery<SurveyInsightsData>(GET_SURVEY_INSIGHTS, {
    variables: { windowDays },
    fetchPolicy: "cache-and-network",
  });

  if (loading && !data?.surveyInsights) {
    return loadingShell(variant);
  }

  if (error && !data?.surveyInsights) {
    return (
      <section
        className={variant === "ios" ? "rounded-xl border border-red-200 bg-white p-4 shadow-sm dark:border-red-900/50 dark:bg-neutral800" : "manifest-panel p-4 sm:p-5"}
        data-testid="survey-insights-panel"
      >
        <p className="text-[0.72rem] font-medium text-red-500">Signals</p>
        <h2 className="mt-3 text-[1.25rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">Survey insights unavailable</h2>
        <p className="mt-3 text-sm leading-7 text-gray500 dark:text-gray400">
          We couldn&apos;t load the current survey snapshot right now.
        </p>
      </section>
    );
  }

  const insights = data?.surveyInsights;
  if (!insights || insights.totalResponses === 0) {
    return emptyState(variant);
  }

  const metrics = [
    {
      label: "Responses",
      value: `${insights.totalResponses}`,
      tone: "text-neutral900 dark:text-white",
    },
    {
      label: "Signup Intent",
      value: scoreValue(insights.researchSignupIntentAvg),
      tone: "text-sky-600 dark:text-sky-300",
    },
    {
      label: "Follow-Up Rate",
      value: metricValue(insights.researchFollowUpRate, "%"),
      tone: "text-emerald-600 dark:text-emerald-300",
    },
    {
      label:
        insights.productPmfVeryDisappointedPct != null
          ? "PMF (very disappointed)"
          : "Satisfaction (4–5)",
      value:
        insights.productPmfVeryDisappointedPct != null
          ? metricValue(insights.productPmfVeryDisappointedPct, "%")
          : metricValue(insights.productSatisfactionTopboxPct, "%"),
      tone: "text-violet-600 dark:text-violet-300",
    },
    {
      label: "NPS",
      value: npsValue(insights.productNpsScore),
      tone: "text-amber-600 dark:text-amber-300",
    },
    {
      label: insights.productSatisfactionAvg != null ? "Satisfaction (avg)" : "Output score (avg)",
      value: scoreValue(insights.productSatisfactionAvg ?? insights.productDeliverableAvg),
      tone: "text-rose-600 dark:text-rose-300",
    },
  ];

  const themeItems = insights.topActionThemes.slice(0, 4);
  const topRole = firstLabel(insights.topResearchRoles);
  const topValueProp = firstLabel(insights.topResearchValueProps);
  const topBarrier = firstLabel(insights.topResearchBarriers);
  const topFirstOutput = firstLabel(insights.topResearchFirstOutputs);
  const topTrustSignal = firstLabel(insights.topResearchTrustSignals);
  const topBenefit = firstLabel(insights.topProductBenefits);
  const topTask = firstLabel(insights.topProductTasks);

  if (variant === "ios") {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm transition-colors dark:border-neutral700 dark:bg-neutral800" data-testid="survey-insights-panel">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">Survey signals</h3>
            <p className="mt-1 text-sm leading-6 text-gray-500 dark:text-gray-400">
              Anonymous trends from the last {insights.windowDays} days across discovery and product feedback.
            </p>
          </div>
          <span className="rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700 dark:bg-sky-900/30 dark:text-sky-200">
            {insights.totalResponses} responses
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          {metrics.slice(1, 5).map((metric) => (
            <div key={metric.label} className="rounded-xl border border-gray-100 px-3 py-3 dark:border-neutral700">
              <p className="text-[0.68rem] font-medium text-gray-500 dark:text-gray-400">{metric.label}</p>
              <p className={`mt-2 text-xl font-semibold ${metric.tone}`}>{metric.value}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 space-y-2 text-sm leading-6 text-gray-600 dark:text-gray-300">
          <p><span className="font-semibold text-gray-900 dark:text-white">Top role:</span> {topRole}</p>
          <p><span className="font-semibold text-gray-900 dark:text-white">Top value prop:</span> {topValueProp}</p>
          <p><span className="font-semibold text-gray-900 dark:text-white">Top improvement theme:</span> {topBarrier}</p>
          <p><span className="font-semibold text-gray-900 dark:text-white">Top product benefit:</span> {topBenefit}</p>
        </div>

        {themeItems.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {themeItems.map((theme) => (
              <span
                key={theme.theme}
                className="rounded-full bg-stone100 px-3 py-1 text-xs font-semibold text-gray-600 dark:bg-neutral700 dark:text-gray-300"
              >
                {theme.theme} ({theme.count})
              </span>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <section className="manifest-panel p-4 sm:p-5" data-testid="survey-insights-panel">
      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Signals</p>
      <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-[1.35rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">Survey insights</h2>
          <p className="mt-2 max-w-2xl text-sm leading-7 text-gray500 dark:text-gray400">
            Anonymous discovery and product-feedback trends from the last {insights.windowDays} days. This is the quickest read on marketability,
            trust, product pull, and recurring friction.
          </p>
        </div>
        <p className="text-sm font-medium text-gray500 dark:text-gray400">
          {insights.researchResponses} research + {insights.productFeedbackResponses} product responses
        </p>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {metrics.map((metric) => (
          <div key={metric.label} className="manifest-card px-5 py-4">
            <p className="text-[0.68rem] font-medium text-gray500 dark:text-gray400">{metric.label}</p>
            <p className={`mt-3 text-3xl font-semibold ${metric.tone}`}>{metric.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-3 xl:grid-cols-2">
        <div className="manifest-card px-5 py-5">
          <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Marketability</p>
          <div className="mt-3 space-y-2 text-sm leading-7 text-gray500 dark:text-gray400">
            <p><span className="font-semibold text-neutral900 dark:text-white">Top role:</span> {topRole}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Strongest value prop:</span> {topValueProp}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Top improvement theme:</span> {topBarrier}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Primary goal / first output:</span> {topFirstOutput}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Familiarity / trust preference:</span> {topTrustSignal}</p>
          </div>
        </div>

        <div className="manifest-card px-5 py-5">
          <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Product Pull</p>
          <div className="mt-3 space-y-2 text-sm leading-7 text-gray500 dark:text-gray400">
            <p><span className="font-semibold text-neutral900 dark:text-white">Main benefit:</span> {topBenefit}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Primary task:</span> {topTask}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Progress score:</span> {scoreValue(insights.productProgressAvg)}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Ease score:</span> {scoreValue(insights.productEaseAvg)}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">Satisfaction:</span> {scoreValue(insights.productSatisfactionAvg)}</p>
            <p><span className="font-semibold text-neutral900 dark:text-white">AI quality:</span> {scoreValue(insights.productAiQualityAvg)}</p>
          </div>
        </div>
      </div>

      {themeItems.length > 0 ? (
        <div className="mt-5">
          <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Recurring themes</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {themeItems.map((theme) => (
              <span
                key={theme.theme}
                className="rounded-full border border-stone200 bg-white/80 px-3 py-1.5 text-xs font-semibold text-gray500 dark:border-neutral700 dark:bg-neutral900/80 dark:text-gray300"
              >
                {theme.theme} ({theme.count})
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
};

export default SurveyInsightsPanel;
