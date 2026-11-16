import React from "react";
import { InMemoryCache } from "@apollo/client";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import { userVar } from "features/core/apollo/localState";
import {
  CREATE_PITCH_REEL_COMMENT,
  GET_PITCH_REEL_COMMENTS,
  GET_PITCH_REELS_FEED,
  RESHARE_PITCH_REEL,
  TOGGLE_FOLLOW,
  TOGGLE_PITCH_REEL_LIKE,
} from "features/core/apollo/queries";

import PitchReelsPage from "../PitchReelsPage";

const buildReel = (overrides: Record<string, unknown> = {}) => ({
  __typename: "PitchReel",
  reelId: "aqua-chain",
  slug: "aqua-chain",
  ideaId: "11111111-1111-1111-1111-111111111111",
  title: "AquaChain",
  subtitle: "Compliance-first water data",
  thesis: "Audit trails for every drop.",
  description: "",
  tags: ["Climate"],
  videoUrl: "https://example.com/aqua.mp4",
  videoStatus: "ready",
  workspacePath: "/ideas",
  accentFrom: "#09111f",
  accentTo: "#2f62e8",
  createdAt: "2025-01-01T00:00:00.000Z",
  creator: {
    userId: "creator-manifest-lab",
    handle: "manifestlab",
    name: "Manifest Lab",
    role: "Founder",
    initials: "ML",
    avatar: null,
    followerCount: 12,
    isFollowing: false,
  },
  posterUrl: null,
  stats: {
    likeCount: 2,
    commentCount: 1,
    shareCount: 3,
  },
  viewerState: {
    liked: false,
    reshared: false,
  },
  ...overrides,
});

const COMMENT = {
  __typename: "PitchReelComment",
  commentId: "c1",
  reelId: "aqua-chain",
  authorId: "om-viewer",
  authorName: "Viewer",
  authorHandle: "viewer",
  authorAvatar: null,
  body: "This feels strong on compliance and audit trail.",
  createdAt: "2025-01-02T00:00:00.000Z",
  isMine: true,
};

/** Open Media mutation and comment mocks used by the default render. */
const buildSocialMocks = () => [
  {
    maxUsageCount: 5,
    request: { query: TOGGLE_PITCH_REEL_LIKE, variables: { reelId: "aqua-chain", liked: true } },
    result: { data: { togglePitchReelLike: { reelId: "aqua-chain", liked: true, likeCount: 3 } } },
  },
  {
    maxUsageCount: 5,
    request: { query: RESHARE_PITCH_REEL, variables: { reelId: "aqua-chain", reshared: true } },
    result: { data: { resharePitchReel: { reelId: "aqua-chain", reshared: true, shareCount: 4 } } },
  },
  {
    maxUsageCount: 5,
    request: { query: TOGGLE_FOLLOW, variables: { followedId: "creator-manifest-lab" } },
    result: { data: { toggleFollow: { following: true, followedId: "creator-manifest-lab" } } },
  },
  {
    request: { query: GET_PITCH_REEL_COMMENTS, variables: { reelId: "aqua-chain", limit: 120 } },
    result: { data: { pitchReelComments: [] } },
  },
  {
    request: {
      query: CREATE_PITCH_REEL_COMMENT,
      variables: { reelId: "aqua-chain", body: COMMENT.body },
    },
    result: { data: { createPitchReelComment: { comment: COMMENT } } },
  },
  {
    maxUsageCount: 5,
    request: { query: GET_PITCH_REEL_COMMENTS, variables: { reelId: "aqua-chain", limit: 120 } },
    result: { data: { pitchReelComments: [COMMENT] } },
  },
];

/** Fresh mocks per render — MockedProvider consumes each mock once. */
const buildDefaultFeedMocks = () => [
  ...buildSocialMocks(),
  {
    maxUsageCount: 20,
    request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
    result: {
      data: {
        pitchReelsFeed: [
          buildReel(),
          buildReel({
            reelId: "dorm-grader",
            slug: "dorm-grader",
            ideaId: "22222222-2222-2222-2222-222222222222",
            title: "DormGrader",
            subtitle: "Housing clarity",
            thesis: "See the dorm before you sign.",
            tags: ["Housing"],
          }),
        ],
      },
    },
  },
];

const renderShorts = () =>
  render(
    <MockedProvider
      mocks={buildDefaultFeedMocks()}
      addTypename={false}
      defaultOptions={{
        watchQuery: { fetchPolicy: "no-cache" },
      }}
    >
      <PitchReelsPage />
    </MockedProvider>,
  );

