import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import IntegrationsSection from "../IntegrationsSection";
import { queryState, resetQueryState } from "../integrationsSectionTestQueryState";

// Mock dependencies
const mockSetMessage = jest.fn();

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

jest.mock("@apollo/client/react", () => {
  const actual = jest.requireActual("@apollo/client/react");
  const { GET_INTEGRATIONS: GQ } = jest.requireActual("features/core/apollo/queries");
  const { queryState, refetchMock } = require("../integrationsSectionTestQueryState");
  return {
    ...actual,
    useQuery: (doc: unknown, options?: object) => {
      if (doc === GQ) {
        if (queryState.loading) {
          return { data: undefined, loading: true, error: undefined, refetch: refetchMock };
        }
        return { data: queryState.data ?? undefined, loading: false, error: undefined, refetch: refetchMock };
      }
      return (actual as { useQuery: (d: unknown, o?: object) => unknown }).useQuery(doc, options);
    },
    useMutation: () => [jest.fn(), { loading: false, error: null }],
  };
});

const twoConnectedIntegrations = {
  integrations: [
    {
      integrationId: "1",
      userId: "user-1",
      serviceName: "Google",
      serviceId: "google",
      connectedAt: "2024-01-01T00:00:00Z",
      metadata: null,
    },
    {
      integrationId: "2",
      userId: "user-1",
      serviceName: "GitHub",
      serviceId: "github",
      connectedAt: "2024-01-02T00:00:00Z",
      metadata: null,
    },
  ],
} as const;

const renderSection = (initialEntries = ["/account"]) =>
  render(
    <MemoryRouter
      initialEntries={initialEntries}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IntegrationsSection />
    </MemoryRouter>
  );

