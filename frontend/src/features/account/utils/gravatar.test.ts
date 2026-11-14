import { getAvatarUrl, getGravatarUrl, normalizeGravatarInput } from "./gravatar";

describe("gravatar utils", () => {
  it("returns the default mystery-person avatar when no gravatar is provided", () => {
    expect(getGravatarUrl("", 64)).toBe("https://www.gravatar.com/avatar/?d=mp&s=64");
  });

  it("extracts a gravatar hash from a pasted gravatar URL", () => {
    expect(
      normalizeGravatarInput("https://www.gravatar.com/avatar/abc123def456?s=120&d=mp")
    ).toBe("abc123def456");
  });

  it("prefers a persisted hosted profile image URL", () => {
    expect(
      getAvatarUrl({
        profilePictureUrl: "https://cdn.example.com/avatar.png",
        gravatarHash: "abc123",
        size: 64,
      })
    ).toBe("https://cdn.example.com/avatar.png");
  });

  it("falls back to gravatar when the stored profile image URL is a stale blob URL", () => {
    expect(
      getAvatarUrl({
        profilePictureUrl: "blob:http://localhost:3000/demo",
        gravatarHash: "abc123",
        size: 64,
      })
    ).toBe("https://www.gravatar.com/avatar/abc123?d=mp&s=64");
  });

  it("resolves backend-relative profile picture URLs against the API origin", () => {
    const originalGraphqlUrl = process.env.REACT_APP_GRAPHQL_URL;
    process.env.REACT_APP_GRAPHQL_URL = "https://api.manifeststartup.com/graphql";

    expect(
      getAvatarUrl({
        profilePictureUrl: "/generated/pdfs/profile-pictures/user/avatar.png",
        gravatarHash: "abc123",
        size: 64,
      })
    ).toBe("https://api.manifeststartup.com/generated/pdfs/profile-pictures/user/avatar.png");

    process.env.REACT_APP_GRAPHQL_URL = originalGraphqlUrl;
  });
});
