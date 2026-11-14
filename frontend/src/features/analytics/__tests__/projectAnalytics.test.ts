import { trackEvent } from "../projectAnalytics";

describe("trackEvent", () => {
  afterEach(() => {
    delete window.umami;
    jest.restoreAllMocks();
  });

  it("forwards event names and data to the injected tracker", () => {
    const track = jest.fn();
    window.umami = { track };

    trackEvent("idea_created", { creation_surface: "new_button" });

    expect(track).toHaveBeenCalledWith("idea_created", {
      creation_surface: "new_button",
    });
  });

  it("is a safe no-op before the tracker is available", () => {
    expect(() => trackEvent("landing_cta_clicked")).not.toThrow();
  });

  it("does not allow tracker failures to interrupt the app", () => {
    window.umami = {
      track: jest.fn(() => {
        throw new Error("tracker unavailable");
      }),
    };

    expect(() => trackEvent("auth_completed", { mode: "login" })).not.toThrow();
  });
});