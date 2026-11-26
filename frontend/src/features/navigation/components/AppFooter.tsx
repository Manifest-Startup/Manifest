import React from "react";
import { Link } from "react-router-dom";

/**
 * Minimal global footer rendered on non-immersive routes (i.e. routes that
 * also show the NavigationBar). Provides:
 *   - copyright line
 *   - Terms of Service / Privacy Policy links
 *   - Contact / Help affordance
 *   - Version, when injected at build time via REACT_APP_VERSION
 *   - Source code link and attribution, which the AGPL-3.0 section 7(b)
 *     term in NOTICE asks every deployment (including forks) to keep
 *
 * Addresses regression #22 — authenticated pages had no footer with legal,
 * contact, or version info.
 */
const AppFooter: React.FC = () => {
  const year = new Date().getFullYear();
  const version =
    (typeof process !== "undefined" && process.env && process.env.REACT_APP_VERSION) || null;

  return (
    <footer
      className="shrink-0 border-t border-stone200/80 bg-white/70 px-4 py-3 text-xs text-gray500 backdrop-blur-sm dark:border-neutral700 dark:bg-neutral900/60 dark:text-gray400 sm:px-5"
      data-testid="app-footer"
      role="contentinfo"
    >
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>© {year} Manifest Startup</span>
          <span data-testid="app-footer-attribution">
            Based on{" "}
            <a
              href="https://github.com/Manifest-Startup/Manifest"
              className="underline-offset-2 hover:text-neutral900 hover:underline dark:hover:text-white"
            >
              Manifest
            </a>{" "}
            by Mihir Kavishwar · AGPL-3.0
          </span>
          {version ? (
            <span className="text-gray400 dark:text-gray500" data-testid="app-footer-version">
              v{version}
            </span>
          ) : null}
        </div>
        <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <Link
            to="/legal/terms"
            className="hover:text-neutral900 dark:hover:text-white"
          >
            Terms of Service
          </Link>
          <Link
            to="/legal/privacy"
            className="hover:text-neutral900 dark:hover:text-white"
          >
            Privacy Policy
          </Link>
          <Link
            to="/docs"
            className="hover:text-neutral900 dark:hover:text-white"
          >
            Docs
          </Link>
          <a
            href="https://github.com/Manifest-Startup/Manifest"
            className="hover:text-neutral900 dark:hover:text-white"
          >
            Source code
          </a>
          <a
            href="mailto:hello@manifeststartup.com"
            className="hover:text-neutral900 dark:hover:text-white"
          >
            Contact
          </a>
        </nav>
      </div>
    </footer>
  );
};

export default AppFooter;
