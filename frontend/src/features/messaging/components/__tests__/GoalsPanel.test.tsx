import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import GoalsPanel from "../GoalsPanel";
import { DECIDE_APPROVAL, GET_GOALS } from "features/core/apollo/queries";

const approval = {
  __typename: "ApprovalRequest",
  id: "a1",
  goalId: "g1",
  summary: 'Send @ana on Open Media: "Hi Ana, pilot?"',
  consequences: "@ana gets this message from your Open Media account. It can't be unsent.",
  riskTier: 2,
  scopeSha256: "f".repeat(64),
  status: "pending",
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
  const { container } = render(
    <MockedProvider mocks={[goalsMock([])]}>
      <GoalsPanel />
    </MockedProvider>,
  );
  await waitFor(() => expect(container).toBeEmptyDOMElement());
});
