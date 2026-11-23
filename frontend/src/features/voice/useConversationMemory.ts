import { useEffect, useRef } from 'react';
import { useApolloClient } from '@apollo/client/react';

import type { PipecatVoiceSessionApi } from './usePipecatVoiceSession';
import { ConversationRecorder, finishConversation } from './voiceMemory';

/**
 * Keep the whole conversation and save it when it ends (ADR 0021): when the session ends or
 * the panel closes, whichever comes first. Saving runs on after the panel is gone.
 */
export function useConversationMemory(session: PipecatVoiceSessionApi, { local }: { local: boolean }): void {
  const apollo = useApolloClient();
  const recorderRef = useRef(new ConversationRecorder());
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const { captions, phase } = session.state;

  const finish = useRef(() => {
    const recorder = recorderRef.current;
    recorderRef.current = new ConversationRecorder(); // a new conversation starts clean
    if (!recorder.heardSomeone) return;
    const agent = local ? sessionRef.current.agentName?.() ?? 'Your agent' : null;
    void finishConversation({ apollo, recorder, localAgent: agent });
  });

  useEffect(() => {
    recorderRef.current.record(captions, session.context.ideaId);
  }, [captions, session.context.ideaId]);

  useEffect(() => {
    if (phase === 'ended') finish.current();
  }, [phase]);

  useEffect(() => () => finish.current(), []);
}
