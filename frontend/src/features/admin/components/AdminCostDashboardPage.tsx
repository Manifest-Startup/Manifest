import React, { useMemo, useState } from "react";
import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import {
  GET_ADMIN_AGENT_RUNS,
  GET_ADMIN_COST_OVERVIEW,
  GET_ADMIN_PRODUCTION_TEST_STATS,
} from "features/core/apollo/queries";

/**
 * Internal admin cost + production-health dashboard.
 *
 * Access is gated server-side by the `admin.cost.read` permission; this
 * page assumes the user has it (the resolver rejects them otherwise,
 * and the error path below surfaces that to the operator).
 */

type WindowDays = 7 | 30 | 90;

interface AdminLabelSpend {
  label: string;
  billableUsd: number;
}

interface AdminDailyPoint {
  date: string;
  billableUsd: number;
  modelCostUsd: number;
  eventCount: number;
}

interface AdminUserSpend {
  userId: string;
  email?: string | null;
  billableUsd: number;
  eventCount: number;
}

interface AdminExpensiveRun {
  id: string;
  userId: string;
  userEmail?: string | null;
  agentKind: string;
  status: string;
  billableUsd: number;
  inputTokens: number;
  outputTokens: number;
  startedAt: string;
}

interface AdminCostTotals {
  totalBillableUsd: number;
  totalModelCostUsd: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalRuns: number;
  failedRuns: number;
  activeUsers: number;
}

interface AdminCostOverview {
  windowDays: number;
  windowStart: string;
  generatedAt: string;
  burnRatePerDayUsd: number;
  monthToDateBillableUsd: number;
  projectedMonthBillableUsd: number;
  totals: AdminCostTotals;
  dailySeries: AdminDailyPoint[];
  topUsers: AdminUserSpend[];
  byAgentKind: AdminLabelSpend[];
  byModel: AdminLabelSpend[];
  expensiveRuns: AdminExpensiveRun[];
}

interface AdminAgentRun {
  id: string;
  userId: string;
  userEmail?: string | null;
  agentKind: string;
  status: string;
  startedAt?: string | null;
  completedAt?: string | null;
  totalBillableCostUsd: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  errorMessage?: string | null;
}

interface AdminProductionTestStats {
  windowHours: number;
  totalRuns: number;
  passCount: number;
  failCount: number;
  flakyCount: number;
  errorCount: number;
  skippedCount: number;
  failureRate: number;
  issuesOpened: number;
  issuesDeduped: number;
  topFailingTests: { testName: string; failures: number }[];
}

const fmtUsd = (n: number): string =>
  `$${(Math.round(n * 100) / 100).toFixed(2)}`;
const fmtPct = (n: number): string => `${(Math.round(n * 1000) / 10).toFixed(1)}%`;
const fmtInt = (n: number): string => n.toLocaleString();

