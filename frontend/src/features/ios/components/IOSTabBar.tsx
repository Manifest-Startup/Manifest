import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useReactiveVar } from "@apollo/client/react";
import { userVar } from "features/core/apollo/localState";
import { safeNavigate } from 'utils/safeNavigate';
import { useMessage } from "features/notifications/context/MessageContext";
import { loadPitchShortsPage } from "features/pitchshorts/loadPitchShortsPage";

interface TabItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  activeIcon: React.ReactNode;
}

const IdeasIcon = ({ active }: { active: boolean }) => (
  <svg className="w-6 h-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
  </svg>
);

const ShortsIcon = ({ active }: { active: boolean }) => (
  <svg className="w-6 h-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7.25 5.25h9.5A2.25 2.25 0 0 1 19 7.5v9a2.25 2.25 0 0 1-2.25 2.25h-9.5A2.25 2.25 0 0 1 5 16.5v-9a2.25 2.25 0 0 1 2.25-2.25Z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="m10 9 5 3-5 3V9Z" />
  </svg>
);

const AccountIcon = ({ active }: { active: boolean }) => (
  <svg className="w-6 h-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
  </svg>
);

const IOSTabBar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isLoggedIn } = useReactiveVar(userVar);
  const { setMessage } = useMessage();

  if (!isLoggedIn) return null;

  const tabs: TabItem[] = [
    {
      label: "Ideas",
      path: "/ideas",
      icon: <IdeasIcon active={false} />,
      activeIcon: <IdeasIcon active={true} />,
    },
    {
      label: "Pitch Reels",
      // #25: canonical path matches the user-visible label.
      path: "/pitch-reels",
      icon: <ShortsIcon active={false} />,
      activeIcon: <ShortsIcon active={true} />,
    },
    {
      label: "Account",
      path: "/account",
      icon: <AccountIcon active={false} />,
      activeIcon: <AccountIcon active={true} />,
    },
  ];

  const isActive = (path: string) => {
    if (path === "/ideas") {
      return location.pathname.startsWith("/ideas");
    }
    if (path === "/pitch-reels") {
      return (
        location.pathname === "/pitch-reels" ||
        location.pathname === "/shorts" ||
        location.pathname === "/discover" ||
        location.pathname === "/pitch-shorts"
      );
    }
    return location.pathname === path;
  };

  const handleTabClick = (path: string) => {
    safeNavigate(navigate, setMessage, path);
  };

  const prefetchTab = (path: string) => {
    if (path === "/pitch-reels" || path === "/shorts") {
      void loadPitchShortsPage();
    }
  };

  return (
    <div className="ios-tab-bar bg-white/95 dark:bg-neutral800/95 backdrop-blur-xl border-t border-gray-200/50 dark:border-neutral700/50 safe-area-bottom transition-colors">
      <div className="max-w-screen-sm mx-auto px-2 h-16 flex items-center justify-around relative">
        {tabs.map((tab) => (
          <button
            key={tab.path}
            onClick={() => handleTabClick(tab.path)}
            onTouchStart={() => prefetchTab(tab.path)}
            className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 transition-colors relative ${
              isActive(tab.path)
                ? 'text-accent-600 dark:text-accent-400'
                : 'text-gray-500 dark:text-gray-400'
            }`}
          >
            {isActive(tab.path) ? tab.activeIcon : tab.icon}
            <span className="text-[10px] font-medium">{tab.label}</span>
            {isActive(tab.path) && (
              <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 w-6 h-0.5 bg-accent-600 dark:bg-accent-400 rounded-full" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
};

export default IOSTabBar;
