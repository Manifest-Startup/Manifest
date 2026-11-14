import React, { useMemo, useState } from "react";
import { useMutation } from "@apollo/client/react";
import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import Button from "features/common-ui/Button";
import {
  GET_MY_COST_DASHBOARD,
  SET_VARIABLE_COST_CAP,
} from "features/core/apollo/queries";

type WarnLevel = "ok" | "elevated" | "critical" | "over" | string;

interface CostByLabel {
  label: string;
  billableUsd: number;
}

interface MonthlySpend {
  monthStart: string;
  totalBillableUsd: number;
  totalModelCostUsd: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  eventCount: number;
  byAgentKind: CostByLabel[];
  byModel: CostByLabel[];
}

interface UserCostLimits {
  monthlyVariableCapUsd: number;
  paused: boolean;
  baseSubscriptionUsd: number;
  currency: string;
}

interface AgentRun {
  id: string;
  agentKind: string;
  status: string;
  startedAt?: string | null;
  completedAt?: string | null;
  totalBillableCostUsd: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  errorMessage?: string | null;
}

interface UserCostDashboard {
  limits: UserCostLimits;
  spend: MonthlySpend;
  remainingUsd: number;
  pctOfCap: number;
  warnLevel: WarnLevel;
  recentRuns: AgentRun[];
  estimatedTotalWithSubscriptionUsd: number;
}

const fmtUsd = (n: number): string =>
  `$${(Math.round(n * 100) / 100).toFixed(2)}`;

const fmtPct = (n: number): string => `${(Math.round(n * 10) / 10).toFixed(1)}%`;

const BillingDashboardPage: React.FC = () => {
  const { data, loading, error, refetch } = useSafeQuery(GET_MY_COST_DASHBOARD, {
    fetchPolicy: "cache-and-network",
    pollInterval: 30_000,
  });

  const dashboard: UserCostDashboard | undefined = (
    data as { myCostDashboard?: UserCostDashboard } | undefined
  )?.myCostDashboard;

  const [setCap, { loading: saving, error: saveError }] = useMutation(
    SET_VARIABLE_COST_CAP,
  );
  const [capDraft, setCapDraft] = useState<string>("");
  const [savedFlash, setSavedFlash] = useState(false);

  // Initialise the cap input from server data when it first loads
  React.useEffect(() => {
    if (dashboard && capDraft === "") {
      setCapDraft(String(dashboard.limits.monthlyVariableCapUsd));
    }
  }, [dashboard, capDraft]);

  const onSaveCap = async () => {
    const numeric = Number(capDraft);
    if (Number.isNaN(numeric) || numeric < 0) return;
    await setCap({ variables: { monthlyCapUsd: numeric } });
    await refetch();
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 1500);
  };

  const onTogglePause = async () => {
    if (!dashboard) return;
    await setCap({ variables: { paused: !dashboard.limits.paused } });
    await refetch();
  };

  if (loading && !dashboard) {
    return (
      <section className="mx-auto w-full max-w-[1200px] px-4 py-10 text-sm text-neutral600 dark:text-gray300">
        Loading billing…
      </section>
    );
  }

  if (error) {
    return (
      <section className="mx-auto w-full max-w-[1200px] px-4 py-10">
        <p className="text-sm text-red-600 dark:text-red-400">
          Couldn't load billing data: {error.message}
        </p>
      </section>
    );
  }

  if (!dashboard) return null;

  const { limits, spend, remainingUsd, pctOfCap, warnLevel, recentRuns } =
    dashboard;

  return (
    <section className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 px-4 py-6 sm:px-5">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="manifest-page-title">
          Billing &amp; usage
        </h1>
        <span className="text-xs normal-case text-gray500 dark:text-gray400">
          Month starting {spend.monthStart.slice(0, 10)}
        </span>
      </header>

      <EnforcementBanner
        paused={limits.paused}
        warnLevel={warnLevel}
        usageUsd={spend.totalBillableUsd}
        capUsd={limits.monthlyVariableCapUsd}
        onUnpause={() => onTogglePause()}
      />

      <SubscriptionCard
        baseSubscriptionUsd={limits.baseSubscriptionUsd}
        currentBillable={spend.totalBillableUsd}
        estimatedTotal={dashboard.estimatedTotalWithSubscriptionUsd}
      />

      <UsageCard
        spend={spend}
        capUsd={limits.monthlyVariableCapUsd}
        remainingUsd={remainingUsd}
        pctOfCap={pctOfCap}
        warnLevel={warnLevel}
      />

      <CapControls
        capDraft={capDraft}
        setCapDraft={setCapDraft}
        onSave={onSaveCap}
        saving={saving}
        savedFlash={savedFlash}
        saveError={saveError ? saveError.message : null}
        paused={limits.paused}
        onTogglePause={onTogglePause}
      />

      <BreakdownCard
        title="Usage by agent"
        items={spend.byAgentKind}
        emptyHint="No agent runs this month yet."
      />
      <BreakdownCard
        title="Usage by model"
        items={spend.byModel}
        emptyHint="No LLM calls this month yet."
      />

      <RecentRunsCard runs={recentRuns} />

      <UsageDriversNote />
    </section>
  );
};

