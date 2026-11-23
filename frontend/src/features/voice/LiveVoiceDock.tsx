import React, { useEffect, useRef } from 'react';

import type { LiveVoiceError } from './liveVoice';
import type { BridgeInfo } from './localAgent';
import LiveVoicePanel, { LiveVoicePanelLayout } from './LiveVoicePanel';
import { useConversationMemory } from './useConversationMemory';
import { usePipecatVoiceSession } from './usePipecatVoiceSession';

interface LiveVoiceDockProps {
  autoStart?: boolean;
  blocked?: LiveVoiceError | null;
  layout?: LiveVoicePanelLayout;
  onClose?: () => void;
  /** Connect here instead of Manifest's server, e.g. the local bridge's Pipecat voice. */
  wsUrl?: string;
  /** The setup card found voice on this computer: switch to it. */
  onSetupReady?: (bridge: BridgeInfo) => void;
}

/** Live voice session + panel. Lazy-loaded, so Pipecat never ships in the boot chunks. */
const LiveVoiceDock: React.FC<LiveVoiceDockProps> = ({
  autoStart = true,
  blocked = null,
  layout = 'docked',
  onClose,
  wsUrl,
  onSetupReady,
}) => {
  const session = usePipecatVoiceSession(wsUrl);
  useConversationMemory(session, { local: Boolean(wsUrl) }); // wsUrl: the bridge's own voice
  const { start, end } = session;
  const started = useRef(false);

  useEffect(() => {
    if (!autoStart || blocked || started.current) return;
    started.current = true;
    void start();
  }, [autoStart, blocked, start]);

  const close = onClose
    ? () => {
        void end();
        onClose();
      }
    : undefined;

  return (
    <LiveVoicePanel blocked={blocked} layout={layout} onClose={close} onSetupReady={onSetupReady} session={session} />
  );
};

export default LiveVoiceDock;
