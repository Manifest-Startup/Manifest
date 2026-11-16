import { mapPitchReelToShortClip, type PitchReelFeedRow } from "../mapPitchReelToShortClip";

const baseRow = (): PitchReelFeedRow => ({
  reelId: "r1",
  slug: "s1",
  title: "T",
  tags: [],
  videoUrl: "https://v",
  workspacePath: "/ideas",
  accentFrom: "#000",
  accentTo: "#111",
  createdAt: "2025-01-01T00:00:00Z",
  creator: {
    userId: "u1",
    name: "N",
    initials: "N",
  },
  stats: { likeCount: 1, commentCount: 0, shareCount: 0 },
});

describe("mapPitchReelToShortClip", () => {
  it("maps ideaId when present", () => {
    const ideaId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    const clip = mapPitchReelToShortClip({ ...baseRow(), ideaId });
    expect(clip.ideaId).toBe(ideaId);
  });

  it("omits ideaId when blank or null", () => {
    expect(mapPitchReelToShortClip({ ...baseRow(), ideaId: null }).ideaId).toBeUndefined();
    expect(mapPitchReelToShortClip({ ...baseRow(), ideaId: "" }).ideaId).toBeUndefined();
    expect(mapPitchReelToShortClip({ ...baseRow(), ideaId: "   " }).ideaId).toBeUndefined();
  });

  it("defaults stats when missing", () => {
    const row = { ...baseRow(), stats: undefined };
    const clip = mapPitchReelToShortClip(row);
    expect(clip.likeCount).toBe(0);
    expect(clip.commentCount).toBe(0);
  });

  it("maps Open Media viewer state and the needs_open_media status", () => {
    const clip = mapPitchReelToShortClip({
      ...baseRow(),
      videoStatus: "needs_open_media",
      posterUrl: "https://poster",
      viewerState: { liked: true, reshared: false },
      creator: { userId: "u1", name: "N", initials: "N", isFollowing: true },
    });
    expect(clip.videoStatus).toBe("needs_open_media");
    expect(clip.liked).toBe(true);
    expect(clip.reshared).toBe(false);
    expect(clip.creatorFollowing).toBe(true);
    expect(clip.posterUrl).toBe("https://poster");
  });
});
