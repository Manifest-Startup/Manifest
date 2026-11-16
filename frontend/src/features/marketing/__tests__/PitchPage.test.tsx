import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import PitchPage from "../components/PitchPage";

const mockNavigate = jest.fn();
const mockStartGuestSession = jest.fn(() => Promise.resolve({ data: {} }));
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

function renderPitchPage() {
  return render(
    <MemoryRouter>
      <PitchPage />
    </MemoryRouter>,
  );
}

describe("PitchPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders a concise demo landing page", () => {
    renderPitchPage();

    expect(screen.getByRole("heading", { name: /Turn your idea into a plan/i })).toBeInTheDocument();
    expect(screen.getByText(/Manifest is still being built/i)).toBeInTheDocument();
    expect(screen.getAllByText(/not operational/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: /Explore the demo/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /How it works/i })).toBeInTheDocument();
  });

  it("does not present voice mode on the landing page", () => {
    renderPitchPage();

    expect(screen.queryByText(/voice/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /voice/i })).not.toBeInTheDocument();
  });

  it("opens the product walkthrough", async () => {
    const user = userEvent.setup();
    renderPitchPage();

    await user.click(screen.getByRole("button", { name: /How it works/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/learn-more");
  });

  it("navigates to sign in", async () => {
    const user = userEvent.setup();
    renderPitchPage();

    await user.click(screen.getByRole("button", { name: /Sign in/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/login");
  });
});
