import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import UniversalSearch from "../components/UniversalSearch";
import { sidebarVar } from "features/core/apollo/localState";

const mockNavigate = jest.fn();
const mockSetMessage = jest.fn();
const mockQuery = jest.fn();
const mockCreateIdea = jest.fn();
const mockUseSafeQuery = jest.fn();
const mockApolloClient = { query: mockQuery };

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

jest.mock("@apollo/client/react", () => {
  const actual = jest.requireActual("@apollo/client/react");
  return {
    ...actual,
    useApolloClient: () => mockApolloClient,
    useMutation: () => [
      mockCreateIdea,
      { loading: false },
    ],
  };
});

jest.mock("features/common-ui/api/useSafeQuery", () => ({
  useSafeQuery: (...args: unknown[]) => mockUseSafeQuery(...args),
}));

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

const renderSearch = () =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <UniversalSearch />
    </MemoryRouter>
  );

describe("UniversalSearch", () => {
  beforeAll(() => {
    window.requestAnimationFrame = ((callback: FrameRequestCallback) => window.setTimeout(callback, 0)) as typeof window.requestAnimationFrame;
    window.cancelAnimationFrame = ((id: number) => window.clearTimeout(id)) as typeof window.cancelAnimationFrame;
  });

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockUseSafeQuery.mockReturnValue({
      data: {
        ideas: [
          {
            ideaId: "recent-1",
            title: "Recent Idea",
            description: "<p>Latest workspace note.</p>",
            isPublished: false,
          },
        ],
      },
    });
    sidebarVar({
      currentIdeaId: null,
      currentIdeaAspect: "description",
      allIdeaIds: [],
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("opens from the keyboard shortcut and shows quick start with recent notes", async () => {
    renderSearch();

    expect(
      screen.getByRole("button", { name: "Search ideas, notes, and the web" })
    ).toBeInTheDocument();
    expect(screen.queryByText(/jump into recent work/i)).not.toBeInTheDocument();

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByLabelText(/search everything/i)).toBeInTheDocument();
    expect(await screen.findByText("New blank idea")).toBeInTheDocument();
    expect(await screen.findByText("Recent Idea")).toBeInTheDocument();
  });

  it("searches and opens an existing note with arrow keys", async () => {
    mockQuery
      .mockResolvedValueOnce({
        data: {
          universalSearch: {
            query: "factory ops",
            assistantSummary: null,
            webSummary: null,
            myIdeas: [
              {
                ideaId: "idea-1",
                title: "AI Supply Chain Copilot",
                snippet: "Predicts vendor and inventory issues for factories.",
                matchedIn: "Description",
                createdAt: "2026-03-13T18:00:00Z",
                userId: "test-user",
                isPublished: false,
              },
            ],
            publishedIdeas: [],
            webSources: [],
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          universalSearch: {
            query: "factory ops",
            assistantSummary: null,
            webSummary: null,
            myIdeas: [
              {
                ideaId: "idea-1",
                title: "AI Supply Chain Copilot",
                snippet: "Predicts vendor and inventory issues for factories.",
                matchedIn: "Description",
                createdAt: "2026-03-13T18:00:00Z",
                userId: "test-user",
                isPublished: false,
              },
            ],
            publishedIdeas: [],
            webSources: [],
          },
        },
      });

    renderSearch();

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = await screen.findByLabelText(/search everything/i);
    fireEvent.change(input, { target: { value: "factory ops" } });

    await act(async () => {
      jest.advanceTimersByTime(700);
      await Promise.resolve();
    });

    expect(await screen.findByText("AI Supply Chain Copilot")).toBeInTheDocument();

    fireEvent.keyDown(input, { key: "ArrowDown" });
    await waitFor(() =>
      expect(screen.getByText("AI Supply Chain Copilot").closest("button")).toHaveAttribute("aria-selected", "true")
    );
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/ideas/idea-1/description"));
  });

  it("creates a new idea from the search brief", async () => {
    const query = "workflow ai";
    const assistantSummary = "Unified search demand is strongest where teams want AI to blend notes, research, and execution context.";
    const webSources = [
      {
        title: "Enterprise search report",
        url: "https://example.com/enterprise-search-report",
        hostname: "example.com",
      },
    ];

    mockQuery
      .mockResolvedValueOnce({
        data: {
          universalSearch: {
            query,
            assistantSummary: null,
            webSummary: null,
            myIdeas: [],
            publishedIdeas: [],
            webSources: [],
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          universalSearch: {
            query,
            assistantSummary,
            webSummary: "Teams increasingly expect a single search surface for notes and research.",
            myIdeas: [],
            publishedIdeas: [],
            webSources,
          },
        },
      });
    mockCreateIdea.mockResolvedValue({
      data: {
        createIdea: {
          ideaId: "created-1",
          title: "workflow ai",
          description: "Idea seed: workflow ai",
        },
      },
    });

    renderSearch();

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = await screen.findByLabelText(/search everything/i);
    fireEvent.change(input, { target: { value: query } });

    await act(async () => {
      jest.advanceTimersByTime(700);
      await Promise.resolve();
    });

    expect(await screen.findByText("New idea")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Unified search demand is strongest where teams want AI to blend notes, research, and execution context."
      )
    ).toBeInTheDocument();
    expect(await screen.findByText("example.com")).toBeInTheDocument();

    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/ideas/created-1/description"));
    expect(mockCreateIdea).toHaveBeenCalledWith({
      variables: {
        title: "workflow ai",
        description: [
          "Idea seed: workflow ai",
          `Manifest search synthesis:\n${assistantSummary}`,
          "Web sources:\n- Enterprise search report: https://example.com/enterprise-search-report",
        ].join("\n\n"),
      },
    });
  });
});