const AdminCostDashboardPage: React.FC = () => {
  const [windowDays, setWindowDays] = useState<WindowDays>(30);
  const [runStatusFilter, setRunStatusFilter] = useState<string>("");

  const { data: overviewData, loading: overviewLoading, error: overviewError } =
    useSafeQuery(GET_ADMIN_COST_OVERVIEW, {
      variables: { windowDays },
      fetchPolicy: "cache-and-network",
      pollInterval: 60_000,
    });
  const { data: runsData, refetch: refetchRuns } = useSafeQuery(
    GET_ADMIN_AGENT_RUNS,
    {
      variables: { limit: 50, status: runStatusFilter || undefined },
      fetchPolicy: "cache-and-network",
    },
  );
  const { data: testStatsData } = useSafeQuery(
    GET_ADMIN_PRODUCTION_TEST_STATS,
    { variables: { hours: 24 }, fetchPolicy: "cache-and-network" },
  );

  const overview: AdminCostOverview | undefined = (
    overviewData as { adminCostOverview?: AdminCostOverview } | undefined
  )?.adminCostOverview;
  const runs: AdminAgentRun[] =
    ((runsData as { adminAgentRuns?: AdminAgentRun[] } | undefined)?.adminAgentRuns) || [];
  const testStats: AdminProductionTestStats | undefined = (
    testStatsData as { adminProductionTestStats?: AdminProductionTestStats } | undefined
  )?.adminProductionTestStats;

  if (overviewError) {
    return (
      <section className="mx-auto w-full max-w-[1200px] px-4 py-10">
        <p className="text-sm text-red-600 dark:text-red-400">
          Couldn't load admin dashboard: {overviewError.message}. Make sure
          your account has the <code>admin.cost.read</code> permission.
        </p>
      </section>
    );
  }

  if (overviewLoading && !overview) {
    return (
      <section className="mx-auto w-full max-w-[1200px] px-4 py-10 text-sm text-neutral600 dark:text-gray300">
        Loading admin dashboard…
      </section>
    );
  }

  if (!overview) return null;

  return (
    <section className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 px-4 py-6 sm:px-5">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="manifest-page-title">
            Admin — cost &amp; agent health
          </h1>
          <p className="text-xs text-gray500 dark:text-gray400">
            Window starts {overview.windowStart.slice(0, 10)} · refreshed{" "}
            {new Date(overview.generatedAt).toLocaleString()}
          </p>
        </div>
        <WindowSwitch active={windowDays} onChange={setWindowDays} />
      </header>

      <TotalsRow overview={overview} />
      <BurnAndProjectionRow overview={overview} />
      <DailySeriesCard series={overview.dailySeries} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BreakdownCard title="Spend by agent" items={overview.byAgentKind} />
        <BreakdownCard title="Spend by model" items={overview.byModel} />
      </div>

      <TopUsersCard users={overview.topUsers} />
      <ExpensiveRunsCard runs={overview.expensiveRuns} />

      <RecentRunsCard
        runs={runs}
        statusFilter={runStatusFilter}
        onStatusFilterChange={(s) => {
          setRunStatusFilter(s);
          setTimeout(refetchRuns, 0);
        }}
        onRefresh={() => refetchRuns()}
      />

      {testStats ? <ProductionTestCard stats={testStats} /> : null}

      <p className="text-[10px] text-neutral400 dark:text-gray600">
        Internal page · do not share. The dashboard is read-only — to
        change a user's cap or pause their agents, ask them to do it from
        /account/billing.
      </p>
    </section>
  );
};

const WindowSwitch: React.FC<{
  active: WindowDays;
  onChange: (days: WindowDays) => void;
}> = ({ active, onChange }) => (
  <div className="flex items-center gap-1 rounded-full border border-stone200 bg-white/80 p-1 text-xs font-semibold dark:border-neutral700 dark:bg-neutral900/70">
    {[7, 30, 90].map((d) => (
      <button
        key={d}
        onClick={() => onChange(d as WindowDays)}
        className={`rounded-full px-3 py-1 transition-colors ${
          active === d
            ? "bg-blue500 text-white"
            : "text-neutral600 hover:bg-stone100 dark:text-gray300 dark:hover:bg-neutral800"
        }`}
      >
        {d}d
      </button>
    ))}
  </div>
);

const TotalsRow: React.FC<{ overview: AdminCostOverview }> = ({ overview }) => (
  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
    <Stat label="Total billable" value={fmtUsd(overview.totals.totalBillableUsd)} hint={`${overview.windowDays}d window`} />
    <Stat label="Model cost (internal)" value={fmtUsd(overview.totals.totalModelCostUsd)} hint="pre-markup" />
    <Stat label="Active users" value={fmtInt(overview.totals.activeUsers)} />
    <Stat
      label="Failed runs"
      value={fmtInt(overview.totals.failedRuns)}
      hint={`of ${fmtInt(overview.totals.totalRuns)} total`}
      emphasis={overview.totals.failedRuns > 0}
    />
  </div>
);

const BurnAndProjectionRow: React.FC<{ overview: AdminCostOverview }> = ({ overview }) => (
  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
    <Stat
      label="Burn rate"
      value={`${fmtUsd(overview.burnRatePerDayUsd)} / day`}
      hint="trailing 7-day avg"
    />
    <Stat
      label="Month to date"
      value={fmtUsd(overview.monthToDateBillableUsd)}
      hint="all users, billable"
    />
    <Stat
      label="Projected month total"
      value={fmtUsd(overview.projectedMonthBillableUsd)}
      hint="MTD + burn × days left"
      emphasis
    />
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
    <p className="text-[10px] font-semibold normal-case text-gray500 dark:text-gray400">
      {label}
    </p>
    <p className="text-xl font-semibold text-neutral900 dark:text-white">{value}</p>
    {hint ? <p className="text-[10px] text-gray500 dark:text-gray400">{hint}</p> : null}
  </div>
);

