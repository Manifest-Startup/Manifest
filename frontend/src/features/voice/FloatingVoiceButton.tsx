import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client/react";
import { useLocation } from "react-router-dom";

import { userVar, voiceOpenRequestVar } from "../core/apollo/localState";
import "./voicePanel.css";
import { useVoiceIdeaSession } from "./useVoiceIdeaSession";

const VoiceModeSurface = lazy(() => import("./VoiceModeSurface"));
import {
  getStoredVoiceMode,
  setStoredVoiceMode,
  VOICE_FULL_AUTO_OPEN_SESSION_KEY,
} from "./voiceLandingStorage";

function isVoiceWorkspacePath(pathname: string): boolean {
  return pathname === "/ideas" || pathname.startsWith("/ideas/");
}

const FloatingVoiceButton: React.FC = () => {
  const location = useLocation();
  const { isLoggedIn } = useReactiveVar(userVar);
  const openRequestVersion = useReactiveVar(voiceOpenRequestVar);
  const [isOpen, setIsOpen] = useState(false);
  const {
    audioRef,
    state,
    startSession,
    endSession,
    openWorkspace,
    pauseSession,
    resumeSession,
    stopListening,
  } = useVoiceIdeaSession();
  const lastHandledOpenRequestRef = useRef(0);
  const launcherRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
        endSession();
        requestAnimationFrame(() => launcherRef.current?.focus());
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [endSession, isOpen]);

  useEffect(() => {
    if (!isLoggedIn || location.pathname === "/login") {
      return;
    }

    const openFromLanding =
      openRequestVersion > lastHandledOpenRequestRef.current;
    if (openFromLanding) {
      lastHandledOpenRequestRef.current = openRequestVersion;
      setIsOpen(true);
      void startSession();
      return;
    }

    if (!isVoiceWorkspacePath(location.pathname)) {
      return;
    }

    if (getStoredVoiceMode() !== "full") {
      return;
    }

    if (
      typeof sessionStorage !== "undefined" &&
      sessionStorage.getItem(VOICE_FULL_AUTO_OPEN_SESSION_KEY) === "1"
    ) {
      return;
    }

    if (typeof sessionStorage !== "undefined") {
      sessionStorage.setItem(VOICE_FULL_AUTO_OPEN_SESSION_KEY, "1");
    }
    setIsOpen(true);
    void startSession();
  }, [isLoggedIn, location.pathname, openRequestVersion, startSession]);

  if (!isLoggedIn || location.pathname === "/login") {
    return null;
  }

  const openVoiceAgent = async () => {
    setIsOpen(true);
    await startSession();
  };

  const closeVoiceAgent = () => {
    setIsOpen(false);
    endSession();
    requestAnimationFrame(() => launcherRef.current?.focus());
  };

  const switchToWorkspaceMode = () => {
    setStoredVoiceMode("standard");
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.removeItem(VOICE_FULL_AUTO_OPEN_SESSION_KEY);
    }
    closeVoiceAgent();
  };

  return (
    <>
      {!isOpen ? (
        <button
          ref={launcherRef}
          aria-label="Start voice conversation"
          className="manifest-voice-launcher fixed z-[120] bottom-[max(1.5rem,calc(env(safe-area-inset-bottom,0px)+5.5rem))] end-[max(1.5rem,env(safe-area-inset-right,0px))] max-sm:bottom-[max(1.25rem,calc(env(safe-area-inset-bottom,0px)+4.25rem))] sm:bottom-[max(1.5rem,env(safe-area-inset-bottom,0px))] sm:end-6"
          data-testid="voice-launcher"
          onClick={() => {
            void openVoiceAgent();
          }}
          type="button"
        >
          <svg
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <rect x="9" y="3" width="6" height="12" rx="3" strokeWidth="1.6" />
            <path
              d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-3 0h6"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
          <span>Voice</span>
        </button>
      ) : null}

      {isOpen ? (
        <div
          className="pointer-events-none fixed inset-0 z-[110] flex items-end justify-end pt-[max(0.75rem,env(safe-area-inset-top,0px))] pe-[max(0.75rem,env(safe-area-inset-right,0px))] pb-[max(0.75rem,env(safe-area-inset-bottom,0px))] ps-[max(0.75rem,env(safe-area-inset-left,0px))] sm:pt-4 sm:pe-4 sm:pb-4 sm:ps-4"
          data-testid="voice-mode-overlay-shell"
        >
          <Suspense fallback={null}>
            <VoiceModeSurface
              audioRef={audioRef}
              hasConversationDraft={
                Boolean(state.currentResponse?.transcript) ||
                Boolean(state.currentResponse?.voice_note_html) ||
                Boolean(state.activeIdeaId)
              }
              mode="overlay"
              onDismiss={closeVoiceAgent}
              onEndSession={endSession}
              onPauseSession={pauseSession}
              onResumeSession={resumeSession}
              onSubmitTurn={stopListening}
              onOpenWorkspace={openWorkspace}
              onStartSession={startSession}
              onSwitchToWorkspaceMode={switchToWorkspaceMode}
              state={state}
            />
          </Suspense>
        </div>
      ) : null}
    </>
  );
};

export default FloatingVoiceButton;
