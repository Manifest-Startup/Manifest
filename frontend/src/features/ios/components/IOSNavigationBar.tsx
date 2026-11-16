import React, { useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useMessage } from "features/notifications/context/MessageContext";
import { useQuery } from '@apollo/client/react';
import { GET_UNREAD_MESSAGE_COUNT } from 'features/core/apollo/queries';
import { useOpenMediaLink } from 'features/open-media/useOpenMediaLink';
import { useReactiveVar } from "@apollo/client/react";
import { userVar, accountVar } from "features/core/apollo/localState";
import { getAvatarUrl } from "features/account/utils/gravatar";
import { performLogout } from "features/auth/logout";
import { createLogger } from "features/core/logError";
import { safeNavigate } from 'utils/safeNavigate';

const logger = createLogger("IOSNavigationBar");

/**
 * iOS-styled navigation bar with native iOS design patterns
 */
const IOSNavigationBar: React.FC = () => {
  logger.log('rendered');
  const navigate = useNavigate();
  const location = useLocation();
  const { setMessage, clearMessage } = useMessage();
  const [showMenu, setShowMenu] = useState(false);
  const { isLoggedIn } = useReactiveVar(userVar);
  const { accountData } = useReactiveVar(accountVar);
  const openMedia = useOpenMediaLink();
  const { data: unreadData } = useQuery(GET_UNREAD_MESSAGE_COUNT, {
    skip: !isLoggedIn || !openMedia.ready,
    pollInterval: 120000,
    fetchPolicy: 'cache-first',
    nextFetchPolicy: 'cache-first',
  });
  const unreadTotal = unreadData?.unreadMessageCount?.count ?? 0;

  const handleLogout = useCallback(async () => {
    logger.log('handleLogout called');
    try {
      await performLogout();
      clearMessage();
      setShowMenu(false);
      navigate("/login", { replace: true });
    } catch (error) {
      logger.error("Logout failed:", error);
      setMessage("Logout failed. Please try again.", "error");
    }
  }, [clearMessage, navigate, setMessage]);

  const handleLogoClick = useCallback(() => {
    safeNavigate(navigate, setMessage, isLoggedIn ? "/ideas" : "/");
  }, [isLoggedIn, navigate, setMessage]);

  const isActive = (path: string) => location.pathname === path;

  return (
    <nav className="ios-nav-bar bg-white/95 dark:bg-neutral800/95 backdrop-blur-xl border-b border-gray-200/50 dark:border-neutral700/50 safe-area-top transition-colors">
      <div className="mx-auto flex h-14 max-w-screen-sm items-center justify-between ps-[max(1rem,env(safe-area-inset-left,0px))] pe-[max(1rem,env(safe-area-inset-right,0px))]">
        <div
          className="text-xl font-semibold text-gray-900 dark:text-white cursor-pointer"
          onClick={handleLogoClick}
        >
          Manifest
        </div>

        <div className="relative flex items-center gap-3">
          {isLoggedIn ? (
            <>
              <button
                onClick={() => setShowMenu(!showMenu)}
                className="w-8 h-8 rounded-full overflow-hidden border border-gray-200 dark:border-neutral600 active:scale-95 transition-transform"
              >
                <img
                  src={getAvatarUrl({
                    profilePictureUrl: accountData?.account?.profilePictureUrl || accountData?.profilePictureUrl,
                    gravatarHash: accountData?.account?.gravatarHash || accountData?.gravatarHash,
                    size: 32,
                  })}
                  alt="Profile"
                  className="w-full h-full object-cover"
                />
              </button>

              {showMenu && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setShowMenu(false)}
                  />
                  <div className="absolute end-[max(1rem,env(safe-area-inset-right,0px))] top-full z-50 mt-2 w-[min(14rem,calc(100vw-2rem))] rounded-2xl border border-gray-100 bg-white py-2 shadow-xl animate-scale-in transition-colors dark:border-neutral700 dark:bg-neutral800">
                    {openMedia.enabled ? (
                      <button
                        type="button"
                        onClick={() => {
                          safeNavigate(navigate, setMessage, "/messages");
                          setShowMenu(false);
                        }}
                        className="w-full px-4 py-3 text-left text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-neutral700 active:bg-gray-100 dark:active:bg-neutral600 transition-colors flex items-center justify-between gap-2"
                      >
                        <span>Messages</span>
                        {unreadTotal > 0 ? (
                          <span className="flex h-6 min-w-[1.5rem] items-center justify-center rounded-full bg-neutral900 px-2 text-xs font-bold text-white dark:bg-white dark:text-neutral900">
                            {unreadTotal > 9 ? '9+' : unreadTotal}
                          </span>
                        ) : null}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => {
                        safeNavigate(navigate, setMessage, "/account");
                        setShowMenu(false);
                      }}
                      className="w-full px-4 py-3 text-left text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-neutral700 active:bg-gray-100 dark:active:bg-neutral600 transition-colors"
                    >
                      Account
                    </button>
                    <div className="border-t border-gray-100 dark:border-neutral700 my-1" />
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="w-full px-4 py-3 text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 active:bg-red-100 dark:active:bg-red-900/30 transition-colors"
                    >
                      Logout
                    </button>
                  </div>
                </>
              )}
            </>
          ) : (
            <button
              onClick={() => safeNavigate(navigate, setMessage, "/login")}
              className="px-4 py-2 text-sm font-medium text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300 active:opacity-70 transition-opacity"
            >
              Sign In
            </button>
          )}
        </div>
      </div>
    </nav>
  );
};

export default IOSNavigationBar;
