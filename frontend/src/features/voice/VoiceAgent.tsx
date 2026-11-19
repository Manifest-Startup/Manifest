import React, { Suspense, lazy, useEffect, useState } from "react";

import VoiceAgentView from "./VoiceAgentView";
import { useVoiceIdeaSession } from "./useVoiceIdeaSession";
import { fetchLiveVoiceStatus } from "./liveVoice";

const LiveVoiceDock = lazy(() => import("./LiveVoiceDock"));

const StandardVoiceAgent: React.FC = () => {
  const session = useVoiceIdeaSession();
  return <VoiceAgentView session={session} />;
};

/**
 * Full-page voice. Uses Manifest's live (Pipecat) agent when the server offers it for
 * this person, and otherwise the browser STT/TTS idea interview. Until the cheap status
 * probe answers, the standard view renders so there is no flash.
 */
const VoiceAgent: React.FC = () => {
  const [liveAvailable, setLiveAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchLiveVoiceStatus(controller.signal).then(status => {
      if (!controller.signal.aborted) setLiveAvailable(status.available);
    });
    return () => controller.abort();
  }, []);

  if (liveAvailable === true) {
    return (
      <Suspense fallback={null}>
        <LiveVoiceDock autoStart={false} layout="page" />
      </Suspense>
    );
  }
  return <StandardVoiceAgent />;
};

export default VoiceAgent;
