import React from "react";
import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import OpenMediaSection from "features/account/components/OpenMediaSection";
import { userVar } from "features/core/apollo/localState";
import { GET_OPEN_MEDIA_LINK } from "features/core/apollo/queries";

const link = (overrides: Record<string, unknown>) => ({
  request: { query: GET_OPEN_MEDIA_LINK },
  result: {
    data: {
      openMediaLink: {
        enabled: true,
        linked: false,
        needsReconnect: false,
        handle: null,
        displayName: null,
        connectUrl: "/api/integrations/open-media/connect",
        ...overrides,
      },
    },
  },
});

const renderSection = (overrides: Record<string, unknown>) =>
  render(
    <MockedProvider mocks={[link(overrides)]}>
      <OpenMediaSection />
    </MockedProvider>,
  );

describe("OpenMediaSection (Account settings)", () => {
  beforeEach(() => {
    userVar({ isLoggedIn: true, authChecked: true, isGuest: false, userData: { userId: "u1" } as never });
  });
  afterEach(() => {
    userVar({ isLoggedIn: false, authChecked: false, isGuest: false, userData: null });
  });

  it("offers Connect Open Media when not linked", async () => {
    renderSection({});
    const connect = await screen.findByTestId("open-media-connect-button");
    expect(connect).toHaveAttribute("href", "/api/integrations/open-media/connect");
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });

  it("shows the linked handle and a disconnect action", async () => {
    renderSection({ linked: true, handle: "ada" });
    expect(await screen.findByText("Connected as @ada.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(screen.queryByTestId("open-media-connect-button")).not.toBeInTheDocument();
  });

  it("asks to reconnect an expired link", async () => {
    renderSection({ linked: true, handle: "ada", needsReconnect: true });
    expect(await screen.findByText(/expired/)).toBeInTheDocument();
    expect(screen.getByTestId("open-media-connect-button")).toHaveTextContent("Reconnect Open Media");
  });

  it("explains when Open Media is off on this server", async () => {
    renderSection({ enabled: false });
    expect(await screen.findByText(/isn't available on this server/)).toBeInTheDocument();
    expect(screen.queryByTestId("open-media-connect-button")).not.toBeInTheDocument();
  });
});
