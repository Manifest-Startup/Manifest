import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { userVar } from "features/core/apollo/localState";
import PrivateRoute from "../PrivateRoute";

const mockSetMessage = jest.fn();

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

const renderProtectedRoute = () =>
  render(
    <MemoryRouter initialEntries={["/protected"]}>
      <Routes>
        <Route
          path="/protected"
          element={
            <PrivateRoute>
              <div data-testid="protected">ok</div>
            </PrivateRoute>
          }
        />
        <Route path="/login" element={<div data-testid="auth">auth</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe("PrivateRoute", () => {
  afterEach(() => {
    userVar({ isLoggedIn: false, authChecked: true, isGuest: false, userData: null });
    jest.clearAllMocks();
  });

  it("renders children when a guest user is already synced", () => {
    userVar({
      isLoggedIn: true,
      authChecked: true,
      isGuest: true,
      userData: { userId: "guest-1", email: "guest@guest.manifest" },
    });

    renderProtectedRoute();

    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("does not show the access message during a logout redirect", () => {
    sessionStorage.setItem("manifest_logout_redirect", "1");
    userVar({ isLoggedIn: false, authChecked: true, isGuest: false, userData: null });

    renderProtectedRoute();

    expect(mockSetMessage).not.toHaveBeenCalled();
    sessionStorage.removeItem("manifest_logout_redirect");
  });
});
