import React, { Suspense, lazy } from "react";
import { useNavigate } from "react-router-dom";

import { setStoredVoiceMode } from "./voiceLandingStorage";
import type { VoiceIdeaSessionApi } from "./useVoiceIdeaSession";

const VoiceModeSurface = lazy(() => import("./VoiceModeSurface"));

export interface VoiceAgentViewProps {
  session: Omit<VoiceIdeaSessionApi, "pauseSession" | "resumeSession"> &
    Partial<Pick<VoiceIdeaSessionApi, "pauseSession" | "resumeSession">>;
  landingLayout?: boolean;
}

const VoiceAgentView: React.FC<VoiceAgentViewProps> = ({
  session,
  landingLayout,
}) => {
  const navigate = useNavigate();
  const { audioRef, state, startSession, endSession, openWorkspace } = session;

  const switchToWorkspaceMode = () => {
    setStoredVoiceMode("standard");
    endSession();
    navigate("/ideas");
  };

  const handleStartSession = async () => {
    if (landingLayout) {
      setStoredVoiceMode("full");
    }
    await startSession();
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
        landingLayout={landingLayout}
        mode="page"
        onEndSession={endSession}
        onPauseSession={session.pauseSession}
        onResumeSession={session.resumeSession}
        onSubmitTurn={session.stopListening}
        onOpenWorkspace={openWorkspace}
        onStartSession={handleStartSession}
        onSwitchToWorkspaceMode={switchToWorkspaceMode}
        state={state}
      />
    </Suspense>
  );
};

export default VoiceAgentView;
