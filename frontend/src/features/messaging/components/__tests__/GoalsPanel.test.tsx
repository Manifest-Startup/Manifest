import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import GoalsPanel from "../GoalsPanel";
import {
  DECIDE_APPROVAL,
  GET_GOAL_TIMELINE,
  GET_GOALS,
  GET_STANDING_AUTHORIZATIONS,
  REVOKE_STANDING_AUTHORIZATION,
} from "features/core/apollo/queries";

const approval = {
  __typename: "ApprovalRequest",
  id: "a1",
  goalId: "g1",
  summary: 'Send @ana on Open Media: "Hi Ana, pilot?"',
  consequences: "@ana gets this message from your Open Media account. It can't be unsent.",
  riskTier: 2,
  scopeSha256: "f".repeat(64),
  status: "pending",
  scope: { action: "message.send", to: "ana", body: "Hi Ana, pilot?", channel: "open_media", idea_id: null },
};

const standing = (rows: unknown[]) => ({
  request: { query: GET_STANDING_AUTHORIZATIONS },
  result: { data: { standingAuthorizations: rows } },
});

const grantRow = {
  __typename: "StandingAuthorization",
  id: "s1",
  action: "message.send",
  recipients: ["ana"],
  maxPerWeek: 3,
  usedThisWeek: 1,
  expiresAt: "2026-12-22T00:00:00+00:00",
};

const goal = (overrides: Record<string, unknown> = {}) => ({
  __typename: "Goal",
  id: "g1",
  title: "Hear back from @ana",
  status: "active",
  approvals: [approval],
  report: {
    __typename: "GoalReport",
    completed: ["Find the person", "Prepare the message"],
    inProgress: [],
    waiting: [],
    needsYou: ["Approve or decline: Send @ana"],
    next: ["Wait for a reply"],
  },
  ...overrides,
});

const goalsMock = (goals: unknown[]) => ({ request: { query: GET_GOALS }, result: { data: { goals } } });

test("shows the exact message and sends only when the person says so", async () => {
  const approved = goal({
    approvals: [{ ...approval, status: "approved" }],
    report: { __typename: "GoalReport", completed: [], inProgress: [], waiting: ["Wait for a reply from @ana"], needsYou: [], next: [] },
  });
  const decided = { data: { decideApproval: approved } };
  render(
    <MockedProvider
      mocks={[
        goalsMock([goal()]),
        standing([]),
        {
          request: { query: DECIDE_APPROVAL, variables: { approvalId: "a1", approve: true, scopeSha256: "f".repeat(64) } },
          result: decided,
        },
        goalsMock([approved]),
      ]}
    >
      <GoalsPanel />
    </MockedProvider>,
  );

  expect(await screen.findByText('Send @ana on Open Media: "Hi Ana, pilot?"')).toBeInTheDocument();
  expect(screen.getByText(/can't be unsent/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  // Approved with the exact scope hash: the card goes and the goal says what it's waiting for.
  expect(await screen.findByText("Wait for a reply from @ana")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
});

test("renders nothing when there are no goals", async () => {
  render(
    <MockedProvider mocks={[goalsMock([]), standing([])]}>
      <GoalsPanel />
    </MockedProvider>,
  );
  await waitFor(() => expect(screen.queryByTestId("goals-panel")).not.toBeInTheDocument());
  expect(screen.queryByTestId("standing-approvals")).not.toBeInTheDocument();
});


test("offers 'don't ask again' only for messages, unticked by default", async () => {
  const other = { ...approval, id: "a2", scope: { action: "something.else" } };
  render(
    <MockedProvider mocks={[goalsMock([goal({ approvals: [approval, other] })]), standing([])]}>
      <GoalsPanel />
    </MockedProvider>,
  );
  const boxes = await screen.findAllByLabelText(/Don't ask again for @ana/);
  expect(boxes).toHaveLength(1);
  expect(boxes[0]).not.toBeChecked();
  expect(screen.getByTestId("goal-approval-a2")).not.toHaveTextContent("Don't ask again");
});

test("standing approvals are listed and can be stopped", async () => {
  render(
    <MockedProvider
      mocks={[
        goalsMock([]),
        standing([grantRow]),
        {
          request: { query: REVOKE_STANDING_AUTHORIZATION, variables: { authorizationId: "s1" } },
          result: { data: { revokeStandingAuthorization: { ...grantRow, id: "s1" } } },
        },
        standing([]),
      ]}
    >
      <GoalsPanel />
    </MockedProvider>,
  );
  expect(await screen.findByText("@ana · 1 of 3 this week")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await waitFor(() => expect(screen.queryByText("@ana · 1 of 3 this week")).not.toBeInTheDocument());
});

test("'What happened' shows the timeline and what was learned, labelled by how sure it is", async () => {
  render(
    <MockedProvider
      mocks={[
        goalsMock([goal({ approvals: [] })]),
        standing([]),
        {
          request: { query: GET_GOAL_TIMELINE, variables: { goalId: "g1" } },
          result: {
            data: {
              goal: {
                __typename: "Goal",
                id: "g1",
                timeline: [
                  { __typename: "GoalEvent", type: "goal.created", summary: "Goal: Hear back from @ana (5 steps)", createdAt: null },
                  { __typename: "GoalEvent", type: "task.completed", summary: "Done: Send the message", createdAt: null },
                ],
                facts: [
                  { __typename: "KnowledgeFact", id: "f1", subject: "@ana", predicate: "needs", value: "support for our internal chat", kind: "inferred", confidence: 0.3, status: "current" },
                  { __typename: "KnowledgeFact", id: "f2", subject: "@ana", predicate: "relationship", value: "customer", kind: "inferred", confidence: 0.3, status: "superseded" },
                ],
              },
            },
          },
        },
      ]}
    >
      <GoalsPanel />
    </MockedProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "What happened" }));
  expect(await screen.findByText("Done: Send the message")).toBeInTheDocument();
  expect(screen.getByText(/support for our internal chat/)).toHaveTextContent("(unconfirmed)");
  expect(screen.queryByText(/customer/)).not.toBeInTheDocument(); // superseded facts aren't shown
});