const DailySeriesCard: React.FC<{ series: AdminDailyPoint[] }> = ({ series }) => {
  const max = useMemo(
    () => Math.max(1, ...series.map((p) => p.billableUsd)),
    [series],
  );
  if (series.length === 0) {
    return (
      <div className="rounded-xl border border-stone200 bg-white/80 p-5 text-xs text-gray500 shadow-none dark:border-neutral700 dark:bg-neutral900/70 dark:text-gray400">
        No spend in this window yet.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">
        Spend over time
      </p>
      <div className="flex items-end gap-1 overflow-x-auto pb-1" style={{ minHeight: 120 }}>
        {series.map((p) => {
          const h = Math.max(4, Math.round((p.billableUsd / max) * 100));
          return (
            <div key={p.date} className="flex flex-col items-center gap-1">
              <div
                title={`${p.date} · ${fmtUsd(p.billableUsd)} · ${p.eventCount} events`}
                className="w-3 rounded-sm bg-blue500/70 hover:bg-blue500"
                style={{ height: `${h}px` }}
              />
              <span className="rotate-90 origin-left whitespace-nowrap text-[8px] text-neutral400 dark:text-gray600">
                {p.date.slice(5)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const BreakdownCard: React.FC<{
  title: string;
  items: AdminLabelSpend[];
}> = ({ title, items }) => {
  const total = items.reduce((s, i) => s + i.billableUsd, 0);
  const sorted = [...items].sort((a, b) => b.billableUsd - a.billableUsd);
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">
        {title}
      </p>
      {sorted.length === 0 ? (
        <p className="text-xs text-gray500 dark:text-gray400">No data.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sorted.map((item) => {
            const pct = total > 0 ? (item.billableUsd / total) * 100 : 0;
            return (
              <li key={item.label} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-baseline justify-between gap-3 text-xs">
                  <span className="font-medium text-neutral800 dark:text-gray100">{item.label}</span>
                  <span className="text-gray500 dark:text-gray400">
                    {fmtUsd(item.billableUsd)} ({fmtPct(pct / 100)})
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-stone100 dark:bg-neutral800">
                  <div className="h-full bg-blue500" style={{ width: `${Math.min(100, pct)}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

const TopUsersCard: React.FC<{ users: AdminUserSpend[] }> = ({ users }) => (
  <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
    <p className="text-sm font-semibold text-neutral900 dark:text-white">
      Top users by spend
    </p>
    {users.length === 0 ? (
      <p className="text-xs text-gray500 dark:text-gray400">No users yet.</p>
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-gray500 dark:text-gray400">
            <tr>
              <th className="py-2 pr-4 font-semibold">User</th>
              <th className="py-2 pr-4 font-semibold text-right">Billable</th>
              <th className="py-2 pr-4 font-semibold text-right">Events</th>
            </tr>
          </thead>
          <tbody className="text-neutral800 dark:text-gray100">
            {users.map((u) => (
              <tr key={u.userId} className="border-t border-stone100 dark:border-neutral800">
                <td className="py-2 pr-4 font-medium">
                  {u.email || (
                    <span className="font-mono text-[10px] text-gray500 dark:text-gray400">
                      {u.userId.slice(0, 8)}
                    </span>
                  )}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">{fmtUsd(u.billableUsd)}</td>
                <td className="py-2 pr-4 text-right tabular-nums text-gray500 dark:text-gray400">
                  {fmtInt(u.eventCount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const ExpensiveRunsCard: React.FC<{ runs: AdminExpensiveRun[] }> = ({ runs }) => (
  <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
    <p className="text-sm font-semibold text-neutral900 dark:text-white">
      Expensive runs
    </p>
    {runs.length === 0 ? (
      <p className="text-xs text-gray500 dark:text-gray400">No runs yet.</p>
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-gray500 dark:text-gray400">
            <tr>
              <th className="py-2 pr-4 font-semibold">User</th>
              <th className="py-2 pr-4 font-semibold">Agent</th>
              <th className="py-2 pr-4 font-semibold">Started</th>
              <th className="py-2 pr-4 font-semibold text-right">Cost</th>
              <th className="py-2 pr-4 font-semibold text-right">Tokens</th>
            </tr>
          </thead>
          <tbody className="text-neutral800 dark:text-gray100">
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-stone100 dark:border-neutral800">
                <td className="py-2 pr-4">{r.userEmail || r.userId.slice(0, 8)}</td>
                <td className="py-2 pr-4 font-mono text-[10px]">{r.agentKind}</td>
                <td className="py-2 pr-4 text-gray500 dark:text-gray400">
                  {r.startedAt ? new Date(r.startedAt).toLocaleString() : "—"}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums font-semibold">
                  {fmtUsd(r.billableUsd)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums text-gray500 dark:text-gray400">
                  {fmtInt(r.inputTokens)} / {fmtInt(r.outputTokens)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const RecentRunsCard: React.FC<{
  runs: AdminAgentRun[];
  statusFilter: string;
  onStatusFilterChange: (s: string) => void;
  onRefresh: () => void;
}> = ({ runs, statusFilter, onStatusFilterChange, onRefresh }) => (
  <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
    <div className="flex flex-wrap items-baseline justify-between gap-3">
      <p className="text-sm font-semibold text-neutral900 dark:text-white">
        Recent agent runs (all users)
      </p>
      <div className="flex items-center gap-2 text-xs">
        <select
          value={statusFilter}
          onChange={(e) => onStatusFilterChange(e.target.value)}
          className="rounded-xl border border-stone200 bg-white/95 px-2 py-1 text-xs dark:border-neutral700 dark:bg-neutral900/85 dark:text-white"
        >
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="complete">Complete</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <button
          onClick={onRefresh}
          className="rounded-xl border border-stone200 px-2 py-1 hover:bg-stone50 dark:border-neutral700 dark:hover:bg-neutral800"
        >
          Refresh
        </button>
      </div>
    </div>
    {runs.length === 0 ? (
      <p className="text-xs text-gray500 dark:text-gray400">No runs match.</p>
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-gray500 dark:text-gray400">
            <tr>
              <th className="py-2 pr-4 font-semibold">User</th>
              <th className="py-2 pr-4 font-semibold">Agent</th>
              <th className="py-2 pr-4 font-semibold">Status</th>
              <th className="py-2 pr-4 font-semibold">Started</th>
              <th className="py-2 pr-4 font-semibold text-right">Cost</th>
            </tr>
          </thead>
          <tbody className="text-neutral800 dark:text-gray100">
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-stone100 dark:border-neutral800">
                <td className="py-2 pr-4">{r.userEmail || r.userId.slice(0, 8)}</td>
                <td className="py-2 pr-4 font-mono text-[10px]">{r.agentKind}</td>
                <td className="py-2 pr-4">
                  <StatusPill status={r.status} />
                </td>
                <td className="py-2 pr-4 text-gray500 dark:text-gray400">
                  {r.startedAt ? new Date(r.startedAt).toLocaleString() : "—"}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {fmtUsd(r.totalBillableCostUsd)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const StatusPill: React.FC<{ status: string }> = ({ status }) => {
  const klass =
    status === "failed"
      ? "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300"
      : status === "complete"
        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
        : status === "running"
          ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
          : "bg-stone100 text-neutral700 dark:bg-neutral800 dark:text-gray300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold normal-case ${klass}`}>
      {status}
    </span>
  );
};

const ProductionTestCard: React.FC<{ stats: AdminProductionTestStats }> = ({ stats }) => (
  <div className="flex flex-col gap-3 rounded-xl border border-stone200 bg-white/80 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
    <p className="text-sm font-semibold text-neutral900 dark:text-white">
      Production tests (last {stats.windowHours}h)
    </p>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Stat label="Pass" value={fmtInt(stats.passCount)} />
      <Stat
        label="Fail"
        value={fmtInt(stats.failCount + stats.errorCount)}
        hint={`${fmtPct(stats.failureRate)} of runs`}
        emphasis={stats.failCount + stats.errorCount > 0}
      />
      <Stat label="Issues opened" value={fmtInt(stats.issuesOpened)} hint="new GH issues" />
      <Stat label="Issues deduped" value={fmtInt(stats.issuesDeduped)} hint="matched existing" />
    </div>
    {stats.topFailingTests.length > 0 ? (
      <div>
        <p className="mb-2 text-[10px] font-semibold normal-case text-gray500 dark:text-gray400">
          Top failing tests
        </p>
        <ul className="flex flex-col gap-1 text-xs">
          {stats.topFailingTests.map((t) => (
            <li
              key={t.testName}
              className="flex flex-wrap items-baseline justify-between gap-3 border-t border-stone100 pt-1 dark:border-neutral800"
            >
              <span className="font-mono text-[10px]">{t.testName}</span>
              <span className="tabular-nums">{t.failures}</span>
            </li>
          ))}
        </ul>
      </div>
    ) : null}
  </div>
);

export default AdminCostDashboardPage;
