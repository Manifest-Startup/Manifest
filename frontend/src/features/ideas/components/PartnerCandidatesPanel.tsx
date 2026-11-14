import React, { useMemo } from "react";
import { useMutation } from "@apollo/client/react";
import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import Button from "features/common-ui/Button";
import {
  APPROVE_PARTNER_CANDIDATE,
  GET_PARTNER_CANDIDATES,
  RUN_PARTNER_DISCOVERY,
} from "features/core/apollo/queries";

/**
 * Partner candidates panel — surfaces the per-idea results of the
 * partner-discovery agent.
 *
 * Safety boundary (per spec): the "approve" button flips an internal
 * flag ONLY. It does NOT initiate outreach or share data externally.
 * A future outreach agent will read approved=true rows.
 */

type IntegrationType =
  | "api"
  | "mcp"
  | "sdk"
  | "webhook"
  | "zapier"
  | "manual"
  | "unknown";

interface PartnerCandidate {
  id: string;
  ideaId: string;
  name: string;
  website?: string | null;
  category: string;
  whyRelevant?: string | null;
  suggestedUse?: string | null;
  integrationType: IntegrationType | string;
  dataRequired?: string | null;
  actionsPossible?: string | null;
  pricingNotes?: string | null;
  riskNotes?: string | null;
  implementationDifficulty?: "low" | "medium" | "high" | string | null;
  recommendedNextStep?: string | null;
  rank: number;
  relevanceScore?: number | null;
  confidence?: "low" | "medium" | "high" | string | null;
  approved: boolean;
  approvedAt?: string | null;
  lastGeneratedAt?: string | null;
}

interface Props {
  ideaId: string;
}

const PartnerCandidatesPanel: React.FC<Props> = ({ ideaId }) => {
  const { data, loading, refetch } = useSafeQuery(GET_PARTNER_CANDIDATES, {
    variables: { ideaId },
    skip: !ideaId,
    fetchPolicy: "cache-and-network",
  });

  const [runDiscovery, { loading: discovering, error: discoveryError }] =
    useMutation(RUN_PARTNER_DISCOVERY);
  const [approveCandidate, { loading: approving }] = useMutation(
    APPROVE_PARTNER_CANDIDATE,
  );

  const candidates: PartnerCandidate[] = useMemo(() => {
    const rows =
      (data as { partnerCandidates?: PartnerCandidate[] } | undefined)
        ?.partnerCandidates || [];
    return [...rows].sort((a, b) => a.rank - b.rank);
  }, [data]);

  const onRunDiscovery = async () => {
    await runDiscovery({ variables: { ideaId, maxCandidates: 10 } });
    await refetch();
  };

  const onToggleApprove = async (candidate: PartnerCandidate) => {
    await approveCandidate({
      variables: { candidateId: candidate.id, approved: !candidate.approved },
    });
    await refetch();
  };

  const hasNone = candidates.length === 0;

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-neutral900 dark:text-white">
            Key Partners — partner discovery agent
          </h2>
          <p className="text-xs text-neutral500 dark:text-gray400">
            Ranks real-world vendors a founder could integrate with for the
            MVP. The "approve" toggle is internal-only — nothing is contacted
            on your behalf.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={onRunDiscovery}
          disabled={discovering || loading}
        >
          {discovering
            ? "Discovering…"
            : hasNone
              ? "Run partner discovery"
              : "Refresh candidates"}
        </Button>
      </header>

      {discoveryError ? (
        <p className="text-xs text-red-600 dark:text-red-400">
          {discoveryError.message}
        </p>
      ) : null}

      {hasNone ? (
        <div className="rounded-3xl border border-dashed border-stone200 p-6 text-center text-xs text-neutral500 dark:border-neutral700 dark:text-gray400">
          No partner candidates yet. Click <em>Run partner discovery</em>.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {candidates.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              busy={approving || discovering}
              onToggleApprove={() => onToggleApprove(c)}
            />
          ))}
        </div>
      )}

      <p className="text-[10px] text-neutral400 dark:text-gray600">
        Approving a candidate sets an internal flag so a future outreach
        agent can act with your consent. No emails are sent, no data is
        shared, and no third-party APIs are called as a side-effect of
        approval.
      </p>
    </section>
  );
};

