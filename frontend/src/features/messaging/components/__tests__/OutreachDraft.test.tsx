import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import GoalsPanel from "../GoalsPanel";
import OutreachDraft, { draftStatus } from "../OutreachDraft";
import {
  DECIDE_APPROVAL,
  EDIT_GOAL_DRAFT,
  FOLLOW_UP_GOAL,
  GET_GOALS,
  GET_STANDING_AUTHORIZATIONS,
} from "features/core/apollo/queries";
import type { GoalSummary } from "features/core/apollo/operationTypes";

// jest.setup stubs useMutation (it resolves to nothing); a test can answer like the server.
let mockMutate: jest.Mock = jest.fn();
jest.mock("@apollo/client/react", () => ({
  ...jest.requireActual("@apollo/client/react"),
  useMutation: () => [(...args: unknown[]) => mockMutate(...args), { loading: false, error: null }],
}));
beforeEach(() => {
  mockMutate = jest.fn();
});

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
  expect(screen.getByText(/To Priya Shah · priya@studio\.test/)).toBeInTheDocument();
  // Your message is a chat bubble, marked as a draft until it's sent.
  expect(screen.getByTestId("outreach-receipt")).toHaveTextContent("Draft · not sent");
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
  // Their reply is their bubble, under yours, like any chat.
  expect(screen.getByText("Priya Shah", { selector: ".om-sender" })).toBeInTheDocument();
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

test("after a few days without a reply it offers the drafted follow-up, ready for a yes", async () => {
  const sentLong = goal({
    approvals: [{ ...approval, status: "approved" }],
    draft: {
      ...draft, sendStatus: "completed", sentAt: "2026-11-20T10:00:00Z", replyStatus: "waiting_external",
      followUpState: { allowed: true, reason: null, after: null },
    } as never,
  });
  const followUpGoal = goal({ id: "g2", title: "Follow up with Priya Shah" });
  const onOpenGoal = jest.fn();
  mockMutate = jest.fn().mockResolvedValue({ data: { followUpGoal } });
  const mutate = mockMutate;
  render(
    <MockedProvider mocks={[{ request: { query: FOLLOW_UP_GOAL, variables: { goalId: "g1" } }, result: { data: { followUpGoal } } }]}>
      <OutreachDraft goal={sentLong} onBack={() => {}} onDecided={() => {}} onOpenGoal={onOpenGoal} />
    </MockedProvider>,
  );
  expect(screen.getByText("No reply yet?")).toBeInTheDocument();
  expect(screen.getByText("One more thought: …")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Draft follow-up" }));
  await waitFor(() => expect(mutate).toHaveBeenCalledWith({ variables: { goalId: "g1" } }));
  await waitFor(() => expect(onOpenGoal).toHaveBeenCalledWith("g2"));
});

test("too soon for a follow-up says when it will be fine", () => {
  const recent = goal({
    approvals: [{ ...approval, status: "approved" }],
    draft: { ...draft, sendStatus: "completed", sentAt: "2026-11-27T10:00:00Z",
      followUpState: { allowed: false, reason: "Give them a few days; a follow-up is fine from Sunday.", after: null } } as never,
  });
  render(
    <MockedProvider mocks={[]}>
      <OutreachDraft goal={recent} onBack={() => {}} onDecided={() => {}} />
    </MockedProvider>,
  );
  expect(screen.getByText(/fine from Sunday/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Draft follow-up" })).not.toBeInTheDocument();
});

test("a send Open Media refused says why and can be tried again", () => {
  const failed = goal({
    approvals: [{ ...approval, status: "approved" }],
    draft: { ...draft, sendStatus: "failed", sendError: "Open Media refused it." } as never,
  });
  expect(draftStatus(failed)).toBe("Not sent yet: needs you");
  render(
    <MockedProvider mocks={[]}>
      <OutreachDraft goal={failed} onBack={() => {}} onDecided={() => {}} />
    </MockedProvider>,
  );
  expect(screen.getByText("Open Media refused it.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

test("a bounced email says it didn't arrive, why, and offers no follow-up", () => {
  const bounced = goal({
    approvals: [{ ...approval, status: "approved" }],
    draft: { ...draft, sendStatus: "completed", sentAt: "2026-11-20T10:00:00Z", replyStatus: "blocked",
      bounced: true, bounceReason: "550 5.7.1 [CS101] Message rejected due to local policy",
      followUpState: { allowed: false, reason: "It didn't arrive, so a follow-up wouldn't either.", after: null } } as never,
  });
  expect(draftStatus(bounced)).toBe("Didn't arrive: rejected before delivery");
  render(
    <MockedProvider mocks={[]}>
      <OutreachDraft goal={bounced} onBack={() => {}} onDecided={() => {}} />
    </MockedProvider>,
  );
  expect(screen.getByTestId("bounce-notice")).toHaveTextContent("CS101");
  expect(screen.queryByText("No reply yet?")).not.toBeInTheDocument();
});