describe("IntegrationsSection", () => {
  beforeEach(() => {
    resetQueryState();
    jest.clearAllMocks();
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      headers: {
        get: () => "application/json",
      },
      json: async () => ({ error: "not_configured" }),
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders the integrations section with header", async () => {
    renderSection();
    expect(screen.getByText("Integrations")).toBeInTheDocument();
    expect(screen.getByText(/Connected partners show under Key Partners/i)).toBeInTheDocument();
  });

  it("renders search input", async () => {
    renderSection();
    const searchInput = screen.getByPlaceholderText("Search integrations...");
    expect(searchInput).toBeInTheDocument();
  });

  it("filters integrations by search query", async () => {
    queryState.data = { ...twoConnectedIntegrations };
    renderSection();

    expect(await screen.findByText("Google")).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText("Search integrations...");
    fireEvent.change(searchInput, { target: { value: "GitHub" } });

    await waitFor(() => {
      expect(screen.queryByText("Google")).not.toBeInTheDocument();
      expect(screen.getByText("GitHub")).toBeInTheDocument();
    });
  });

  it("renders category filters", async () => {
    renderSection();

    const allButtons = screen.getAllByRole("button");
    const categoryButtons = allButtons.filter(
      (button) =>
        button.textContent === "All" ||
        button.textContent === "Productivity" ||
        button.textContent === "Social Media" ||
        button.textContent === "Automation"
    );

    expect(categoryButtons.length).toBeGreaterThan(0);
    expect(screen.getAllByText("All").some((el) => el.tagName === "BUTTON")).toBe(true);
  });

  it("filters integrations by category", async () => {
    queryState.data = { ...twoConnectedIntegrations };
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("GitHub")).toBeInTheDocument();
    });

    const developmentButtons = screen.getAllByText("Development");
    const developmentButton = developmentButtons.find((button) => button.tagName === "BUTTON");
    expect(developmentButton).toBeInTheDocument();

    if (developmentButton) {
      fireEvent.click(developmentButton);
    }

    await waitFor(() => {
      expect(screen.getByText("GitHub")).toBeInTheDocument();
    });
  });

  it("shows connected status for connected integrations", async () => {
    queryState.data = { ...twoConnectedIntegrations };
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("Google")).toBeInTheDocument();
    });

    const connectedTexts = screen.getAllByText("Connected");
    expect(connectedTexts.length).toBeGreaterThan(0);

    const googleCard = screen.getByText("Google").closest(".group");
    expect(googleCard).toBeInTheDocument();
  });

  it("calls connect mutation when connecting an integration", async () => {
    const user = userEvent.setup();
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("Slack")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    const slackConnectButton = connectButtons.find(
      (button) => button.closest(".group")?.textContent?.includes("Slack")
    );

    if (slackConnectButton) {
      await user.click(slackConnectButton);
      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalled();
      });
    }
  }, 10000);

  it("calls disconnect mutation when disconnecting an integration", async () => {
    const user = userEvent.setup();
    queryState.data = { ...twoConnectedIntegrations };
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("Google")).toBeInTheDocument();
    });

    const disconnectButtons = screen.getAllByText("Disconnect");
    const googleDisconnectButton = disconnectButtons.find(
      (button) => button.closest(".group")?.textContent?.includes("Google")
    );

    if (googleDisconnectButton) {
      await user.click(googleDisconnectButton);
      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalled();
      });
    }
  }, 10000);

  it("displays loading state", async () => {
    queryState.loading = true;
    queryState.data = null;
    renderSection();
    await waitFor(
      () => {
        expect(screen.getByText("Loading integrations...")).toBeInTheDocument();
      },
      { timeout: 1000 }
    );
  });

  it("displays empty state when no integrations match search", async () => {
    renderSection();
    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText("Search integrations...");
      fireEvent.change(searchInput, { target: { value: "NonExistentIntegration" } });
    });
    await waitFor(() => {
      expect(screen.getByText(/No integrations found matching your search/i)).toBeInTheDocument();
    });
  });

  it("renders integration cards with icons and descriptions", async () => {
    renderSection();
    await waitFor(() => {
      expect(screen.getByText("Google")).toBeInTheDocument();
      expect(screen.getByText(/Connect Google Workspace/i)).toBeInTheDocument();
    });
  });

  it("groups integrations by category", async () => {
    renderSection();
    await waitFor(() => {
      expect(screen.getByText("Google")).toBeInTheDocument();
    });
    const productivityHeaders = screen.getAllByText("Productivity").filter((el) => el.tagName === "H3");
    const developmentHeaders = screen.getAllByText("Development").filter((el) => el.tagName === "H3");
    expect(productivityHeaders.length).toBeGreaterThan(0);
    expect(developmentHeaders.length).toBeGreaterThan(0);
  });

  it("regression #6: shows 'Coming soon' (not 'Connect') for unsupported providers like Trello", async () => {
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("Trello")).toBeInTheDocument();
    });

    // The Trello card should expose the coming-soon affordance and NOT a Connect button.
    expect(screen.getByTestId("integration-coming-soon-trello")).toBeInTheDocument();

    const trelloCard = screen.getByText("Trello").closest(".group");
    expect(trelloCard).toBeInTheDocument();
    expect(trelloCard?.querySelector("button")).toBeNull();
  });

  it("regression #6: also hides Connect for jira, monday, clickup", async () => {
    renderSection();
    await waitFor(() => {
      expect(screen.getByText("Jira")).toBeInTheDocument();
    });
    expect(screen.getByTestId("integration-coming-soon-jira")).toBeInTheDocument();
    expect(screen.getByTestId("integration-coming-soon-monday")).toBeInTheDocument();
    expect(screen.getByTestId("integration-coming-soon-clickup")).toBeInTheDocument();
  });

  it("applies the focusIntegration query param to search and category state", async () => {
    renderSection(["/account?focusIntegration=stripe"]);
    const searchInput = await screen.findByPlaceholderText("Search integrations...");
    await waitFor(() => {
      expect(searchInput).toHaveValue("Stripe");
    });
    const financeCategoryButton = screen.getByRole("button", { name: "Finance" });
    expect(fireEvent.click(financeCategoryButton)).toBe(true);
    expect(screen.getByText("Stripe")).toBeInTheDocument();
  });
});
