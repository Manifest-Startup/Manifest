import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing/react";

import MessagesPage from "../MessagesPage";
import { userVar } from "features/core/apollo/localState";
import { GET_MY_CONVERSATIONS, GET_OPEN_MEDIA_LINK } from "features/core/apollo/queries";

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

const conversationsMock = {
  request: { query: GET_MY_CONVERSATIONS, variables: { limit: 50, offset: 0 } },
  result: { data: { myConversations: [] } },
};

const renderPage = (mocks: unknown[]) =>
  render(
    <MockedProvider mocks={mocks as never}>
      <MemoryRouter initialEntries={["/messages"]}>
        <Routes>
          <Route path="/messages" element={<MessagesPage />} />
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

  it("renders inbox layout and empty state once Open Media is linked", async () => {
    renderPage([linkMock(), conversationsMock]);
    expect(await screen.findByTestId("messages-empty-state")).toBeInTheDocument();
    expect(screen.getByText("Inbox")).toBeInTheDocument();
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
