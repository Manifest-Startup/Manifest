import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { userVar } from "features/core/apollo/localState";
import LoginPage from "../LoginPage";

const mockNavigate = jest.fn();
const mockStartGuestSession = jest.fn();
const mockSetMessage = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

jest.mock("@apollo/client/react", () => ({
  ...jest.requireActual("@apollo/client/react"),
  useMutation: () => [mockStartGuestSession, { loading: false }],
}));

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

type Entry = string | { pathname: string; search?: string; state?: unknown };

const renderLogin = (entry: Entry = "/login") =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe("LoginPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    userVar({ isLoggedIn: false, authChecked: true, isGuest: false, userData: null });
  });

  it("lets a guest go back to their workspace instead of starting another one", () => {
    userVar({ isLoggedIn: true, authChecked: true, isGuest: true, userData: { userId: "g1", email: "g@guest.manifest" } });
    renderLogin();
    expect(screen.getByTestId("back-to-guest-workspace")).toHaveAttribute("href", "/ideas");
    expect(screen.queryByTestId("try-without-account")).not.toBeInTheDocument();
  });

  it("offers one Continue with Open Media button, the guest path and legal links", () => {
    renderLogin();
    expect(screen.getByText("Manifest")).toBeInTheDocument();
    const cta = screen.getByTestId("continue-with-open-media");
    expect(cta).toHaveTextContent("Continue with Open Media");
    expect(cta).toHaveAttribute("href", "/api/auth/open-media/start");
    expect(
      screen.getByText("One account for Manifest and Open Media. Sign in with a passkey, email link or password."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("try-without-account")).toHaveTextContent("Try without an account");
    expect(screen.getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/legal/terms");
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/legal/privacy");
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
  });

  it("returns to the protected page the visitor came from", () => {
    renderLogin({ pathname: "/login", state: { from: { pathname: "/ideas/42", search: "?tab=deck" } } });
    expect(screen.getByTestId("continue-with-open-media")).toHaveAttribute(
      "href",
      "/api/auth/open-media/start?next=%2Fideas%2F42%3Ftab%3Ddeck",
    );
  });

  it.each([
    ["unverified_email", "Confirm your email address in Open Media"],
    ["cancelled", "Sign-in was cancelled"],
    ["linked_elsewhere", "linked to a different Manifest account"],
    ["something-new", "Open Media sign-in didn't finish"],
  ])("explains the %s error from the callback", (code, text) => {
    renderLogin(`/login?error=${code}`);
    expect(screen.getByRole("alert")).toHaveTextContent(text);
  });

  it("starts a guest workspace without an account", async () => {
    mockStartGuestSession.mockResolvedValue({
      data: { startGuestSession: { token: "t", userId: "g1", mergeSecret: "s", email: "guest+g1@guest.manifest" } },
    });
    renderLogin();
    await userEvent.click(screen.getByTestId("try-without-account"));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/ideas"));
    expect(userVar().isGuest).toBe(true);
    expect(localStorage.getItem("access_token")).toBe("t");
  });
});
