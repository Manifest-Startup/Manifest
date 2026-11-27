import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing/react";

import MessagesPage from "../MessagesPage";
import { userVar } from "features/core/apollo/localState";
import {
  GET_INBOX_CONVERSATION,
  GET_MY_INBOX,
  GET_OPEN_MEDIA_LINK,
  MARK_INBOX_READ,
  REPLY_IN_INBOX,
} from "features/core/apollo/queries";

const linkMock = (overrides: Record<string, unknown> = {}) => ({
  request: { query: GET_OPEN_MEDIA_LINK },
  result: {
    data: {
      openMediaLink: {
        enabled: true,
        linked: true,
        needsReconnect: false,
        handle: "ada",
        displayName: "Ada",
        connectUrl: "/api/auth/open-media/start",
        ...overrides,
      },
    },
  },
});

const inboxRow = (overrides: Record<string, unknown>) => ({
  __typename: "InboxConversation",
  conversationId: "c1",
  kind: "chat",
  source: "open_media",
  title: "Ada Lovelace",
  initials: "AL",
  avatarColor: null,
  avatarUrl: null,
  group: false,
  company: null,
  preview: "See you then",
  lastMessageAt: "2026-11-17T12:00:00+00:00",
  unreadCount: 0,
  ideaId: null,
  ideaTitle: null,
  canReply: true,
  ...overrides,
});

const inbox = [
  inboxRow({ ideaTitle: "Tidy", ideaId: "i1" }),
  inboxRow({
    conversationId: "company:doordash.com",
    kind: "email",
    source: "gmail",
    title: "DoorDash",
    initials: "D",
    company: "doordash.com",
    preview: "Your order is on its way",
    lastMessageAt: "2026-11-17T11:00:00+00:00",
    unreadCount: 2,
  }),
];

const inboxMock = (rows = inbox) => ({
  request: { query: GET_MY_INBOX, variables: { limit: 100 } },
  result: { data: { myInbox: rows } },
});

const threadMock = {
  request: { query: GET_INBOX_CONVERSATION, variables: { conversationId: "company:doordash.com" } },
  result: {
    data: {
      inboxConversation: {
        __typename: "InboxThread",
        conversation: inbox[1],
        items: [
          { __typename: "InboxItem", kind: "time", key: "time-m1", at: "2026-11-17T11:00:00+00:00", messageId: null, isMine: false, senderName: null, sentAt: null, source: null, subject: null, body: [], attachmentCount: 0, quotedHistoryHidden: false, groupStart: true, groupEnd: true },
          {
            __typename: "InboxItem", kind: "message", key: "m1", at: null, messageId: "m1", isMine: false, senderName: "DoorDash",
            sentAt: "2026-11-17T11:00:00+00:00", source: "gmail", subject: "Your order",
            body: [{ __typename: "InboxTextSegment", text: "Your order is on its way. ", url: null }, { __typename: "InboxTextSegment", text: "Track it", url: "https://doordash.com/t" }],
            attachmentCount: 0, quotedHistoryHidden: true, groupStart: true, groupEnd: true,
          },
        ],
      },
    },
  },
};

const replyMock = {
  request: { query: REPLY_IN_INBOX },
  variableMatcher: (vars: Record<string, unknown>) => vars.conversationId === "company:doordash.com" && vars.content === "Thanks!",
  result: { data: { replyInInbox: true } },
};

const readMock = {
  request: { query: MARK_INBOX_READ, variables: { conversationId: "company:doordash.com" } },
  result: { data: { markInboxRead: true } },
};

const renderPage = (mocks: unknown[], path = "/messages") =>
  render(
    <MockedProvider mocks={mocks as never}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/messages" element={<MessagesPage />} />
          <Route path="/messages/:conversationId" element={<MessagesPage />} />
        </Routes>
      </MemoryRouter>
    </MockedProvider>,
  );

