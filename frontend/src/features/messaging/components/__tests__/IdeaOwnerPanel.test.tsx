import React from "react";
import { render, screen } from "@testing-library/react";

import { GET_IDEA_CORE, GET_IDEA_OWNER, GET_OPEN_MEDIA_LINK } from "features/core/apollo/queries";

import IdeaOwnerPanel from "../IdeaOwnerPanel";

const mockSetMessage = jest.fn();
const mockStartConversation = jest.fn();
const mockUseQuery = jest.fn();

const linkResult = (overrides: Record<string, unknown> = {}) => ({
  data: {
    openMediaLink: {
      enabled: true,
      linked: true,
      needsReconnect: false,
      handle: "viewer",
      displayName: "Viewer",
      connectUrl: "/api/integrations/open-media/connect",
      ...overrides,
    },
  },
  loading: false,
  error: null,
});
let mockLinkResult = linkResult();

const defaultCoreResult = {
  data: {
    idea: {
      ideaId: "idea-1",
      userId: "owner-1",
      title: "AI Fitness App",
      description: "",
      isPublished: true,
    },
  },
  loading: false,
  error: null,
};

const defaultOwnerResult = {
  data: {
    ideaOwner: {
      userId: "owner-1",
      firstName: "Mihir",
      lastName: "Shah",
      username: "mihir",
      profilePictureUrl: null,
      bio: "Founder and builder.",
      ideaTitle: "AI Fitness App",
      isPublished: true,
      canMessage: true,
      openMediaHandle: "mihir" as string | null,
    },
  },
  loading: false,
  error: null,
};

function setupDualQueryMock(
  core: typeof defaultCoreResult = defaultCoreResult,
  owner: typeof defaultOwnerResult = defaultOwnerResult,
) {
  mockUseQuery.mockImplementation((doc: unknown, options?: { skip?: boolean }) => {
    if (doc === GET_IDEA_CORE) {
      return core;
    }
    if (doc === GET_OPEN_MEDIA_LINK) {
      return mockLinkResult;
    }
    if (doc === GET_IDEA_OWNER) {
      if (options?.skip) {
        return { data: undefined, loading: false, error: null };
      }
      return owner;
    }
    return { data: undefined, loading: false, error: null };
  });
}

jest.mock("features/ideas/components/SimilarIdeas", () => ({
  __esModule: true,
  default: ({ headerAction }: { headerAction?: React.ReactNode }) => (
    <div data-testid="similar-ideas-stub">
      <span>Similar Ideas</span>
      {headerAction}
    </div>
  ),
}));

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: "info" as const },
  }),
}));

jest.mock("@apollo/client/react", () => {
  const actual = jest.requireActual("@apollo/client/react");
  return {
    ...actual,
    useMutation: () => [mockStartConversation, { loading: false }],
    useApolloClient: () => ({ refetchQueries: jest.fn(), query: jest.fn() }),
    useQuery: (...args: unknown[]) => mockUseQuery(...args),
    useReactiveVar: (reactiveVar: () => unknown) => {
      const localState = require("features/core/apollo/localState");
      if (reactiveVar === localState.userVar) {
        return {
          isLoggedIn: true,
          userData: {
            userId: "viewer-1",
          },
        };
      }

      return reactiveVar();
    },
  };
});

