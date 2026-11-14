import React, { memo, useEffect, useRef, useState } from "react";

import VoiceLiveTranscript from "./VoiceLiveTranscript";
import type { VoiceSessionState } from "./useVoiceIdeaSession";
import "./voicePanel.css";

type VoiceModeSurfaceMode = "overlay" | "page";

export const VoiceMicIcon = () => (
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
);

interface VoiceModeSurfaceProps {
  audioRef: React.RefObject<HTMLAudioElement | null>;
  hasConversationDraft: boolean;
  mode: VoiceModeSurfaceMode;
  landingLayout?: boolean;
  onDismiss?: () => void;
  onEndSession: () => void;
  onOpenWorkspace: () => void;
  onStartSession: () => void | Promise<void>;
  onPauseSession?: () => void;
  onResumeSession?: () => void;
  onSubmitTurn?: () => void;
  onSwitchToWorkspaceMode?: () => void;
  state: VoiceSessionState;
}

const VoiceModeSurface: React.FC<VoiceModeSurfaceProps> = ({
  audioRef,
  hasConversationDraft,
  mode,
  landingLayout = false,
  onDismiss,
  onEndSession,
  onOpenWorkspace,
  onStartSession,
  onPauseSession,
  onResumeSession,
  onSubmitTurn,
  onSwitchToWorkspaceMode,
  state,
}) => {
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isCompact, setIsCompact] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!state.isActive) setIsCompact(false);
  }, [state.isActive]);
  useEffect(() => {
    if (mode === "overlay") closeRef.current?.focus();
  }, [mode]);

  const status = !state.isActive
    ? "Ready to talk"
    : state.isPaused
      ? "Paused · microphone off"
      : state.error
        ? "Needs attention"
        : state.isSpeaking
          ? "Speaking"
          : state.isProcessing
            ? "Thinking…"
            : state.isListening
              ? "Listening"
              : state.currentResponse
                ? "Ready"
                : "Connecting…";
  const showOpenIdea =
    !landingLayout &&
    (state.isQualified || hasConversationDraft || Boolean(state.activeIdeaId));
  const hasTranscript = Boolean(
    state.conversationMessages.length ||
      state.currentMessage ||
      state.interimTranscript,
  );
  const close = () =>
    mode === "overlay" && onDismiss ? onDismiss() : onEndSession();

  return (
    <section
      aria-label="Manifest voice assistant"
      className={`manifest-voice-panel manifest-voice-panel--${mode}${isCompact ? " manifest-voice-panel--compact" : ""}`}
      data-testid="voice-mode-surface"
      role={mode === "overlay" ? "dialog" : "region"}
      aria-modal={mode === "overlay" ? false : undefined}
    >
      <audio ref={audioRef} className="hidden" />
      <header className="manifest-voice-header">
        <div className="manifest-voice-heading">
          <span className="manifest-voice-mark">
            <VoiceMicIcon />
          </span>
          <div>
            <h2>Manifest Voice</h2>
            <p role="status">
              <span
                className={`manifest-voice-dot${state.isActive && !state.isPaused && !state.error ? " manifest-voice-dot--active" : ""}`}
                aria-hidden="true"
              />
              {status}
            </p>
          </div>
        </div>
        <div className="manifest-voice-tools">
          {state.isActive ? (
            <button
              className="manifest-voice-icon"
              type="button"
              aria-label={
                isCompact ? "Expand voice panel" : "Minimize voice panel"
              }
              aria-expanded={!isCompact}
              title={isCompact ? "Expand" : "Minimize"}
              onClick={() => setIsCompact((value) => !value)}
            >
              <svg
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  d={isCompact ? "m7 14 5-5 5 5" : "M6 12h12"}
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          ) : null}
          {mode === "overlay" || state.isActive ? (
            <button
              ref={closeRef}
              className="manifest-voice-icon"
              aria-label={
                mode === "overlay" ? "Close voice mode" : "End voice session"
              }
              title="End conversation"
              onClick={close}
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
                <path
                  d="m6 6 12 12M18 6 6 18"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          ) : null}
        </div>
      </header>

      {/* Keep the audio element mounted when minimized; session controls stay visible. */}
      {!isCompact ? (
        <div className="manifest-voice-body">
          {!state.isActive ? (
            <div className="manifest-voice-intro">
              <h3>
                {landingLayout
                  ? "Start with an idea."
                  : "Talk your idea through."}
              </h3>
              <p>Shape an idea, capture a thought, or ask for a next step.</p>
              <button
                className="manifest-voice-primary"
                onClick={() => void onStartSession()}
                type="button"
              >
                <VoiceMicIcon />
                {landingLayout
                  ? "Use microphone and start"
                  : "Start conversation"}
              </button>
              <p className="manifest-voice-caption">
                Nothing records until you choose to start.
              </p>
            </div>
          ) : hasTranscript ? (
            <VoiceLiveTranscript
              conversationMessages={state.conversationMessages}
              interimTranscript={state.interimTranscript}
              isListening={state.isListening}
              isProcessing={state.isProcessing}
              isSpeaking={state.isSpeaking}
              streamingAssistantText={state.currentMessage.trim()}
            />
          ) : (
            <p className="manifest-voice-empty">
              {state.isPaused
                ? "Resume whenever you’re ready."
                : state.isListening
                  ? "Go ahead. I’m listening."
                  : "Getting the conversation ready…"}
            </p>
          )}
          {isDetailsOpen ? (
            <div className="manifest-voice-details">
              {state.currentResponse?.summary ? (
                <p>{state.currentResponse.summary}</p>
              ) : null}
              <p>Try “create a new idea” or “show my ideas”.</p>
              {onSwitchToWorkspaceMode && !landingLayout ? (
                <button
                  type="button"
                  className="manifest-voice-text-button"
                  aria-label="Continue in workspace without voice next time"
                  onClick={onSwitchToWorkspaceMode}
                >
                  Use workspace by default
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {state.error ? (
        <p className="manifest-voice-alert" role="alert">
          {state.error}
        </p>
      ) : null}
      {state.voiceWarning ? (
        <p className="manifest-voice-alert" role="status">
          {state.voiceWarning}
        </p>
      ) : null}
      {state.isActive ? (
        <footer className="manifest-voice-footer">
          <div className="manifest-voice-tools">
            {onPauseSession && onResumeSession ? (
              <button
                type="button"
                className="manifest-voice-secondary"
                aria-label={
                  state.isPaused
                    ? "Resume voice conversation"
                    : "Pause voice conversation"
                }
                onClick={state.isPaused ? onResumeSession : onPauseSession}
              >
                {state.isPaused ? (
                  <VoiceMicIcon />
                ) : (
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <rect x="4" y="3" width="2" height="10" rx="1" />
                    <rect x="10" y="3" width="2" height="10" rx="1" />
                  </svg>
                )}
                {state.isPaused ? "Resume" : "Pause"}
              </button>
            ) : null}
            <button
              type="button"
              className="manifest-voice-text-button"
              onClick={onEndSession}
            >
              End
            </button>
          </div>
          <div className="manifest-voice-tools">
            {!isCompact ? (
              <button
                type="button"
                className="manifest-voice-icon"
                aria-label={
                  isDetailsOpen ? "Hide session details" : "Session details"
                }
                title="Session details"
                aria-expanded={isDetailsOpen}
                onClick={() => setIsDetailsOpen((value) => !value)}
              >
                <svg
                  width="18"
                  height="18"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle cx="5" cy="12" r="1.5" />
                  <circle cx="12" cy="12" r="1.5" />
                  <circle cx="19" cy="12" r="1.5" />
                </svg>
              </button>
            ) : null}
            {state.isListening && onSubmitTurn ? (
              <button
                className="manifest-voice-text-button"
                type="button"
                onClick={onSubmitTurn}
              >
                Send
              </button>
            ) : showOpenIdea ? (
              <button
                className="manifest-voice-text-button"
                disabled={state.isProcessing}
                onClick={onOpenWorkspace}
                type="button"
              >
                Open idea
              </button>
            ) : null}
          </div>
        </footer>
      ) : null}
      {!isCompact ? (
        <p className="manifest-voice-disclosure">
          AI voice ·{" "}
          {state.voiceMode === "browser"
            ? "Device voice in use"
            : "You can end the conversation anytime"}
        </p>
      ) : null}
    </section>
  );
};

export default memo(VoiceModeSurface);
