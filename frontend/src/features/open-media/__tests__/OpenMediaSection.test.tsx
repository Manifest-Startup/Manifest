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
        connectUrl: "/api/auth/open-media/start",
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

  it("offers Continue with Open Media when the account is not linked yet", async () => {
    renderSection({});
    const connect = await screen.findByTestId("open-media-connect-button");
    expect(connect).toHaveAttribute("href", "/api/auth/open-media/start?next=%2F");
    expect(connect).toHaveTextContent("Continue with Open Media");
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });

  it("says which Open Media account signs in and links to its security settings", async () => {
    renderSection({ linked: true, handle: "ada" });
    expect(await screen.findByText("Signed in with Open Media @ada.")).toBeInTheDocument();
    expect(screen.getByTestId("open-media-security-link")).toHaveAttribute("href", "https://openmedia.site/signin");
    expect(screen.getByText("Manage sign-in and security")).toBeInTheDocument();
    expect(screen.queryByTestId("open-media-connect-button")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });

  it("asks to continue with Open Media again when the link expired", async () => {
    renderSection({ linked: true, handle: "ada", needsReconnect: true });
    expect(await screen.findByText(/expired/)).toBeInTheDocument();
    expect(screen.getByTestId("open-media-connect-button")).toHaveTextContent("Continue with Open Media");
  });

  it("still shows the sign-in account when Messages and Pitch Shorts are off", async () => {
    renderSection({ enabled: false, linked: true, handle: "ada" });
    expect(await screen.findByText("Signed in with Open Media @ada.")).toBeInTheDocument();
    expect(screen.getByText(/off on this server/)).toBeInTheDocument();
  });
});
