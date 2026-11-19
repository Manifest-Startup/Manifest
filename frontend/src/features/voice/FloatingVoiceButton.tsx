import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client/react";
import { useLocation } from "react-router-dom";

import { userVar, voiceOpenRequestVar } from "../core/apollo/localState";
import "./voicePanel.css";
import { useVoiceIdeaSession } from "./useVoiceIdeaSession";
import { fetchLiveVoiceStatus, LiveVoiceError } from "./liveVoice";
import {
  getStoredVoiceMode,
  setStoredVoiceMode,
  VOICE_FULL_AUTO_OPEN_SESSION_KEY,
} from "./voiceLandingStorage";

const VoiceModeSurface = lazy(() => import("./VoiceModeSurface"));
const LiveVoiceDock = lazy(() => import("./LiveVoiceDock"));

function isVoiceWorkspacePath(pathname: string): boolean {
  return pathname === "/ideas" || pathname.startsWith("/ideas/");
}

/** "live" = Manifest's Pipecat agent; "legacy" = the browser STT/TTS idea interview. */
type VoiceEngine = { kind: "live"; blocked: LiveVoiceError | null } | { kind: "legacy" };

const NO_KEY: LiveVoiceError = {
  kind: "no_api_key",
  message: "Voice runs on your own OpenAI key. Add it once in Account → AI settings, then just talk.",
};

/**
 * Pick the engine: live voice whenever the server offers it (or only lacks the person's
 * key, which we ask them to add); guests and servers without live voice keep the legacy
 * interview so landing onboarding still works.
 */
async function chooseEngine(isGuest: boolean): Promise<VoiceEngine> {
  if (isGuest) return { kind: "legacy" };
  const status = await fetchLiveVoiceStatus();
  if (status.available) return { kind: "live", blocked: null };
  if (status.reason === "no_api_key") {
    return { kind: "live", blocked: status.message ? { ...NO_KEY, message: status.message } : NO_KEY };
  }
  return { kind: "legacy" };
}

const LegacyVoiceOverlay: React.FC<{ onClose: () => void; onSwitchToWorkspace: () => void }> = ({
  onClose,
  onSwitchToWorkspace,
}) => {
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
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void startSession();
  }, [startSession]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        endSession();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [endSession, onClose]);

  const close = () => {
    endSession();
    onClose();
  };

  return (
    <Suspense fallback={null}>
      <VoiceModeSurface
        audioRef={audioRef}
        hasConversationDraft={
          Boolean(state.currentResponse?.transcript) ||
          Boolean(state.currentResponse?.voice_note_html) ||
          Boolean(state.activeIdeaId)
        }
        mode="overlay"
        onDismiss={close}
        onEndSession={endSession}
        onPauseSession={pauseSession}
        onResumeSession={resumeSession}
        onSubmitTurn={stopListening}
        onOpenWorkspace={openWorkspace}
        onStartSession={startSession}
        onSwitchToWorkspaceMode={() => {
          endSession();
          onSwitchToWorkspace();
        }}
        state={state}
      />
    </Suspense>
  );
};

const FloatingVoiceButton: React.FC = () => {
  const location = useLocation();
  const { isLoggedIn, isGuest } = useReactiveVar(userVar);
  const openRequestVersion = useReactiveVar(voiceOpenRequestVar);
  const [engine, setEngine] = useState<VoiceEngine | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const lastHandledOpenRequestRef = useRef(0);
  const launcherRef = useRef<HTMLButtonElement>(null);

  const open = useCallback(async () => {
    setIsOpen(true);
    setEngine(await chooseEngine(Boolean(isGuest)));
  }, [isGuest]);

  const close = useCallback(() => {
    setIsOpen(false);
    setEngine(null);
    requestAnimationFrame(() => launcherRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!isLoggedIn || location.pathname === "/login") {
      return;
    }

    const openFromLanding = openRequestVersion > lastHandledOpenRequestRef.current;
    if (openFromLanding) {
      lastHandledOpenRequestRef.current = openRequestVersion;
      void open();
      return;
    }

    if (!isVoiceWorkspacePath(location.pathname) || getStoredVoiceMode() !== "full") {
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
    void open();
  }, [isLoggedIn, location.pathname, openRequestVersion, open]);

  if (!isLoggedIn || location.pathname === "/login") {
    return null;
  }

  const switchToWorkspaceMode = () => {
    setStoredVoiceMode("standard");
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.removeItem(VOICE_FULL_AUTO_OPEN_SESSION_KEY);
    }
    close();
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
            void open();
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

      {isOpen && engine ? (
        <div
          className="pointer-events-none fixed inset-0 z-[110] flex items-end justify-end pt-[max(0.75rem,env(safe-area-inset-top,0px))] pe-[max(0.75rem,env(safe-area-inset-right,0px))] pb-[max(0.75rem,env(safe-area-inset-bottom,0px))] ps-[max(0.75rem,env(safe-area-inset-left,0px))] sm:pt-4 sm:pe-4 sm:pb-4 sm:ps-4"
          data-testid="voice-mode-overlay-shell"
        >
          {engine.kind === "live" ? (
            <Suspense fallback={null}>
              <LiveVoiceDock autoStart={!engine.blocked} blocked={engine.blocked} onClose={close} />
            </Suspense>
          ) : (
            <LegacyVoiceOverlay onClose={close} onSwitchToWorkspace={switchToWorkspaceMode} />
          )}
        </div>
      ) : null}
    </>
  );
};

export default FloatingVoiceButton;
