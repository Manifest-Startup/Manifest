import React from "react";
import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { MemoryRouter } from "react-router-dom";

import { userVar } from "features/core/apollo/localState";
import GuestSessionBanner from "../GuestSessionBanner";

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({ setMessage: jest.fn(), clearMessage: jest.fn(), message: { text: null, type: "info" } }),
}));

describe("GuestSessionBanner", () => {
  afterEach(() => userVar({ isLoggedIn: false, authChecked: false, isGuest: false, userData: null }));

  it("sends guests to Continue with Open Media and back to the same page", () => {
    userVar({ isLoggedIn: true, authChecked: true, isGuest: true, userData: { userId: "g1", email: "g@guest.manifest" } });
    render(
      <MockedProvider mocks={[]}>
        <MemoryRouter initialEntries={["/ideas/abc?tab=deck"]}>
          <GuestSessionBanner />
        </MemoryRouter>
      </MockedProvider>,
    );
    const cta = screen.getByTestId("guest-continue-with-open-media");
    expect(cta).toHaveTextContent("Continue with Open Media");
    expect(cta).toHaveAttribute("href", "/api/auth/open-media/start?next=%2Fideas%2Fabc%3Ftab%3Ddeck");
  });

  it("stays hidden for full accounts", () => {
    userVar({ isLoggedIn: true, authChecked: true, isGuest: false, userData: { userId: "u1", email: "a@b.c" } });
    render(
      <MockedProvider mocks={[]}>
        <MemoryRouter>
          <GuestSessionBanner />
        </MemoryRouter>
      </MockedProvider>,
    );
    expect(screen.queryByTestId("guest-continue-with-open-media")).not.toBeInTheDocument();
  });
});
