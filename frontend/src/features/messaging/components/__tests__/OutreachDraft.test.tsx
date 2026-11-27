import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import GoalsPanel from "../GoalsPanel";
import OutreachDraft, { draftStatus } from "../OutreachDraft";
import {
  DECIDE_APPROVAL,
  EDIT_GOAL_DRAFT,
  GET_GOALS,
  GET_STANDING_AUTHORIZATIONS,
} from "features/core/apollo/queries";
import type { GoalSummary } from "features/core/apollo/operationTypes";

const BODY =
  "Hi Priya, I read your post about juggling three docs while applying to accelerators. I'm Mihir, and I'm exploring a workspace that keeps them in one place. It's early and I'm not selling anything. How do you keep them in sync today?\n\nIf this isn't relevant to you, just say so and I won't follow up.\n\nMihir";

const approval = {
  __typename: "ApprovalRequest",
  id: "a1",
  goalId: "g1",
  summary: 'Email Priya Shah: "Question about your accelerator prep"',
  consequences: "Priya Shah gets this email from your own mailbox, and their reply comes to your Messages. It can't be unsent.",
  riskTier: 2,
  scopeSha256: "e".repeat(64),
  status: "pending",
  scope: { action: "email.send", to: "priya@studio.test", subject: "Question about your accelerator prep", body: BODY },
};

const draft = {
  channel: "email",
  to: "priya@studio.test",
  toName: "Priya Shah",
  organization: null,
  subject: "Question about your accelerator prep",
  body: BODY,
  why: "Posted about juggling application documents.",
  evidence: [{ text: "Her post on accelerator prep", url: "https://example.org/post" }],
  followUp: "One more thought: …",
  composeUrl: "https://mail.google.com/mail/?view=cm&to=priya%40studio.test",
  edited: false,
  sendStatus: "awaiting_authorization",
  sendError: null,
  sentAt: null,
  from: null,
  replyStatus: "proposed",
  reply: null,
};

const goal = (overrides: Partial<GoalSummary> & Record<string, unknown> = {}) =>
  ({
    __typename: "Goal",
    id: "g1",
    title: "Email Priya Shah",
    status: "active",
    approvals: [approval],
    report: { __typename: "GoalReport", completed: [], inProgress: [], waiting: [], needsYou: [], next: [] },
    draft,
    ...overrides,
  }) as unknown as GoalSummary;

test("the whole message, who it's for and why, then Send approves exactly it", async () => {
  const sent = goal({ approvals: [{ ...approval, status: "approved" }], draft: { ...draft, sendStatus: "completed", sentAt: "2026-11-27T10:00:00Z" } as never });
  const onDecided = jest.fn();
  render(
    <MockedProvider
      mocks={[
        {
          request: { query: DECIDE_APPROVAL, variables: { approvalId: "a1", approve: true, scopeSha256: "e".repeat(64) } },
          result: { data: { decideApproval: sent } },
        },
      ]}
    >
      <OutreachDraft goal={goal()} position={{ index: 0, total: 3 }} onBack={() => {}} onDecided={onDecided} />
    </MockedProvider>,
  );
  expect(screen.getByText("Priya Shah · priya@studio.test")).toBeInTheDocument();
  expect(screen.getByText("Question about your accelerator prep")).toBeInTheDocument();
  expect(screen.getByText(/juggling three docs/)).toBeInTheDocument();
  expect(screen.getByText("Posted about juggling application documents.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "example.org" })).toHaveAttribute("href", "https://example.org/post");
  expect(screen.getByText(/1 of 3/)).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("outreach-send"));
  await waitFor(() => expect(onDecided).toHaveBeenCalled());
});

test("editing saves the new text for a fresh yes; nothing is sent", async () => {
  const edited = goal({ draft: { ...draft, body: "Hey Priya, shorter now. How do you keep them in sync today? Mihir", edited: true } as never });
  render(
    <MockedProvider
      mocks={[
        {
          request: {
            query: EDIT_GOAL_DRAFT,
            variables: { goalId: "g1", body: "Hey Priya, shorter now. How do you keep them in sync today? Mihir", subject: "Question about your accelerator prep" },
          },
          result: { data: { editGoalDraft: edited } },
        },
      ]}
    >
      <OutreachDraft goal={goal()} onBack={() => {}} onDecided={() => {}} />
    </MockedProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  const box = screen.getByLabelText("Message");
  fireEvent.change(box, { target: { value: "Hey Priya, shorter now. How do you keep them in sync today? Mihir" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByText("Saved. Read it once more, then send.")).toBeInTheDocument();
  expect(screen.queryByTestId("outreach-send")).toBeInTheDocument();
});

test("a send that can't go out says why and offers Open in Gmail", () => {
  const blocked = goal({
    approvals: [{ ...approval, status: "approved" }],
    draft: { ...draft, sendStatus: "blocked", sendError: "Your email isn't connected for sending yet." } as never,
  });
  render(
    <MockedProvider mocks={[]}>
      <OutreachDraft goal={blocked} onBack={() => {}} onDecided={() => {}} />
    </MockedProvider>,
  );
  expect(screen.getByText("Your email isn't connected for sending yet.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open in Gmail" })).toHaveAttribute("href", draft.composeUrl);
  expect(screen.queryByTestId("outreach-send")).not.toBeInTheDocument();
});

test("a reply is shown in their words, without the untrusted markers", () => {
  const replied = goal({
    approvals: [{ ...approval, status: "approved" }],
    draft: { ...draft, sendStatus: "completed", sentAt: "2026-11-27T10:00:00Z", replyStatus: "completed", reply: "<<<UNTRUSTED_BEGIN:reply>>>\nI use Notion, it's a mess.\n<<<UNTRUSTED_END:reply>>>" } as never,
  });
  expect(draftStatus(replied)).toBe("Replied: “I use Notion, it's a mess.”");
  render(
    <MockedProvider mocks={[]}>
      <OutreachDraft goal={replied} onBack={() => {}} onDecided={() => {}} />
    </MockedProvider>,
  );
  expect(screen.getByText("Priya Shah replied")).toBeInTheDocument();
  expect(screen.getByText("I use Notion, it's a mess.")).toBeInTheDocument();
});

test("messages waiting for an OK are listed first in Messages and open on click", async () => {
  const onOpen = jest.fn();
  render(
    <MockedProvider
      mocks={[
        { request: { query: GET_GOALS }, result: { data: { goals: [goal()] } } },
        { request: { query: GET_STANDING_AUTHORIZATIONS }, result: { data: { standingAuthorizations: [] } } },
      ]}
    >
      <GoalsPanel onOpenDraft={onOpen} />
    </MockedProvider>,
  );
  expect(await screen.findByText("Waiting for your OK · 1")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("draft-row-g1"));
  expect(onOpen).toHaveBeenCalledWith("g1");
});
