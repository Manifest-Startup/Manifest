import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import AppFooter from "../AppFooter";

describe("AppFooter (regression #22)", () => {
  const renderFooter = () =>
    render(
      <MemoryRouter>
        <AppFooter />
      </MemoryRouter>,
    );

  it("renders the copyright with the current year", () => {
    renderFooter();
    const year = new Date().getFullYear();
    expect(screen.getByText(`© ${year} Manifest Startup`)).toBeInTheDocument();
  });

  it("links to Terms of Service, Privacy Policy and Docs", () => {
    renderFooter();
    expect(screen.getByRole("link", { name: /terms of service/i })).toHaveAttribute("href", "/legal/terms");
    expect(screen.getByRole("link", { name: /privacy policy/i })).toHaveAttribute("href", "/legal/privacy");
    expect(screen.getByRole("link", { name: /docs/i })).toHaveAttribute("href", "/docs");
  });

  it("keeps the AGPL attribution line and a source code link", () => {
    renderFooter();
    expect(screen.getByTestId("app-footer-attribution")).toHaveTextContent(
      "Based on Manifest by Mihir Kavishwar · AGPL-3.0",
    );
    expect(screen.getByRole("link", { name: "Manifest" })).toHaveAttribute(
      "href",
      "https://github.com/Manifest-Startup/Manifest",
    );
    expect(screen.getByRole("link", { name: /source code/i })).toHaveAttribute(
      "href",
      "https://github.com/Manifest-Startup/Manifest",
    );
  });

  it("provides a contact email affordance", () => {
    renderFooter();
    expect(screen.getByRole("link", { name: /contact/i })).toHaveAttribute(
      "href",
      "mailto:hello@manifeststartup.com",
    );
  });

  it("hides the version chip when REACT_APP_VERSION is unset", () => {
    const previous = process.env.REACT_APP_VERSION;
    delete process.env.REACT_APP_VERSION;
    try {
      renderFooter();
      expect(screen.queryByTestId("app-footer-version")).not.toBeInTheDocument();
    } finally {
      if (previous !== undefined) {
        process.env.REACT_APP_VERSION = previous;
      }
    }
  });

  it("renders the version chip when REACT_APP_VERSION is set", () => {
    const previous = process.env.REACT_APP_VERSION;
    process.env.REACT_APP_VERSION = "1.2.3";
    try {
      renderFooter();
      const chip = screen.getByTestId("app-footer-version");
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveTextContent("v1.2.3");
    } finally {
      if (previous === undefined) {
        delete process.env.REACT_APP_VERSION;
      } else {
        process.env.REACT_APP_VERSION = previous;
      }
    }
  });

  it("uses contentinfo landmark for accessibility", () => {
    renderFooter();
    const footer = screen.getByTestId("app-footer");
    expect(footer.tagName).toBe("FOOTER");
    expect(footer).toHaveAttribute("role", "contentinfo");
  });
});
