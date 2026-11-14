import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import PrivacyControlsPanel from "../PrivacyControlsPanel";
import { PrivacyConsentProvider } from "features/privacy/PrivacyConsentContext";

const renderPanel = (ui: React.ReactElement) =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{ui}</MemoryRouter>
  );

const mockRequestDeletion = jest.fn();
const mockSetMessage = jest.fn();

jest.mock("@apollo/client/react", () => {
  const actual = jest.requireActual("@apollo/client/react");
  return {
    ...actual,
    useQuery: () => ({
      data: {
        privacyStatus: {
          exportAvailable: true,
          deletionRequestedAt: null,
          guestRetentionDays: 30,
          passwordResetRetentionMinutes: 30,
        },
      },
      loading: false,
      refetch: jest.fn(),
    }),
    useMutation: () => [mockRequestDeletion, { loading: false }],
  };
});

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

jest.mock("features/privacy/analyticsClient", () => ({
  syncAnalyticsConsent: jest.fn(),
  canCaptureAnalytics: jest.fn(() => false),
  captureAnalyticsEvent: jest.fn(),
  hasAnalyticsConfiguration: jest.fn(() => true),
}));

describe("PrivacyControlsPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it("renders retention details and privacy controls", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        hasStoredPreference: true,
        necessaryEnabled: true,
        analyticsEnabled: true,
        communicationsEnabled: false,
        doNotSellOrShare: false,
        policyVersion: "2026-04",
        consentUpdatedAt: "2026-04-18T00:00:00+00:00",
        source: "account_privacy_panel",
      }),
    }) as unknown as typeof fetch;

    renderPanel(
      <PrivacyConsentProvider>
        <PrivacyControlsPanel accountEmail="hello@manifeststartup.com" />
      </PrivacyConsentProvider>
    );

    expect(await screen.findByText(/Tracking and outreach/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Save privacy choices/i })).toBeInTheDocument();
    expect(screen.getByText(/30 day retention window/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/Product analytics/i)).toBeChecked();
    });
  });

  it("saves updated privacy choices", async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          hasStoredPreference: true,
          necessaryEnabled: true,
          analyticsEnabled: false,
          communicationsEnabled: false,
          doNotSellOrShare: true,
          policyVersion: "2026-04",
          consentUpdatedAt: "2026-04-18T00:00:00+00:00",
          source: "account_privacy_panel",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          hasStoredPreference: true,
          necessaryEnabled: true,
          analyticsEnabled: true,
          communicationsEnabled: false,
          doNotSellOrShare: false,
          policyVersion: "2026-04",
          consentUpdatedAt: "2026-04-18T01:00:00+00:00",
          source: "account_privacy_panel",
        }),
      });
    global.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();

    renderPanel(
      <PrivacyConsentProvider>
        <PrivacyControlsPanel accountEmail="hello@manifeststartup.com" />
      </PrivacyConsentProvider>
    );

    await screen.findByRole("button", { name: /Save privacy choices/i });
    await user.click(screen.getByLabelText(/Product analytics/i));
    await user.click(screen.getByRole("button", { name: /Save privacy choices/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(mockSetMessage).toHaveBeenCalledWith("Privacy choices updated.", "success");
  });
});
