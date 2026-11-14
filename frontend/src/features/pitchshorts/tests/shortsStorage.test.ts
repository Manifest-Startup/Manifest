import {
  DEFAULT_SHORTS_STATE,
  loadShortsState,
  persistShortsState,
} from "../shortsStorage";

describe("shortsStorage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns the default state when storage is empty", () => {
    expect(loadShortsState()).toEqual(DEFAULT_SHORTS_STATE);
  });

  it("persists and reloads the shorts state", () => {
    const nextState = {
      muted: false,
      likedClipIds: ["clip-1"],
      savedClipIds: ["clip-1"],
      followedCreatorIds: ["creator-1"],
      commentsByClipId: {
        "clip-1": [
          {
            id: "comment-1",
            clipId: "clip-1",
            author: "You",
            body: "Strong founder angle.",
            createdAt: new Date().toISOString(),
          },
        ],
      },
    };

    persistShortsState(nextState);

    expect(loadShortsState()).toEqual(nextState);
  });

  it("falls back safely when storage is malformed", () => {
    window.localStorage.setItem("manifest.pitch-shorts.state.v1", "{bad-json");

    expect(loadShortsState()).toEqual(DEFAULT_SHORTS_STATE);
  });
});