const CandidateCard: React.FC<{
  candidate: PartnerCandidate;
  busy: boolean;
  onToggleApprove: () => void;
}> = ({ candidate: c, busy, onToggleApprove }) => (
  <article className="flex flex-col gap-3 rounded-3xl border border-stone200 bg-white/80 p-4 shadow-soft dark:border-neutral700 dark:bg-neutral900/70">
    <header className="flex items-baseline justify-between gap-2">
      <div className="flex flex-col">
        <h3 className="text-sm font-semibold text-neutral900 dark:text-white">
          #{c.rank} · {c.name}
          {c.website ? (
            <a
              href={`https://${c.website.replace(/^https?:\/\//, "")}`}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-2 text-[10px] font-normal text-blue500 hover:underline"
            >
              {c.website}
            </a>
          ) : null}
        </h3>
        <span className="text-[10px] uppercase tracking-wider text-neutral500 dark:text-gray400">
          {c.category}
        </span>
      </div>
      <IntegrationBadge type={c.integrationType} />
    </header>

    {c.whyRelevant ? (
      <p className="text-xs text-neutral700 dark:text-gray200">
        {c.whyRelevant}
      </p>
    ) : null}

    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-neutral600 dark:text-gray300">
      {c.relevanceScore !== null && c.relevanceScore !== undefined ? (
        <Field label="Relevance" value={`${c.relevanceScore}/100`} />
      ) : null}
      {c.confidence ? (
        <Field label="Confidence" value={c.confidence} />
      ) : null}
      {c.implementationDifficulty ? (
        <Field label="Difficulty" value={c.implementationDifficulty} />
      ) : null}
      {c.pricingNotes ? <Field label="Pricing" value={c.pricingNotes} /> : null}
    </div>

    {c.suggestedUse ? (
      <p className="text-[11px] leading-relaxed text-neutral700 dark:text-gray200">
        <span className="font-semibold">How:</span> {c.suggestedUse}
      </p>
    ) : null}

    {c.recommendedNextStep ? (
      <p className="text-[11px] leading-relaxed text-neutral700 dark:text-gray200">
        <span className="font-semibold">Next step:</span> {c.recommendedNextStep}
      </p>
    ) : null}

    {c.riskNotes ? (
      <p className="text-[10px] italic text-amber-700 dark:text-amber-300">
        ⚠ {c.riskNotes}
      </p>
    ) : null}

    <footer className="flex items-center justify-between gap-2 border-t border-stone100 pt-2 text-[10px] dark:border-neutral800">
      <span className="text-neutral500 dark:text-gray400">
        {c.lastGeneratedAt
          ? new Date(c.lastGeneratedAt).toLocaleDateString()
          : ""}
      </span>
      <button
        type="button"
        onClick={onToggleApprove}
        disabled={busy}
        className={`rounded-full px-3 py-1 font-semibold disabled:opacity-50 ${
          c.approved
            ? "border border-green-500/50 bg-green-50 text-green-800 hover:bg-green-100 dark:bg-green-900/20 dark:text-green-300"
            : "border border-stone200 text-neutral700 hover:bg-stone50 dark:border-neutral700 dark:text-gray300 dark:hover:bg-neutral800"
        }`}
      >
        {c.approved ? "Approved ✓" : "Approve (internal)"}
      </button>
    </footer>
  </article>
);

const Field: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-baseline justify-between gap-2">
    <span className="text-neutral400 dark:text-gray600">{label}</span>
    <span className="text-neutral700 dark:text-gray200">{value}</span>
  </div>
);

const IntegrationBadge: React.FC<{ type: string }> = ({ type }) => {
  const palette: Record<string, string> = {
    api: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
    mcp: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
    sdk: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300",
    webhook: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300",
    zapier: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300",
    manual: "bg-stone100 text-neutral700 dark:bg-neutral800 dark:text-gray300",
    unknown: "bg-stone100 text-neutral500 dark:bg-neutral800 dark:text-gray400",
  };
  const klass = palette[type] || palette.unknown;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${klass}`}
    >
      {type}
    </span>
  );
};

export default PartnerCandidatesPanel;