describe("MessagesPage", () => {
  beforeEach(() => {
    userVar({ isLoggedIn: true, authChecked: true, isGuest: false, userData: { userId: "u1" } as never });
  });
  afterEach(() => {
    userVar({ isLoggedIn: false, authChecked: false, isGuest: false, userData: null });
  });

  it("shows chats and email in one list, with no tabs", async () => {
    renderPage([linkMock(), inboxMock()]);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("DoorDash")).toBeInTheDocument();
    expect(screen.getByText("Re: Tidy")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-row-company:doordash.com")).toHaveAccessibleName(/2 unread/);
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.getByTestId("messages-empty-state")).toBeInTheDocument();
  });

  it("searches the list by person, company, message and idea", async () => {
    renderPage([linkMock(), inboxMock()]);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("inbox-search"), { target: { value: "order way" } });
    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument();
    expect(screen.getByText("DoorDash")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("inbox-search"), { target: { value: "tidy" } });
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.queryByText("DoorDash")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("inbox-search"), { target: { value: "nobody" } });
    expect(screen.getByTestId("inbox-no-match")).toBeInTheDocument();
  });

  it("filters to unread conversations and says when all are read", async () => {
    renderPage([linkMock(), inboxMock()]);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("inbox-unread-filter"));
    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument();
    expect(screen.getByText("DoorDash")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-unread-filter")).toHaveAttribute("aria-pressed", "true");
  });

  it("says when everything is read under the unread filter", async () => {
    renderPage([linkMock(), inboxMock([inbox[0]])]);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("inbox-unread-filter"));
    expect(screen.getByTestId("inbox-caught-up")).toBeInTheDocument();
  });

  it("explains an empty inbox", async () => {
    renderPage([linkMock(), inboxMock([])]);
    expect(await screen.findByTestId("inbox-empty")).toBeInTheDocument();
  });

  it("opens an email as Open Media lays it out and replies to it", async () => {
    renderPage([linkMock(), inboxMock(), threadMock, readMock, replyMock, threadMock, inboxMock()], "/messages/company%3Adoordash.com");
    expect(await screen.findByText("Your order")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Track it" })).toHaveAttribute("href", "https://doordash.com/t");
    fireEvent.change(screen.getByTestId("inbox-composer"), { target: { value: "Thanks!" } });
    fireEvent.click(screen.getByTestId("inbox-send"));
    // The reply shows at once while it's on its way, and the composer is ready for the next one.
    expect(screen.getByTestId("inbox-composer")).toHaveValue("");
    expect(screen.getByText("Thanks!")).toBeInTheDocument();
    expect(screen.getByText("Sending…")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Sending…")).not.toBeInTheDocument());
  });

  it("keeps a failed reply on screen with a way to try again", async () => {
    const failing = { ...replyMock, result: undefined, error: new Error("Open Media didn't answer.") };
    renderPage([linkMock(), inboxMock(), threadMock, readMock, failing], "/messages/company%3Adoordash.com");
    expect(await screen.findByText("Your order")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("inbox-composer"), { target: { value: "Thanks!" } });
    fireEvent.keyDown(screen.getByTestId("inbox-composer"), { key: "Enter" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not delivered");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByTestId("inbox-composer")).toHaveValue("Thanks!");
  });

  it("asks to connect Open Media before showing messages", async () => {
    renderPage([linkMock({ linked: false, handle: null })]);
    expect(await screen.findByTestId("open-media-connect-prompt")).toBeInTheDocument();
    expect(screen.getByTestId("open-media-connect-link")).toHaveAttribute(
      "href",
      "/api/auth/open-media/start?next=%2F",
    );
    expect(screen.queryByText("Inbox")).not.toBeInTheDocument();
  });

  it("asks to reconnect when the link expired", async () => {
    renderPage([linkMock({ needsReconnect: true })]);
    expect(await screen.findByText(/Your Open Media connection expired/)).toBeInTheDocument();
  });

  it("explains when this server has no Open Media", async () => {
    renderPage([linkMock({ enabled: false, linked: false })]);
    expect(await screen.findByTestId("messages-unavailable")).toBeInTheDocument();
  });
});
