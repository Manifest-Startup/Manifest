import { isVaultMode } from "features/vault/mode";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery, useReactiveVar } from "@apollo/client/react";

import { performLogout } from "features/auth/logout";
import { GET_UNREAD_MESSAGE_COUNT } from "features/core/apollo/queries";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";

import Button from "features/common-ui/Button";
import { accountVar, userVar } from "features/core/apollo/localState";
import { useMessage } from "features/notifications/context/MessageContext";
import { getAvatarUrl } from "features/account/utils/gravatar";
import { loadPitchReelsPage } from "features/pitch-reels/loadPitchReelsPage";
import { safeNavigate } from "utils/safeNavigate";
import UniversalSearch from "./UniversalSearch";
import ManifestLogo from "features/common-ui/ManifestLogo";

interface NavItem {
  label: string;
  path: string;
  matchStartsWith?: boolean;
}

interface DropdownItem {
  label: string;
  path?: string;
  action?: () => void;
  /** Unread count badge (e.g. Messages) */
  badgeCount?: number;
}

const NavigationBar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { setMessage, clearMessage } = useMessage();
  const { isLoggedIn, userData } = useReactiveVar(userVar);
  const { accountData } = useReactiveVar(accountVar);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const openMedia = useOpenMediaLink();
  const { data: unreadData } = useQuery(GET_UNREAD_MESSAGE_COUNT, {
    skip: !isLoggedIn || !openMedia.ready,
    pollInterval: 120000,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });
  const unreadTotal = unreadData?.unreadMessageCount?.count ?? 0;

  const navLinks: NavItem[] = useMemo(
    () => [
      { label: "Ideas", path: "/ideas", matchStartsWith: true },
      // #25: canonical URL aligned with the user-visible label ("Pitch Reels").
      // Legacy /shorts redirects to this path so old bookmarks keep working.
      // Hidden when this server runs without Open Media (pitch shorts live there).
      // Pitch Reels live in the account: not shown for a local vault (ADR 0011).
      ...(openMedia.enabled && !isVaultMode()
        ? [{ label: "Pitch Reels", path: "/pitch-reels", matchStartsWith: true }]
        : []),
    ],
    [openMedia.enabled],
  );

  useEffect(() => {
    if (!showDropdown) {
      return;
    }

    const handleOutsideClick = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [showDropdown]);

  const createNavigateHandler = useCallback(
    (path: string) => () => {
      setShowDropdown(false);
      safeNavigate(navigate, setMessage, path);
    },
    [navigate, setMessage]
  );

  const prefetchRoute = useCallback((path: string) => {
    if (path === "/pitch-reels" || path === "/shorts") {
      void loadPitchReelsPage();
    }
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await performLogout();
      clearMessage();
      setShowDropdown(false);
      navigate("/login", { replace: true });
    } catch (error) {
      console.error("Logout failed:", error);
      setMessage("Logout failed. Please try again.", "error");
    }
  }, [clearMessage, navigate, setMessage]);

  const handleLogoClick = useCallback(() => {
    safeNavigate(navigate, setMessage, isLoggedIn ? "/ideas" : "/");
  }, [isLoggedIn, navigate, setMessage]);

  const avatarSrc = getAvatarUrl({
    profilePictureUrl: accountData?.account?.profilePictureUrl || accountData?.profilePictureUrl,
    gravatarHash: accountData?.account?.gravatarHash || accountData?.gravatarHash,
    size: 64,
  });

  // #43: avoid the "Workspace / Workspace" duplicate label by falling back to
  // a name the user can actually recognise (full name → first name → username
  // → email → "Founder"), rather than echoing the eyebrow back at them.
  const accountFullName = [
    accountData?.account?.firstName,
    accountData?.account?.lastName,
  ]
    .filter(Boolean)
    .join(" ")
    .trim();
  const profileName =
    accountFullName ||
    accountData?.account?.firstName ||
    accountData?.firstName ||
    accountData?.account?.username ||
    accountData?.username ||
    accountData?.account?.email ||
    accountData?.email ||
    userData?.email ||
    "Founder";

  const dropdownItems: DropdownItem[] = useMemo(
    () => [
      ...(openMedia.enabled
        ? [{ label: "Messages", path: "/messages", badgeCount: unreadTotal > 0 ? unreadTotal : undefined }]
        : []),
      { label: "Account", path: "/account" },
      { label: "Docs", path: "/docs" },
      { label: "Logout", action: handleLogout },
    ],
    [handleLogout, openMedia.enabled, unreadTotal],
  );

  const isActive = (item: NavItem) =>
    item.matchStartsWith ? location.pathname.startsWith(item.path) : location.pathname === item.path;

  return (
    <header className="manifest-navigation sticky top-0 z-50">
      <nav
        className="manifest-shell flex min-h-14 min-w-0 items-center justify-between gap-3 px-3 py-1.5 sm:px-4"
        role="navigation"
        aria-label="Main Navigation"
      >
        <div
          className="flex min-w-0 cursor-pointer items-center gap-2 sm:gap-3"
          onClick={handleLogoClick}
          role="button"
          aria-label="Navigate to Home"
          tabIndex={0}
        >
          <ManifestLogo size={32} />
          <span className="hidden text-sm font-semibold text-neutral900 dark:text-white sm:block">Manifest</span>
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-1.5 sm:gap-3" role="menubar" aria-label="Navigation Area">
          {isLoggedIn ? (
            <>
              <div className="hidden shrink-0 items-center gap-1 md:flex">
                {navLinks.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={createNavigateHandler(item.path)}
                    onMouseEnter={() => prefetchRoute(item.path)}
                    onFocus={() => prefetchRoute(item.path)}
                    className={`rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                      isActive(item)
                        ? "bg-stone100 text-neutral900 dark:bg-neutral800 dark:text-white"
                        : "text-neutral700 hover:bg-stone50 hover:text-neutral900 dark:text-gray300 dark:hover:bg-neutral800 dark:hover:text-white"
                    }`}
                    role="menuitem"
                    aria-label={`Navigate to ${item.label}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className="flex shrink-0 items-center gap-1 md:hidden" aria-label="Primary navigation">
                {navLinks.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={createNavigateHandler(item.path)}
                    onTouchStart={() => prefetchRoute(item.path)}
                    className={`shrink-0 rounded-md px-2.5 py-2 text-[0.7rem] font-semibold leading-tight transition-all sm:px-3 sm:text-xs ${
                      isActive(item)
                        ? "bg-stone100 text-neutral900 dark:bg-neutral800 dark:text-white"
                        : "text-neutral700 hover:bg-stone50 hover:text-neutral900 dark:text-gray300 dark:hover:bg-neutral800 dark:hover:text-white"
                    }`}
                    role="menuitem"
                  >
                    {item.label === "Pitch Reels" ? "Reels" : item.label}
                  </button>
                ))}
              </div>

              <div className="min-w-0 flex-1 md:max-w-none">
                <UniversalSearch />
              </div>

              <div
                ref={dropdownRef}
                className="relative shrink-0"
                role="region"
                aria-label="Profile Section"
              >
                <button
                  type="button"
                  onClick={() => setShowDropdown((value) => !value)}
                  className="flex h-11 items-center gap-2 rounded-md px-2 hover:bg-stone50 dark:hover:bg-neutral800"
                  aria-label="Toggle Profile Dropdown Menu"
                >
                  <img
                    src={avatarSrc}
                    alt="User Profile Icon"
                    className="h-9 w-9 rounded-full object-cover"
                  />
                  <div className="hidden text-left lg:block">
                    <p className="text-[0.68rem] font-medium text-gray500 dark:text-gray400">
                      Workspace
                    </p>
                    <p className="max-w-[10rem] truncate text-sm font-semibold text-neutral900 dark:text-white">
                      {profileName}
                    </p>
                  </div>
                  <svg className="hidden h-4 w-4 text-gray500 lg:block dark:text-gray400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m6 9 6 6 6-6" />
                  </svg>
                </button>

                {showDropdown ? (
                  <div
                    className="absolute right-0 z-[60] mt-3 w-[min(16rem,calc(100vw-1.5rem))] max-w-[calc(100vw-1.5rem)] rounded-xl border border-stone200 bg-white/95 p-3 shadow-panel backdrop-blur-xl dark:border-neutral700 dark:bg-neutral900/95"
                    role="menu"
                    aria-label="Dropdown Menu"
                  >
                    <div className="rounded-lg border border-stone200 bg-stone50 px-4 py-3 dark:border-neutral700 dark:bg-neutral800">
                      <p className="text-[0.68rem] font-medium text-gray500 dark:text-gray400">
                        Signed in
                      </p>
                      <p className="mt-1 truncate text-sm font-semibold text-neutral900 dark:text-white">
                        {/* #43: prefer the logged-in user's email; fall back to
                            the Apollo account doc; fall back to a generic
                            label only if neither is loaded. */}
                        {userData?.email ||
                          accountData?.account?.email ||
                          accountData?.email ||
                          "Manifest account"}
                      </p>
                    </div>
                    <div className="mt-2 space-y-1">
                      {dropdownItems.map((item) => (
                        <Button
                          key={item.label}
                          onClick={item.action ?? (item.path ? createNavigateHandler(item.path) : undefined)}
                          variant="dropdown"
                          role="menuitem"
                          aria-label={item.label === "Logout" ? "Logout" : `Go to ${item.label}`}
                          className="flex w-full items-center justify-between gap-3"
                        >
                          <span>{item.label}</span>
                          {item.badgeCount ? (
                            <span className="flex h-6 min-w-[1.5rem] shrink-0 items-center justify-center rounded-full bg-neutral900 px-2 text-xs font-bold text-white dark:bg-white dark:text-neutral900">
                              {item.badgeCount > 9 ? "9+" : item.badgeCount}
                            </span>
                          ) : null}
                        </Button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <>
              <div className="hidden flex-1 text-sm text-theme-secondary sm:block">
                Research. Model. Launch.
              </div>
              <Button
                onClick={createNavigateHandler("/login")}
                variant="primary"
                role="menuitem"
                aria-label="Sign In"
                className="ml-auto px-5 py-2.5"
              >
                Sign In
              </Button>
            </>
          )}
        </div>
      </nav>
    </header>
  );
};

export default NavigationBar;
