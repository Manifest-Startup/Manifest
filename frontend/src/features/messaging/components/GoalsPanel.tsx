import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import { DECIDE_APPROVAL, GET_GOALS } from "features/core/apollo/queries";
import type { GoalApproval, GoalSummary } from "features/core/apollo/operationTypes";

const GOALS_POLL_MS = 30_000;

function Approval({ approval, onDecided }: { approval: GoalApproval; onDecided: () => void }) {
  const [decide, { loading }] = useMutation(DECIDE_APPROVAL);
  const [error, setError] = useState<string | null>(null);
  const answer = async (approve: boolean) => {
    setError(null);
    try {
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
      <div className="om-goal-actions">
        <button type="button" className="om-goal-primary" disabled={loading} onClick={() => answer(true)}>
          Send
        </button>
        <button type="button" className="om-goal-secondary" disabled={loading} onClick={() => answer(false)}>
          Don&apos;t send
        </button>
      </div>
    </div>
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

/** What Manifest is doing for the person through Open Media (ADR 0020): messages waiting for
 * their yes, and where each goal stands. Renders nothing when there are no goals. */
const GoalsPanel: React.FC = () => {
  const { data, refetch } = useQuery(GET_GOALS, {
    pollInterval: GOALS_POLL_MS,
    fetchPolicy: "cache-and-network",
  });
  const goals = data?.goals ?? [];
  if (goals.length === 0) return null;
  return (
    <section className="om-goals" aria-label="Manifest is working on" data-testid="goals-panel">
      {goals.map((goal) => {
        const pending = goal.approvals.filter((a) => a.status === "pending");
        const status = pending.length ? null : line(goal); // the approval says it all
        return (
          <div key={goal.id} className="om-goal" data-testid={`goal-${goal.id}`}>
            <p className="om-goal-title">{goal.title}</p>
            {status ? <p className="om-goal-note">{status}</p> : null}
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
