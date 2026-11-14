import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import ApiDocsPage from "./ApiDocsPage";
import DocsHubPage from "./DocsHubPage";
import LegalDocumentPage from "./LegalDocumentPage";
import UserGuidePage from "./UserGuidePage";

const mockFetch = jest.fn();

describe("Docs pages", () => {
  beforeAll(() => {
    Object.defineProperty(global, "fetch", {
      writable: true,
      value: mockFetch,
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockImplementation((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input.toString();

      if (path.includes("VOICE_AGENT_API.md")) {
        return Promise.resolve({
          ok: true,
          text: async () => "# Voice Agent API\n\nVoice details.",
        });
      }

      if (path.includes("TERMS_OF_SERVICE.md")) {
        return Promise.resolve({
          ok: true,
          text: async () => "# Manifest Terms of Service\n\nTerms details.",
        });
      }

      if (path.includes("PRIVACY_POLICY.md")) {
        return Promise.resolve({
          ok: true,
          text: async () => "# Manifest Privacy Policy\n\nPrivacy details.",
        });
      }

      return Promise.resolve({
        ok: true,
        text: async () => "# Manifest API Reference\n\nCanonical API details.",
      });
    });
  });

  const renderRoute = (initialEntry: string) =>
    render(
      <MemoryRouter
        initialEntries={[initialEntry]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/docs" element={<DocsHubPage />} />
          <Route path="/docs/guide" element={<UserGuidePage />} />
          <Route path="/docs/api" element={<ApiDocsPage />} />
          <Route path="/legal/terms" element={<LegalDocumentPage />} />
          <Route path="/legal/privacy" element={<LegalDocumentPage />} />
        </Routes>
      </MemoryRouter>,
    );

  it("renders the docs hub route", () => {
    renderRoute("/docs");

    expect(screen.getByRole("heading", { name: /^Documentation$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open user guide/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open API reference/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open legal pages/i })).toBeInTheDocument();
  });

  it("renders the user guide route", () => {
    renderRoute("/docs/guide");

    expect(screen.getByRole("heading", { name: /^User guide$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View API docs/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ideas workspace/i })).toBeInTheDocument();
  });

  it("renders the API docs route and loads the synced markdown reference", async () => {
    renderRoute("/docs/api");

    expect(screen.getByRole("heading", { name: /^API reference$/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /Manifest API Reference/i })).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith("/docs/API.md", expect.any(Object));
  });

  it("renders the terms route and loads the synced legal markdown reference", async () => {
    renderRoute("/legal/terms");

    expect(screen.getByRole("heading", { name: /^Terms of Service$/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /Manifest Terms of Service/i })).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith("/docs/TERMS_OF_SERVICE.md", expect.any(Object));
  });
});
