import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import {
  DECIDE_APPROVAL,
  GET_GOAL_TIMELINE,
  GET_GOALS,
  GET_STANDING_AUTHORIZATIONS,
  GRANT_STANDING_AUTHORIZATION,
  REVOKE_STANDING_AUTHORIZATION,
} from "features/core/apollo/queries";
import type { GoalApproval, GoalSummary } from "features/core/apollo/operationTypes";

const GOALS_POLL_MS = 30_000;
// The standing approval the card offers: small on purpose, and revocable below.
const STANDING = { maxPerWeek: 3, days: 30 };

function Approval({ approval, onDecided }: { approval: GoalApproval; onDecided: () => void }) {
  const [decide, { loading }] = useMutation(DECIDE_APPROVAL);
  const [grant, { loading: granting }] = useMutation(GRANT_STANDING_AUTHORIZATION, {
    refetchQueries: [{ query: GET_STANDING_AUTHORIZATIONS }],
  });
  const [error, setError] = useState<string | null>(null);
  const [standing, setStanding] = useState(false);
  const recipient = approval.scope?.action === "message.send" ? approval.scope?.to ?? null : null;
  const answer = async (approve: boolean) => {
    setError(null);
    try {
      if (approve && standing && recipient) {
        await grant({ variables: { recipients: [recipient], ...STANDING } });
      }
      await decide({ variables: { approvalId: approval.id, approve, scopeSha256: approval.scopeSha256 } });
      onDecided();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't go through. Try again.");
    }
  };
  return (
    <div className="om-goal-approval" data-testid={`goal-approval-${approval.id}`}>
      <p className="om-goal-summary">{approval.summary}</p>
      <p className="om-goal-note">{approval.consequences}</p>
      {error ? (
        <p role="alert" className="om-goal-error">
          {error}
        </p>
      ) : null}
      {recipient ? (
        <label className="om-goal-standing">
          <input type="checkbox" checked={standing} onChange={(e) => setStanding(e.target.checked)} />
          Don&apos;t ask again for @{recipient} (up to {STANDING.maxPerWeek} a week, {STANDING.days} days)
        </label>
      ) : null}
      <div className="om-goal-actions">
        <button type="button" className="om-goal-primary" disabled={loading || granting} onClick={() => answer(true)}>
          Send
        </button>
        <button type="button" className="om-goal-secondary" disabled={loading || granting} onClick={() => answer(false)}>
          Don&apos;t send
        </button>
      </div>
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  stated_by_user: "you said",
  verified: "checked",
  external_claim: "they said",
  inferred: "unconfirmed",
};

function Timeline({ goalId }: { goalId: string }) {
  const { data, loading, error } = useQuery(GET_GOAL_TIMELINE, { variables: { goalId }, fetchPolicy: "network-only" });
  if (loading && !data) return <p className="om-goal-note">Loading…</p>;
  if (error || !data) return <p className="om-goal-error">Couldn&apos;t load what happened.</p>;
  const facts = data.goal.facts.filter((f) => f.status === "current");
  return (
    <div className="om-goal-timeline" data-testid={`goal-timeline-${goalId}`}>
      <ol>
        {data.goal.timeline.map((event, i) => (
          <li key={`${event.type}-${i}`} className="om-goal-note">
            {event.summary}
          </li>
        ))}
      </ol>
      {facts.length ? (
        <>
          <p className="om-goal-subtitle">What Manifest learned</p>
          <ul>
            {facts.map((fact) => (
              <li key={fact.id} className="om-goal-note">
                {fact.subject} {fact.predicate.replace(/_/g, " ")}: {fact.value}{" "}
                <span className="om-goal-kind">({KIND_LABEL[fact.kind] ?? fact.kind})</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function GoalDetails({ goalId }: { goalId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="om-goal-link" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide what happened" : "What happened"}
      </button>
      {open ? <Timeline goalId={goalId} /> : null}
    </>
  );
}

function line(goal: GoalSummary): string | null {
  const report = goal.report;
  if (!report) return null;
  if (report.waiting.length) return report.waiting.join(" · ");
  if (report.inProgress.length) return report.inProgress.join(" · ");
  if (report.needsYou.length) return report.needsYou.join(" · ");
  if (report.next.length) return `Next: ${report.next.join(" · ")}`;
  return null;
}

function StandingApprovals() {
  const { data, refetch } = useQuery(GET_STANDING_AUTHORIZATIONS, { fetchPolicy: "cache-and-network" });
  const [revoke, { loading }] = useMutation(REVOKE_STANDING_AUTHORIZATION);
  const rows = data?.standingAuthorizations ?? [];
  if (rows.length === 0) return null;
  return (
    <div className="om-goal" data-testid="standing-approvals">
      <p className="om-goal-title">Sends without asking</p>
      {rows.map((row) => (
        <div key={row.id} className="om-goal-standing-row">
          <p className="om-goal-note">
            {row.recipients.map((r) => `@${r}`).join(", ")} · {row.usedThisWeek} of {row.maxPerWeek} this week
          </p>
          <button
            type="button"
            className="om-goal-secondary"
            disabled={loading}
            onClick={async () => {
              await revoke({ variables: { authorizationId: row.id } });
              void refetch();
            }}
          >
            Stop
          </button>
        </div>
      ))}
    </div>
  );
}

/** What Manifest is doing for the person through Open Media (ADR 0020): messages waiting for
 * their yes, and where each goal stands. Renders nothing when there are no goals. */
const GoalsPanel: React.FC = () => {
  const { data, previousData, refetch } = useQuery(GET_GOALS, {
    pollInterval: GOALS_POLL_MS,
    fetchPolicy: "cache-and-network",
  });
  // Keep the last answer on screen while a refetch is in flight, so a card the person is
  // using never unmounts under their click.
  const goals = (data ?? previousData)?.goals ?? [];
  if (goals.length === 0) {
    return (
      <section className="om-goals" aria-label="Manifest is working on">
        <StandingApprovals />
      </section>
    );
  }
  return (
    <section className="om-goals" aria-label="Manifest is working on" data-testid="goals-panel">
      <StandingApprovals />
      {goals.map((goal) => {
        const pending = goal.approvals.filter((a) => a.status === "pending");
        const status = pending.length ? null : line(goal); // the approval says it all
        return (
          <div key={goal.id} className="om-goal" data-testid={`goal-${goal.id}`}>
            <p className="om-goal-title">{goal.title}</p>
            {status ? <p className="om-goal-note">{status}</p> : null}
            <GoalDetails goalId={goal.id} />
            {pending.map((approval) => (
              <Approval key={approval.id} approval={approval} onDecided={() => void refetch()} />
            ))}
          </div>
        );
      })}
    </section>
  );
};

export default GoalsPanel;