describe("IdeaOwnerPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLinkResult = linkResult();
    setupDualQueryMock();
  });

  const ownerWith = (overrides: Record<string, unknown>) => ({
    ...defaultOwnerResult,
    data: { ideaOwner: { ...defaultOwnerResult.data.ideaOwner, ...overrides } },
  });

  it("explains when the founder has not connected Open Media", () => {
    setupDualQueryMock(defaultCoreResult, ownerWith({ canMessage: false, openMediaHandle: null }));
    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    expect(screen.getByText(/hasn't connected Open Media yet/)).toBeInTheDocument();
    expect(screen.getByTestId("message-founder-button")).toBeDisabled();
  });

  it("offers to connect Open Media when the viewer has not linked", () => {
    mockLinkResult = linkResult({ linked: false, handle: null });
    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    expect(screen.getByTestId("open-media-connect-prompt")).toBeInTheDocument();
    expect(screen.queryByTestId("message-founder-button")).not.toBeInTheDocument();
  });

  it("hides founder messaging when Open Media is off on this server", () => {
    mockLinkResult = linkResult({ enabled: false, linked: false });
    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    expect(screen.queryByTestId("founder-messaging")).not.toBeInTheDocument();
    expect(screen.getByText("Founder and builder.")).toBeInTheDocument();
  });

  it("starts the conversation with the founder's Manifest id and the idea", async () => {
    mockStartConversation.mockResolvedValue({ data: { startConversation: { conversationId: "c1" } } });
    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    screen.getByTestId("message-founder-button").click();
    expect(mockStartConversation).toHaveBeenCalledWith({
      variables: { otherUserId: "owner-1", ideaId: "idea-1" },
    });
  });

  it("puts similar ideas first and uses simpler founder labels", () => {
    render(<IdeaOwnerPanel ideaId="idea-1" onToggleCollapse={jest.fn()} similarIdeas="# Similar Landscape" />);

    const similarIdeas = screen.getByTestId("similar-ideas-stub");
    const founderHeading = screen.getAllByText("Founder")[0];

    expect(similarIdeas.compareDocumentPosition(founderHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByText("Message founder").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Founder and builder.")).toBeInTheDocument();
  });

  it("uses a scroll container so similar ideas do not clip in the right rail", () => {
    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    expect(screen.getByTestId("idea-owner-panel-scroll")).toHaveClass("overflow-y-auto", "overflow-x-hidden");
  });

  it("renders a clear icon button in collapsed mode", () => {
    render(<IdeaOwnerPanel ideaId="idea-1" collapsed onToggleCollapse={jest.fn()} />);

    const expandButton = screen.getByLabelText("Expand similar ideas");
    expect(expandButton.querySelector("svg")).toBeInTheDocument();
    expect(screen.getByText("Similar")).toBeInTheDocument();
    expect(expandButton).toHaveClass("manifest-control-secondary", "h-12", "w-12");
  });

  it("renders the expanded collapse control inside the similar ideas header", () => {
    render(<IdeaOwnerPanel ideaId="idea-1" onToggleCollapse={jest.fn()} similarIdeas="# Similar Landscape" />);

    const collapseButton = screen.getByLabelText("Collapse similar ideas");
    expect(collapseButton).toBeInTheDocument();
    expect(collapseButton).toHaveClass("manifest-control-ghost", "h-11", "w-11");
  });

  it("disables founder messaging when the idea is not published", () => {
    setupDualQueryMock(defaultCoreResult, {
      data: {
        ideaOwner: {
          userId: "owner-1",
          firstName: "Mihir",
          lastName: "Shah",
          username: "mihir",
          profilePictureUrl: null,
          bio: "Founder and builder.",
          ideaTitle: "AI Fitness App",
          isPublished: false,
          canMessage: false,
          openMediaHandle: "mihir",
        },
      },
      loading: false,
      error: null,
    });

    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    expect(screen.getByRole("button", { name: /publish to message/i })).toBeDisabled();
  });

  it("hides the founder section when the viewer owns the idea", () => {
    setupDualQueryMock({
      data: {
        idea: {
          ideaId: "idea-1",
          userId: "viewer-1",
          title: "My App",
          description: "",
          isPublished: false,
        },
      },
      loading: false,
      error: null,
    });

    render(<IdeaOwnerPanel ideaId="idea-1" onToggleCollapse={jest.fn()} similarIdeas="# Similar Landscape" />);

    expect(screen.queryByRole("heading", { name: "Founder" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("message-founder-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("similar-ideas-stub")).toBeInTheDocument();
  });

  it("shows only similar ideas while idea core is loading (no founder skeleton)", () => {
    setupDualQueryMock(
      { data: undefined, loading: true, error: null },
      defaultOwnerResult,
    );

    render(<IdeaOwnerPanel ideaId="idea-1" similarIdeas="# Similar Landscape" />);

    expect(screen.queryByText("Loading founder...")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Founder" })).not.toBeInTheDocument();
    expect(screen.getByTestId("similar-ideas-stub")).toBeInTheDocument();
  });
});
