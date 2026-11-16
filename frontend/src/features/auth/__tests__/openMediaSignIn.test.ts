import { openMediaSignInUrl, signInErrorMessage } from "features/auth/openMediaSignIn";
import { performLogout } from "features/auth/logout";
import { userVar } from "features/core/apollo/localState";

describe("openMediaSignInUrl", () => {
  it("adds a same-origin next path", () => {
    expect(openMediaSignInUrl("/ideas/7?x=1")).toBe("/api/auth/open-media/start?next=%2Fideas%2F7%3Fx%3D1");
  });

  it.each([undefined, "", "https://evil.example", "//evil.example", "ideas"])("drops an unsafe next (%s)", (next) => {
    expect(openMediaSignInUrl(next)).toBe("/api/auth/open-media/start");
  });
});

describe("signInErrorMessage", () => {
  it("maps known codes and falls back for unknown ones", () => {
    expect(signInErrorMessage(null)).toBeNull();
    expect(signInErrorMessage("unverified_email")).toMatch(/Confirm your email/);
    expect(signInErrorMessage("nope")).toMatch(/didn't finish/);
  });
});

describe("performLogout", () => {
  it("posts to the backend logout route and clears local state", async () => {
    const fetchMock = jest.fn().mockResolvedValue({ ok: true });
    (global as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    localStorage.setItem("access_token", "t");
    userVar({ isLoggedIn: true, authChecked: true, isGuest: false, userData: { userId: "u1", email: "a@b.c" } });

    await performLogout();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/logout",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(userVar().isLoggedIn).toBe(false);
  });
});
