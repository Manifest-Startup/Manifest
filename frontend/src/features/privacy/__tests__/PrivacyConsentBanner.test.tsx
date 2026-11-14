import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PrivacyConsentBanner from "../PrivacyConsentBanner";
import { PrivacyConsentProvider } from "../PrivacyConsentContext";

jest.mock("features/privacy/analyticsClient", () => ({
  syncAnalyticsConsent: jest.fn(),
  canCaptureAnalytics: jest.fn(() => false),
  captureAnalyticsEvent: jest.fn(),
  hasAnalyticsConfiguration: jest.fn(() => true),
}));

describe("PrivacyConsentBanner", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it("shows the banner when no stored preference exists", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        hasStoredPreference: false,
        necessaryEnabled: true,
        analyticsEnabled: false,
        communicationsEnabled: false,
        doNotSellOrShare: false,
        policyVersion: "2026-04",
        consentUpdatedAt: null,
        source: "default",
      }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    render(
      <PrivacyConsentProvider>
        <PrivacyConsentBanner />
      </PrivacyConsentProvider>,
    );

    expect(await screen.findByText(/Privacy choices/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Essential only/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Accept all/i })).toBeInTheDocument();
  });

  it("posts consent when the user accepts all", async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          hasStoredPreference: false,
          necessaryEnabled: true,
          analyticsEnabled: false,
          communicationsEnabled: false,
          doNotSellOrShare: false,
          policyVersion: "2026-04",
          consentUpdatedAt: null,
          source: "default",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          hasStoredPreference: true,
          necessaryEnabled: true,
          analyticsEnabled: true,
          communicationsEnabled: true,
          doNotSellOrShare: false,
          policyVersion: "2026-04",
          consentUpdatedAt: "2026-04-18T00:00:00+00:00",
          source: "banner_accept_all",
        }),
      });
    global.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();

    render(
      <PrivacyConsentProvider>
        <PrivacyConsentBanner />
      </PrivacyConsentProvider>,
    );

    await screen.findByText(/Privacy choices/i);
    await user.click(screen.getByRole("button", { name: /Accept all/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/privacy/consent");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "POST",
      credentials: "include",
    });
  });
});
