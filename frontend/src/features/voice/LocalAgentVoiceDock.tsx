import React, { useEffect, useRef } from 'react';

import type { BridgeInfo } from './localAgent';
import LiveVoicePanel, { LiveVoicePanelLayout } from './LiveVoicePanel';
import { useLocalAgentVoiceSession } from './useLocalAgentVoiceSession';

/** Voice with the person's own agent (`manifest bridge`), no OpenAI key; same panel. */
const LocalAgentVoiceDock: React.FC<{
  layout?: LiveVoicePanelLayout;
  onClose?: () => void;
  onSetupReady?: (bridge: BridgeInfo) => void;
}> = ({ layout = 'docked', onClose, onSetupReady }) => {
  const session = useLocalAgentVoiceSession();
  const { start, end } = session;
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  const close = onClose
    ? () => {
        void end();
        onClose();
      }
    : undefined;

  return <LiveVoicePanel layout={layout} onClose={close} onSetupReady={onSetupReady} session={session} />;
};

export default LocalAgentVoiceDock;