const EnforcementBanner: React.FC<{
  paused: boolean;
  warnLevel: WarnLevel;
  usageUsd: number;
  capUsd: number;
  onUnpause: () => void;
}> = ({ paused, warnLevel, usageUsd, capUsd, onUnpause }) => {
  // Only render when the user actually IS blocked. Soft warnings
  // (50%/80% of cap) are handled by the existing progress bar.
  const isBlocked = paused || warnLevel === "over";
  if (!isBlocked) return null;

  const title = paused
    ? "Agents are paused"
    : "You've hit your monthly variable-cost cap";
  const subtitle = paused
    ? "New agent runs (idea qualification, BMC sub-agents, partner discovery, …) are blocked until you unpause."
    : `You've used ${fmtUsd(usageUsd)} of your ${fmtUsd(capUsd)} cap. New agent runs are blocked until you raise the cap or wait for the month to reset.`;

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-red-500/50 bg-red-50 p-5 shadow-none dark:border-red-500/40 dark:bg-red-900/15">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-red-800 dark:text-red-200">
            🚫 {title}
          </p>
          <p className="text-xs text-red-700 dark:text-red-300">{subtitle}</p>
        </div>
        {paused ? (
          <Button variant="primary" onClick={onUnpause}>
            Unpause agents
          </Button>
        ) : null}
      </div>
      <p className="text-[10px] text-red-700/80 dark:text-red-300/80">
        Already-running agents will complete. Read-only views (this page,
        admin dashboard, idea workspace) stay available.
      </p>
    </div>
  );
};


const SubscriptionCard: React.FC<{
  baseSubscriptionUsd: number;
  currentBillable: number;
  estimatedTotal: number;
}> = ({ baseSubscriptionUsd, currentBillable, estimatedTotal }) => (
  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
    <Stat label="Base subscription" value={fmtUsd(baseSubscriptionUsd)} hint="per month" />
    <Stat label="Variable usage" value={fmtUsd(currentBillable)} hint="this month so far" />
    <Stat label="Estimated bill" value={fmtUsd(estimatedTotal)} hint="if usage stops today" emphasis />
  </div>
);

const Stat: React.FC<{
  label: string;
  value: string;
  hint?: string;
  emphasis?: boolean;
}> = ({ label, value, hint, emphasis }) => (
  <div
    className={`flex flex-col gap-1 rounded-xl border p-4 shadow-none ${
      emphasis
        ? "border-blue500/60 bg-blue500/5 dark:border-blue500/40"
        : "border-stone200 bg-white/80 dark:border-neutral700 dark:bg-neutral900/70"
    }`}
  >
    <p className="text-xs font-semibold normal-case text-gray500 dark:text-gray400">
      {label}
    </p>
    <p className="text-2xl font-semibold text-neutral900 dark:text-white">{value}</p>
    {hint ? (
      <p className="text-xs text-gray500 dark:text-gray400">{hint}</p>
    ) : null}
  </div>
);

const UsageCard: React.FC<{
  spend: MonthlySpend;
  capUsd: number;
  remainingUsd: number;
  pctOfCap: number;
  warnLevel: WarnLevel;
}> = ({ spend, capUsd, remainingUsd, pctOfCap, warnLevel }) => {
  const barWidth = Math.min(100, Math.max(0, pctOfCap));
  const barColor =
    warnLevel === "over"
      ? "bg-red-500"
      : warnLevel === "critical"
        ? "bg-orange-500"
        : warnLevel === "elevated"
          ? "bg-yellow-500"
          : "bg-blue500";
  const message = useMemo(() => {
    if (capUsd === 0)
      return "Set a monthly cap below to control your variable spend.";
    if (warnLevel === "over")
      return `You're over your monthly cap. Agents are still running for now — enforcement ships in a follow-up; pause agents below to be safe.`;
    if (warnLevel === "critical")
      return `You've used more than 80% of your monthly cap. Consider raising the cap or pausing.`;
    if (warnLevel === "elevated")
      return `You've crossed 50% of your monthly cap.`;
    return `You're well within your cap.`;
  }, [capUsd, warnLevel]);
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
      <div className="flex flex-wrap items-baseline justify-between gap-3 gap-4">
        <p className="text-sm font-semibold text-neutral900 dark:text-white">
          Variable usage vs. cap
        </p>
        <p className="text-xs text-gray500 dark:text-gray400">
          {fmtUsd(spend.totalBillableUsd)} / {fmtUsd(capUsd)} ({fmtPct(pctOfCap)})
        </p>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-stone100 dark:bg-neutral800">
        <div
          className={`h-full ${barColor} transition-all duration-500`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <p className="text-xs text-neutral600 dark:text-gray300">{message}</p>
      <p className="text-xs text-gray500 dark:text-gray400">
        Remaining this month: {fmtUsd(remainingUsd)} • {spend.eventCount} LLM
        calls • {spend.totalInputTokens.toLocaleString()} input /{" "}
        {spend.totalOutputTokens.toLocaleString()} output tokens
      </p>
    </div>
  );
};