const renderShortsWithMocks = (mocks: any[]) =>
  render(
    <MockedProvider
      mocks={mocks}
      addTypename={false}
      defaultOptions={{
        watchQuery: { fetchPolicy: "no-cache" },
      }}
    >
      <PitchReelsPage />
    </MockedProvider>,
  );

const mockNavigate = jest.fn();
const linkedOpenMedia = {
  loading: false,
  enabled: true,
  ready: true,
  status: {
    enabled: true,
    linked: true,
    needsReconnect: false,
    handle: "viewer",
    displayName: "Viewer",
    connectUrl: "/api/integrations/open-media/connect",
  },
  connectUrl: "/api/integrations/open-media/connect",
};
let mockOpenMedia = linkedOpenMedia;
jest.mock("features/open-media/useOpenMediaLink", () => ({
  useOpenMediaLink: () => mockOpenMedia,
}));
const mockPlay = jest.fn().mockResolvedValue(undefined);
const mockPause = jest.fn();
const mockLoad = jest.fn();
const mockWriteText = jest.fn().mockResolvedValue(undefined);

class MockIntersectionObserver {
  observe = jest.fn();
  unobserve = jest.fn();
  disconnect = jest.fn();

  constructor(public callback: IntersectionObserverCallback) {}
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

Object.defineProperty(global, "IntersectionObserver", {
  writable: true,
  value: MockIntersectionObserver,
});

Object.defineProperty(HTMLVideoElement.prototype, "play", {
  writable: true,
  value: mockPlay,
});

Object.defineProperty(HTMLVideoElement.prototype, "pause", {
  writable: true,
  value: mockPause,
});

Object.defineProperty(HTMLVideoElement.prototype, "load", {
  writable: true,
  value: mockLoad,
});

Object.defineProperty(navigator, "clipboard", {
  writable: true,
  value: {
    writeText: mockWriteText,
  },
});

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

describe("PitchReelsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockOpenMedia = linkedOpenMedia;
    userVar({
      isLoggedIn: true,
      userData: { userId: "viewer-investor-1", email: "inv@example.com" },
    });
    Object.defineProperty(navigator, "share", {
      writable: true,
      value: undefined,
      configurable: true,
    });
  });

  it("keeps loading honest without showing sample reels", async () => {
    renderShortsWithMocks([
      {
        delay: 50,
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: { data: { pitchReelsFeed: [] } },
      },
    ]);
    expect(screen.getByRole("status")).toHaveTextContent("Loading pitch reels");
    expect(
      screen.queryByTestId("short-clip-aqua-chain"),
    ).not.toBeInTheDocument();
    expect(await screen.findByText("No pitch reels yet")).toBeInTheDocument();
  });

  it("shows a retry state rather than sample reels when the feed fails", async () => {
    renderShortsWithMocks([
      {
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        error: new Error("Feed unavailable"),
      },
    ]);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't load pitch reels",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("AquaChain")).not.toBeInTheDocument();
  });

  it("shows cached reels immediately while fetching the current feed", async () => {
    const cache = new InMemoryCache();
    cache.writeQuery({
      query: GET_PITCH_REELS_FEED,
      variables: { limit: 12 },
      data: {
        pitchReelsFeed: [buildReel({ title: "Previously loaded pitch" })],
      },
    });
    render(
      <MockedProvider
        cache={cache}
        mocks={[
          {
            delay: 50,
            request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
            result: {
              data: { pitchReelsFeed: [buildReel({ title: "Updated pitch" })] },
            },
          },
        ]}
      >
        <PitchReelsPage />
      </MockedProvider>,
    );
    expect(screen.getByText("Previously loaded pitch")).toBeInTheDocument();
    expect(screen.queryByText("Loading pitch reels…")).not.toBeInTheDocument();
    expect(await screen.findByText("Updated pitch")).toBeInTheDocument();
  });

  it("keeps the pitch readable if its video cannot be played", async () => {
    renderShorts();
    const video = await screen.findByTestId("short-video-aqua-chain");
    fireEvent.error(video);
    expect(screen.getByText("No video available yet")).toBeInTheDocument();
    expect(screen.getByText("AquaChain")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Open workspace for AquaChain" }),
    ).toBeInTheDocument();
  });

  it("renders the simple reels page", async () => {
    renderShorts();

    expect(screen.getByTestId("shorts-page")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("AquaChain")).toBeInTheDocument();
    });
    expect(screen.getByText("DormGrader")).toBeInTheDocument();
  });

  it("shows a quiet empty video state without downloading a placeholder", async () => {
    const mocks = [
      {
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: {
          data: {
            pitchReelsFeed: [
              buildReel({ videoUrl: "", videoStatus: "failed" }),
            ],
          },
        },
      },
    ];
    const { container } = renderShortsWithMocks(mocks);
    expect(
      await screen.findByText("No video available yet"),
    ).toBeInTheDocument();
    expect(screen.getByText("AquaChain")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
  });

  it("dedupes repeated hero copy and shows one inline failed-video notice", async () => {
    const repeatedCopyMocks = [
      {
        maxUsageCount: 20,
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: {
          data: {
            pitchReelsFeed: [
              buildReel(),
              buildReel({
                reelId: "dorm-grader",
                slug: "dorm-grader",
                title: "DormGrader",
                subtitle:
                  "<p>DormGrader helps rate the student housing for students</p>",
                thesis:
                  "<p>DormGrader helps rate the student housing for students</p>",
                videoStatus: "failed",
                videoUrl: "",
              }),
            ],
          },
        },
      },
    ];

    renderShortsWithMocks(repeatedCopyMocks);

    const dormSection = await waitFor(() =>
      screen.getByTestId("short-clip-dorm-grader"),
    );

    expect(
      within(dormSection).getAllByText(
        "DormGrader helps rate the student housing for students",
      ),
    ).toHaveLength(1);
    expect(
      within(dormSection).getAllByText("No video available yet"),
    ).toHaveLength(1);
  });

  it("toggles like state and updates the action label", async () => {
    renderShorts();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Like AquaChain/i }),
      ).toBeInTheDocument();
    });

    const likeButton = screen.getByRole("button", { name: /Like AquaChain/i });
    fireEvent.click(likeButton);

    expect(
      screen.getByRole("button", { name: /Unlike AquaChain/i }),
    ).toBeInTheDocument();
  });

  it("opens the comments drawer and posts a comment", async () => {
    renderShorts();

    const commentButton = await screen.findByRole("button", {
      name: /Comment on AquaChain/i,
    });

    fireEvent.click(commentButton);
    expect(
      await screen.findByRole("dialog", { name: "Comments" }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Comment" }), {
      target: { value: "This feels strong on compliance and audit trail." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Post" }));

    expect(
      await screen.findByText(
        "This feels strong on compliance and audit trail.",
        {},
        { timeout: 10000 },
      ),
    ).toBeInTheDocument();
  });

  it("opens invest modal from the rail", async () => {
    renderShorts();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Invest in AquaChain/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Invest in AquaChain/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("dialog", { name: "Invest in Idea" }),
      ).toBeInTheDocument();
    });
  });

  it("hides invest on own reel", async () => {
    userVar({
      isLoggedIn: true,
      userData: { userId: "creator-manifest-lab", email: "me@example.com" },
    });

    const ownFeedMocks = () => [
      {
        maxUsageCount: 20,
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: {
          data: {
            pitchReelsFeed: [
              buildReel({ reelId: "only-own", slug: "only-own" }),
            ],
          },
        },
      },
    ];

    render(
      <MockedProvider
        mocks={ownFeedMocks()}
        addTypename={false}
        defaultOptions={{
          watchQuery: { fetchPolicy: "no-cache" },
        }}
      >
        <PitchReelsPage />
      </MockedProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("AquaChain")).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /Invest in AquaChain/i }),
    ).not.toBeInTheDocument();
  });

  it("hides invest when ideaId is missing", async () => {
    const noIdeaMocks = () => [
      {
        maxUsageCount: 20,
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: {
          data: {
            pitchReelsFeed: [
              buildReel({ ideaId: null, reelId: "legacy", slug: "legacy" }),
            ],
          },
        },
      },
    ];

    render(
      <MockedProvider
        mocks={noIdeaMocks()}
        addTypename={false}
        defaultOptions={{
          watchQuery: { fetchPolicy: "no-cache" },
        }}
      >
        <PitchReelsPage />
      </MockedProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("AquaChain")).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /Invest in AquaChain/i }),
    ).not.toBeInTheDocument();
  });

  it("only downloads the active reel video", async () => {
    const manyReelsMocks = [
      {
        maxUsageCount: 20,
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: {
          data: {
            pitchReelsFeed: Array.from({ length: 5 }, (_, index) =>
              buildReel({
                reelId: `reel-${index + 1}`,
                slug: `reel-${index + 1}`,
                title: `Reel ${index + 1}`,
                ideaId: `${index + 1}`.padStart(32, "1"),
              }),
            ),
          },
        },
      },
    ];

    const { container } = renderShortsWithMocks(manyReelsMocks);

    await waitFor(() => {
      expect(screen.getByText("Reel 1")).toBeInTheDocument();
      expect(screen.getByText("Reel 5")).toBeInTheDocument();
    });

    expect(container.querySelectorAll("video[src]")).toHaveLength(1);
  });

  it("copies a share link when the native share sheet is unavailable", async () => {
    renderShorts();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Share AquaChain/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Share AquaChain/i }));

    await waitFor(() => {
      // #25: canonical share URL is /pitch-reels (was /shorts).
      expect(mockWriteText).toHaveBeenCalledWith(
        expect.stringContaining("/pitch-reels?clip=aqua-chain"),
      );
    });
  });

  it("opens the workspace from the primary action", async () => {
    renderShorts();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Open workspace for AquaChain/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Open workspace for AquaChain/i }),
    );

    expect(mockNavigate).toHaveBeenCalledWith("/ideas");
  });

  it("toggles follow state", async () => {
    renderShorts();

    const aquaSection = await waitFor(() =>
      screen.getByTestId("short-clip-aqua-chain"),
    );

    const followBtn = within(aquaSection).getByRole("button", {
      name: /Follow Manifest Lab/i,
    });
    fireEvent.click(followBtn);

    expect(
      within(aquaSection).getByRole("button", {
        name: /Unfollow Manifest Lab/i,
      }),
    ).toBeInTheDocument();
    expect(within(aquaSection).getByText("Following")).toBeInTheDocument();
  });

  it("toggles the mute button label", async () => {
    renderShorts();

    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /Enable sound/i })[0],
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /Enable sound/i })[0],
    );

    expect(
      screen.getAllByRole("button", { name: /Mute sound/i }).length,
    ).toBeGreaterThan(0);
  });

  it("reposts a reel to Open Media", async () => {
    renderShorts();

    const repost = await screen.findByRole("button", { name: /^Repost AquaChain/i });
    fireEvent.click(repost);

    expect(
      await screen.findByRole("button", { name: /Undo repost of AquaChain/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Reposted to Open Media.")).toBeInTheDocument();
  });

  it("has no save action (Open Media has no saves)", async () => {
    renderShorts();
    await screen.findByTestId("short-clip-aqua-chain");
    expect(screen.queryByRole("button", { name: /Save AquaChain/i })).not.toBeInTheDocument();
  });

  it("asks unlinked viewers to connect Open Media before liking", async () => {
    mockOpenMedia = {
      ...linkedOpenMedia,
      ready: false,
      status: { ...linkedOpenMedia.status, linked: false, handle: null as unknown as string },
    };
    renderShorts();

    const likeButton = await screen.findByRole("button", { name: /Like AquaChain/i });
    expect(screen.getByTestId("shorts-connect-banner")).toBeInTheDocument();
    fireEvent.click(likeButton);

    expect(await screen.findByText(/Connect Open Media in Account settings/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Like AquaChain/i })).toBeInTheDocument();
  });

  it("explains when Pitch Shorts are not available on this server", () => {
    mockOpenMedia = { ...linkedOpenMedia, enabled: false, ready: false };
    renderShortsWithMocks([]);
    expect(screen.getByTestId("shorts-unavailable")).toBeInTheDocument();
  });

  it("tells viewers a reel is waiting for its founder to connect", async () => {
    renderShortsWithMocks([
      {
        request: { query: GET_PITCH_REELS_FEED, variables: { limit: 12 } },
        result: {
          data: {
            pitchReelsFeed: [buildReel({ videoUrl: "", videoStatus: "needs_open_media" })],
          },
        },
      },
    ]);
    expect(
      await screen.findByText("Waiting for the founder to connect Open Media"),
    ).toBeInTheDocument();
  });

  it("supports keyboard navigation between clips", async () => {
    renderShorts();

    await waitFor(() => {
      expect(screen.getByTestId("short-clip-dorm-grader")).toBeInTheDocument();
    });

    const secondClip = screen.getByTestId("short-clip-dorm-grader");
    const scrollTo = jest.fn();
    secondClip.parentElement!.scrollTo = scrollTo;

    fireEvent.keyDown(window, { key: "ArrowDown" });

    expect(scrollTo).toHaveBeenCalled();
  });
});
