import React from "react";
import { act, render } from "@testing-library/react";
import { ThemeProvider, useTheme } from "../ThemeContext";

const metas = () =>
  [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => [
    (m as HTMLMetaElement).content,
    m.getAttribute("media") ?? "",
  ]);

let setTheme: (t: "light" | "dark" | "system") => void = () => undefined;
const Grab = () => {
  setTheme = useTheme().setTheme;
  return null;
};

describe("the installed app's title bar", () => {
  beforeEach(() => {
    localStorage.clear();
    document.head.innerHTML =
      '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">' +
      '<meta name="theme-color" content="#161617" media="(prefers-color-scheme: dark)">';
    window.matchMedia = jest.fn().mockReturnValue({ matches: false, addEventListener: jest.fn(), removeEventListener: jest.fn() });
  });

  it("takes the page background and follows the in-app theme", () => {
    render(
      <ThemeProvider>
        <Grab />
      </ThemeProvider>,
    );
    expect(metas()).toEqual([["#ffffff", ""]]);
    act(() => setTheme("dark"));
    expect(metas()).toEqual([["#161617", ""]]);
  });
});
