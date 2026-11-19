import React, { useEffect, useRef } from 'react';

import type { LiveVoiceError } from './liveVoice';
import LiveVoicePanel, { LiveVoicePanelLayout } from './LiveVoicePanel';
import { usePipecatVoiceSession } from './usePipecatVoiceSession';

interface LiveVoiceDockProps {
  autoStart?: boolean;
  blocked?: LiveVoiceError | null;
  layout?: LiveVoicePanelLayout;
  onClose?: () => void;
}

/** Live voice session + panel. Lazy-loaded, so Pipecat never ships in the boot chunks. */
const LiveVoiceDock: React.FC<LiveVoiceDockProps> = ({ autoStart = true, blocked = null, layout = 'docked', onClose }) => {
  const session = usePipecatVoiceSession();
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

  return <LiveVoicePanel blocked={blocked} layout={layout} onClose={close} session={session} />;
};

export default LiveVoiceDock;
