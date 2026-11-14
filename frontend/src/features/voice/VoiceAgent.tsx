import React, { useEffect, useState } from "react";

import VoiceAgentView from "./VoiceAgentView";
import { useVoiceIdeaSession } from "./useVoiceIdeaSession";
import { useRealtimeVoiceSession } from "./useRealtimeVoiceSession";
import { fetchRealtimeStatus } from "./voiceAgentApi";

const StandardVoiceAgent: React.FC = () => {
  const session = useVoiceIdeaSession();
  return <VoiceAgentView session={session} />;
};

const RealtimeVoiceAgent: React.FC = () => {
  const session = useRealtimeVoiceSession();
  return <VoiceAgentView session={session} />;
};

/**
 * Chooses the speech-to-speech Realtime pipeline when the backend reports it is
 * enabled (VOICE_REALTIME_ENABLED), and otherwise falls back to the proven
 * streaming TTS pipeline. The probe never mints a token, so it is cheap and
 * safe; until it resolves we render the standard path to avoid any flash.
 */
const VoiceAgent: React.FC = () => {
  const [realtimeEnabled, setRealtimeEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    fetchRealtimeStatus()
      .then(enabled => {
        if (active) {
          setRealtimeEnabled(enabled);
        }
      })
      .catch(() => {
        if (active) {
          setRealtimeEnabled(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (realtimeEnabled === true) {
    return <RealtimeVoiceAgent />;
  }
  return <StandardVoiceAgent />;
};

export default VoiceAgent;