const CapControls: React.FC<{
  capDraft: string;
  setCapDraft: (s: string) => void;
  onSave: () => void;
  saving: boolean;
  savedFlash: boolean;
  saveError: string | null;
  paused: boolean;
  onTogglePause: () => void;
}> = ({
  capDraft,
  setCapDraft,
  onSave,
  saving,
  savedFlash,
  saveError,
  paused,
  onTogglePause,
}) => (
  <div className="flex flex-col gap-4 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
    <p className="text-sm font-semibold text-neutral900 dark:text-white">
      Cap &amp; agent controls
    </p>
    <div className="flex flex-wrap items-end gap-4">
      <label className="flex flex-col gap-1 text-xs font-semibold normal-case text-gray500 dark:text-gray400">
        Monthly variable cap (USD)
        <input
          type="number"
          min={0}
          step={1}
          value={capDraft}
          onChange={(e) => setCapDraft(e.target.value)}
          className="w-40 rounded-xl border border-stone200 bg-white/95 px-3 py-2 text-sm font-medium text-neutral900 focus:border-accent-300 focus:outline-none focus:ring-2 focus:ring-accent-200 dark:border-neutral700 dark:bg-neutral900/85 dark:text-white"
        />
      </label>
      <Button variant="primary" onClick={onSave} disabled={saving}>
        {saving ? "Saving…" : savedFlash ? "Saved" : "Update cap"}
      </Button>
      <Button
        variant={paused ? "secondary" : "danger"}
        onClick={onTogglePause}
        disabled={saving}
      >
        {paused ? "Resume agents" : "Pause agents"}
      </Button>
    </div>
    {saveError ? (
      <p className="text-xs text-red-600 dark:text-red-400">{saveError}</p>
    ) : null}
    <p className="text-xs text-gray500 dark:text-gray400">
      Pause stops your account from being charged for new variable agent
      work. Enforcement of the cap (blocking new runs at 100%) ships in a
      follow-up — for now, this is a soft limit with warnings.
    </p>
  </div>
);

const BreakdownCard: React.FC<{
  title: string;
  items: CostByLabel[];
  emptyHint: string;
}> = ({ title, items, emptyHint }) => {
  const total = items.reduce((s, i) => s + i.billableUsd, 0);
  const sorted = [...items].sort((a, b) => b.billableUsd - a.billableUsd);
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">
        {title}
      </p>
      {sorted.length === 0 ? (
        <p className="text-xs text-gray500 dark:text-gray400">{emptyHint}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sorted.map((item) => {
            const pct = total > 0 ? (item.billableUsd / total) * 100 : 0;
            return (
              <li key={item.label} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-baseline justify-between gap-3 text-xs text-neutral700 dark:text-gray200">
                  <span className="font-medium">{item.label}</span>
                  <span>
                    {fmtUsd(item.billableUsd)}{" "}
                    <span className="text-gray500 dark:text-gray400">
                      ({fmtPct(pct)})
                    </span>
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-stone100 dark:bg-neutral800">
                  <div
                    className="h-full bg-blue500"
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

const RecentRunsCard: React.FC<{ runs: AgentRun[] }> = ({ runs }) => {
  if (runs.length === 0) {
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
        <p className="text-sm font-semibold text-neutral900 dark:text-white">
          Recent agent runs
        </p>
        <p className="text-xs text-gray500 dark:text-gray400">
          No agent runs yet this month.
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">
        Recent agent runs
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-gray500 dark:text-gray400">
            <tr>
              <th className="py-2 pr-4 font-semibold">Agent</th>
              <th className="py-2 pr-4 font-semibold">Status</th>
              <th className="py-2 pr-4 font-semibold">Started</th>
              <th className="py-2 pr-4 font-semibold text-right">Cost</th>
              <th className="py-2 pr-4 font-semibold text-right">Tokens</th>
            </tr>
          </thead>
          <tbody className="text-neutral800 dark:text-gray100">
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-stone100 dark:border-neutral800">
                <td className="py-2 pr-4 font-medium">{r.agentKind}</td>
                <td className="py-2 pr-4">{r.status}</td>
                <td className="py-2 pr-4 text-gray500 dark:text-gray400">
                  {r.startedAt ? new Date(r.startedAt).toLocaleString() : "—"}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {fmtUsd(r.totalBillableCostUsd)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums text-gray500 dark:text-gray400">
                  {r.totalInputTokens.toLocaleString()} /{" "}
                  {r.totalOutputTokens.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const UsageDriversNote: React.FC = () => (
  <div className="rounded-xl border border-dashed border-stone200 bg-stone50 p-5 text-xs leading-relaxed text-neutral600 dark:border-neutral700 dark:bg-neutral900/50 dark:text-gray300">
    <p className="font-semibold text-neutral800 dark:text-gray200">
      Why does usage vary?
    </p>
    <p className="mt-1">
      Variable usage reflects the actual AI-agent work Manifest does for
      you: idea qualification, document generation, similar-idea
      research, and (soon) partner discovery. Longer conversations, more
      generated documents, and stronger models cost more per run.
      Subscribers can pause agents or lower the cap at any time.
    </p>
  </div>
);

export default BillingDashboardPage;
