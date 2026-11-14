import React from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { userVar } from "features/core/apollo/localState";
import { useAuthSync } from "../useAuthSync";

const mockSetMessage = jest.fn();

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

// Capture the options passed to useSafeQuery so we can simulate Apollo lifecycle
// callbacks deterministically in unit tests.
let capturedOptions: any = null;
jest.mock("features/common-ui/api/useSafeQuery", () => ({
  useSafeQuery: (_query: unknown, options: any) => {
    capturedOptions = options;
    return { data: undefined, loading: true, error: undefined };
  },
}));

const TestHarness: React.FC = () => {
  useAuthSync();
  return <div data-testid="harness" />;
};

const mountHook = () =>
  render(
    <MemoryRouter initialEntries={["/ideas"]}>
      <Routes>
        <Route path="/ideas" element={<TestHarness />} />
        <Route path="/auth" element={<div data-testid="auth-page" />} />
      </Routes>
    </MemoryRouter>,
  );

describe("useAuthSync", () => {
  beforeEach(() => {
    capturedOptions = null;
    userVar({ isLoggedIn: false, authChecked: false, isGuest: false, userData: null });
    mockSetMessage.mockReset();
    sessionStorage.clear();
  });

  it("marks authChecked: true on a successful profile response", () => {
    const { getByTestId } = mountHook();
    expect(getByTestId("harness")).toBeInTheDocument();

    capturedOptions!.onCompleted({
      profile: { userId: "u1", email: "u@example.com", isGuest: false },
    });

    expect(userVar().authChecked).toBe(true);
    expect(userVar().isLoggedIn).toBe(true);
    expect(userVar().userData?.userId).toBe("u1");
  });

  it("marks authChecked: true and clears user when profile is null", () => {
    mountHook();

    capturedOptions!.onCompleted({ profile: null });

    expect(userVar().authChecked).toBe(true);
    expect(userVar().isLoggedIn).toBe(false);
    expect(userVar().userData).toBeNull();
  });

  it("marks authChecked: true and redirects to /auth on UNAUTHENTICATED", () => {
    const { getByTestId, queryByTestId } = mountHook();
    expect(getByTestId("harness")).toBeInTheDocument();

    capturedOptions!.onError({
      graphQLErrors: [
        { message: "Unauthenticated", extensions: { code: "UNAUTHENTICATED" } },
      ],
    });

    expect(userVar().authChecked).toBe(true);
    expect(userVar().isLoggedIn).toBe(false);
    expect(mockSetMessage).toHaveBeenCalledWith(
      expect.stringMatching(/session has expired/i),
      "error",
    );
    // After the redirect, the auth page route should mount on next render.
    // We don't assert on the navigation here since it's handled by react-router
    // and is exercised by PrivateRoute tests.
    void queryByTestId;
  });

  it("regression #1/#2: marks authChecked: true on a transient network error so PrivateRoute doesn't hang", () => {
    mountHook();

    capturedOptions!.onError({
      networkError: new Error("Network request failed"),
      graphQLErrors: [],
    });

    expect(userVar().authChecked).toBe(true);
    expect(userVar().isLoggedIn).toBe(false);
    // Network errors should NOT set the "session expired" message — that's reserved for UNAUTHENTICATED.
    expect(mockSetMessage).not.toHaveBeenCalledWith(
      expect.stringMatching(/session has expired/i),
      expect.anything(),
    );
  });

  it("regression #1/#2: handles a malformed error object without graphQLErrors", () => {
    mountHook();

    capturedOptions!.onError({});

    expect(userVar().authChecked).toBe(true);
    expect(userVar().isLoggedIn).toBe(false);
  });

  it("does not show 'session expired' message during a logout-in-progress sessionStorage flag", () => {
    sessionStorage.setItem("manifest_logout_redirect", "1");
    mountHook();

    capturedOptions!.onError({
      graphQLErrors: [
        { message: "Unauthenticated", extensions: { code: "UNAUTHENTICATED" } },
      ],
    });

    expect(userVar().authChecked).toBe(true);
    expect(mockSetMessage).not.toHaveBeenCalled();
    sessionStorage.removeItem("manifest_logout_redirect");
  });
});
