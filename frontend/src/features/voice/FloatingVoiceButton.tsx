import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client/react";
import { useLocation } from "react-router-dom";

import { userVar, voiceOpenRequestVar } from "../core/apollo/localState";
import { isVaultMode } from "features/vault/mode";
import { ariaShortcut, hasMod, shortcutLabel } from "features/ideas/utils/noteFocus";
import "./voicePanel.css";
import { useVoiceIdeaSession } from "./useVoiceIdeaSession";
import { liveVoiceStatus, LiveVoiceError, warmLiveVoice } from "./liveVoice";
import { browserSpeechAvailable, primeVoiceAudio, probeBridge, VOICE_SETUP_COMMAND } from "./localAgent";
import {
  getStoredVoiceMode,
  setStoredVoiceMode,
  VOICE_FULL_AUTO_OPEN_SESSION_KEY,
} from "./voiceLandingStorage";

const VoiceModeSurface = lazy(() => import("./VoiceModeSurface"));
const LiveVoiceDock = lazy(() => import("./LiveVoiceDock"));
const LocalAgentVoiceDock = lazy(() => import("./LocalAgentVoiceDock"));

/** An idea's note has its own voice orb beside the text, so the corner pill steps aside. */
export function hasNoteOrb(pathname: string): boolean {
  const match = pathname.match(/^\/ideas\/([A-Za-z0-9_-]+)(\/description)?\/?$/);
  return Boolean(match && match[1] !== "qualify");
}

function isVoiceWorkspacePath(pathname: string): boolean {
  return pathname === "/ideas" || pathname.startsWith("/ideas/");
}

/** "live" = Manifest's Pipecat agent; "legacy" = the browser STT/TTS idea interview. */
type VoiceEngine =
  | { kind: "live"; blocked: LiveVoiceError | null; wsUrl?: string }
  | { kind: "local" } // the person's own agent via `manifest bridge`; no OpenAI key
  | { kind: "legacy" };

const NO_KEY: LiveVoiceError = {
  kind: "no_api_key",
  message: `Use Claude Code or Codex on this computer (run ${VOICE_SETUP_COMMAND} once), or add your OpenAI key in Settings.`,
};

const VAULT_SIGN_IN: LiveVoiceError = {
  kind: "sign_in",
  message: `Use Claude Code or Codex on this computer (run ${VOICE_SETUP_COMMAND} once), or sign in to use Manifest's voice.`,
};

/**
 * Pick the engine: live voice whenever the server offers it (or only lacks the person's
 * key, which we ask them to add); guests and servers without live voice keep the legacy
 * interview so landing onboarding still works. A vault (local folder, e.g. the installed
 * Chrome app) always uses live voice through the account, and says so when not signed in.
 */
export async function chooseEngine(isGuest: boolean, vault = isVaultMode()): Promise<VoiceEngine> {
  if (isGuest && !vault) return { kind: "legacy" };
  const status = await liveVoiceStatus();
  if (status.available) return { kind: "live", blocked: null };
  // No key (or no account): Claude Code / Codex on this computer can answer instead. Only
  // asked now, so people who have a key never see Chrome's local-network question.
  const bridge = await probeBridge();
  // Natural voice on this Mac: Pipecat with local Whisper + Kokoro, the agent as the brain.
  if (bridge?.voice) return { kind: "live", blocked: null, wsUrl: bridge.voice };
  if (bridge && browserSpeechAvailable()) return { kind: "local" };
  if (status.reason === "no_api_key") {
    return { kind: "live", blocked: NO_KEY };
  }
  if (vault) {
    return {
      kind: "live",
      blocked:
        status.reason === "sign_in"
          ? VAULT_SIGN_IN
          : { kind: "unavailable", message: status.message || "Voice isn't reachable right now." },
    };
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
    primeVoiceAudio(); // still inside the click or key press: lets Safari play the answers
    setIsOpen(true);
    setEngine(await chooseEngine(Boolean(isGuest)));
  }, [isGuest]);

  // The setup card saw voice come up on this computer: pick the engine again and reconnect.
  const [attempt, setAttempt] = useState(0);
  const reconnect = useCallback(async () => {
    setEngine(await chooseEngine(Boolean(isGuest)));
    setAttempt((n) => n + 1);
  }, [isGuest]);
  const onSetupReady = useCallback(() => void reconnect(), [reconnect]);

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

  // ⌥⌘V (Ctrl+Alt+V) opens or closes Manifest voice from anywhere in the app.
  useEffect(() => {
    if (!isLoggedIn || location.pathname === "/login") return;
    const onKey = (event: KeyboardEvent) => {
      if (!hasMod(event) || !event.altKey || event.shiftKey || event.code !== "KeyV") return;
      event.preventDefault();
      if (isOpen) close();
      else void open();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close, isLoggedIn, isOpen, location.pathname, open]);

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
      {!isOpen && !hasNoteOrb(location.pathname) ? (
        <button
          ref={launcherRef}
          aria-keyshortcuts={ariaShortcut("V")}
          aria-label="Start voice conversation"
          className="manifest-voice-launcher fixed z-[120] bottom-[max(1.5rem,calc(env(safe-area-inset-bottom,0px)+5.5rem))] end-[max(1.5rem,env(safe-area-inset-right,0px))] max-sm:bottom-[max(1.25rem,calc(env(safe-area-inset-bottom,0px)+4.25rem))] sm:bottom-[max(1.5rem,env(safe-area-inset-bottom,0px))] sm:end-6"
          data-testid="voice-launcher"
          onClick={() => {
            void open();
          }}
          onFocus={warmLiveVoice}
          onPointerEnter={warmLiveVoice}
          title={`Talk to Manifest (${shortcutLabel("V")})`}
          type="button"
        >
          <span aria-hidden="true" className="manifest-voice-launcher__orb" />
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
              <LiveVoiceDock
                autoStart={!engine.blocked}
                blocked={engine.blocked}
                key={attempt}
                onClose={close}
                onSetupReady={onSetupReady}
                wsUrl={engine.wsUrl}
              />
            </Suspense>
          ) : engine.kind === "local" ? (
            <Suspense fallback={null}>
              <LocalAgentVoiceDock key={attempt} onClose={close} onSetupReady={onSetupReady} />
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
